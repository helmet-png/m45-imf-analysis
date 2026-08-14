# -*- coding: utf-8 -*-
"""C18（selection_color_dependence_fix）：BP/RP 流量超額那一刀的存活率
殘留顏色相依性，畫成隨顏色變化的函數，不是只有一個平均值。

**背景**：`scripts/data_prep/build_selection.py` 的 `excess_curve()`
docstring 明講這一刀「實測對顏色近乎中性（G>=17 的紅藍差只有 +0.014），
所以用一維近似」——只用 G 星等一維曲線描述存活率，顏色只在 G>=17
這一個粗切裡量過一次平均差異。這支腳本把同一批資料重新依「星等 x 顏色」
細分箱，看這個 +0.014 是不是掩蓋了更細的結構。

**做法**：重用 `scripts/diagnostics/selection_probe.load()`（已經把原始
星表、成員機率、篩選後名單接好），只看「沒被訊噪比切掉」的那批星
（避免重複算兩把刀，跟 `build_selection.py` 的 `excess_curve()` 用同一個
篩法），依星等分箱後，箱內再依顏色細分，直接看**存活率**（有沒有通過
BP/RP 超額那一刀）隨顏色怎麼變，不需要另外算超額因子期望值——存活率
本身就是我們真正關心的量。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts" / "diagnostics"))

from selection_probe import load  # noqa: E402


def main():
    d = load()
    g = d["g"]
    bp_rp = d["bp"] - d["rp"]
    kept = d["kept"]

    # 只看沒被訊噪比切掉的那批（跟 build_selection.py 的 excess_curve 一致）
    snr_cut = ((d["snr_bp"] < 20) | (d["snr_rp"] < 20) | (d["snr_g"] < 50)
              | ~np.isfinite(d["bp"]) | ~np.isfinite(d["rp"]))
    pool = ~snr_cut & np.isfinite(bp_rp) & np.isfinite(g)
    print(f"扣掉訊噪比切掉的星，剩下 {int(pool.sum())} 顆進 BP/RP 超額分析池")

    # 星等分箱（跟 build_selection.py 一致，1 星等一箱）
    g_edges = np.arange(np.floor(g[pool].min()), np.ceil(g[pool].max()) + 1, 1.0)

    print(f"\n{'G範圍':>10}{'顏色分箱':>18}{'星數':>7}{'存活率':>9}")
    rows = []
    for i in range(len(g_edges) - 1):
        glo, ghi = g_edges[i], g_edges[i + 1]
        gm = pool & (g >= glo) & (g < ghi)
        if gm.sum() < 30:
            continue
        # 箱內再依顏色切三份（藍/中/紅，各約等星數）
        c = bp_rp[gm]
        terciles = np.percentile(c, [0, 33.3, 66.7, 100])
        for j in range(3):
            clo, chi = terciles[j], terciles[j + 1]
            in_bin = (c >= clo) & (c <= chi if j == 2 else c < chi)
            n = int(in_bin.sum())
            if n < 5:
                continue
            surv = float(kept[gm][in_bin].mean())
            rows.append((glo, ghi, clo, chi, n, surv))
            print(f"{glo:>4.0f}-{ghi:<4.0f}{clo:>8.2f}-{chi:<8.2f}"
                  f"{n:>7}{surv:>9.3f}")

    def fit_and_report(mask, label):
        c_f = bp_rp[mask]
        k_f = kept[mask].astype(float)
        n = len(c_f)
        if n < 30:
            print(f"\n{label}：只有 {n} 顆，樣本太小跳過")
            return
        A = np.vstack([np.ones_like(c_f), c_f]).T
        coef, *_ = np.linalg.lstsq(A, k_f, rcond=None)
        a, b = coef
        rng = np.random.default_rng(20260814)
        boots = []
        for _ in range(500):
            idx = rng.integers(0, n, n)
            Ai = np.vstack([np.ones(n), c_f[idx]]).T
            ci, *_ = np.linalg.lstsq(Ai, k_f[idx], rcond=None)
            boots.append(ci[1])
        boots = np.array(boots)
        sig = abs(b) / boots.std() if boots.std() > 0 else np.nan
        print(f"\n{label}（n={n}）：survival = {a:.3f} + {b:+.4f} * bp_rp，"
              f"斜率標準誤 {boots.std():.4f}（{sig:.1f} 倍標準誤，"
              f"{'顯著' if sig > 2 else '不顯著'}）")

    # 跟原本「G>=17 紅藍落差 0.014」同一個切法比較基準
    fit_and_report(pool & (g >= 17), "G>=17 存活率對顏色的線性回歸")
    # 全樣本（星數多很多，檢定力較高，用來判斷「不顯著」是真的沒有
    # 效應，還是只是 G>=17 那個子樣本統計力不夠）
    fit_and_report(pool, "全樣本（G 全範圍）存活率對顏色的線性回歸")


if __name__ == "__main__":
    main()
