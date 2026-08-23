#!/usr/bin/env python3
"""Join the saved HR23 M45 snapshot to the saved bright-star cross-check."""
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    with (ROOT / "data" / "hr23_Melotte_22.csv").open(encoding="utf-8") as f:
        hr = {r["GaiaDR3"]: r for r in csv.DictReader(f)}
    with (ROOT / "results" / "m45_hipparcos_gaia_bright_crosscheck_2026-08-20.csv").open(encoding="utf-8") as f:
        bright = list(csv.DictReader(f))

    rows = []
    for r in bright:
        sid = r["gaia_source_id"]
        h = hr.get(sid)
        rows.append({
            "hip": r["hip"], "gaia_source_id": sid or None,
            "gaia_g": r["gaia_g"] or None,
            "pipeline_probability": r["baseline_probability"] or None,
            "in_cmd_members": r["in_cmd_members"] == "true",
            "hr23_in_saved_snapshot": h is not None,
            "hr23_probability": float(h["Prob"]) if h else None,
            "guardrail": ("not_in_snapshot_is_not_nonmember" if sid and not h
                          else ""),
        })
    dest = ROOT / "results" / "m45_bright_hr23_crosscheck.json"
    dest.write_text(json.dumps({
        "hr23_snapshot": "data/hr23_Melotte_22.csv",
        "bright_input": "results/m45_hipparcos_gaia_bright_crosscheck_2026-08-20.csv",
        "rows": rows,
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(rows)} Hipparcos rows)")


if __name__ == "__main__":
    main()
