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
              n_gen=400_000, return_binary_flag=False):
    """生成一批假觀測。

    先用獨立的亂數生成 n_gen 顆，套用選擇函數後再隨機抽出 n_stars 顆 ——
    這個抽樣步驟很重要，它才是真觀測「只有 1,078 顆」帶來的統計雜訊來源。

    `return_binary_flag=True` 時多回傳每顆抽中的星是不是雙星的真值，
    預設 `False`、行為不變（見 `JointModel.synthesise()` 的說明）。
    """
    import copy
    gen = copy.copy(model)
    gen.n_syn = n_gen
    gen.draws = draw_randoms(n_gen, np.random.default_rng(seed))
    gen.dav = dav
    gen.selection = selection
    out = gen.synthesise(theta, return_binary_flag=return_binary_flag)
    if out is None:
        raise RuntimeError("生成失敗：檢查 theta 是否在 isochrone 網格範圍內")
    if return_binary_flag:
        color, mag, is_bin = out
    else:
        color, mag = out
    if len(color) < n_stars:
        raise RuntimeError(f"通過選擇函數的只有 {len(color)} 顆，不足 {n_stars}")
    pick = np.random.default_rng(seed + 99).choice(len(color), n_stars,
                                                   replace=False)
    if return_binary_flag:
        return color[pick], mag[pick], is_bin[pick]
    return color[pick], mag[pick]


