# -*- coding: utf-8 -*-
"""建立測光品質篩選的選擇函數，並驗證它重現得出觀測到的存活率樣態。

驗收標準（在建立之前先訂好，避免事後挑指標）：
  1. 整體存活率誤差 < 0.02
  2. 逐星等的存活率，最大誤差 < 0.08
  3. **G>=17 紅藍兩半的存活率差**要重現得出來（實測 0.410 / 0.799）——
     這是整件事的重點，一維曲線就是敗在這裡

驗證用的是「把模型套回觀測星本身」。這只證明選擇函數描述得了那幾把刀，
不證明前向模型正確；後者要靠注入回收測試。

======================================================================
【這支程式在做什麼】
======================================================================
第 2 步的品質篩選會砍掉一部分成員星（訊噪比太低、BP/RP 被汙染），而且砍得
不平均：暗的紅星被砍得比暗的藍星多很多。前向模型生成合成星團時，必須用
**同樣的刀**砍合成星，合成色光圖才能跟觀測比。這支程式就是把那幾把刀
做成一個「給一顆星的星等與顏色，判斷它會不會被留下」的模型（選擇函數）：
  1. 用整片天區所有星，把每個波段的訊噪比寫成「星等的函數 + 顏色的線性項」
  2. 用成員星量出「BP/RP 超額那一刀」在每個星等砍掉多少比例
  3. 把模型套回觀測成員星，檢查預測的存活率跟實際吻不吻合（三項驗收標準）
  4. 存成 data/selection.npz
執行方式：python scripts/data_prep/build_selection.py
需要先有：data/m45_r5_g18_plx4.csv、data/cmd_members.csv、data/comparison.csv
後續使用者：fit_real.py、traditional_accounting.py、injection_recovery.py 等
（透過 pipeline/selection.py 的 load() 讀入）

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  csv           csv.DictReader 逐列讀 CSV（每列一個字典）
  sys, pathlib  設定 import 路徑
第三方套件：
  numpy（np）
      np.histogram        數每個星等區間各有幾顆星
      np.arange           等間隔數列（區間邊界）
      np.interp           一維線性內插
      np.clip             把值限制在範圍內
      np.random.default_rng  亂數產生器；.normal 常態亂數、.random 0–1 均勻亂數
      np.savez            把多個陣列存成一個 .npz
本專案其他模組：
  pipeline/config.py      cfgmod.load()：讀 config.toml
  pipeline/selection.py   選擇函數本體：
      selmod.build(星等, 顏色, 訊噪比, 門檻)
          對 G、BP、RP 各迴歸一次 log10(訊噪比) = 該星等分箱的基準值
          + 顏色係數 × 顏色，並量出每個星等的殘差散布 → 回傳 SelectionModel
      model.keep(g, bp, rp, z, u)
          對每顆星：預測的 log10(訊噪比) + 散布 × 常態亂數 z，
          三個波段都 ≥ 門檻才留下；再以「BP/RP 超額存活率」為機率，
          用均勻亂數 u 決定是否留下 → 回傳布林遮罩
      model.describe()      印出每個波段的迴歸摘要
      selmod.BANDS          ("g", "bp", "rp")
  scripts/diagnostics/selection_probe.py
      load()   讀出「成員機率 ≥ 0.7、G ≥ 4 的星」各自的星等、訊噪比，
               以及它有沒有出現在 cmd_members.csv（= 有沒有通過篩選，欄位 kept）

======================================================================
【(b) 用到的參數與意義】
======================================================================
沒有命令列參數。從 config.toml [step2_cmd] 讀：
  min_flux_snr_g = 50、min_flux_snr_bp = 20、min_flux_snr_rp = 20
      三把訊噪比刀的門檻（跟第 2 步實際篩選用的完全一樣）
寫死在程式裡的數值：
  bin_width = 1.0     BP/RP 超額存活率曲線的星等區間寬度
  n_rep = 40          驗證時重複抽亂數的次數（取平均）
  驗收門檻：整體差 < 0.02、逐星等最大差 < 0.08、紅減藍差 < 0.10
輸出 data/selection.npz 的內容：
  {波段}_mag／_level／_colour_coef／_scatter  訊噪比模型的係數
  thr_{波段}                                   訊噪比門檻
  excess_g, excess_f                           BP/RP 超額那一刀的存活率曲線

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 112–137 行｜load_all_field()：讀整片天區的星等與訊噪比（迴歸用）
  核心 2｜第 140–167 行｜excess_curve()：量 BP/RP 超額那一刀在各星等的存活率
  核心 3｜第 171–186 行｜main() 建模型：迴歸訊噪比關係＋接上超額曲線
  核心 4｜第 188–245 行｜main() 驗證：模型套回觀測成員星，比對三項驗收標準
  核心 5｜第 247–255 行｜main() 存檔

======================================================================
【(d) 整體流程】
======================================================================
  讀 config 的三個訊噪比門檻
    → 讀整片天區所有星 → 對 G、BP、RP 各迴歸「訊噪比 vs (星等, 顏色)」
    → 讀成員星 → 先排除被訊噪比解釋掉的星，量剩下的星在每個星等被 BP/RP
      超額砍掉的比例 → 得到存活率曲線
    → 驗證：對每顆觀測成員星重複 40 次「抽亂數 → 模型判斷留不留」取平均
      → 跟它實際有沒有被留下比：整體、逐星等、G ≥ 17 紅半邊 vs 藍半邊
    → 印出三項驗收是否通過（只印，不會因未通過而中止）
    → 存 data/selection.npz
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

# ↓ repo 根目錄（本檔在 scripts/data_prep/，往上三層），加進 import 路徑
HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import selection as selmod       # noqa: E402
from scripts.diagnostics.selection_probe import load, G_BRIGHT  # noqa: E402


# ═══════════════ 核心 1：讀整片天區（訊噪比迴歸用） ═══════════════
def load_all_field():
    """原始星表的全部星，用來迴歸訊噪比關係（星數多、星等涵蓋廣）。

    訊噪比是測光的性質、與是不是成員無關，所以用全體迴歸統計較穩；
    而且場星提供了成員樣本裡缺乏的藍色端，顏色係數才定得住。
    """
    # ↓ 要讀的六個欄位：三個波段的星等與流量訊噪比
    cols = ("phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag",
            "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
            "phot_rp_mean_flux_over_error")
    # ↓ acc：每個欄位一個清單，逐列累加
    acc = {c: [] for c in cols}
    with open(HERE / "data" / "m45_r5_g18_plx4.csv", newline="",
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for c in cols:
                v = r[c]
                # ↓ 空字串、"null"、"NaN" 都當成缺值（NaN）
                acc[c].append(float(v) if v not in ("", "null", "NaN")
                              else np.nan)
    # ↓ 清單轉成 numpy 陣列，整理成 {波段: 星等}、{波段: 訊噪比}、顏色
    a = {c: np.array(v, float) for c, v in acc.items()}
    mags = {"g": a[cols[0]], "bp": a[cols[1]], "rp": a[cols[2]]}
    snrs = {"g": a[cols[3]], "bp": a[cols[4]], "rp": a[cols[5]]}
    return mags, snrs, a[cols[1]] - a[cols[2]]


# ═══════════════ 核心 2：BP/RP 超額那一刀的存活率曲線 ═══════════════
def excess_curve(d, bin_width=1.0):
    """BP/RP 流量超額那一刀的存活率對 G 星等的曲線。

    這一刀砍的是「孔徑測光被鄰居或星雲汙染」，不是星本身的性質，
    實測對顏色近乎中性（G>=17 的紅藍差只有 +0.014），所以用一維近似。
    """
    # ↓ snr：會被訊噪比刀（或缺 BP/RP 星等）砍掉的星
    snr = ((d["snr_bp"] < 20) | (d["snr_rp"] < 20) | (d["snr_g"] < 50)
           | ~np.isfinite(d["bp"]) | ~np.isfinite(d["rp"]))
    # 只看沒被訊噪比解釋掉的那一批，避免同一顆星被兩把刀重複計入
    pool = ~snr
    # ↓ 在這一批裡卻沒被留下的 = 被 BP/RP 超額砍掉的
    removed = pool & ~d["kept"]
    # ↓ 以 1 星等為一格切 G 星等區間
    edges = np.arange(np.floor(d["g"][pool].min()),
                      np.ceil(d["g"][pool].max()) + bin_width, bin_width)
    # ↓ 每格的總星數與被砍星數
    n_all, _ = np.histogram(d["g"][pool], edges)
    n_rm, _ = np.histogram(d["g"][removed], edges)
    centres = 0.5 * (edges[:-1] + edges[1:])
    # ↓ 只信任至少 10 顆星的格子；存活率 = 1 − 被砍比例
    good = n_all >= 10
    frac = np.ones(len(centres))
    frac[good] = 1.0 - n_rm[good] / n_all[good]
    # ↓ 星數不足的格子，用相鄰可信格子內插補上
    frac = np.interp(centres, centres[good], frac[good])
    return centres, np.clip(frac, 0.0, 1.0)


def main():
    # ═══════════════ 核心 3：建立選擇函數 ═══════════════
    cfg = cfgmod.load()
    c2 = cfg.step2_cmd
    # ↓ 三把訊噪比刀的門檻，直接取第 2 步用的同一組數值
    thr = {"g": c2.min_flux_snr_g, "bp": c2.min_flux_snr_bp,
           "rp": c2.min_flux_snr_rp}

    print("迴歸訊噪比關係（全場星）：")
    mags, snrs, colour = load_all_field()
    # ↓ 三個波段各迴歸一次訊噪比關係，包成 SelectionModel
    model = selmod.build(mags, colour, snrs, thr, verbose=True)

    # ↓ 讀成員星（含「有沒有通過篩選」），量出超額那一刀的存活率曲線，接到模型上
    d = load()
    model.excess_curve = excess_curve(d)
    print("\n" + model.describe())

    # ═══════════════ 核心 4：套回觀測成員星驗證 ═══════════════
    # --- 驗證：把模型套回觀測星本身 ---
    # ↓ 固定種子 0 的亂數產生器，結果可重現
    rng = np.random.default_rng(0)
    n_rep = 40          # 訊噪比散布是隨機的，多抽幾次取平均
    g, bp, rp = d["g"], d["bp"], d["rp"]
    # ↓ 三個星等都有值的星才驗證
    fin = np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp)
    # ↓ pred：每顆星「被模型判定留下」的平均次數比例 = 預測存活機率
    pred = np.zeros(fin.sum())
    for _ in range(n_rep):
        z = rng.normal(0, 1, fin.sum())
        u = rng.random(fin.sum())
        pred += model.keep(g[fin], bp[fin], rp[fin], z, u)
    pred /= n_rep
    # ↓ obs：每顆星實際有沒有被留下（1 或 0）
    obs = d["kept"][fin].astype(float)
    colour_m = (bp - rp)[fin]
    gg = g[fin]

    # ↓ 驗收 1：整體存活率
    print(f"\n{'='*70}\n驗證：把選擇函數套回觀測星\n{'='*70}")
    print(f"整體存活率  觀測 {obs.mean():.3f}   模型 {pred.mean():.3f}   "
          f"差 {pred.mean()-obs.mean():+.3f}")

    # ↓ 驗收 2：G 8–18 每 1 星等一格，比對存活率，記錄最大差距
    print(f"\n{'G 區間':>13}{'星數':>7}{'觀測':>9}{'模型':>9}{'差':>9}")
    worst = 0.0
    for lo in np.arange(8, 18, 1.0):
        m = (gg >= lo) & (gg < lo + 1)
        if m.sum() < 20:
            continue
        o, p = obs[m].mean(), pred[m].mean()
        worst = max(worst, abs(p - o))
        print(f"{lo:5.1f}–{lo+1:<7.1f}{m.sum():>7}{o:>9.3f}{p:>9.3f}{p-o:>+9.3f}")
    print(f"  逐星等最大誤差 {worst:.3f}")

    # ↓ 驗收 3：G ≥ 17 的星依顏色中位數分成紅、藍兩半，比「紅減藍」的存活率差
    faint = gg >= 17.0
    med = np.median(colour_m[faint])
    red, blue = faint & (colour_m > med), faint & (colour_m <= med)
    print(f"\nG>=17 顏色分半（模型能不能重現這一項是重點）：")
    print(f"{'':>10}{'觀測':>9}{'模型':>9}{'差':>9}")
    print(f"{'紅半邊':>10}{obs[red].mean():>9.3f}{pred[red].mean():>9.3f}"
          f"{pred[red].mean()-obs[red].mean():>+9.3f}")
    print(f"{'藍半邊':>10}{obs[blue].mean():>9.3f}{pred[blue].mean():>9.3f}"
          f"{pred[blue].mean()-obs[blue].mean():>+9.3f}")
    d_obs = obs[red].mean() - obs[blue].mean()
    d_mod = pred[red].mean() - pred[blue].mean()
    print(f"{'紅減藍':>10}{d_obs:>9.3f}{d_mod:>9.3f}{d_mod-d_obs:>+9.3f}")

    # ↓ 印出三項驗收結果（⚠ 只印出來，未通過也不會中止或拒絕存檔）
    ok1 = abs(pred.mean() - obs.mean()) < 0.02
    ok2 = worst < 0.08
    ok3 = abs(d_mod - d_obs) < 0.10
    print(f"\n驗收：整體 {'通過' if ok1 else '未過'}、"
          f"逐星等 {'通過' if ok2 else '未過'}、"
          f"顏色相依 {'通過' if ok3 else '未過'}")

    # ═══════════════ 核心 5：存檔 ═══════════════
    # ↓ 每個波段的四組係數、三個門檻、超額曲線，全部存進同一個 .npz
    np.savez(HERE / "data" / "selection.npz",
             **{f"{b}_{k}": np.asarray(model.fits[b][k])
                for b in selmod.BANDS
                for k in ("mag", "level", "colour_coef", "scatter")},
             **{f"thr_{b}": thr[b] for b in selmod.BANDS},
             excess_g=model.excess_curve[0], excess_f=model.excess_curve[1])
    print("寫入 data/selection.npz")


if __name__ == "__main__":
    main()
