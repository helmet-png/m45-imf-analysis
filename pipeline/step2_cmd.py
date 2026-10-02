# -*- coding: utf-8 -*-
"""第 2 步：用成員星建色光圖（CMD），並做測光品質篩選。

這一步的產出不只是一張圖，更重要的是**第 3 步前向模型需要的觀測特性**：
每個星等的測光誤差有多大、樣本的完整度到哪裡。沒有這些，合成星團就無法
生成得跟觀測同等品質，擬合會系統性偏差。

======================================================================
【這支程式在做什麼】
======================================================================
兩件事：
  1. 測光品質篩選：把測光不可靠的成員星丟掉——太亮（偵測器飽和）、
     訊噪比太低、BP/RP 被附近星光或星雲汙染。
  2. 測光誤差模型：量出「多亮的星，測光誤差大約多少」，存成一張對照表。
     前向模型生成合成星時，依每顆合成星的亮度加上同樣大小的隨機誤差，
     合成色光圖才會跟觀測一樣「模糊」。

這個檔案**沒有 main()，不能直接執行**。正式流程由
scripts/drivers/run_pipeline.py --steps 2 呼叫 run()；輸出由 run_pipeline.py
寫成 data/cmd_members.csv（通過篩選的成員）與 data/errmodel.npz（誤差模型）。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
第三方套件：
  numpy（np）
      np.asarray       轉成數值陣列
      np.where         依條件逐元素二選一
      np.errstate      暫時關掉「除以零」等數值警告
      np.isfinite      判斷是不是正常數字
      np.linspace      在兩數之間等分出 n+1 個點（分箱邊界用）
      np.median／np.nanmin／np.nanmax  中位數、忽略 NaN 的最小／最大值
  astropy.table.Table  天文表格型別；成員星資料以它傳入傳出
Python 標準庫：
  pathlib.Path         路徑（ROOT 這個版本沒有用到）

======================================================================
【(b) 用到的參數與意義】
======================================================================
run(cfg, members)：
  cfg      整份 config.toml；本檔只讀 [step2_cmd] 這一段
  members  第 1 步選出的成員星表格（含 Gaia 的星等與品質欄位）
config.toml [step2_cmd] 被用到的設定：
  g_bright_limit = 4.0        比 G=4 更亮的星丟掉（偵測器飽和，測光不可靠）
  min_flux_snr_g = 50.0       G 波段流量訊噪比至少 50
  min_flux_snr_bp = 20.0      BP 波段至少 20
  min_flux_snr_rp = 20.0      RP 波段至少 20
  bp_rp_excess_sigma = 3.0    BP/RP 流量超額偏離正常值超過 3 倍散布就丟掉
  ext_coeff_g／bp／rp         消光係數（只有 deredden() 用，run() 沒用到）
名詞：
  流量訊噪比 flux_over_error  流量 ÷ 流量誤差；越大代表量得越準
  BP/RP 超額因子             (BP 流量 + RP 流量) ÷ G 流量。正常單星有一個
                             隨顏色變化的固定值；明顯偏高代表 BP、RP 的大孔徑
                             收到了別的光（鄰星或 M45 周圍的反射星雲）

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 163–213 行｜apply_quality_cuts()：三道品質篩選，記錄每道砍掉幾顆
  核心 2｜第 242–280 行｜photometric_error_model()：依星等分箱，量每箱的測光誤差中位數
  核心 3｜第 283–301 行｜run()：依序呼叫上面兩個函式
其餘輔助：mag_error（流量訊噪比 → 星等誤差）、bp_rp_excess_expected／sigma
（正常單星的超額因子與其散布）、_bin_by（分箱取中位數）。
photometric_quality_masks() 與 deredden() 是給診斷程式用的，run() 沒有呼叫。

======================================================================
【(d) 整體流程】
======================================================================
  成員星表格
    → 亮端：G < 4 丟掉
    → 訊噪比：G < 50、BP < 20、RP < 20 任一不達標就丟掉
    → BP/RP 超額：算出「這個顏色的正常單星應有的超額因子」，
      實測值偏離超過 3 倍散布就丟掉
    → 剩下的星 = 乾淨樣本
    → 用乾淨樣本：流量訊噪比換成星等誤差 → 依星等分 20 箱 → 每箱取誤差中位數
    → 回傳（乾淨樣本, 誤差模型）
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
    # ↓ 星等誤差 = 1.0857 ÷ 流量訊噪比；訊噪比 ≤ 0 或缺值時給 NaN。
    #   np.errstate 讓除以零時不印警告（那些結果反正會被 np.where 換成 NaN）
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
    # ↓ 分三段的多項式：顏色 < 0.5、0.5–4.0、≥ 4.0 各用一條公式
    return np.where(
        c < 0.5,
        1.154360 + 0.033772 * c + 0.032277 * c**2,
        np.where(c < 4.0,
                 1.162004 + 0.011464 * c + 0.049255 * c**2 - 0.005879 * c**3,
                 1.057572 + 0.140537 * c))


def bp_rp_excess_sigma(gmag: np.ndarray) -> np.ndarray:
    """該經驗關係式的散布（隨星等變化），Riello et al. 2021。"""
    g = np.asarray(gmag, float)
    # ↓ 越暗的星（G 越大）正常散布越大，所以容許的偏離也越寬
    return 0.0059898 + 8.817481e-12 * g**7.618399


def photometric_quality_masks(
        g, bp, rp, snr_g, snr_bp, snr_rp, excess_factor, *,
        g_bright_limit, min_flux_snr_g, min_flux_snr_bp,
        min_flux_snr_rp, excess_sigma_limit) -> tuple[np.ndarray, np.ndarray]:
    """Return the shared SNR/brightness and BP/RP-excess quality masks.

    Keyword thresholds make controlled diagnostics (for example BP15) reuse
    the production Gaia quality formulas without mutating global config.

    （中文：跟 apply_quality_cuts() 同樣的篩選公式，但門檻用參數傳入、
    回傳兩個布林遮罩而不是篩過的表格。給 BP15 等診斷程式用，正式流程沒用到。）
    """
    g = np.asarray(g, float)
    bp = np.asarray(bp, float)
    rp = np.asarray(rp, float)
    snr_g = np.asarray(snr_g, float)
    snr_bp = np.asarray(snr_bp, float)
    snr_rp = np.asarray(snr_rp, float)
    excess_factor = np.asarray(excess_factor, float)
    brightness = np.ones(g.shape, dtype=bool)
    if g_bright_limit is not None:
        brightness = ~(g < g_bright_limit)
    snr_mask = brightness
    for values, limit in ((snr_g, min_flux_snr_g),
                          (snr_bp, min_flux_snr_bp),
                          (snr_rp, min_flux_snr_rp)):
        if limit > 0:
            snr_mask &= np.isfinite(values) & (values >= limit)
    residual = excess_factor - bp_rp_excess_expected(bp - rp)
    sigma = bp_rp_excess_sigma(g)
    if excess_sigma_limit > 0:
        excess_mask = (np.isfinite(residual) & np.isfinite(sigma) & (sigma > 0)
                       & (np.abs(residual) < excess_sigma_limit * sigma))
    else:
        excess_mask = np.ones(g.shape, dtype=bool)
    return snr_mask, excess_mask


# ═══════════════ 核心 1：三道測光品質篩選 ═══════════════
def apply_quality_cuts(t: Table, cfg) -> tuple[Table, dict]:
    """套用測光品質篩選，回傳 (篩選後的表, 各條件砍掉幾顆的統計)。"""
    # ↓ n0：篩選前的星數；stats：記錄每道篩選砍掉幾顆
    n0 = len(t)
    stats = {}
    # ↓ keep：每顆星是否保留，先全部 True，每道篩選把不合格的改成 False
    keep = np.ones(n0, bool)

    g = np.asarray(t["phot_g_mean_mag"], float)
    bp_rp = np.asarray(t["bp_rp"], float)

    # 亮端飽和
    if cfg.g_bright_limit is not None:
        # ↓ m：不比上限亮的星（G ≥ 4）。寫成 ~(g < 4) 的效果是：
        #   G 缺值（NaN）的星在這一道不會被砍（NaN < 4 是 False，取反變 True）
        m = ~(g < cfg.g_bright_limit)
        # ↓ 記錄「原本還保留、這一道才被砍掉」的星數，各道統計才不會重複計算
        stats["亮端飽和"] = int((~m & keep).sum())
        keep &= m

    # 測光訊噪比
    # ↓ 三個波段各跑一次同樣的檢查：(欄位名, 門檻, 統計標籤)
    for col, lim, label in (
            ("phot_g_mean_flux_over_error", cfg.min_flux_snr_g, "G 訊噪比"),
            ("phot_bp_mean_flux_over_error", cfg.min_flux_snr_bp, "BP 訊噪比"),
            ("phot_rp_mean_flux_over_error", cfg.min_flux_snr_rp, "RP 訊噪比")):
        # ↓ 沒有這個欄位、或門檻設成 0，就跳過這一道
        if col not in t.colnames or lim <= 0:
            continue
        v = np.asarray(t[col], float)
        # ↓ 訊噪比要是正常數字而且 ≥ 門檻
        m = np.isfinite(v) & (v >= lim)
        stats[label] = int((~m & keep).sum())
        keep &= m

    # BP/RP 流量超額（星雲與擁擠區汙染）
    if cfg.bp_rp_excess_sigma > 0 and "phot_bp_rp_excess_factor" in t.colnames:
        e = np.asarray(t["phot_bp_rp_excess_factor"], float)
        # ↓ 殘差 = 實測超額因子 − 這個顏色的正常單星應有的值
        resid = e - bp_rp_excess_expected(bp_rp)
        # ↓ |殘差| < 3 × 該星等的正常散布才保留
        m = np.isfinite(resid) & (
            np.abs(resid) < cfg.bp_rp_excess_sigma * bp_rp_excess_sigma(g))
        stats["BP/RP 超額"] = int((~m & keep).sum())
        keep &= m

    # ↓ 記下總數，回傳篩選後的表格
    stats["_保留"] = int(keep.sum())
    stats["_原始"] = n0
    return t[keep], stats


def deredden(t: Table, av: float, cfg) -> tuple[np.ndarray, np.ndarray]:
    """套用消光修正，回傳 (絕對星等前的 G0, 顏色 (BP-RP)0)。"""
    g = np.asarray(t["phot_g_mean_mag"], float)
    bp_rp = np.asarray(t["bp_rp"], float)
    # ↓ 扣掉消光：G0 = G − A_G；(BP−RP)0 = (BP−RP) − (A_BP − A_RP)
    g0 = g - cfg.ext_coeff_g * av
    c0 = bp_rp - (cfg.ext_coeff_bp - cfg.ext_coeff_rp) * av
    return g0, c0


def _bin_by(x: np.ndarray, y: np.ndarray, ok: np.ndarray, n_bins: int):
    # ↓ 在 x 的最小值與最大值之間等分出 n_bins 個箱子
    edges = np.linspace(np.nanmin(x[ok]), np.nanmax(x[ok]), n_bins + 1)
    centres, vals = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        # ↓ 落在這一箱的星
        m = ok & (x >= lo) & (x < hi)
        # ↓ 少於 3 顆就略過這一箱（中位數不可靠）
        if m.sum() < 3:
            continue
        # ↓ 記下箱子中心與這一箱 y 的中位數
        centres.append(0.5 * (lo + hi))
        vals.append(float(np.median(y[m])))
    return np.array(centres), np.array(vals)


# ═══════════════ 核心 2：測光誤差模型 ═══════════════
def photometric_error_model(t: Table, n_bins: int = 20) -> dict:
    """量出「星等 → 測光誤差」的關係，供前向模型生成合成星時使用。

    回傳分箱後的中位數誤差；合成星團的每顆星會依其星等內插出對應的誤差。

    **2026-08-10 新增 e_bp/e_rp 各自波段的版本（"待辦逐項體檢" 發現的
    現役缺陷）**：`e_bp`/`e_rp`（用 G 分箱）保留給舊呼叫端相容，新增
    `bp`/`e_bp_native`、`rp`/`e_rp_native`（改用星體自己的 BP/RP 星等
    分箱）。同一顆星在給定 G 之下，紅星的 BP 比藍星暗得多——用 G 查
    BP 誤差等於用一個比真實 BP 星等亮的值去查，會低估紅星的 BP 誤差。
    這裡先把兩種都算出來、寫進同一個 errmodel，讓
    `pipeline/step3_age.synth_populations()` 可以在有 native 版本時
    優先使用，同時不破壞任何舊快取的 `errmodel.npz`（沒有這兩個鍵的
    舊檔案會自動退回舊行為，不會炸掉）。
    """
    # ↓ 三個波段的星等
    g = np.asarray(t["phot_g_mean_mag"], float)
    bp = np.asarray(t["phot_bp_mean_mag"], float)
    rp = np.asarray(t["phot_rp_mean_mag"], float)
    # ↓ 三個波段的星等誤差（由流量訊噪比換算）
    e_g = mag_error(t["phot_g_mean_flux_over_error"])
    e_bp = mag_error(t["phot_bp_mean_flux_over_error"])
    e_rp = mag_error(t["phot_rp_mean_flux_over_error"])

    # ↓ 只用六個量都正常的星
    ok = (np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp) &
          np.isfinite(e_g) & np.isfinite(e_bp) & np.isfinite(e_rp))
    # ↓ 依 G 分箱：G 誤差、以及舊版的 BP、RP 誤差
    g_c, sg = _bin_by(g, e_g, ok, n_bins)
    _, sbp_by_g = _bin_by(g, e_bp, ok, n_bins)
    _, srp_by_g = _bin_by(g, e_rp, ok, n_bins)
    # ↓ 新版：BP 誤差依 BP 星等分箱、RP 誤差依 RP 星等分箱
    bp_c, sbp_native = _bin_by(bp, e_bp, ok, n_bins)
    rp_c, srp_native = _bin_by(rp, e_rp, ok, n_bins)
    # ↓ 回傳的字典就是 errmodel：g／bp／rp 是箱子中心星等，e_* 是對應誤差
    return {"g": g_c, "e_g": sg, "e_bp": sbp_by_g, "e_rp": srp_by_g,
            "bp": bp_c, "e_bp_native": sbp_native,
            "rp": rp_c, "e_rp_native": srp_native}


# ═══════════════ 核心 3：第 2 步的入口 ═══════════════
def run(cfg, members: Table) -> tuple[Table, dict]:
    """執行第 2 步。members 需含 phot_* 欄位。"""
    # ↓ 只取 config 的 [step2_cmd] 這一段
    c2 = cfg.step2_cmd
    # ↓ 品質篩選（核心 1）
    clean, stats = apply_quality_cuts(members, c2)

    # ↓ 印出每道篩選砍掉幾顆
    print(f"測光品質篩選：{stats['_原始']:,} -> {stats['_保留']:,} 顆")
    for k, v in stats.items():
        if not k.startswith("_") and v:
            print(f"  {k:<12} 砍掉 {v:,}")

    # ↓ 用篩選後的乾淨樣本量測光誤差模型（核心 2）
    errmodel = photometric_error_model(clean)
    print(f"測光誤差模型：{len(errmodel['g'])} 個星等分箱，"
          f"G 誤差 {errmodel['e_g'].min():.4f} – {errmodel['e_g'].max():.4f} mag")
    return clean, errmodel