# 擬合用的網格。範圍刻意開得比真值寬很多 ——
# 切半實驗就是因為網格窗太窄（MH 只有 0.00–0.30），
# 20 個半樣本裡有 7 個貼在牆上、散布被截斷。
COARSE = [np.arange(7.30, 8.401, 0.10),      # logage
          # 下界原本 7.90 -> 7.70，2026-08-09 P9（MIST + 鎖住 MH）連續兩次
          # 撞到網格/先驗下限，代表它想跑到比 7.70 更年輕的地方 ——
          # 這正是 P9 要偵測的訊號（MH 被鎖住後模型跑向不合理年齡去補償），
          # 已把先驗一併放寬到 7.30（約 20 Myr，遠低於 M45 公認的
          # 100-135 Myr）才能看清楚它真正想落在哪裡，不要在邊界上硬截斷。
          # A_V 上界原本 0.40，真實資料四種設定全部貼牆
          #（A/B 貼下界 0.000、C/D 貼上界 0.400），答案被邊界決定。
          # 放寬到 1.0：若 A_V 能自由移動，dav 就不必獨自承擔展寬，
          # C 對 D 那 0.400 的 alpha 擺動有可能只是 A_V 被鎖死的副作用。
          np.arange(0.00, 1.001, 0.10),      # A_V
          # 原本 0.15-0.80（實際只到 0.75，np.arange 的步長把上限吃掉了），
          # 2026-08-09 P9（鎖住 MH）第一次讓 f_bin 撞到這道牆 ——
          # 之前所有設定的最佳解都落在 0.40-0.65，從沒測過先驗越界處。
          # 物理上限是 1.0（PHYSICAL_LIMITS 字典），先驗也已同步放寬到 1.0，
          # 這裡放到 0.95 覆蓋到底，留一點餘裕避免剛好卡在邊界的數值問題。
          np.arange(0.15, 0.951, 0.10),      # f_bin
          # 原本 1.70-3.00，先驗（config.toml alpha_min/max）其實是 1.5-3.2，
          # 網格又比先驗窄，2026-08-09 低質量段冪次延伸掃描（p=1.9/2.0）
          # 撞到這個上界。alpha 沒有物理硬上限（不像 f_bin 那樣），
          # 直接放寬到跟先驗一致。
          np.arange(1.50, 3.201, 0.20),      # alpha
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
                     allow_wall=(), raise_on_wall=True, names=None,
                     no_refine=()):
    """多階段網格搜尋：每一階在上一階的最佳點附近縮小格距重掃。

    比兩階段多一階，是因為這裡的網格開得很寬（為了避免貼牆），
    粗格距因此較大，只精修一次的解析度不夠。
    extra_axis 用來附加額外維度。可以是單一陣列（第七維，差異消光），
    也可以是陣列的 list/tuple（第七、八維，例如再加低質量段冪次）。
    寫成兩種都吃，是為了不動到既有呼叫端 —— fit_real.py 與
    profile_lowmass.py 都傳單一陣列。

    **貼牆自動偵測**：搜尋範圍的邊界決定了答案，這件事在本專案已經發生五次
    （金屬量先驗上界 0.25、切半實驗的網格窗、S4 的 A_V 下界、S4 的 dav 上界、
    fit_real 第一次執行的 A_V）。每一次都是事後看報表才發現，中間已經根據
    被邊界決定的數字做了判斷。所以改成當場中止並報錯。

    allow_wall 傳入「已知會貼牆且已理解原因」的維度索引 —— 目前只有 dav，
    它經注入回收證實不可辨識，貼牆是預期行為而非錯誤。
    """
    # **2026-08-11 修正的嚴重 bug**：原本的迴圈把「粗網格搜尋」跟「第一次
    # 精修」搞成同一輪——`for r in refines: best,lp = grid_best_parallel(cur)`
    # 用的 `cur` 在第一輪迭代時還是原始粗網格，算完精修軸 `nxt` 卻只有在
    # 迴圈還有下一個 `r` 時才會真的拿去搜尋。傳 `refines=[3]`（單一值，
    # 這個專案裡 `fit_real.py`/`profile_lowmass.py`/`inject_lowmass.py`/
    # `profile_outlierfrac.py` 全部預設如此）代表迴圈只跑一輪，回傳的
    # `best` 是**純粗網格 argmax，完全沒有精修過**——alpha 只可能落在
    # COARSE 的 0.20 間距格點上，logage/A_V/f_bin 同理落在各自的粗網格
    # 間距上，這正是 P11（`profile_outlierfrac`）12 次執行 alpha 精確等於
    # 2.500、散布 0.000 的成因，而且不只 P11 中招——`fit_real.py` 沒帶
    # `--refines 3,3` 的每一次呼叫都受影響。完整波及範圍記在
    # `LIMITATIONS.md`。
    #
    # 修正：粗網格搜尋永遠先做一次（迴圈外），`refines` 裡的每個值代表
    # 一輪真正的精修（迴圈內，搜尋剛算出來的精修軸）。`refines=[3]` 現在
    # 代表「粗網格 + 一次精修」，`refines=[3,3]` 代表「粗網格 + 兩次精修」，
    # 跟函式文件字面上寫的「多階段」定義一致，也是這個專案本來就以為在
    # 發生的行為。
    if extra_axis is None:
        extras = []
    elif isinstance(extra_axis, (list, tuple)):
        extras = list(extra_axis)
    else:
        extras = [extra_axis]          # 單一陣列：維持舊呼叫端的行為
    cur = list(axes) + extras
    bounds = [(a.min(), a.max()) for a in cur]
    # 2026-08-23：跟 model.bounds（真正生效的先驗）取交集，理由見
    # LIMITATIONS.md 新增條目——搜尋軸的名目邊界有時刻意開得比先驗寬
    # （例如這支模組自己的 COARSE 常數，A_V 軸開到 1.0，但
    # config.toml [joint_fit] av_max 當時沒有跟著從 0.6 放寬，logage
    # 軸開到 8.40、av_max 仍是 8.30），此時任何超出先驗的格點在
    # log_prior() 都會被直接判 -inf、永遠選不到，真正的「牆」是先驗
    # 邊界，不是搜尋軸本身的邊界。check_walls()／report() 都直接沿用
    # 這裡回傳的 bounds 判斷貼牆，若不取交集，會在先驗邊界被貼住時
    # 誤判成「還沒到牆」，讓角落解悄悄當成收斂解通過——這正是
    # CONTRIBUTING.md 第六節第 2 條「先驗、搜尋軸、網格涵蓋三層邊界
    # 必須一致」在貼牆偵測這裡的變體。只會讓 bounds 變緊不會變寬，
    # 所以只要現有結果從未真的貼到先驗牆（headline 與 radial 系列的
    # A_V 都遠低於 0.6，查證過程見 LIMITATIONS.md），這個改動對它們的
    # 數值結果逐位元不變，只有貼牆偵測本身變準。`axes` 一律是模型的前
    # N 個核心參數、`extra_axis` 一律接在後面（呼叫端與 JointModel 的
    # bounds 都遵守同一個「六參數在前，dav／低質量段冪次視情況接在
    # 第七維」的固定順序——見 JointModel.enable_dav_fit()／
    # enable_lowmass_fit() 都是 vstack 到 self.bounds 尾端），所以就算
    # `model.bounds` 跟 `cur` 維度數不一致（例如這次呼叫沒開 dav，
    # model.bounds 只有 6 維，但 bounds 因為 extra_axis 有 7 維），
    # 前面對得上的那幾維位置對應仍然成立，只有多出來的尾端維度沒有
    # 對應的先驗可以收緊——那幾維維持原本的搜尋軸邊界，不是整批放棄
    # 交集（2026-08-23 CodeRabbit review：原本長度不符就整批跳過，
    # 會讓明明對得上的前幾維也白白錯過收緊機會）。
    model_bounds = getattr(model, "bounds", None)
    if model_bounds is not None:
        n = min(len(model_bounds), len(bounds))
        # strict=True（2026-08-23 CodeRabbit review nitpick）：bounds[:n]
        # 跟 model_bounds[:n] 已經用同一個 n 切過，長度理論上一定相等，
        # 這裡只是讓「萬一以後邏輯改動導致兩者長度分歧」當場報錯，不要
        # 讓 zip() 預設的截斷行為悄悄吃掉多出來的那幾維。
        merged = [(max(lo, float(mlo)), min(hi, float(mhi)))
                  for (lo, hi), (mlo, mhi) in zip(bounds[:n], model_bounds[:n],
                                                   strict=True)]
        # 2026-08-23 CodeRabbit review：搜尋軸跟先驗如果根本沒有重疊
        # （例如網格開錯範圍、或先驗事後改過沒同步更新網格常數），
        # 交集會是空的（lo > hi），後面的貼牆判斷會拿一個下界大於
        # 上界的無效區間去算容忍帶，安靜地算出沒有意義的數字。
        # 這種情況不該悄悄放行——立刻中止並點名是哪一維，讓人去確認
        # 網格常數跟 config.toml 先驗是不是真的對不上。
        #
        # **2026-08-23 CodeRabbit review 第二輪追加**：上面那個檢查只擋
        # 得住「連續區間本身反了」，擋不住「連續區間有效、但離散網格軸
        # 剛好一個格點都沒落在裡面」——例如網格步距 0.2、真正先驗恰好
        # 卡在 (0.61, 0.65) 這種比一個格距還窄的範圍，merged 的 (lo,hi)
        # 是合法區間（lo<hi）不會觸發上面的檢查，但 log_prior() 會讓
        # 這個維度上每一個實際格點都判 -inf，grid_best_parallel() 在
        # 這一維上等於在搜尋一個永遠選不到合法解的空間——這不是貼牆，
        # 是網格解析度細不過先驗寬度，同樣要當場中止，不能讓後面的
        # 搜尋悄悄跑完再回傳一個被 -inf 決定的無意義最佳點。
        for i, (lo, hi) in enumerate(merged):
            if lo > hi:
                nm = names[i] if names and i < len(names) else f"dim{i}"
                raise ValueError(
                    f"搜尋軸跟先驗的交集是空的（{nm}：搜尋軸 "
                    f"{bounds[i]}，先驗 {tuple(model_bounds[i])}，交集 "
                    f"({lo:.4g}, {hi:.4g}) 下界大於上界）——網格常數跟 "
                    f"model 的先驗完全對不上，不是單純貼牆，先去確認"
                    f"這兩邊的範圍設定。")
            axis = np.asarray(cur[i])
            n_in = int(((axis >= lo) & (axis <= hi)).sum())
            if n_in == 0:
                nm = names[i] if names and i < len(names) else f"dim{i}"
                raise ValueError(
                    f"搜尋軸跟先驗的交集是有效區間，但這一維的網格格點"
                    f"沒有任何一個落在裡面（{nm}：交集 ({lo:.4g}, "
                    f"{hi:.4g})，搜尋軸 {axis.size} 個格點、步距約 "
                    f"{(axis.max() - axis.min()) / max(axis.size - 1, 1):.4g}，"
                    f"全部落在交集之外）——這一維的網格解析度比先驗寬度"
                    f"還粗，這一維的每個格點在 log_prior() 都會判 -inf，"
                    f"grid_best_parallel() 在這一維上選不到任何合法解，"
                    f"不是貼牆，先去確認網格步距或先驗範圍是不是設錯了。")
        bounds = merged + bounds[n:]
    best, lp = grid_best_parallel(model, cur, n_proc)
    for r in refines:
        nxt = []
        for i, ax in enumerate(cur):
            # Some parameters select a discrete physical model (for example an
            # isochrone age or metallicity).  Refining between downloaded grid
            # values only creates a more precise-looking theta that is silently
            # snapped back to the same model.  Callers can freeze those axes at
            # the best actually evaluated grid point after the coarse search.
            if i in no_refine:
                nxt.append(np.array([best[i]]))
                continue
            if len(ax) < 2:
                nxt.append(ax)
                continue
            step = float(ax[1] - ax[0])
            lo = max(best[i] - step, bounds[i][0])
            hi = min(best[i] + step, bounds[i][1])
            nxt.append(np.arange(lo, hi + 1e-9, step / r))
        cur = nxt
        best, lp = grid_best_parallel(model, cur, n_proc)

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
    ap.add_argument("--extra-scatter-sweep", default=None,
                    help="逗號分隔的多個額外亮度散布量級（星等），對每個值"
                         "各跑一次 S1 變體：假資料帶這個散布、擬合模型沒有"
                         "（模型本身就沒有這一項，見 LIMITATIONS.md C19）。"
                         "用來量自轉調製／前主序光變／黑子這類未建模物理"
                         "對 alpha 的敏感度曲線")
    ap.add_argument("--refines", default="3,3",
                    help="各精修階段的縮小倍率。七維時用單階段以免格點爆炸")
    ap.add_argument("--n-syn", type=int, default=None,
                    help="覆寫擬合模型的合成星數。合成星越多，"
                         "概似曲面的蒙地卡羅雜訊越小")
    ap.add_argument("--model-seed", type=int, default=None,
                    help="改掉擬合模型的共用亂數種子。"
                         "用來判定 S1 的殘餘偏差是不是蒙地卡羅產物")
    ap.add_argument("--dav-distribution", default="lognormal",
                    choices=["lognormal", "trunc_exp"],
                    help="差異消光的分布形式（見 LIMITATIONS.md C5）。"
                         "預設 lognormal 與原本行為一致。設在 base 上，"
                         "透過 make_fake()/with_observations() 的淺複製"
                         "自動傳給注入與擬合兩側，不需要另外改動")
    ap.add_argument("--tag", default="", help="輸出檔名後綴，避免覆蓋"
                     "results/injection_recovery.npz（跟 fit_real.py／"
                     "inject_lowmass.py 同款式，見 LIMITATIONS.md D6："
                     "固定檔名被重跑覆寫過，這裡原本沒有這個防呆）")
    # 2026-08-20：開跑前檢查（見 scripts/tools/preflight.py）。
    ap.add_argument("--preflight", action="store_true",
                    help="只做開跑前檢查然後結束，不進行任何擬合")
    ap.add_argument("--force", action="store_true",
                    help="略過開跑前檢查的阻擋（不建議，僅供已知情況使用）")
    args = ap.parse_args()
    # 數值參數驗證（2026-08-21 CodeRabbit review）：--trials 0 會讓結果
    # 陣列為空，後面 arr[:, 3] 丟 IndexError；--n-syn 0 會被下面的 `or`
    # 靜默換回設定檔值（看起來成功、其實沒照你給的跑）；負值或非正的
    # refines 會在模型建構／精修時才炸。這些都是結構性輸入錯誤，在
    # argparse 階段擋掉最省。
    if args.trials < 1:
        ap.error("--trials must be positive")
    if args.n_syn is not None and args.n_syn < 1:
        ap.error("--n-syn must be positive（不給這個旗標才是沿用 config 值）")
    if "/" in args.tag or "\\" in args.tag:
        ap.error("--tag 只能包含檔名後綴字元，不能包含路徑分隔符")
    if args.dav_distribution != "lognormal" and not args.tag:
        ap.error("--dav-distribution 不是 lognormal 時必須給 --tag，"
                 "避免覆寫 results/injection_recovery.npz（A1 統計誤差 "
                 "0.144 的來源檔案，見 LIMITATIONS.md D6 記錄過的同類事故）")
    n_proc = args.procs or (os.cpu_count() or 1)
    out_path = HERE / "results" / f"injection_recovery{args.tag}.npz"

    # **B1（意圖對帳）要用的「已知情境名稱」必須在這裡（模型建構之前）就
    # 算出來**：dav_sweep／extra_scatter_sweep 兩個旗標會動態追加
    # S2@<v>／S1var@<v> 這種情境名稱，原本這段邏輯（連同 want 的更新）
    # 寫在 SCEN 字典旁邊，比模型建構晚很多——但 preflight 的 gate 要在
    # 建好模型後、真正開始擬合前就跑，所以「這次到底會處理哪些情境」
    # 必須先算好。SCEN 字典本體（含每個情境的實際定義）仍留在原本位置
    # 建構，因為它需要 sel（選擇函數，稍後才載入）；這裡只需要「名稱」。
    want = [s.strip().upper() for s in args.scenarios.split(",")]
    known_scenarios = {"S1", "S2", "S3", "S3F", "S4"}
    var_inject = {}
    if args.dav_sweep:
        dav_sweep_vals = [float(x) for x in args.dav_sweep.split(",")]
        want = [k for k in want if k != "S2"] \
            + [f"S2@{v:g}" for v in dav_sweep_vals]
        known_scenarios |= {f"S2@{v:g}" for v in dav_sweep_vals}
    if args.extra_scatter_sweep:
        scatter_vals = [float(x) for x in args.extra_scatter_sweep.split(",")]
        want = want + [f"S1var@{v:g}" for v in scatter_vals]
        for v in scatter_vals:
            key = f"S1var@{v:g}"
            known_scenarios.add(key)
            var_inject[key] = v
    # 原本這裡是 `if key not in SCEN: print("未知情境", key, "，略過")`——
    # 靜默略過，preflight 通過、擬合照跑，但實際處理的情境跟意圖不同，
    # 是跟 fit_real.py 打錯 --configs 名稱一模一樣的錯誤形狀（見 main()
    # 下方那道不能被 --force 繞過的硬阻擋，跟 workload_audit 那道可以
    # 被 --force 繞過的阻擋，兩者都要有，理由同 fit_real.py 的註解）。
    unknown_scenarios = [k for k in want if k not in known_scenarios]

    def _store_key(k: str) -> str:
        """情境名稱轉成存檔用的鍵——`@`／`.` 不是合法的 npz 鍵字元，跟
        main() 最後寫檔時原本用的轉換規則一致（S2@0.3 -> S2_at_0p3）。"""
        return k.replace("@", "_at_").replace(".", "p")

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

    effective_n_syn = args.n_syn or cj.n_synthetic
    cfg._data["step3_age"]["n_synthetic"] = effective_n_syn
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0   # 測流程本身，關掉先驗

    base = joint_fit.JointModel(cfg, color[ok], mag[ok], grid, errmodel, dm)
    base.dav_distribution = args.dav_distribution
    if args.dav_distribution != "lognormal":
        print(f"差異消光分布形式改用 {args.dav_distribution}（C5 系統誤差比較）")
    if args.model_seed is not None:
        # 擬合模型的共用亂數是固定的一批，n_synthetic 有限就會留下一個
        # 與參數無關的蒙地卡羅偏移。換種子重跑，偏差若跟著變，
        # 就證明 S1 的殘餘偏差是取樣產物、可以靠加大 n_synthetic 壓下去。
        base.draws = draw_randoms(base.n_syn,
                                  np.random.default_rng(args.model_seed))
        print(f"擬合模型的共用亂數改用種子 {args.model_seed}")
    refines = [int(x) for x in args.refines.split(",") if x.strip()]

    # 2026-08-20：B3（續傳）—— 這支腳本原本完全沒有續傳機制，只在全部
    # 情境跑完後 np.savez 一次，中途被砍就整批白工。改用 checkpoint.py，
    # 顆粒度到「每個情境的每一次試驗」。這支腳本的 multi_stage_best() 呼叫
    # 帶 raise_on_wall=False（貼牆只印警告、不丟例外），跟 inject_lowmass.py
    # 不同，不需要 attempted 計數區分「已嘗試」跟「已成功」——每次嘗試
    # 必定成功，跟 profile_lowmass.py 同一種情況。
    manifest = {"n_syn": effective_n_syn, "refines": args.refines,
                "dav_true": args.dav_true, "model_seed": args.model_seed,
                "dav_distribution": args.dav_distribution}
    sys.path.insert(0, str(HERE / "scripts" / "tools"))
    import checkpoint                                            # noqa: E402
    import preflight                                             # noqa: E402
    partial = checkpoint.load_partial(out_path)
    checkpoint.check_manifest(out_path, manifest, partial)

    if args.preflight:
        preflight._force_utf8_stdout()
    scan_keys = [k for k in want if k in known_scenarios]
    partial_counts = {k: min(len(partial.get(_store_key(k), [])), args.trials)
                      for k in scan_keys}
    w_fails, w_warns = preflight.workload_audit(
        scan_keys=scan_keys, repeats=args.trials, n_syn=effective_n_syn,
        n_obs=n_obs, refines=refines, partial_counts=partial_counts,
        unit="次試驗", unknown=unknown_scenarios,
        known=sorted(known_scenarios), scan_label="情境（--scenarios）")
    preflight.output_audit(out_path, partial)
    preflight.mandatory_gate(
        base, grid, refines, script="injection_recovery.py",
        expected_overrides={"mh_prior_sigma": 0.0},
        force=args.force, dry_run=args.preflight,
        extra_fails=w_fails, extra_warns=w_warns)
    # 打錯的情境名稱要當場中止，不能像下面迴圈那樣靜默略過——理由跟
    # fit_real.py 對 --configs 的處理完全一樣（見該檔案 main() 裡的
    # 註解）：workload_audit 那道阻擋可以被 --force 繞過，這裡不行。
    if unknown_scenarios:
        print(f"錯誤：--scenarios 有不存在的情境名稱 {unknown_scenarios}"
              f"（可用：{', '.join(sorted(known_scenarios))}）", flush=True)
        sys.exit(1)

    sel = selmod.load(HERE / "data" / "selection.npz")
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

    # dav 掃描：把 S2 換成一系列不同注入值的情境。`want` 的更新（S2 換成
    # S2@<v> 一系列）已經在檔案上面（模型建構之前，preflight 需要用到
    # 完整的 want 清單）做過一次，這裡只需要把對應的 SCEN 定義補上。
    if args.dav_sweep:
        for v in dav_sweep_vals:
            SCEN[f"S2@{v:g}"] = (f"漏掉差異消光（注入 dav={v:g}，擬合當作 0）",
                                 v, None, 0.0, None, None)

    # C19 額外亮度散布掃描：情境本身跟 S1 對照組完全一樣（有選擇函數、
    # 有差異消光），唯一差別是假資料多帶一個未被模型描述的亮度散布。
    # `var_inject`（「這個情境要注入多少散布」）跟 `want` 的更新同樣已經
    # 在檔案上面做過，這裡只補 SCEN 定義——不擴充 SCEN 的六元組本身，
    # 那個元組在下面迴圈裡被拆解使用，多加一個欄位要動到所有既有情境，
    # 改動面大且容易出錯。
    if args.extra_scatter_sweep:
        for v in scatter_vals:
            SCEN[f"S1var@{v:g}"] = (f"額外亮度散布 {v:g} mag（模型沒有這一項，C19）",
                                    0.0, None, 0.0, None, None)

    results = {}
    for key in want:
        if key not in SCEN:
            # 走到這裡代表用了 --force 略過上面的硬阻擋；仍然略過，不要
            # 假裝算過這個情境。
            print(f"未知情境 {key}，略過")
            continue
        skey = _store_key(key)
        desc, dav_in, sel_in, dav_fit, sel_fit, extra = SCEN[key]
        print(f"\n{'='*74}\n{key}：{desc}\n{'='*74}")
        # 截到 args.trials：理由同 inject_lowmass.py 的同一處修正
        # （2026-08-21 CodeRabbit review）——磁碟已有的次數比這次要求的多時，
        # 不截斷會讓統計與 dav sweep 總表用了超過本次 --trials 的筆數。
        got_all = list(partial.get(skey, []))[:args.trials]
        for t in range(args.trials):
            if t < len(got_all):
                print(f"  {key} 第 {t+1} 次：沿用既有結果，跳過重算",
                      flush=True)
                continue
            t0 = time.time()
            # C19：只有生成端帶額外亮度散布，擬合端一律 0——這正是要測的
            # 「模型沒有這一項」的情境。用 try/finally 還原，避免某次試驗
            # 中途丟例外時把污染留給後面的情境（base 是所有情境共用的）。
            var_in = var_inject.get(key, 0.0)
            base.extra_scatter = var_in
            try:
                fc, fm = make_fake(base, THETA_TRUE, n_obs, seed=1000 + 17 * t,
                                   dav=dav_in, selection=sel_in)
            finally:
                base.extra_scatter = 0.0
            m = base.with_observations(fc, fm)
            m.dav, m.selection = dav_fit, sel_fit
            m.extra_scatter = 0.0   # 擬合模型明確不帶這一項
            if extra is not None:
                m.enable_dav_fit(float(extra.min()), float(extra.max()))
            # dav（索引 6）已由注入回收證實不可辨識，貼牆是預期行為；
            # 其餘維度貼牆會印出警告（診斷用的跑法不中止，
            # 產出科學數字的 fit_real.py 則設成直接報錯）。raise_on_wall=
            # False 代表這裡不會丟例外，每次嘗試必定成功，不需要像
            # inject_lowmass.py 那樣另外追蹤「已嘗試」跟「已成功」的差別。
            best, lp, bounds = multi_stage_best(
                m, COARSE, refines, n_proc, extra_axis=extra,
                allow_wall=(6,) if extra is not None else (),
                raise_on_wall=False)
            truth = (list(THETA_TRUE) + [dav_in]) if extra is not None \
                else THETA_TRUE
            report(f"{key} 第 {t+1} 次  lnP={lp:.1f}", truth, best, bounds,
                   time.time() - t0)
            got_all.append(best)
            # 跑完一次試驗就存一次，不等這個情境或全部情境都跑完——
            # 中途被砍，已經算完的每一次試驗都保得住，重跑時讀回來跳過。
            got_all = checkpoint.save_progress(
                out_path, skey, got_all, manifest,
                extra_arrays={"theta_true": THETA_TRUE,
                             "dav_distribution": args.dav_distribution})
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
        print("      與選擇函數的 -0.178 相等純屬巧合（因為 0.30 是我挑的）。")

    # 每一次試驗跑完就已經存過檔了（見上面迴圈裡的
    # checkpoint.save_progress()，含 theta_true／dav_distribution 這兩個
    # metadata——2026-08-19 CodeRabbit PR #63 要求存的欄位，現在每次存檔
    # 都會寫，不用等到最後），這裡不用再存一次，只是印出最終確認訊息。
    print(f"\n寫入 {out_path}")


if __name__ == "__main__":
    main()
