# -*- coding: utf-8 -*-
"""把注入回收原封不動套到傳統方法上 —— 缺口一與缺口二的核心計算（P1）。

**為什麼需要**：表 3 要把傳統法與前向模型放在同一張表，兩邊的誤差必須用
同一把尺量。前向模型那邊已有注入回收（偏差 +0.017、散布 0.14）；
傳統法目前只有概似曲率給的 ±0.069，而那把尺已被證明低估約 4 倍。

**傳統方法在這裡的定義**（文獻最常見的作法，即 step5 的方法 A）：
  1.（變體 B 才有）用 CMD 偏移法剔除偵測得到的雙星
  2. 取一條 isochrone 的單星主序，建立星等 -> 質量的對應
  3. 每顆觀測星（含未被剔除的雙星）當單星查質量
  4. 對質量做未分箱 MLE 冪律擬合

**刻意對傳統法有利的設定，使量到的偏差是下界**：
  - 給它「真的」isochrone（真實年齡、消光、金屬量）——
    實務上傳統法還得自己擬合年齡，誤差只會更大；
  - 統計散布用同一批 1,078 顆的注入回收量，與前向模型完全同基準。

假資料由前向模型生成（含雙星、選擇函數、差異消光 0.30 ——
與真實世界一致的已知效應），這正是「用已知答案考傳統方法」。
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
                      remove_cmd_binaries=False, cmd_thresh=0.375):
    """跑一次完整的傳統流程，回傳 (alpha, 使用星數, 剔除數)。"""
    color = np.asarray(color, float)
    mag = np.asarray(mag, float)
    n_rm = 0
    if remove_cmd_binaries:
        cs, gs = ms_colour_to_g(iso, dm, av, ext)
        g_ms = np.interp(color, cs, gs)
        is_bin = (g_ms - mag) > cmd_thresh     # 比同顏色主序亮超過門檻
        n_rm = int(is_bin.sum())
        color, mag = color[~is_bin], mag[~is_bin]
    masses = assign_masses(mag, iso, dm, av, ext)
    fit = mle_powerlaw(masses, m_lo, m_hi)
    return fit["alpha"], fit["n"], n_rm, fit["alpha_err"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--dav-true", type=float, default=0.30)
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
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    n_obs = len(color)

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    sel = selmod.load(HERE / "data" / "selection.npz")
    m_lo, m_hi = c5.mass_min, c5.mass_max

    # 傳統法拿到的是「真的」isochrone —— 對它有利，量到的偏差是下界
    iso_true = isomod.isochrone_at(grid, THETA_TRUE[0], THETA_TRUE[4])
    av_true = THETA_TRUE[1]
    a_true = THETA_TRUE[3]
    print(f"觀測 {n_obs:,} 顆；假資料真值 alpha={a_true}、"
          f"f_bin={THETA_TRUE[2]}、dav={args.dav_true}、選擇函數開")
    print(f"質量範圍 {m_lo}–{m_hi} M☉；每情境 {args.trials} 次\n")

    # --- 注入回收：不同真實雙星比例 × 兩種傳統變體 ---
    print(f"{'f_bin 真值':>10}{'變體':>14}{'alpha 平均':>11}{'散布':>8}"
          f"{'偏差':>9}{'平均剔除':>9}")
    results = {}
    # f_bin = 0 是**必要的對照組**，我一開始漏了它。
    #
    # 傳統法用 mle_powerlaw 在 0.30–2.50 M☉ 上擬合**單一**冪律，
    # 但前向模型的 alpha 只是 Kroupa 分段冪律裡 m > 0.5 M☉ 那一段的冪次
    # （0.08–0.5 那段固定在 1.3）。兩者不是同一個量：把單一冪律硬套在
    # 有轉折的質量函數上，本來就會得到比高質量端更平的斜率。
    #
    # 沒有這個對照，量到的偏差裡混著「雙星」與「分段定義不一致」兩個原因，
    # 而我們會把全部算到雙星頭上。f_bin=0 時的殘餘偏差就是後者的大小。
    #
    # 兩個擬合質量範圍：0.30–2.50 是 config 原設定，但它跨過了 Kroupa 在
    # 0.5 M☉ 的轉折；0.50–2.50 才與前向模型 alpha 的定義域一致。
    # 兩者的差 = 「分段定義不一致」這個純方法學效應的大小。
    for rlo, rhi, rtag in ((m_lo, m_hi, "0.30-2.50原設定"),
                           (0.50, m_hi, "0.50-2.50對齊")):
        for fbin in (0.00, 0.30, 0.45, 0.60):
            th = THETA_TRUE.copy()
            th[2] = fbin
            for remove, tag in ((False, "全當單星"), (True, "CMD剔除")):
                outs, rms = [], []
                for t in range(args.trials):
                    fc, fm = make_fake(base, th, n_obs, seed=5000 + 31 * t,
                                       dav=args.dav_true, selection=sel)
                    a, n, n_rm, _ = traditional_alpha(
                        fc, fm, iso_true, dm, av_true, ext, rlo, rhi,
                        remove_cmd_binaries=remove)
                    outs.append(a)
                    rms.append(n_rm)
                outs = np.array(outs)
                results[(rtag, fbin, tag)] = outs
                print(f"{fbin:>10.2f}{tag:>14}{outs.mean():>11.3f}"
                      f"{outs.std():>8.3f}{outs.mean()-a_true:>+9.3f}"
                      f"{np.mean(rms):>9.1f}   {rtag}")
        print()

    # --- 真實資料：兩種變體 × 兩種 isochrone 選擇 ---
    print("\n真實資料（1,078 顆）：")
    print(f"{'isochrone':>22}{'變體':>14}{'alpha':>8}{'曲率誤差':>9}"
          f"{'星數':>7}{'剔除':>6}")
    real = {}
    for la, av, note in ((8.00, 0.20, "step3 舊最佳(8.00,0.20)"),
                         (8.10, 0.30, "C 設定最佳(8.10,0.30)")):
        iso = isomod.isochrone_at(grid, la, 0.0)
        for remove, tag in ((False, "全當單星"), (True, "CMD剔除")):
            a, n, n_rm, err = traditional_alpha(
                color, mag, iso, dm, av, ext, m_lo, m_hi,
                remove_cmd_binaries=remove)
            real[(note, tag)] = a
            print(f"{note:>22}{tag:>14}{a:>8.3f}{err:>9.3f}{n:>7}{n_rm:>6}")

    print("\n判讀：")
    print("  「全當單星」的偏差 = 缺口一的量化（雙星沒接回 MF 的代價）")
    print("  「CMD剔除」剩下的偏差 = 單一偵測法剔除救不回來的部分（缺口二）")
    print("  真實資料兩條 isochrone 的差 = 傳統法對等時線選擇的敏感度")
    np.savez(HERE / "results" / "traditional_accounting.npz",
             **{f"inj::{r}::{fb}::{tag}": v
                for (r, fb, tag), v in results.items()},
             **{f"real::{k[0]}::{k[1]}": v for k, v in real.items()})
    print("寫入 results/traditional_accounting.npz")


if __name__ == "__main__":
    main()
