#!/usr/bin/env python
"""Aggregate completed PeTar PDMF-to-IMF runs into an uncertainty summary."""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
DELTA_KEYS = (
    "survival_selection",
    "stellar_evolution_after_survival",
    "finite_aperture",
    "total_pdmf_minus_imf",
    "correction_to_add_to_pdmf_for_imf",
)


def expand_inputs(patterns):
    paths = []
    for pattern in patterns:
        matches = [Path(path) for path in glob.glob(pattern)]
        if matches:
            paths.extend(matches)
        else:
            candidate = Path(pattern)
            if candidate.exists():
                paths.append(candidate)
    unique = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def read_grid(path):
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["run_id"]: row for row in csv.DictReader(handle)}


def infer_run_id(path, payload):
    if payload.get("run_id"):
        return str(payload["run_id"])
    name = path.stem
    for suffix in ("_pdmf", "_analysis", "_selftest"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def flatten_run(path, payload, grid):
    run_id = infer_run_id(path, payload)
    alpha = payload["alpha"]
    delta = payload["delta_alpha"]
    accounting = payload["particle_accounting"]
    row = {
        "run_id": run_id,
        "source": str(path),
        "status": payload["status"],
        "initial_time_myr": payload.get("initial_time_myr", math.nan),
        "final_time_myr": payload.get("final_time_myr", math.nan),
        "n_initial": accounting["n_initial"],
        "n_final": accounting["n_final"],
        "n_matched": accounting["n_matched"],
        "alpha_initial": alpha["initial_global_birth_mass"],
        "alpha_survivor_birth": alpha["final_survivors_birth_mass"],
        "alpha_survivor_current": alpha["final_survivors_current_mass"],
        "alpha_aperture": alpha["final_projected_aperture_median"],
        "projection_sd": alpha["projection_standard_deviation"],
        "n_projections": alpha["n_projections"],
    }
    row.update({f"delta_{key}": delta[key] for key in DELTA_KEYS})
    if run_id in grid:
        for key, value in grid[run_id].items():
            if key not in row:
                row[key] = value
    return row


def summarize(values):
    values = np.asarray(values, float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {"n": 0, "median": math.nan, "q16": math.nan, "q84": math.nan, "sd": math.nan}
    return {
        "n": int(len(values)),
        "median": float(np.median(values)),
        "q16": float(np.quantile(values, 0.16)),
        "q84": float(np.quantile(values, 0.84)),
        "sd": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
    }


def aggregate(paths, grid, allow_synthetic=False):
    rows = []
    mass_range = None
    rejected = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        status = payload.get("status")
        if status == "synthetic_validation_only" and not allow_synthetic:
            rejected.append({"path": str(path), "reason": "synthetic validation"})
            continue
        if status not in (
            "component_star_dynamical_correction",
            "synthetic_validation_only",
        ):
            rejected.append({"path": str(path), "reason": f"status={status!r}"})
            continue
        current_range = tuple(payload["mass_range_msun"])
        if mass_range is None:
            mass_range = current_range
        elif current_range != mass_range:
            raise ValueError(
                f"Mass-range mismatch: {path} uses {current_range}, expected {mass_range}"
            )
        rows.append(flatten_run(path, payload, grid))

    if not rows:
        raise ValueError("No eligible PeTar result JSON files were found")
    if len({row["run_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate run_id values in PeTar ensemble inputs")

    metrics = {
        key: summarize([row[f"delta_{key}"] for row in rows])
        for key in DELTA_KEYS
    }
    central_rows = [
        row for row in rows if row.get("priority") in ("1", 1)
    ]
    central_seed_summary = None
    if central_rows:
        central_seed_summary = {
            key: summarize([row[f"delta_{key}"] for row in central_rows])
            for key in DELTA_KEYS
        }
    summary = {
        "status": (
            "synthetic_validation_only"
            if all(row["status"] == "synthetic_validation_only" for row in rows)
            else "petar_ensemble"
        ),
        "n_runs": len(rows),
        "mass_range_msun": list(mass_range),
        "delta_alpha": metrics,
        "priority_1_seed_scatter": central_seed_summary,
        "rejected_inputs": rejected,
        "interpretation": (
            "Add correction_to_add_to_pdmf_for_imf to the matched PDMF alpha; "
            "do not combine with unresolved-binary corrections until sample definitions match."
        ),
    }
    return summary, rows


def write_outputs(prefix, summary, rows):
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_name(prefix.name + "_runs").with_suffix(".csv")
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="JSON paths or glob patterns")
    parser.add_argument("--grid", type=Path, default=HERE / "petar_m45_grid.csv")
    parser.add_argument("--allow-synthetic", action="store_true")
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=HERE / "results/petar_pdmf_ensemble",
    )
    args = parser.parse_args()

    paths = expand_inputs(args.inputs)
    if not paths:
        parser.error("no input paths matched")
    summary, rows = aggregate(
        paths, read_grid(args.grid), allow_synthetic=args.allow_synthetic
    )
    json_path, csv_path = write_outputs(args.output_prefix, summary, rows)
    print(json.dumps(summary, indent=2))
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
