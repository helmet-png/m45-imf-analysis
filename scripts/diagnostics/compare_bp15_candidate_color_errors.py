#!/usr/bin/env python
"""Compare colour errors for BP15-recovered HR23 candidates and current CMD stars."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MAG_ERR_COEF = 2.5 / np.log(10)


def expected_excess(color):
    c = np.asarray(color, float)
    return np.where(
        c < 0.5,
        1.154360 + 0.033772*c + 0.032277*c**2,
        np.where(
            c < 4.0,
            1.162004 + 0.011464*c + 0.049255*c**2 - 0.005879*c**3,
            1.057572 + 0.140537*c,
        ),
    )


def excess_sigma(g):
    return 0.0059898 + 8.817481e-12 * np.asarray(g, float)**7.618399


def load(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def column(rows, name):
    return np.asarray([
        float(row[name]) if row.get(name, "") not in ("", "null") else np.nan
        for row in rows
    ])


def describe(rows, mask):
    bp_snr = column(rows, "phot_bp_mean_flux_over_error")[mask]
    rp_snr = column(rows, "phot_rp_mean_flux_over_error")[mask]
    bp_error = MAG_ERR_COEF / bp_snr
    rp_error = MAG_ERR_COEF / rp_snr
    colour_error = np.hypot(bp_error, rp_error)

    def stats(values):
        return {
            "median": float(np.median(values)),
            "p90": float(np.percentile(values, 90)),
            "max": float(np.max(values)),
        }

    return {
        "n": int(mask.sum()),
        "bp_mag_error": stats(bp_error),
        "rp_mag_error": stats(rp_error),
        "bp_rp_colour_error": stats(colour_error),
    }


def main():
    candidates = load(ROOT / "data" / "hr23_passprob_notcmd_gaia_photometry.csv")
    cmd = load(ROOT / "data" / "cmd_members.csv")
    if len(candidates) != 62:
        raise RuntimeError(f"Expected 62 traced candidates, found {len(candidates)}")

    g = column(candidates, "phot_g_mean_mag")
    colour = column(candidates, "bp_rp")
    g_snr = column(candidates, "phot_g_mean_flux_over_error")
    bp_snr = column(candidates, "phot_bp_mean_flux_over_error")
    rp_snr = column(candidates, "phot_rp_mean_flux_over_error")
    residual_sigma = np.abs(
        column(candidates, "phot_bp_rp_excess_factor") - expected_excess(colour)
    ) / excess_sigma(g)
    recovered = (
        np.isfinite(g) & (g >= 16) & (g < 18)
        & np.isfinite(g_snr) & (g_snr >= 50)
        & np.isfinite(bp_snr) & (bp_snr >= 15)
        & np.isfinite(rp_snr) & (rp_snr >= 20)
        & np.isfinite(residual_sigma) & (residual_sigma < 3)
    )
    if recovered.sum() != 16:
        raise RuntimeError(f"Expected BP15/3sigma to recover 16, found {recovered.sum()}")

    cmd_g = column(cmd, "phot_g_mean_mag")
    cmd_mask = (
        np.isfinite(cmd_g) & (cmd_g >= 16) & (cmd_g < 18)
        & np.isfinite(column(cmd, "phot_bp_mean_flux_over_error"))
        & np.isfinite(column(cmd, "phot_rp_mean_flux_over_error"))
    )
    recovered_stats = describe(candidates, recovered)
    cmd_stats = describe(cmd, cmd_mask)
    ratio = (
        recovered_stats["bp_rp_colour_error"]["median"]
        / cmd_stats["bp_rp_colour_error"]["median"]
    )
    output = {
        "status": "candidate_error_comparison_not_selection_validation",
        "selection_tested": "G16-18, G_SNR>=50, BP_SNR>=15, RP_SNR>=20, excess<3sigma",
        "bp15_recovered_hr23_candidates": recovered_stats,
        "current_cmd_members_G16_to_18": cmd_stats,
        "median_colour_error_ratio_candidate_over_cmd": float(ratio),
        "recovered_source_ids": [
            candidates[i]["source_id"] for i in np.flatnonzero(recovered)
        ],
        "limits": [
            "The comparison uses only known HR23 candidates and cannot measure contamination.",
            "HR23 membership is an external reference, not ground truth.",
            "Magnitude errors are flux-SNR approximations and omit covariance/systematics.",
            "No membership model, selection function, forward model or IMF was rerun.",
        ],
    }
    out = ROOT / "results" / "hr23_bp15_colour_error_comparison.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
