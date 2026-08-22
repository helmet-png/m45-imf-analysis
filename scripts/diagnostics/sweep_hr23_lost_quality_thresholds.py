#!/usr/bin/env python
"""Candidate-only threshold sweep for 62 HR23 stars excluded after membership."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipeline import config as cfgmod  # noqa: E402

MAG_ERR_COEF = 2.5 / np.log(10)


def expected_excess(color):
    c = np.asarray(color, float)
    return np.where(c < 0.5, 1.154360 + 0.033772*c + 0.032277*c**2,
                    np.where(c < 4.0, 1.162004 + 0.011464*c + 0.049255*c**2
                             - 0.005879*c**3, 1.057572 + 0.140537*c))


def excess_sigma(g):
    return 0.0059898 + 8.817481e-12 * np.asarray(g, float)**7.618399


def main():
    with (ROOT / "data" / "hr23_passprob_notcmd_gaia_photometry.csv").open(
            newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 62:
        raise RuntimeError(f"Expected 62 candidates, found {len(rows)}")
    def col(name):
        return np.asarray([float(row[name]) if row[name] not in ("", "null") else np.nan
                           for row in rows])
    cfg = cfgmod.load(ROOT / "config.toml").step2_cmd
    g, color = col("phot_g_mean_mag"), col("bp_rp")
    gsnr = col("phot_g_mean_flux_over_error")
    bpsnr = col("phot_bp_mean_flux_over_error")
    rpsnr = col("phot_rp_mean_flux_over_error")
    residual_sigma = np.abs(col("phot_bp_rp_excess_factor") - expected_excess(color)) / excess_sigma(g)
    fixed = (np.isfinite(g) & (g >= cfg.g_bright_limit) & np.isfinite(gsnr)
             & (gsnr >= cfg.min_flux_snr_g) & np.isfinite(rpsnr)
             & (rpsnr >= cfg.min_flux_snr_rp))

    scenarios = []
    for bp_limit in (10.0, 15.0, 20.0):
        for excess_limit in (3.0, 5.0):
            keep = (fixed & np.isfinite(bpsnr) & (bpsnr >= bp_limit)
                    & np.isfinite(residual_sigma) & (residual_sigma < excess_limit))
            bp_error = MAG_ERR_COEF / bpsnr[keep]
            scenarios.append({
                "bp_snr_limit": bp_limit, "excess_sigma_limit": excess_limit,
                "recovered_of_62": int(keep.sum()),
                "recovered_G16_to_18": int((keep & (g >= 16) & (g < 18)).sum()),
                "recovered_bp_mag_error_median": float(np.median(bp_error)) if len(bp_error) else None,
                "recovered_bp_mag_error_max": float(np.max(bp_error)) if len(bp_error) else None,
                "source_ids": [rows[i]["source_id"] for i in np.flatnonzero(keep)],
            })
    output = {
        "status": "candidate_only_threshold_sensitivity_not_a_new_selection_function",
        "candidate_count": len(rows), "scenarios": scenarios,
        "limits": [
            "Counts apply only to the 62 traced HR23 candidates, not to all Gaia sources or contaminants.",
            "Recovering more external candidates does not establish that their colours are unbiased.",
            "No IMF, selection function or membership model was rerun.",
        ],
    }
    out = ROOT / "results" / "hr23_lost_quality_threshold_sweep.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(scenarios, indent=2))


if __name__ == "__main__":
    main()
