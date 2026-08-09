# -*- coding: utf-8 -*-
"""比較兩種成員機率的算法：

  KDE 後驗版（pyUPMASK 預設）：P = 1/(1 + L_field/L_memb)，連續、會飽和
  頻率版（原始 UPMASK）：P = 25 輪外圈中被判為成員的比例，離散、刻度 1/25

比四件事：機率分布形狀、換種子的穩定度、與 HR23 的一致程度、穩定門檻在哪。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent

hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
hr_ref = set(np.asarray(hr["GaiaDR3"], np.int64)[
    np.asarray(hr["Prob"], float) >= 0.5].tolist())

KDE = {"seed42": "baseline", "seed43": "seed43", "seed99": "seed99"}
FRQ = {"seed42": "freq_s42", "seed43": "freq_s43", "seed99": "freq_s99"}


def load(name):
    t = Table.read(HERE / "results" / f"{name}.dat", format="ascii")
    return (np.asarray(t["source_id"], np.int64),
            np.asarray(t["probs_final"], float))


print("=== 機率分布形狀（seed42）===")
for lab, name in (("KDE 後驗", KDE["seed42"]), ("頻率版", FRQ["seed42"])):
    _, p = load(name)
    v = p[p >= 0]
    uniq = np.unique(np.round(v, 6))
    print(f"\n{lab}：{len(v):,} 顆有效，相異值 {len(uniq):,} 個")
    print(f"  最小 {v.min():.4f}  中位 {np.median(v):.4f}  最大 {v.max():.4f}")
    print(f"  P=0 的顆數 {int((v == 0).sum()):,}，P=1 的顆數 {int((v >= 0.99999).sum()):,}")
    for lo, hi in [(0, 1e-9), (1e-9, .3), (.3, .5), (.5, .7), (.7, .9),
                   (.9, .99), (.99, 1.0001)]:
        n = int(((v >= lo) & (v < hi)).sum()) if hi < 1 else \
            int(((v >= lo) & (v <= hi)).sum())
        if n:
            print(f"    {lo:g} – {hi:g}: {n:,}")

print("\n\n=== 換種子的穩定度（成員數）===")
print(f"{'門檻':>6}{'KDE:42':>9}{'43':>7}{'99':>7}{'離散':>8}"
      f"{'FRQ:42':>9}{'43':>7}{'99':>7}{'離散':>8}")
for thr in (0.5, 0.7, 0.9, 0.95, 0.99):
    row = f"{thr:>6.2f}"
    for group in (KDE, FRQ):
        ns = []
        for s in ("seed42", "seed43", "seed99"):
            _, p = load(group[s])
            ns.append(int((p >= thr).sum()))
        spread = (max(ns) - min(ns)) / np.mean(ns) * 100
        row += "".join(f"{n:>7,}" if i else f"{n:>9,}"
                       for i, n in enumerate(ns)) + f"{spread:>7.1f}%"
    print(row)

print("\n\n=== 與 HR23 的一致程度（seed42）===")
print(f"{'方法':<10}{'門檻':>6}{'選出':>8}{'命中930':>9}{'漏':>6}"
      f"{'我方獨有':>9}{'precision':>11}{'recall':>8}")
for lab, name in (("KDE 後驗", KDE["seed42"]), ("頻率版", FRQ["seed42"])):
    ids, p = load(name)
    truth = np.isin(ids, list(hr_ref))
    for thr in (0.5, 0.7, 0.9):
        sel = p >= thr
        tp = int((sel & truth).sum())
        fp = int((sel & ~truth).sum())
        fn = int((~sel & truth).sum())
        print(f"{lab:<10}{thr:>6.2f}{tp+fp:>8,}{tp:>9,}{fn:>6,}{fp:>9,}"
              f"{tp/max(tp+fp,1):>11.4f}{tp/max(tp+fn,1):>8.4f}")
