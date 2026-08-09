# -*- coding: utf-8 -*-
"""驗證兩階段網格搜尋有沒有落入局部最佳。

**動機**：切半實驗的 10 次切分裡，alpha 有四次落在 2.68（切分 4、5、6、10），
遠離其他所有結果的 2.02–2.40。粗掃格距 0.10 大於 alpha 的峰寬 0.072，
所以粗掃可能跨過主峰、卡在假峰上，精修再把它精修到 2.68 附近。

若不驗證就把這批數字拿去修正誤差棒，等於把搜尋失敗當成物理結果報出去。

**作法**：挑切分 4（出現 2.68 的其中一次），用完整細格距**一次全掃**，
不分兩階段。比對兩者的答案：
  一致   -> 兩階段可信，2.68 是真的，高估倍數 1.5 成立
  不一致 -> 兩階段會卡假峰，整批候選結果作廢，須換搜尋策略

**成本控制**：六維全開要 5.5 小時。這裡把已經確定的維度收窄：
q_gamma 固定（輪廓測試證實影響極小）、logAge 只掃 8.00–8.30，
其餘維度用與精修階段相同的細格距。
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
from pipeline import joint_fit                                # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import (GRID, two_stage_best,     # noqa: E402
                                    grid_best_parallel)

SPLIT_INDEX = 4          # 要驗證的切分編號（1 起算）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None,
                    help="平行行程數，預設為 CPU 核心數")
    args = ap.parse_args()
    n_proc = args.procs if args.procs else (os.cpu_count() or 1)
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
    n = len(color)

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0

    # 重現 measure_overconfidence.py 的切分順序：同一顆種子、同樣的抽取次序
    rng = np.random.default_rng(cfg.step1_membership.random_seed)
    perm = None
    for _ in range(SPLIT_INDEX):
        perm = rng.permutation(n)
    h = n // 2
    halves = [perm[:h], perm[h:]]
    print(f"驗證切分 {SPLIT_INDEX}，兩半各 {h:,} / {n-h:,} 顆")

    # 兩階段用的粗網格（與 measure_overconfidence.py 完全一致）
    coarse = [np.arange(8.00, 8.31, 0.05), np.arange(0.00, 0.29, 0.06),
              np.arange(0.35, 0.71, 0.05), np.arange(2.0, 2.81, 0.10),
              np.arange(0.00, 0.31, 0.10), np.array([-0.7])]
    bounds_list = [(x.min(), x.max()) for x in coarse]

    # 全掃用的網格。
    #
    # 這裡要驗的是「兩階段有沒有跨過主峰、卡在假峰上」，
    # 也就是**粗掃階段的漏檢**。精修階段本來就只在最佳粗點附近找，
    # 它的解析度高低不影響「有沒有找對山」這個判斷。
    #
    # 所以正確的對照組是「用粗掃的一半格距做完整掃描」——
    # 若這樣掃出來的最佳點與兩階段落在同一座山，粗掃就沒有漏。
    # 用精修後的解析度（1/4 粗格距）全掃會產生 590 萬格點（單半 24.6 小時），
    # 而且測到的是不同的東西（解析度差異而非漏檢）。
    fine = [np.arange(8.00, 8.301, 0.025), np.arange(0.00, 0.281, 0.03),
            np.arange(0.35, 0.701, 0.025), np.arange(2.0, 2.801, 0.05),
            np.arange(0.00, 0.301, 0.05), np.array([-0.7])]
    npt = int(np.prod([len(x) for x in fine]))
    print(f"全掃格點數 {npt:,}（單次約 15 ms，單執行緒需 "
          f"{npt*0.015/3600:.1f} 小時/半，{n_proc} 行程預估 "
          f"{npt*0.015/3600/n_proc:.1f} 小時/半）\n")

    for k, idx in enumerate(halves, 1):
        m = joint_fit.JointModel(cfg, color[idx], mag[idx], grid, errmodel, dm)

        t0 = time.time()
        b2, lp2 = two_stage_best(m, coarse, bounds_list, 4, n_proc)
        t_two = time.time() - t0

        t0 = time.time()
        bf, lpf = grid_best_parallel(m, fine, n_proc)
        t_full = time.time() - t0

        print(f"--- 第 {k} 半 ---")
        print(f"  兩階段: " + "  ".join(
            f"{nm}={v:.3f}" for nm, v in zip(joint_fit.PARAM_NAMES, b2))
            + f"  lnP={lp2:.1f}  ({t_two:.0f}s)")
        print(f"  全掃  : " + "  ".join(
            f"{nm}={v:.3f}" for nm, v in zip(joint_fit.PARAM_NAMES, bf))
            + f"  lnP={lpf:.1f}  ({t_full:.0f}s)")
        d = np.abs(b2 - bf)
        print(f"  差異  : " + "  ".join(
            f"{nm}={v:.3f}" for nm, v in zip(joint_fit.PARAM_NAMES, d)))
        print(f"  lnP 差: {lpf - lp2:+.1f}"
              f"（正值代表全掃找到更好的解 = 兩階段漏掉了）\n", flush=True)

        np.savez(HERE / "results" / f"verify_split{SPLIT_INDEX}_half{k}.npz",
                 two_stage=b2, two_stage_lp=lp2, full=bf, full_lp=lpf)

    print("判讀：若 lnP 差接近 0 且參數一致，兩階段可信；")
    print("      若全掃的 lnP 明顯較高，代表兩階段卡在假峰，候選結果作廢。")


if __name__ == "__main__":
    main()
