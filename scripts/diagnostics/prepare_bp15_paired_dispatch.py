#!/usr/bin/env python
"""Create and validate the formal BP20/BP15 paired-forward dispatch plan.

This does not submit anything to Kaggle.  It makes the ten long jobs explicit,
checks that the BP15-only inputs exist, and prevents accidental use of a seed
or output tag twice.  The plan is intentionally separate from kaggle_queue.txt:
someone must choose accounts after confirming Kaggle login is available.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
sys.path.insert(0, str(ROOT))
GRID = "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"
BP15_INPUTS = [
    RESULTS / "cmd_members_bp15_smoke.csv",
    RESULTS / "errmodel_bp15_smoke.npz",
    RESULTS / "selection_bp15_smoke.npz",
]


def command(sample: str, offset: int, n_syn: int) -> dict:
    if n_syn != 40_000:
        raise ValueError("formal BP15/BP20 dispatch requires n_syn=40000")
    tag = f"_bp{sample}_formal_40k_rep{offset}"
    args = [
        "--procs", "4", "--n-syn", str(n_syn), "--repeats", "1",
        "--repeat-offset", str(offset), "--configs", "C", "--refines", "3,3",
        "--grid", GRID, "--tag", tag,
    ]
    extras = ["measure_overconfidence.py", "injection_recovery.py"]
    if sample == "15":
        # kaggle_sync copies explicit extras into the kernel root, so the three
        # flags below deliberately omit the local results/ prefix.
        extras += [str(p.relative_to(ROOT)).replace("\\", "/") for p in BP15_INPUTS]
        args += [
            "--members-file", "cmd_members_bp15_smoke.csv",
            "--errmodel-file", "errmodel_bp15_smoke.npz",
            "--selection-file", "selection_bp15_smoke.npz",
        ]
    return {"sample": f"BP{sample}", "repeat_offset": offset,
            "tag": tag, "args": args, "extra_files": extras}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0,1,2,3,4",
                    help="Five or more non-negative repeat offsets")
    ap.add_argument("--n-syn", type=int, default=40_000)
    ap.add_argument("--write", action="store_true",
                    help="Write results/bp15_formal_paired_dispatch.json")
    ap.add_argument("--payload-check", action="store_true",
                    help="Build a temporary BP15 Kaggle payload and verify paths")
    args = ap.parse_args()
    offsets = [int(x) for x in args.seeds.split(",") if x.strip()]
    if len(offsets) < 5 or len(offsets) != len(set(offsets)) or min(offsets) < 0:
        raise ValueError("--seeds must contain at least five unique non-negative offsets")
    missing = [str(p.relative_to(ROOT)) for p in BP15_INPUTS if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing BP15 inputs: " + ", ".join(missing))

    jobs = [command(sample, offset, args.n_syn)
            for offset in offsets for sample in ("20", "15")]
    tags = [job["tag"] for job in jobs]
    if len(tags) != len(set(tags)):
        raise RuntimeError("Duplicate output tag: refusing to create a colliding plan")
    plan = {
        "status": "ready_for_external_account_assignment",
        "purpose": "Formal paired BP20/BP15 diagnostic; not a new headline IMF.",
        "n_synthetic": args.n_syn,
        "refines": "3,3",
        "paired_offsets": offsets,
        "pairing_rule": "For each offset, run BP20 and BP15 once with exactly the same offset; analyse BP15-BP20 per offset.",
        "bp15_inputs_verified": [str(p.relative_to(ROOT)).replace("\\", "/") for p in BP15_INPUTS],
        "jobs": jobs,
        "acceptance": [
            "Each job must produce a complete NPZ with a manifest matching its planned tag and offset.",
            "Do not average all BP20 and BP15 values separately; pair by repeat_offset first.",
            "Report the paired mean and paired standard error, plus all five individual differences.",
            "This uses a narrower local PARSEC grid for controlled comparison and cannot replace the headline grid by itself.",
        ],
    }
    if args.payload_check:
        # Test the real packager without credentials or any network call.  This
        # is deliberately a temporary directory: no queued job is modified.
        from kaggle_sync import build_payload
        bp15 = next(job for job in jobs if job["sample"] == "BP15")
        with tempfile.TemporaryDirectory(prefix="m45_bp15_payload_") as tmp:
            payload = Path(tmp) / "payload"
            build_payload("fit_real.py", bp15["extra_files"], payload)
            expected = [
                payload / "fit_real.py",
                payload / "cmd_members_bp15_smoke.csv",
                payload / "errmodel_bp15_smoke.npz",
                payload / "selection_bp15_smoke.npz",
                payload / "pipeline",
                payload / "data" / "cmd_members.csv",
            ]
            missing_payload = [str(p.name) for p in expected if not p.exists()]
            if missing_payload:
                raise RuntimeError("Payload check failed: " + ", ".join(missing_payload))
        plan["payload_check"] = "passed_with_temporary_local_payload"
    if args.write:
        (RESULTS / "bp15_formal_paired_dispatch.json").write_text(
            json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, indent=2))


if __name__ == "__main__":
    main()
