#!/usr/bin/env python
"""Bootstrap uncertainty for the LIMEPY spatial-coverage smoking test.

The structural library is solved once. Individual observed stars are then
resampled with replacement, and every resample chooses its best structural
model from the full library. Component masses are held at their observed
values while building the library; this approximation is recorded explicitly.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from pdmf_limepy_smoke import (
    DEFAULT_MASS_EDGES,
    DEFAULT_RADIAL_EDGES_DEG,
    binned_powerlaw_slope,
    load_limepy,
    load_observations,
    make_radial_profile,
    parse_float_list,
    projected_cumulative,
    representative_masses,
)


HERE = Path(__file__).resolve().parent


def category_index(masses, radii, mass_edges, radial_edges):
    mass_index = np.searchsorted(mass_edges, masses, side="right") - 1
    mass_index[masses == mass_edges[-1]] = len(mass_edges) - 2
    radial_index = np.searchsorted(radial_edges, radii, side="right") - 1
    valid = (
        (mass_index >= 0)
        & (mass_index < len(mass_edges) - 1)
        & (radial_index >= 0)
        & (radial_index < len(radial_edges) - 1)
    )
    category = mass_index * (len(radial_edges) - 1) + radial_index
    return valid, mass_index, category


def build_library(
    limepy_class,
    mass_mid,
    component_mass,
    radial_edges_pc,
    phi0_values,
    g_values,
    delta_values,
    rh_values,
):
    records = []
    log_probability = []
    inside_fraction = []
    total_mass = max(float(component_mass.sum()), 1.0)
    model_index = 0
    for phi0 in phi0_values:
        for g in g_values:
            for delta in delta_values:
                for rh in rh_values:
                    model_index += 1
                    try:
                        model = limepy_class(
                            float(phi0),
                            float(g),
                            mj=mass_mid,
                            Mj=component_mass,
                            M=total_mass,
                            rh=float(rh),
                            delta=float(delta),
                            project=True,
                            meanmassdef="global",
                            verbose=False,
                        )
                        if not model.converged:
                            continue
                        probabilities = []
                        fractions = []
                        for component in range(len(mass_mid)):
                            cumulative = projected_cumulative(
                                model, component, radial_edges_pc
                            )
                            probability = np.diff(cumulative) / cumulative[-1]
                            probability = np.clip(probability, 1e-12, None)
                            probability /= probability.sum()
                            probabilities.append(probability)
                            fractions.append(
                                cumulative[-1] / float(model.mcpj[component, -1])
                            )
                    except Exception:
                        continue
                    records.append(
                        {
                            "phi0": float(phi0),
                            "g": float(g),
                            "delta": float(delta),
                            "rh_pc": float(rh),
                            "rt_pc": float(model.rt),
                        }
                    )
                    log_probability.append(
                        np.log(np.asarray(probabilities).ravel())
                    )
                    inside_fraction.append(fractions)
                    if model_index % 100 == 0:
                        print(
                            f"library {model_index}: "
                            f"{len(records)} converged",
                            flush=True,
                        )
    if not records:
        raise RuntimeError("No LIMEPY models converged")
    return records, np.asarray(log_probability), np.asarray(inside_fraction)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percentile_summary(values):
    return {
        "median": float(np.median(values)),
        "p16": float(np.percentile(values, 16)),
        "p84": float(np.percentile(values, 84)),
        "p2p5": float(np.percentile(values, 2.5)),
        "p97p5": float(np.percentile(values, 97.5)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members", type=Path, default=HERE / "data/cmd_members.csv")
    parser.add_argument("--masses", type=Path, default=HERE / "results/step5_imf.npz")
    parser.add_argument("--config", type=Path, default=HERE / "config.toml")
    parser.add_argument("--package-path", type=Path)
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--phi0", default="3,4,5,6,7,8,9")
    parser.add_argument("--g", default="0,1,2")
    parser.add_argument("--delta", default="0,0.15,0.3,0.45,0.6")
    parser.add_argument("--rh-pc", default="2,3,4,5,6,8,10")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=HERE / "results/pdmf_limepy_bootstrap",
    )
    args = parser.parse_args()

    limepy_class, environment = load_limepy(args.package_path)
    masses, radii, weights, metadata = load_observations(
        args.members, args.masses, args.config
    )
    _, weighted, _, radial_edges_pc = make_radial_profile(
        masses,
        radii,
        weights,
        DEFAULT_MASS_EDGES,
        DEFAULT_RADIAL_EDGES_DEG,
        metadata["distance_pc"],
    )
    mass_mid = representative_masses(masses, DEFAULT_MASS_EDGES)
    observed_number = weighted.sum(axis=1)
    component_mass = observed_number * mass_mid
    records, log_probability, inside_fraction = build_library(
        limepy_class,
        mass_mid,
        component_mass,
        radial_edges_pc,
        parse_float_list(args.phi0),
        parse_float_list(args.g),
        parse_float_list(args.delta),
        parse_float_list(args.rh_pc),
    )

    valid, mass_index, category = category_index(
        masses, radii, DEFAULT_MASS_EDGES, DEFAULT_RADIAL_EDGES_DEG
    )
    valid_indices = np.flatnonzero(valid)
    mass_index = mass_index[valid]
    category = category[valid]
    selected_weights = weights[valid]
    rng = np.random.default_rng(args.seed)
    trial_rows = []
    selected_models = Counter()
    delta_alpha = np.empty(args.trials)

    for trial in range(args.trials):
        draw = rng.integers(0, len(valid_indices), len(valid_indices))
        counts_flat = np.bincount(
            category[draw],
            weights=selected_weights[draw],
            minlength=weighted.size,
        )
        nll = -(log_probability @ counts_flat)
        best_index = int(np.argmin(nll))
        selected_models[best_index] += 1
        counts_by_mass = np.bincount(
            mass_index[draw],
            weights=selected_weights[draw],
            minlength=len(DEFAULT_MASS_EDGES) - 1,
        )
        corrected = counts_by_mass / inside_fraction[best_index]
        observed_fit = binned_powerlaw_slope(
            counts_by_mass, DEFAULT_MASS_EDGES
        )
        corrected_fit = binned_powerlaw_slope(corrected, DEFAULT_MASS_EDGES)
        delta_alpha[trial] = corrected_fit["alpha"] - observed_fit["alpha"]
        record = records[best_index]
        trial_rows.append(
            {
                "trial": trial + 1,
                "alpha_observed": observed_fit["alpha"],
                "alpha_spatial_corrected": corrected_fit["alpha"],
                "delta_alpha_spatial": delta_alpha[trial],
                "model_index": best_index,
                **record,
            }
        )
        if (trial + 1) % 1000 == 0:
            print(f"bootstrap {trial + 1}/{args.trials}", flush=True)

    frequency_rows = []
    for model_index, count in selected_models.most_common():
        frequency_rows.append(
            {
                "model_index": model_index,
                "count": count,
                "fraction": count / args.trials,
                **records[model_index],
                "inside_fraction_low_mass": inside_fraction[model_index, 0],
                "inside_fraction_high_mass": inside_fraction[model_index, -1],
            }
        )
    result = {
        "status": "bootstrap_for_spatial_smoking_test_not_final_imf",
        "environment": environment,
        "metadata": metadata,
        "parameters": {
            "trials": args.trials,
            "seed": args.seed,
            "n_resampled_stars": int(len(valid_indices)),
            "n_structural_models": len(records),
        },
        "delta_alpha_spatial": percentile_summary(delta_alpha),
        "fraction_delta_alpha_positive": float(np.mean(delta_alpha > 0)),
        "fraction_abs_delta_alpha_below_0p02": float(
            np.mean(np.abs(delta_alpha) < 0.02)
        ),
        "most_frequent_models": frequency_rows[:10],
        "approximation": (
            "The structural library holds component masses at their observed "
            "values; each bootstrap resamples stars and reselects the best "
            "model, but does not rebuild the multi-mass library."
        ),
    }
    prefix = args.output_prefix
    write_csv(prefix.with_name(prefix.name + "_trials.csv"), trial_rows)
    write_csv(prefix.with_name(prefix.name + "_models.csv"), frequency_rows)
    json_path = prefix.with_suffix(".json")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
