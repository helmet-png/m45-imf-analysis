# -*- coding: utf-8 -*-
"""注入回收測試：用已知答案的假資料檢驗擬合流程。

**這支程式存在的理由**

上一輪打算把「差異消光」升格成自由參數，理由是紅化向量的方向與雙星偏移的
方向不同、所以可分辨。但方向不同只是必要條件不是充分條件，而且只比了雙星
一項。現有六參數的相關矩陣本來就已經接近奇異（年齡↔金屬量 +0.96、
年齡↔消光 −0.96、金屬量↔消光 −0.95），再往這個方向加參數風險很高。

靠論證判斷不了，只能實測：**用模型自己生成一批「假觀測」，參數是我們指定的
已知值，再把它當成真資料丟進整套擬合流程，看能不能把那組值找回來。**

三件靠它才能回答的事：

  1. 流程本身有沒有偏差（對照組：注入什麼、擬合什麼都一致）
  2. 模型漏掉某個效應的代價（注入時有、擬合時沒有 -> 量 alpha 被推歪多少）
  3. 新參數可不可解（注入時有、擬合時也放自由 -> 找不找得回來）

沒有第 1 項當基準，第 2、3 項都沒有意義 —— 這是這個專案犯過八次的錯。

**兩個一定要做對的地方**

  * 假資料必須用**與模型不同的亂數種子**。若共用同一批亂數，
    在真值處等於拿合成星團跟自己比，概似會是完美的，回收率一定 100%，
    測到的是同義反覆而不是流程的能力。
  * 假資料的顆數要跟真觀測一樣（1,078）。顆數決定統計雜訊的量級，
    生一萬顆再擬合等於在測一個我們沒有的資料集。
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
from measure_overconfidence import GRID, grid_best_parallel   # noqa: E402

# 注入用的真值。取自高斯先驗版六參數 MCMC 的後驗中位數，
# 這樣假資料落在與真實觀測相近的參數區域，測試才有代表性。
THETA_TRUE = np.array([8.15, 0.15, 0.45, 2.35, 0.00, -0.50])
NAMES = joint_fit.PARAM_NAMES


def make_fake(model, theta, n_stars, seed, dav=0.0, selection=None,
              n_gen=400_000):
    """生成一批假觀測。

    先用獨立的亂數生成 n_gen 顆，套用選擇函數後再隨機抽出 n_stars 顆 ——
    這個抽樣步驟很重要，它才是真觀測「只有 1,078 顆」帶來的統計雜訊來源。
    """
    import copy
    gen = copy.copy(model)
    gen.n_syn = n_gen
    gen.draws = draw_randoms(n_gen, np.random.default_rng(seed))
    gen.dav = dav
    gen.selection = selection
    out = gen.synthesise(theta)
    if out is None:
        raise RuntimeError("生成失敗：檢查 theta 是否在 isochrone 網格範圍內")
    color, mag = out
    if len(color) < n_stars:
        raise RuntimeError(f"通過選擇函數的只有 {len(color)} 顆，不足 {n_stars}")
    pick = np.random.default_rng(seed + 99).choice(len(color), n_stars,
                                                   replace=False)
    return color[pick], mag[pick]


# 擬合用的網格。範圍刻意開得比真值寬很多 ——
# 切半實驗就是因為網格窗太窄（MH 只有 0.00–0.30），
# 20 個半樣本裡有 7 個貼在牆上、散布被截斷。
COARSE = [np.arange(7.90, 8.401, 0.10),      # logage
          # A_V 上界原本 0.40，真實資料四種設定全部貼牆
          #（A/B 貼下界 0.000、C/D 貼上界 0.400），答案被邊界決定。
          # 放寬到 1.0：若 A_V 能自由移動，dav 就不必獨自承擔展寬，
          # C 對 D 那 0.400 的 alpha 擺動有可能只是 A_V 被鎖死的副作用。
          np.arange(0.00, 1.001, 0.10),      # A_V
          np.arange(0.15, 0.801, 0.10),      # f_bin
          np.arange(1.70, 3.001, 0.20),      # alpha
          np.arange(-0.40, 0.401, 0.15),     # MH
          np.arange(-1.20, 0.801, 0.50)]     # q_gamma


class WallError(RuntimeError):
    """最佳解落在搜尋範圍的邊界上 —— 答案是被邊界決定的，不是被資料決定的。"""


class CornerError(RuntimeError):
    """最佳解落在**物理**邊界上 —— 放寬範圍不可能，這是模型設定錯誤的徵狀。"""


# 參數自身的物理上下限。None 表示該方向沒有物理限制。
#
# **為什麼要分開**：先前的貼牆偵測把所有邊界一視同仁，訊息一律是
# 「必須放寬範圍重跑」。但 dav 掃描實測到 A_V 貼在 0.000 —— 消光不可能為負，
# 這道牆放寬不了。兩者的意義完全不同：
#   人為邊界貼牆 = 我把範圍設太窄，放寬即可，資料本身沒問題
#   物理邊界貼牆 = 模型跑到角落解，代表模型與資料不符，放寬無濟於事
# 給錯訊息會讓下一輪往錯的方向修。
PHYSICAL_LIMITS = {
    "A_V":   (0.0, None),    # 消光不可能為負
    "f_bin": (0.0, 1.0),     # 比例
    "dav":   (0.0, None),    # 散布不可能為負
    # alpha、q_gamma 沒有物理上下限
}

# 這兩個的範圍受限於已下載的 isochrone 網格涵蓋範圍，不是物理限制也不是
# 隨手設的 —— 放寬要重新下載網格。單獨分類以免被當成「改個數字就好」。
GRID_LIMITED = {"logage", "MH"}


def check_walls(best, bounds, names, allow=(), tol=0.02):
    """回傳貼牆的維度清單，每項是 (種類, 說明字串)。

    種類為 "physical"（物理邊界，角落解）、"grid"（受 isochrone 網格限制）、
    或 "search"（我自己設的搜尋範圍太窄）。tol 以該維跨度為單位。
    """
    hits = []
    for i, (lo, hi) in enumerate(bounds):
        if i in allow or hi <= lo:
            continue
        span = hi - lo
        at_lo = best[i] - lo < tol * span
        at_hi = hi - best[i] < tol * span
        if not (at_lo or at_hi):
            continue
        nm = names[i] if i < len(names) else f"dim{i}"
        side, edge = ("下界", lo) if at_lo else ("上界", hi)

        plim = PHYSICAL_LIMITS.get(nm, (None, None))
        phys_edge = plim[0] if at_lo else plim[1]
        if phys_edge is not None and abs(edge - phys_edge) < 1e-9:
            kind = "physical"
        elif nm in GRID_LIMITED:
            kind = "grid"
        else:
            kind = "search"
        hits.append((kind, f"{nm}={best[i]:.3f} 貼{side}"
                           f"（範圍 {lo:.3f}–{hi:.3f}）"))
    return hits


def wall_message(hits):
    """依種類給出對應的處置說明。不同種類的補救方式完全不同。"""
    lines = []
    for kind, txt in hits:
        if kind == "physical":
            lines.append(f"[物理邊界] {txt}\n"
                         "    這是角落解：該參數已頂到物理上不可能超越的值。"
                         "放寬範圍不可能，\n"
                         "    也不該把它當成擬合結果。它代表模型描述不了這批資料，"
                         "要回頭檢查模型。")
        elif kind == "grid":
            lines.append(f"[網格邊界] {txt}\n"
                         "    受限於已下載的 isochrone 網格涵蓋範圍。"
                         "要放寬必須重新下載網格，\n"
                         "    不是改個數字就好。")
        else:
            lines.append(f"[搜尋範圍] {txt}\n"
                         "    這道牆是我自己設的，答案被它決定而非被資料決定。"
                         "放寬範圍重跑。")
    return "\n  ".join(lines)


def multi_stage_best(model, axes, refines, n_proc, extra_axis=None,
                     allow_wall=(), raise_on_wall=True, names=None):
    """多階段網格搜尋：每一階在上一階的最佳點附近縮小格距重掃。

    比兩階段多一階，是因為這裡的網格開得很寬（為了避免貼牆），
    粗格距因此較大，只精修一次的解析度不夠。
    extra_axis 用來附加第七維（差異消光）。

    **貼牆自動偵測**：搜尋範圍的邊界決定了答案，這件事在本專案已經發生五次
    （金屬量先驗上界 0.25、切半實驗的網格窗、S4 的 A_V 下界、S4 的 dav 上界、
    fit_real 第一次執行的 A_V）。每一次都是事後看報表才發現，中間已經根據
    被邊界決定的數字做了判斷。所以改成當場中止並報錯。

    allow_wall 傳入「已知會貼牆且已理解原因」的維度索引 —— 目前只有 dav，
    它經注入回收證實不可辨識，貼牆是預期行為而非錯誤。
    """
    cur = list(axes) + ([extra_axis] if extra_axis is not None else [])
    bounds = [(a.min(), a.max()) for a in cur]
    best, lp = None, -np.inf
    for r in refines:
        best, lp = grid_best_parallel(model, cur, n_proc)
        nxt = []
        for i, ax in enumerate(cur):
            if len(ax) < 2:
                nxt.append(ax)
                continue
            step = float(ax[1] - ax[0])
            lo = max(best[i] - step, bounds[i][0])
            hi = min(best[i] + step, bounds[i][1])
            nxt.append(np.arange(lo, hi + 1e-9, step / r))
        cur = nxt

    hits = check_walls(best, bounds, names or NAMES + ["dav"], allow_wall)
    if hits:
        msg = "最佳解落在邊界上：\n  " + wall_message(hits) + \
              "\n（若已確認該維度不可辨識、貼牆是預期行為，" \
              "把它的索引加進 allow_wall。）"
        if raise_on_wall:
            # 物理邊界與搜尋邊界要用不同的例外型別，因為補救方式不同：
            # 前者不能靠放寬範圍解決，硬放寬只會得到非物理的參數值。
            kinds = {k for k, _ in hits}
            raise (CornerError(msg) if "physical" in kinds else WallError(msg))
        print("警告：" + msg, flush=True)
    return best, lp, bounds


def report(tag, truth, got, bounds, elapsed):
    print(f"\n--- {tag} ---")
    names = NAMES + (["dav"] if len(got) > 6 else [])
    print(f"{'參數':<10}{'真值':>9}{'回收':>9}{'偏差':>9}{'貼牆':>7}")
    for i, nm in enumerate(names):
        t = truth[i] if i < len(truth) else np.nan
        lo, hi = bounds[i]
        span = hi - lo
        wall = "是" if (got[i] - lo < 0.02 * span
                        or hi - got[i] < 0.02 * span) else ""
        print(f"{nm:<10}{t:>9.3f}{got[i]:>9.3f}{got[i]-t:>+9.3f}{wall:>7}")
    print(f"（{elapsed:.0f}s）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--trials", type=int, default=3,
                    help="每個情境跑幾次（不同的雜訊實現）")
    ap.add_argument("--scenarios", default="S1",
                    help="逗號分隔：S1 對照組 / S2 漏掉差異消光 / "
                         "S3 漏掉選擇函數 / S3F 選擇函數已補上 / "
                         "S4 差異消光放自由")
    ap.add_argument("--dav-true", type=float, default=0.30)
    ap.add_argument("--dav-sweep", default=None,
                    help="逗號分隔的多個 dav 真值，對每個值各跑一次 S2。"
                         "用來判定「兩個偏差剛好抵消」是不是巧合："
                         "若 alpha 偏差隨 dav 平滑變化並通過原點，"
                         "0.178 就只是曲線在 dav=0.30 這一點的值")
    ap.add_argument("--refines", default="3,3",
                    help="各精修階段的縮小倍率。七維時用單階段以免格點爆炸")
    ap.add_argument("--n-syn", type=int, default=None,
                    help="覆寫擬合模型的合成星數。合成星越多，"
                         "概似曲面的蒙地卡羅雜訊越小")
    ap.add_argument("--model-seed", type=int, default=None,
                    help="改掉擬合模型的共用亂數種子。"
                         "用來判定 S1 的殘餘偏差是不是蒙地卡羅產物")
    args = ap.parse_args()
    n_proc = args.procs or (os.cpu_count() or 1)
    want = [s.strip().upper() for s in args.scenarios.split(",")]

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
    n_obs = int(ok.sum())

    cfg._data["step3_age"]["n_synthetic"] = args.n_syn or cj.n_synthetic
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0   # 測流程本身，關掉先驗

    base = joint_fit.JointModel(cfg, color[ok], mag[ok], grid, errmodel, dm)
    if args.model_seed is not None:
        # 擬合模型的共用亂數是固定的一批，n_synthetic 有限就會留下一個
        # 與參數無關的蒙地卡羅偏移。換種子重跑，偏差若跟著變，
        # 就證明 S1 的殘餘偏差是取樣產物、可以靠加大 n_synthetic 壓下去。
        base.draws = draw_randoms(base.n_syn,
                                  np.random.default_rng(args.model_seed))
        print(f"擬合模型的共用亂數改用種子 {args.model_seed}")
    sel = selmod.load(HERE / "data" / "selection.npz")
    refines = [int(x) for x in args.refines.split(",") if x.strip()]
    npt = int(np.prod([len(a) for a in COARSE]))
    print(f"假觀測每批 {n_obs:,} 顆（與真實觀測相同）")
    print(f"粗網格 {npt:,} 點，三階段精修，{n_proc} 行程")
    print(f"注入真值：" + "  ".join(f"{n}={v:.3f}"
                                    for n, v in zip(NAMES, THETA_TRUE)))

    # 情境定義：(注入時 dav, 注入時選擇函數, 擬合時 dav, 擬合時選擇函數, 第七維)
    SCEN = {
        "S1": ("對照組：注入與擬合完全一致",
               0.0, None, 0.0, None, None),
        "S2": (f"模型漏掉差異消光（注入 dav={args.dav_true}，擬合當作 0）",
               args.dav_true, None, 0.0, None, None),
        "S3": ("模型漏掉測光品質選擇函數（注入有，擬合沒有）",
               0.0, sel, 0.0, None, None),
        # S3 量出漏掉選擇函數的代價，S3F 檢查補上之後代價有沒有消失。
        # 只做 S3 只證明「不補會壞」，不證明「補了就對」。
        "S3F": ("選擇函數已補上（注入與擬合都有）",
                0.0, sel, 0.0, sel, None),
        # dav 的上界原本設 0.6，結果 3 次裡有 2 次貼在 0.600 上 ——
        # 又是「牆決定答案」。放寬到 1.2 才能分辨「dav 真的很大」
        # 與「dav 不受約束、有多少吃多少」。
        "S4": (f"差異消光放自由（注入 dav={args.dav_true}，擬合第七維）",
               args.dav_true, None, 0.0, None, np.arange(0.0, 1.21, 0.20)),
    }

    # dav 掃描：把 S2 換成一系列不同注入值的情境
    if args.dav_sweep:
        vals = [float(x) for x in args.dav_sweep.split(",")]
        for v in vals:
            SCEN[f"S2@{v:g}"] = (f"漏掉差異消光（注入 dav={v:g}，擬合當作 0）",
                                 v, None, 0.0, None, None)
        want = [k for k in want if k != "S2"] + [f"S2@{v:g}" for v in vals]

    results = {}
    for key in want:
        if key not in SCEN:
            print(f"未知情境 {key}，略過")
            continue
        desc, dav_in, sel_in, dav_fit, sel_fit, extra = SCEN[key]
        print(f"\n{'='*74}\n{key}：{desc}\n{'='*74}")
        got_all = []
        for t in range(args.trials):
            t0 = time.time()
            fc, fm = make_fake(base, THETA_TRUE, n_obs, seed=1000 + 17 * t,
                               dav=dav_in, selection=sel_in)
            m = base.with_observations(fc, fm)
            m.dav, m.selection = dav_fit, sel_fit
            if extra is not None:
                m.enable_dav_fit(float(extra.min()), float(extra.max()))
            # dav（索引 6）已由注入回收證實不可辨識，貼牆是預期行為；
            # 其餘維度貼牆會印出警告（診斷用的跑法不中止，
            # 產出科學數字的 fit_real.py 則設成直接報錯）。
            best, lp, bounds = multi_stage_best(
                m, COARSE, refines, n_proc, extra_axis=extra,
                allow_wall=(6,) if extra is not None else (),
                raise_on_wall=False)
            truth = (list(THETA_TRUE) + [dav_in]) if extra is not None \
                else THETA_TRUE
            report(f"{key} 第 {t+1} 次  lnP={lp:.1f}", truth, best, bounds,
                   time.time() - t0)
            got_all.append(best)
        got_all = np.array(got_all)
        results[key] = got_all
        if len(got_all) > 1:
            print(f"\n{key} 跨 {len(got_all)} 次的平均偏差與散布：")
            names = NAMES + (["dav"] if got_all.shape[1] > 6 else [])
            truth = (list(THETA_TRUE) + [dav_in]) if extra is not None \
                else list(THETA_TRUE)
            for i, nm in enumerate(names):
                b = got_all[:, i] - truth[i]
                print(f"  {nm:<10}偏差 {b.mean():+.3f}   散布 {b.std():.3f}")

    # dav 掃描的總表：alpha 偏差對注入的 dav
    sweep = sorted([(float(k.split("@")[1]), v)
                    for k, v in results.items() if k.startswith("S2@")])
    if len(sweep) >= 2:
        base = results.get("S1")
        floor = float(np.mean(base[:, 3] - THETA_TRUE[3])) if base is not None \
            else 0.0
        print(f"\n{'='*74}\nalpha 偏差對注入的差異消光\n{'='*74}")
        print(f"對照組偏差地板 = {floor:+.3f}（已從下表扣除）\n")
        print(f"{'注入 dav':>10}{'alpha 偏差':>12}{'扣掉地板':>10}{'散布':>9}")
        for v, arr in sweep:
            b = arr[:, 3] - THETA_TRUE[3]
            print(f"{v:>10.2f}{b.mean():>+12.3f}{b.mean()-floor:>+10.3f}"
                  f"{b.std():>9.3f}")
        print("\n判讀：若偏差隨 dav 平滑變化且外推到 dav=0 時趨近 0，")
        print("      代表 +0.178 只是曲線在 dav=0.30 這一點的值，")
        print("      與選擇函數的 −0.178 相等純屬巧合（因為 0.30 是我挑的）。")

    np.savez(HERE / "results" / "injection_recovery.npz",
             theta_true=THETA_TRUE,
             **{k.replace("@", "_at_").replace(".", "p"): v
                for k, v in results.items()})
    print("\n寫入 results/injection_recovery.npz")


if __name__ == "__main__":
    main()
