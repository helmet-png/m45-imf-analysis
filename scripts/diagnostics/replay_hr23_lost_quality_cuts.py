#!/usr/bin/env python
"""Replay step2 photometric-quality cuts for the traced 62 HR23 stars."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
BINS = [(-float("inf"), 4.0), (4.0, 5.2), (5.2, 8.0), (8.0, 12.0),
        (12.0, 16.0), (16.0, 18.0), (18.0, float("inf"))]

from pipeline import config as cfgmod  # noqa: E402


def bp_rp_excess_expected(bp_rp):
    """Numerical copy of step2_cmd; kept local because this small venv lacks Astropy."""
    c = np.asarray(bp_rp, float)
    return np.where(c < 0.5,
                    1.154360 + 0.033772 * c + 0.032277 * c**2,
                    np.where(c < 4.0,
                             1.162004 + 0.011464 * c + 0.049255 * c**2
                             - 0.005879 * c**3,
                             1.057572 + 0.140537 * c))


def bp_rp_excess_sigma(gmag):
    g = np.asarray(gmag, float)
    return 0.0059898 + 8.817481e-12 * g**7.618399


def bin_label(value):
    for lo, hi in BINS:
        if lo <= value < hi:
            if lo == -float("inf"):
                return f"G < {hi:g}"
            if hi == float("inf"):
                return f"G >= {lo:g}"
            return f"{lo:g} <= G < {hi:g}"
    raise AssertionError(value)


def main():
    path = ROOT / "data" / "hr23_passprob_notcmd_gaia_photometry.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 62:
        raise RuntimeError(f"Expected 62 queried stars, found {len(rows)}")
    cfg = cfgmod.load(ROOT / "config.toml").step2_cmd
    def col(name):
        return np.asarray([float(r[name]) if r[name] not in ("", "null") else np.nan
                           for r in rows], float)
    g, color = col("phot_g_mean_mag"), col("bp_rp")
    checks = [
        ("bright_limit", np.isfinite(g) & (g >= cfg.g_bright_limit)),
        ("G_signal_to_noise", np.isfinite(col("phot_g_mean_flux_over_error"))
         & (col("phot_g_mean_flux_over_error") >= cfg.min_flux_snr_g)),
        ("BP_signal_to_noise", np.isfinite(col("phot_bp_mean_flux_over_error"))
         & (col("phot_bp_mean_flux_over_error") >= cfg.min_flux_snr_bp)),
        ("RP_signal_to_noise", np.isfinite(col("phot_rp_mean_flux_over_error"))
         & (col("phot_rp_mean_flux_over_error") >= cfg.min_flux_snr_rp)),
    ]
    excess = col("phot_bp_rp_excess_factor") - bp_rp_excess_expected(color)
    checks.append(("BP_RP_excess", np.isfinite(excess) &
                   (np.abs(excess) < cfg.bp_rp_excess_sigma * bp_rp_excess_sigma(g))))

    alive = np.ones(len(rows), bool)
    first_failure = np.full(len(rows), "passes_all_replayed_cuts", dtype=object)
    sequential = []
    for name, passes in checks:
        newly_failed = alive & ~passes
        first_failure[newly_failed] = name
        sequential.append({"cut": name, "failed_at_this_cut": int(newly_failed.sum()),
                           "remaining": int((alive & passes).sum())})
        alive &= passes
    counts = {name: int(np.sum(first_failure == name))
              for name, _ in checks}
    counts["passes_all_replayed_cuts"] = int(alive.sum())
    labels = list(counts)
    by_g_bin = {}
    for lo, hi in BINS:
        representative = hi - 1 if lo == -float("inf") else lo
        name = bin_label(representative)
        in_bin = np.asarray([name == bin_label(value) for value in g])
        by_g_bin[name] = {label: int(np.sum(in_bin & (first_failure == label)))
                          for label in labels}
    stars = [{"source_id": rows[i]["source_id"], "Gmag": float(g[i]),
              "first_failure": str(first_failure[i])} for i in range(len(rows))]
    output = {
        "status": "exact_replay_of_saved_step2_quality_cut_formulas",
        "queried_stars": len(rows), "exclusive_first_failure_counts": counts,
        "sequential_accounting": sequential, "by_G_bin": by_g_bin,
        "stars": stars,
        "limits": [
            "Gaia DR3 fields were queried on 2026-08-22; the saved baseline may have originated from a different retrieval date but the same DR3 source IDs.",
            "The replay covers apply_quality_cuts in the current branch only; it does not prove older pipeline code used identical settings.",
        ],
    }
    out = ROOT / "results" / "hr23_lost_quality_cut_replay.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exclusive_first_failure_counts": counts,
                      "sequential_accounting": sequential,
                      "by_G_bin": by_g_bin}, indent=2))


if __name__ == "__main__":
    main()
