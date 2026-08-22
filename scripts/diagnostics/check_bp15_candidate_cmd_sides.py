#!/usr/bin/env python
"""Locate BP15-recovered HR23 candidates relative to the empirical CMD locus."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MAG_ERR_COEF = 2.5 / np.log(10)
WINDOW = 0.25


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row, name):
    value = row.get(name, "")
    return float(value) if value not in ("", "null") else np.nan


def main():
    gate = json.loads(
        (ROOT / "results" / "hr23_bp15_colour_error_comparison.json")
        .read_text(encoding="utf-8")
    )
    wanted = set(gate["recovered_source_ids"])
    candidates = [
        row for row in load_csv(ROOT / "data" / "hr23_passprob_notcmd_gaia_photometry.csv")
        if row["source_id"] in wanted
    ]
    cmd = load_csv(ROOT / "data" / "cmd_members.csv")
    cmd_g = np.asarray([number(row, "phot_g_mean_mag") for row in cmd])
    cmd_colour = np.asarray([number(row, "bp_rp") for row in cmd])

    stars = []
    for row in candidates:
        g = number(row, "phot_g_mean_mag")
        colour = number(row, "bp_rp")
        local = cmd_colour[
            np.isfinite(cmd_g) & np.isfinite(cmd_colour) & (np.abs(cmd_g - g) <= WINDOW)
        ]
        if len(local) < 10:
            raise RuntimeError(f"Only {len(local)} local CMD stars near G={g:.3f}")
        median = float(np.median(local))
        residual = colour - median
        percentile = float(np.mean(local <= colour))
        bp_error = MAG_ERR_COEF / number(row, "phot_bp_mean_flux_over_error")
        rp_error = MAG_ERR_COEF / number(row, "phot_rp_mean_flux_over_error")
        colour_error = float(np.hypot(bp_error, rp_error))
        stars.append({
            "source_id": row["source_id"],
            "g": g,
            "bp_rp": colour,
            "local_cmd_n": int(len(local)),
            "local_cmd_colour_median": median,
            "colour_residual_from_local_median": float(residual),
            "local_colour_percentile": percentile,
            "colour_error_from_snr": colour_error,
            "side": "red" if residual > 0 else "blue",
            "side_is_robust_at_1sigma": bool(abs(residual) > colour_error),
        })

    residuals = np.asarray([star["colour_residual_from_local_median"] for star in stars])
    percentiles = np.asarray([star["local_colour_percentile"] for star in stars])
    output = {
        "status": "candidate_cmd_location_not_selection_validation",
        "empirical_reference": f"current CMD members within +/-{WINDOW:.2f} mag in G",
        "candidate_count": len(stars),
        "red_of_local_median": int((residuals > 0).sum()),
        "blue_of_local_median": int((residuals < 0).sum()),
        "robust_side_at_1sigma": int(sum(star["side_is_robust_at_1sigma"] for star in stars)),
        "redder_than_local_90th_percentile": int((percentiles >= 0.9).sum()),
        "bluer_than_local_10th_percentile": int((percentiles <= 0.1).sum()),
        "colour_residual_median": float(np.median(residuals)),
        "colour_residual_min": float(np.min(residuals)),
        "colour_residual_max": float(np.max(residuals)),
        "stars": sorted(stars, key=lambda star: star["g"]),
        "limits": [
            "The current CMD sample is a descriptive reference, not an unbiased single-star locus.",
            "The local comparison includes binaries and any remaining contaminants.",
            "Candidate membership and background contamination are not established here.",
            "No selection function, membership model, forward model or IMF was rerun.",
        ],
    }
    out = ROOT / "results" / "hr23_bp15_candidate_cmd_sides.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "stars"}, indent=2))


if __name__ == "__main__":
    main()
