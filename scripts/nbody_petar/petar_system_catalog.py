#!/usr/bin/env python
"""Export PeTar processed single/multiple catalogs to a definition-bridge NPZ.

Run ``petar.data.process`` first, then provide every object catalog produced for
the snapshot.  Binary trees are flattened recursively, so binary, hierarchical
triple and binary-binary quadruple files all become component rows sharing one
``system_id``.  Omitting a non-empty multiplicity catalog changes the scientific
definition, so the command records every supplied path and requires an explicit
``--confirm-complete`` acknowledgement.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


def _load_ascii(data, path: Path):
    data.loadtxt(str(path))
    return data


def _particle(petar, interrupt_mode: str):
    kwargs = {} if interrupt_mode == "none" else {"interrupt_mode": interrupt_mode}
    return petar.Particle(**kwargs)


def _binary(petar, left, right):
    return petar.Binary(left, right)


def _leaves(node):
    if hasattr(node, "p1") and hasattr(node, "p2"):
        yield from _leaves(node.p1)
        yield from _leaves(node.p2)
    else:
        yield node


def _append_category(
    node,
    category: str,
    system_offset: int,
    particle_ids: list,
    masses: list,
    positions: list,
    system_ids: list,
):
    leaves = list(_leaves(node))
    if not leaves:
        return system_offset, {"category": category, "n_systems": 0, "multiplicity": 0}
    sizes = {int(leaf.size) for leaf in leaves}
    if len(sizes) != 1:
        raise ValueError(f"{category} leaf arrays have inconsistent sizes: {sizes}")
    n_systems = sizes.pop()
    for leaf in leaves:
        particle_ids.append(np.asarray(leaf.id))
        masses.append(np.asarray(leaf.mass, float))
        positions.append(np.asarray(leaf.pos, float))
        system_ids.append(np.arange(system_offset, system_offset + n_systems))
    return system_offset + n_systems, {
        "category": category,
        "n_systems": n_systems,
        "multiplicity": len(leaves),
        "n_components": n_systems * len(leaves),
    }


def export_catalog(args) -> dict:
    if args.petar_package_path is not None:
        sys.path.insert(0, str(args.petar_package_path.resolve()))
    import petar

    particle_ids, masses, positions, system_ids = [], [], [], []
    categories = []
    offset = 0

    single = _load_ascii(_particle(petar, args.interrupt_mode), args.single)
    n_single = int(single.size)
    particle_ids.append(np.asarray(single.id))
    masses.append(np.asarray(single.mass, float))
    positions.append(np.asarray(single.pos, float))
    system_ids.append(np.arange(offset, offset + n_single))
    categories.append(
        {
            "category": "single",
            "n_systems": n_single,
            "multiplicity": 1,
            "n_components": n_single,
            "path": str(args.single),
        }
    )
    offset += n_single

    specs = [
        ("binary", args.binary, lambda: _binary(
            petar,
            _particle(petar, args.interrupt_mode),
            _particle(petar, args.interrupt_mode),
        )),
        ("triple", args.triple, lambda: _binary(
            petar,
            _particle(petar, args.interrupt_mode),
            _binary(
                petar,
                _particle(petar, args.interrupt_mode),
                _particle(petar, args.interrupt_mode),
            ),
        )),
        ("quadruple", args.quadruple, lambda: _binary(
            petar,
            _binary(
                petar,
                _particle(petar, args.interrupt_mode),
                _particle(petar, args.interrupt_mode),
            ),
            _binary(
                petar,
                _particle(petar, args.interrupt_mode),
                _particle(petar, args.interrupt_mode),
            ),
        )),
    ]
    for category, path, constructor in specs:
        if path is None:
            continue
        node = _load_ascii(constructor(), path)
        offset, accounting = _append_category(
            node,
            category,
            offset,
            particle_ids,
            masses,
            positions,
            system_ids,
        )
        accounting["path"] = str(path)
        categories.append(accounting)

    particle_id = np.concatenate(particle_ids)
    mass = np.concatenate(masses)
    position = np.concatenate(positions)
    system_id = np.concatenate(system_ids)
    if len(np.unique(particle_id)) != len(particle_id):
        unique, count = np.unique(particle_id, return_counts=True)
        duplicate = unique[count > 1][:10].tolist()
        raise ValueError(
            "Components occur in more than one processed category; "
            f"duplicate IDs include {duplicate}"
        )
    if not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError("Processed component masses must be finite and positive")
    if not np.all(np.isfinite(position)):
        raise ValueError("Processed component positions must be finite")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        id=particle_id,
        mass=mass,
        pos=position,
        system_id=system_id,
        time_myr=np.array([args.time_myr]),
    )
    metadata = {
        "status": "physical_system_catalog",
        "output": str(args.output),
        "time_myr": args.time_myr,
        "interrupt_mode": args.interrupt_mode,
        "confirmed_complete": bool(args.confirm_complete),
        "n_components": int(len(particle_id)),
        "n_systems": int(offset),
        "categories": categories,
        "warning": (
            "Scientific use is valid only if every non-empty single/binary/"
            "triple/quadruple catalog from the same processed snapshot was supplied."
        ),
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    metadata["metadata_output"] = str(metadata_path)
    return metadata


def run_self_test() -> dict:
    def leaf(ids, masses):
        ids = np.asarray(ids)
        return SimpleNamespace(
            id=ids,
            mass=np.asarray(masses, float),
            pos=np.column_stack((ids, np.zeros((len(ids), 2)))),
            size=len(ids),
        )

    # Two hierarchical triples: one outer leaf plus two inner leaves.
    tree = SimpleNamespace(
        p1=leaf([1, 4], [1.0, 0.8]),
        p2=SimpleNamespace(
            p1=leaf([2, 5], [0.7, 0.6]),
            p2=leaf([3, 6], [0.5, 0.4]),
        ),
    )
    particle_ids, masses, positions, system_ids = [], [], [], []
    offset, accounting = _append_category(
        tree, "triple", 10, particle_ids, masses, positions, system_ids
    )
    ids = np.concatenate(particle_ids)
    groups = np.concatenate(system_ids)
    checks = {
        "recursive_leaf_count": accounting["multiplicity"] == 3,
        "two_systems": accounting["n_systems"] == 2 and offset == 12,
        "all_components_preserved": sorted(ids.tolist()) == [1, 2, 3, 4, 5, 6],
        "grouping_preserved": (
            sorted(ids[groups == 10].tolist()) == [1, 2, 3]
            and sorted(ids[groups == 11].tolist()) == [4, 5, 6]
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"System catalog self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "self_test": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--triple", type=Path)
    parser.add_argument("--quadruple", type=Path)
    parser.add_argument("--time-myr", type=float)
    parser.add_argument(
        "--interrupt-mode", choices=("none", "bse", "mobse", "bseEmp"), default="bse"
    )
    parser.add_argument("--petar-package-path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm-complete", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return
    if args.single is None or args.time_myr is None or args.output is None:
        parser.error("--single, --time-myr and --output are required")
    if not args.confirm_complete:
        parser.error(
            "--confirm-complete is required after checking that every non-empty "
            "multiplicity catalog for this snapshot is supplied"
        )
    for path in (args.single, args.binary, args.triple, args.quadruple):
        if path is not None and not path.is_file():
            parser.error(f"input file does not exist: {path}")
    metadata = export_catalog(args)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
