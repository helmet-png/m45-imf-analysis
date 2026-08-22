#!/usr/bin/env python
"""Small injection/recovery check for a mass-dependent binary fraction.

This is intentionally not a new M45 fit.  It makes deterministic fake CMDs,
where only the injected binary probability changes with primary-star mass,
then fits them with the unchanged constant-f_bin likelihood on a coarse grid.
The resulting alpha shift is a screening diagnostic, not an uncertainty for
the published M45 result.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.step3_age import draw_randoms                   # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402

THETA_TRUE = np.array([8.15, 0.15, 0.45, 2.35, 0.00, -0.50])


def make_fake(model, theta, n_stars, n_gen, seed, selection, profile):
    """Generate a selected fake catalogue without touching the base model."""
    gen = copy.copy(model)
    gen.n_syn = n_gen
    gen.draws = draw_randoms(n_gen, np.random.default_rng(seed))
    gen.selection = selection
    gen.binary_fraction_profile = profile
    color, mag, binary = gen.synthesise(theta, return_binary_flag=True)
    if len(color) < n_stars:
        raise RuntimeError(f"Only {len(color)} selected synthetic stars; need {n_stars}")
    pick = np.random.default_rng(seed + 1000).choice(len(color), n_stars,
                                                       replace=False)
    return color[pick], mag[pick], binary[pick]


def best_constant_fit(model, fbin_grid, alpha_grid):
    """Profile only f_bin and alpha; the other injection inputs stay fixed."""
    rows = []
    for fbin in fbin_grid:
        for alpha in alpha_grid:
            theta = THETA_TRUE.copy()
            theta[2], theta[3] = fbin, alpha
            rows.append((float(model.log_likelihood(theta)), float(fbin),
                         float(alpha)))
    best = max(rows, key=lambda x: x[0])
    second = sorted(rows, reverse=True)[:5]
    return {"loglike": best[0], "fbin": best[1], "alpha": best[2],
            "top5": [{"loglike": x[0], "fbin": x[1], "alpha": x[2]}
                     for x in second]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat")
    ap.add_argument("--n-stars", type=int, default=1078)
    ap.add_argument("--n-gen", type=int, default=80000)
    ap.add_argument("--n-syn", type=int, default=8000)
    ap.add_argument("--output", default="results/mass_dependent_fbin_smoke.json")
    args = ap.parse_args()

    cfg = cfgmod.load(ROOT / "config.toml")
    clean = Table.read(ROOT / "data" / "cmd_members.csv", format="csv")
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    good = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[good], mag[good]
    plx = np.asarray(clean["parallax"], float)[good]
    dm = 5.0 * np.log10(1000.0 / (np.median(plx)
                                  - cfg.step3_age.parallax_zero_point)) - 5.0
    errmodel = dict(np.load(ROOT / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / args.grid)
    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    selection = selmod.load(ROOT / "data" / "selection.npz")
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    base.selection = selection

    # The break is deliberately within the well-populated CMD range.  The
    # two cases are illustrative strengths, not a measured binary law.
    profiles = {
        "constant_0.45": None,
        "mild_low0.35_high0.65_at0.8Msun": (0.8, 0.35, 0.65),
        "strong_low0.20_high0.80_at0.8Msun": (0.8, 0.20, 0.80),
    }
    fbin_grid = np.arange(0.15, 0.901, 0.10)
    alpha_grid = np.arange(1.75, 2.951, 0.15)
    results = {}
    for name, profile in profiles.items():
        fake_c, fake_g, fake_binary = make_fake(
            # The same random stream makes the constant case a genuine
            # control: differences are then caused by the profile rather
            # than a separately drawn fake cluster.
            base, THETA_TRUE, args.n_stars, args.n_gen, 2200,
            selection, profile)
        fit = joint_fit.JointModel(cfg, fake_c, fake_g, grid, errmodel, dm)
        fit.selection = selection
        recovered = best_constant_fit(fit, fbin_grid, alpha_grid)
        results[name] = {
            "injected_profile": profile,
            "selected_fake_stars": int(len(fake_c)),
            "realised_selected_binary_fraction": float(fake_binary.mean()),
            "constant_model_recovery": recovered,
            "alpha_shift_from_injected": float(recovered["alpha"] - THETA_TRUE[3]),
        }

    control_alpha = results["constant_0.45"]["constant_model_recovery"]["alpha"]
    for name, item in results.items():
        item["alpha_shift_relative_to_constant_control"] = float(
            item["constant_model_recovery"]["alpha"] - control_alpha)

    payload = {
        "status": "coarse_smoke_diagnostic_not_headline_fit",
        "purpose": "Screen alpha sensitivity to an unmodelled mass-dependent binary fraction.",
        "true_theta": {k: float(v) for k, v in zip(joint_fit.PARAM_NAMES, THETA_TRUE)},
        "fixed_parameters_in_recovery": ["logage", "A_V", "MH", "q_gamma"],
        "fitted_grid": {"f_bin": fbin_grid.tolist(), "alpha": alpha_grid.tolist()},
        "n_stars": args.n_stars, "n_gen_for_injection": args.n_gen,
        "n_syn_per_likelihood": args.n_syn, "profiles": results,
        "limits": [
            "One deterministic fake catalogue per profile; no sampling error bar.",
            "The two mass-dependent profiles are examples, not a measured M45 law.",
            "A coarse grid is for direction and scale only; it does not replace a joint fit.",
            "Compare profiles against constant_0.45, not directly against the injected alpha: the control itself reveals finite-catalogue and grid recovery error.",
        ],
    }
    out = ROOT / args.output
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: {"alpha": v["constant_model_recovery"]["alpha"],
                          "alpha_shift": v["alpha_shift_from_injected"],
                          "fbin": v["constant_model_recovery"]["fbin"]}
                      for k, v in results.items()}, indent=2))


if __name__ == "__main__":
    main()
