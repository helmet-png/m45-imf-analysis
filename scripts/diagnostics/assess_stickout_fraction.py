# -*- coding: utf-8 -*-
"""Assess whether CMD "stick-out" stars could constrain ``f_bin``.

This is deliberately a *diagnostic*, not an IMF fit.  It reads the completed
``p2final_v3`` samples and generates small deterministic synthetic catalogues
with the same selection function.  The aim is to quantify the mapping between
the observable CMD-offset fraction and the model's intrinsic system-binary
fraction before anyone considers adding a new likelihood term.

The CMD-offset count comes from the same CMD used by the Hess likelihood.  It
therefore must not be multiplied into the current likelihood as an independent
binomial likelihood without a joint/calibrated treatment; that would count the
same information twice.  This program measures usefulness and risks only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.step3_age import _Ext                           # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402


def _fraction(n_flag: int, n_total: int) -> dict:
    """Return a fraction and its simple binomial counting uncertainty."""
    f = n_flag / n_total if n_total else float("nan")
    se = np.sqrt(f * (1.0 - f) / n_total) if n_total else float("nan")
    return {"n_flag": int(n_flag), "n_eligible": int(n_total),
            "fraction": float(f), "binomial_se": float(se)}


def _flag_cmd_offset(obs_color, obs_mag, iso, dm, av, ext, threshold):
    """Numerical equivalent of step4_binaries.flag_cmd_offset.

    It is repeated locally instead of importing that module because the
    diagnostic's small SciPy environment deliberately does not install the
    unrelated Astropy dependency used by the older population-fit wrapper.
    """
    c_iso = (np.asarray(iso["G_BP_fSBmag"], float)
             - np.asarray(iso["G_RP_fSBmag"], float)
             + (ext.bp - ext.rp) * av)
    g_iso = np.asarray(iso["G_fSBmag"], float) + dm + ext.g * av
    order = np.argsort(c_iso)
    g_expect = np.interp(obs_color, c_iso[order], g_iso[order],
                         left=np.nan, right=np.nan)
    return np.nan_to_num(g_expect - obs_mag, nan=-99.0) > threshold


def _cmd_offset_flags(color, mag, grid, theta, dm, ext, threshold):
    iso = isomod.isochrone_at(grid, float(theta[0]), float(theta[4]))
    flags = _flag_cmd_offset(color, mag, iso, dm, float(theta[1]), ext,
                             threshold)
    # ``flag_cmd_offset`` makes extrapolated points False.  Count only the
    # in-range ones so that the denominator is the same physical CMD region.
    c_iso = (np.asarray(iso["G_BP_fSBmag"], float)
             - np.asarray(iso["G_RP_fSBmag"], float)
             + (ext.bp - ext.rp) * float(theta[1]))
    inside = ((np.asarray(color, float) >= np.nanmin(c_iso))
              & (np.asarray(color, float) <= np.nanmax(c_iso)))
    return flags, inside


def _one_model(model, grid, theta, threshold, ext):
    syn = model.synthesise(theta, return_binary_flag=True)
    if syn is None:
        raise RuntimeError("Synthetic catalogue has fewer than 50 selected stars")
    color, mag, true_binary = syn
    flags, inside = _cmd_offset_flags(color, mag, grid, theta, model.dm, ext,
                                      threshold)
    fso = _fraction(int((flags & inside).sum()), int(inside.sum()))
    detected = flags & inside
    true_in = true_binary & inside
    fso.update({
        "selected_stars": int(len(color)),
        "true_binary_fraction_selected": float(true_binary.mean()),
        "cmd_offset_precision": float((detected & true_binary).sum()
                                      / max(int(detected.sum()), 1)),
        "cmd_offset_recall": float((detected & true_binary).sum()
                                   / max(int(true_in.sum()), 1)),
    })
    return fso


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default="results/fit_real_p2final_v3.npz")
    # This is the grid recorded for the completed p2_final2_v3 run in
    # WORK_BOARD.md.  Keeping it explicit prevents silently snapping the
    # 106 Myr solution to an unrelated cached grid.
    ap.add_argument("--grid", default="parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat")
    ap.add_argument("--n-syn", type=int, default=40000,
                    help="Small diagnostic catalogue size; this does not fit.")
    ap.add_argument("--output", default="results/stickout_fraction_assessment_p2final_v3.json")
    args = ap.parse_args()

    cfg = cfgmod.load(ROOT / "config.toml")
    clean = Table.read(ROOT / "data" / "cmd_members.csv", format="csv")
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    plx = np.asarray(clean["parallax"], float)[ok]
    dm = 5.0 * np.log10(1000.0 / (np.median(plx)
                                  - cfg.step3_age.parallax_zero_point)) - 5.0
    errmodel = dict(np.load(ROOT / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / args.grid)
    samples = np.asarray(np.load(ROOT / args.result)["C"], float)
    if samples.ndim != 2 or samples.shape[1] < 7:
        raise ValueError("Expected completed config-C samples with seven parameters")
    theta_ref = np.mean(samples, axis=0)
    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    model = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    model.selection = selmod.load(ROOT / "data" / "selection.npz")
    model.enable_dav_fit(0.0, 0.6)
    ext = _Ext(cfg.step2_cmd.ext_coeff_g, cfg.step2_cmd.ext_coeff_bp,
               cfg.step2_cmd.ext_coeff_rp)
    threshold = 0.5 * float(cfg.step2_cmd.binary_offset_mag)

    obs_flags, obs_inside = _cmd_offset_flags(color, mag, grid, theta_ref, dm,
                                               ext, threshold)
    observed = _fraction(int((obs_flags & obs_inside).sum()),
                         int(obs_inside.sum()))

    # A coarse monotonicity test around the completed solution, then the ten
    # already-completed repeats.  No optimiser or new posterior is run here.
    grid_results = {}
    for fbin in (0.2, 0.4, 0.6, 0.8, 1.0):
        theta = theta_ref.copy()
        theta[2] = fbin
        grid_results[f"{fbin:.1f}"] = _one_model(model, grid, theta,
                                                   threshold, ext)
    repeat_results = [_one_model(model, grid, row, threshold, ext)
                      for row in samples]
    repeat_fso = np.asarray([r["fraction"] for r in repeat_results])
    slope = ((grid_results["0.8"]["fraction"]
              - grid_results["0.2"]["fraction"]) / 0.6)
    output = {
        "status": "diagnostic_only_not_an_independent_likelihood",
        "source_result": str(args.result),
        "n_completed_repeats": int(len(samples)),
        "n_syn_per_diagnostic": int(args.n_syn),
        "cmd_offset_threshold_mag": threshold,
        "distance_modulus": float(dm),
        "reference_theta_mean": {k: float(v) for k, v in zip(
            ["logage", "A_V", "f_bin", "alpha", "MH", "q_gamma", "dav"],
            theta_ref)},
        "observed_cmd_offset": observed,
        "fixed_other_parameters_fbin_grid": grid_results,
        "completed_repeat_predictions": repeat_results,
        "repeat_prediction_fraction_mean": float(repeat_fso.mean()),
        "repeat_prediction_fraction_min": float(repeat_fso.min()),
        "repeat_prediction_fraction_max": float(repeat_fso.max()),
        "coarse_sensitivity_dfso_dfbin": float(slope),
        "interpretation": [
            "The CMD-offset fraction is an observable proxy, not f_bin itself.",
            "It is affected by q_gamma, errors, extinction, the isochrone and selection.",
            "It uses the same CMD as the Hess likelihood, so a separate binomial term would double-count unless a joint/calibrated likelihood replaces or conditions the Hess information.",
        ],
    }
    out = ROOT / args.output
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(json.dumps({
        "observed_fso": observed["fraction"],
        "predicted_fso_mean": output["repeat_prediction_fraction_mean"],
        "predicted_fso_range": [output["repeat_prediction_fraction_min"],
                                output["repeat_prediction_fraction_max"]],
        "dfso_dfbin": slope,
        "output": str(out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
