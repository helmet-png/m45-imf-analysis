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

======================================================================
【這支程式在做什麼】
======================================================================
「輪廓／敏感度掃描」：把一個平常固定不動的參數（低質量段冪次 p，預設 1.3）
依序固定在 0.9、1.1、1.3、1.5、1.7，每個值都用前向模型（config C）重新完整
擬合一次，看 α 跟著變多少。α 變得越多，代表「把 p 固定在 1.3」這個假設對
α 的影響越大。
執行方式：python profile_lowmass.py [--refines 3,3,3] [--repeats 3]
輸出：results/profile_lowmass<tag>.npz（每個 p、每次重複的最佳參數）
⚠ 這支程式只印出「α 的跨度」與「跨度是統計誤差 0.144 的幾倍」。
  LIMITATIONS.md A3 引用的斜率 dα/dp = −0.495 ± 0.111 與系統誤差 0.248
  （= 0.495 × Kroupa 給的 p 不確定度 0.5）是由這裡的結果另外算出的。
⚠ 產生 0.248 的那次執行（p6_lowmass）是在精修 bug 修好前跑的，等於完全沒有
  精修（α 只落在 0.20 間距的粗格點上），LIMITATIONS.md A1／A3 標為
  「待重跑確認、精確值不可引用」。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, os, sys, time, pathlib   參數、CPU 數、路徑、計時
  copy（在迴圈裡 import）           淺複製模型
第三方套件：
  numpy（np）   陣列運算、存讀檔
本專案其他模組：
  pipeline/config.py, isochrones.py, selection.py, table_compat.py
                         讀設定、等時線、選擇函數、成員表
  pipeline/joint_fit.py  JointModel：前向模型；本程式改它的 low_mass_slope 屬性
  pipeline/step3_age.py  draw_randoms()：每次重複換一批模型端亂數
  measure_overconfidence.py  GRID：網格檔名
  injection_recovery.py  COARSE（粗網格軸）、multi_stage_best()（多階段網格搜尋，
                         見 fit_real.py 檔頭）
  scripts/tools/checkpoint.py  續傳（每算完一次就存檔）
  scripts/tools/preflight.py   開跑前檢查

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --procs        平行行程數
  --n-syn (40000)  合成星數
  --repeats (3)  每個 p 值重複幾次（每次換模型端亂數，量重現性）
  --refines (3)  精修輪數與倍數；要可信的數字需要 3,3,3
  --dav-max (0.6)  差異消光 dav 的搜尋上限（等同 config C）
  --tag          輸出檔名後綴
  --slopes       覆寫掃描點，逗號分隔
  --preflight／--force   開跑前檢查
模組常數：
  ALPHA_STAT_SIGMA = 0.144   注入回收量出的 α 統計誤差，當比較基準
  SLOPES = [0.9, 1.1, 1.3, 1.5, 1.7]   掃描點；涵蓋 Kroupa (2001) 1.3 ± 0.3～0.5
刻意的設定：金屬量改用均勻先驗（mh_prior_sigma = 0），避免先驗干擾要測的敏感度

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 168–190 行｜讀資料、建立前向模型
  核心 2｜第 247–303 行｜主迴圈：每個 p × 每次重複，固定 p 後做一次完整擬合
  核心 3｜第 305–325 行｜整理：每個 p 的 α 平均、跨度、跨度是統計誤差的幾倍

