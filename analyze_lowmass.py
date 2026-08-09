# -*- coding: utf-8 -*-
"""P6b 第一步：把「低質量段冪次不確定」換算成 alpha 的系統誤差。

**這支程式不做新的擬合**，只分析 P6（profile_lowmass.py）已經跑出來的結果，
回答一個具體問題：既然 Kroupa 給的低質量段冪次是 1.3 +- 0.5（不是精確值），
那這個不確定度會在我們測的 alpha 上造成多大的系統誤差？

作法：對 P6 的 (p, alpha) 資料做加權線性迴歸求 d(alpha)/d(p)，
再乘上文獻給的 p 不確定度，就是傳播到 alpha 的系統誤差。

**為什麼要先做這個、而不是直接把 p 升格成自由參數**：
升格是有代價的（多一個自由度會稀釋本來就緊繃的識別力，而且可能與 alpha
產生新的簡併，需要重跑一整輪注入回收才能確認）。先算出「不升格的代價
是多少」，才知道值不值得付那個代價。這跟先前處理差異消光 dav 的決策
邏輯一致。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# 文獻值。**注意符號慣例**：本專案與 Kroupa 2001 都用
#   dN/dm 正比於 m^(-alpha)
# 有些論文改用 Gamma 或 x，定義是 dN/dlog(m) 正比於 m^(-Gamma)，
# 兩者差 1（alpha = Gamma + 1）。查文獻時若看到「Pleiades 低質量段
# 斜率 0.5」這種數字，必須先確認是哪個慣例 —— 在 alpha 慣例下 0.5
# 與 Kroupa 的 1.3 差很多，在 Gamma 慣例下 0.5 就等於 alpha=1.5，
# 反而與 1.3 相容。這個混淆會直接改變結論，不能靠猜。
KROUPA_ALPHA1 = 1.3
KROUPA_ALPHA1_ERR = 0.5      # Kroupa (2001) MNRAS 322, 231


def main():
    d = np.load(HERE / "results" / "profile_lowmass.npz")
    ps = np.array(d["slopes"], float)
    means, sems, n_rep = [], [], None
    print(f"{'冪次 p':>8}{'各次 alpha':>26}{'平均':>8}{'散布':>8}{'標準誤':>8}")
    for p in ps:
        a = d[f"p{p}"][:, 3]
        n_rep = len(a)
        sem = a.std(ddof=1) / np.sqrt(len(a))
        means.append(a.mean())
        sems.append(sem)
        vals = "  ".join(f"{v:.2f}" for v in a)
        print(f"{p:>8.1f}{vals:>26}{a.mean():>8.3f}{a.std(ddof=1):>8.3f}"
              f"{sem:>8.3f}")
    means, sems = np.array(means), np.array(sems)

    # 加權最小平方（權重 1/sem^2）。用加權而非普通迴歸，是因為各點的
    # 重複次數雖同、散布卻不同，等權處理會讓雜訊大的點過度影響斜率。
    w = 1.0 / np.maximum(sems, 1e-6) ** 2
    A = np.vstack([ps, np.ones_like(ps)]).T
    W = np.diag(w)
    cov = np.linalg.inv(A.T @ W @ A)
    coef = cov @ (A.T @ W @ means)
    slope, intercept = coef
    slope_err = np.sqrt(cov[0, 0])

    print(f"\n加權線性迴歸：alpha = {slope:+.3f} * p + {intercept:.3f}")
    print(f"  斜率 d(alpha)/d(p) = {slope:+.3f} +- {slope_err:.3f}")
    print(f"  斜率顯著性 = {abs(slope)/slope_err:.1f} sigma")

    # 傳播文獻的 p 不確定度
    induced = abs(slope) * KROUPA_ALPHA1_ERR
    print(f"\n{'='*66}")
    print("把 Kroupa (2001) 的 alpha1 = 1.3 +- 0.5 傳播到我們測的 alpha")
    print(f"{'='*66}")
    print(f"  d(alpha)/d(p) = {slope:+.3f}")
    print(f"  文獻的 p 不確定度 = +-{KROUPA_ALPHA1_ERR}")
    print(f"  -> 傳播到 alpha 的系統誤差 = {induced:.3f}")

    # 跟已知的其他誤差項比較
    stat = 0.144      # 注入回收（S3F）
    print(f"\n對照其他誤差來源：")
    print(f"  統計誤差（注入回收，1,078 顆）  {stat:.3f}")
    print(f"  低質量段冪次（本項）            {induced:.3f}"
          f"   = 統計誤差的 {induced/stat:.1f} 倍")
    print(f"  等時線模型（修正後）            0.000")
    print(f"  濾光片定義                      0.040")
    print(f"  雙星處理                        0.020")

    print(f"\n判讀：")
    if induced > stat:
        print(f"  低質量段冪次是**目前最大的單一誤差來源**"
              f"（{induced/stat:.1f} 倍於統計誤差）。")
        print("  只用文獻先驗鎖住它並不能消除這個誤差 —— 先驗的寬度")
        print("  本身就是誤差的來源。要真正縮小它，必須讓資料自己去約束，")
        print("  也就是升格為自由參數（前提是注入回收證實它可辨識）。")
    else:
        print("  這一項小於統計誤差，用文獻先驗鎖住即可，不必升格。")

    np.savez(HERE / "results" / "lowmass_systematic.npz",
             p=ps, alpha_mean=means, alpha_sem=sems,
             slope=slope, slope_err=slope_err, induced=induced)
    print(f"\n寫入 results/lowmass_systematic.npz")


if __name__ == "__main__":
    main()
