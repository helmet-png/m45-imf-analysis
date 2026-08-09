# -*- coding: utf-8 -*-
"""第 2 步：用成員星建色光圖（CMD），並做測光品質篩選。

這一步的產出不只是一張圖，更重要的是**第 3 步前向模型需要的觀測特性**：
每個星等的測光誤差有多大、樣本的完整度到哪裡。沒有這些，合成星團就無法
生成得跟觀測同等品質，擬合會系統性偏差。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from astropy.table import Table

ROOT = Path(__file__).resolve().parent.parent

# Gaia 星等誤差與流量訊噪比的關係。星等 = -2.5*log10(flux)，微分後
# sigma_mag = (2.5/ln10) * sigma_flux/flux = 1.0857 / (flux/flux_error)
MAG_ERR_COEF = 2.5 / np.log(10)


def mag_error(flux_over_error) -> np.ndarray:
    foe = np.asarray(flux_over_error, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(foe > 0, MAG_ERR_COEF / foe, np.nan)


def bp_rp_excess_expected(bp_rp: np.ndarray) -> np.ndarray:
    """單星在給定顏色下應有的 BP/RP 流量超額因子。

    取自 Riello et al. 2021 (Gaia EDR3 photometry) 的經驗關係式。
    實測值明顯高於此曲線，代表 BP/RP 的孔徑測光被鄰星或星雲汙染 ——
    對 M45 這種泡在反射星雲裡的星團特別重要，因為顏色被汙染得最嚴重的
    正好是星雲裡的成員星。
    """
    c = np.asarray(bp_rp, float)
    return np.where(
        c < 0.5,
        1.154360 + 0.033772 * c + 0.032277 * c**2,
        np.where(c < 4.0,
                 1.162004 + 0.011464 * c + 0.049255 * c**2 - 0.005879 * c**3,
                 1.057572 + 0.140537 * c))


def bp_rp_excess_sigma(gmag: np.ndarray) -> np.ndarray:
    """該經驗關係式的散布（隨星等變化），Riello et al. 2021。"""
    g = np.asarray(gmag, float)
    return 0.0059898 + 8.817481e-12 * g**7.618399


def apply_quality_cuts(t: Table, cfg) -> tuple[Table, dict]:
    """套用測光品質篩選，回傳 (篩選後的表, 各條件砍掉幾顆的統計)。"""
    n0 = len(t)
    stats = {}
    keep = np.ones(n0, bool)

    g = np.asarray(t["phot_g_mean_mag"], float)
    bp_rp = np.asarray(t["bp_rp"], float)

    # 亮端飽和
    if cfg.g_bright_limit is not None:
        m = ~(g < cfg.g_bright_limit)
        stats["亮端飽和"] = int((~m & keep).sum())
        keep &= m

    # 測光訊噪比
    for col, lim, label in (
            ("phot_g_mean_flux_over_error", cfg.min_flux_snr_g, "G 訊噪比"),
            ("phot_bp_mean_flux_over_error", cfg.min_flux_snr_bp, "BP 訊噪比"),
            ("phot_rp_mean_flux_over_error", cfg.min_flux_snr_rp, "RP 訊噪比")):
        if col not in t.colnames or lim <= 0:
            continue
        v = np.asarray(t[col], float)
        m = np.isfinite(v) & (v >= lim)
        stats[label] = int((~m & keep).sum())
        keep &= m

    # BP/RP 流量超額（星雲與擁擠區汙染）
    if cfg.bp_rp_excess_sigma > 0 and "phot_bp_rp_excess_factor" in t.colnames:
        e = np.asarray(t["phot_bp_rp_excess_factor"], float)
        resid = e - bp_rp_excess_expected(bp_rp)
        m = np.isfinite(resid) & (
            np.abs(resid) < cfg.bp_rp_excess_sigma * bp_rp_excess_sigma(g))
        stats["BP/RP 超額"] = int((~m & keep).sum())
        keep &= m

    stats["_保留"] = int(keep.sum())
    stats["_原始"] = n0
    return t[keep], stats


def deredden(t: Table, av: float, cfg) -> tuple[np.ndarray, np.ndarray]:
    """套用消光修正，回傳 (絕對星等前的 G0, 顏色 (BP-RP)0)。"""
    g = np.asarray(t["phot_g_mean_mag"], float)
    bp_rp = np.asarray(t["bp_rp"], float)
    g0 = g - cfg.ext_coeff_g * av
    c0 = bp_rp - (cfg.ext_coeff_bp - cfg.ext_coeff_rp) * av
    return g0, c0


def photometric_error_model(t: Table, n_bins: int = 20) -> dict:
    """量出「星等 → 測光誤差」的關係，供前向模型生成合成星時使用。

    回傳分箱後的中位數誤差；合成星團的每顆星會依其星等內插出對應的誤差。
    """
    g = np.asarray(t["phot_g_mean_mag"], float)
    e_g = mag_error(t["phot_g_mean_flux_over_error"])
    e_bp = mag_error(t["phot_bp_mean_flux_over_error"])
    e_rp = mag_error(t["phot_rp_mean_flux_over_error"])

    ok = np.isfinite(g) & np.isfinite(e_g) & np.isfinite(e_bp) & np.isfinite(e_rp)
    edges = np.linspace(np.nanmin(g[ok]), np.nanmax(g[ok]), n_bins + 1)
    centres, sg, sbp, srp = [], [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = ok & (g >= lo) & (g < hi)
        if m.sum() < 3:
            continue
        centres.append(0.5 * (lo + hi))
        sg.append(float(np.median(e_g[m])))
        sbp.append(float(np.median(e_bp[m])))
        srp.append(float(np.median(e_rp[m])))
    return {"g": np.array(centres), "e_g": np.array(sg),
            "e_bp": np.array(sbp), "e_rp": np.array(srp)}


def run(cfg, members: Table) -> tuple[Table, dict]:
    """執行第 2 步。members 需含 phot_* 欄位。"""
    c2 = cfg.step2_cmd
    clean, stats = apply_quality_cuts(members, c2)

    print(f"測光品質篩選：{stats['_原始']:,} -> {stats['_保留']:,} 顆")
    for k, v in stats.items():
        if not k.startswith("_") and v:
            print(f"  {k:<12} 砍掉 {v:,}")

    errmodel = photometric_error_model(clean)
    print(f"測光誤差模型：{len(errmodel['g'])} 個星等分箱，"
          f"G 誤差 {errmodel['e_g'].min():.4f} – {errmodel['e_g'].max():.4f} mag")
    return clean, errmodel
