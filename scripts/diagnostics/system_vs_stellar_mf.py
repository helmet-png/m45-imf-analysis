# -*- coding: utf-8 -*-
"""量化 system MF 與 stellar MF 的冪次差（LIMITATIONS.md D14）。

**為什麼需要這支腳本**：我們擬合出來的 `alpha` 是**主星質量分布**的冪次
（見 `pipeline/joint_fit.JointModel.synthesise()` 的抽樣順序、
`PAPER_OUTLINE.md` 3.4 節），也就是以主星質量標記的 **system MF**。
但文獻不一定報同一個東西——Hobart et al. 2026 就明確把兩者分開，
內部用 system MF 擬合、報告時轉成 stellar MF。拿我們的數字直接跟一篇
報 stellar MF 的論文並排，兩者的差會被誤讀成物理差異。

這支腳本不改任何模型、不碰觀測資料，只回答一個純統計問題：
**同一個星團，用「只算主星」和「主星＋伴星都算」兩種方式量冪律斜率，
差多少？** 用的是專案實際在用的參數（見下面 DEFAULTS），抽樣公式與
`synthesise()` 裡的 q 分布反 CDF 逐字一致。

判讀：stellar MF 恆比 system MF **陡**（伴星質量 m2 = q·m1 恆小於主星，
把它們加進同一個量測窗等於在低質量端多塞星）。差隨 f_bin 單調變大。

用法：
    python scripts/diagnostics/system_vs_stellar_mf.py
    python scripts/diagnostics/system_vs_stellar_mf.py --alpha 2.4 --n 1000000
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy.optimize import brentq

# 專案實際在用的值：alpha 取 injection_recovery.THETA_TRUE[3]，
# q_gamma 取歷次擬合的大致中位，q_min 取 config.toml 的 binary_q_min，
# 量測窗取 alpha 這個參數實際管到的那一段（Kroupa 分段的 m > 0.5）。
DEFAULTS = dict(alpha=2.35, qgamma=-0.50, qmin=0.10, mlo=0.5, mhi=2.5)
FBINS = [0.30, 0.45, 0.60, 0.75]


def sample_powerlaw(rng, n, slope, lo, hi):
    """抽 p(m) ∝ m^-slope on [lo, hi]，用反 CDF。"""
    u = rng.random(n)
    a = 1.0 - slope
    return (lo ** a + u * (hi ** a - lo ** a)) ** (1.0 / a)


def sample_q(rng, n, gamma, qmin):
    """抽 p(q) ∝ q^gamma on [qmin, 1]。

    公式與 `JointModel.synthesise()` 裡那段逐字一致（含 gamma = -1 的
    對數特例），不要改成別的寫法——這裡的重點就是重現模型的抽樣。
    """
    u = rng.random(n)
    if abs(gamma + 1) < 1e-9:
        return qmin * (1.0 / qmin) ** u
    return (qmin ** (gamma + 1)
            + u * (1.0 - qmin ** (gamma + 1))) ** (1.0 / (gamma + 1))


def mle_slope(m, lo, hi):
    """截斷冪律 p(m) ∝ m^-s on [lo, hi] 的最大概似斜率。

    logL/N = -s·<ln m> - ln Z(s)，Z(s) = (hi^a - lo^a)/a，a = 1-s
    d(logL/N)/ds = -<ln m> + (hi^a·ln hi - lo^a·ln lo)/(hi^a - lo^a) - 1/a
    """
    m = m[(m >= lo) & (m <= hi)]
    lnm_bar = np.log(m).mean()

    def dll(s):
        a = 1.0 - s
        if abs(a) < 1e-8:
            a = 1e-8
        num = hi ** a * np.log(hi) - lo ** a * np.log(lo)
        den = hi ** a - lo ** a
        return -lnm_bar + num / den - 1.0 / a

    return brentq(dll, 0.01, 8.0, xtol=1e-8)


def main():
    ap = argparse.ArgumentParser()
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k}", type=float, default=v)
    ap.add_argument("--n", type=int, default=4_000_000,
                    help="蒙地卡羅樣本數（預設四百萬，差值收斂到 ~0.001）")
    ap.add_argument("--seed", type=int, default=20260819)
    a = ap.parse_args()

    rng = np.random.default_rng(a.seed)
    m1 = sample_powerlaw(rng, a.n, a.alpha, a.mlo, a.mhi)

    # 健全性檢查：只有主星時必須把注入的 alpha 原樣量回來。這一步不能省——
    # 若 MLE 或抽樣寫錯，下面的差值會是兩個錯誤數字相減，看起來仍然「合理」。
    s_sys = mle_slope(m1, a.mlo, a.mhi)
    print(f"參數：alpha={a.alpha}, q_gamma={a.qgamma}, q_min={a.qmin}, "
          f"量測窗 {a.mlo}-{a.mhi} Msun, N={a.n:,}")
    print(f"健全性檢查：只算主星時回收 {s_sys:.4f}"
          f"（注入 {a.alpha}，差 {s_sys - a.alpha:+.4f}）\n")

    print(f"{'f_bin':>7}{'system MF':>12}{'stellar MF':>12}{'差':>10}")
    for fbin in FBINS:
        is_bin = rng.random(a.n) < fbin
        m2 = m1[is_bin] * sample_q(rng, int(is_bin.sum()), a.qgamma, a.qmin)
        # 伴星只有落在同一個量測窗裡的才算——換成別的窗就是在比兩個不同的
        # 量，mle_slope() 內部已經做這個過濾。
        s_ste = mle_slope(np.concatenate([m1, m2]), a.mlo, a.mhi)
        print(f"{fbin:>7.2f}{s_sys:>12.4f}{s_ste:>12.4f}{s_ste - s_sys:>+10.4f}")

    print("\n判讀：stellar MF 恆較陡（伴星 m2 = q·m1 恆小於主星，等於在低質量端")
    print("      多塞星）。我們報的是 system MF；跟報 stellar MF 的文獻並排前")
    print("      要先做這個換算，見 LIMITATIONS.md D14。")


if __name__ == "__main__":
    main()
