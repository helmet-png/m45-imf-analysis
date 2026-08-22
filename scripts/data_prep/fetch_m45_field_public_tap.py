#!/usr/bin/env python
"""Fetch the bounded M45 Gaia field without the expensive COUNT query."""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAP = "https://gaia.ari.uni-heidelberg.de/tap/sync"
TOP = 20000
RA_DEG = 56.60083
DEC_DEG = 24.11389
RADIUS_DEG = 5.0
FIELDS = [
    "source_id", "ra", "dec", "pmra", "pmdec", "parallax",
    "pmra_error", "pmdec_error", "parallax_error",
    "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp",
    "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
    "phot_rp_mean_flux_over_error", "phot_bp_rp_excess_factor", "ruwe",
    "non_single_star",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap-url", default=DEFAULT_TAP)
    ap.add_argument("--output", default="data/m45_r5_g18_plx4.csv")
    args = ap.parse_args()
    query = (
        f"SELECT TOP {TOP} " + ", ".join(FIELDS)
        + " FROM gaiadr3.gaia_source WHERE "
        + f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{RA_DEG},{DEC_DEG},{RADIUS_DEG})) "
        + "AND phot_g_mean_mag<=18 AND parallax>=4"
    )
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query,
    }).encode("ascii")
    request = urllib.request.Request(args.tap_url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=300) as response:
        text = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows:
        raise RuntimeError("Gaia returned no rows")
    if len(rows) >= TOP:
        raise RuntimeError(f"Query reached TOP {TOP}; refusing a potentially truncated field")
    if not (5000 <= len(rows) <= 10000):
        raise RuntimeError(f"Unexpected M45 field size {len(rows)}; refusing to write")
    returned_fields = list(rows[0])
    if returned_fields != FIELDS:
        raise RuntimeError(f"Unexpected Gaia columns: {returned_fields}")
    out = ROOT / args.output
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({
        "status": "complete_bounded_public_tap_query",
        "rows": len(rows), "top_guard": TOP, "output": str(out),
        "query_geometry": {"ra": RA_DEG, "dec": DEC_DEG, "radius_deg": RADIUS_DEG},
        "cuts": {"g_max": 18.0, "parallax_min_mas": 4.0},
    }))


if __name__ == "__main__":
    main()
