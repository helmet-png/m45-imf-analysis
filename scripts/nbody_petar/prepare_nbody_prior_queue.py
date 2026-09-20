#!/usr/bin/env python
"""Prepare a reviewable A5 N-body run manifest without starting simulations.

The manifest is the hand-off between parameter review and the remote queue.
It deliberately emits commands only; dispatching remains a separate, gated step.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_manifest(seeds: list[int], n: int, radius_pc: float, virial_q: float) -> dict:
    runs = []
    for segregation, seed in zip((0.3, 0.5, 0.7), seeds):
        tag = f"a5_s{segregation:.1f}_seed{seed}"
        runs.append(
            {
                "tag": tag,
                "mass_segregation": segregation,
                "seed": seed,
                "command": [
                    "mcluster_sse",
                    "-N",
                    str(n),
                    "-P",
                    "0",
                    "-S",
                    f"{segregation:g}",
                    "-R",
                    f"{radius_pc:g}",
                    "-Q",
                    f"{virial_q:g}",
                    "-s",
                    str(seed),
                ],
            }
        )
    return {
        "status": "prepared_not_dispatched",
        "task": "nbody_prior_from_radial",
        "n_stars": n,
        "radius_pc": radius_pc,
        "virial_ratio_q": virial_q,
        "runs": runs,
        "notes": [
            "This file is a parameter manifest, not a simulation result.",
            "Review the three initial conditions before queue submission.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, nargs=3, default=[301, 302, 303])
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--radius-pc", type=float, default=2.3)
    parser.add_argument("--virial-q", type=float, default=0.5)
    args = parser.parse_args()
    if args.n <= 0 or args.radius_pc <= 0 or args.virial_q <= 0:
        parser.error("n, radius-pc and virial-q must be positive")
    manifest = build_manifest(args.seeds, args.n, args.radius_pc, args.virial_q)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} ({len(manifest['runs'])} runs; not dispatched)")


if __name__ == "__main__":
    main()
