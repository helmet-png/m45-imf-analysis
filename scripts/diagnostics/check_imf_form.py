# -*- coding: utf-8 -*-
"""低質量段到底該用冪律還是對數常態？這個選擇會不會改變 alpha？

**問題來源**：Moraux et al. (2003) 對 Pleiades 本身的測量顯示，
0.03-10 Msun 的質量函數用**對數常態**（m_c ~ 0.25 Msun, sigma ~ 0.52）
描述得比分段冪律好。Chabrier (2003) 對銀盤場星也主張 1 Msun 以下用對數常態
（m_c = 0.079, sigma = 0.69）。

但我們的前向模型用的是 Kroupa 分段冪律，在 0.08-0.5 Msun 這段假設
「單一冪次 p」。**如果真實形狀是彎的，那「冪次是多少」這個問題本身就問錯了**
—— P6b 在測一個不存在的量，而且模型形狀對不上會把誤差推給 alpha。

**這支程式回答三件事**（純解析計算，不需要跑擬合）：
  1. 對數常態在 0.08-0.5 Msun 這段的「局部冪次」變化多大？
     變化小 = 冪律是好近似；變化大 = 形狀真的不同。
  2. 若硬用單一冪律去逼近對數常態，最佳的 p 是多少、殘差多大？
  3. 這個殘差跟我們的測光誤差、統計誤差相比，是可忽略還是會被資料看見？

第 3 點是關鍵判準：若殘差遠小於資料的雜訊，資料根本分辨不出兩種形式，
那用哪個都可以（但要在論文聲明）；若殘差大於雜訊，形式選擇就是一個
必須進誤差預算的系統項。
"""
from __future__ import annotations

import numpy as np

# 質量範圍：Kroupa 分段冪律裡「固定冪次」的那一段，也是 59.5% 樣本的所在
M_LO, M_HI = 0.08, 0.5

# 對數常態參數的兩組文獻值
FORMS = {
    "Moraux+2003 (Pleiades 本身)": dict(m_c=0.25, sigma=0.52),
    "Chabrier 2003 (銀盤場星)": dict(m_c=0.079, sigma=0.69),
}
KROUPA_P = 1.3          # 我們目前固定的值


def lognormal_dNdm(m, m_c, sigma):
    """對數常態的 dN/dm。

    慣例：Chabrier 定義在 dN/dlog(m) 上是高斯，
    轉成 dN/dm 要除以 m*ln(10)，所以多一個 1/m 因子。
    """
    x = np.log10(m)
    xc = np.log10(m_c)
    return np.exp(-((x - xc) ** 2) / (2 * sigma ** 2)) / m


def local_slope(m, m_c, sigma):
    """對數常態在質量 m 處的局部冪次（負的 dlnXi/dlnm）。

    解析解：alpha_eff(m) = 1 + (log m - log m_c) / (sigma^2 * ln10)
    在 m = m_c 處等於 1，往兩側線性變化。
    """
    return 1.0 + (np.log10(m) - np.log10(m_c)) / (sigma ** 2 * np.log(10))


def main():
    m = np.logspace(np.log10(M_LO), np.log10(M_HI), 200)

    print(f"質量範圍 {M_LO}-{M_HI} Msun"
          f"（跨度 {np.log10(M_HI/M_LO):.2f} dex，{M_HI/M_LO:.1f} 倍）")
    print(f"我們目前固定的冪次 p = {KROUPA_P}\n")

    for name, par in FORMS.items():
        print(f"{'='*68}\n{name}：m_c={par['m_c']}, sigma={par['sigma']}\n"
              f"{'='*68}")

        # 1. 局部冪次的變化
        a_lo = local_slope(M_LO, **par)
        a_hi = local_slope(M_HI, **par)
        print(f"  局部冪次：m={M_LO} 處 {a_lo:.2f}，"
              f"m={M_HI} 處 {a_hi:.2f}，跨度 {abs(a_hi-a_lo):.2f}")

        # 2. 用單一冪律逼近：在 log-log 空間做最小平方
        y = np.log(lognormal_dNdm(m, **par))
        X = np.vstack([np.log(m), np.ones_like(m)]).T
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        p_best = -coef[0]
        resid = y - X @ coef
        # 殘差換算成「星數的相對偏差」才有物理意義
        rel = np.exp(resid) - 1.0
        print(f"  最佳單一冪律 p = {p_best:.2f}"
              f"（對照我們固定的 {KROUPA_P}，差 {p_best-KROUPA_P:+.2f}）")
        print(f"  殘差（星數相對偏差）：最大 {np.abs(rel).max():.1%}，"
              f"均方根 {np.sqrt(np.mean(rel**2)):.1%}")

        # 3. 殘差有沒有大到資料看得見
        #    比較基準：每個質量分箱的 Poisson 相對雜訊。
        #    641 顆星分佈在這段，若分成 N 箱，每箱約 641/N 顆，
        #    Poisson 相對誤差 = 1/sqrt(每箱星數)。
        n_stars = 641
        for n_bins in (5, 10, 20):
            per = n_stars / n_bins
            poisson_rel = 1.0 / np.sqrt(per)
            verdict = ("殘差 > 雜訊，資料看得見"
                       if np.sqrt(np.mean(rel**2)) > poisson_rel
                       else "殘差 < 雜訊，資料分辨不出")
            print(f"    分成 {n_bins:>2} 箱（每箱 {per:.0f} 顆）："
                  f"Poisson 相對雜訊 {poisson_rel:.1%} -> {verdict}")
        print()

    # 用我們固定的 p=1.3 反推：它對應到對數常態的哪個質量？
    print(f"{'='*68}\n我們固定的 p=1.3 在對數常態上對應什麼位置\n{'='*68}")
    for name, par in FORMS.items():
        # 解 1 + (log m - log m_c)/(sigma^2 ln10) = 1.3
        log_m = np.log10(par["m_c"]) + 0.3 * par["sigma"] ** 2 * np.log(10)
        m_match = 10 ** log_m
        inside = M_LO <= m_match <= M_HI
        print(f"  {name}：p=1.3 對應 m = {m_match:.3f} Msun"
              f"（{'在範圍內' if inside else '**在範圍外**'}）")
    print("\n判讀：若 p=1.3 對應的質量落在範圍外，代表我們固定的冪次")
    print("      在整個 0.08-0.5 區間都比對數常態陡（或平），是系統性偏移")
    print("      而不是「取了個中間值」。")


if __name__ == "__main__":
    main()
