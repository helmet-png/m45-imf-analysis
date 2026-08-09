# -*- coding: utf-8 -*-
"""第 4 步：雙星處理與多方法比較。

兩件事：

A. 族群層級 —— 把雙星比例升級成前向模型的自由參數，與年齡、消光一起求解。
   這是給第 5 步用的：IMF 反捲積需要的是「雙星比例與質量比分布」這組族群參數，
   不是「哪一顆是雙星」的清單。

B. 逐星層級 —— 用擬合好的族群模型回推每顆星的雙星機率，再跟 RUWE、CMD 偏移、
   Gaia NSS 三種傳統判定法比較。順序是「先族群、後逐星」（Liu et al. 2025 的作法），
   不是「先逐星標記、再加總成族群」—— 後者會因為每種方法各有偵測盲區而漏算
   偵測不到的雙星，且殘留偏差無法量化。

注意這四種方法偵測的**不是同一群雙星**：RUWE 對特定分離度/週期的天測擺動敏感、
CMD 偏移抓質量比高的組合、NSS 有自己的選擇函數、前向模型則是統計推論而非個別偵測。
比較的意義在於量化「方法選擇對結果的影響」，不是評判誰對誰錯。
"""
from __future__ import annotations

import numpy as np
from astropy.table import Table

from .step3_age import (COL_G, COL_BP, COL_RP, _Ext, draw_randoms, hess,
                        poisson_loglike, synth_populations)


def fit_with_binaries(cfg, obs_color, obs_mag, iso_grid, errmodel,
                      dist_mod: float, verbose: bool = True) -> dict:
    """在 (logAge, A_V, 雙星比例) 三維網格上搜尋最佳解。"""
    from . import isochrones as iso_mod

    c3, c2 = cfg.step3_age, cfg.step2_cmd
    c4 = cfg.step4_binaries
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    # 共用亂數：每個網格點都從同一顆種子重新開始，否則概似值的差異裡會混進
    # 蒙地卡羅雜訊，最佳解可能只是挑到雜訊的高點而非真的參數較好。
    seed = cfg.step1_membership.random_seed

    crange, mrange = tuple(c3.hess_color_range), tuple(c3.hess_mag_range)
    obs_h = hess(obs_color, obs_mag, c3.hess_color_bins, c3.hess_mag_bins,
                 crange, mrange)
    n_obs = len(obs_color)

    ages = np.arange(c4.fit_logage_min, c4.fit_logage_max + 1e-9,
                     c4.fit_logage_step)
    avs = np.arange(c4.fit_av_min, c4.fit_av_max + 1e-9, c4.fit_av_step)
    fbins = np.arange(c4.fit_fbin_min, c4.fit_fbin_max + 1e-9, c4.fit_fbin_step)
    mh = c3.metallicity_mh
    draws = draw_randoms(c3.n_synthetic, np.random.default_rng(seed))

    ll = np.full((len(ages), len(avs), len(fbins)), -np.inf)
    for i, la in enumerate(ages):
        one = iso_mod.isochrone_at(iso_grid, la, mh)
        if len(one) < 10:
            continue
        for j, av in enumerate(avs):
            for k, fb in enumerate(fbins):
                pop = synth_populations(
                    one, c3.n_synthetic, dist_mod, av, fb,
                    c3.binary_q_gamma, c3.binary_q_min, c3.imf,
                    errmodel, ext, draws,
                    g_faint=cfg.step1_membership.g_mag_max,
                    g_bright=c2.g_bright_limit)
                mod_h = hess(pop["color"], pop["mag"], c3.hess_color_bins,
                             c3.hess_mag_bins, crange, mrange,
                             smooth=c3.model_hess_smooth)
                ll[i, j, k] = poisson_loglike(obs_h, mod_h, n_obs)
        if verbose:
            b = np.unravel_index(np.argmax(ll[i]), ll[i].shape)
            print(f"  logAge={la:.2f}  A_V={avs[b[0]]:.2f}  "
                  f"f_bin={fbins[b[1]]:.2f}  lnL={ll[i][b]:.1f}", flush=True)

    k = np.unravel_index(np.argmax(ll), ll.shape)
    return {
        "logage": float(ages[k[0]]), "av": float(avs[k[1]]),
        "fbin": float(fbins[k[2]]), "age_myr": float(10 ** ages[k[0]] / 1e6),
        "loglike": float(ll[k]), "ages": ages, "avs": avs, "fbins": fbins,
        "loglike_grid": ll,
    }


