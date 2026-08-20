# -*- coding: utf-8 -*-
"""給出可用的 IMF 斜率與誠實的誤差estimate。

**為什麼不直接用六參數 MCMC 的結果**：
Poisson-Hess 概似把 2,000 個格子當成互相獨立，把同一份證詞重複採計，
導致它過度自信到任何合理的先驗都推不動（實測高斯先驗中心 -0.03、sigma 0.10，
後驗仍跑到 +0.181，離先驗 2.1 sigma，因為先驗懲罰只有 -2.2 而概似差異數百）。
在這種情況下 MCMC 報的誤差棒沒有意義。

**改用的作法**：
金屬量由外部資料（Gaia 光譜）約束在一個區間，在該區間內掃描，
每個值都重新擬合其餘參數。α 的移動範圍就是**系統誤差**，
這比概似曲率算出的統計誤差誠實得多。

年齡網格必須涵蓋 MCMC 找到的區域（logAge 約 8.18）——
先前的輪廓測試網格上限只到 8.10，根本沒涵蓋到真正的峰值。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit                                # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402

GRID = "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"

# Gaia 光譜給的金屬量約束（與 CMD 擬合機制完全獨立）
#   GSP-Spec（RVS 高解析度譜線，153 顆）  -0.020
#   GSP-Phot（BP/RP 低解析度光譜，1015 顆）-0.061
# 取中心 -0.03，1 sigma 範圍 +-0.10
MH_VALUES = [-0.13, -0.08, -0.03, 0.02, 0.07]


def main():
    cfg = cfgmod.load()
    c3, cj = cfg.step3_age, cfg.joint_fit

    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / GRID)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    print(f"觀測 {len(color):,} 顆，距離模數 {dm:.4f}")

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    # 掃描時關掉高斯先驗，否則會把金屬量往中心拉、破壞輪廓的意義
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    model = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)

    # 年齡範圍必須涵蓋 MCMC 找到的區域（logAge 約 8.18）
    ages = np.arange(7.95, 8.31, 0.05)
    avs = np.arange(0.00, 0.33, 0.04)
    fbins = np.arange(0.30, 0.71, 0.05)
    alphas = np.arange(1.9, 2.91, 0.05)
    qgs = [-0.7, 0.0]          # 輪廓測試顯示影響很小，取兩個值確認
    n = len(ages) * len(avs) * len(fbins) * len(alphas) * len(qgs)
    print(f"每個金屬量值要掃 {n:,} 個格點\n")

    rows = []
    for mh in MH_VALUES:
        t0 = time.time()
        best, best_lp = None, -np.inf
        for la in ages:
            for av in avs:
                for fb in fbins:
                    for al in alphas:
                        for qg in qgs:
                            th = np.array([la, av, fb, al, mh, qg])
                            lp = model.log_posterior(th)
                            if lp > best_lp:
                                best_lp, best = lp, th.copy()
        rows.append((mh, best, best_lp))
        print(f"[M/H]={mh:+.2f}  logAge={best[0]:.2f} ({10**best[0]/1e6:.0f} Myr)"
              f"  A_V={best[1]:.2f}  f_bin={best[2]:.2f}  "
              f"alpha={best[3]:.2f}  q_g={best[5]:+.1f}  "
              f"lnP={best_lp:.1f}  ({time.time()-t0:.0f}s)", flush=True)

    arr = np.array([r[1] for r in rows])
    lps = np.array([r[2] for r in rows])
    best_i = int(np.argmax(lps))

    print(f"\n{'='*60}\n最終結果\n{'='*60}")
    print(f"最佳解（[M/H]={MH_VALUES[best_i]:+.2f}）：")
    print(f"  年齡      {10**arr[best_i,0]/1e6:.0f} Myr (logAge {arr[best_i,0]:.2f})")
    print(f"  消光      A_V = {arr[best_i,1]:.2f}")
    print(f"  雙星比例  f_bin = {arr[best_i,2]:.2f}")
    print(f"  IMF 斜率  alpha = {arr[best_i,3]:.2f}")

    print(f"\n系統誤差（金屬量在 Gaia 光譜給的 1 sigma 內變動造成的移動）：")
    names = ["logAge", "A_V", "f_bin", "alpha"]
    for i, nm in enumerate(names):
        lo, hi = arr[:, i].min(), arr[:, i].max()
        print(f"  {nm:<8} {lo:.3f} – {hi:.3f}   跨度 {hi-lo:.3f}"
              f"   (+-{(hi-lo)/2:.3f})")
    print(f"  年齡      {10**arr[:,0].min()/1e6:.0f} – "
          f"{10**arr[:,0].max()/1e6:.0f} Myr")

    a_lo, a_hi = arr[:, 3].min(), arr[:, 3].max()
    print(f"\n**可報告的 IMF 斜率：alpha = {arr[best_i,3]:.2f} "
          f"+- {(a_hi-a_lo)/2:.2f}（系統）**")
    print(f"  對照 Salpeter 2.35、Kroupa 高質量端 2.30")
    print(f"  對照傳統法（每顆星當單星）1.98 +- 0.07（僅統計誤差）")

    np.savez(HERE / "results" / "final_imf.npz",
             mh_values=np.array(MH_VALUES), best=arr, logp=lps, dm=dm)
    print(f"\n寫入 results/final_imf.npz")


if __name__ == "__main__":
    main()
