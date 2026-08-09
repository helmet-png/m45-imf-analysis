# -*- coding: utf-8 -*-
"""比較各變因跑出來的成員名單差多少。

重點不是誰的 F1 好看（F1 是對 HR23 而言，而 HR23 也只是另一個演算法的輸出），
而是「改了這個設定，成員名單到底有沒有變」。名單幾乎不變 = 該設定不影響結論。
"""
import argparse
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
_ap = argparse.ArgumentParser()
_ap.add_argument("--thr", type=float, default=0.99, help="成員判定門檻")
THR = _ap.parse_args().thr

hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
hr_ref = set(np.asarray(hr["GaiaDR3"], np.int64)[
    np.asarray(hr["Prob"], float) >= 0.5].tolist())

runs = {}
for f in sorted((HERE / "results").glob("*.dat")):
    t = Table.read(f, format="ascii")
    ids = np.asarray(t["source_id"], np.int64)
    p = np.asarray(t["probs_final"], float)
    runs[f.stem] = set(ids[p >= THR].tolist())

print(f"成員判定門檻 P >= {THR}\n")
print(f"{'變因':<12}{'選出':>8}{'∩HR23':>9}{'HR23漏':>9}{'我方獨有':>10}")
for name, s in runs.items():
    print(f"{name:<12}{len(s):>8,}{len(s & hr_ref):>9,}"
          f"{len(hr_ref - s):>9,}{len(s - hr_ref):>10,}")

names = list(runs)
print(f"\n兩兩比較（對稱差 / 聯集，越小代表兩個設定給的名單越像）")
print(f"{'':<12}" + "".join(f"{n:>12}" for n in names))
for a in names:
    row = f"{a:<12}"
    for b in names:
        if a == b:
            row += f"{'-':>12}"
        else:
            sa, sb = runs[a], runs[b]
            row += f"{len(sa ^ sb) / len(sa | sb) * 100:>11.1f}%"
    print(row)

base = runs.get("baseline")
if base:
    print(f"\n相對 baseline 的實際變動：")
    for n, s in runs.items():
        if n == "baseline":
            continue
        print(f"  {n:<10} 多了 {len(s - base):>4} 顆，少了 {len(base - s):>4} 顆"
              f"（baseline {len(base):,} 顆）")
