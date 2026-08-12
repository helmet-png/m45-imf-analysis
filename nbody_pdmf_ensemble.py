#!/usr/bin/env python
"""Robustness ensemble for the native-Windows PDMF N-body pre-flight test."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from nbody_pdmf_smoke import diagnostics, prepare_cluster


HERE = Path(__file__).resolve().parent


def parse_values(text, cast):
    return [cast(value) for value in text.split(",")]


def run_one(rebound, n_stars, softening, seed, alpha, mass_min, mass_max, time_end, dt):
    rng = np.random.default_rng(seed)
    physical_mass, simulation_mass, position, velocity = prepare_cluster(
        rng, n_stars, alpha, mass_min, mass_max, softening
    )
    simulation = rebound.Simulation()
    simulation.G = 1.0
    simulation.integrator = "leapfrog"
    simulation.dt = dt
    simulation.softening = softening
    for mass, xyz, uvw in zip(simulation_mass, position, velocity):
        simulation.add(
            m=float(mass),
            x=float(xyz[0]),
            y=float(xyz[1]),
            z=float(xyz[2]),
            vx=float(uvw[0]),
            vy=float(uvw[1]),
            vz=float(uvw[2]),
        )
    simulation.move_to_com()
    energy = float(simulation.energy())
    initial = diagnostics(
        simulation, physical_mass, energy, mass_min, mass_max
    )
    simulation.integrate(time_end, exact_finish_time=1)
    final = diagnostics(
        simulation, physical_mass, energy, mass_min, mass_max
    )
    initial_contrast = initial["alpha_outer_half"] - initial["alpha_inner_half"]
    final_contrast = final["alpha_outer_half"] - final["alpha_inner_half"]
    return {
        "n_stars": n_stars,
        "softening_rh": softening,
        "seed": seed,
        "initial_alpha_global": initial["alpha_global"],
        "final_alpha_global": final["alpha_global"],
        "initial_alpha_contrast_outer_minus_inner": initial_contrast,
        "final_alpha_contrast_outer_minus_inner": final_contrast,
        "delta_alpha_contrast": final_contrast - initial_contrast,
        "initial_radius_ratio_low_to_high": initial["radius_ratio_low_to_high"],
        "final_radius_ratio_low_to_high": final["radius_ratio_low_to_high"],
        "delta_radius_ratio": (
            final["radius_ratio_low_to_high"]
            - initial["radius_ratio_low_to_high"]
        ),
        "relative_energy_error": final["relative_energy_error"],
        "energy_pass": abs(final["relative_energy_error"]) < 1e-3,
    }


def group_summary(rows, n_stars=None, softening=None):
    selected = [
        row
        for row in rows
        if (n_stars is None or row["n_stars"] == n_stars)
        and (softening is None or row["softening_rh"] == softening)
    ]
    contrast = np.array([row["delta_alpha_contrast"] for row in selected])
    radius = np.array([row["delta_radius_ratio"] for row in selected])
    energy = np.array([abs(row["relative_energy_error"]) for row in selected])
    passed = energy < 1e-3
    passed_contrast = contrast[passed]
    passed_radius = radius[passed]
    return {
        "n_stars": n_stars if n_stars is not None else "all",
        "softening_rh": softening if softening is not None else "all",
        "n_runs": len(selected),
        "median_delta_alpha_contrast": float(np.median(contrast)),
        "p16_delta_alpha_contrast": float(np.percentile(contrast, 16)),
        "p84_delta_alpha_contrast": float(np.percentile(contrast, 84)),
        "fraction_positive_delta_alpha_contrast": float(np.mean(contrast > 0)),
        "median_delta_radius_ratio": float(np.median(radius)),
        "fraction_positive_delta_radius_ratio": float(np.mean(radius > 0)),
        "max_absolute_energy_error": float(np.max(energy)),
        "fraction_energy_pass": float(np.mean(energy < 1e-3)),
        "n_energy_pass": int(passed.sum()),
        "median_delta_alpha_contrast_energy_pass": (
            float(np.median(passed_contrast)) if passed.any() else None
        ),
        "fraction_positive_delta_alpha_contrast_energy_pass": (
            float(np.mean(passed_contrast > 0)) if passed.any() else None
        ),
        "median_delta_radius_ratio_energy_pass": (
            float(np.median(passed_radius)) if passed.any() else None
        ),
        "fraction_positive_delta_radius_ratio_energy_pass": (
            float(np.mean(passed_radius > 0)) if passed.any() else None
        ),
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-path", type=Path)
    parser.add_argument("--n-stars", default="128,256,512")
    parser.add_argument("--softening", default="0.005,0.01,0.02")
    parser.add_argument("--replicates", type=int, default=8)
    parser.add_argument("--seed-base", type=int, default=2026081300)
    parser.add_argument("--alpha", type=float, default=2.30)
    parser.add_argument("--mass-min", type=float, default=0.30)
    parser.add_argument("--mass-max", type=float, default=2.50)
    parser.add_argument("--time-end", type=float, default=10.0)
    parser.add_argument("--dt", type=float, default=0.001)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=HERE / "results/nbody_pdmf_ensemble",
    )
    args = parser.parse_args()
    if args.package_path is not None:
        sys.path.insert(0, str(args.package_path.resolve()))
    import rebound

    n_values = parse_values(args.n_stars, int)
    softening_values = parse_values(args.softening, float)
    rows = []
    run_index = 0
    for n_stars in n_values:
        for softening in softening_values:
            for replicate in range(args.replicates):
                seed = args.seed_base + run_index
                row = run_one(
                    rebound,
                    n_stars,
                    softening,
                    seed,
                    args.alpha,
                    args.mass_min,
                    args.mass_max,
                    args.time_end,
                    args.dt,
                )
                row["replicate"] = replicate + 1
                rows.append(row)
                run_index += 1
                print(
                    f"{run_index}: N={n_stars}, eps={softening:g}, "
                    f"dalpha={row['delta_alpha_contrast']:+.3f}, "
                    f"dR={row['delta_radius_ratio']:+.3f}, "
                    f"dE={row['relative_energy_error']:+.2e}",
                    flush=True,
                )

    summaries = [group_summary(rows)]
    for n_stars in n_values:
        for softening in softening_values:
            summaries.append(group_summary(rows, n_stars, softening))
    result = {
        "status": "preflight_ensemble_not_production_cluster_model",
        "environment": {"rebound_version": rebound.__version__},
        "parameters": {
            "n_stars": n_values,
            "softening_rh": softening_values,
            "replicates": args.replicates,
            "input_alpha": args.alpha,
            "time_end_crossing": args.time_end,
            "dt_crossing": args.dt,
            "seed_base": args.seed_base,
        },
        "overall": summaries[0],
        "groups": summaries[1:],
        "interpretation_rule": (
            "A robust pre-flight signal requires positive median changes in "
            "both radial-alpha contrast and low/high-mass radius ratio, plus "
            "acceptable energy conservation. It does not quantify the M45 correction."
        ),
    }
    prefix = args.output_prefix
    write_csv(prefix.with_name(prefix.name + "_runs.csv"), rows)
    write_csv(prefix.with_name(prefix.name + "_summary.csv"), summaries)
    json_path = prefix.with_suffix(".json")
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
