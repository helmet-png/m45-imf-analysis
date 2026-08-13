# -*- coding: utf-8 -*-
"""A6（wd_exclude_rerun）：`assign_masses()` 加顏色一致性檢查後，量化對
兩個實際引用頭條數字的影響。

**背景**：`LIMITATIONS.md` A6 記錄 `data/cmd_members.csv` 混進至少一顆
白矮星（source_id=66697547870378368，Gentile-Fusillo+2021 命中 Pwd=0.999），
`pipeline/step5_imf.assign_masses()` 只用 G 星等一維反查質量，這顆星會被
誤判成一顆質量落在下限附近的主序星。`assign_masses()` 已加上可選的
`obs_color` 顏色一致性檢查（偏離主序色 >0.4 星等回傳 NaN）。這支腳本
只做查證：**不改動 pipeline，不覆寫任何 tracked 結果檔**，量出加了檢查
前後 alpha 差多少，數字直接寫進 LIMITATIONS.md，不用「應該影響很小」
帶過。

量兩個真正在用的頭條數字：
  (A) alpha_naive —— `run_pipeline.py` 第 5 步方法 A，用
      `results/step4_fit.npz` 記錄的 (logage=8.0, av=0.15)、
      `config.toml` 的質量範圍 0.30-2.50
  (B) traditional_accounting.py 主表「全當單星」變體 —— 用 p2_final2 最終
      isochrone（CURRENT_LOGAGE=8.033, CURRENT_AV=0.383, mh=0.0）、
      跟前向模型對齊的質量範圍 0.50-2.50（見該檔案開頭說明）
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


def report(label, mag, color, iso, dm, av, ext, m_lo, m_hi, sid):
    m_before = step5_imf.assign_masses(mag, iso, dm, av, ext)
    m_after = step5_imf.assign_masses(mag, iso, dm, av, ext, obs_color=color)
    a_before = step5_imf.mle_powerlaw(m_before, m_lo, m_hi)
    a_after = step5_imf.mle_powerlaw(m_after, m_lo, m_hi)

    idx = np.where(sid == WD_SOURCE_ID)[0]
    wd_note = "（樣本中沒有這顆星）"
    if len(idx) == 1:
        i = idx[0]
        after_str = "NaN" if np.isnan(m_after[i]) else f"{m_after[i]:.3f}"
        wd_note = (f"source_id={WD_SOURCE_ID}：mass_before="
                  f"{m_before[i]:.3f}, mass_after={after_str}")

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"  修正前：alpha = {a_before['alpha']:.4f} +/- "
          f"{a_before['alpha_err']:.4f}  (n={a_before['n']:,})")
    print(f"  修正後：alpha = {a_after['alpha']:.4f} +/- "
          f"{a_after['alpha_err']:.4f}  (n={a_after['n']:,})")
    print(f"  差異：{a_after['alpha'] - a_before['alpha']:+.4f}"
          f"  （剔除 {a_before['n'] - a_after['n']} 顆）")
    print(f"  {wd_note}")
    return a_before, a_after


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

    # (A) alpha_naive：run_pipeline.py 第 5 步實際用的設定
    f4 = dict(np.load(HERE / "results" / "step4_fit.npz"))
    iso_a = isomod.isochrone_at(grid, float(f4["logage"]),
                                cfg.step3_age.metallicity_mh)
    report("(A) alpha_naive — run_pipeline.py 第 5 步（logage=%.3f, av=%.3f, "
           "質量範圍 %.2f-%.2f）" % (f4["logage"], f4["av"],
                                    cfg.step5_imf.mass_min,
                                    cfg.step5_imf.mass_max),
           mag, color, iso_a, dm, float(f4["av"]), ext,
           cfg.step5_imf.mass_min, cfg.step5_imf.mass_max, sid)

    # (B) traditional_accounting.py 主表「全當單星」— p2_final2 isochrone
    CURRENT_LOGAGE, CURRENT_AV = 8.033, 0.383
    iso_b = isomod.isochrone_at(grid, CURRENT_LOGAGE, 0.0)
    report("(B) traditional_accounting 主表「全當單星」— p2_final2 "
           "isochrone（logage=%.3f, av=%.3f, 質量範圍 0.50-2.50）"
           % (CURRENT_LOGAGE, CURRENT_AV),
           mag, color, iso_b, dm, CURRENT_AV, ext, 0.50,
           cfg.step5_imf.mass_max, sid)


if __name__ == "__main__":
    main()