def per_star_binary_prob(obs_color, obs_mag, pop: dict, cfg) -> np.ndarray:
    """用擬合好的族群模型算每顆觀測星的雙星機率。

    P(bin | 顏色, 星等) = f_b·L_bin / (f_b·L_bin + (1-f_b)·L_single)

    L_bin 與 L_single 用合成星團的單星／雙星在 CMD 上的二維密度估計。
    這是「先族群、後逐星」的第二步：族群參數已定，才回頭問個別的星。
    """
    c3 = cfg.step3_age
    crange, mrange = tuple(c3.hess_color_range), tuple(c3.hess_mag_range)
    nb_c, nb_m = c3.hess_color_bins, c3.hess_mag_bins

    b = pop["is_binary"]
    h_s, ce, me = np.histogram2d(
        pop["color"][~b], pop["mag"][~b], bins=[nb_c, nb_m],
        range=[crange, mrange])
    h_b, _, _ = np.histogram2d(
        pop["color"][b], pop["mag"][b], bins=[nb_c, nb_m],
        range=[crange, mrange])

    ic = np.clip(np.digitize(obs_color, ce) - 1, 0, nb_c - 1)
    im = np.clip(np.digitize(obs_mag, me) - 1, 0, nb_m - 1)
    ns, nbin = h_s[ic, im], h_b[ic, im]
    tot = ns + nbin
    return np.where(tot > 0, nbin / np.maximum(tot, 1e-9), np.nan)


def flag_ruwe(t: Table, threshold: float) -> np.ndarray:
    return np.asarray(t["ruwe"], float) > threshold


def flag_nss(t: Table) -> np.ndarray:
    """Gaia 的 non_single_star 位元遮罩，非零即為 Gaia 判定的非單星。"""
    if "non_single_star" not in t.colnames:
        return np.zeros(len(t), bool)
    v = np.asarray(t["non_single_star"], float)
    return np.nan_to_num(v, nan=0.0) > 0


def flag_cmd_offset(obs_color, obs_mag, iso: Table, dist_mod: float,
                    av: float, ext, threshold_mag: float) -> np.ndarray:
    """CMD 偏移法：比同顏色的單星序亮超過 threshold_mag 就判為雙星。

    等質量雙星比單星亮 0.753 星等，所以門檻通常取其一半左右，
    以涵蓋質量比中等的組合。
    """
    c_iso = (np.asarray(iso[COL_BP], float) - np.asarray(iso[COL_RP], float)
             + (ext.bp - ext.rp) * av)
    g_iso = np.asarray(iso[COL_G], float) + dist_mod + ext.g * av
    order = np.argsort(c_iso)
    c_iso, g_iso = c_iso[order], g_iso[order]
    # 同顏色下單星應有的星等
    g_expect = np.interp(obs_color, c_iso, g_iso,
                         left=np.nan, right=np.nan)
    # 星等越小越亮，所以「亮多少」= 期望值 - 觀測值
    excess = g_expect - obs_mag
    return np.nan_to_num(excess, nan=-99.0) > threshold_mag


def compare_methods(flags: dict) -> Table:
    """兩兩比較各方法標記出的雙星集合。"""
    names = list(flags)
    rows = []
    for a in names:
        row = {"方法": a, "標記數": int(flags[a].sum())}
        for b in names:
            if a == b:
                row[b] = "-"
            else:
                inter = int((flags[a] & flags[b]).sum())
                union = int((flags[a] | flags[b]).sum())
                row[b] = f"{inter}/{union} ({inter/max(union,1)*100:.0f}%)"
        rows.append(row)
    return Table(rows)
