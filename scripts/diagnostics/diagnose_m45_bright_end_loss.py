#!/usr/bin/env python3
"""Trace bright M45 stars through the checked-in pipeline checkpoints.

This is deliberately a *read-only* diagnostic.  It does not rerun pyUPMASK
or query Gaia.  `results/baseline.dat` is the saved result immediately before
the membership threshold in ``run_pipeline.load_members``; `cmd_members.csv`
is the saved result after that threshold and the step-2 photometry cuts.

The raw Gaia table is not checked in, so this program must not claim whether a
star that failed the membership threshold would also have failed a step-2
photometry cut.  It writes a small JSON record that keeps this distinction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "results" / "baseline.dat"
CMD = ROOT / "data" / "cmd_members.csv"
DEFAULT_IDS = (65205373152172032, 66529975427235712)


def _rows_by_id(table: np.ndarray) -> dict[int, np.void]:
    return {int(row["source_id"]): row for row in table}


def _as_number(value: object) -> float:
    return float(value)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", type=int, action="append", dest="ids",
                    help="source_id to trace; repeatable")
    ap.add_argument("--output", type=Path,
                    default=ROOT / "results" / "bright_end_loss_diagnosis.json")
    args = ap.parse_args()
    ids = tuple(args.ids) if args.ids else DEFAULT_IDS

    baseline = np.genfromtxt(BASELINE, names=True, dtype=None, encoding="utf-8")
    cmd = np.genfromtxt(CMD, delimiter=",", names=True, dtype=None,
                        encoding="utf-8")
    by_baseline = _rows_by_id(baseline)
    by_cmd = _rows_by_id(cmd)

    records = []
    for source_id in ids:
        row = by_baseline.get(source_id)
        record: dict[str, object] = {"source_id": source_id}
        if row is None:
            record.update({"in_baseline": False, "in_cmd_members": False,
                           "stage": "not_evaluable"})
            records.append(record)
            continue

        probability = _as_number(row["probs_final"])
        record.update({
            "in_baseline": True,
            "gmag_baseline": _as_number(row["Gmag"]),
            "parallax_mas_baseline": _as_number(row["Plx"]),
            "pmra_masyr_baseline": _as_number(row["pmRA"]),
            "pmdec_masyr_baseline": _as_number(row["pmDE"]),
            "ruwe_baseline": _as_number(row["RUWE"]),
            "membership_probability": probability,
            "membership_threshold": 0.7,
            "passes_membership_threshold": probability >= 0.7,
            "in_cmd_members": source_id in by_cmd,
        })
        if probability < 0.7:
            record["stage"] = "membership_threshold"
            record["step2_quality_status"] = "not_evaluable_not_passed_to_step2"
        elif source_id in by_cmd:
            record["stage"] = "retained"
            record["step2_quality_status"] = "retained"
        else:
            record["stage"] = "step2_or_missing_join"
            record["step2_quality_status"] = "raw_table_needed"
        records.append(record)

    bright = baseline[(baseline["Gmag"] >= 4.0) & (baseline["Gmag"] <= 5.203287)]
    output = {
        "purpose": "Read-only trace of selected bright stars through saved checkpoints",
        "inputs": {"baseline": str(BASELINE.relative_to(ROOT)),
                   "cmd_members": str(CMD.relative_to(ROOT))},
        "raw_gaia_table_available": (ROOT / "data" / "m45_r5_g18_plx4.csv").exists(),
        "bright_interval_baseline_rows": [
            {"source_id": int(r["source_id"]), "gmag": _as_number(r["Gmag"]),
             "parallax_mas": _as_number(r["Plx"]),
             "membership_probability": _as_number(r["probs_final"]),
             "ruwe": _as_number(r["RUWE"])} for r in bright],
        "traced_sources": records,
        "interpretation_guardrail": (
            "A source below P=0.7 is excluded before step 2.  Without the raw "
            "Gaia table, this diagnostic cannot test its hypothetical step-2 "
            "photometry status."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")

    print(f"baseline bright interval rows: {len(bright)}")
    for item in records:
        print(json.dumps(item, ensure_ascii=False, sort_keys=True))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
