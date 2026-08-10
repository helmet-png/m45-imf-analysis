# -*- coding: utf-8 -*-
"""把注入回收原封不動套到傳統方法上 —— 缺口一與缺口二的核心計算（P1/P7）。

**為什麼需要**：表 3 要把傳統法與前向模型放在同一張表，兩邊的誤差必須用
同一把尺量。前向模型那邊已有注入回收（偏差 +0.017、散布 0.14）；
傳統法目前只有概似曲率給的 ±0.069，而那把尺已被證明低估約 4 倍。

**2026-08-10 擴充（見 PLAN_傳統法雙星修正比較.md）**：從兩種雙星處理變體
擴充到全部主流做法 + 前向模型，一次比較五種傳統變體：

  A. **全當單星**（忽略雙星）—— 基準線，前 Gaia 時代傳統法論文的隱含預設
  B. **CMD 偏移剔除法** —— 對齊 Cordoni et al. (2023, A&A 672, A29) 與
     Mikhnevich et al. (2026, arXiv:2604.20722，含 M45 本身)
  C. **RUWE 剔除法** —— Gaia 天測品質指標（Lindegren et al. 2021,
     A&A 649, A2），重用 `pipeline/step4_binaries.flag_ruwe()`
  D. **Gaia NSS 剔除法** —— 官方 non_single_star 目錄旗標，重用
     `pipeline/step4_binaries.flag_nss()`
  E. **文獻解析統計修正法** —— 不逐星剔除，直接對變體 A 的 alpha 套用
     Rosen (2026, arXiv:2603.15779) 給的光度加總修正量（−0.011～−0.021，
     取中點 0.016，方向：忽略雙星會低估 alpha，所以修正是加回去）

  C、D 兩個變體**做不到注入回收**（`make_fake()` 只產生 color/mag，
  不模擬 RUWE 或 Gaia NSS 目錄旗標），改用 bootstrap 重抽真實 1,078 顆——
  這是誠實的方法論限制，不是待修的 bug，論文裡要講清楚 C/D 的誤差棒
  跟 A/B/E 不是同一把尺，只能比中心值、不能直接比誤差棒大小。

**傳統方法在這裡的共同定義**（文獻最常見的作法，即 step5 的方法 A）：
  1.（B/C/D 才有）用對應判準剔除偵測得到的雙星
  2. 取一條 isochrone 的單星主序，建立星等 -> 質量的對應
  3. 每顆觀測星（含未被剔除的雙星）當單星查質量
  4. 對質量做未分箱 MLE 冪律擬合

**刻意對傳統法有利的設定，使量到的偏差是下界**：
  - 給它「真的」isochrone（真實年齡、消光、金屬量）——
    實務上傳統法還得自己擬合年齡，誤差只會更大；
  - 統計散布用同一批 1,078 顆的注入回收量，與前向模型完全同基準。

假資料由前向模型生成（含雙星、選擇函數、差異消光 0.30 ——
與真實世界一致的已知效應），這正是「用已知答案考傳統方法」。

**跟前向模型的控制變因一致性**（完整核對表見 PLAN 文件第三節）：
  - 質量範圍：主表只用 0.50–2.50（跟前向模型 alpha 定義域一致），
    0.30–2.50 降級為附錄，量化「範圍不對齊」這個純方法學效應
  - isochrone：主表只用當下 config C 的最終確認值（p2_final2：
    logage=8.033、A_V=0.383），`step3 舊最佳(8.00,0.20)` 降級為附錄
    敏感度測試
  - 差異消光：傳統法完全沒有消光自由度，這是兩個方法本質上的差異，
    不是能對齊的控制變因，不假裝一致
"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# step5_imf 開頭 import astropy，ARM64 上裝不起來；墊一個 table_compat 的替身。
from pipeline.table_compat import Table as _CompatTable  # noqa: E402
_a = types.ModuleType("astropy")
_t = types.ModuleType("astropy.table")
_t.Table = _CompatTable
_a.table = _t
sys.modules.setdefault("astropy", _a)
sys.modules.setdefault("astropy.table", _t)

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.step3_age import COL_G, COL_BP, COL_RP, _Ext    # noqa: E402
from pipeline.step5_imf import assign_masses, mle_powerlaw    # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import THETA_TRUE, make_fake          # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402

# Rosen (2026, arXiv:2603.15779) 光度加總的雙星偏差區間 −0.011～−0.021，
# 取中點的絕對值。忽略雙星會讓 alpha 偏低，所以修正是「加回去」。
ANALYTIC_CORRECTION = 0.016

# 當下 config C 的最終確認值（來自 p2_final2，10 次重複 logage 全部
# 精確落在 8.033；A_V 10 次平均 0.383，範圍 0.333–0.433）。
# **不要寫死在別處**——只有這裡一個地方定義，其他要用的地方 import 它。
CURRENT_LOGAGE = 8.033
CURRENT_AV = 0.383

# 舊選擇，降級為附錄敏感度測試用，不再進主表。
LEGACY_ISOCHRONE = (8.00, 0.20, "step3 舊最佳(8.00,0.20)")


def ms_colour_to_g(iso, dist_mod, av, ext):
    """單星主序的 顏色 -> 視星等 G 對應（CMD 偏移法要用）。

    只取「質量遞增時 G 單調變亮」的主序段（與 assign_masses 同邏輯），
    在該段上顏色隨質量單調變藍，所以 顏色 -> G 是良定義的。
    """
    m = np.asarray(iso["Mini"], float)
    g = np.asarray(iso[COL_G], float) + dist_mod + ext.g * av
    c = (np.asarray(iso[COL_BP], float) - np.asarray(iso[COL_RP], float)
         + (ext.bp - ext.rp) * av)
    o = np.argsort(m)
    m, g, c = m[o], g[o], c[o]
    keep = np.ones(len(m), bool)
    gmin = np.inf
    for i in range(len(m)):
        if g[i] < gmin:
            gmin = g[i]
        else:
            keep[i] = False
    g, c = g[keep], c[keep]
    o = np.argsort(c)
    return c[o], g[o]


def traditional_alpha(color, mag, iso, dm, av, ext, m_lo, m_hi,
                      variant="ignore", cmd_thresh=0.375,
                      ruwe=None, nss=None, ruwe_threshold=1.4):
    """跑一次完整的傳統流程，回傳 (alpha, 使用星數, 剔除數, alpha_err)。

    variant: "ignore"（全當單星）/ "cmd_offset"（CMD剔除）/
             "ruwe"（RUWE剔除，需傳 ruwe 陣列）/
             "nss"（GaiaNSS剔除，需傳 nss 陣列）/
             "analytic_correct"（不剔除，對 ignore 的結果套文獻修正量）
    """
    color = np.asarray(color, float)
    mag = np.asarray(mag, float)
    n_rm = 0
    if variant == "cmd_offset":
        cs, gs = ms_colour_to_g(iso, dm, av, ext)
        g_ms = np.interp(color, cs, gs)
        is_bin = (g_ms - mag) > cmd_thresh     # 比同顏色主序亮超過門檻
        n_rm = int(is_bin.sum())
        color, mag = color[~is_bin], mag[~is_bin]
    elif variant == "ruwe":
        if ruwe is None:
            raise ValueError("variant='ruwe' 需要傳 ruwe 陣列")
        is_bin = np.asarray(ruwe, float) > ruwe_threshold
        n_rm = int(is_bin.sum())
        color, mag = color[~is_bin], mag[~is_bin]
    elif variant == "nss":
        if nss is None:
            raise ValueError("variant='nss' 需要傳 nss 陣列")
        is_bin = np.asarray(nss, bool)
        n_rm = int(is_bin.sum())
        color, mag = color[~is_bin], mag[~is_bin]
    elif variant not in ("ignore", "analytic_correct"):
        raise ValueError(f"未知的 variant：{variant!r}")

    masses = assign_masses(mag, iso, dm, av, ext)
    fit = mle_powerlaw(masses, m_lo, m_hi)
    alpha = fit["alpha"]
    if variant == "analytic_correct" and np.isfinite(alpha):
        alpha = alpha + ANALYTIC_CORRECTION
    return alpha, fit["n"], n_rm, fit["alpha_err"]


def bootstrap_alpha_err(color, mag, iso, dm, av, ext, m_lo, m_hi, variant,
                        ruwe=None, nss=None, ruwe_threshold=1.4,
                        n_boot=1000, seed=7000):
    """對真實資料做 with-replacement 重抽，量「對這 1,078 顆星本身的敏感度」。

    **這跟注入回收量的不是同一個量**：注入回收量的是「對真實但未知的
    星團真值的偏差與散布」；bootstrap 量的是「換一批（重抽的）樣本會不會
    給出差不多的答案」。C/D（RUWE/NSS）做不到注入回收，只能用這個。
    順便對 A/B 也各跑一次當交叉檢查——量級接近是好現象，但不強求相等。
    """
    rng = np.random.default_rng(seed)
    n = len(color)
    color = np.asarray(color, float)
    mag = np.asarray(mag, float)
    outs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        a, _, _, _ = traditional_alpha(
            color[idx], mag[idx], iso, dm, av, ext, m_lo, m_hi,
            variant=variant,
            ruwe=(np.asarray(ruwe)[idx] if ruwe is not None else None),
            nss=(np.asarray(nss)[idx] if nss is not None else None),
            ruwe_threshold=ruwe_threshold)
        if np.isfinite(a):
            outs.append(a)
    outs = np.array(outs)
    return float(outs.mean()), float(outs.std())


# 三個能做注入回收的變體（A、B、E）。
INJ_VARIANTS = [("ignore", "全當單星"), ("cmd_offset", "CMD剔除"),
               ("analytic_correct", "文獻解析修正")]
# 只能在真實資料上跑、用 bootstrap 誤差的兩個變體（C、D）。
REAL_ONLY_VARIANTS = [("ruwe", "RUWE剔除"), ("nss", "GaiaNSS剔除")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--dav-true", type=float, default=0.30)
    ap.add_argument("--n-boot", type=int, default=1000,
                    help="RUWE/NSS 變體與 A/B 交叉檢查用的 bootstrap 次數")
    ap.add_argument("--skip-legacy", action="store_true",
                    help="跳過附錄用的舊 isochrone/舊質量範圍敏感度測試，加快跑完主表")
    args = ap.parse_args()

    cfg = cfgmod.load()
    c3, c2, c5 = cfg.step3_age, cfg.step2_cmd, cfg.step5_imf
    cj = cfg.joint_fit
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / GRID)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ruwe_all = np.asarray(clean["ruwe"], float)
    nss_all = (np.asarray(clean["non_single_star"], float)
              if "non_single_star" in clean.colnames
              else np.zeros(len(clean)))
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    ruwe_all, nss_all = ruwe_all[ok], nss_all[ok]
    nss_all = np.nan_to_num(nss_all, nan=0.0) > 0
    n_obs = len(color)

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    sel = selmod.load(HERE / "data" / "selection.npz")
    m_lo, m_hi = c5.mass_min, c5.mass_max
    ruwe_thr = cfg.step4_binaries.ruwe_threshold

    # 傳統法拿到的是「真的」isochrone —— 對它有利，量到的偏差是下界
    iso_true = isomod.isochrone_at(grid, THETA_TRUE[0], THETA_TRUE[4])
    av_true = THETA_TRUE[1]
    a_true = THETA_TRUE[3]
    print(f"觀測 {n_obs:,} 顆；假資料真值 alpha={a_true}、"
          f"f_bin={THETA_TRUE[2]}、dav={args.dav_true}、選擇函數開")
    print(f"質量範圍（主表）0.50–{m_hi}；每情境 {args.trials} 次\n")

    # --- 注入回收：不同真實雙星比例 x 三種能做注入回收的傳統變體 ---
    # f_bin = 0 是必要的對照組：傳統法用 mle_powerlaw 在對齊範圍
    # 0.50–2.50 上擬合單一冪律，這跟前向模型 alpha 定義域一致，
    # f_bin=0 時的殘餘偏差理論上該接近 0（沒有其他已知的定義域錯位）。
    mass_ranges = [(0.50, m_hi, "0.50-2.50對齊")]
    if not args.skip_legacy:
        mass_ranges.append((m_lo, m_hi, "0.30-2.50原設定(附錄)"))

    print(f"{'f_bin 真值':>10}{'變體':>16}{'alpha 平均':>11}{'散布':>8}"
          f"{'偏差':>9}{'平均剔除':>9}")
    results = {}
    for rlo, rhi, rtag in mass_ranges:
        for fbin in (0.00, 0.30, 0.45, 0.60):
            th = THETA_TRUE.copy()
            th[2] = fbin
            for variant, tag in INJ_VARIANTS:
                outs, rms = [], []
                for t in range(args.trials):
                    fc, fm = make_fake(base, th, n_obs, seed=5000 + 31 * t,
                                       dav=args.dav_true, selection=sel)
                    a, n, n_rm, _ = traditional_alpha(
                        fc, fm, iso_true, dm, av_true, ext, rlo, rhi,
                        variant=variant)
                    outs.append(a)
                    rms.append(n_rm)
                outs = np.array(outs)
                results[(rtag, fbin, tag)] = outs
                print(f"{fbin:>10.2f}{tag:>16}{outs.mean():>11.3f}"
                      f"{outs.std():>8.3f}{outs.mean()-a_true:>+9.3f}"
                      f"{np.mean(rms):>9.1f}   {rtag}")
        print()

    # --- 真實資料：五種變體 x isochrone 選擇 x 質量範圍 ---
    print("\n真實資料（1,078 顆）：")
    print(f"{'isochrone':>26}{'質量範圍':>16}{'變體':>16}{'alpha':>8}"
          f"{'誤差':>8}{'誤差核算':>10}{'星數':>7}{'剔除':>6}")
    real = {}
    isochrones = [(CURRENT_LOGAGE, CURRENT_AV, "config C 最終值(8.033,0.383)")]
    if not args.skip_legacy:
        isochrones.append(LEGACY_ISOCHRONE)
    for la, av, note in isochrones:
        iso = isomod.isochrone_at(grid, la, 0.0)
        ranges = [(0.50, m_hi, "0.50-2.50對齊")]
        if not args.skip_legacy:
            ranges.append((m_lo, m_hi, "0.30-2.50原設定(附錄)"))
        for rlo, rhi, rtag in ranges:
            for variant, tag in INJ_VARIANTS:
                a, n, n_rm, err = traditional_alpha(
                    color, mag, iso, dm, av, ext, rlo, rhi, variant=variant)
                real[(note, rtag, tag)] = (a, err, "曲率")
                print(f"{note:>26}{rtag:>16}{tag:>16}{a:>8.3f}"
                      f"{err:>8.3f}{'曲率':>10}{n:>7}{n_rm:>6}")
            for variant, tag in REAL_ONLY_VARIANTS:
                a, n, n_rm, _ = traditional_alpha(
                    color, mag, iso, dm, av, ext, rlo, rhi, variant=variant,
                    ruwe=ruwe_all, nss=nss_all, ruwe_threshold=ruwe_thr)
                _, boot_err = bootstrap_alpha_err(
                    color, mag, iso, dm, av, ext, rlo, rhi, variant,
                    ruwe=ruwe_all, nss=nss_all, ruwe_threshold=ruwe_thr,
                    n_boot=args.n_boot)
                real[(note, rtag, tag)] = (a, boot_err, "bootstrap")
                print(f"{note:>26}{rtag:>16}{tag:>16}{a:>8.3f}"
                      f"{boot_err:>8.3f}{'bootstrap':>10}{n:>7}{n_rm:>6}")

    print("\n交叉檢查：bootstrap vs 注入回收（只對主表 0.50-2.50、"
          "config C isochrone 做，f_bin 用未知——這裡是拿真實資料本身"
          "重抽，跟上面注入回收用假資料是不同的量，量級接近即可）：")
    iso_c = isomod.isochrone_at(grid, CURRENT_LOGAGE, 0.0)
    for variant, tag in INJ_VARIANTS[:2]:   # analytic_correct 沒有獨立剔除，不必比
        boot_mean, boot_err = bootstrap_alpha_err(
            color, mag, iso_c, dm, CURRENT_AV, ext, 0.50, m_hi, variant,
            n_boot=args.n_boot)
        print(f"  {tag:<12} bootstrap: alpha={boot_mean:.3f} 散布={boot_err:.3f}")

    print("\n判讀：")
    print("  「全當單星」的偏差 = 缺口一的量化（雙星沒接回 MF 的代價）")
    print("  「CMD剔除」/「RUWE剔除」/「GaiaNSS剔除」剩下的偏差 = 該偵測法")
    print("    剔除救不回來的部分（缺口二），三者判準不同、偵測到的雙星")
    print("    族群不同（見 Table 2 四法重疊矩陣，最高只重疊 18%）")
    print("  「文獻解析修正」不逐星剔除，是族群層級的解析修正，跟前三者是")
    print("    不同類別的做法，數字接近代表兩種哲學互相印證")
    print("  真實資料兩條 isochrone 的差（若有跑附錄）= 傳統法對等時線選擇的敏感度")
    print("  RUWE/GaiaNSS 兩欄的誤差是 bootstrap，跟其他欄的注入回收/曲率")
    print("    不是同一把尺，只能比中心值")

    np.savez(HERE / "results" / "traditional_accounting_v2.npz",
             **{f"inj::{r}::{fb}::{tag}": v
                for (r, fb, tag), v in results.items()},
             **{f"real::{k[0]}::{k[1]}::{k[2]}::alpha": v[0]
                for k, v in real.items()},
             **{f"real::{k[0]}::{k[1]}::{k[2]}::err": v[1]
                for k, v in real.items()})
    print("\n寫入 results/traditional_accounting_v2.npz")


if __name__ == "__main__":
    main()
