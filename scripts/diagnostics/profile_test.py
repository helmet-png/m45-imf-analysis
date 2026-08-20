# -*- coding: utf-8 -*-
"""輪廓測試：固定住的參數，會不會污染 IMF 斜率？

我們把金屬量固定在太陽值、把雙星質量比分布 q_gamma 固定為均勻。
固定在**錯的值**上不只損失精度，而是會系統性偏移其他參數 ——
這比誤差變大嚴重，因為它不會讓誤差棒變寬，而是讓中心值錯掉卻看起來很精確。

作法：把待測參數固定在數個不同的值，每次重新擬合其他所有參數，
看 alpha（以及年齡）移動多少。若移動量超過其自身的統計誤差，
代表固定該參數正在污染結果，必須放開或邊際化。

用網格搜尋而非 MCMC：四參數的網格只要幾分鐘，且不受概似曲面尖刺影響 ——
優化器會被尖刺困住，網格只是「某幾格的值偏高」，仍能看出整體趨勢。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit                                # noqa: E402
from pipeline.step3_age import IMF_BREAKS                     # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402


def grid_search(model, ages, avs, fbins, alphas, fixed_mh, fixed_qg,
                verbose=False):
    """固定金屬量與 q_gamma，在其餘四維網格上找最佳解。

    模型是六參數的，但輪廓測試的重點是「把待測參數釘死、其他全部重新擬合」，
    所以這裡把被測的那個當常數傳進去，只搜尋其餘四個。
    """
    best, best_lp = None, -np.inf
    for la in ages:
        for av in avs:
            for fb in fbins:
                for al in alphas:
                    theta = np.array([la, av, fb, al, fixed_mh, fixed_qg])
                    lp = model.log_posterior(theta)
                    if lp > best_lp:
                        best_lp, best = lp, theta.copy()
        if verbose:
            print(f"    logAge={la:.2f} 掃完，目前最佳 lnP={best_lp:.1f}",
                  flush=True)
    if best is None:
        # 整個網格都被先驗擋掉（通常是被測值超出 config 的先驗範圍）
        raise ValueError(
            f"固定 mh={fixed_mh:+.2f}, q_gamma={fixed_qg:+.2f} 時所有格點的 "
            f"lnP 都是 -inf。檢查 config.toml 的 joint_fit 先驗範圍是否涵蓋這些值。")
    return np.asarray(best), best_lp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", choices=["mh", "qgamma"], required=True)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--grid", default=None,
                    help="isochrone 網格檔名；預設沿用 config 的 joint_fit.grid_file")
    ap.add_argument("--all-mh", action="store_true",
                    help="param=mh 時掃過網格裡所有金屬量格點，而非預設的五個值")
    a = ap.parse_args()

    cfg = cfgmod.load()
    c3, cj = cfg.step3_age, cfg.joint_fit

    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    gname = a.grid or cj.get("grid_file") or (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat")
    print(f"isochrone 網格：{gname}")
    grid = isomod.load_grid(isomod.CACHE / gname)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    cfg._data["step3_age"]["n_synthetic"] = a.n_syn

    # 粗網格：夠看出趨勢即可，不求精確定位
    ages = np.arange(7.90, 8.11, 0.05)
    avs = np.arange(0.08, 0.33, 0.04)
    fbins = np.arange(0.25, 0.66, 0.05)
    alphas = np.arange(1.8, 2.81, 0.10)
    n_eval = len(ages) * len(avs) * len(fbins) * len(alphas)
    print(f"每次網格 {n_eval:,} 點，合成星 {a.n_syn:,}")

    if a.param == "mh":
        if a.all_mh:
            # 掃過網格裡實際存在的每一個金屬量格點 —— 這才能看出
            # 概似沿金屬量方向是有峰、還是一路往邊界爬（＝資料無約束力）
            values = [float(v) for v in
                      np.unique(np.asarray(grid["MH"], float))]
        else:
            values = [-0.2, -0.1, 0.0, 0.1, 0.2]
        label = "[M/H]"
    else:
        values = [-1.0, -0.5, 0.0, 0.5, 1.0]
        label = "q_gamma"
    print(f"測試參數：{label}，{len(values)} 個值："
          f"{min(values):.2f} 到 {max(values):.2f}\n")

    # 模型只需建一次：被測參數是每次呼叫時傳入的，不影響模型本身
    model = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    # 未被測的那個維持在目前的最佳估計上
    base_qg = -0.74      # 六參數 MCMC 給的 q_gamma 中位數
    base_mh = 0.19

    rows = []
    for v in values:
        t0 = time.time()
        fmh = v if a.param == "mh" else base_mh
        fqg = v if a.param == "qgamma" else base_qg
        best, lp = grid_search(model, ages, avs, fbins, alphas, fmh, fqg)
        rows.append((v, best, lp))
        print(f"{label}={v:+.2f}  logAge={best[0]:.3f}  A_V={best[1]:.3f}  "
              f"f_bin={best[2]:.2f}  alpha={best[3]:.2f}  lnP={lp:.1f}"
              f"  ({time.time()-t0:.0f}s)", flush=True)

    arr = np.array([r[1] for r in rows])
    print(f"\n=== 固定 {label} 造成的參數移動範圍 ===")
    names = ["logAge", "A_V", "f_bin", "alpha"]
    # 這些是四參數聯合擬合報出的統計誤差，拿來當比較基準
    stat_err = [0.017, 0.001, 0.017, 0.003]
    for i, nm in enumerate(names):
        span = arr[:, i].max() - arr[:, i].min()
        print(f"  {nm:<8} 範圍 {arr[:, i].min():.3f} – {arr[:, i].max():.3f}"
              f"  跨度 {span:.3f}   統計誤差 {stat_err[i]:.3f}"
              f"   倍數 {span/max(stat_err[i],1e-9):>6.1f}x")

    print(f"\n年齡對應 {10**arr[:,0].min()/1e6:.1f} – "
          f"{10**arr[:,0].max()/1e6:.1f} Myr")
    print("\n判讀：跨度遠大於統計誤差，代表固定該參數會系統性污染結果，")
    print("      必須放開成自由參數或在先驗上邊際化，不能只是固定住不管。")

    # 輪廓概似曲線：判斷資料到底有沒有約束這個參數的能力
    lps = np.array([r[2] for r in rows])
    vals = np.array(values, float)
    peak = int(np.argmax(lps))
    print(f"\n=== 輪廓概似（判斷資料有無約束力）===")
    print(f"{label:>8}{'lnP':>12}{'ΔlnP':>10}")
    for v, lp in zip(vals, lps):
        mark = "  <- 峰值" if lp == lps.max() else ""
        print(f"{v:>8.2f}{lp:>12.1f}{lp-lps.max():>10.1f}{mark}")

    at_edge = peak in (0, len(vals) - 1)
    print()
    if at_edge:
        print("峰值落在掃描範圍的**邊界**上 —— 資料偏好的值超出可測範圍，")
        print("代表對此參數沒有有效約束，報出的值是被邊界決定的，不是資料決定的。")
    else:
        # 用 ΔlnP = 0.5 當 1 sigma 的粗略界線
        inside = vals[lps > lps.max() - 0.5]
        print(f"峰值在範圍內部（{vals[peak]:+.2f}），資料**有**約束力。")
        print(f"ΔlnP < 0.5 的範圍：{inside.min():+.2f} 到 {inside.max():+.2f}"
              f"（約 1 sigma）")

    np.savez(HERE / "results" / f"profile_{a.param}.npz",
             values=np.array(values), best=arr,
             logp=np.array([r[2] for r in rows]))
    print(f"\n寫入 results/profile_{a.param}.npz")


if __name__ == "__main__":
    main()
