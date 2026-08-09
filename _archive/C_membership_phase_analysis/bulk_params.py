# -*- coding: utf-8 -*-
"""取星團的整體運動參數，供 prep.py --deproject 使用。"""
import argparse
import json
import urllib.parse
import urllib.request

VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"

ap = argparse.ArgumentParser()
ap.add_argument("--cluster", default="Melotte_22")
a = ap.parse_args()

adql = ('SELECT "pmRA","pmDE","Plx","RV","n_RV","rtpc","dist50" '
        'FROM "J/A+A/673/A114/clusters" '
        f"WHERE \"Name\"='{a.cluster}'")
body = urllib.parse.urlencode({
    "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql}).encode()
req = urllib.request.Request(VIZIER, data=body, headers={"User-Agent": "m45/1.0"})
d = json.loads(urllib.request.urlopen(req, timeout=300).read().decode())

cols = [m["name"] for m in d["metadata"]]
row = dict(zip(cols, d["data"][0]))
for k, v in row.items():
    print(f"  {k:<8} {v}")
print("\nprep.py 用的參數：")
print(f"  --bulk {row['pmRA']} {row['pmDE']} {row['Plx']} {row['RV']}")
