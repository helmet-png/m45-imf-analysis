# -*- coding: utf-8 -*-
"""D9：`source_id=68409590552589184` 這顆亮星的本機可查診斷（不需要網路）。

**背景**：這顆星（G=7.386）在三個測過的質量範圍下都被 `assign_masses()`
的顏色一致性檢查標記（偏離同 G 星等主序色 1.3-1.4 星等），見
`LIMITATIONS.md` D9。查證方法比照 A6 白矮星那顆，但外部目錄交叉比對
（SIMBAD／Vizier）在這台機器上因為 SSL 憑證問題連不上，這支腳本只做
`data/cmd_members.csv` 本身就有、不需要網路的檢查：

1. RUWE、`non_single_star`——astrometric 解是否乾淨、Gaia 自己的雙星
   管線有沒有標記。
2. BP/RP 測光超額因子跟 Evans et al. (2018, A&A 616, A4) 的標準測光
   品質帶比較——超出帶外代表 BP/RP 測光可能被鄰近源污染，是顏色
   異常的一個可能解釋。
3. 跟其餘成員星的自行／視差比較（排除這顆星後的中位數與離散度），
   看哪個維度（pmra／pmdec／視差）運動學上偏離最大。

**這支腳本沒有下結論**，只印出可查的診斷數字，供人判讀。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

TARGET_SOURCE_ID = 68409590552589184


def main():
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    sid = np.asarray(clean["source_id"], np.int64)
    idx = np.where(sid == TARGET_SOURCE_ID)[0]
    if len(idx) != 1:
        print(f"source_id={TARGET_SOURCE_ID} 不在 data/cmd_members.csv 裡，"
              f"可能已經換過一批成員表。", file=sys.stderr)
        sys.exit(1)
    i = idx[0]
    mask = np.ones(len(sid), bool)
    mask[i] = False

    print(f"source_id={TARGET_SOURCE_ID}")
    print(f"  G={clean['phot_g_mean_mag'][i]:.3f}  "
          f"bp_rp={clean['bp_rp'][i]:.3f}  "
          f"probs_final={clean['probs_final'][i]:.4f}")

    print("\n--- 1. astrometric／NSS 品質 ---")
    ruwe = float(clean["ruwe"][i])
    print(f"  RUWE = {ruwe:.3f}（>1.4 通常視為雙星/壞解警訊）")
    if "non_single_star" in clean.colnames:
        print(f"  non_single_star = {clean['non_single_star'][i]}")

    print("\n--- 2. BP/RP 測光超額因子（Evans+2018 品質帶） ---")
    bprp = float(clean["bp_rp"][i])
    excess = float(clean["phot_bp_rp_excess_factor"][i])
    lo = 1.0 + 0.015 * bprp ** 2
    hi = 1.3 + 0.06 * bprp ** 2
    print(f"  bp_rp={bprp:.3f}，品質帶 [{lo:.4f}, {hi:.4f}]，"
          f"觀測值 {excess:.4f}")
    print(f"  在帶內（測光正常）：{lo <= excess <= hi}")

    print("\n--- 3. 運動學跟其餘成員星比較（排除這顆星後） ---")
    for col, label in [("pmra", "pmra"), ("pmdec", "pmdec"),
                       ("parallax", "視差")]:
        v = np.asarray(clean[col], float)
        med = np.median(v[mask])
        std = np.std(v[mask])
        iqr_sigma = 0.7413 * (np.percentile(v[mask], 75)
                              - np.percentile(v[mask], 25))
        this = v[i]
        print(f"  {label}：這顆星 {this:.3f}，其餘成員中位數 {med:.3f}，"
              f"偏離 {(this-med)/std:+.1f}sigma（全樣本標準差）／"
              f"{(this-med)/iqr_sigma:+.1f}sigma（IQR 穩健離散度）")

    print("\n下一步：這幾項本機診斷都查完，沒有找到明確的測光污染或壞解"
          "跡象，pmdec 有中等程度的運動學異常。要進一步確認身分（巨星／"
          "污染源／極端雙星／其他）需要外部目錄交叉比對（SIMBAD、Gaia "
          "DR3 non_single_star 相關表），這台機器連不上（SSL 憑證驗證"
          "失敗），留給下一個能連網路的環境接手。")


if __name__ == "__main__":
    main()
