# -*- coding: utf-8 -*-
"""第 5 步：質量函數與 IMF 斜率。

用兩種作法算，重點在**兩者的差距**：

方法 A（樸素）：把每顆觀測星當單星，用 isochrone 的質量-光度關係指派質量，
    再對質量做冪律擬合。這是傳統作法，也是文獻裡最常見的。
方法 B（前向模型）：把 IMF 斜率當成合成星團的自由參數，讓合成 CMD 去符合觀測。
    雙星在模型裡本來就存在，不需要事先挑掉。

兩者的差距就是「忽略未解析雙星對 IMF 斜率造成的偏差」的直接測量。
arXiv:2603.15779 指出這個偏差不隨樣本數縮小（統計誤差 ~1/sqrt(N) 遞減，
偏差是常數），樣本夠大時會「精確地錯」。

冪律擬合一律用未分箱資料的最大概似估計，不用分箱後的最小平方 ——
分箱方式會左右斜率，而且計數是 Poisson 不是 Gaussian。
"""
from __future__ import annotations

import numpy as np
from astropy.table import Table
from scipy.optimize import minimize_scalar

from .step3_age import (COL_G, COL_BP, COL_RP, _Ext, draw_randoms, hess,
                        poisson_loglike, synth_populations)


def main_sequence_mass_luminosity(iso: Table, dist_mod: float, av: float,
                                  ext) -> tuple[np.ndarray, np.ndarray]:
    """從 isochrone 取出單調的主序段，回傳 (視星等 G, 初始質量)。

    必須單調才能反過來由星等查質量。轉折點以上的演化階段 G 與質量不再單調
    （巨星比主序星亮但質量未必大），所以只取單調遞減的那一段。
    """
    m = np.asarray(iso["Mini"], float)
    g = np.asarray(iso[COL_G], float) + dist_mod + ext.g * av
    order = np.argsort(m)
    m, g = m[order], g[order]
    # 由低質量往高質量走，保留 G 持續變亮（數值變小）的部分
    keep = np.ones(len(m), bool)
    gmin = np.inf
    for i in range(len(m)):
        if g[i] < gmin:
            gmin = g[i]
        else:
            keep[i] = False
    m, g = m[keep], g[keep]
    # 讓 G 遞增以便 np.interp 使用
    idx = np.argsort(g)
    return g[idx], m[idx]


def assign_masses(obs_mag, iso: Table, dist_mod: float, av: float,
                  ext) -> np.ndarray:
    """方法 A：把每顆星當單星，由 G 星等查出質量。"""
    g_ms, m_ms = main_sequence_mass_luminosity(iso, dist_mod, av, ext)
    return np.interp(obs_mag, g_ms, m_ms, left=np.nan, right=np.nan)


def mle_powerlaw(masses: np.ndarray, m_lo: float, m_hi: float) -> dict:
    """對 dN/dm ∝ m^(-alpha) 做最大概似估計（未分箱、含上下截斷）。

    截斷冪律的正規化常數：C = (1-alpha) / (m_hi^(1-alpha) - m_lo^(1-alpha))
    對數概似：lnL = n·ln(C) - alpha·sum(ln m)
    """
    m = np.asarray(masses, float)
    m = m[np.isfinite(m) & (m >= m_lo) & (m <= m_hi)]
    n = len(m)
    if n < 10:
        return {"alpha": np.nan, "alpha_err": np.nan, "n": n}
    slog = np.sum(np.log(m))

    def neg_ll(alpha):
        if abs(alpha - 1.0) < 1e-8:
            alpha = 1.0 + 1e-8
        denom = m_hi ** (1 - alpha) - m_lo ** (1 - alpha)
        if denom == 0 or (1 - alpha) / denom <= 0:
            return 1e18
        c = (1 - alpha) / denom
        return -(n * np.log(c) - alpha * slog)

    r = minimize_scalar(neg_ll, bounds=(0.1, 5.0), method="bounded")
    alpha = float(r.x)
    # 用概似曲率估標準誤（二階數值微分）
    h = 1e-3
    d2 = (neg_ll(alpha + h) - 2 * neg_ll(alpha) + neg_ll(alpha - h)) / h ** 2
    err = float(1.0 / np.sqrt(d2)) if d2 > 0 else np.nan
    return {"alpha": alpha, "alpha_err": err, "n": n,
            "m_lo": m_lo, "m_hi": m_hi}


