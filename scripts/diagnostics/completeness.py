# -*- coding: utf-8 -*-
"""從資料量出第 2 步測光品質篩選的完整度曲線。

**為什麼需要它**：成員判定給出 1,297 顆（P>=0.7），第 2 步的測光品質篩選
（BP/RP 流量超額、三個波段的訊噪比下限、亮端飽和）把它砍到 1,078 顆。
被砍掉的 219 顆不是隨機分布的 —— BP 訊噪比那一刀砍掉 130 顆，
而紅色暗星的 BP 流量本來就低，所以這一刀系統性偏向移除低質量端，
**正好是 IMF 最敏感的地方**。

前向模型目前只套用 G<18 與 G>4 兩個星等切，沒有模擬這組篩選。
於是模型會生出觀測裡已經被砍掉的暗紅星，擬合只好改 alpha 去補這個落差 ——
直接偏誤要測的量。

這支程式量出「每個星等的成員有多少比例通過品質篩選」，
再交給前向模型當作固定的選擇函數。**它是資料的函數，不是自由參數**，
所以不會替擬合多出一個簡併方向。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent


# 亮端飽和切（config 的 g_bright_limit）由前向模型自己套用，
# 不能再算進完整度曲線，否則同一刀被砍兩次。
G_BRIGHT = 4.0


def load_pairs(prob_min: float = 0.7):
    """回傳（篩選前的 G 星等, 顏色, 是否通過篩選）。"""
    pre_id, pre_g, pre_c = [], [], []
    with open(HERE / "data" / "comparison.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if float(r["my_prob"]) >= prob_min:
                pre_id.append(r["source_id"])
                pre_g.append(float(r["Gmag"]))
                pre_c.append(float(r["BP_RP"]) if r["BP_RP"] else np.nan)
    post = set()
    with open(HERE / "data" / "cmd_members.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            post.add(r["source_id"])
    kept = np.array([i in post for i in pre_id], bool)
    g = np.array(pre_g, float)
    sel = g >= G_BRIGHT
    return g[sel], np.array(pre_c, float)[sel], kept[sel]


def completeness_curve(bin_width: float = 0.5, prob_min: float = 0.7):
    """回傳 (G 格點中心, 存活比例)，可直接餵給 JointModel.completeness。

    星等格寬取 0.5 —— 夠細以呈現暗端的下滑，又夠粗讓每格有足夠星數；
    格子空的地方用相鄰值內插，避免 0/0。
    """
    g, _, kept = load_pairs(prob_min)
    lo = np.floor(g.min() / bin_width) * bin_width
    # 上界要用 ceil 再多加一格，否則最暗那批星會整批落在最後一個邊界之外
    # 而被 histogram 丟掉 —— 丟掉的正好是最需要的低質量端。
    hi = np.ceil(g.max() / bin_width) * bin_width + bin_width
    edges = np.arange(lo, hi + 1e-9, bin_width)
    n_all, _ = np.histogram(g, edges)
    n_ok, _ = np.histogram(g[kept], edges)
    centres = 0.5 * (edges[:-1] + edges[1:])
    good = n_all > 0
    frac = np.full(len(centres), np.nan)
    frac[good] = n_ok[good] / n_all[good]
    # 空格用有資料的鄰居內插；兩端沿用最近的有效值
    frac = np.interp(centres, centres[good], frac[good])
    return centres, np.clip(frac, 0.0, 1.0), n_all


def main():
    g, c, kept = load_pairs()
    print(f"P>=0.7 且 G>={G_BRIGHT} 的成員 {len(g):,} 顆，"
          f"通過測光品質篩選 {kept.sum():,} 顆（{kept.mean():.1%}）")
    print(f"星等範圍 {g.min():.2f} – {g.max():.2f}\n")

    centres, frac, n_all = completeness_curve(bin_width=1.0)
    print(f"{'G 區間':>12}{'成員數':>8}{'存活比例':>10}")
    for ctr, f_, n in zip(centres, frac, n_all):
        if n == 0:
            continue
        bar = "#" * int(round(f_ * 30))
        print(f"{ctr-0.5:6.1f}–{ctr+0.5:<5.1f}{n:>8}{f_:>10.3f}  {bar}")

    # 加權平均與暗端的落差 —— 這就是模型漏掉的東西有多大
    faint = g >= 16.0
    print(f"\n整體存活率 {kept.mean():.3f}；"
          f"G>=16 的暗星存活率 {kept[faint].mean():.3f}"
          f"（{faint.sum()} 顆中的 {kept[faint].sum()} 顆）")
    bright = g < 14.0
    print(f"G<14 的亮星存活率 {kept[bright].mean():.3f}"
          f"（{bright.sum()} 顆中的 {kept[bright].sum()} 顆）")

    # 一維（只看星等）夠不夠？BP 訊噪比那一刀對同星等的紅星更不利，
    # 若存活率在固定星等下還隨顏色變，就必須用二維的完整度圖。
    print("\n同一星等內，存活率是否隨顏色變（判斷一維曲線夠不夠）：")
    print(f"{'G 區間':>12}{'紅半邊':>18}{'藍半邊':>18}{'差':>8}")
    ok = np.isfinite(c)
    worst = 0.0
    for lo_ in [14.0, 15.0, 16.0, 17.0]:
        m = ok & (g >= lo_) & (g < lo_ + 1.0)
        if m.sum() < 40:
            continue
        med = np.median(c[m])
        red, blue = m & (c > med), m & (c <= med)
        fr, fb = kept[red].mean(), kept[blue].mean()
        worst = max(worst, abs(fr - fb))
        print(f"{lo_:6.1f}–{lo_+1:<5.1f}"
              f"{f'{fr:.3f} ({red.sum()} 顆)':>18}"
              f"{f'{fb:.3f} ({blue.sum()} 顆)':>18}{fr-fb:>+8.3f}")
    print(f"\n最大顏色相依差異 {worst:.3f}"
          f"（與整體星等相依 {kept[bright].mean()-kept[faint].mean():.3f} 相比）")

    c, f_, _ = completeness_curve()
    np.savez(HERE / "data" / "completeness.npz", g=c, frac=f_)
    print(f"\n寫入 data/completeness.npz（{len(c)} 個格點，格寬 0.5 星等）")


if __name__ == "__main__":
    main()
