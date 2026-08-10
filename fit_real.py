# -*- coding: utf-8 -*-
"""把修好的模型接上真實資料，看 alpha 到底移到哪裡。

**這支程式回答的問題**：注入回收量出模型漏了兩個效應（選擇函數 −0.178、
差異消光 +0.178），但那是在假資料上量的。真實資料上實際會移動多少？

作法是同一批觀測星、同一套搜尋，只換模型設定，逐項加回去：

  A  舊模型（無選擇函數、無差異消光）      <- 現有的 2.26–2.35 從這裡來
  B  只加選擇函數                          <- 預期 alpha 變陡
  C  選擇函數 + 差異消光自由（上界 0.6）    <- 預期抵消掉一部分
  D  同 C，但 dav 上界放到 1.2              <- 檢查 alpha 會不會跟著牆跑

D 是必要的：注入回收顯示 dav 是**不可辨識**的，給多少範圍它就吃多少
（上界 0.6 時跑到 0.600，放寬到 1.2 就跑到 1.200，加大 n_synthetic 也沒用）。
既然 dav 自己會貼牆，就必須確認 alpha 不會跟著牆的位置變 ——
在假資料上確認過（alpha 偏差與對照組完全相同），真實資料上要再確認一次，
因為真實資料還有模型沒描述到的其他不符。

**這裡報出來的 alpha 仍然不是最終值。** isochrone 模型的系統誤差
（PARSEC vs MIST/BHAC15）還沒量過，而注入回收在設計上就看不到它。
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=120_000)
    ap.add_argument("--configs", default="A,B,C,D")
    # 真實資料只有一份，重複擬合時「變的是什麼」必須講清楚：
    # 變的是**模型端的共用亂數**。合成星團是有限筆抽樣，換一批亂數
    # 概似曲面就會微幅改變，最佳解跟著移動。這個移動量就是
    # 「單次擬合的重現性」，A 與 C 的差要大於它才算真的位移。
    ap.add_argument("--repeats", type=int, default=1,
                    help="每個設定重複幾次（每次換一組模型端共用亂數）")
    ap.add_argument("--grid", default=GRID,
                    help="isochrone 網格檔名（在 isochrones/ 底下）。"
                         "換成 MIST 的檔案即可量出等時線模型造成的系統誤差")
    ap.add_argument("--tag", default="", help="輸出檔名後綴，避免覆蓋")
    # 精修階數。預設單階（格距 1/3）會讓 alpha 只落在 2.1/2.3/2.5 這種粗格點上；
    # 要當最終數字報時用 3,3（格距 1/9 = 0.022）才不會被量化污染。
    ap.add_argument("--refines", default="3")
    # P9：把金屬量釘死在指定值，判別表 4 的等時線穩健性是真的、
    # 還是靠 MH 這個自由參數在兩套模型上各自吸收了共同偏差換來的。
    #
    # **必須用兩套網格共有的格點**。isochrone 是離散的，_isochrone() 會
    # 吸附到最近的格點：PARSEC 的 MH 間距 0.05、MIST 只有 0.25，
    # 若指定光譜值 -0.03，PARSEC 吸附到 -0.05、MIST 吸附到 +0.00，
    # 憑空造出 0.05 dex 的差異，正好污染這個檢驗要看的東西。
    # MH=0.00 兩套都有（吸附誤差為零），且距光譜值 -0.03 僅 0.03，
    # 遠比自由擬合跑到的 +0.18 接近，檢驗邏輯成立。
    ap.add_argument("--fix-mh", type=float, default=None,
                    help="把金屬量固定在此值（P9 檢驗用）。"
                         "務必選 PARSEC 與 MIST 共有的格點，預設建議 0.0")
    # 驗證排程項目（2026-08-10，LIMITATIONS.md 待辦分類標準訂定後）：
    # 用 G 查 BP/RP 誤差會低估紅星誤差，這是每次擬合都在用的現役假設，
    # 從未驗證過代價。開這個旗標改用星體自己的 BP/RP 星等查各自波段
    # 的誤差曲線，A/B 跑兩次比較 alpha 有沒有變。
    ap.add_argument("--native-bprp-err", action="store_true",
                    help="改用星體自己的 BP/RP 星等查測光誤差（而非用 G）。"
                         "需要 errmodel.npz 含 e_bp_native/e_rp_native 鍵")
    args = ap.parse_args()
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    n_proc = args.procs or (os.cpu_count() or 1)

    cfg = cfgmod.load()
    c3 = cfg.step3_age
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / args.grid)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]

    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0   # 先看概似本身要什麼

    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    base.use_native_bprp_err = args.native_bprp_err
    if args.native_bprp_err and "e_bp_native" not in errmodel:
        print("錯誤：--native-bprp-err 需要 errmodel.npz 含 e_bp_native/"
              "e_rp_native 鍵，目前載入的檔案沒有，先重建 errmodel.npz")
        sys.exit(1)
    sel = selmod.load(HERE / "data" / "selection.npz")
    print(f"真實觀測 {len(color):,} 顆，距離模數 {dm:.4f}，"
          f"n_synthetic {args.n_syn:,}")
    print(f"等時線網格：{args.grid}\n")

    # 第四項是允許貼牆的維度索引。
    #
    # A 與 B 沒有差異消光參數，而注入回收已證實：真實世界有差異消光、
    # 模型沒有時，A_V（索引 1）會被壓到物理下限 0。實測真實資料上確實如此
    # —— 這是這兩個設定**預期的症狀**，不是意外，所以放行但會標示出來。
    # q_gamma（索引 5）注入回收判定不受資料約束（對照組散布 0.157–0.236、
    # 正負亂跳），跟 dav 一樣是 nuisance，會在兩側牆之間遊走 ——
    # 實測 PARSEC 撞下界 −1.2、MIST 撞上界 +0.8。放行，但絕不能當測量值報。
    # C 與 D 是修好的模型，除上述已知項外任何一維貼牆都必須中止。
    CONFIGS = {
        "A": ("舊模型：無選擇函數、無差異消光", None, None, (1, 5)),
        "B": ("只加選擇函數", sel, None, (1, 5)),
        "C": ("選擇函數 + 差異消光（上界 0.6）", sel,
              np.arange(0.0, 0.61, 0.15), (5, 6)),
        "D": ("選擇函數 + 差異消光（上界 1.2）", sel,
              np.arange(0.0, 1.21, 0.20), (5, 6)),
    }

    from pipeline.step3_age import draw_randoms
    out = {}
    for key in [k.strip().upper() for k in args.configs.split(",")]:
        if key not in CONFIGS:
            continue
        desc, s, extra, allow = CONFIGS[key]
        print(f"{'='*74}\n{key}：{desc}\n{'='*74}", flush=True)
        reps = []
        for rep in range(args.repeats):
            import copy
            m = copy.copy(base)
            m.obs_h = joint_fit.hess(color, mag, base.nb_c, base.nb_m,
                                     base.crange, base.mrange)
            m.n_obs = len(color)
            m.selection = s
            m.bounds = base.bounds[:6].copy()
            if args.repeats > 1:
                m.draws = draw_randoms(m.n_syn,
                                       np.random.default_rng(2000 + 13 * rep))
            if extra is not None:
                m.enable_dav_fit(float(extra.min()), float(extra.max()))
            t0 = time.time()
            # P9：固定 MH 時，把該維的搜尋軸換成單一值。用替換座標軸而不是
            # 收窄 bounds 的原因：bounds 只擋先驗，多階段精修仍會在該維
            # 產生格點；換成單元素陣列才能真正讓它不動，且 multi_stage_best
            # 對 len(ax) < 2 的維度會直接沿用、不做精修。
            axes = list(COARSE)
            if args.fix_mh is not None:
                axes[4] = np.array([args.fix_mh])
            # dav（索引 6）不可辨識、貼牆是預期行為；其餘維度貼牆直接報錯，
            # 因為這支程式產出的是要寫進論文的數字。
            best, lp, bounds = multi_stage_best(
                m, axes, refines, n_proc, extra_axis=extra, allow_wall=allow)
            names = joint_fit.PARAM_NAMES + (["dav"] if extra is not None
                                             else [])
            # 放行的維度仍要標示出來，否則「允許」會變成「看不見」
            from injection_recovery import check_walls
            noted = check_walls(best, bounds, names)
            if noted:
                print("  [注意] " + "；".join(t for _, t in noted), flush=True)
            tag = f" 第 {rep+1} 次" if args.repeats > 1 else ""
            print(f"{'參數':<10}{'最佳值' + tag:>12}")
            for i, nm in enumerate(names):
                print(f"{nm:<10}{best[i]:>12.3f}")
            print(f"lnP = {lp:.1f}   年齡 {10**best[0]/1e6:.1f} Myr"
                  f"   ({time.time()-t0:.0f}s)\n", flush=True)
            reps.append(best)
        arr = np.array(reps)
        out[key] = arr
        if args.repeats > 1:
            print(f"{key} 跨 {args.repeats} 次：alpha 平均 {arr[:,3].mean():.3f}"
                  f"、散布 {arr[:,3].std():.3f}"
                  f"（{'  '.join(f'{v:.3f}' for v in arr[:,3])}）\n", flush=True)

    print(f"{'='*74}\nalpha 隨模型設定的變化\n{'='*74}")
    print(f"{'設定':<6}{'說明':<34}{'alpha 平均':>11}{'散布':>8}{'相對 A':>10}")
    a0 = out["A"][:, 3].mean() if "A" in out else np.nan
    for key in out:
        a = out[key][:, 3]
        print(f"{key:<6}{CONFIGS[key][0]:<34}{a.mean():>11.3f}"
              f"{a.std():>8.3f}{a.mean()-a0:>+10.3f}")
    if "A" in out and "C" in out and args.repeats > 1:
        # 位移要與重現性比較才有意義。兩組各自的散布合併成位移的標準誤。
        na, nc = len(out["A"]), len(out["C"])
        se = np.sqrt(out["A"][:, 3].var(ddof=1) / na
                     + out["C"][:, 3].var(ddof=1) / nc)
        d = out["C"][:, 3].mean() - a0
        print(f"\nA -> C 的 alpha 位移 = {d:+.3f} ± {se:.3f}（標準誤）"
              f" = {abs(d)/se if se > 0 else np.inf:.1f} 倍標準誤")
        print("判讀：位移要明顯大於標準誤，才能說模型修正真的改變了 alpha。")
    if "C" in out and "D" in out:
        print(f"\ndav 上界從 0.6 放到 1.2："
              f"dav {out['C'][:,6].mean():.3f} -> {out['D'][:,6].mean():.3f}，"
              f"alpha {out['C'][:,3].mean():.3f} -> {out['D'][:,3].mean():.3f}")

    np.savez(HERE / "results" / f"fit_real{args.tag}.npz",
             **{k: v for k, v in out.items()})
    print("\n寫入 results/fit_real.npz")


if __name__ == "__main__":
    main()
