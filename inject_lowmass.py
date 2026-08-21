# -*- coding: utf-8 -*-
"""P6b 第二步：低質量段冪次可不可辨識？（升格為自由參數的通行閘）

**為什麼一定要先做這個**：dav（差異消光）的教訓是「參數可以放進模型，
卻完全不被資料約束，只會貼著先驗邊界跑」—— 給多少範圍它就吃多少，
加大 n_synthetic 也沒用。若低質量段冪次也是這樣，升格只會多一個
不可解讀的 nuisance，不會縮小 alpha 的系統誤差 0.248。

**判讀標準（事前訂好，避免事後挑指標）**：
  1. 回收值要接近注入的真值（偏差 < 0.3，約為 Kroupa 誤差 0.5 的一半）
  2. **不能貼牆**（範圍 0.3-2.3，貼牆代表答案被邊界決定）
  3. 回收值要**隨注入的真值改變**（注入 0.9 與注入 1.7 要能分辨出來）——
     這是可辨識性最直接的定義，dav 就是敗在這一項
  4. alpha 的回收偏差不能因為多這一維而變糟（散布可以略增，偏差不行）

三個條件都過才升格；任何一項不過就退回文獻先驗，並把 0.248 誠實
列為系統誤差。

假資料一律用**與擬合模型不同的亂數種子**（見 injection_recovery.py 檔頭），
否則在真值處等於拿合成星團跟自己比，回收率必定 100%。
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
from pipeline.step3_age import draw_randoms                   # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import (COARSE, THETA_TRUE, CornerError,  # noqa: E402
                                WallError, make_fake, multi_stage_best)

# 注入的低質量段冪次真值。涵蓋 Kroupa 1.3+-0.5 的範圍兩端與中心。
P_TRUE_LIST = [0.9, 1.3, 1.7]
P_MIN, P_MAX = 0.3, 2.3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--trials", type=int, default=2)
    ap.add_argument("--trial-offset", type=int, default=0,
                    help="試驗次數的起始索引偏移（假資料種子 = 7000+37*(t+offset)，"
                         "擬合種子 = 4000+11*(t+offset)）。只吃單一整數，不接受逗號"
                         "清單。用來把同一組 --trials N 拆到不同機器/帳號各跑一部分："
                         "3 個帳號各跑一次時，是各自下 --trials 1 --trial-offset 0 / "
                         "1 / 2 三道獨立指令。**每個分片必須配一個唯一的 --tag**"
                         "（例如 _p6b_v2_t0 / _t1 / _t2）——輸出路徑只由 --tag 決定，"
                         "共用同一個 --tag 的分片會互相覆寫，"
                         "scripts/tools/checkpoint.py 的存檔機制不會幫忙"
                         "合併。全部跑完後把各檔案依 offset 由小到大沿 axis=0 串接，"
                         "即等於一次跑完。預設 0，不影響既有行為（比照 fit_real.py 的"
                         "--repeat-offset，見 PR #55）")
    ap.add_argument("--refines", default="3")
    ap.add_argument("--dav-max", type=float, default=0.6)
    ap.add_argument("--tag", default="", help="輸出檔名後綴，避免覆蓋前一次跑的"
                     "完整參數向量（見 LIMITATIONS.md D6：p6b/p6b2/p6b3 的中間"
                     "結果曾經因為固定檔名被後續跑覆寫，永久遺失）")
    ap.add_argument("--only", type=float, default=None,
                    help="只測 P_TRUE_LIST 裡的其中一個真值（例如 1.3），"
                         "不是全部三個都跑。用於補測單一可疑結果，不用重跑"
                         "整批（見 LIMITATIONS.md D5）")
    # 2026-08-20：開跑前檢查（見 scripts/tools/preflight.py）。
    ap.add_argument("--preflight", action="store_true",
                    help="只做開跑前檢查然後結束，不進行任何擬合")
    ap.add_argument("--force", action="store_true",
                    help="略過開跑前檢查的阻擋（不建議，僅供已知情況使用）")
    args = ap.parse_args()
    if args.trial_offset < 0:
        ap.error("--trial-offset must be non-negative")
    p_true_list = P_TRUE_LIST
    if args.only is not None:
        if args.only not in P_TRUE_LIST:
            ap.error(f"--only {args.only} 不在 P_TRUE_LIST={P_TRUE_LIST} 裡")
        p_true_list = [args.only]
    # --tag 只能是檔名後綴，不能是路徑（CodeRabbit 2026-08-13 抓到：不擋的話
    # --tag "/../../tmp/x" 能把輸出導到 results/ 之外，覆寫任意 .npz）。
    if "/" in args.tag or "\\" in args.tag:
        ap.error("--tag 只能包含檔名後綴字元，不能包含路徑分隔符")
    out_path = HERE / "results" / f"inject_lowmass{args.tag}.npz"
    n_proc = args.procs or (os.cpu_count() or 1)
    refines = [int(x) for x in args.refines.split(",") if x.strip()]

    cfg = cfgmod.load()
    c3 = cfg.step3_age
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

    # 2026-08-20：B3（續傳）—— 這支腳本原本每跑完一個 p_true 才存一次，
    # 但重啟時不會讀回既有進度，一樣會重算已經跑完的 p_true。改用
    # checkpoint.py，顆粒度細到「每一次試驗」（不是每個 p_true），且用
    # attempted 計數區分「已嘗試」跟「已成功」——貼牆例外會跳過某次試驗
    # 不計入結果，但那個試驗索引真的跑過一次，續傳時不該重跑
    # （見 scripts/tools/checkpoint.py 的 load_progress() 說明）。
    manifest = {"n_syn": args.n_syn, "refines": args.refines,
                "dav_max": args.dav_max, "trial_offset": args.trial_offset}
    # **p_true_list 不放進 manifest**（2026-08-21 CodeRabbit review）：
    # --only 的用途正是「補測單一可疑真值、不重跑整批」。若把掃描點清單
    # 也拿去比對，先跑完整批（[0.9,1.3,1.7]）再用同一個 --tag 下
    # --only 1.3，manifest 會變成 [1.3]，check_manifest() 判定設定不同
    # 直接 sys.exit(1)——把這個旗標的用途整個擋掉。每個真值各自有獨立的
    # scan_key（f"p{p}"），互不污染，不需要靠 manifest 擋。
    # 跟 profile_lowmass.py 的 slopes、profile_outlierfrac.py 的 fracs
    # 同一個理由、同一個處置。
    sys.path.insert(0, str(HERE / "scripts" / "tools"))
    import checkpoint                                            # noqa: E402
    import preflight                                             # noqa: E402
    partial = checkpoint.load_partial(out_path)
    checkpoint.check_manifest(out_path, manifest, partial)

    if args.preflight:
        preflight._force_utf8_stdout()
    scan_keys = [f"p{p}" for p in p_true_list]
    partial_counts = {}
    for p in p_true_list:
        _, att = checkpoint.load_progress(partial, f"p{p}")
        partial_counts[f"p{p}"] = att
    w_fails, w_warns = preflight.workload_audit(
        scan_keys=scan_keys, repeats=args.trials, n_syn=args.n_syn,
        n_obs=n_obs, refines=refines, partial_counts=partial_counts,
        unit="次試驗", scan_label="注入真值（P_TRUE_LIST／--only）")
    preflight.output_audit(out_path, partial)
    preflight.mandatory_gate(
        base, grid, refines, script="inject_lowmass.py",
        expected_overrides={"mh_prior_sigma": 0.0},
        force=args.force, dry_run=args.preflight,
        extra_fails=w_fails, extra_warns=w_warns)

    sel = selmod.load(HERE / "data" / "selection.npz")

    dav_true = 0.30
    print(f"assumed n_obs={n_obs}, alpha_true={THETA_TRUE[3]}, "
          f"dav_true={dav_true}")
    print(f"injecting p_lowmass = {p_true_list}, "
          f"fit range {P_MIN}-{P_MAX}\n", flush=True)

    # 八維全掃會爆炸（粗掃 240 萬點、精修 7^8 = 576 萬點），必須收窄。
    # 收窄的是**已經在先前所有擬合中穩定收斂**的維度，不是隨便砍：
    #   q_gamma 實測不受資料約束、對 alpha 影響小，固定在歷次中位 -0.7
    # alpha 與 f_bin 維持全範圍 —— 它們是要測的量與主要簡併對象，
    # 收窄它們等於預設答案。
    #
    # **logage 與 MH 曾被我收窄，第一次跑就被貼牆偵測攔下（2026-08-09）**：
    # 我以「歷次結果都落在 8.00-8.20」為由把 logage 上界設成 8.20，
    # 但歷次最佳解本來就常落在 8.100-8.200，等於把答案頂在自己設的牆上。
    # 這正是 LIMITATIONS 記錄過五次的同一個錯誤 —— 用「過去的結果」去
    # 收窄「這次的搜尋範圍」，本質上是拿結論當前提。
    # 已改回 COARSE 的完整範圍：省時間不能用犧牲搜尋範圍來換。
    coarse = [
        COARSE[0],                          # logage 全範圍（曾收窄致貼牆）
        COARSE[1],                          # A_V 全範圍（物理邊界要看得到）
        COARSE[2],                          # f_bin 全範圍
        COARSE[3],                          # alpha 全範圍（要測的量）
        COARSE[4],                          # MH 全範圍（曾收窄）
        np.array([-0.7]),                   # q_gamma（固定）
    ]
    dav_axis = np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 3)
    p_axis = np.arange(P_MIN, P_MAX + 1e-9, 0.4)
    n_pts = int(np.prod([len(a) for a in coarse])) * len(dav_axis) * len(p_axis)
    print(f"coarse grid = {n_pts:,} points "
          f"(~{n_pts*0.015/n_proc/60:.0f} min per fit)\n", flush=True)
    results = {}

    for p_true in p_true_list:
        key = f"p{p_true}"
        outs, attempted = checkpoint.load_progress(partial, key)
        # 截到 args.trials：磁碟已有的成功次數可能比這次要求的多（例如
        # 已有 3 筆、這次只下 --trials 2），不截斷的話下面迴圈會因為
        # t < attempted 全部跳過、outs 卻仍帶著 3 筆，最後的 p_rec／
        # alpha_rec 是用 3 筆算的，跟印出的 --trials 2 對不上
        # （2026-08-21 CodeRabbit review，同 profile_lowmass.py 的修正）。
        outs = outs[:args.trials]
        for t in range(args.trials):
            if t < attempted:
                print(f"  p_true={p_true:.1f} trial{t+1}：已嘗試過，跳過"
                      f"（不管當時成功或失敗，重跑只會用同一組亂數種子"
                      f"再得到同一個結果）", flush=True)
                continue
            # 生成假資料：注入指定的低質量段冪次
            gen = base.with_observations(color, mag)
            gen.selection = sel
            gen.low_mass_slope = -p_true
            fc, fm = make_fake(gen, THETA_TRUE, n_obs,
                               seed=7000 + 37 * (t + args.trial_offset),
                               dav=dav_true, selection=sel)

            # 擬合：八參數，低質量段冪次自由
            m = base.with_observations(fc, fm)
            m.selection = sel
            m.bounds = base.bounds[:6].copy()
            m.enable_dav_fit(0.0, args.dav_max)
            m.enable_lowmass_fit(P_MIN, P_MAX)
            m.draws = draw_randoms(
                m.n_syn,
                np.random.default_rng(4000 + 11 * (t + args.trial_offset)))
            t0 = time.time()
            # q_gamma(5) 與 dav(6) 是已知的 nuisance，貼牆放行；
            # p_lowmass(7) **不放行** —— 它貼牆正是我們要偵測的失敗模式。
            #
            # **單一次假資料撞牆不該毀掉整批結果**（2026-08-09 教訓：
            # 108 分鐘、6 筆已成功算出的試驗，因為第 7 筆撞到 A_V 角落解
            # 就被一起丟掉，因為例外沒被接住、np.savez 只在全部跑完後
            # 才執行一次）。跟 run_queue.py 對每個項目容錯是同一個原則，
            # 只是這裡的「項目」是單一次試驗。
            try:
                best, lp, bounds = multi_stage_best(
                    m, coarse, refines, n_proc,
                    extra_axis=[dav_axis, p_axis], allow_wall=(5, 6),
                    names=joint_fit.PARAM_NAMES + ["dav", "p_lowmass"])
            except (WallError, CornerError) as e:
                print(f"  p_true={p_true:.1f} trial{t+1} 失敗（跳過，"
                      f"不影響其餘試驗）：{type(e).__name__}: "
                      f"{str(e).splitlines()[1] if len(str(e).splitlines()) > 1 else e}",
                      flush=True)
                attempted = t + 1
                outs = checkpoint.save_progress(out_path, key, outs, manifest,
                                                attempted=attempted)
                continue
            outs.append(best)
            attempted = t + 1
            print(f"  p_true={p_true:.1f} trial{t+1}  "
                  f"p_rec={best[7]:.3f}  alpha={best[3]:.3f}  "
                  f"dav={best[6]:.3f}  lnP={lp:.1f}  "
                  f"({time.time()-t0:.0f}s)", flush=True)
            # 跑完一次試驗就存一次（不管成功或失敗），不等這個 p_true 的
            # 全部 trials 都跑完——中途被砍，已經算完的每一次試驗都保得住。
            outs = checkpoint.save_progress(out_path, key, outs, manifest,
                                            attempted=attempted)
        if not outs:
            print(f"  p_true={p_true:.1f} 全部 {args.trials} 次試驗都失敗，"
                  "略過（見上方各次的失敗原因）", flush=True)
            continue
        if len(outs) < args.trials:
            print(f"  p_true={p_true:.1f}：{len(outs)}/{args.trials} 次成功，"
                  "其餘見上方失敗紀錄", flush=True)
        results[p_true] = np.array(outs)
        # 補記 p_true 摘要陣列（試驗層級的存檔在上面迴圈已經逐次做了，
        # 這裡只是把「目前有哪些 p_true 已經有成功結果」這個摘要寫回去，
        # 跟原本「每跑完一個 p_true 就存一次」同一個顆粒度）。
        outs = checkpoint.save_progress(
            out_path, key, outs, manifest, attempted=attempted,
            extra_arrays={"p_true": np.array(list(results.keys()))})

    print(f"\n{'='*70}")
    print("identifiability of low-mass slope")
    print(f"{'='*70}")
    print(f"{'p_true':>8}{'p_recovered':>14}{'bias':>9}"
          f"{'alpha_rec':>11}{'alpha_bias':>11}")
    p_recs, p_true_ok = [], []
    for p_true in p_true_list:
        if p_true not in results:
            print(f"{p_true:>8.1f}  (全部試驗失敗，無資料)")
            continue
        a = results[p_true]
        p_rec, al = a[:, 7].mean(), a[:, 3].mean()
        p_recs.append(p_rec)
        p_true_ok.append(p_true)
        print(f"{p_true:>8.1f}{p_rec:>14.3f}{p_rec-p_true:>+9.3f}"
              f"{al:>11.3f}{al-THETA_TRUE[3]:>+11.3f}")

    if len(p_recs) < 2:
        print("\n少於兩個 p_true 有成功資料，無法判斷可辨識性（條件 3 需要"
              "跨多個真值比較），僅供參考個別數字。")
        # 每一次試驗跑完就已經存過檔了（見上面迴圈裡的
        # checkpoint.save_progress()），這裡不用再存一次。
        return

    p_recs = np.array(p_recs)
    # 用 p_true_ok（實際成功的真值）而不是覆寫 P_TRUE_LIST ——
    # 在函式裡對一個跟模組層級同名的變數賦值，Python 會把它當成整個函式的
    # 區域變數，導致函式**開頭**引用模組常數的那行也讀到未賦值的區域變數
    # （UnboundLocalError，2026-08-09 實測踩到，讓 p6b3 跑 9 秒就死）。
    spread = p_recs.max() - p_recs.min()
    inj_spread = max(p_true_ok) - min(p_true_ok)
    print(f"\ncriterion 3 (does recovery track truth?):")
    print(f"  injected spread {inj_spread:.2f} -> recovered spread "
          f"{spread:.2f}  (ratio {spread/inj_spread:.2f})")
    print("  ratio near 1 = identifiable; near 0 = unconstrained "
          "(recovers same value regardless of truth)")

    # 每一次試驗跑完就已經存過檔了（見上面迴圈裡的
    # checkpoint.save_progress()），這裡不用再存一次，只是印出最終確認訊息。
    print(f"\nwrote {out_path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
