#!/usr/bin/env python
"""Build and validate an isolated BP-SNR>=15 M45 selection smoking test."""
from __future__ import annotations

import csv
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.table_compat import Table as _CompatTable  # noqa: E402

_astropy = types.ModuleType("astropy")
_astropy_table = types.ModuleType("astropy.table")
_astropy_table.Table = _CompatTable
_astropy.table = _astropy_table
sys.modules.setdefault("astropy", _astropy)
sys.modules.setdefault("astropy.table", _astropy_table)

from pipeline import selection as selmod  # noqa: E402
from pipeline.step2_cmd import bp_rp_excess_expected, bp_rp_excess_sigma  # noqa: E402

THRESHOLDS = {"g": 50.0, "bp": 15.0, "rp": 20.0}
G_BRIGHT = 4.0


def value(row, key):
    raw = row.get(key, "")
    return float(raw) if raw not in ("", "null", "NaN") else np.nan


def load_raw():
    path = ROOT / "data" / "m45_r5_g18_plx4.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def load_probabilities():
    probs = {}
    path = ROOT / "results" / "baseline.dat"
    with path.open(encoding="utf-8") as handle:
        header = handle.readline().split()
        sid_i, prob_i = header.index("source_id"), header.index("probs_final")
        for line in handle:
            fields = line.split()
            probs[fields[sid_i]] = float(fields[prob_i])
    return probs


def arrays(rows):
    return {
        "g": np.asarray([value(row, "phot_g_mean_mag") for row in rows]),
        "bp": np.asarray([value(row, "phot_bp_mean_mag") for row in rows]),
        "rp": np.asarray([value(row, "phot_rp_mean_mag") for row in rows]),
        "snr_g": np.asarray([value(row, "phot_g_mean_flux_over_error") for row in rows]),
        "snr_bp": np.asarray([value(row, "phot_bp_mean_flux_over_error") for row in rows]),
        "snr_rp": np.asarray([value(row, "phot_rp_mean_flux_over_error") for row in rows]),
        "excess": np.asarray([value(row, "phot_bp_rp_excess_factor") for row in rows]),
    }


def quality_masks(d):
    colour = d["bp"] - d["rp"]
    snr = (
        np.isfinite(d["g"]) & (d["g"] >= G_BRIGHT)
        & np.isfinite(d["bp"]) & np.isfinite(d["rp"])
        & np.isfinite(d["snr_g"]) & (d["snr_g"] >= THRESHOLDS["g"])
        & np.isfinite(d["snr_bp"]) & (d["snr_bp"] >= THRESHOLDS["bp"])
        & np.isfinite(d["snr_rp"]) & (d["snr_rp"] >= THRESHOLDS["rp"])
    )
    residual = d["excess"] - bp_rp_excess_expected(colour)
    excess = np.isfinite(residual) & (
        np.abs(residual) < 3.0 * bp_rp_excess_sigma(d["g"])
    )
    return snr, excess


def make_excess_curve(d, snr, excess):
    edges = np.arange(np.floor(d["g"][snr].min()), np.ceil(d["g"][snr].max()) + 1, 1.0)
    n_all, _ = np.histogram(d["g"][snr], edges)
    n_keep, _ = np.histogram(d["g"][snr & excess], edges)
    centres = 0.5 * (edges[:-1] + edges[1:])
    good = n_all >= 10
    fraction = n_keep[good] / n_all[good]
    return centres[good], fraction


def rate(obs, pred, mask):
    return {
        "n": int(mask.sum()),
        "observed": float(obs[mask].mean()),
        "predicted": float(pred[mask].mean()),
        "difference": float(pred[mask].mean() - obs[mask].mean()),
    }