======================================================================
【(d) 整體流程】
======================================================================
  讀 cmd_members.csv、誤差模型、網格 → 算距離模數 → 建前向模型
    → 續傳檢查＋開跑前檢查
    → 對每個 p（0.9…1.7）、每次重複：
        複製模型 → 掛選擇函數 → low_mass_slope = −p（固定，不擬合）
        → 換一批模型端亂數 → 加上 dav 維度
        → multi_stage_best（跟頭條同一套網格搜尋，q_gamma 與 dav 允許貼牆）
        → 存檔
    → 印出每個 p 的 α 平均與散布
    → 跨度 = 最大平均 − 最小平均；印出跨度 ÷ 0.144
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
    # --tag（2026-08-21，對應 LIMITATIONS.md D6）：這兩支腳本原本輸出路徑
    # 寫死，是六支計算腳本裡最後兩支沒有 --tag 的——D6 記錄的「中間結果檔案
    # 會被重跑覆寫」在它們身上仍然成立。有了 --tag 才能讓不同設定（例如
    # 換一組 --slopes）的結果各存一份、事後可回溯比較，也才能在
    # check_manifest() 擋下無 manifest 舊檔時，真的給得出「換一個 --tag」
    # 這個選項。預設空字串＝維持原本檔名，既有呼叫端與既有結果檔不受影響。
    ap.add_argument("--tag", default="",
                    help="輸出檔名後綴，避免不同設定的結果互相覆寫"
                         "（見 LIMITATIONS.md D6）")
    ap.add_argument("--slopes", default=None,
                    help="逗號分隔，覆寫預設的 SLOPES 掃描點。"
                         "本機已掃過 0.9-1.7，要擴大範圍時用這個而不改本檔，"
                         "避免正在跑的背景工作看到不一致的模組狀態")
    # 2026-08-20：開跑前檢查（見 scripts/tools/preflight.py、
    # docs/reference/PREFLIGHT.md）——本機曾經因為 Windows 非預期重開機
    # 連續四天從頭重算一次都沒完成，確保設定沒錯比 fit_real.py 更要緊，
    # 不是次要功能。**續傳已在下面補上**（見 checkpoint.py 那段），這裡
    # 原本寫「這支腳本沒有續傳機制」已經過時，2026-08-21 訂正。
    ap.add_argument("--preflight", action="store_true",
                    help="只做開跑前檢查然後結束，不進行任何擬合")
    ap.add_argument("--force", action="store_true",
                    help="略過開跑前檢查的阻擋（不建議，僅供已知情況使用）")
    args = ap.parse_args()
    # --tag 只能是檔名後綴，不能是路徑（比照 fit_real.py／
    # inject_lowmass.py：不擋的話 --tag "/../../tmp/x" 能把輸出導到
    # results/ 之外、覆寫任意 .npz）。
    if "/" in args.tag or "\\" in args.tag:
        ap.error("--tag 只能包含檔名後綴字元，不能包含路徑分隔符")
    if args.repeats < 1:
        # --repeats 0（或負數）會讓 outs 被截成空 list（見下面
        # [:args.repeats] 那行），np.array([]) 是 shape (0,) 的一維陣列，
        # 後面 arr[:, 3] 直接丟 IndexError；且這段沒有被 --force 保護的
        # 條件包住，屬於結構性輸入錯誤（2026-08-20 CodeRabbit review）。
        ap.error("--repeats must be positive")
    n_proc = args.procs or (os.cpu_count() or 1)
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    slopes = ([float(x) for x in args.slopes.split(",")] if args.slopes
             else SLOPES)

    # ═══════════════ 核心 1：讀資料、建立前向模型 ═══════════════
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

    # ↓ 合成星數改成 --n-syn；金屬量改用均勻先驗（刻意，見檔頭 (b)）
    cfg._data["step3_age"]["n_synthetic"] = args.n_syn
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    base = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)

    # 2026-08-20：B3（續傳）—— 這支腳本原本只在全部掃描點跑完後 np.savez
    # 一次，中途被砍（p6_lowmass_v2 案例：本機四天內被 Windows 強制重開機
    # 四次）就得從頭重算，即使前面已經跑完的冪次本身沒有問題。改用
    # scripts/tools/checkpoint.py 的共用續傳機制，跟 fit_real.py 同一套。
    # ═══════════════ 輔助：續傳與開跑前檢查 ═══════════════
    out_path = HERE / "results" / f"profile_lowmass{args.tag}.npz"
    # slopes 不放進 manifest：每個掃描點各自有獨立的 scan_key
    # （f"p{p}"），互不污染，不需要靠 manifest 擋。這支腳本現在雖然有
    # --tag 了（2026-08-21），但「同一個 --tag、逐次擴大 --slopes」本來
    # 就是設計上允許的用法（跟 fit_real.py 的 --configs 同一個道理：
    # --configs 也不在 manifest 裡，允許同一個 --tag 逐次補跑不同設定）
    # ——manifest 管的是「同一批掃描點的參數是否一致」，不是「這次要掃
    # 哪些點」。slopes 本身透過下面迴圈的 extra_arrays 存進輸出檔，事後
    # 查得到這批掃過哪些點；**存的是磁碟既有加這次要求的聯集，不是只存
    # 這次的清單**（見下方「合併既有 slopes」），否則同一 --tag 分兩次
    # 跑不同 --slopes 時，後面那次的 extra_arrays 會覆寫掉 metadata，讓
    # 它跟檔案裡實際存在的 scan_key 對不上（2026-08-21 CodeRabbit review）。
    manifest = {"n_syn": args.n_syn, "refines": args.refines,
                "dav_max": args.dav_max}
    sys.path.insert(0, str(HERE / "scripts" / "tools"))
    import checkpoint                                            # noqa: E402
    import preflight                                             # noqa: E402
    partial = checkpoint.load_partial(out_path)
    # supports_tag=False：這支腳本的輸出路徑是寫死的、沒有 --tag，
    # 錯誤訊息不能建議「換一個 --tag」（2026-08-21 CodeRabbit review）。
    checkpoint.check_manifest(out_path, manifest, partial,
                              supports_tag=False)

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

    # 合併既有 slopes：磁碟上可能已經記過別次（同一 --tag、不同
    # --slopes）掃過的點，metadata 要反映「檔案裡實際有哪些 scan_key」，
    # 不能只反映「這次要求的清單」（2026-08-21 CodeRabbit review）。
    _existing_slopes = partial.get("slopes")
    all_slopes = sorted(set(slopes)
                        | (set(np.asarray(_existing_slopes).tolist())
                           if _existing_slopes is not None else set()))

    sel = selmod.load(HERE / "data" / "selection.npz")
    print(f"真實觀測 {n_obs:,} 顆，config C（選擇函數 + 差異消光），"
          f"n_synthetic {args.n_syn:,}")
    print(f"掃描低質量段冪次：{slopes}\n")

    # ═══════════════ 核心 2：主迴圈（每個 p × 每次重複） ═══════════════
    from pipeline.step3_age import draw_randoms
    results = {}
    for p in slopes:
        key = f"p{p}"
        # 截到 args.repeats：既有結果比這次要求的 --repeats 多時（例如
        # 磁碟上已有 3 次、這次只要 2 次），不截斷的話下面的迴圈會因為
        # rep < len(outs) 全部跳過、outs 卻仍帶著全部 3 筆，讓「跨 2 次」
        # 的平均/散布統計實際上是用 3 筆算出來的，跟印出來的次數對不上
        # （2026-08-20 CodeRabbit review）。不把 repeats 放進 manifest 就是
        # 為了讓「加大 --repeats」保持可續傳，這裡只是不讓「縮小
        # --repeats」意外地用了太多筆。
        outs = list(partial.get(key, []))[:args.repeats]
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
            # ↓ 關鍵的一行：把低質量段（0.08–0.5 M☉）冪次固定成 −p
            #   （存的是 dN/dm 的冪次，所以加負號）
            m.low_mass_slope = -p
            if args.repeats > 1:
                m.draws = draw_randoms(m.n_syn,
                                       np.random.default_rng(3000 + 13 * rep))
            # ↓ dav 的搜尋軸：0 到 dav_max 等分 4 段；並把 dav 加成第七個參數
            extra = np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 4)
            m.enable_dav_fit(0.0, args.dav_max)

            t0 = time.time()
            # q_gamma（5）與 dav（6）是已知的 nuisance，貼牆放行；
            # 其餘任何一維貼牆都要中止 —— 若低質量段冪次的改變讓 alpha
            # 或 A_V 撞到牆，那本身就是重要的診斷結果。
            best, lp, bounds = multi_stage_best(
                m, COARSE, refines, n_proc, extra_axis=extra,
                allow_wall=(5, 6))
            # ↓ best[3] 就是 alpha（第 0 欄是 logage）
            outs.append(best)
            print(f"  p={p:.1f} 第{rep+1}次  alpha={best[3]:.3f}  "
                  f"A_V={best[1]:.3f}  logage={best[0]:.3f}  "
                  f"lnP={lp:.1f}  ({time.time()-t0:.0f}s)", flush=True)
            # 跑完一次重複就存一次，不等全部冪次或全部重複都跑完——中途
            # 被砍，已經算完的每一次重複都保得住，重跑時讀回來跳過。
            outs = checkpoint.save_progress(
                out_path, key, outs, manifest,
                extra_arrays={"slopes": np.array(all_slopes)})
        arr = np.array(outs)
        results[p] = arr
        print(f"  -> p={p:.1f} 跨 {args.repeats} 次：alpha 平均 "
              f"{arr[:,3].mean():.3f}，散布 {arr[:,3].std():.3f}\n",
              flush=True)

    # ═══════════════ 核心 3：整理敏感度 ═══════════════
    print(f"{'='*70}\nalpha 對低質量段冪次的敏感度\n{'='*70}")
    print(f"{'冪次 p':>8}{'alpha 平均':>11}{'散布':>8}")
    means = []
    for p in slopes:
        a = results[p][:, 3]
        means.append(a.mean())
        print(f"{p:>8.1f}{a.mean():>11.3f}{a.std():>8.3f}")
    means = np.array(means)
    # ↓ 跨度：不同 p 之下 α 平均的最大值 − 最小值
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
