#!/usr/bin/env python
"""Summarise an existing mass-dependent-fbin injection result without rerunning it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="results/mass_dependent_fbin_matched_fast.json")
    ap.add_argument("--output", default="results/mass_dependent_fbin_matched_fast_summary.json")
    ap.add_argument("--headline-sigma", type=float, default=0.144)
    args = ap.parse_args()

    source = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    summaries = {}
    for name, profile in source["profiles"].items():
        shifts = np.asarray([t["alpha_shift_relative_to_constant_control"]
                             for t in profile["trials"]], float)
        selected_fbin = np.asarray([t["realised_selected_binary_fraction"]
                                    for t in profile["trials"]], float)
        n = len(shifts)
        mean = float(shifts.mean())
        sd = float(shifts.std(ddof=1)) if n > 1 else None
        sem = float(sd / np.sqrt(n)) if n > 1 else None
        if n > 1 and sem > 0.0:
            ci = stats.t.interval(0.95, n - 1, loc=mean, scale=sem)
        elif n > 1:
            ci = (mean, mean)
        else:
            ci = (None, None)
        summaries[name] = {
            "n_trials": n,
            "alpha_shift_mean": mean,
            "alpha_shift_median": float(np.median(shifts)),
            "alpha_shift_sd": sd,
            "alpha_shift_sem": sem,
            "alpha_shift_95pct_t_interval": [float(ci[0]), float(ci[1])]
            if n > 1 else [None, None],
            "fraction_abs_shift_ge_headline_sigma": float(
                np.mean(np.abs(shifts) >= args.headline_sigma)),
            "selected_binary_fraction_mean": float(selected_fbin.mean()),
            "selected_binary_fraction_sd": float(selected_fbin.std(ddof=1))
            if n > 1 else None,
        }

    output = {
        "status": "fixed_nuisance_medium_cost_gate_not_formal_7d_recovery",
        "source": args.input,
        "headline_alpha_sigma_reference": args.headline_sigma,
        "summaries": summaries,
        "interpretation_limits": [
            "The injected primary-mass-weighted mean f_bin is fixed before photometric selection.",
            "The selected binary fraction may differ because binarity and mass affect detectability.",
            "Age, extinction, metallicity and q_gamma were fixed; this cannot replace the pending full seven-parameter recovery on branch mass-dep-fbin.",
            "The 95% intervals describe variability across these 20 deterministic fake catalogues, not a measured M45 systematic uncertainty.",
        ],
    }
    out = ROOT / args.output
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
