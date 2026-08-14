# -*- coding: utf-8 -*-
"""C3（rv_binary_investigate）：`f_bin=0.45` + Kroupa/Sana 週期分布估計，
看 56/499（11.2%）RV 顯著離群這個比例，分光雙星本身能不能解釋掉。

**背景**：`data/radial_velocity.csv`（C3）發現 499 顆有 Gaia 官方 RV 的
成員裡，56 顆（11.2%）偏離 bulk_rv=5.343 km/s 超過各自誤差棒的 5σ。
`WORK_BOARD.md` 的 `rv_binary_investigate` 要求先查文獻有沒有現成的
M45 分光雙星編目能直接核對，查不到的話用 f_bin=0.45 加上 Kroupa/Sana
週期分布做期望比例估計。**這台機器連不上 SIMBAD／Vizier 等外部服務
（SSL 憑證驗證失敗，見 D9／A6 的記錄），沒辦法查文獻編目，直接做第二種
估計。**

**方法**：蒙地卡羅模擬 `f_bin=0.45` 比例的雙星系統，在隨機軌道相位／
傾角下抽出徑向速度偏移量，量有多少比例的偏移量會超過**用真實 499 顆星
的誤差棒重抽樣**得到的 5σ 門檻，這個比例乘上 f_bin 就是「雙星本身能
解釋的離群比例上限」，拿去跟觀測到的 11.2% 比較。

**週期與質量比分布**（Sana et al. 2012, Science 337, 444，本來是校準給
大質量/O 型雙星，M45 主要是 F–K 型矮星，物理上不完全對應，這裡當作
量級估計用，不是精確模型，結果要標明這個限制）：
  - logP（天）：`f(logP) ∝ (logP)^-0.55`，範圍 [0.15, 3.5]
  - 質量比 q：`f(q) ∝ q^-0.1`，範圍 [0.1, 1]
  - 簡化成圓軌道（e=0）——真實偏心軌道會讓部分系統的 RV 變化更集中在
    近星點附近，這裡的簡化偏向低估極端偏移的機率，是保守方向

**主星質量**：從這個專案本來就在用的擬合質量範圍（0.30–2.50 M☉）用
Kroupa (2001) 高質量段冪次 -2.3 抽樣，跟前向模型的 IMF 假設一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

G_SUN_AU3_MSUN_DAY2 = 2.959122e-4  # G in AU^3 / (Msun * day^2)
BULK_RV = 5.343
N_TRIALS = 200_000
SEED = 20260814


def sample_kroupa_mass(rng, n, m_lo=0.30, m_hi=2.50, alpha=2.3):
    """逆變換抽樣，Kroupa 高質量段冪次 alpha=2.3（跟前向模型假設一致）。"""
    u = rng.random(n)
    p = 1 - alpha
    return (u * (m_hi ** p - m_lo ** p) + m_lo ** p) ** (1 / p)


def sample_power_law(rng, n, lo, hi, exponent):
    """逆變換抽樣一般冪律，exponent 是 f(x) 的冪次（可正可負，!=-1）。"""
    u = rng.random(n)
    p = exponent + 1
    if abs(p) < 1e-8:
        return np.exp(u * (np.log(hi) - np.log(lo)) + np.log(lo))
    return (u * (hi ** p - lo ** p) + lo ** p) ** (1 / p)


def rv_semi_amplitude_kms(m1, m2, period_day, cos_i):
    """圓軌道 RV 半振幅（km/s）。m1/m2 用太陽質量，period 用天。"""
    period_yr = period_day / 365.25
    a_au = (m1 + m2) ** (1 / 3) * period_yr ** (2 / 3)  # Kepler 第三定律
    sin_i = np.sqrt(1 - cos_i ** 2)
    # K1 = 2*pi*a2*sin(i) / P，a2 = a * m1/(m1+m2)
    a2_au = a_au * m1 / (m1 + m2)
    period_s = period_day * 86400.0
    au_km = 1.495978707e8
    k1_kms = 2 * np.pi * a2_au * au_km * sin_i / period_s
    return k1_kms


def main():
    rv = Table.read(HERE / "data" / "radial_velocity.csv", format="csv")
    err_all = np.asarray(rv["radial_velocity_error"], float)
    err_ok = err_all[np.isfinite(err_all) & (err_all > 0)]
    print(f"真實 RV 誤差棒樣本：{len(err_ok)} 顆，中位 {np.median(err_ok):.2f} "
          f"km/s，範圍 [{err_ok.min():.2f}, {err_ok.max():.2f}]")

    rng = np.random.default_rng(SEED)
    f_bin = 0.45

    q = sample_power_law(rng, N_TRIALS, 0.1, 1.0, exponent=-0.1)
    cos_i = rng.uniform(-1, 1, N_TRIALS)
    phase = rng.uniform(0, 2 * np.pi, N_TRIALS)
    sigma = rng.choice(err_ok, size=N_TRIALS, replace=True)

    scenarios = [
        ("Sana+2012（O 型雙星校準，短週期為主，如上方 docstring 說明）",
         lambda: 10 ** sample_power_law(rng, N_TRIALS, 0.15, 3.5,
                                        exponent=-0.55)),
        ("Raghavan+2010（太陽型場星雙星，logP 常態分布，"
         "中位周期~300年，M45 F-K 矮星母體更接近的參考）",
         lambda: 10 ** rng.normal(5.03, 2.28, N_TRIALS)),
    ]

    print(f"\n觀測到的離群比例（C3）：11.2%（56/499）\n")
    for label, sample_period in scenarios:
        m1 = sample_kroupa_mass(rng, N_TRIALS)
        m2 = m1 * q
        period_day = sample_period()
        k1 = rv_semi_amplitude_kms(m1, m2, period_day, cos_i)
        rv_offset = k1 * np.cos(phase)
        sigma_dev = np.abs(rv_offset) / sigma

        frac_given_binary = float((sigma_dev > 5).mean())
        frac_overall = frac_given_binary * f_bin

        print(f"=== {label} ===")
        print(f"  週期中位 {np.median(period_day):.1f} 天，K1 中位 "
              f"{np.median(k1):.2f} km/s（90% {np.percentile(k1,90):.2f}）")
        print(f"  給定是雙星，隨機相位/傾角下 RV 偏移 >5sigma 的比例："
              f"{frac_given_binary*100:.1f}%")
        print(f"  乘上 f_bin={f_bin}，雙星本身能解釋的離群比例上限："
              f"{frac_overall*100:.1f}%")
        if frac_overall >= 0.112:
            print(f"  => >= 觀測的 11.2%，這個週期分布下分光雙星足以"
                  f"解釋掉整個離群比例\n")
        else:
            print(f"  => < 觀測的 11.2%，缺口 {0.112-frac_overall:.3f}"
                  f"（約 {(0.112-frac_overall)*499:.0f} 顆量級）\n")

    print("誠實結論：兩個週期分布給出的答案方向不一致——用 Sana+2012（短"
          "週期為主，物理上是校準給大質量/O 型雙星，M45 主要是 F-K 矮星，"
          "不完全對應）算出來雙星綽綽有餘解釋 11.2%；改用更貼近 M45 母體"
          "的 Raghavan+2010 太陽型場星週期分布（中位周期~300 年，RV 半"
          "振幅小很多），雙星能解釋的比例大幅縮水。**這代表 11.2% 這個"
          "數字能不能完全歸給分光雙星，高度依賴週期分布的假設，不是一個"
          "穩定的結論**——不能只挑一個分布就下定論，誠實記錄兩種答案，"
          "不是只呈現對「污染源不存在」有利的那個。")


if __name__ == "__main__":
    main()
