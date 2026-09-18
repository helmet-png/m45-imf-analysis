#!/usr/bin/env python3
"""Build definition-matched M45 system catalogs from completed PeTar runs.

This is a short post-processing job: it never re-integrates a cluster.  For
each completed run it exports the processed t=0 and t=125 Myr catalogs, then
measures component, primary, system-total, and photometric-equivalent slope
corrections.  The script fails closed if a required processed catalog is
missing, so an incomplete multiplicity inventory cannot silently become a
scientific result.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATALOG_SCRIPT = HERE / "petar_system_catalog.py"
BRIDGE_SCRIPT = HERE / "pdmf_system_definition_bridge.py"
CATEGORIES = ("single", "binary", "triple", "quadruple")


def snapshot_arguments(run_dir: Path, snapshot_index: int, time_myr: float) -> list[str]:
    """Return catalog-export arguments after checking the complete inventory."""
    base = run_dir / f"data.{snapshot_index}"
    files = {category: Path(f"{base}.{category}") for category in CATEGORIES}
    if not files["single"].is_file():
        raise FileNotFoundError(f"Required processed single catalog is missing: {files['single']}")

    supplied = ["--single", str(files["single"])]
    for category in CATEGORIES[1:]:
        path = files[category]
        if path.is_file():
            supplied.extend([f"--{category}", str(path)])
    return supplied + ["--time-myr", str(time_myr), "--confirm-complete"]


def run_command(command: list[str]) -> None:
    printable = " ".join(command)
    print(f"$ {printable}", flush=True)
    subprocess.run(command, check=True)


def process_run(
    run_dir: Path,
    output_dir: Path,
    petar_package_path: Path | None,
    aperture_pc: float,
    n_projections: int,
) -> dict:
    run_id = run_dir.name
    run_output = output_dir / run_id
    run_output.mkdir(parents=True, exist_ok=True)
    catalog_paths = {}
    for snapshot_index, time_myr, tag in ((0, 0.0, "t0"), (25, 125.0, "t125")):
        output = run_output / f"{run_id}_{tag}_systems.npz"
        command = [sys.executable, str(CATALOG_SCRIPT)]
        command.extend(snapshot_arguments(run_dir, snapshot_index, time_myr))
        if petar_package_path is not None:
            command.extend(["--petar-package-path", str(petar_package_path)])
        command.extend(["--output", str(output)])
        run_command(command)
        catalog_paths[tag] = output

    bridge_output = run_output / f"{run_id}_definition_bridge.json"
    run_command([
        sys.executable,
        str(BRIDGE_SCRIPT),
        "--initial", str(catalog_paths["t0"]),
        "--final", str(catalog_paths["t125"]),
        "--mass-min", "0.30",
        "--mass-max", "2.50",
        "--aperture-pc", str(aperture_pc),
        "--n-projections", str(n_projections),
        "--output", str(bridge_output),
    ])
    return {"run_id": run_id, "bridge": str(bridge_output)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-glob", default="m45_*_formal_125myr_*")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "m45_system_definition_bridge")
    parser.add_argument("--petar-package-path", type=Path)
    parser.add_argument("--aperture-pc", type=float, default=11.68)
    parser.add_argument("--n-projections", type=int, default=32)
    parser.add_argument("--require-run-count", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.aperture_pc <= 0 or args.n_projections < 1:
        parser.error("aperture and projection count must be positive")
    run_dirs = sorted(path for path in args.runs_root.glob(args.run_glob) if path.is_dir())
    if len(run_dirs) != args.require_run_count:
        parser.error(
            f"Expected exactly {args.require_run_count} run directories under {args.runs_root}, found {len(run_dirs)}: "
            + ", ".join(path.name for path in run_dirs)
        )

    plan = {
        "status": "dry_run" if args.dry_run else "running",
        "runs_root": str(args.runs_root),
        "run_ids": [path.name for path in run_dirs],
        "mass_range_msun": [0.30, 2.50],
        "aperture_radius_pc": args.aperture_pc,
        "n_projections": args.n_projections,
    }
    print(json.dumps(plan, indent=2), flush=True)
    if args.dry_run:
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    completed = [
        process_run(
            run_dir, args.output_dir, args.petar_package_path,
            args.aperture_pc, args.n_projections,
        )
        for run_dir in run_dirs
    ]
    manifest = {**plan, "status": "complete", "completed": completed}
    manifest_path = args.output_dir / "m45_system_definition_bridge_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
