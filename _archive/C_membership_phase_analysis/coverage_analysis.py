# -*- coding: utf-8 -*-
"""拆解「涵蓋率」的損失來自哪裡：半徑切、還是星等切？

順便釐清 HR23 成員在潮汐半徑內外的分布 —— rt 之外的星是「運動學上有關聯」
但「重力上已不束縛」，這兩件事不同。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
RA, DEC = 56.60083, 24.11389
RT_DEG = 4.71        # HR23 給 M45 的潮汐半徑
RTOT_DEG = 14.78     # 總半徑（含潮汐尾、星冕）


def sep(ra, dec):
    a, d = np.radians(ra), np.radians(dec)
    a0, d0 = np.radians(RA), np.radians(DEC)
    c = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(a - a0)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))


hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
r = sep(np.asarray(hr["RA_ICRS"], float), np.asarray(hr["DE_ICRS"], float))
g = np.asarray(hr["Gmag"], float)
inrt = np.array([str(v).strip() == "True" for v in hr["inrt"]])
n_all = len(hr)
print(f"HR23 給 M45 的成員共 {n_all:,} 顆\n")

print("=== 涵蓋率的損失來自哪裡 ===")
print(f"{'條件':<28}{'成員數':>8}{'涵蓋率':>9}{'相對全天損失':>14}")
cases = [
    ("全天（HR23 的全部）", np.ones(n_all, bool)),
    ("只切半徑 5 度", r <= 5),
    ("只切星等 G<18", g <= 18),
    ("兩者都切", (r <= 5) & (g <= 18)),
    ("半徑 5 度 + G<19", (r <= 5) & (g <= 19)),
    ("半徑 5 度 + G<20", (r <= 5) & (g <= 20)),
    ("半徑 15 度 + G<18", (r <= 15) & (g <= 18)),
    ("半徑 15 度 + G<20", (r <= 15) & (g <= 20)),
]
for label, m in cases:
    n = int(m.sum())
    print(f"{label:<28}{n:>8,}{n/n_all*100:>8.1f}%{n_all-n:>14,}")

print("\n=== 用同樣的算力，往哪個方向走比較划算 ===")
print("（耗時為先前實測／外推，pyUPMASK 內圈成本約隨 N^2）")
opts = [
    ("目前：5 度 + G<18", (r <= 5) & (g <= 18), "10 分"),
    ("加深星等：5 度 + G<20", (r <= 5) & (g <= 20), "17 分"),
    ("擴大半徑：15 度 + G<18", (r <= 15) & (g <= 18), "8.1 小時"),
]
base = int(((r <= 5) & (g <= 18)).sum())
for label, m, cost in opts:
    n = int(m.sum())
    print(f"  {label:<26}{n:>6,} 顆（+{n-base:>4}）  {cost:>9}")

print("\n=== 潮汐半徑內外：束縛 vs 只是運動學關聯 ===")
print(f"HR23 的 rt = {RT_DEG} 度（重力束縛的邊界）")
print(f"HR23 的 rtot = {RTOT_DEG} 度（含潮汐尾、星冕的總延伸）\n")
for lab, m in [("inrt = True（在潮汐半徑內）", inrt),
               ("inrt = False（在潮汐半徑外）", ~inrt)]:
    n = int(m.sum())
    print(f"{lab:<30}{n:>6,} 顆 ({n/n_all*100:.1f}%)")
    print(f"    角距 中位 {np.median(r[m]):.2f} 度，"
          f"範圍 {r[m].min():.2f} – {r[m].max():.2f} 度")
    print(f"    G 中位 {np.median(g[m]):.2f}")

print("\n=== 角距分布：外圍那些星佔多少 ===")
for lo, hi in [(0, 2), (2, 4.71), (4.71, 8), (8, 15), (15, 99)]:
    m = (r >= lo) & (r < hi)
    n = int(m.sum())
    if n:
        tag = "  <- 潮汐半徑內" if hi <= 4.71 else "  <- 潮汐半徑外（不再束縛）"
        print(f"  {lo:>5.2f}–{hi:<5.2f}度: {n:>5} 顆 ({n/n_all*100:>4.1f}%)"
              f"  G 中位 {np.median(g[m]):.2f}{tag}")
