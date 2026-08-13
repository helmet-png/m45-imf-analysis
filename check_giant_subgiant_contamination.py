# -*- coding: utf-8 -*-
"""A6 延伸：白矮星以外，`cmd_members.csv` 有沒有混進次巨星/巨星？

**背景**：`check_white_dwarf_contamination.py` 的 docstring 誠實列出限制
「只查白矮星，不查其他非主序天體（次巨星、前主序離群點等）」。這支腳本
補上次巨星/巨星這一類——不需要另外查外部目錄，用本地已有的兩份資料
交叉比對：

1. `data/astrophys.csv`（`scripts/data_prep/gaia_astrophys.py` 產生）的
   `logg_gspphot`：M45 只有 ~100 Myr，全部成員應該是主序星或前主序星，
   不該有任何一顆走到次巨星/巨星階段（表面重力顯著偏低）。
2. `data/radial_velocity.csv`（`gaia_radial_velocity.py` 產生）的徑向
   速度：跟星團整體值差很多，代表自行/視差恰好落在星團範圍內只是巧合。

**為什麼不能只看 logg 就下結論**：GSP-Phot 對暗、冷的星本身精確度較差
（訓練樣本較少、簡併較嚴重），單一顆星 logg 偏低有可能只是擬合雜訊，不是
真的次巨星/巨星。這支腳本的作法是**要求兩個獨立訊號都命中**才列為高
置信度候選——單一訊號命中的星只列出來，不下結論。

**做法**：
1. 冷星（Teff<4500K）理論上該是主序矮星，logg 應該落在 ~4.3-5.3；
   `logg_gspphot < 4.3` 列為「偏低，值得懷疑」。
2. 徑向速度偏離 bulk_rv 超過各自誤差棒 5σ（跟 `gaia_radial_velocity.py`
   同一個定義）列為「RV 離群」。
3. **兩者都命中**的星列為高置信度非成員候選。

跑法：`python check_giant_subgiant_contamination.py`（不需要網路，用本地
已有的 `data/astrophys.csv`／`data/radial_velocity.csv`／
`data/cmd_members.csv`，這三份檔案必須先存在——前兩份分別由
`scripts/data_prep/gaia_astrophys.py`／`gaia_radial_velocity.py` 產生）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline.table_compat import Table  # noqa: E402

BULK_RV = 5.343  # HR23，跟 gaia_radial_velocity.py 同一個比對基準
COOL_TEFF_MAX = 4500.0  # K，低於這個溫度預期是晚型矮星/前主序星
COOL_LOGG_MIN = 4.3  # 低於這個值視為偏低，值得懷疑
RV_SIGMA_MIN = 5.0


def main():
    needed = {
        "data/cmd_members.csv": "成員表",
        "data/astrophys.csv": "logg_gspphot（先跑 "
                               "scripts/data_prep/gaia_astrophys.py）",
        "data/radial_velocity.csv": "徑向速度（先跑 "
                                    "scripts/data_prep/gaia_radial_velocity.py）",
    }
    for rel, desc in needed.items():
        if not (HERE / rel).exists():
            print(f"缺少 {rel}（{desc}），無法比對。", file=sys.stderr)
            sys.exit(1)

    mem = Table.read(str(HERE / "data" / "cmd_members.csv"), format="csv")
    astro = Table.read(str(HERE / "data" / "astrophys.csv"), format="csv")
    rv_t = Table.read(str(HERE / "data" / "radial_velocity.csv"), format="csv")

    sid = np.asarray(mem["source_id"], np.int64)
    sid_astro = np.asarray(astro["source_id"], np.int64)
    sid_rv = np.asarray(rv_t["source_id"], np.int64)
    if not (np.array_equal(sid, sid_astro) and np.array_equal(sid, sid_rv)):
        print("三份檔案的 source_id 順序對不上，可能是不同批次產生的，"
              "不能直接逐列比對。請重新用同一份 cmd_members.csv 產生"
              "astrophys.csv 與 radial_velocity.csv 後再跑這支腳本。",
              file=sys.stderr)
        sys.exit(1)

    logg = np.asarray(astro["logg_gspphot"], float)
    teff = np.asarray(astro["teff_gspphot"], float)
    rv = np.asarray(rv_t["radial_velocity"], float)
    rv_err = np.asarray(rv_t["radial_velocity_error"], float)
    g = np.asarray(mem["phot_g_mean_mag"], float)
    bprp = np.asarray(mem["bp_rp"], float)

    ok_rv = np.isfinite(rv) & np.isfinite(rv_err) & (rv_err > 0)
    sigma = np.full(len(rv), np.nan)
    sigma[ok_rv] = np.abs(rv[ok_rv] - BULK_RV) / rv_err[ok_rv]
    rv_outlier = ok_rv & (sigma > RV_SIGMA_MIN)

    cool = np.isfinite(teff) & (teff < COOL_TEFF_MAX)
    cool_low_logg = cool & np.isfinite(logg) & (logg < COOL_LOGG_MIN)

    print(f"成員 {len(sid):,} 顆，Teff<{COOL_TEFF_MAX:.0f}K 的冷星"
          f"（預期是晚型矮星/前主序星）共 {cool.sum():,} 顆。")
    print(f"其中 logg_gspphot<{COOL_LOGG_MIN}（偏低，值得懷疑）的有 "
          f"{cool_low_logg.sum()} 顆：")
    for i in np.where(cool_low_logg)[0]:
        flag = "  [RV 也離群]" if rv_outlier[i] else ""
        print(f"    source_id={sid[i]}  Teff={teff[i]:.0f}  "
              f"logg={logg[i]:.2f}  G={g[i]:.2f}  BP-RP={bprp[i]:.2f}{flag}")

    double = cool_low_logg & rv_outlier
    print(f"\n高置信度候選（logg 偏低 **且** RV 顯著離群，兩個獨立訊號都"
          f"命中）：{double.sum()} 顆")
    for i in np.where(double)[0]:
        print(f"    source_id={sid[i]}  Teff={teff[i]:.0f}  "
              f"logg={logg[i]:.2f}  RV={rv[i]:+.2f}±{rv_err[i]:.2f} km/s  "
              f"({sigma[i]:.1f}σ)  G={g[i]:.2f}  BP-RP={bprp[i]:.2f}")
    if double.sum() == 0:
        print("    無——沒有星同時被兩個獨立訊號標記。單一訊號命中的星"
              "（上面列出的）不足以下結論，GSP-Phot 對冷暗星的 logg "
              "本身就不夠可靠，需要更多獨立證據才能判定。")
    else:
        print("\n下一步：確認這幾顆星的 G 星等是不是落在擬合質量範圍內"
              "（G<16.63，見 LIMITATIONS.md C16），若是，代表跟 A6 的白"
              "矮星一樣，現在就在每次頭條擬合的樣本裡。")


if __name__ == "__main__":
    main()
