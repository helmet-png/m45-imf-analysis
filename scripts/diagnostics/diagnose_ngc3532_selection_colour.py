"""Diagnose the NGC 3532 faint red/blue selection-gate failure.

This is a read-only accounting diagnostic.  It replays the production quality
cuts from saved CSV columns, but does not rebuild selection or run an IMF fit.
"""
from __future__ import annotations

import argparse
import csv
import json
from math import comb
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
MAG_LIMIT = 17.0
FAINT_MAX_G = 18.0
SNR_LIMITS = {"g_snr": 50.0, "bp_snr": 20.0, "rp_snr": 20.0}
EXCESS_SIGMA_LIMIT = 3.0


def load(path: Path) -> dict[str, np.ndarray]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    names = rows[0].keys()
    output = {}
    for name in names:
        if name == "source_id":
            # Gaia identifiers exceed float64's exact integer range.
            output[name] = np.asarray([int(row[name]) for row in rows], dtype=np.int64)
        else:
            output[name] = np.asarray(
                [float(row[name]) if row[name] else np.nan for row in rows], dtype=float)
    return output


def expected_excess(colour: np.ndarray) -> np.ndarray:
    return np.where(
        colour < 0.5,
        1.154360 + 0.033772 * colour + 0.032277 * colour**2,
        np.where(
            colour < 4.0,
            1.162004 + 0.011464 * colour + 0.049255 * colour**2 - 0.005879 * colour**3,
            1.057572 + 0.140537 * colour,
        ),
    )


def excess_sigma(g: np.ndarray) -> np.ndarray:
    return 0.0059898 + 8.817481e-12 * g**7.618399


def stats(mask: np.ndarray, cuts: dict[str, np.ndarray], arrays: dict[str, np.ndarray]) -> dict:
    n = int(mask.sum())
    sequential = mask.copy()
    result = {"n": n, "cuts": {}}
    for name, passed in cuts.items():
        fail_alone = int((mask & ~passed).sum())
        before = int(sequential.sum())
        sequential &= passed
        result["cuts"][name] = {
            "fail_alone": fail_alone,
            "fail_sequential": before - int(sequential.sum()),
        }
    result["kept"] = int(sequential.sum())
    result["survival"] = float(sequential.sum() / n) if n else None
    result["medians"] = {
        key: float(np.nanmedian(value[mask])) for key, value in arrays.items()
    }
    return result


def magnitude_bins(mask: np.ndarray, red: np.ndarray, blue: np.ndarray,
                   passed: np.ndarray, g: np.ndarray) -> list[dict]:
    rows = []
    for lo in np.arange(17.0, 18.0, 0.25):
        row = {"g_lo": float(lo), "g_hi": float(lo + 0.25)}
        for label, side in (("red", red), ("blue", blue)):
            upper = g <= lo + 0.25 if np.isclose(lo + 0.25, FAINT_MAX_G) else g < lo + 0.25
            use = mask & side & (g >= lo) & upper
            n = int(use.sum())
            row[label] = {
                "n": n,
                "kept": int((use & passed).sum()),
                "survival": float((use & passed).sum() / n) if n else None,
            }
        rows.append(row)
    return rows


