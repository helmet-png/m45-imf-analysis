#!/usr/bin/env python
"""Fail-closed summary for the formal BP20/BP15 paired comparison."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def load_one(path: Path, sample: str, offset: int) -> dict:
    if offset < 0:
        raise ValueError("repeat_offset must be non-negative")
    if not path.exists():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as raw:
        if "C" not in raw or "__manifest__" not in raw:
            raise ValueError(f"{path.name}: missing C or manifest")
        c = np.asarray(raw["C"], float)
        manifest = json.loads(str(raw["__manifest__"]))
    if c.shape != (1, 7):
        raise ValueError(f"{path.name}: expected one config-C row, got {c.shape}")
    expected_tag = f"_bp{sample}_formal_40k_rep{offset}"
    if manifest.get("tag") != expected_tag:
        raise ValueError(f"{path.name}: manifest tag does not match {expected_tag}")
    if int(manifest.get("repeat_offset", -1)) != offset:
        raise ValueError(f"{path.name}: wrong repeat_offset")
    expected_inputs = ({
        "members_file": "cmd_members_bp15_smoke.csv",
        "errmodel_file": "errmodel_bp15_smoke.npz",
        "selection_file": "selection_bp15_smoke.npz",
    } if sample == "15" else {
        "members_file": "data/cmd_members.csv",
        "errmodel_file": "data/errmodel.npz",
        "selection_file": "data/selection.npz",
    })
    for field, expected in expected_inputs.items():
        if manifest.get(field) != expected:
            raise ValueError(f"{path.name}: manifest {field} does not match {expected}")
    if int(manifest.get("n_syn", -1)) != 40_000 or manifest.get("refines") != "3,3":
        raise ValueError(f"{path.name}: not the formal 40k/refines=3,3 recipe")
    return {"alpha": float(c[0, 3]), "logage": float(c[0, 0]),
            "f_bin": float(c[0, 2]), "manifest": manifest}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offsets", default="0,1,2,3,4")
    ap.add_argument("--results-dir", type=Path, default=RESULTS)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    offsets = [int(x) for x in args.offsets.split(",") if x.strip()]
    if (len(offsets) < 5 or len(set(offsets)) != len(offsets)
            or any(offset < 0 for offset in offsets)):
        raise ValueError("Need at least five unique non-negative offsets")

    pairs = []
    missing = []
    for offset in offsets:
        names = {
            sample: args.results_dir / f"fit_real_bp{sample}_formal_40k_rep{offset}.npz"
            for sample in ("20", "15")
        }
        absent = [str(p) for p in names.values() if not p.exists()]
        if absent:
            missing.extend(absent)
            continue
        bp20, bp15 = (load_one(names[s], s, offset) for s in ("20", "15"))
        pairs.append({"offset": offset, "alpha_bp20": bp20["alpha"],
                      "alpha_bp15": bp15["alpha"],
                      "delta_alpha_bp15_minus_bp20": bp15["alpha"] - bp20["alpha"]})
    if missing:
        output = {"status": "blocked_incomplete_formal_pairs", "offsets_expected": offsets,
                  "offsets_complete": [p["offset"] for p in pairs], "missing_files": missing,
                  "rule": "Do not calculate a formal mean until every planned pair is present."}
    else:
        delta = np.asarray([p["delta_alpha_bp15_minus_bp20"] for p in pairs])
        output = {"status": "complete_formal_paired_summary", "pairs": pairs,
                  "mean_delta_alpha": float(delta.mean()),
                  "paired_standard_error": float(delta.std(ddof=1) / np.sqrt(len(delta))),
                  "n_pairs": len(pairs),
                  "rule": "This is a BP-threshold diagnostic, not a replacement M45 headline."}
    if args.write:
        (args.results_dir / "bp15_formal_paired_summary.json").write_text(
            json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
