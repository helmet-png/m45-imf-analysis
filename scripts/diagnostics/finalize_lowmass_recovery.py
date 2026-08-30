#!/usr/bin/env python3
"""Fail-closed validation and uncertainty summary for P6b v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


EXPECTED_TRUTH = np.array([0.9, 1.3, 1.7], dtype=float)
P_MIN, P_MAX = 0.3, 2.3
ALPHA_TRUE = 2.35


def _manifest(npz: np.lib.npyio.NpzFile) -> dict:
    raw = npz["__manifest__"]
    return json.loads(str(raw.item() if raw.shape == () else raw))


def validate(path: Path, bootstrap: int, seed: int) -> dict:
    with np.load(path, allow_pickle=False) as data:
        required = {"p_true", "__manifest__"}
        for value in EXPECTED_TRUTH:
            required.update({f"p{value:.1f}", f"__attempted_p{value:.1f}"})
        missing = sorted(required.difference(data.files))
        if missing:
            raise ValueError(f"missing required arrays: {missing}")

        truth = np.asarray(data["p_true"], dtype=float)
        if not np.array_equal(truth, EXPECTED_TRUTH):
            raise ValueError(f"unexpected p_true: {truth.tolist()}")

        manifest = _manifest(data)
        expected_manifest = {
            "n_syn": 40000,
            "refines": "3,3",
            "manifest_type": "aggregate",
            "aggregated_trial_offsets": [0, 1, 2],
        }
        for key, expected in expected_manifest.items():
            if manifest.get(key) != expected:
                raise ValueError(
                    f"manifest mismatch for {key}: {manifest.get(key)!r} != {expected!r}"
                )

        groups = []
        alpha_groups = []
        for value in truth:
            key = f"p{value:.1f}"
            attempted = np.asarray(data[f"__attempted_{key}"], dtype=int)
            values = np.asarray(data[key], dtype=float)
            if attempted.shape != (1,) or attempted[0] != 3:
                raise ValueError(f"{key}: expected attempted=[3], got {attempted.tolist()}")
            if values.shape != (3, 8):
                raise ValueError(f"{key}: expected shape (3, 8), got {values.shape}")
            if not np.isfinite(values).all():
                raise ValueError(f"{key}: contains non-finite values")
            groups.append(values[:, 7])
            alpha_groups.append(values[:, 3])

    means = np.array([group.mean() for group in groups])
    sds = np.array([group.std(ddof=1) for group in groups])
    biases = means - truth
    alpha_means = np.array([group.mean() for group in alpha_groups])
    alpha_biases = alpha_means - ALPHA_TRUE
    slope, intercept = np.polyfit(truth, means, 1)

    rng = np.random.default_rng(seed)
    bootstrap_slopes = np.empty(bootstrap, dtype=float)
    for index in range(bootstrap):
        sampled_means = np.array(
            [rng.choice(group, size=len(group), replace=True).mean() for group in groups]
        )
        bootstrap_slopes[index] = np.polyfit(truth, sampled_means, 1)[0]

    wall_distance = np.minimum(
        np.concatenate(groups) - P_MIN, P_MAX - np.concatenate(groups)
    )
    criteria = {
        "absolute_p_bias_below_0p3": bool(np.all(np.abs(biases) < 0.3)),
        "no_p_wall_hit": bool(np.all(wall_distance >= 0.02 * (P_MAX - P_MIN))),
        "recovery_tracks_truth": bool(means[-1] > means[0] and slope > 0),
        "absolute_alpha_bias_below_0p3": bool(np.all(np.abs(alpha_biases) < 0.3)),
    }

    return {
        "status": "validated" if all(criteria.values()) else "failed_gate",
        "source": str(path).replace("\\", "/"),
        "manifest": manifest,
        "n_trials_total": int(sum(len(group) for group in groups)),
        "p_true": truth.tolist(),
        "p_recovered_trials": [group.tolist() for group in groups],
        "p_recovered_mean": means.tolist(),
        "p_recovered_sample_sd": sds.tolist(),
        "p_bias": biases.tolist(),
        "p_bias_rmse": float(np.sqrt(np.mean(biases**2))),
        "identifiability_slope": float(slope),
        "identifiability_intercept": float(intercept),
        "bootstrap": {
            "method": "resample three trials independently within each injected truth",
            "draws": bootstrap,
            "seed": seed,
            "slope_percentiles_2p5_16_50_84_97p5": np.percentile(
                bootstrap_slopes, [2.5, 16, 50, 84, 97.5]
            ).tolist(),
        },
        "alpha_true": ALPHA_TRUE,
        "alpha_recovered_mean": alpha_means.tolist(),
        "alpha_bias": alpha_biases.tolist(),
        "minimum_p_wall_distance": float(wall_distance.min()),
        "criteria": criteria,
        "interpretation_limits": [
            "Only three trials are available at each injected truth.",
            "The bootstrap is conditional on these nine deterministic fake catalogues.",
            "A slope below one indicates compression toward the middle of the tested range.",
            "This validates identifiability but does not replace the pending P6 alpha-versus-p profile.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", type=Path, default=Path("results/inject_lowmass_p6b_v2.npz")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/inject_lowmass_p6b_v2_validation.json"),
    )
    parser.add_argument("--bootstrap", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260829)
    args = parser.parse_args()
    if args.bootstrap < 1000:
        parser.error("--bootstrap must be at least 1000")

    result = validate(args.input, args.bootstrap, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "validated":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
