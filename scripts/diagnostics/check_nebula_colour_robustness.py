# -*- coding: utf-8 -*-
"""D19 Stage 0：C21 星雲汙染定量檢查——G-RP 真的比 BP-RP 更不受星雲汙染影響嗎？

**背景（C21）**：M45 泡在反射星雲裡，HR23 給的差異消光 0.634 遠大於平均
消光 0.102，且「BP/RP 孔徑測光被汙染最嚴重的正好是星雲裡的成員星」
（`pipeline/step2_cmd.py` 的 `bp_rp_excess_expected()` docstring 已經有
這個判斷，但從沒被量化成具體數字）。D19 Stage 0 選 G-RP 當暗端顏色，
理由之一是它對模型選擇更穩健（`compare_lowmass_isochrones.py`），但
「對星雲汙染更穩健」是另一個獨立的理由，一直沒有直接測過。

**怎麼量測汙染程度**：Gaia 的 `phot_bp_rp_excess_factor` 是 BP+RP 相對
G 的流量超額——單星在給定顏色下有一條經驗基準曲線（Riello et al. 2021，
`pipeline/step2_cmd.py` 的 `bp_rp_excess_expected()`），**實測值明顯高於
這條曲線就代表孔徑測光被鄰星或背景（這裡是星雲）汙染**。用
`(實測 excess − 基準期望值) / 基準散布` 當汙染程度的訊噪比：這個值越大，
代表這顆星的孔徑測光被汙染得越嚴重（不管是不是星雲造成，任何額外的
背景光都會推高 excess factor，星雲是 M45 已知的主要嫌疑對象——C21
提出的假設，不是本腳本能獨立證實的機制）。

**測什麼**：把成員依汙染訊噪比分成「低汙染」「高汙染」兩組（中位數切），
對兩組各自算兩種顏色（BP-RP、G-RP）相對等時線主序的殘差散布。如果
G-RP 的散布從低汙染組到高汙染組幾乎不變、而 BP-RP 的散布明顯變大，
就支持「G-RP 對汙染更穩健」這個假設——量化 C21 的定性判斷，也是 D19
Stage 0 選色的第三個獨立理由（前兩個是深度與模型穩健度）。

用法：
    python scripts/diagnostics/check_nebula_colour_robustness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod              # noqa: E402
from pipeline import isochrones as isomod           # noqa: E402
from pipeline import step5_imf                      # noqa: E402
from pipeline.step2_cmd import (                    # noqa: E402
    bp_rp_excess_expected, bp_rp_excess_sigma)
from pipeline.step3_age import _Ext                 # noqa: E402

# 出處同 assess_colour_options.py／estimate_lowmass_precision.py：
# 現行 headline 前向模型設定（config C），只當換算用的標尺。
CONFIG_C_LOGAGE = 8.033
CONFIG_C_AV = 0.383


def main():
    cfg = cfgmod.load(None)
    c3 = cfg.step3_age
    mem = pd.read_csv(HERE / "data" / "cmd_members.csv")

    plx = mem["parallax"].to_numpy(float)
    dist_mod = 5.0 * np.log10(
        1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0

    grid = isomod.load_grid(isomod.CACHE / (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))
    iso = isomod.isochrone_at(grid, CONFIG_C_LOGAGE, c3.metallicity_mh)
    ext = _Ext(cfg.step2_cmd.ext_coeff_g, cfg.step2_cmd.ext_coeff_bp,
               cfg.step2_cmd.ext_coeff_rp)

    g = mem["phot_g_mean_mag"].to_numpy(float)
    bp_rp = mem["bp_rp"].to_numpy(float)
    excess = mem["phot_bp_rp_excess_factor"].to_numpy(float)

    excess_expected = bp_rp_excess_expected(bp_rp)
    excess_sigma = bp_rp_excess_sigma(g)
    contam_snr = (excess - excess_expected) / excess_sigma

    g_ms, c_bprp_ms = step5_imf.main_sequence_color(iso, dist_mod,
                                                     CONFIG_C_AV, ext)
    pred_bprp = np.interp(g, g_ms, c_bprp_ms, left=np.nan, right=np.nan)
    resid_bprp = bp_rp - pred_bprp

    rp = mem["phot_rp_mean_mag"].to_numpy(float)
    g_rp_obs = g - rp
    m_all = np.asarray(iso["Mini"], float)
    order = np.argsort(m_all)
    m_s = m_all[order]
    g_iso = (np.asarray(iso["G_fSBmag"], float)[order] + dist_mod
             + ext.g * CONFIG_C_AV)
    rp_iso = (np.asarray(iso["G_RP_fSBmag"], float)[order] + dist_mod
              + ext.rp * CONFIG_C_AV)
    keep = np.ones(len(m_s), bool)
    gmin = np.inf
    for i in range(len(m_s)):
        if g_iso[i] < gmin:
            gmin = g_iso[i]
        else:
            keep[i] = False
    g_grp_ms = g_iso[keep]
    c_grp_ms = (g_iso - rp_iso)[keep]
    o2 = np.argsort(g_grp_ms)
    pred_grp = np.interp(g, g_grp_ms[o2], c_grp_ms[o2],
                         left=np.nan, right=np.nan)
    resid_grp = g_rp_obs - pred_grp

    ok = np.isfinite(contam_snr) & np.isfinite(resid_bprp) & np.isfinite(resid_grp)
    n_dropped = int((~ok).sum())
    contam_snr, resid_bprp, resid_grp = (
        contam_snr[ok], resid_bprp[ok], resid_grp[ok])
    print(f"樣本數 {ok.sum()}（丟棄 {n_dropped} 顆等時線範圍外或缺值的星）")

    med = np.median(contam_snr)
    low = contam_snr <= med
    high = ~low
    print(f"\n汙染訊噪比 (excess-expected)/sigma：中位數 {med:.2f}，"
          f"範圍 [{contam_snr.min():.2f}, {contam_snr.max():.2f}]")
    print(f"低汙染組 N={low.sum()}，高汙染組 N={high.sum()}")

    def mad_std(x):
        return 1.4826 * np.median(np.abs(x - np.median(x)))

    print(f"\n{'顏色':>10}{'低汙染組散布':>14}{'高汙染組散布':>14}{'比值':>8}")
    for name, resid in [("BP-RP", resid_bprp), ("G-RP", resid_grp)]:
        s_low = mad_std(resid[low])
        s_high = mad_std(resid[high])
        print(f"{name:>10}{s_low:>14.4f}{s_high:>14.4f}{s_high / s_low:>8.2f}")

    r_bprp = mad_std(resid_bprp[high]) / mad_std(resid_bprp[low])
    r_grp = mad_std(resid_grp[high]) / mad_std(resid_grp[low])
    print(f"\n判讀：高／低汙染散布比值，BP-RP={r_bprp:.2f}、G-RP={r_grp:.2f}")

    # 兩個比值單獨看都有抽樣雜訊，比較兩者高低前先用 bootstrap 給信賴區間——
    # 只有一個點估計看不出 1.11 對 0.92 這個差距是不是雜訊。
    rng = np.random.default_rng(20260918)
    n = ok.sum()
    diffs = np.empty(2000)
    for i in range(2000):
        idx = rng.integers(0, n, n)
        lo_b, hi_b = low[idx], high[idx]
        if lo_b.sum() < 10 or hi_b.sum() < 10:
            diffs[i] = np.nan
            continue
        rb = mad_std(resid_bprp[idx][hi_b]) / mad_std(resid_bprp[idx][lo_b])
        rg = mad_std(resid_grp[idx][hi_b]) / mad_std(resid_grp[idx][lo_b])
        diffs[i] = rb - rg
    diffs = diffs[np.isfinite(diffs)]
    lo_ci, hi_ci = np.percentile(diffs, [2.5, 97.5])
    frac_positive = float((diffs > 0).mean())
    print(f"bootstrap（{len(diffs)} 次重抽）：(BP-RP 比值 − G-RP 比值) 的 95% CI "
          f"[{lo_ci:.3f}, {hi_ci:.3f}]，{frac_positive * 100:.1f}% 的重抽為正")
    if r_grp < r_bprp:
        sig = "但 95% CI 窄幅涵蓋 0，只是邊緣證據，不是明確顯著" \
            if lo_ci <= 0 <= hi_ci else "且 95% CI 不含 0，方向確立"
        print(f"G-RP 的散布隨汙染程度增加得比 BP-RP 慢（{r_grp:.2f} < {r_bprp:.2f}），"
              f"方向支持「G-RP 對星雲汙染更穩健」，{sig}。")
    else:
        print(f"沒有支持「G-RP 更穩健」——G-RP 散布反而隨汙染程度增加得"
              f"更快或相當（{r_grp:.2f} >= {r_bprp:.2f}），需要回頭檢視 C21"
              f"這項假設，不要直接引用。")

    np.savez(HERE / "results" / "d19_nebula_colour_robustness.npz",
             contam_snr=contam_snr, resid_bprp=resid_bprp,
             resid_grp=resid_grp, median_split=med,
             mad_low_bprp=mad_std(resid_bprp[low]),
             mad_high_bprp=mad_std(resid_bprp[high]),
             mad_low_grp=mad_std(resid_grp[low]),
             mad_high_grp=mad_std(resid_grp[high]),
             ratio_bprp=r_bprp, ratio_grp=r_grp,
             bootstrap_diff_ci=[lo_ci, hi_ci],
             bootstrap_frac_positive=frac_positive)
    print(f"\n寫入 results/d19_nebula_colour_robustness.npz")


if __name__ == "__main__":
    main()
