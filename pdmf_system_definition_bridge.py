#!/usr/bin/env python
"""Measure PDMF-to-IMF corrections under component and unresolved-system definitions.

Input snapshots are NPZ files containing ``id``, ``mass``, ``pos`` and
``system_id``.  Components with the same system ID are treated as one
unresolved object.  The catalog must come from a physical pair/multiple finder
(for PeTar, use ``petar.data.process`` outputs); raw snapshot ``status`` is an
integrator state and is not a complete primordial-binary catalog.

The script reports four compatible mass definitions:

* component: every star is counted separately;
* primary: the most massive component in each system (the definition used by
  this repository's forward generator when it draws ``m1`` from the IMF);
* system_total: sum of component masses;
* photometric_beta_N: the single-star-equivalent mass obtained from
  L proportional to M**N, a transparent sensitivity test for traditional
  single-star mass assignment.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from petar_pdmf_analysis import (
    mle_powerlaw,
    projection_directions,
    shrinking_sphere_center,
)


HERE = Path(__file__).resolve().parent


def load_catalog(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        required = {"id", "mass", "pos", "system_id"}
        missing = required - set(data.files)
        if missing:
            raise ValueError(f"{path} is missing NPZ fields: {sorted(missing)}")
        catalog = {key: np.asarray(data[key]) for key in required}
        catalog["time_myr"] = (
            float(np.asarray(data["time_myr"]).reshape(-1)[0])
            if "time_myr" in data.files
            else math.nan
        )
    particle_id = catalog["id"]
    mass = np.asarray(catalog["mass"], float)
    position = np.asarray(catalog["pos"], float)
    system_id = catalog["system_id"]
    n = len(mass)
    if particle_id.shape != (n,) or system_id.shape != (n,) or position.shape != (n, 3):
        raise ValueError("Expected id/mass/system_id (N,) and pos (N,3)")
    if len(np.unique(particle_id)) != n:
        raise ValueError(f"Component IDs are not unique in {path}")
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError(f"Masses must be finite and positive in {path}")
    if not np.all(np.isfinite(position)):
        raise ValueError(f"Positions must be finite in {path}")
    if system_id.dtype.kind in "f" and not np.all(np.isfinite(system_id)):
        raise ValueError(f"system_id must be finite in {path}")
    return {
        "id": particle_id,
        "mass": mass,
        "pos": position,
        "system_id": system_id,
        "time_myr": catalog["time_myr"],
        "source": str(path),
    }


def collapse_systems(catalog: dict, betas: tuple[float, ...]) -> dict:
    system_id, inverse = np.unique(catalog["system_id"], return_inverse=True)
    mass = catalog["mass"]
    position = catalog["pos"]
    n_systems = len(system_id)
    count = np.bincount(inverse, minlength=n_systems)
    total = np.bincount(inverse, weights=mass, minlength=n_systems)
    primary = np.full(n_systems, -np.inf)
    np.maximum.at(primary, inverse, mass)
    weighted_position = np.column_stack(
        [
            np.bincount(inverse, weights=mass * position[:, axis], minlength=n_systems)
            for axis in range(3)
        ]
    )
    center = weighted_position / total[:, None]
    definitions = {
        "component": mass,
        "primary": primary,
        "system_total": total,
    }
    for beta in betas:
        luminosity = np.bincount(
            inverse, weights=mass**beta, minlength=n_systems
        )
        definitions[f"photometric_beta_{beta:g}"] = luminosity ** (1.0 / beta)
    return {
        "system_id": system_id,
        "inverse": inverse,
        "multiplicity": count,
        "position": center,
        "definitions": definitions,
    }


def _fit(mass, mass_min, mass_max):
    result = mle_powerlaw(mass, mass_min, mass_max)
    return {
        "alpha": result["alpha"],
        "alpha_err": result["alpha_err"],
        "n": result["n"],
    }


def analyze_definition_bridge(
    initial: dict,
    final: dict,
    mass_min: float,
    mass_max: float,
    aperture_pc: float,
    n_projections: int,
    betas: tuple[float, ...],
) -> dict:
    initial_systems = collapse_systems(initial, betas)
    final_systems = collapse_systems(final, betas)
    center, center_n = shrinking_sphere_center(final["pos"], final["mass"])
    component_position = final["pos"] - center
    system_position = final_systems["position"] - center
    component_r3 = np.linalg.norm(component_position, axis=1)
    system_r3 = np.linalg.norm(system_position, axis=1)

    initial_fit = {
        name: _fit(mass, mass_min, mass_max)
        for name, mass in initial_systems["definitions"].items()
    }
    projection_values = {name: [] for name in initial_fit}
    projection_counts = {name: [] for name in initial_fit}
    for direction in projection_directions(n_projections):
        component_parallel = component_position @ direction
        component_radius = np.sqrt(
            np.maximum(component_r3**2 - component_parallel**2, 0.0)
        )
        system_parallel = system_position @ direction
        system_radius = np.sqrt(np.maximum(system_r3**2 - system_parallel**2, 0.0))
        component_selected = component_radius <= aperture_pc
        system_selected = system_radius <= aperture_pc
        for name, mass in final_systems["definitions"].items():
            selected = component_selected if name == "component" else system_selected
            fit = _fit(mass[selected], mass_min, mass_max)
            projection_values[name].append(fit["alpha"])
            projection_counts[name].append(fit["n"])

    definitions = {}
    for name in initial_fit:
        values = np.asarray(projection_values[name], float)
        final_alpha = float(np.nanmedian(values))
        initial_alpha = initial_fit[name]["alpha"]
        definitions[name] = {
            "initial_global": initial_fit[name],
            "final_aperture_alpha_median": final_alpha,
            "final_aperture_alpha_values": values.tolist(),
            "final_aperture_n_median": float(np.median(projection_counts[name])),
            "delta_alpha_pdmf_minus_imf": final_alpha - initial_alpha,
            "correction_to_add_to_pdmf_for_imf": initial_alpha - final_alpha,
        }

    component_delta = definitions["component"]["delta_alpha_pdmf_minus_imf"]
    for values in definitions.values():
        values["delta_relative_to_component"] = (
            values["delta_alpha_pdmf_minus_imf"] - component_delta
        )

    def multiplicity_summary(collapsed):
        multiplicity = collapsed["multiplicity"]
        return {
            "n_components": int(multiplicity.sum()),
            "n_systems": int(len(multiplicity)),
            "multiple_systems": int(np.count_nonzero(multiplicity > 1)),
            "max_multiplicity": int(multiplicity.max()),
            "component_binary_or_higher_fraction": float(
                multiplicity[multiplicity > 1].sum() / multiplicity.sum()
            ),
        }

    return {
        "status": "system_definition_bridge",
        "mass_range_msun": [float(mass_min), float(mass_max)],
        "aperture_radius_pc": float(aperture_pc),
        "n_projections": int(n_projections),
        "photometric_mass_luminosity_betas": list(betas),
        "initial_time_myr": initial["time_myr"],
        "final_time_myr": final["time_myr"],
        "center": {
            "method": "shrinking_sphere_component_mass_weighted",
            "position_pc": center.tolist(),
            "sample_size": center_n,
        },
        "multiplicity": {
            "initial": multiplicity_summary(initial_systems),
            "final": multiplicity_summary(final_systems),
        },
        "definitions": definitions,
        "interpretation": {
            "forward_model_match": "primary",
            "traditional_single_star_proxy": "photometric_beta_N",
            "warning": (
                "Do not add a component-star dynamical correction to an "
                "unresolved-system PDMF. Use the correction under the matching "
                "definition, or include delta_relative_to_component exactly once."
            ),
        },
    }


def synthetic_catalogs(seed=20260813, n_systems=8000):
    rng = np.random.default_rng(seed)
    primary = 0.3 * (2.5 / 0.3) ** rng.random(n_systems)
    is_binary = rng.random(n_systems) < 0.55
    q = 0.2 + 0.8 * rng.random(n_systems)
    component_system = np.repeat(np.arange(n_systems), 1 + is_binary.astype(int))
    component_mass = []
    for index in range(n_systems):
        component_mass.append(primary[index])
        if is_binary[index]:
            component_mass.append(primary[index] * q[index])
    component_mass = np.asarray(component_mass)
    initial_position = rng.normal(size=(len(component_mass), 3))
    final_position = rng.normal(size=(len(component_mass), 3))
    final_position *= (3.0 / np.sqrt(component_mass))[:, None]
    particle_id = np.arange(1, len(component_mass) + 1)
    common = {
        "id": particle_id,
        "mass": component_mass,
        "system_id": component_system,
        "source": "synthetic",
    }
    return (
        {**common, "pos": initial_position, "time_myr": 0.0},
        {**common, "pos": final_position, "time_myr": 125.0},
    )


def run_self_test(output: Path) -> dict:
    initial, final = synthetic_catalogs()
    summary = analyze_definition_bridge(
        initial, final, 0.3, 2.5, 12.09, 32, (2.0, 3.0, 4.0)
    )
    definitions = summary["definitions"]
    checks = {
        "all_definitions_finite": all(
            np.isfinite(values["delta_alpha_pdmf_minus_imf"])
            for values in definitions.values()
        ),
        "component_count_exceeds_system_count": (
            summary["multiplicity"]["initial"]["n_components"]
            > summary["multiplicity"]["initial"]["n_systems"]
        ),
        "forward_definition_present": "primary" in definitions,
        "photometric_sensitivity_present": all(
            f"photometric_beta_{beta:g}" in definitions for beta in (2.0, 3.0, 4.0)
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"Definition bridge self-test failed: {checks}")
    summary["status"] = "synthetic_validation_only"
    summary["self_test"] = checks
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--final", type=Path)
    parser.add_argument("--mass-min", type=float, default=0.3)
    parser.add_argument("--mass-max", type=float, default=2.5)
    parser.add_argument("--aperture-pc", type=float, default=12.09)
    parser.add_argument("--n-projections", type=int, default=32)
    parser.add_argument("--betas", type=float, nargs="+", default=(2.0, 3.0, 4.0))
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "results/pdmf_system_definition_bridge.json",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        summary = run_self_test(args.output)
    else:
        if args.initial is None or args.final is None:
            parser.error("--initial and --final are required unless --self-test is used")
        if args.mass_min <= 0 or args.mass_max <= args.mass_min:
            parser.error("mass limits must satisfy 0 < mass-min < mass-max")
        if args.aperture_pc <= 0:
            parser.error("--aperture-pc must be positive")
        betas = tuple(sorted(set(args.betas)))
        if not betas or min(betas) <= 0:
            parser.error("--betas must be positive")
        summary = analyze_definition_bridge(
            load_catalog(args.initial),
            load_catalog(args.final),
            args.mass_min,
            args.mass_max,
            args.aperture_pc,
            args.n_projections,
            betas,
        )
        summary["inputs"] = {"initial": str(args.initial), "final": str(args.final)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
