# -*- coding: utf-8 -*-
"""驗證排程項目：殘留場星污染比例（outlier_frac）的敏感度輪廓測試。

**動機**（2026-08-10，LIMITATIONS.md 待辦分類標準訂定後的體檢發現）：
`pipeline/step3_age.poisson_loglike()` 用一個均勻離群成分描述殘留場星污染，
比例寫死在函式簽名的預設值 `outlier_frac=0.01`，從未做過敏感度測試就套用
到目前所有已引用的結果上。有一個獨立佐證撐著（與 HR23 真正判定分歧
20/1078=1.9% 量級相符），但這不等於驗證過——這是**現在每一次擬合都在用**
的假設，不是「以後可能發生」的風險，按 `CLAUDE.md` 的分類標準不該只
安靜排隊，必須量出改變它的代價。

**判讀基準**：同 profile_lowmass.py，用注入回收量到的 alpha 統計誤差
0.144（S3F，最乾淨的一次）當比較尺度。

**用修好的模型（config C：選擇函數 + 差異消光）**，理由同 profile_lowmass.py：
論文要報的數字來自 C，用舊模型測敏感度答非所問。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import COARSE, multi_stage_best       # noqa: E402

ALPHA_STAT_SIGMA = 0.144

# 掃描範圍：現行值 0.01 的一半到三倍，涵蓋「殘留污染其實更少」跟
# 「其實更多」兩種方向。20/1078=1.9% 落在這個範圍中間偏右。
OUTLIER_FRACS = [0.005, 0.01, 0.02, 0.03]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--repeats", type=int, default=3,
                    help="每個 outlier_frac 值重複幾次")
    ap.add_argument("--refines", default="3",
                    help="精修階數，逗號分隔。3,3 較精確但貴一倍")
    ap.add_argument("--dav-max", type=float, default=0.6)
    ap.add_argument("--fracs", default=None,
                    help="逗號分隔，覆寫預設的 OUTLIER_FRACS 掃描點")
    args = ap.parse_args()
    n_proc = args.procs or (os.cpu_count() or 1)
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    fracs = ([float(x) for x in args.fracs.split(",")] if args.fracs
            else OUTLIER_FRACS)

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
    n_obs = len(color)

    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    sel = selmod.load(HERE / "data" / "selection.npz")
    print(f"真實觀測 {n_obs:,} 顆，config C（選擇函數 + 差異消光），"
          f"n_synthetic {args.n_syn:,}")
    print(f"掃描殘留場星污染比例 outlier_frac：{fracs}\n")

    from pipeline.step3_age import draw_randoms
    results = {}
    for frac in fracs:
        outs = []
        for rep in range(args.repeats):
            import copy
            m = copy.copy(base)
            m.obs_h = joint_fit.hess(color, mag, base.nb_c, base.nb_m,
                                     base.crange, base.mrange)
            m.n_obs = n_obs
            m.selection = sel
            m.bounds = base.bounds[:6].copy()
            m.outlier_frac = frac
            if args.repeats > 1:
                m.draws = draw_randoms(m.n_syn,
                                       np.random.default_rng(5000 + 13 * rep))
            extra = np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 4)
            m.enable_dav_fit(0.0, args.dav_max)

            t0 = time.time()
            # q_gamma(5) 與 dav(6) 是已知的 nuisance，貼牆放行；其餘任何
            # 一維貼牆都要中止——若改變 outlier_frac 讓 alpha 或 A_V
            # 撞到牆，那本身就是重要的診斷結果。
            best, lp, bounds = multi_stage_best(
                m, COARSE, refines, n_proc, extra_axis=extra,
                allow_wall=(5, 6))
            outs.append(best)
            print(f"  frac={frac:.3f} 第{rep+1}次  alpha={best[3]:.3f}  "
                  f"A_V={best[1]:.3f}  logage={best[0]:.3f}  "
                  f"lnP={lp:.1f}  ({time.time()-t0:.0f}s)", flush=True)
        arr = np.array(outs)
        results[frac] = arr
        print(f"  -> frac={frac:.3f} 跨 {args.repeats} 次：alpha 平均 "
              f"{arr[:,3].mean():.3f}，散布 {arr[:,3].std():.3f}\n",
              flush=True)

    print(f"{'='*70}\nalpha 對殘留場星污染比例的敏感度\n{'='*70}")
    print(f"{'frac':>8}{'alpha 平均':>11}{'散布':>8}")
    means = []
    for frac in fracs:
        a = results[frac][:, 3]
        means.append(a.mean())
        print(f"{frac:>8.3f}{a.mean():>11.3f}{a.std():>8.3f}")
    means = np.array(means)
    span = float(means.max() - means.min())
    print(f"\nalpha 跨度（掃過 frac={min(fracs)}-{max(fracs)}）= {span:.3f}")
    print(f"對照注入回收統計誤差 {ALPHA_STAT_SIGMA:.3f} "
          f"-> {span/ALPHA_STAT_SIGMA:.1f} 倍")
    print("\n判讀：倍數遠大於 1，代表 1% 這個猜的常數必須量測或升格為自由參數；")
    print("      倍數接近或小於 1，代表目前固定 0.01 不是主要誤差來源，")
    print("      LIMITATIONS.md 裡「現役假設」的標記可以降級為「已驗證安全」。")

    np.savez(HERE / "results" / "profile_outlierfrac.npz",
             fracs=np.array(fracs),
             **{f"f{frac}": v for frac, v in results.items()})
    print("\n寫入 results/profile_outlierfrac.npz")


if __name__ == "__main__":
    main()
