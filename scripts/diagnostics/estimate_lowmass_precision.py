# -*- coding: utf-8 -*-
"""D19：低質量段會多幾顆成員星、低質量段冪次能量到多準。

**不做擬合**，回答兩個問題：

1. 現有成員在各質量區間有幾顆，D19 延伸到 G<20 大約會多幾顆？
   新增數用 HR23（Hunt & Reffert 2023）在 G 18–20 的成員數，乘上本專案
   在 G<18 對 HR23 的比例（含測光品質切）估計。HR23 本身也建立在 Gaia
   天測上，暗端完整度會下降，所以這是**上限傾向的估計**，實際數字要等
   Stage 2 成員判定重跑。
2. 截斷冪律斜率的統計誤差下限（Fisher 資訊）：
       sigma_p = 1 / sqrt(N * Var(ln m))
   Var(ln m) 在截斷冪律分布下計算，區間越寬（槓桿越長）越大，
   因此 sigma_p 越小。這是「質量
   完美已知、沒有雙星」的理想下限，所以另外拿 P6b v2 注入回收在**現有
   深度**實測的回收散布去校準，看理想值跟前向模型實際表現差多少。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod          # noqa: E402
from pipeline import isochrones as isomod      # noqa: E402
from pipeline import step5_imf                 # noqa: E402
from pipeline.step3_age import _Ext            # noqa: E402

CONFIG_C_LOGAGE = 8.033      # 出處同 assess_colour_options.py
CONFIG_C_AV = 0.383
P_TRUE = 1.3
M_BREAK = 0.5
M_NOW = 0.173                # G = 18 對應的質量（C16，本專案閘門重現 0.1725）
M_EXT = 0.090                # D19 Stage 0 的質量下限


def fisher_sigma(n, lo, hi, p):
    lnm = np.linspace(np.log(lo), np.log(hi), 20001)
    w = np.exp(lnm * (1.0 - p))          # dN/dln m 正比 m^(1-p)
    w /= np.trapezoid(w, lnm)
    mu = np.trapezoid(w * lnm, lnm)
    var = np.trapezoid(w * (lnm - mu) ** 2, lnm)
    return 1.0 / np.sqrt(n * var)


def main():
    cfg = cfgmod.load(None)
    c3 = cfg.step3_age
    grid = isomod.load_grid(isomod.CACHE / (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))
    iso = isomod.isochrone_at(grid, CONFIG_C_LOGAGE, c3.metallicity_mh)
    ext = _Ext(cfg.step2_cmd.ext_coeff_g, cfg.step2_cmd.ext_coeff_bp,
               cfg.step2_cmd.ext_coeff_rp)
    mem = pd.read_csv(HERE / "data" / "cmd_members.csv")
    plx = np.asarray(mem["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    m = step5_imf.assign_masses(np.asarray(mem["phot_g_mean_mag"], float),
                                iso, dm, CONFIG_C_AV, ext)

    print("現有成員（單星質量，config C）")
    for lo, hi in [(0.08, M_NOW), (M_NOW, 0.30), (0.30, M_BREAK), (M_BREAK, 2.5)]:
        print(f"  {lo:.3f}-{hi:.3f} M☉  {int(((m >= lo) & (m < hi)).sum()):5d}")
    n_now = int(((m >= M_NOW) & (m < M_BREAK)).sum())

    hr = pd.read_csv(HERE / "data" / "hr23_Melotte_22.csv")
    g = np.asarray(hr["Gmag"], float)
    n_hr18 = int((g < 18).sum())
    n_hr_add = int(((g >= 18) & (g < 20)).sum())
    recall = len(mem) / n_hr18
    n_add = int(round(n_hr_add * recall))
    print(f"\nHR23：G<18 有 {n_hr18} 顆，G 18–20 有 {n_hr_add} 顆")
    print(f"本專案對 HR23 在 G<18 的比例 {recall:.3f} -> 估計新增 {n_add} 顆"
          f"（上限 {n_hr_add}）")

    d = json.loads((HERE / "results" /
                    "inject_lowmass_p6b_v2_validation.json").read_text("utf-8"))
    emp = float(np.sqrt(np.mean(np.square(d["p_recovered_sample_sd"]))))
    s_now = fisher_sigma(n_now, M_NOW, M_BREAK, P_TRUE)
    infl = emp / s_now
    print(f"\n低質量段冪次統計誤差（真值 p = {P_TRUE}）")
    print(f"  現有深度 [{M_NOW}, {M_BREAK}] N={n_now}：理想 {s_now:.3f}，"
          f"P6b v2 實測回收散布 {emp:.3f}（比值 {infl:.2f}）")
    out = {"n_now": n_now, "n_add": n_add, "n_add_upper": n_hr_add,
           "sigma_now_fisher": s_now, "sigma_now_p6b": emp}
    for tag, add in (("est", n_add), ("upper", n_hr_add)):
        s = fisher_sigma(n_now + add, M_EXT, M_BREAK, P_TRUE)
        print(f"  延伸後   [{M_EXT}, {M_BREAK}] N={n_now + add}：理想 {s:.3f}，"
              f"按實測比值換算 {s * infl:.3f}")
        out[f"sigma_ext_{tag}"] = s * infl
    print("  對照：現行 Kroupa 外部不確定度 ±0.5")
    print("  注意：P6b v2 每個真值只有 3 次試驗，實測散布本身的不確定度約 ±40%；"
          "且回收對真值的斜率 0.80（向中間壓縮約 20%），那是偏差不是雜訊，"
          "不含在上面的數字裡。")
    np.savez(HERE / "results" / "d19_lowmass_precision.npz", **out)
    print("\n寫入 results/d19_lowmass_precision.npz")


if __name__ == "__main__":
    main()
