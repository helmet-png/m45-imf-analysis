# -*- coding: utf-8 -*-
"""修正 pyUPMASK 隱含的「成員與場星各佔一半」先驗。

pyUPMASK 的機率來自 P = 1 / (1 + L_field/L_memb)，這條式子等價於在貝氏公式裡
假設 P(成員) = P(場星) = 1/2。但我們的樣本 6,956 顆裡只有約 1,300 顆是成員，
真實先驗約 0.19 而非 0.5，所以算出來的機率系統性偏高。

好消息是**不需要改 pyUPMASK，也不需要重跑**：從 P 就能反推出概似比，
再套用任意先驗重算。

    P = 1/(1 + R)，其中 R = L_field/L_memb   ->   R = 1/P - 1

改用先驗 pi = P(成員) 後：

    P_new = pi·L_memb / (pi·L_memb + (1-pi)·L_field)
          = 1 / (1 + ((1-pi)/pi)·R)

先驗本身可以由資料自洽地決定：先猜一個 pi，算出新的機率，再把新機率的平均
當成新的 pi，反覆到收斂。這其實就是 EM 演算法用在混合比例上的作法。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent


def likelihood_ratio(p: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    """由 pyUPMASK 的機率反推概似比 R = L_field / L_memb。"""
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    return 1.0 / p - 1.0


def reweight(p: np.ndarray, prior: float) -> np.ndarray:
    """把 50/50 先驗下的機率換算成任意先驗下的機率。"""
    r = likelihood_ratio(p)
    return 1.0 / (1.0 + ((1.0 - prior) / prior) * r)


def self_consistent_prior(p: np.ndarray, tol: float = 1e-6,
                          max_iter: int = 200) -> tuple[float, np.ndarray]:
    """讓先驗與後驗自洽：pi 反覆更新為新機率的平均值，直到收斂。"""
    r = likelihood_ratio(p)
    pi = 0.5
    for i in range(max_iter):
        p_new = 1.0 / (1.0 + ((1.0 - pi) / pi) * r)
        pi_new = float(np.mean(p_new))
        if abs(pi_new - pi) < tol:
            return pi_new, p_new
        pi = pi_new
    return pi, 1.0 / (1.0 + ((1.0 - pi) / pi) * r)


def main():
    ap = argparse.ArgumentParser(description="修正 pyUPMASK 的等機率先驗")
    ap.add_argument("--result", default="results/baseline.dat")
    ap.add_argument("--prior", type=float, default=None,
                    help="指定先驗；不給則由資料自洽決定")
    a = ap.parse_args()

    t = Table.read(HERE / a.result, format="ascii")
    p = np.asarray(t["probs_final"], float)
    ok = p >= 0        # -1 是離群遮罩，不是機率
    print(f"讀入 {len(p):,} 顆，其中 {int(ok.sum()):,} 顆有有效機率")

    if a.prior is None:
        pi, p_new = self_consistent_prior(p[ok])
        print(f"自洽先驗收斂到 pi = {pi:.4f}")
    else:
        pi = a.prior
        p_new = reweight(p[ok], pi)
        print(f"使用指定先驗 pi = {pi:.4f}")

    print(f"\n{'門檻':>6}{'原本(50/50)':>14}{'修正後':>10}{'減少':>10}")
    for thr in (0.5, 0.7, 0.9, 0.99):
        n_old = int((p[ok] >= thr).sum())
        n_new = int((p_new >= thr).sum())
        print(f"{thr:>6.2f}{n_old:>14,}{n_new:>10,}{n_old - n_new:>10,}")

    print(f"\n機率中位數：{np.median(p[ok]):.4f} -> {np.median(p_new):.4f}")
    hi = p[ok] >= 0.99
    if hi.any():
        print(f"原本 P>=0.99 那批，修正後的機率範圍："
              f"{p_new[hi].min():.4f} – {p_new[hi].max():.4f}"
              f"（中位 {np.median(p_new[hi]):.4f}）")

    out = Table({"source_id": t["source_id"][ok],
                 "prob_equal_prior": p[ok], "prob_corrected": p_new})
    dest = HERE / "results" / "prior_corrected.csv"
    out.write(dest, format="csv", overwrite=True)
    print(f"\n寫入 {dest}")


if __name__ == "__main__":
    main()
