#!/usr/bin/env python
"""Measure the dynamical PDMF-to-IMF correction from PeTar snapshots.

The initial and final particles are matched by ID.  This lets the analysis
separate three effects that are otherwise easy to mix together:

1. preferential escape (fit the *birth* masses of final survivors),
2. stellar evolution (replace survivor birth masses by final masses), and
3. finite projected aperture (select final stars in an M45-sized footprint).

PeTar's Python analysis module is the preferred reader.  NPZ input is also
supported so the scientific logic can be tested on machines without PeTar.
NPZ files must contain ``id``, ``mass`` and ``pos`` (N x 3); ``time_myr`` is
optional.  Results here are component-star mass functions.  Do not add the
result to a separately inferred unresolved-binary correction unless the two
selection definitions have explicitly been reconciled.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DEFAULT_RADII_PC = np.array([2.0, 4.0, 8.0, 12.09, 20.0])


@dataclass(frozen=True)
class Snapshot:
    particle_id: np.ndarray
    mass: np.ndarray
    position: np.ndarray
    time_myr: float
    source: str
    raw_particle_count: int | None = None
    artificial_removed: int = 0
    unused_removed: int = 0
    member_masses_restored: int = 0


def _physical_petar_particles(particle_id, mass, position, status, mass_backup):
    """Return physical stars using PeTar's ArtificialParticleInformation rules.

    PeTar raw snapshots include algorithmic particles.  In the upstream C++
    implementation, singles have ``status == mass_backup == 0``, subsystem
    members have ``status < 0`` and a positive backup mass, and artificial
    particles (including centres of mass) have ``status > 0``.  A member's
    physical mass is its backup mass while it is represented by a subsystem.
    Unknown combinations are rejected instead of silently biasing the MF.
    """
    particle_id = np.asarray(particle_id)
    mass = np.asarray(mass, float)
    position = np.asarray(position, float)
    status = np.asarray(status, float)
    mass_backup = np.asarray(mass_backup, float)
    expected = (len(mass),)
    if any(array.shape != expected for array in (status, mass_backup)):
        raise ValueError("PeTar status and mass_bk must each have shape (N,)")
    if not np.all(np.isfinite(status)) or not np.all(np.isfinite(mass_backup)):
        raise ValueError("PeTar status and mass_bk must be finite")

    single = (status == 0.0) & (mass_backup == 0.0)
    member = (status < 0.0) & (mass_backup > 0.0)
    unused = (status < 0.0) & (mass_backup < 0.0)
    artificial = status > 0.0
    recognized = single | member | unused | artificial
    if not np.all(recognized):
        bad = np.flatnonzero(~recognized)
        preview = [
            {
                "index": int(index),
                "status": float(status[index]),
                "mass_bk": float(mass_backup[index]),
            }
            for index in bad[:5]
        ]
        raise ValueError(
            f"Unrecognized PeTar artificial-particle state for {len(bad)} rows: "
            f"{preview}"
        )

    physical = single | member
    physical_mass = mass[physical].copy()
    physical_mass[member[physical]] = mass_backup[member]
    accounting = {
        "raw_particle_count": int(len(mass)),
        "physical_particle_count": int(np.count_nonzero(physical)),
        "artificial_removed": int(np.count_nonzero(artificial)),
        "unused_removed": int(np.count_nonzero(unused)),
        "member_masses_restored": int(np.count_nonzero(member)),
    }
    return (
        particle_id[physical],
        physical_mass,
        position[physical],
        accounting,
    )


def mle_powerlaw(masses, mass_min: float, mass_max: float) -> dict:
    """Fit dN/dm proportional to m**(-alpha), including both truncations."""
    selected = np.asarray(masses, float)
    selected = selected[
        np.isfinite(selected)
        & (selected >= mass_min)
        & (selected <= mass_max)
    ]
    if len(selected) < 10:
        return {"alpha": math.nan, "alpha_err": math.nan, "n": len(selected)}

    alpha_grid = np.linspace(0.1, 5.0, 4901)
    exponent = 1.0 - alpha_grid
    close = np.isclose(alpha_grid, 1.0)
    normalization = np.empty_like(alpha_grid)
    regular = ~close
    normalization[regular] = exponent[regular] / (
        mass_max ** exponent[regular] - mass_min ** exponent[regular]
    )
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


def _validate_snapshot(snapshot: Snapshot) -> Snapshot:
    particle_id = np.asarray(snapshot.particle_id)
    mass = np.asarray(snapshot.mass, float)
    position = np.asarray(snapshot.position, float)
    if particle_id.ndim != 1 or mass.ndim != 1:
        raise ValueError("Particle IDs and masses must be one-dimensional")
    if position.shape != (len(mass), 3) or len(particle_id) != len(mass):
        raise ValueError("Snapshot arrays must have shapes (N,), (N,), (N, 3)")
    if len(np.unique(particle_id)) != len(particle_id):
        raise ValueError(f"Particle IDs are not unique in {snapshot.source}")
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError(f"Masses must be finite and positive in {snapshot.source}")
    if not np.all(np.isfinite(position)):
        raise ValueError(f"Positions must be finite in {snapshot.source}")
    return Snapshot(
        particle_id=particle_id,
        mass=mass,
        position=position,
        time_myr=float(snapshot.time_myr),
        source=snapshot.source,
        raw_particle_count=(
            len(mass) if snapshot.raw_particle_count is None
            else int(snapshot.raw_particle_count)
        ),
        artificial_removed=int(snapshot.artificial_removed),
        unused_removed=int(snapshot.unused_removed),
        member_masses_restored=int(snapshot.member_masses_restored),
    )


def load_npz(path: Path) -> Snapshot:
    with np.load(path) as data:
        missing = {"id", "mass", "pos"} - set(data.files)
        if missing:
            raise ValueError(f"{path} is missing NPZ fields: {sorted(missing)}")
        time_myr = float(np.asarray(data["time_myr"]).reshape(-1)[0]) \
            if "time_myr" in data.files else math.nan
        particle_id = np.asarray(data["id"])
        mass = np.asarray(data["mass"], float)
        position = np.asarray(data["pos"], float)
        accounting = {}
        has_status = "status" in data.files
        has_mass_backup = "mass_bk" in data.files
        if has_status != has_mass_backup:
            raise ValueError(
                f"{path} must provide both status and mass_bk, or neither"
            )
        if has_status:
            particle_id, mass, position, accounting = _physical_petar_particles(
                particle_id,
                mass,
                position,
                data["status"],
                data["mass_bk"],
            )
        snapshot = Snapshot(
            particle_id=particle_id,
            mass=mass,
            position=position,
            time_myr=time_myr,
            source=str(path),
            raw_particle_count=accounting.get("raw_particle_count", len(mass)),
            artificial_removed=accounting.get("artificial_removed", 0),
            unused_removed=accounting.get("unused_removed", 0),
            member_masses_restored=accounting.get("member_masses_restored", 0),
        )
    return _validate_snapshot(snapshot)


def load_petar(
    path: Path,
    package_path: Path | None,
    interrupt_mode: str,
    external_mode: str,
    snapshot_format: str,
) -> Snapshot:
    if package_path is not None:
        sys.path.insert(0, str(package_path.resolve()))
    import petar

    particle_kwargs = {}
    if interrupt_mode != "none":
        particle_kwargs["interrupt_mode"] = interrupt_mode
    if external_mode != "none":
        particle_kwargs["external_mode"] = external_mode
    header_kwargs = {"snapshot_format": snapshot_format}
    if external_mode != "none":
        header_kwargs["external_mode"] = external_mode

    header = petar.PeTarDataHeader(str(path), **header_kwargs)
    particle = petar.Particle(**particle_kwargs)
    if snapshot_format == "binary":
        offset = (
            petar.HEADER_OFFSET_WITH_CM
            if external_mode != "none"
            else petar.HEADER_OFFSET
        )
        particle.fromfile(str(path), offset=offset)
    else:
        particle.loadtxt(str(path), skiprows=1)

    if int(header.n) != int(particle.size):
        raise ValueError(
            f"PeTar header N={header.n} but reader returned {particle.size}; "
            "check --interrupt-mode, --external-mode and --snapshot-format"
        )
    if not hasattr(particle, "status") or not hasattr(particle, "mass_bk"):
        raise ValueError(
            "PeTar reader did not expose status and mass_bk; refusing to treat "
            "raw snapshot rows as physical stars"
        )
    particle_id, mass, position, accounting = _physical_petar_particles(
        particle.id,
        particle.mass,
        particle.pos,
        particle.status,
        particle.mass_bk,
    )
    snapshot = Snapshot(
        particle_id=particle_id,
        mass=mass,
        position=position,
        time_myr=float(header.time),
        source=str(path),
        raw_particle_count=accounting["raw_particle_count"],
        artificial_removed=accounting["artificial_removed"],
        unused_removed=accounting["unused_removed"],
        member_masses_restored=accounting["member_masses_restored"],
    )
    return _validate_snapshot(snapshot)


def load_snapshot(path: Path, args) -> Snapshot:
    if args.reader == "npz" or (args.reader == "auto" and path.suffix == ".npz"):
        return load_npz(path)
    try:
        return load_petar(
            path,
            args.petar_package_path,
            args.interrupt_mode,
            args.external_mode,
            args.snapshot_format,
        )
    except ImportError as exc:
        raise RuntimeError(
            "The PeTar Python module is unavailable. Supply "
            "--petar-package-path or use NPZ input for validation."
        ) from exc


def mass_weighted_center(position, masses):
    return np.sum(position * masses[:, None], axis=0) / np.sum(masses)


def shrinking_sphere_center(position, masses, retain_fraction=0.8, minimum=128):
    """Robust cluster center that is not dragged far into tidal tails."""
    position = np.asarray(position, float)
    masses = np.asarray(masses, float)
    selected = np.arange(len(masses))
    center = mass_weighted_center(position[selected], masses[selected])
    while len(selected) > minimum:
        radius = np.linalg.norm(position[selected] - center, axis=1)
        keep_n = max(minimum, int(math.ceil(retain_fraction * len(selected))))
        selected = selected[np.argsort(radius)[:keep_n]]
        updated = mass_weighted_center(position[selected], masses[selected])
        if np.linalg.norm(updated - center) < 1e-10:
            center = updated
            break
        center = updated
    return center, int(len(selected))


def projection_directions(count):
    """Deterministic approximately uniform lines of sight on a sphere."""
    if count < 3:
        raise ValueError("At least three projection directions are required")
    directions = [
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, 1.0, 0.0]),
        np.array([0.0, 0.0, 1.0]),
    ]
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    remaining = count - 3
    for index in range(remaining):
        z = 1.0 - 2.0 * (index + 0.5) / remaining
        transverse = math.sqrt(max(0.0, 1.0 - z * z))
        phi = index * golden_angle
        directions.append(
            np.array([transverse * math.cos(phi), transverse * math.sin(phi), z])
        )
    return np.asarray(directions)


def match_snapshots(initial: Snapshot, final: Snapshot) -> dict:
    initial_order = np.argsort(initial.particle_id)
    final_order = np.argsort(final.particle_id)
    initial_ids = initial.particle_id[initial_order]
    final_ids = final.particle_id[final_order]
    common, initial_index, final_index = np.intersect1d(
        initial_ids, final_ids, assume_unique=True, return_indices=True
    )
    return {
        "id": common,
        "birth_mass": initial.mass[initial_order[initial_index]],
        "final_mass": final.mass[final_order[final_index]],
        "final_position": final.position[final_order[final_index]],
        "n_initial": len(initial_ids),
        "n_final": len(final_ids),
        "n_matched": len(common),
        "n_lost_from_initial": len(initial_ids) - len(common),
        "n_final_not_in_initial": len(final_ids) - len(common),
    }


def _fit_row(label, masses, mass_min, mass_max, **extra):
    fit = mle_powerlaw(masses, mass_min, mass_max)
    return {"sample": label, **extra, **fit}


def analyze(initial, final, mass_min, mass_max, radii_pc, n_projections=32):
    matched = match_snapshots(initial, final)
    if matched["n_final_not_in_initial"]:
        raise ValueError(
            f"Final snapshot has {matched['n_final_not_in_initial']} unmatched IDs"
        )
    if matched["n_matched"] < 10:
        raise ValueError("Fewer than 10 initial/final particle IDs matched")

    birth_mass = matched["birth_mass"]
    final_mass = matched["final_mass"]
    position = matched["final_position"].copy()
    center, center_sample_size = shrinking_sphere_center(position, final_mass)
    position -= center
    radius_3d = np.linalg.norm(position, axis=1)
    directions = projection_directions(n_projections)

    rows = [
        _fit_row(
            "initial_global_birth_mass",
            initial.mass,
            mass_min,
            mass_max,
            geometry="global",
            radius_inner_pc=0.0,
            radius_pc=math.inf,
            projection="none",
        ),
        _fit_row(
            "final_survivors_birth_mass",
            birth_mass,
            mass_min,
            mass_max,
            geometry="global",
            radius_inner_pc=0.0,
            radius_pc=math.inf,
            projection="none",
        ),
        _fit_row(
            "final_survivors_current_mass",
            final_mass,
            mass_min,
            mass_max,
            geometry="global",
            radius_inner_pc=0.0,
            radius_pc=math.inf,
            projection="none",
        ),
    ]

    for radius_pc in radii_pc:
        selected_3d = radius_3d <= radius_pc
        rows.append(
            _fit_row(
                "final_current_mass_3d",
                final_mass[selected_3d],
                mass_min,
                mass_max,
                geometry="sphere",
                radius_inner_pc=0.0,
                radius_pc=float(radius_pc),
                projection="none",
            )
        )
        for projection_index, line_of_sight in enumerate(directions):
            parallel = position @ line_of_sight
            radius_projected = np.sqrt(
                np.maximum(radius_3d * radius_3d - parallel * parallel, 0.0)
            )
            selected = radius_projected <= radius_pc
            rows.append(
                _fit_row(
                    "final_current_mass_projected",
                    final_mass[selected],
                    mass_min,
                    mass_max,
                    geometry="cylinder",
                    radius_inner_pc=0.0,
                    radius_pc=float(radius_pc),
                    projection=f"p{projection_index:03d}",
                )
            )

    annulus_edges = np.concatenate(([0.0], np.asarray(radii_pc, float)))
    for projection_index, line_of_sight in enumerate(directions):
        parallel = position @ line_of_sight
        radius_projected = np.sqrt(
            np.maximum(radius_3d * radius_3d - parallel * parallel, 0.0)
        )
        for radius_inner, radius_outer in zip(
            annulus_edges[:-1], annulus_edges[1:]
        ):
            selected = (
                (radius_projected >= radius_inner)
                & (radius_projected < radius_outer)
            )
            rows.append(
                _fit_row(
                    "final_current_mass_projected_annulus",
                    final_mass[selected],
                    mass_min,
                    mass_max,
                    geometry="annulus",
                    radius_inner_pc=float(radius_inner),
                    radius_pc=float(radius_outer),
                    projection=f"p{projection_index:03d}",
                )
            )

    initial_alpha = rows[0]["alpha"]
    survivor_birth_alpha = rows[1]["alpha"]
    survivor_current_alpha = rows[2]["alpha"]
    target_radius = float(radii_pc[np.argmin(np.abs(radii_pc - 12.09))])
    target_rows = [
        row
        for row in rows
        if row["sample"] == "final_current_mass_projected"
        and row["radius_pc"] == target_radius
    ]
    projected_alphas = np.array([row["alpha"] for row in target_rows], float)
    projected_alpha = float(np.nanmedian(projected_alphas))

    summary = {
        "status": "component_star_dynamical_correction",
        "definition": "delta_alpha = measured_PDMF_alpha - birth_IMF_alpha",
        "mass_range_msun": [float(mass_min), float(mass_max)],
        "initial_time_myr": initial.time_myr,
        "final_time_myr": final.time_myr,
        "particle_accounting": {
            key: int(matched[key])
            for key in (
                "n_initial",
                "n_final",
                "n_matched",
                "n_lost_from_initial",
                "n_final_not_in_initial",
            )
        },
        "reader_accounting": {
            "initial": {
                "raw_particle_count": (
                    len(initial.mass)
                    if initial.raw_particle_count is None
                    else initial.raw_particle_count
                ),
                "physical_particle_count": len(initial.mass),
                "artificial_removed": initial.artificial_removed,
                "unused_removed": initial.unused_removed,
                "member_masses_restored": initial.member_masses_restored,
            },
            "final": {
                "raw_particle_count": (
                    len(final.mass)
                    if final.raw_particle_count is None
                    else final.raw_particle_count
                ),
                "physical_particle_count": len(final.mass),
                "artificial_removed": final.artificial_removed,
                "unused_removed": final.unused_removed,
                "member_masses_restored": final.member_masses_restored,
            },
        },
        "center": {
            "method": "shrinking_sphere_mass_weighted",
            "position_pc": center.tolist(),
            "final_center_sample_size": center_sample_size,
        },
        "alpha": {
            "initial_global_birth_mass": initial_alpha,
            "final_survivors_birth_mass": survivor_birth_alpha,
            "final_survivors_current_mass": survivor_current_alpha,
            "final_projected_aperture_median": projected_alpha,
            "final_projected_aperture_values": projected_alphas.tolist(),
            "n_projections": int(n_projections),
            "projection_standard_deviation": float(np.nanstd(projected_alphas)),
            "aperture_radius_pc": target_radius,
        },
        "delta_alpha": {
            "survival_selection": survivor_birth_alpha - initial_alpha,
            "stellar_evolution_after_survival": (
                survivor_current_alpha - survivor_birth_alpha
            ),
            "finite_aperture": projected_alpha - survivor_current_alpha,
            "total_pdmf_minus_imf": projected_alpha - initial_alpha,
            "correction_to_add_to_pdmf_for_imf": initial_alpha - projected_alpha,
        },
        "limitations": [
            "Component-star mass functions; unresolved observational systems are not synthesized.",
            "Missing IDs combine escape, removal and merger unless event catalogs are supplied.",
            "Uniform sky projections quantify orientation sensitivity but not Gaia selection.",
            "A production inference needs an ensemble over initial conditions and random seeds.",
        ],
    }
    return summary, rows


def write_outputs(prefix: Path, summary: dict, rows: list[dict]):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_name(prefix.name + "_profiles").with_suffix(".csv")
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def sample_power_law(rng, n, alpha, mass_min, mass_max):
    exponent = 1.0 - alpha
    u = rng.random(n)
    return (
        mass_min**exponent
        + u * (mass_max**exponent - mass_min**exponent)
    ) ** (1.0 / exponent)


def synthetic_snapshots(seed=20260813, n=12000):
    """Create a deterministic sign test with evaporation and segregation."""
    rng = np.random.default_rng(seed)
    birth_mass = sample_power_law(rng, n, 2.30, 0.30, 2.50)
    initial_position = rng.normal(size=(n, 3))
    particle_id = np.arange(1, n + 1)

    # Preferentially remove low-mass stars, producing a flatter survivor MF.
    retain_probability = np.clip(0.68 + 0.22 * np.log(birth_mass / 0.30), 0.2, 0.98)
    retained = rng.random(n) < retain_probability
    final_mass = birth_mass[retained].copy()
    final_position = rng.normal(size=(retained.sum(), 3))
    # High-mass stars are more concentrated; the aperture MF should flatten.
    final_position *= (3.2 / np.sqrt(final_mass))[:, None]

    initial = Snapshot(
        particle_id, birth_mass, initial_position, 0.0, "synthetic_initial"
    )
    final = Snapshot(
        particle_id[retained], final_mass, final_position, 125.0, "synthetic_final"
    )
    return initial, final


def run_self_test(output_prefix: Path):
    test_id = np.arange(1, 6)
    test_mass = np.array([1.0, 0.0, 3.0, 0.0, 0.0])
    test_position = np.zeros((5, 3))
    test_status = np.array([0.0, -12.0, 2.0, 3.0, -1.0e30])
    test_mass_backup = np.array([0.0, 0.7, 3.0, 0.0, -1.0e30])
    clean_id, clean_mass, _, reader_check = _physical_petar_particles(
        test_id,
        test_mass,
        test_position,
        test_status,
        test_mass_backup,
    )
    unknown_state_rejected = False
    try:
        _physical_petar_particles(
            np.array([1]),
            np.array([1.0]),
            np.zeros((1, 3)),
            np.array([0.0]),
            np.array([1.0]),
        )
    except ValueError:
        unknown_state_rejected = True

    initial, final = synthetic_snapshots()
    summary, rows = analyze(
        initial,
        final,
        0.30,
        2.50,
        np.array([2.0, 4.0, 8.0, 12.09, 20.0]),
        n_projections=32,
    )
    delta = summary["delta_alpha"]
    checks = {
        "survival_selection_flattens": delta["survival_selection"] < -0.05,
        "finite_aperture_flattens": delta["finite_aperture"] < -0.05,
        "all_final_ids_match": summary["particle_accounting"]["n_final_not_in_initial"] == 0,
        "artificial_particles_removed": (
            clean_id.tolist() == [1, 2]
            and np.allclose(clean_mass, [1.0, 0.7])
            and reader_check["artificial_removed"] == 2
            and reader_check["unused_removed"] == 1
            and reader_check["member_masses_restored"] == 1
        ),
        "unknown_particle_state_rejected": unknown_state_rejected,
    }
    summary["self_test"] = checks
    summary["status"] = "synthetic_validation_only"
    if not all(checks.values()):
        raise AssertionError(f"Synthetic validation failed: {checks}")
    return (*write_outputs(output_prefix, summary, rows), summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial", type=Path)
    parser.add_argument("--final", type=Path)
    parser.add_argument("--reader", choices=("auto", "petar", "npz"), default="auto")
    parser.add_argument("--petar-package-path", type=Path)
    parser.add_argument(
        "--interrupt-mode", choices=("none", "bse", "mobse", "bseEmp"), default="bse"
    )
    parser.add_argument("--external-mode", choices=("none", "galpy"), default="none")
    parser.add_argument("--snapshot-format", choices=("ascii", "binary"), default="ascii")
    parser.add_argument("--mass-min", type=float, default=0.30)
    parser.add_argument("--mass-max", type=float, default=2.50)
    parser.add_argument("--radii-pc", type=float, nargs="+", default=DEFAULT_RADII_PC)
    parser.add_argument("--n-projections", type=int, default=32)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=HERE / "results/petar_pdmf_analysis",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        json_path, csv_path, summary = run_self_test(args.output_prefix)
    else:
        if args.initial is None or args.final is None:
            parser.error("--initial and --final are required unless --self-test is used")
        radii_pc = np.unique(np.asarray(args.radii_pc, float))
        if np.any(radii_pc <= 0):
            parser.error("--radii-pc values must be positive")
        initial = load_snapshot(args.initial, args)
        final = load_snapshot(args.final, args)
        summary, rows = analyze(
            initial,
            final,
            args.mass_min,
            args.mass_max,
            radii_pc,
            n_projections=args.n_projections,
        )
        summary["inputs"] = {"initial": str(args.initial), "final": str(args.final)}
        json_path, csv_path = write_outputs(args.output_prefix, summary, rows)

    print(json.dumps(summary, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
