# -*- coding: utf-8 -*-
"""D14 衍生（`mass_dependent_fbin`）：雙星比例隨質量變化，會把 alpha 推歪多少？

見 `WORK_BOARD.md`「對照 Hobart et al. 2026 的鞏固工作」表的
`mass_dependent_fbin` 條目、`LIMITATIONS.md` D14。

**問題**：`pipeline/joint_fit.py` 的 `synthesise()` 裡決定「誰帶伴星」的
Bernoulli(`f_bin`) 跟主星質量 `m1` **完全獨立**，等於假設雙星比例不隨質量
變化。這是已知簡化但從沒量化過代價（Torres+2025 對 Pleiades 觀測到雙星
比例隨半徑呈雙峰，質量相依性同樣沒理由預設為常數）。

**做法**（比照 `inject_lowmass.py`，注入回收，不直接升格成自由參數——
dav 的教訓是「參數可以放進模型卻完全不被資料約束」）：
  1. 生成端呼叫 `set_mass_dependent_fbin(contrast)`，讓假資料帶有
     「重星段與輕星段 f_bin 相差 contrast」的質量相依性
  2. 擬合端用**現有的常數 f_bin 六參數模型**（完全不改）
  3. 比較回收到的 alpha 與注入真值，量偏移

**整體雙星比例在所有 contrast 下都固定**（見 `set_mass_dependent_fbin()`
的說明）：兩段的 f_bin 由樣本比例加權後恰好等於名目 f_bin。這樣才是
只動「質量相依性」這一個變因；若只把某一段調高，整體雙星比例會跟著變，
量到的 alpha 偏移就分不清是哪一個造成的。

**驗收標準（WORK_BOARD）**：給出「雙星比例質量相依性的強度 vs alpha
偏移」的具體數字；若偏移遠小於統計誤差 0.144 就記為可忽略並結案，
不必升格成自由參數。

用法（比照 inject_lowmass.py，可用 --trial-offset 拆片跑在 Kaggle）：
  python inject_massdep_fbin.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3
"""
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
from inject_lowmass import atomic_savez                       # noqa: E402