def main():
    raw = load_raw()
    probs = load_probabilities()
    field = arrays(raw)
    selected_rows = [
        row for row in raw
        if probs.get(row["source_id"], 0.0) >= 0.7
        and value(row, "phot_g_mean_mag") >= G_BRIGHT
    ]
    d = arrays(selected_rows)
    snr, excess = quality_masks(d)
    observed = snr & excess
    bp15_ids = {row["source_id"] for row, keep in zip(selected_rows, observed) if keep}
    with (ROOT / "data" / "cmd_members.csv").open(newline="", encoding="utf-8-sig") as handle:
        current_ids = {row["source_id"] for row in csv.DictReader(handle)}

    mags = {band: field[band] for band in ("g", "bp", "rp")}
    snrs = {band: field[f"snr_{band}"] for band in ("g", "bp", "rp")}
    model = selmod.build(mags, field["bp"] - field["rp"], snrs, THRESHOLDS, verbose=False)
    model.excess_curve = make_excess_curve(d, snr, excess)

    finite = np.isfinite(d["g"]) & np.isfinite(d["bp"]) & np.isfinite(d["rp"])
    g, bp, rp = d["g"][finite], d["bp"][finite], d["rp"][finite]
    obs = observed[finite].astype(float)
    rng = np.random.default_rng(20260822)
    pred = np.zeros(len(g))
    repeats = 2000
    for _ in range(repeats):
        pred += model.keep(g, bp, rp, rng.normal(size=len(g)), rng.random(len(g)))
    pred /= repeats

    overall = rate(obs, pred, np.ones(len(g), bool))
    bins = []
    for lo in np.arange(5, 18, 1.0):
        mask = (g >= lo) & (g < lo + 1)
        if mask.sum() >= 20:
            item = rate(obs, pred, mask)
            item.update({"g_lo": float(lo), "g_hi": float(lo + 1)})
            bins.append(item)
    worst_bin = max(abs(item["difference"]) for item in bins)

    colour = bp - rp
    faint = g >= 17
    median = float(np.median(colour[faint]))
    red = faint & (colour > median)
    blue = faint & (colour <= median)
    red_rate, blue_rate = rate(obs, pred, red), rate(obs, pred, blue)
    observed_contrast = red_rate["observed"] - blue_rate["observed"]
    predicted_contrast = red_rate["predicted"] - blue_rate["predicted"]
    contrast_error = predicted_contrast - observed_contrast
    gates = {
        "overall_abs_difference_lt_0p02": abs(overall["difference"]) < 0.02,
        "all_magnitude_bins_abs_difference_lt_0p08": worst_bin < 0.08,
        "faint_red_blue_contrast_error_abs_lt_0p10": abs(contrast_error) < 0.10,
    }
    margins = {
        "overall_to_limit": 0.02 - abs(overall["difference"]),
        "worst_magnitude_bin_to_limit": 0.08 - worst_bin,
        "faint_red_blue_contrast_to_limit": 0.10 - abs(contrast_error),
    }
    passed = all(gates.values())
    low_margin = passed and min(margins.values()) < 0.02

    output = {
        "status": ("selection_smoke_pass_low_margin" if low_margin else
                   "selection_smoke_pass" if passed else "selection_smoke_fail"),
        "thresholds": THRESHOLDS,
        "raw_field_rows": len(raw),
        "p_ge_0p7_and_g_ge_4_rows": len(selected_rows),
        "observed_bp15_quality_pass": int(observed.sum()),
        "source_id_accounting_vs_current_cmd": {
            "overlap": len(bp15_ids & current_ids),
            "bp15_only": len(bp15_ids - current_ids),
            "current_cmd_only": len(current_ids - bp15_ids),
            "net_change": len(bp15_ids) - len(current_ids),
        },
        "monte_carlo_repeats": repeats,
        "overall": overall,
        "magnitude_bins": bins,
        "worst_magnitude_bin_abs_difference": float(worst_bin),
        "faint_g_ge_17": {
            "colour_split_median": median,
            "red": red_rate,
            "blue": blue_rate,
            "observed_red_minus_blue": float(observed_contrast),
            "predicted_red_minus_blue": float(predicted_contrast),
            "contrast_error": float(contrast_error),
        },
        "gates": gates,
        "gate_margins": margins,
        "limits": [
            "This is an isolated selection-function smoking test, not a new official selection.",
            "The saved baseline membership probabilities are reused; membership is not rerun.",
            "Passing does not establish background contamination after membership selection.",
            "No forward model or IMF was rerun.",
        ],
    }
    (ROOT / "results" / "selection_bp15_smoke.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8"
    )
    np.savez(
        ROOT / "results" / "selection_bp15_smoke.npz",
        **{f"{band}_{key}": np.asarray(model.fits[band][key])
           for band in selmod.BANDS for key in ("mag", "level", "colour_coef", "scatter")},
        **{f"thr_{band}": THRESHOLDS[band] for band in selmod.BANDS},
        excess_g=model.excess_curve[0], excess_f=model.excess_curve[1],
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