def fit_imf_forward(cfg, obs_color, obs_mag, iso: Table, errmodel,
                    dist_mod: float, av: float, fbin: float,
                    verbose: bool = True) -> dict:
    """方法 B：把 IMF 斜率當自由參數，用前向模型擬合。

    只改高質量端那一段的冪次（Kroupa 分段冪律的 m > 0.5 M☉ 段），
    因為觀測的星等下限決定了低質量端根本沒有涵蓋到足以約束的資料。
    """
    from .step3_age import IMF_BREAKS
    c3, c2 = cfg.step3_age, cfg.step2_cmd
    c5 = cfg.step5_imf
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    # 共用亂數，理由同 step3/step4：讓概似差異只反映 alpha 的差異
    seed = cfg.step1_membership.random_seed

    crange, mrange = tuple(c3.hess_color_range), tuple(c3.hess_mag_range)
    obs_h = hess(obs_color, obs_mag, c3.hess_color_bins, c3.hess_mag_bins,
                 crange, mrange)
    n_obs = len(obs_color)

    alphas = np.arange(c5.fit_alpha_min, c5.fit_alpha_max + 1e-9,
                       c5.fit_alpha_step)
    ll = np.full(len(alphas), -np.inf)
    draws = draw_randoms(c3.n_synthetic, np.random.default_rng(seed))
    orig = IMF_BREAKS["kroupa"]
    try:
        for i, a in enumerate(alphas):
            # 暫時把高質量段的冪次換成 -a
            IMF_BREAKS["kroupa"] = (orig[0], [orig[1][0], orig[1][1], -a])
            pop = synth_populations(
                iso, c3.n_synthetic, dist_mod, av, fbin,
                c3.binary_q_gamma, c3.binary_q_min, "kroupa",
                errmodel, ext, draws,
                g_faint=cfg.step1_membership.g_mag_max,
                g_bright=c2.g_bright_limit)
            mod_h = hess(pop["color"], pop["mag"], c3.hess_color_bins,
                         c3.hess_mag_bins, crange, mrange,
                         smooth=c3.model_hess_smooth)
            ll[i] = poisson_loglike(obs_h, mod_h, n_obs)
            if verbose:
                print(f"  alpha={a:.2f}  lnL={ll[i]:.1f}", flush=True)
    finally:
        IMF_BREAKS["kroupa"] = orig

    k = int(np.argmax(ll))
    return {"alpha": float(alphas[k]), "loglike": float(ll[k]),
            "alphas": alphas, "loglike_grid": ll}


def mass_function_by_radius(masses, radii_deg, edges, m_lo, m_hi) -> Table:
    """量質量函數隨半徑的變化 —— 質量分層的直接測量。

    M45 已動力學演化，低質量星會優先被甩到外圍。若在有限半徑內量 IMF，
    量到的 alpha 會偏平（偏向重星）。把它當成要測量的物理量而不是要消除的誤差。
    """
    rows = []
    r = np.asarray(radii_deg, float)
    m = np.asarray(masses, float)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (r >= lo) & (r < hi) & np.isfinite(m)
        fit = mle_powerlaw(m[sel], m_lo, m_hi)
        rows.append({
            "r_lo": lo, "r_hi": hi, "n": fit["n"],
            "alpha": fit["alpha"], "alpha_err": fit["alpha_err"],
            "median_mass": float(np.nanmedian(m[sel])) if sel.sum() else np.nan,
        })
    return Table(rows)
