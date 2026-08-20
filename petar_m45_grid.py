#!/usr/bin/env python
"""Validate the M45 PeTar screening grid and render reproducible commands."""
from __future__ import annotations

import argparse
import csv
import json
import shlex
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_grid(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("PeTar grid is empty")
    return rows


def parse_row(raw: dict) -> dict:
    row = dict(raw)
    for key in ("n_systems", "n_stars", "n_binaries", "profile", "seed", "priority"):
        row[key] = int(row[key])
    for key in ("binary_system_fraction", "mcluster_S", "half_mass_radius_pc"):
        row[key] = float(row[key])
    row["galactic_tide"] = row["galactic_tide"].strip().lower() == "true"
    return row


def validate_grid(rows: list[dict]) -> dict:
    parsed = [parse_row(row) for row in rows]
    errors = []
    run_ids = [row["run_id"] for row in parsed]
    if len(set(run_ids)) != len(run_ids):
        errors.append("run_id values are not unique")

    for row in parsed:
        expected_binaries = round(
            row["n_systems"] * row["binary_system_fraction"]
        )
        expected_stars = row["n_systems"] + row["n_binaries"]
        if row["n_binaries"] != expected_binaries:
            errors.append(
                f"{row['run_id']}: n_binaries={row['n_binaries']}, "
                f"expected {expected_binaries}"
            )
        if row["n_stars"] != expected_stars:
            errors.append(
                f"{row['run_id']}: n_stars={row['n_stars']}, "
                f"expected {expected_stars}"
            )
        if not 0.0 <= row["binary_system_fraction"] <= 1.0:
            errors.append(f"{row['run_id']}: binary fraction is outside [0, 1]")
        if row["profile"] not in (0, 2):
            errors.append(f"{row['run_id']}: unsupported screening profile")
        if row["profile"] == 2 and not 0.0 <= row["mcluster_S"] < 0.5:
            errors.append(f"{row['run_id']}: profile 2 requires 0 <= S < 0.5")
        if row["half_mass_radius_pc"] <= 0:
            errors.append(f"{row['run_id']}: half-mass radius must be positive")

    summary = {
        "status": "pass" if not errors else "fail",
        "grid_path": str(Path(rows[0].get("_grid_path", "petar_m45_grid.csv"))),
        "n_runs": len(parsed),
        "n_priority_1": sum(row["priority"] == 1 for row in parsed),
        "n_priority_2": sum(row["priority"] == 2 for row in parsed),
        "seeds": sorted({row["seed"] for row in parsed}),
        "half_mass_radius_pc": sorted({row["half_mass_radius_pc"] for row in parsed}),
        "binary_system_fraction": sorted(
            {row["binary_system_fraction"] for row in parsed}
        ),
        "mcluster_S": sorted({row["mcluster_S"] for row in parsed}),
        "profiles": sorted({row["profile"] for row in parsed}),
        "errors": errors,
    }
    if errors:
        raise ValueError("; ".join(errors))
    return summary


def render_commands(row: dict) -> str:
    row = parse_row(row)
    run_id = shlex.quote(row["run_id"])
    command = [
        "mcluster_sse",
        "-N", str(row["n_stars"]),
        "-B", str(row["n_binaries"]),
        "-P", str(row["profile"]),
        "-R", f"{row['half_mass_radius_pc']:.2f}",
        "-f", "1",
        "-C", "5",
        "-u", "1",
        "-s", str(row["seed"]),
        "-Z", "0.02",
        "-o", row["run_id"],
    ]
    if row["profile"] == 2:
        command[9:9] = ["-S", f"{row['mcluster_S']:.2f}"]
    mcluster = " ".join(shlex.quote(part) for part in command)
    return "\n".join(
        [
            f"mkdir -p runs/{run_id}",
            f"cd runs/{run_id}",
            f"{mcluster} > mcluster.log",
            "petar.init -s bse -v kms2pcmyr -f input <MCLUSTER_OUTPUT>",
            "export OMP_STACKSIZE=128M",
            "export OMP_NUM_THREADS=8",
            (
                f"petar -u 1 -b {row['n_binaries']} --bse-metallicity 0.02 "
                "--stellar-evolution 1 --detect-interrupt 1 "
                "-t 125.0 -o 5.0 input > petar.log 2>&1"
            ),
            "petar.data.gether data",
            "petar.data.process -i bse data.snap.lst",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=HERE / "petar_m45_grid.csv")
    parser.add_argument("--run-id")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    rows = load_grid(args.grid)
    for row in rows:
        row["_grid_path"] = str(args.grid)
    summary = validate_grid(rows)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))

    if args.run_id:
        selected = [row for row in rows if row["run_id"] == args.run_id]
        if not selected:
            parser.error(f"unknown --run-id {args.run_id!r}")
        print("\n# Review <MCLUSTER_OUTPUT> before continuing\n")
        print(render_commands(selected[0]))


if __name__ == "__main__":
    main()
