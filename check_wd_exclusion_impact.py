# -*- coding: utf-8 -*-
"""A6（wd_exclude_rerun、rv_outlier_member_exclude）：兩個已確認非成員
天體的排除機制，量化對實際引用頭條數字的影響。

**背景**：`LIMITATIONS.md` A6 記錄 `data/cmd_members.csv` 混進至少一顆
白矮星（source_id=66697547870378368，Gentile-Fusillo+2021 命中 Pwd=0.999），
`pipeline/step5_imf.assign_masses()` 只用 G 星等一維反查質量，這顆星會被
誤判成一顆質量落在下限附近的主序星。`assign_masses()` 已加上可選的
`obs_color` 顏色一致性檢查（偏離主序色 >0.4 星等回傳 NaN）。這支腳本
只做查證：**不改動 pipeline，不覆寫任何 tracked 結果檔**，量出加了檢查
前後 alpha 差多少，數字直接寫進 LIMITATIONS.md，不用「應該影響很小」
帶過。

**CodeRabbit review 抓到的真的問題（2026-08-13 修正）**：第一版只挑了
一個「跟前向模型對齊」的質量範圍（0.50-2.50）當作驗收設定，沒有先確認
這顆白矮星的假質量到底落不落在這個範圍內就直接下結論「只剔除這顆白矮星」。
實際查證後發現：這顆白矮星的假質量在**所有測過的設定下都落在 0.276-0.307
之間**，剛好卡在 0.30-0.50 這個邊界帶——在 0.50-2.50 範圍下它根本不在
擬合樣本裡（不管有沒有這個修正都一樣），色檢查在那個範圍剔除的其實是
*另一顆*星（`source_id=68409590552589184`）。**這支腳本現在明確列出每個
設定下實際被剔除的 source_id，不再只挑一顆星確認、假設其他星不受影響。**

**第二顆非成員天體**：另一個並行 session 用 `check_giant_subgiant_
contamination.py`（RV+logg 交叉比對）獨立找到 `source_id=64895139073954944`
（logg_gspphot=4.00、Teff=3317K、RV=−93.65±5.08 km/s，偏離 bulk_rv 達
19.5σ）。這顆星的顏色（bp_rp=2.516）跟真成員無異，`assign_masses()` 的
顏色檢查抓不到，改用 `pipeline/step5_imf.exclude_confirmed_non_members()`
（一個小型、有清楚出處的已確認非成員名單）排除。

量三個真正在用／有意義的設定，每個都比較四種情境（都不排除／只排白矮星／
只排 RV 星／兩者都排）：
  (A) alpha_naive —— `run_pipeline.py` 第 5 步方法 A，用
      `results/step4_fit.npz` 記錄的 (logage=8.0, av=0.15)、
      `config.toml` 的質量範圍 0.30-2.50
  (B) traditional_accounting.py 主表「全當單星」變體（跟前向模型對齊）——
      p2_final2 isochrone（logage=8.033, av=0.383, mh=0.0）、質量範圍
      0.50-2.50。**這兩顆星都在此範圍外，完全不受這個設定影響**
  (C) traditional_accounting.py「附錄」變體 —— 同一條 p2_final2
      isochrone，但用較寬的質量範圍 0.30-2.50（跟 config.toml 的
      mass_min/mass_max 一致）。**這是兩顆星都真的落在擬合樣本裡的設定**
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import step3_age, step5_imf                    # noqa: E402

WD_SOURCE_ID = 66697547870378368
GRID_FILE = "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"


def report(label, mag, color, sid, iso, dm, av, ext, m_lo, m_hi, rv_excl):
    m_base = step5_imf.assign_masses(mag, iso, dm, av, ext)
    m_color = step5_imf.assign_masses(mag, iso, dm, av, ext, obs_color=color)
    m_rv = step5_imf.assign_masses(mag[~rv_excl], iso, dm, av, ext)
    m_both = step5_imf.assign_masses(mag[~rv_excl], iso, dm, av, ext,
                                     obs_color=color[~rv_excl])

    a_base = step5_imf.mle_powerlaw(m_base, m_lo, m_hi)
    a_color = step5_imf.mle_powerlaw(m_color, m_lo, m_hi)
    a_rv = step5_imf.mle_powerlaw(m_rv, m_lo, m_hi)
    a_both = step5_imf.mle_powerlaw(m_both, m_lo, m_hi)

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"  基準（都不排除）    alpha = {a_base['alpha']:.4f} +/- "
          f"{a_base['alpha_err']:.4f}  (n={a_base['n']:,})")
    print(f"  只排白矮星（顏色）  alpha = {a_color['alpha']:.4f}"
          f"  差異 {a_color['alpha']-a_base['alpha']:+.4f}"
          f"  (n={a_color['n']:,})")
    print(f"  只排 RV 離群星      alpha = {a_rv['alpha']:.4f}"
          f"  差異 {a_rv['alpha']-a_base['alpha']:+.4f}"
          f"  (n={a_rv['n']:,})")
    print(f"  兩者都排            alpha = {a_both['alpha']:.4f}"
          f"  差異 {a_both['alpha']-a_base['alpha']:+.4f}"
          f"  (n={a_both['n']:,})")

    inrange_before = np.isfinite(m_base) & (m_base >= m_lo) & (m_base <= m_hi)
    inrange_after = np.isfinite(m_color) & (m_color >= m_lo) & (m_color <= m_hi)
    dropped = np.where(inrange_before & ~inrange_after)[0]
    print(f"  顏色檢查實際剔除 {len(dropped)} 顆：")
    for i in dropped:
        tag = "  <== 已知白矮星" if sid[i] == WD_SOURCE_ID else ""
        print(f"    source_id={sid[i]}  G={mag[i]:.3f}  bp_rp={color[i]:.3f}"
              f"  mass_before={m_base[i]:.3f}{tag}")

    for i in np.where(rv_excl)[0]:
        in_range = m_lo <= m_base[i] <= m_hi
        print(f"  RV 離群星 source_id={sid[i]}：mass_before={m_base[i]:.3f}，"
              f"在此範圍內={in_range}")
    return a_base, a_color, a_rv, a_both


def main():
    cfg = cfgmod.load()
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    sid = np.asarray(clean["source_id"], np.int64)
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (
        np.median(plx) - cfg.step3_age.parallax_zero_point)) - 5.0
    ext = step3_age._Ext(cfg.step2_cmd.ext_coeff_g,
                         cfg.step2_cmd.ext_coeff_bp,
                         cfg.step2_cmd.ext_coeff_rp)
    grid = isomod.load_grid(isomod.CACHE / GRID_FILE)
    CURRENT_LOGAGE, CURRENT_AV = 8.033, 0.383
    rv_excl = step5_imf.exclude_confirmed_non_members(sid)
    print(f"RV 離群星排除名單：{int(rv_excl.sum())} 顆 "
          f"（source_id={sid[rv_excl].tolist()}）")

    # (A) alpha_naive
    f4 = dict(np.load(HERE / "results" / "step4_fit.npz"))
    iso_a = isomod.isochrone_at(grid, float(f4["logage"]),
                                cfg.step3_age.metallicity_mh)
    report("(A) alpha_naive — run_pipeline.py 第5步（logage=%.3f, av=%.3f, "
           "質量範圍 %.2f-%.2f）" % (f4["logage"], f4["av"],
                                    cfg.step5_imf.mass_min,
                                    cfg.step5_imf.mass_max),
           mag, color, sid, iso_a, dm, float(f4["av"]), ext,
           cfg.step5_imf.mass_min, cfg.step5_imf.mass_max, rv_excl)

    # (B) traditional_accounting.py 主表 — 跟前向模型對齊的範圍
    iso_b = isomod.isochrone_at(grid, CURRENT_LOGAGE, 0.0)
    report("(B) traditional_accounting 主表「全當單星」— p2_final2 "
           "isochrone、對齊範圍（logage=%.3f, av=%.3f, 質量範圍 0.50-2.50）"
           % (CURRENT_LOGAGE, CURRENT_AV),
           mag, color, sid, iso_b, dm, CURRENT_AV, ext, 0.50,
           cfg.step5_imf.mass_max, rv_excl)

    # (C) traditional_accounting.py 附錄 — 同 isochrone，較寬範圍
    report("(C) traditional_accounting 附錄「全當單星」— p2_final2 "
           "isochrone、較寬範圍（logage=%.3f, av=%.3f, 質量範圍 %.2f-%.2f）"
           % (CURRENT_LOGAGE, CURRENT_AV, cfg.step5_imf.mass_min,
              cfg.step5_imf.mass_max),
           mag, color, sid, iso_b, dm, CURRENT_AV, ext,
           cfg.step5_imf.mass_min, cfg.step5_imf.mass_max, rv_excl)


if __name__ == "__main__":
    main()
