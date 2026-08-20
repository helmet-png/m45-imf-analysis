# -*- coding: utf-8 -*-
"""P6：輪廓測試低質量段冪次（0.08-0.5 Msun，佔樣本 59.5%）。

**動機**：`alpha` 這個自由參數只改 Kroupa 分段冪律裡 m>0.5 Msun 那一段。
0.08-0.5 Msun 那段固定在 -1.3、從未參與擬合。實測 M45 的 1,078 顆成員星裡
有 641 顆（59.5%）落在這個固定段。Hess 圖概似是整張圖一起算的，
這 641 顆星在推動包括 alpha 在內的所有參數 —— 若 1.3 對 M45 不對，
模型會用其他參數去補償，alpha 可能被系統性拖偏卻看起來很精確。

這與「以 M45 金屬量接近太陽為由固定金屬量」是同一類錯誤，
那次的輪廓測試顯示代價是 alpha 偏 0.40（統計誤差的 133 倍）。
低質量段冪次至今沒做過同樣的檢查。

**用修好的模型（config C：選擇函數 + 差異消光），不是舊六參數版** ——
論文要報的數字來自 C，用舊模型測敏感度答非所問。

**判讀基準**：用注入回收量到的 alpha 統計誤差 0.144（見
injection_recovery.py 的 S3F，最乾淨的一次）。若固定低質量段冪次
造成的 alpha 跨度遠大於 0.144，代表它跟金屬量一樣必須升格。
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

# 統計誤差的比較基準，來自注入回收（S3F，config C 對應的情境）。
ALPHA_STAT_SIGMA = 0.144

# Kroupa (2001) 原文對 0.08-0.5 Msun 段冪次的估計本身帶不確定度
# （約 1.3 +- 0.3~0.5，依版本而定）。掃過這個量級的範圍。
SLOPES = [0.9, 1.1, 1.3, 1.5, 1.7]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--repeats", type=int, default=3,
                    help="每個冪次值重複幾次（換模型端共用亂數，量重現性）")
    ap.add_argument("--refines", default="3",
                    help="精修階數，逗號分隔。3,3 較精確但貴一倍")
    ap.add_argument("--dav-max", type=float, default=0.6)
    ap.add_argument("--slopes", default=None,
                    help="逗號分隔，覆寫預設的 SLOPES 掃描點。"
                         "本機已掃過 0.9-1.7，要擴大範圍時用這個而不改本檔，"
                         "避免正在跑的背景工作看到不一致的模組狀態")
    # 2026-08-20：開跑前檢查（見 scripts/tools/preflight.py、
    # docs/reference/PREFLIGHT.md）——這支腳本沒有續傳機制，本機曾經因為
    # Windows 非預期重開機連續四天從頭重算一次都沒完成，確保設定沒錯
    # 比 fit_real.py 更要緊，不是次要功能。
    ap.add_argument("--preflight", action="store_true",
                    help="只做開跑前檢查然後結束，不進行任何擬合")
    ap.add_argument("--force", action="store_true",
                    help="略過開跑前檢查的阻擋（不建議，僅供已知情況使用）")
    args = ap.parse_args()
    n_proc = args.procs or (os.cpu_count() or 1)
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    slopes = ([float(x) for x in args.slopes.split(",")] if args.slopes
             else SLOPES)

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

    # 2026-08-20：B3（續傳）—— 這支腳本原本只在全部掃描點跑完後 np.savez
    # 一次，中途被砍（p6_lowmass_v2 案例：本機四天內被 Windows 強制重開機
    # 四次）就得從頭重算，即使前面已經跑完的冪次本身沒有問題。改用
    # scripts/tools/checkpoint.py 的共用續傳機制，跟 fit_real.py 同一套。
    out_path = HERE / "results" / "profile_lowmass.npz"
    # slopes 不放進 manifest：這支腳本沒有 --tag（輸出檔名固定），若把
    # 掃描點清單也拿去比對，擴大 --slopes 範圍就會被 check_manifest()
    # 判定成「設定不同」而 sys.exit(1)，錯誤訊息還會叫使用者「換一個
    # --tag」——但這支腳本根本沒有這個旗標，使用者只能手動刪掉整個
    # 既有結果檔，前面已經跑完的掃描點全部作廢。每個掃描點各自有獨立
    # 的 scan_key（f"p{p}"），互不污染，不需要靠 manifest 擋這個
    # （2026-08-20 CodeRabbit review）。slopes 本身仍會透過下面迴圈裡
    # 的 extra_arrays 存進輸出檔，事後查得到這批掃過哪些點。
    manifest = {"n_syn": args.n_syn, "refines": args.refines,
                "dav_max": args.dav_max}
    sys.path.insert(0, str(HERE / "scripts" / "tools"))
    import checkpoint                                            # noqa: E402
    import preflight                                             # noqa: E402
    partial = checkpoint.load_partial(out_path)
    checkpoint.check_manifest(out_path, manifest, partial)

    # 開跑前檢查——無條件執行，不是選用步驟（見 scripts/tools/
    # preflight.py 的 mandatory_gate() 說明）。mh_prior_sigma=0.0 是這支
    # 腳本刻意的行為（先驗會污染要測的低質量段冪次敏感度），登記進
    # expected_overrides 避免每次都誤報成阻擋。
    if args.preflight:
        preflight._force_utf8_stdout()
    scan_keys = [f"p{p}" for p in slopes]
    partial_counts = {k: len(partial.get(k, [])) for k in scan_keys}
    w_fails, w_warns = preflight.workload_audit(
        scan_keys=scan_keys, repeats=args.repeats, n_syn=args.n_syn,
        n_obs=n_obs, refines=refines, partial_counts=partial_counts,
        unit="次重複", scan_label="低質量段冪次（--slopes）")
    preflight.output_audit(out_path, partial)
    preflight.mandatory_gate(
        base, grid, refines, script="profile_lowmass.py",
        expected_overrides={"mh_prior_sigma": 0.0},
        force=args.force, dry_run=args.preflight,
        extra_fails=w_fails, extra_warns=w_warns)

    sel = selmod.load(HERE / "data" / "selection.npz")
    print(f"真實觀測 {n_obs:,} 顆，config C（選擇函數 + 差異消光），"
          f"n_synthetic {args.n_syn:,}")
    print(f"掃描低質量段冪次：{slopes}\n")

    from pipeline.step3_age import draw_randoms
    results = {}
    for p in slopes:
        key = f"p{p}"
        outs = list(partial.get(key, []))
        for rep in range(args.repeats):
            if rep < len(outs):
                print(f"  p={p:.1f} 第{rep+1}次：沿用既有結果，跳過重算",
                      flush=True)
                continue
            import copy
            m = copy.copy(base)
            m.obs_h = joint_fit.hess(color, mag, base.nb_c, base.nb_m,
                                     base.crange, base.mrange)
            m.n_obs = n_obs
            m.selection = sel
            m.bounds = base.bounds[:6].copy()
            m.low_mass_slope = -p
            if args.repeats > 1:
                m.draws = draw_randoms(m.n_syn,
                                       np.random.default_rng(3000 + 13 * rep))
            extra = np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 4)
            m.enable_dav_fit(0.0, args.dav_max)

            t0 = time.time()
            # q_gamma（5）與 dav（6）是已知的 nuisance，貼牆放行；
            # 其餘任何一維貼牆都要中止 —— 若低質量段冪次的改變讓 alpha
            # 或 A_V 撞到牆，那本身就是重要的診斷結果。
            best, lp, bounds = multi_stage_best(
                m, COARSE, refines, n_proc, extra_axis=extra,
                allow_wall=(5, 6))
            outs.append(best)
            print(f"  p={p:.1f} 第{rep+1}次  alpha={best[3]:.3f}  "
                  f"A_V={best[1]:.3f}  logage={best[0]:.3f}  "
                  f"lnP={lp:.1f}  ({time.time()-t0:.0f}s)", flush=True)
            # 跑完一次重複就存一次，不等全部冪次或全部重複都跑完——中途
            # 被砍，已經算完的每一次重複都保得住，重跑時讀回來跳過。
            outs = checkpoint.save_progress(
                out_path, key, outs, manifest,
                extra_arrays={"slopes": np.array(slopes)})
        arr = np.array(outs)
        results[p] = arr
        print(f"  -> p={p:.1f} 跨 {args.repeats} 次：alpha 平均 "
              f"{arr[:,3].mean():.3f}，散布 {arr[:,3].std():.3f}\n",
              flush=True)

    print(f"{'='*70}\nalpha 對低質量段冪次的敏感度\n{'='*70}")
    print(f"{'冪次 p':>8}{'alpha 平均':>11}{'散布':>8}")
    means = []
    for p in slopes:
        a = results[p][:, 3]
        means.append(a.mean())
        print(f"{p:>8.1f}{a.mean():>11.3f}{a.std():>8.3f}")
    means = np.array(means)
    span = float(means.max() - means.min())
    print(f"\nalpha 跨度（掃過 p={min(slopes)}-{max(slopes)}）= {span:.3f}")
    print(f"對照注入回收統計誤差 {ALPHA_STAT_SIGMA:.3f} "
          f"-> {span/ALPHA_STAT_SIGMA:.1f} 倍")
    print("\n判讀：倍數遠大於 1，代表固定低質量段冪次會系統性污染 alpha，")
    print("      必須升格為自由參數或至少在論文列為系統誤差項；")
    print("      倍數接近或小於 1，代表目前的固定值不是主要誤差來源。")

    # 每一次重複跑完就已經存過檔了（見上面迴圈裡的 checkpoint.save_progress()），
    # 這裡不用再存一次，只是印出最終確認訊息。
    print(f"\n已寫入 {out_path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
