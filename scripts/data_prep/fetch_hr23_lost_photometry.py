#!/usr/bin/env python
"""Fetch only the Gaia photometric-quality fields needed for 62 traced stars."""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAP = "https://gaia.ari.uni-heidelberg.de/tap/sync"
FIELDS = ["source_id", "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag",
          "bp_rp", "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
          "phot_rp_mean_flux_over_error", "phot_bp_rp_excess_factor"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap-url", default=DEFAULT_TAP)
    ap.add_argument("--input", default="results/hr23_recall_stage_trace.json")
    ap.add_argument("--output", default="data/hr23_passprob_notcmd_gaia_photometry.csv")
    args = ap.parse_args()

    trace = json.loads((ROOT / args.input).read_text(encoding="utf-8"))
    ids = sorted(int(row["source_id"]) for row in trace["stars"]
                 if row["stage"] == "baseline_pass_probability_not_in_cmd")
    if len(ids) != 62:
        raise RuntimeError(f"Expected the traced 62 stars, found {len(ids)}; refusing a broader query")
    query = ("SELECT " + ", ".join(FIELDS) + " FROM gaiadr3.gaia_source "
             + "WHERE source_id IN (" + ",".join(map(str, ids)) + ")")
    body = urllib.parse.urlencode({"REQUEST": "doQuery", "LANG": "ADQL",
                                   "FORMAT": "csv", "QUERY": query}).encode("ascii")
    request = urllib.request.Request(args.tap_url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=180) as response:
        text = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    returned = {int(row["source_id"]) for row in rows}
    if returned != set(ids):
        raise RuntimeError(f"Gaia returned {len(returned)}/{len(ids)} requested IDs")
    out = ROOT / args.output
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"requested": len(ids), "returned": len(rows), "output": str(out)}))


if __name__ == "__main__":
    main()
