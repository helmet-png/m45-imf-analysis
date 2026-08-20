# -*- coding: utf-8 -*-
"""建立測光品質篩選的選擇函數，並驗證它重現得出觀測到的存活率樣態。

驗收標準（在建立之前先訂好，避免事後挑指標）：
  1. 整體存活率誤差 < 0.02
  2. 逐星等的存活率，最大誤差 < 0.08
  3. **G>=17 紅藍兩半的存活率差**要重現得出來（實測 0.410 / 0.799）——
     這是整件事的重點，一維曲線就是敗在這裡

驗證用的是「把模型套回觀測星本身」。這只證明選擇函數描述得了那幾把刀，
不證明前向模型正確；後者要靠注入回收測試。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import selection as selmod       # noqa: E402
from selection_probe import load, G_BRIGHT     # noqa: E402


def load_all_field():
    """原始星表的全部星，用來迴歸訊噪比關係（星數多、星等涵蓋廣）。

    訊噪比是測光的性質、與是不是成員無關，所以用全體迴歸統計較穩；
    而且場星提供了成員樣本裡缺乏的藍色端，顏色係數才定得住。
    """
    cols = ("phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag",
            "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
            "phot_rp_mean_flux_over_error")
    acc = {c: [] for c in cols}
    with open(HERE / "data" / "m45_r5_g18_plx4.csv", newline="",
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for c in cols:
                v = r[c]
                acc[c].append(float(v) if v not in ("", "null", "NaN")
                              else np.nan)
    a = {c: np.array(v, float) for c, v in acc.items()}
    mags = {"g": a[cols[0]], "bp": a[cols[1]], "rp": a[cols[2]]}
    snrs = {"g": a[cols[3]], "bp": a[cols[4]], "rp": a[cols[5]]}
    return mags, snrs, a[cols[1]] - a[cols[2]]


def excess_curve(d, bin_width=1.0):
    """BP/RP 流量超額那一刀的存活率對 G 星等的曲線。

    這一刀砍的是「孔徑測光被鄰居或星雲汙染」，不是星本身的性質，
    實測對顏色近乎中性（G>=17 的紅藍差只有 +0.014），所以用一維近似。
    """
    snr = ((d["snr_bp"] < 20) | (d["snr_rp"] < 20) | (d["snr_g"] < 50)
           | ~np.isfinite(d["bp"]) | ~np.isfinite(d["rp"]))
    # 只看沒被訊噪比解釋掉的那一批，避免同一顆星被兩把刀重複計入
    pool = ~snr
    removed = pool & ~d["kept"]
    edges = np.arange(np.floor(d["g"][pool].min()),
                      np.ceil(d["g"][pool].max()) + bin_width, bin_width)
    n_all, _ = np.histogram(d["g"][pool], edges)
    n_rm, _ = np.histogram(d["g"][removed], edges)
    centres = 0.5 * (edges[:-1] + edges[1:])
    good = n_all >= 10
    frac = np.ones(len(centres))
    frac[good] = 1.0 - n_rm[good] / n_all[good]
    frac = np.interp(centres, centres[good], frac[good])
    return centres, np.clip(frac, 0.0, 1.0)


def main():
    cfg = cfgmod.load()
    c2 = cfg.step2_cmd
    thr = {"g": c2.min_flux_snr_g, "bp": c2.min_flux_snr_bp,
           "rp": c2.min_flux_snr_rp}

    print("迴歸訊噪比關係（全場星）：")
    mags, snrs, colour = load_all_field()
    model = selmod.build(mags, colour, snrs, thr, verbose=True)

    d = load()
    model.excess_curve = excess_curve(d)
    print("\n" + model.describe())

    # --- 驗證：把模型套回觀測星本身 ---
    rng = np.random.default_rng(0)
    n_rep = 40          # 訊噪比散布是隨機的，多抽幾次取平均
    g, bp, rp = d["g"], d["bp"], d["rp"]
    fin = np.isfinite(g) & np.isfinite(bp) & np.isfinite(rp)
    pred = np.zeros(fin.sum())
    for _ in range(n_rep):
        z = rng.normal(0, 1, fin.sum())
        u = rng.random(fin.sum())
        pred += model.keep(g[fin], bp[fin], rp[fin], z, u)
    pred /= n_rep
    obs = d["kept"][fin].astype(float)
    colour_m = (bp - rp)[fin]
    gg = g[fin]

    print(f"\n{'='*70}\n驗證：把選擇函數套回觀測星\n{'='*70}")
    print(f"整體存活率  觀測 {obs.mean():.3f}   模型 {pred.mean():.3f}   "
          f"差 {pred.mean()-obs.mean():+.3f}")

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

    ok1 = abs(pred.mean() - obs.mean()) < 0.02
    ok2 = worst < 0.08
    ok3 = abs(d_mod - d_obs) < 0.10
    print(f"\n驗收：整體 {'通過' if ok1 else '未過'}、"
          f"逐星等 {'通過' if ok2 else '未過'}、"
          f"顏色相依 {'通過' if ok3 else '未過'}")

    np.savez(HERE / "data" / "selection.npz",
             **{f"{b}_{k}": np.asarray(model.fits[b][k])
                for b in selmod.BANDS
                for k in ("mag", "level", "colour_coef", "scatter")},
             **{f"thr_{b}": thr[b] for b in selmod.BANDS},
             excess_g=model.excess_curve[0], excess_f=model.excess_curve[1])
    print("寫入 data/selection.npz")


if __name__ == "__main__":
    main()