def fisher_two_sided(blue_fail: int, blue_n: int, red_fail: int, red_n: int) -> float:
    """Two-sided Fisher exact p-value for fail rate versus colour side."""
    total_fail = blue_fail + red_fail
    total = blue_n + red_n
    lo = max(0, total_fail - red_n)
    hi = min(total_fail, blue_n)
    denom = comb(total, total_fail)
    probabilities = {
        k: comb(blue_n, k) * comb(red_n, total_fail - k) / denom
        for k in range(lo, hi + 1)
    }
    observed = probabilities[blue_fail]
    return float(sum(value for value in probabilities.values() if value <= observed + 1e-15))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "data/cluster_NGC_3532_gaia.csv")
    parser.add_argument("--validation-report", type=Path,
                        default=ROOT / "results/cluster_tier2_prep_NGC_3532_postmerge.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/ngc3532_selection_colour_rootcause.json")
    args = parser.parse_args()
    d = load(args.input)
    g = d["phot_g_mean_mag"]
    colour = d["phot_bp_mean_mag"] - d["phot_rp_mean_mag"]
    finite = np.isfinite(g) & np.isfinite(colour)
    # prepare_cluster_tier2 validates only the G<=18 table held in memory;
    # the saved Gaia CSV still contains the pre-limit rows.
    faint = finite & (g >= MAG_LIMIT) & (g <= FAINT_MAX_G)
    split = float(np.median(colour[faint]))
    red = faint & (colour > split)
    blue = faint & (colour <= split)
    residual_sigma = np.abs(d["phot_bp_rp_excess_factor"] - expected_excess(colour)) / excess_sigma(g)
    cuts = {
        "g_snr": np.isfinite(d["phot_g_mean_flux_over_error"]) & (d["phot_g_mean_flux_over_error"] >= SNR_LIMITS["g_snr"]),
        "bp_snr": np.isfinite(d["phot_bp_mean_flux_over_error"]) & (d["phot_bp_mean_flux_over_error"] >= SNR_LIMITS["bp_snr"]),
        "rp_snr": np.isfinite(d["phot_rp_mean_flux_over_error"]) & (d["phot_rp_mean_flux_over_error"] >= SNR_LIMITS["rp_snr"]),
        "bp_rp_excess": np.isfinite(residual_sigma) & (residual_sigma < EXCESS_SIGMA_LIMIT),
    }
    arrays = {
        "g": g,
        "bp_rp": colour,
        "g_snr": d["phot_g_mean_flux_over_error"],
        "bp_snr": d["phot_bp_mean_flux_over_error"],
        "rp_snr": d["phot_rp_mean_flux_over_error"],
        "excess_residual_sigma": residual_sigma,
    }
    output = {
        "input": str(args.input.relative_to(ROOT)),
        "faint_limit_g": MAG_LIMIT,
        "faint_max_g": FAINT_MAX_G,
        "colour_split_bp_rp": split,
        "thresholds": {**SNR_LIMITS, "bp_rp_excess_sigma": EXCESS_SIGMA_LIMIT},
        "red": stats(red, cuts, arrays),
        "blue": stats(blue, cuts, arrays),
    }
    all_passed = np.logical_and.reduce(list(cuts.values()))
    output["magnitude_bins"] = magnitude_bins(faint, red, blue, all_passed, g)
    output["failed_sources"] = []
    for index in np.flatnonzero(faint & ~all_passed):
        output["failed_sources"].append({
            "source_id": int(d["source_id"][index]),
            "side": "red" if red[index] else "blue",
            "g": float(g[index]),
            "bp_rp": float(colour[index]),
            "failed_cuts": [name for name, passed in cuts.items() if not passed[index]],
            "bp_snr": float(d["phot_bp_mean_flux_over_error"][index]),
            "excess_residual_sigma": float(residual_sigma[index]),
        })
    output["observed_red_minus_blue"] = output["red"]["survival"] - output["blue"]["survival"]
    red_excess_fail = output["red"]["cuts"]["bp_rp_excess"]["fail_alone"]
    blue_excess_fail = output["blue"]["cuts"]["bp_rp_excess"]["fail_alone"]
    output["bp_rp_excess_colour_fisher_two_sided_p"] = fisher_two_sided(
        blue_excess_fail, output["blue"]["n"], red_excess_fail, output["red"]["n"])
    validation = json.loads(args.validation_report.read_text(encoding="utf-8"))["selection_validation"]
    output["selection_model"] = {
        key: validation[key] for key in (
            "observed_survival_red", "observed_survival_blue",
            "predicted_survival_red", "predicted_survival_blue",
            "red_minus_blue_error", "pass_faint_colour_split",
        )
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
