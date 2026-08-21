#!/usr/bin/env python
"""Native-Windows N-body smoke test for the PDMF analysis chain.

The experiment starts with a known single-slope mass function and no
mass-position correlation.  It checks whether a small direct N-body run can
produce and measure radial mass segregation while preserving the global mass
function.  This is a PeTar/AMUSE *pre-flight test*, not a production cluster
model: there is no stellar evolution, Galactic tide, primordial binary
population, or observational selection function.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent


def sample_power_law(rng, n, alpha, mass_min, mass_max):
    u = rng.random(n)
    if abs(alpha - 1.0) < 1e-12:
        return mass_min * (mass_max / mass_min) ** u
    exponent = 1.0 - alpha
    return (
        mass_min**exponent
        + u * (mass_max**exponent - mass_min**exponent)
    ) ** (1.0 / exponent)


def sample_isotropic_directions(rng, n):
    z = rng.uniform(-1.0, 1.0, n)
    phi = rng.uniform(0.0, 2.0 * math.pi, n)
    transverse = np.sqrt(1.0 - z * z)
    return np.column_stack(
        (transverse * np.cos(phi), transverse * np.sin(phi), z)
    )


def sample_plummer(rng, n):
    u = np.clip(rng.random(n), 1e-12, 1.0 - 1e-12)
    radii = 1.0 / np.sqrt(u ** (-2.0 / 3.0) - 1.0)
    position = sample_isotropic_directions(rng, n) * radii[:, None]

    # Aarseth-Henon-Wielen rejection sampler for the Plummer speed law.
    q = np.empty(n)
    filled = 0
    while filled < n:
        trial_count = max(64, 2 * (n - filled))
        trial = rng.random(trial_count)
        ordinate = rng.uniform(0.0, 0.1, trial_count)
        accepted = trial[
            ordinate < trial**2 * np.maximum(1.0 - trial**2, 0.0) ** 3.5
        ]
        take = min(len(accepted), n - filled)
        q[filled : filled + take] = accepted[:take]
        filled += take
    escape_speed = np.sqrt(2.0) * (1.0 + radii**2) ** (-0.25)
    velocity = (
        sample_isotropic_directions(rng, n) * (q * escape_speed)[:, None]
    )
    return position, velocity


def mass_weighted_center(values, masses):
    return np.sum(values * masses[:, None], axis=0) / masses.sum()


def softened_potential_energy(position, masses, softening):
    potential = 0.0
    for index in range(len(masses) - 1):
        separation = position[index + 1 :] - position[index]
        radius = np.sqrt(np.sum(separation * separation, axis=1) + softening**2)
        potential -= masses[index] * np.sum(masses[index + 1 :] / radius)
    return float(potential)


def half_mass_radius(position, masses):
    radius = np.linalg.norm(position, axis=1)
    order = np.argsort(radius)
    cumulative = np.cumsum(masses[order])
    return float(radius[order][np.searchsorted(cumulative, 0.5 * masses.sum())])


def prepare_cluster(rng, n, alpha, mass_min, mass_max, softening):
    physical_mass = sample_power_law(rng, n, alpha, mass_min, mass_max)
    simulation_mass = physical_mass / physical_mass.sum()
    position, velocity = sample_plummer(rng, n)

    # Random mass labels ensure there is no primordial mass segregation.
    permutation = rng.permutation(n)
    physical_mass = physical_mass[permutation]
    simulation_mass = simulation_mass[permutation]
    position -= mass_weighted_center(position, simulation_mass)
    velocity -= mass_weighted_center(velocity, simulation_mass)

    radius_scale = half_mass_radius(position, simulation_mass)
    position /= radius_scale
    potential = softened_potential_energy(position, simulation_mass, softening)
    kinetic = 0.5 * np.sum(
        simulation_mass[:, None] * np.square(velocity)
    )
    velocity *= math.sqrt((-0.5 * potential) / kinetic)
    return physical_mass, simulation_mass, position, velocity


def mle_powerlaw(masses, mass_min, mass_max):
    selected = np.asarray(masses, float)
    selected = selected[
        np.isfinite(selected)
        & (selected >= mass_min)
        & (selected <= mass_max)
    ]
    if len(selected) < 10:
        return {"alpha": math.nan, "alpha_err": math.nan, "n": len(selected)}
    alpha_grid = np.linspace(0.5, 4.0, 3501)
    exponent = 1.0 - alpha_grid
    close = np.isclose(alpha_grid, 1.0)
    normalization = np.empty_like(alpha_grid)
    regular = ~close
    denominator = (
        mass_max ** exponent[regular] - mass_min ** exponent[regular]
    )
    normalization[regular] = exponent[regular] / denominator
    normalization[close] = 1.0 / math.log(mass_max / mass_min)
    loglike = (
        len(selected) * np.log(normalization)
        - alpha_grid * np.log(selected).sum()
    )
    peak = int(np.argmax(loglike))
    accepted = alpha_grid[loglike >= loglike[peak] - 0.5]
    return {
        "alpha": float(alpha_grid[peak]),
        "alpha_err": float(0.5 * (accepted[-1] - accepted[0])),
        "n": int(len(selected)),
    }


def extract_arrays(simulation, physical_mass):
    position = np.array([[p.x, p.y, p.z] for p in simulation.particles])
    velocity = np.array([[p.vx, p.vy, p.vz] for p in simulation.particles])
    simulation_mass = np.array([p.m for p in simulation.particles])
    position -= mass_weighted_center(position, simulation_mass)
    velocity -= mass_weighted_center(velocity, simulation_mass)
    radius = np.linalg.norm(position, axis=1)
    return position, velocity, radius


def diagnostics(simulation, physical_mass, initial_energy, mass_min, mass_max):
    _, _, radius = extract_arrays(simulation, physical_mass)
    current_energy = float(simulation.energy())
    r_half = float(np.median(radius))
    inner = radius <= r_half
    outer = ~inner
    low = physical_mass < np.median(physical_mass)
    high = ~low
    return {
        "time_crossing": float(simulation.t),
        "relative_energy_error": (current_energy - initial_energy)
        / abs(initial_energy),
        "median_radius_all": float(np.median(radius)),
        "median_radius_low_mass": float(np.median(radius[low])),
        "median_radius_high_mass": float(np.median(radius[high])),
        "radius_ratio_low_to_high": float(
            np.median(radius[low]) / np.median(radius[high])
        ),
        "alpha_global": mle_powerlaw(
            physical_mass, mass_min, mass_max
        )["alpha"],
        "alpha_inner_half": mle_powerlaw(
            physical_mass[inner], mass_min, mass_max
        )["alpha"],
        "alpha_outer_half": mle_powerlaw(
            physical_mass[outer], mass_min, mass_max
        )["alpha"],
        "n_inner": int(inner.sum()),
        "n_outer": int(outer.sum()),
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
    parser.add_argument("--n-stars", type=int, default=256)
    parser.add_argument("--alpha", type=float, default=2.30)
    parser.add_argument("--mass-min", type=float, default=0.30)
    parser.add_argument("--mass-max", type=float, default=2.50)
    parser.add_argument("--softening", type=float, default=0.01)
    parser.add_argument("--time-end", type=float, default=10.0)
    parser.add_argument("--snapshots", type=int, default=21)
    parser.add_argument("--dt", type=float, default=0.002)
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument(
        "--output-prefix", type=Path, default=HERE / "results/nbody_pdmf_smoke"
    )
    args = parser.parse_args()

    if args.package_path is not None:
        sys.path.insert(0, str(args.package_path.resolve()))
    import rebound

    rng = np.random.default_rng(args.seed)
    physical_mass, simulation_mass, position, velocity = prepare_cluster(
        rng,
        args.n_stars,
        args.alpha,
        args.mass_min,
        args.mass_max,
        args.softening,
    )
    simulation = rebound.Simulation()
    simulation.G = 1.0
    simulation.integrator = "leapfrog"
    simulation.dt = args.dt
    simulation.softening = args.softening
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
    initial_energy = float(simulation.energy())

    rows = []
    for target_time in np.linspace(0.0, args.time_end, args.snapshots):
        simulation.integrate(float(target_time), exact_finish_time=1)
        rows.append(
            diagnostics(
                simulation,
                physical_mass,
                initial_energy,
                args.mass_min,
                args.mass_max,
            )
        )

    final = rows[-1]
    output = {
        "status": "preflight_not_production_cluster_model",
        "environment": {
            "rebound_version": rebound.__version__,
            "integrator": str(simulation.integrator),
            "gravity": str(simulation.gravity),
        },
        "parameters": {
            "n_stars": args.n_stars,
            "input_alpha": args.alpha,
            "mass_min_msun": args.mass_min,
            "mass_max_msun": args.mass_max,
            "softening_rh": args.softening,
            "time_end_crossing": args.time_end,
            "dt_crossing": args.dt,
            "seed": args.seed,
        },
        "initial": rows[0],
        "final": final,
        "checks": {
            "energy_error_below_1e_3": abs(final["relative_energy_error"]) < 1e-3,
            "global_alpha_unchanged_by_dynamics": abs(
                final["alpha_global"] - rows[0]["alpha_global"]
            )
            < 1e-12,
            "mass_segregation_direction_detected": (
                final["radius_ratio_low_to_high"]
                > rows[0]["radius_ratio_low_to_high"]
            ),
        },
        "caveats": [
            "Dimensionless isolated Plummer model; one time unit is approximately one initial crossing time.",
            "No Galactic tide, stellar evolution, primordial binaries, membership selection, or Gaia errors.",
            "Gravitational softening suppresses hard encounters; PeTar is required for production collisional runs.",
            "A single stochastic realization cannot calibrate the M45 IMF correction.",
        ],
    }
    prefix = args.output_prefix
    csv_path = prefix.with_name(prefix.name + "_timeseries.csv")
    json_path = prefix.with_suffix(".json")
    write_csv(csv_path, rows)
    json_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
