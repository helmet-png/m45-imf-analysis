# -*- coding: utf-8 -*-
"""檢查切半實驗的搜尋網格邊界有沒有把散布截斷。

**動機**：切半實驗量出的「高估倍數」是拿兩半答案的差當真實 sigma。
但那個差是在一個有限網格上找出來的 —— 若最佳點常常落在網格邊界上，
真正的散布就被牆擋住了，量到的差會偏小、高估倍數會偏低。

這正是本專案已經踩過一次的坑：金屬量先驗上界原本 0.25，
後驗 95 百分位跑到 0.224、走者貼牆，報出的 +0.194 是被牆決定的。
切半實驗用的網格上下界更窄（MH 只有 0.00–0.30），要先確認同樣的事沒再發生。

輸入直接讀 logs/overconf_fine.log，避免手抄出錯。
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "overconf_fine.log"

NAMES = ["logAge", "A_V", "f_bin", "alpha", "MH"]
# 與 measure_overconfidence.py 的 coarse 網格一致
BOUNDS = {
    "logAge": (8.00, 8.30),
    "A_V":    (0.00, 0.24),      # arange(0.00, 0.29, 0.06) -> 最大 0.24
    "f_bin":  (0.35, 0.70),
    "alpha":  (2.00, 2.80),
    "MH":     (0.00, 0.30),
}
# 精修後的有效解析度，用來判定「貼在牆上」
STEP = {"logAge": 0.0125, "A_V": 0.015, "f_bin": 0.0125,
        "alpha": 0.025, "MH": 0.025}

PAT = re.compile(
    r"切分\s*(\d+):\s*logAge=([\d.]+)/([\d.]+)\s+A_V=([\d.]+)/([\d.]+)\s+"
    r"f_bin=([\d.]+)/([\d.]+)\s+alpha=([\d.]+)/([\d.]+)\s+MH=([\d.]+)/([\d.]+)")


def main():
    text = LOG.read_text(encoding="utf-8")
    halves = []          # 每個元素是一個「半」的五個參數值
    for m in PAT.finditer(text):
        g = [float(x) for x in m.groups()[1:]]
        halves.append(g[0::2])
        halves.append(g[1::2])
    arr = np.array(halves)
    print(f"讀到 {len(arr)} 個半樣本擬合結果\n")

    print(f"{'參數':<8}{'網格範圍':>16}{'實際範圍':>16}"
          f"{'貼下界':>8}{'貼上界':>8}{'佔比':>8}")
    total_pinned = np.zeros(len(arr), bool)
    for i, nm in enumerate(NAMES):
        lo, hi = BOUNDS[nm]
        tol = STEP[nm] * 1.01
        at_lo = arr[:, i] <= lo + tol
        at_hi = arr[:, i] >= hi - tol
        total_pinned |= at_lo | at_hi
        frac = (at_lo | at_hi).mean()
        print(f"{nm:<8}{f'{lo:.2f}–{hi:.2f}':>16}"
              f"{f'{arr[:,i].min():.2f}–{arr[:,i].max():.2f}':>16}"
              f"{at_lo.sum():>8}{at_hi.sum():>8}{frac:>7.0%}")

    print(f"\n至少有一個參數貼在牆上的半樣本：{total_pinned.sum()}/{len(arr)} "
          f"（{total_pinned.mean():.0%}）")

    print("\n各參數在網格窗內的位置分布（看是不是塞滿整個窗）：")
    for i, nm in enumerate(NAMES):
        lo, hi = BOUNDS[nm]
        u = (arr[:, i] - lo) / (hi - lo)
        print(f"  {nm:<8}窗內相對位置 中位 {np.median(u):.2f}，"
              f"最小 {u.min():.2f}，最大 {u.max():.2f}，"
              f"標準差 {u.std():.2f}")

    print("\n判讀：貼牆比例高，代表量到的兩半差值是被網格截斷後的值，")
    print("      推得的 sigma 偏小、高估倍數偏低，只能當下限。")


if __name__ == "__main__":
    main()
