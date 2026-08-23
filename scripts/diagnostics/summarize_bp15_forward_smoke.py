#!/usr/bin/env python
"""Summarize completed paired BP20/BP15 diagnostic forward runs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def row(name: str) -> list[float]:
    with np.load(RESULTS / name, allow_pickle=False) as data:
        return np.asarray(data["C"], float)[0].tolist()


def main() -> None:
    names = ["logage", "av", "f_bin", "alpha", "mh", "q_gamma", "dav"]
    pairs = []
    # Each offset is a new paired Monte-Carlo draw.  Keep this list explicit
    # so a missing or mismatched output cannot silently be averaged in.
    for seed, suffix in [(2000, ""), (2013, "_rep1"), (2026, "_rep2")]:
        bp20 = row(f"fit_real_bp20_control_3k{suffix}.npz")
        bp15 = row(f"fit_real_bp15_smoke_3k{suffix}.npz")
        pairs.append({
            "seed": seed,
            "bp20": dict(zip(names, bp20)),
            "bp15": dict(zip(names, bp15)),
            "bp15_minus_bp20": dict(zip(names, np.subtract(bp15, bp20).tolist())),
        })
    deltas = np.asarray([[p["bp15_minus_bp20"][n] for n in names] for p in pairs])
    output = {
        "status": "diagnostic_inconclusive_monte_carlo_noise",
        "settings": {"n_synthetic": 3000, "paired_seeds": [2000, 2013, 2026],
                     "refines": [3, 3], "config": "C"},
        "pairs": pairs,
        "paired_delta_mean": dict(zip(names, deltas.mean(axis=0).tolist())),
        "paired_delta_range": dict(zip(names, np.ptp(deltas, axis=0).tolist())),
        "stopped_incomplete_runs": {
            "n_synthetic": 10000, "seed": 2026,
            "reason": "both paired jobs exceeded 55 minutes when sharing one machine; no atomic result file was produced"
        },
        "interpretation": [
            "The alpha delta changed sign across the paired seeds, so these runs cannot establish a BP15 effect.",
            "The isolated BP15 inputs and custom fit entrypoint are verified and reproducible.",
            "A formal comparison needs matched BP20/BP15 runs at 40000 synthetic systems and multiple paired seeds on separate workers.",
        ],
    }
    (RESULTS / "bp15_forward_smoke_summary.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
