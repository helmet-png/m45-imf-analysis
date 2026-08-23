#!/usr/bin/env python
"""Measure CMD-sample overlap with the saved HR23 M45 member snapshot.

This is a catalogue-comparison diagnostic.  HR23 is an external comparison
catalogue, not ground truth, and the result must not be used to add stars to
the IMF sample without a separately defined membership policy.
"""
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


def label(lo, hi):
    if lo == -float("inf"):
        return f"G < {hi:g}"
    if hi == float("inf"):
        return f"G >= {lo:g}"
    return f"{lo:g} <= G < {hi:g}"


def summarise(hr, cmd_ids, threshold):
    chosen = [r for r in hr if float(r["Prob"]) >= threshold]
    total = len(chosen)
    rows = []
    for lo, hi in BINS:
        group = [r for r in chosen if lo <= float(r["Gmag"]) < hi]
        kept = sum(r["GaiaDR3"] in cmd_ids for r in group)
        rows.append({"G_bin": label(lo, hi), "external_members": len(group),
                     "in_cmd_members": kept,
                     "recall": kept / len(group) if group else None})
    kept_total = sum(r["GaiaDR3"] in cmd_ids for r in chosen)
    return {"threshold": threshold, "external_members": total,
            "in_cmd_members": kept_total,
            "recall": kept_total / total if total else None,
            "by_G_bin": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="results/hr23_cmd_recall_by_magnitude.json")
    args = ap.parse_args()
    hr = read_csv(ROOT / "data" / "hr23_Melotte_22.csv")
    cmd = read_csv(ROOT / "data" / "cmd_members.csv")
    cmd_ids = {r["source_id"] for r in cmd}
    output = {
        "status": "catalogue_overlap_diagnostic_not_membership_truth",
        "external_catalogue": "saved Hunt & Reffert 2023 M45 snapshot",
        "external_rows": len(hr), "cmd_rows": len(cmd),
        "source_id_overlap_all_hr23_rows": int(sum(r["GaiaDR3"] in cmd_ids for r in hr)),
        "threshold_summaries": [summarise(hr, cmd_ids, p) for p in (0.5, 0.7)],
        "limits": [
            "HR23 probabilities and this pipeline probabilities are different catalogue products.",
            "Recall below 100% can reflect deliberately different spatial, probability, magnitude or quality selections.",
            "This diagnostic never labels a non-overlap as a non-member and never adds it to the IMF sample.",
        ],
    }
    out = ROOT / args.output
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["threshold_summaries"], indent=2))


if __name__ == "__main__":
    main()
