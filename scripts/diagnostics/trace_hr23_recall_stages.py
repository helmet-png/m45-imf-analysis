#!/usr/bin/env python
"""Trace saved HR23 M45 members through baseline probability and CMD stages."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BINS = [(-float("inf"), 4.0), (4.0, 5.2), (5.2, 8.0), (8.0, 12.0),
        (12.0, 16.0), (16.0, 18.0), (18.0, float("inf"))]


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_baseline(path):
    with path.open(encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle, delimiter=" ", skipinitialspace=True))


def bin_label(g):
    for lo, hi in BINS:
        if lo <= g < hi:
            if lo == -float("inf"):
                return f"G < {hi:g}"
            if hi == float("inf"):
                return f"G >= {lo:g}"
            return f"{lo:g} <= G < {hi:g}"
    raise AssertionError(g)


def probability(value):
    value = float(value)
    if not 0.0 <= value <= 1.0:
        raise argparse.ArgumentTypeError("probability must be in [0, 1]")
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hr23-prob", type=probability, default=0.7)
    ap.add_argument("--pipeline-prob", type=probability, default=0.7)
    ap.add_argument("--output", default="results/hr23_recall_stage_trace.json")
    args = ap.parse_args()

    hr = [r for r in read_csv(ROOT / "data" / "hr23_Melotte_22.csv")
          if float(r["Prob"]) >= args.hr23_prob]
    baseline = {r["source_id"]: r for r in read_baseline(ROOT / "results" / "baseline.dat")}
    cmd_ids = {r["source_id"] for r in read_csv(ROOT / "data" / "cmd_members.csv")}

    stages = ["not_in_saved_baseline", "baseline_below_pipeline_probability",
              "baseline_pass_probability_not_in_cmd", "in_cmd"]
    totals = {stage: 0 for stage in stages}
    by_bin = {bin_label((lo + hi) / 2 if abs(lo) != float("inf") and abs(hi) != float("inf")
                        else (hi - 1 if lo == -float("inf") else lo)):
              {stage: 0 for stage in stages} for lo, hi in BINS}
    rows = []
    for star in hr:
        source_id = star["GaiaDR3"]
        base = baseline.get(source_id)
        if source_id in cmd_ids:
            stage = "in_cmd"
        elif base is None:
            stage = "not_in_saved_baseline"
        elif float(base["probs_final"]) < args.pipeline_prob:
            stage = "baseline_below_pipeline_probability"
        else:
            stage = "baseline_pass_probability_not_in_cmd"
        gbin = bin_label(float(star["Gmag"]))
        totals[stage] += 1
        by_bin[gbin][stage] += 1
        rows.append({"source_id": source_id, "hr23_probability": float(star["Prob"]),
                     "Gmag": float(star["Gmag"]), "stage": stage,
                     "pipeline_probability": float(base["probs_final"]) if base else None})

    output = {
        "status": "saved_file_stage_trace_not_membership_truth",
        "hr23_probability_threshold": args.hr23_prob,
        "pipeline_probability_threshold": args.pipeline_prob,
        "external_members": len(hr), "stage_totals": totals,
        "stage_fractions": ({k: v / len(hr) for k, v in totals.items()}
                            if hr else {k: 0.0 for k in totals}),
        "by_G_bin": by_bin, "stars": rows,
        "limits": [
            "The saved baseline is an intermediate project snapshot, not necessarily the original Gaia query universe.",
            "Not in baseline does not mean non-member; below project probability does not prove HR23 is wrong.",
            "Pass probability but absent from CMD localises a later selection loss but does not by itself identify the exact quality cut.",
        ],
    }
    out = ROOT / args.output
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"external_members": len(hr), "stage_totals": totals,
                      "by_G_bin": by_bin}, indent=2))


if __name__ == "__main__":
    main()