# 注入的質量相依強度（重星段 f_bin - 輕星段 f_bin）。
# 0.0 是對照組（沒有質量相依性）——**一定要留著**，它是判斷「偏移是
# 質量相依性造成的，還是這套注入回收本身的偏差地板」的唯一依據
# （C13 記錄的 alpha 偏差地板目前是 -0.050，跟這裡要測的量級接近）。
CONTRAST_LIST = [0.0, 0.15, 0.30]
M_BREAK = 0.5   # 跟 Kroupa 分段點、alpha 只控制 m>0.5 段一致


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--trial-offset", type=int, default=0,
                    help="試驗編號的起始偏移（種子 = 7000 + 37*(t+offset)）。"
                         "用來把同一批試驗拆到多台機器/多個 Kaggle 帳號跑，"
                         "比照 inject_lowmass.py 的同名旗標。")
    ap.add_argument("--refines", default="3,3")
    ap.add_argument("--dav-max", type=float, default=0.6)
    ap.add_argument("--m-break", type=float, default=M_BREAK)
    ap.add_argument("--tag", default="")
    ap.add_argument("--only", type=float, default=None,
                    help="只測 CONTRAST_LIST 裡的其中一個值")
    args = ap.parse_args()

    contrasts = CONTRAST_LIST
    if args.only is not None:
        if args.only not in CONTRAST_LIST:
            ap.error(f"--only {args.only} 不在 CONTRAST_LIST={CONTRAST_LIST} 裡")
        contrasts = [args.only]

    # --tag 只能是檔名後綴，不能是路徑（比照 inject_lowmass.py：不擋的話
    # --tag "/../../tmp/x" 能把輸出導到 results/ 之外、覆寫任意 .npz）
    if "/" in args.tag or "\\" in args.tag:
        ap.error("--tag 只能包含檔名後綴字元，不能包含路徑分隔符")
    # **檔名要帶 trial_offset**（2026-08-21 CodeRabbit review）：每個分片
    # 都從空的 results 開始跑，存檔時是整份覆寫。若兩個 --trial-offset
    # 共用同一個檔名，後跑完的分片會用「只含自己那幾次試驗」的內容蓋掉
    # 前一個分片，--trial-offset 這個拆分機制等於無聲失效。帶上 offset
    # 之後各分片天然分開，跑完再串接。offset=0 時維持原檔名，不影響
    # 既有單機一次跑完的用法。
    _off_sfx = f"_t{args.trial_offset}" if args.trial_offset else ""
    out_path = (HERE / "results"
                / f"inject_massdep_fbin{args.tag}{_off_sfx}.npz")
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
    sel = selmod.load(HERE / "data" / "selection.npz")

    dav_true = 0.30
    fbin_true = THETA_TRUE[2]
    print(f"n_obs={n_obs}, alpha_true={THETA_TRUE[3]}, f_bin_true={fbin_true}, "
          f"dav_true={dav_true}")
    print(f"注入的質量相依強度 contrast = {contrasts}，分段質量 "
          f"{args.m_break} Msun")
    print("整體雙星比例在所有 contrast 下固定不變（只動質量相依性這一個變因）")
    print("擬合端用**現有的常數 f_bin 模型**（七參數：六參數 + dav）\n",
          flush=True)

    # 收窄方式與 inject_lowmass.py 一致：只固定實測不受資料約束、對 alpha
    # 影響小的 q_gamma；alpha 與 f_bin 保持全範圍——它們正是要測的量與
    # 主要簡併對象，收窄它們等於預設答案。logage/MH 也保持全範圍
    # （inject_lowmass.py 記錄過收窄它們會導致貼牆的教訓）。
    coarse = [
        COARSE[0],            # logage 全範圍
        COARSE[1],            # A_V 全範圍
        COARSE[2],            # f_bin 全範圍（主要簡併對象）
        COARSE[3],            # alpha 全範圍（要測的量）
        COARSE[4],            # MH 全範圍
        np.array([-0.7]),     # q_gamma（固定，實測不受資料約束）
    ]
    dav_axis = np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 3)
    results = {}
    trial_ids = {}          # 每個 contrast 實際成功的 trial id

    for contrast in contrasts:
        outs = []
        for t in range(args.trials):
            # 生成假資料：注入質量相依的雙星比例
            gen = base.with_observations(color, mag)
            gen.selection = sel
            gen.set_mass_dependent_fbin(contrast, m_break=args.m_break)
            fc, fm = make_fake(gen, THETA_TRUE, n_obs,
                               seed=7000 + 37 * (t + args.trial_offset),
                               dav=dav_true, selection=sel)

            # 擬合：現有的常數 f_bin 模型，**完全不知道質量相依性存在**
            m = base.with_observations(fc, fm)
            m.selection = sel
            m.bounds = base.bounds[:6].copy()
            m.enable_dav_fit(0.0, args.dav_max)
            m.draws = draw_randoms(
                m.n_syn,
                np.random.default_rng(4000 + 11 * (t + args.trial_offset)))
            t0 = time.time()
            # q_gamma(5) 與 dav(6) 是已知 nuisance，貼牆放行。
            # f_bin(2) **不放行**——注入質量相依性後常數模型可能被逼到
            # f_bin 邊界，那正是要偵測的失敗模式之一。
            # 單次試驗撞牆不該毀掉整批（inject_lowmass.py 的同一個教訓）。
            try:
                best, lp, bounds = multi_stage_best(
                    m, coarse, refines, n_proc,
                    extra_axis=[dav_axis], allow_wall=(5, 6),
                    names=joint_fit.PARAM_NAMES + ["dav"])
            except (WallError, CornerError) as e:
                print(f"  contrast={contrast:.2f} trial{t+1} 失敗（跳過，"
                      f"不影響其餘試驗）：{type(e).__name__}: {e}", flush=True)
                continue
            dt = time.time() - t0
            # 連 trial id 一起存（2026-08-21 CodeRabbit review）：撞牆的
            # 試驗會被跳過，各 contrast 成功的是哪幾次不見得一樣。下面算
            # 淨偏移是「contrast=X 減 contrast=0」，若兩邊用的是不同的
            # 試驗集合，扣掉的偏差地板就不是同一批假資料的地板。
            outs.append((t + args.trial_offset, best))
            print(f"  contrast={contrast:.2f} trial{t+1}/{args.trials}: "
                  f"alpha={best[3]:.3f}（真值 {THETA_TRUE[3]:.3f}，偏差 "
                  f"{best[3]-THETA_TRUE[3]:+.3f}）  f_bin={best[2]:.3f}"
                  f"（名目 {fbin_true:.3f}）  {dt/60:.1f} min", flush=True)

        if outs:
            key = f"contrast_{contrast:.2f}"
            results[key] = np.array([b for _, b in outs])
            trial_ids[key] = np.array([tid for tid, _ in outs], dtype=int)
            # 邊跑邊存：長跑到一半被中斷時，已算完的不該陪葬
            atomic_savez(out_path, contrast_list=np.array(contrasts),
                         m_break=args.m_break, theta_true=THETA_TRUE,
                         dav_true=dav_true, n_syn=args.n_syn,
                         trial_offset=args.trial_offset,
                         **results,
                         **{f"{k}__trials": v for k, v in trial_ids.items()})

    print(f"\n{'contrast':>10} {'n':>3} {'alpha 平均':>10} {'偏差':>8} "
          f"{'散布':>8} {'f_bin 平均':>10}")
    base_bias = None
    for contrast in contrasts:
        key = f"contrast_{contrast:.2f}"
        if key not in results:
            print(f"{contrast:10.2f}   0   （全部試驗都失敗）")
            continue
        arr = results[key]
        bias = arr[:, 3].mean() - THETA_TRUE[3]
        spread = arr[:, 3].std(ddof=1) if len(arr) > 1 else np.nan
        if contrast == 0.0:
            base_bias = bias
        print(f"{contrast:10.2f} {len(arr):3d} {arr[:,3].mean():10.3f} "
              f"{bias:+8.3f} {spread:8.3f} {arr[:,2].mean():10.3f}")

    # --- 完整性把關（2026-08-21 CodeRabbit review）---
    # 撞牆的試驗會被跳過，程式仍可能帶著不完整的 outs 正常結束、被
    # run_queue.py 記成 ok。但「淨偏移」是拿 contrast=X 減 contrast=0 的
    # 偏差地板，任何一邊不完整，扣出來的就不是原本要量的東西——尤其
    # contrast=0 若只跑成 1/3 次，地板本身只是單次雜訊。不完整時
    # **不下結論、且以非零碼結束**，讓佇列標成失敗而不是 ok。
    incomplete = []
    for contrast in contrasts:
        key = f"contrast_{contrast:.2f}"
        n_ok = len(results.get(key, []))
        if n_ok < args.trials:
            incomplete.append((contrast, n_ok))

    ALPHA_STAT_SIGMA = 0.144      # 注入回收量到的 alpha 統計誤差（S3F）
    if incomplete:
        print(f"\n**這批結果不完整，不下結論**（每個 contrast 都要跑滿 "
              f"{args.trials} 次）：")
        for contrast, n_ok in incomplete:
            print(f"  contrast={contrast:.2f}: 只成功 {n_ok}/{args.trials} 次")
        print("  撞牆而被跳過的試驗見上方各次的失敗訊息。補跑缺的試驗"
              "（或放寬對應維度的搜尋範圍再跑）之後才能判讀。")
        print(f"\n寫入 {out_path}")
        sys.exit(1)

    if base_bias is None:
        print(f"\n**沒有 contrast=0 對照組**，無法扣掉偏差地板"
              "（C13 記錄目前 alpha 偏差地板約 -0.050，跟要測的量級接近），"
              "這批數字不能單獨判讀。")
        print(f"\n寫入 {out_path}")
        sys.exit(1)

    # --- 淨偏移只用兩邊都成功的 trial id（2026-08-21 CodeRabbit review）---
    base_key = "contrast_0.00"
    base_ids = trial_ids.get(base_key, np.array([], dtype=int))
    print(f"\n**扣掉 contrast=0 對照組的偏差地板之後**"
          "（只用兩邊都成功的試驗配對相減）：")
    verdicts = []
    for contrast in contrasts:
        key = f"contrast_{contrast:.2f}"
        if contrast == 0.0 or key not in results:
            continue
        ids = trial_ids.get(key, np.array([], dtype=int))
        common = np.intersect1d(base_ids, ids)
        if len(common) == 0:
            print(f"  contrast={contrast:.2f}: 與對照組沒有共同成功的試驗，"
                  "無法配對相減")
            verdicts.append((contrast, None))
            continue
        bi = {t: i for i, t in enumerate(base_ids)}
        ci = {t: i for i, t in enumerate(ids)}
        b_al = np.array([results[base_key][bi[t], 3] for t in common])
        c_al = np.array([results[key][ci[t], 3] for t in common])
        net = float((c_al - b_al).mean())
        print(f"  contrast={contrast:.2f}: 淨 alpha 偏移 {net:+.3f}"
              f"（統計誤差 {ALPHA_STAT_SIGMA} 的 "
              f"{abs(net)/ALPHA_STAT_SIGMA:.2f} 倍；配對 "
              f"{len(common)}/{args.trials} 次，trial id {common.tolist()}）")
        verdicts.append((contrast, net))

    # --- 結論只在真的通過門檻時才下（2026-08-21 CodeRabbit review）---
    # 原本那兩行不看任何 net 值就印「可忽略並結案」，淨偏移再大也照印。
    usable = [(c, n) for c, n in verdicts if n is not None]
    unpaired = [c for c, n in verdicts if n is None]
    over = [(c, n) for c, n in usable if abs(n) >= ALPHA_STAT_SIGMA]
    print()
    if unpaired:
        print(f"**無法判讀**：contrast={unpaired} 與對照組沒有共同成功的"
              "試驗，配對相減做不出來，這幾個 contrast 要補跑。")
    elif not usable:
        print("**無法判讀**：沒有任何可用的 contrast 淨偏移。")
    elif over:
        print("**未通過驗收門檻**：contrast="
              f"{[c for c, _ in over]} 的淨 alpha 偏移絕對值達到或超過統計"
              f"誤差 {ALPHA_STAT_SIGMA}（"
              + "、".join(f"{c:.2f}->{n:+.3f}" for c, n in over) + "）。"
              "**不能結案**——質量相依 f_bin 對 alpha 的影響不可忽略，要進一步"
              "分析（升格成自由參數、或列為系統誤差項）。")
    else:
        worst = max(abs(n) for _, n in usable)
        print("**通過驗收門檻**：所有 contrast 的淨 alpha 偏移絕對值都小於"
              f"統計誤差 {ALPHA_STAT_SIGMA}（最大 {worst:.3f}），依 "
              "WORK_BOARD 驗收標準記為可忽略並結案，不必把質量相依 f_bin "
              "升格成自由參數。")

    print(f"\n寫入 {out_path}")


if __name__ == "__main__":
    main()
