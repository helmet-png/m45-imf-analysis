# -*- coding: utf-8 -*-
"""追兩件先前擱置的事：
  (1) inrt 到底是什麼定義（rt=4.71 度，但 5 度錐內有 1,595 顆成員、Nt 只有 1,014）
  (2) 我判為成員但 HR23 完全沒收的那 20 顆是什麼來歷
      —— HR23 有一張 membrej（被剔除的候選成員）表，先去那裡找
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
RA0, DEC0 = 56.60083, 24.11389


def vizier(adql, fmt="json"):
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": fmt, "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER, data=body, headers={"User-Agent": "m45/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def sep_deg(ra, dec, ra0=RA0, dec0=DEC0):
    """天球角距（度）。"""
    a, d, a0, d0 = map(np.radians, (ra, dec, ra0, dec0))
    c = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(a - a0)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
ra = np.asarray(hr["RA_ICRS"], float)
dec = np.asarray(hr["DE_ICRS"], float)
prob = np.asarray(hr["Prob"], float)
inrt = np.asarray([str(v).strip() == "True" for v in hr["inrt"]])
r = sep_deg(ra, dec)

print("=== (1) inrt 是什麼 ===")
print(f"  HR23 M45 成員總數 {len(hr):,}，inrt=True {inrt.sum():,}")
print(f"  inrt=True  角距範圍 {r[inrt].min():.2f} ~ {r[inrt].max():.2f} 度"
      f"（中位 {np.median(r[inrt]):.2f}）")
print(f"  inrt=False 角距範圍 {r[~inrt].min():.2f} ~ {r[~inrt].max():.2f} 度"
      f"（中位 {np.median(r[~inrt]):.2f}）")
print(f"  5 度錐內的成員 {int((r <= 5).sum()):,}，其中 inrt=True {int((inrt & (r <= 5)).sum()):,}")
overlap = int((inrt & (r > 4.71)).sum()), int((~inrt & (r <= 4.71)).sum())
print(f"  inrt=True 但角距 > rt(4.71): {overlap[0]:,} 顆")
print(f"  inrt=False 但角距 <= rt   : {overlap[1]:,} 顆")
print(f"  inrt=True 的 Prob 中位 {np.median(prob[inrt]):.3f}，"
      f"inrt=False 的 Prob 中位 {np.median(prob[~inrt]):.3f}")

print("\n=== (2) 那 20 顆爭議星 ===")
cmp_t = Table.read(HERE / "data" / "comparison.csv", format="csv")
p = np.asarray(cmp_t["my_prob"], float)
hr_p = np.asarray(cmp_t["hr23_prob"], float)
ids = np.asarray(cmp_t["source_id"], np.int64)
disputed = ids[(p >= .99) & ~np.isfinite(hr_p)]
print(f"  我 P>=0.99 且不在 HR23 成員表（任何 Prob）的：{len(disputed)} 顆")

# 這些星在不在 HR23 的「被剔除候選成員」表裡？
idlist = ",".join(str(int(i)) for i in disputed)
raw = vizier('SELECT "GaiaDR3","Name","Prob" FROM "J/A+A/673/A114/membrej" '
             f'WHERE "GaiaDR3" IN ({idlist})', fmt="csv")
rej = Table.read(raw.decode(), format="csv") if raw.strip().count(b"\n") else None
if rej is not None and len(rej):
    print(f"  其中出現在 membrej（被 HR23 剔除的候選）：{len(rej)} 顆")
    for row in rej:
        print(f"    {row['GaiaDR3']}  被歸給 {row['Name']}  Prob={row['Prob']}")
else:
    print("  沒有一顆出現在 membrej -> HR23 的流程根本沒把它們當成候選")

# 有沒有被 HR23 指派給「別的」星團？
raw = vizier('SELECT "GaiaDR3","Name","Prob" FROM "J/A+A/673/A114/members" '
             f'WHERE "GaiaDR3" IN ({idlist})', fmt="csv")
other = Table.read(raw.decode(), format="csv") if raw.strip().count(b"\n") else None
if other is not None and len(other):
    print(f"  被 HR23 指派給其他星團：{len(other)} 顆")
    for row in other:
        print(f"    {row['GaiaDR3']}  -> {row['Name']}  Prob={row['Prob']}")
else:
    print("  也沒有被指派給任何其他星團")

# 它們自己的 Gaia 品質長怎樣
m = np.isin(ids, disputed)
for c in ("Gmag", "Plx", "pmRA", "pmDE"):
    if c in cmp_t.colnames:
        v = np.asarray(cmp_t[c], float)[m]
        print(f"  {c:<6} 中位 {np.median(v):8.3f}  範圍 {v.min():8.3f} ~ {v.max():8.3f}")

# 它們在天上離團心多遠？HDBSCAN 是密度式的，外圍密度低本來就容易漏
xx = np.hypot(np.asarray(cmp_t["_x"], float), np.asarray(cmp_t["_y"], float))
acc = np.asarray(cmp_t["hr23_member"], int).astype(bool)
print(f"\n  天球半徑（度）：爭議星 中位 {np.median(xx[m]):.2f}"
      f"（範圍 {xx[m].min():.2f}~{xx[m].max():.2f}）"
      f" vs 公認成員 中位 {np.median(xx[acc]):.2f}")
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5.1)]:
    b = (xx >= lo) & (xx < hi)
    n_d, n_a = int((b & m).sum()), int((b & acc).sum())
    rate = f"{n_d/(n_a+n_d)*100:5.1f}%" if n_a + n_d else "    -"
    print(f"    r {lo}-{hi:g} 度：爭議 {n_d:>3}  公認 {n_a:>4}  爭議佔比 {rate}")

# inrt 是不是三維判準？用 1/視差當距離，算與團心的三維距離
print("\n=== (1b) inrt 是不是三維判準 ===")
d_pc = 1000.0 / np.asarray(hr["Plx"], float)
d0 = 1000.0 / 7.366
sep3d = np.sqrt(d_pc**2 + d0**2 - 2 * d_pc * d0 * np.cos(np.radians(r)))
for lab, mask in [("inrt=True", inrt), ("inrt=False", ~inrt)]:
    q = np.percentile(sep3d[mask], [50, 90, 99])
    print(f"  {lab:<11} 三維距團心 中位 {q[0]:6.1f} / 90% {q[1]:6.1f} / 99% {q[2]:7.1f} pc")
print("  （HR23 給 M45 的潮汐半徑 rtpc 約 11.6 pc）")
