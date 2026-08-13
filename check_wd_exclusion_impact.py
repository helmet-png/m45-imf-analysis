# -*- coding: utf-8 -*-
"""A6（wd_exclude_rerun）：`assign_masses()` 加顏色一致性檢查後，量化對
實際引用頭條數字的影響。

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

量三個真正在用／有意義的設定：
  (A) alpha_naive —— `run_pipeline.py` 第 5 步方法 A，用
      `results/step4_fit.npz` 記錄的 (logage=8.0, av=0.15)、
      `config.toml` 的質量範圍 0.30-2.50
  (B) traditional_accounting.py 主表「全當單星」變體（跟前向模型對齊）——
      p2_final2 isochrone（logage=8.033, av=0.383, mh=0.0）、質量範圍
      0.50-2.50。**這顆白矮星在此範圍外，不受這個設定影響**
  (C) traditional_accounting.py「附錄」變體 —— 同一條 p2_final2
      isochrone，但用較寬的質量範圍 0.30-2.50（跟 config.toml 的
      mass_min/mass_max 一致）。**這是唯一一個測過、白矮星真的落在擬合
      樣本裡的設定**
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


def report(label, mag, color, sid, iso, dm, av, ext, m_lo, m_hi):
    m_before = step5_imf.assign_masses(mag, iso, dm, av, ext)
    m_after = step5_imf.assign_masses(mag, iso, dm, av, ext, obs_color=color)
    inrange_before = np.isfinite(m_before) & (m_before >= m_lo) & (m_before <= m_hi)
    inrange_after = np.isfinite(m_after) & (m_after >= m_lo) & (m_after <= m_hi)
    dropped = np.where(inrange_before & ~inrange_after)[0]

    a_before = step5_imf.mle_powerlaw(m_before, m_lo, m_hi)
    a_after = step5_imf.mle_powerlaw(m_after, m_lo, m_hi)

    wd_idx = np.where(sid == WD_SOURCE_ID)[0]
    if len(wd_idx) == 1:
        i = wd_idx[0]
        wd_note = (f"source_id={WD_SOURCE_ID}：mass_before={m_before[i]:.3f}，"
                  f"在此範圍內={bool(inrange_before[i])}")
    else:
        wd_note = "（樣本中沒有這顆星）"

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"  修正前：alpha = {a_before['alpha']:.4f} +/- "
          f"{a_before['alpha_err']:.4f}  (n={a_before['n']:,})")
    print(f"  修正後：alpha = {a_after['alpha']:.4f} +/- "
          f"{a_after['alpha_err']:.4f}  (n={a_after['n']:,})")
    print(f"  差異：{a_after['alpha'] - a_before['alpha']:+.4f}"
          f"  （實際剔除 {len(dropped)} 顆，逐顆列出：）")
    for i in dropped:
        tag = "  <== 已知白矮星" if sid[i] == WD_SOURCE_ID else ""
        print(f"    source_id={sid[i]}  G={mag[i]:.3f}  bp_rp={color[i]:.3f}"
              f"  mass_before={m_before[i]:.3f}{tag}")
    print(f"  白矮星狀態：{wd_note}")
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
    CURRENT_LOGAGE, CURRENT_AV = 8.033, 0.383

    # (A) alpha_naive
    f4 = dict(np.load(HERE / "results" / "step4_fit.npz"))
    iso_a = isomod.isochrone_at(grid, float(f4["logage"]),
                                cfg.step3_age.metallicity_mh)
    report("(A) alpha_naive — run_pipeline.py 第5步（logage=%.3f, av=%.3f, "
           "質量範圍 %.2f-%.2f）" % (f4["logage"], f4["av"],
                                    cfg.step5_imf.mass_min,
                                    cfg.step5_imf.mass_max),
           mag, color, sid, iso_a, dm, float(f4["av"]), ext,
           cfg.step5_imf.mass_min, cfg.step5_imf.mass_max)

    # (B) traditional_accounting.py 主表 — 跟前向模型對齊的範圍
    iso_b = isomod.isochrone_at(grid, CURRENT_LOGAGE, 0.0)
    report("(B) traditional_accounting 主表「全當單星」— p2_final2 "
           "isochrone、對齊範圍（logage=%.3f, av=%.3f, 質量範圍 0.50-2.50）"
           % (CURRENT_LOGAGE, CURRENT_AV),
           mag, color, sid, iso_b, dm, CURRENT_AV, ext, 0.50,
           cfg.step5_imf.mass_max)

    # (C) traditional_accounting.py 附錄 — 同 isochrone，較寬範圍
    report("(C) traditional_accounting 附錄「全當單星」— p2_final2 "
           "isochrone、較寬範圍（logage=%.3f, av=%.3f, 質量範圍 %.2f-%.2f）"
           % (CURRENT_LOGAGE, CURRENT_AV, cfg.step5_imf.mass_min,
              cfg.step5_imf.mass_max),
           mag, color, sid, iso_b, dm, CURRENT_AV, ext,
           cfg.step5_imf.mass_min, cfg.step5_imf.mass_max)


if __name__ == "__main__":
    main()
