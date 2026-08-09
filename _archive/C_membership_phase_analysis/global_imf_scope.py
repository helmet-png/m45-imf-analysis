# -*- coding: utf-8 -*-
"""評估「量全局 IMF」的實際規模：各半徑下的樣本量、成員涵蓋率、預估計算量。

HR23 給 M45 的總半徑 rtot = 14.78 度（含潮汐尾與星冕），潮汐半徑 rt = 4.71 度。
我們目前只做到 5 度。
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from astropy.table import Table

sys.path.insert(0, r"C:\Users\Alber\Claude\gaia-export")
import server  # noqa: E402

HERE = Path(__file__).resolve().parent
VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"
RA, DEC = 56.60083, 24.11389
# 基準：5 度、G<18、plx>4 是 6,956 顆，25 輪跑 9.8 分鐘
N_REF, MIN_REF = 6956, 9.8
RADII = [5.0, 8.0, 10.0, 12.0, 15.0]


def vizier(adql):
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER, data=body,
                                 headers={"User-Agent": "m45/1.0"})
    return json.loads(urllib.request.urlopen(req, timeout=300).read().decode())


def sep(ra, dec):
    a, d = np.radians(ra), np.radians(dec)
    a0, d0 = np.radians(RA), np.radians(DEC)
    c = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(a - a0)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


# HR23 成員的角距分布
hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
r_hr = sep(np.asarray(hr["RA_ICRS"], float), np.asarray(hr["DE_ICRS"], float))
g_hr = np.asarray(hr["Gmag"], float)
n_all = len(hr)
print(f"HR23 給 M45 的成員共 {n_all:,} 顆\n")

print(f"{'半徑':>6}{'Gaia樣本':>12}{'HR23成員':>10}{'涵蓋率':>9}"
      f"{'成員佔比':>10}{'預估耗時':>12}")
rows = []
for rad in RADII:
    p = {"mode": "cone", "ra": RA, "dec": DEC, "radius": rad,
         "mag_max": 18, "parallax_min": 4}
    n = server.count_sources(p)
    m = int(((r_hr <= rad) & (g_hr <= 18)).sum())
    cov = m / n_all * 100
    frac = m / n * 100
    # pyUPMASK 內圈成本大致隨 N^2
    est_min = MIN_REF * (n / N_REF) ** 2
    est = f"{est_min:.0f} 分" if est_min < 120 else f"{est_min/60:.1f} 小時"
    print(f"{rad:>5.0f}°{n:>12,}{m:>10,}{cov:>8.1f}%{frac:>9.2f}%{est:>12}")
    rows.append((rad, n, m, cov, est_min))
    time.sleep(2)

print("\n注意：涵蓋率的分母是 HR23 全天成員數，但 HR23 自己也只找到那些；")
print("      真正的成員可能更多，尤其是被潮汐尾帶走的低質量星。")

print("\n=== 成員的角距分布（看 5 度外還有多少）===")
for lo, hi in [(0, 5), (5, 8), (8, 10), (10, 12), (12, 15), (15, 99)]:
    m = int(((r_hr >= lo) & (r_hr < hi)).sum())
    mg = int(((r_hr >= lo) & (r_hr < hi) & (g_hr <= 18)).sum())
    if m:
        print(f"  {lo:>2}–{hi:<3}度: {m:>5} 顆（G<18 者 {mg:>5} 顆）")

print("\n=== 投影效應隨半徑（M45 整體自行運動 49.6 mas/yr）===")
for rad in RADII:
    print(f"  {rad:>5.1f}°  跨天區的自行運動變化約 "
          f"{49.6 * np.sin(np.radians(rad)):.1f} mas/yr")
print("  （對照：M45 真實內部速度彌散約 0.8 mas/yr）")
