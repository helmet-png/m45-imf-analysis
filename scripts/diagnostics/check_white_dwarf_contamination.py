# -*- coding: utf-8 -*-
"""A6（原 D7）：`data/cmd_members.csv` 有沒有混進白矮星？

**背景**（見 `LIMITATIONS.md` A6，這條原本編號 D7，查出真的有命中後升級
成 A 類）：`pipeline/step5_imf.assign_masses()` 只用觀測 G 星等對主序等時線
做一維反查，範圍內、但顏色遠離主序的星（例如白矮星）不會被現有的 NaN 機制
擋下，會拿到一個對應同 G 星等主序星的錯誤質量。這支腳本不改動 pipeline，
只查證「現役成員表裡有沒有這類天體」。

**做法**：跟 Gentile-Fusillo et al. (2021, MNRAS 508, 3877) 的 Gaia EDR3 白
矮星目錄（Vizier `J/MNRAS/508/3877/maincat`）比對 `source_id`。這份目錄用
天體測量＋測光機率分類，`Pwd` 欄是白矮星機率（實測查詢回傳 1,280,266 筆，
比原始論文摘要提到的量級大，可能是這份 Vizier 表收錄了機率較寬鬆的候選星，
不只嚴格高信心白矮星，比對到的命中仍應以 `Pwd` 個別判讀，不是「有在表裡
就一定是白矮星」）。

**已知的比對限制（誠實列出，不是模型的一部分）**：
1. 目錄用的是 EDR3 source_id，這個 repo 的 `cmd_members.csv` 是 DR3。同一顆
   星從 EDR3 到 DR3 的 source_id 絕大多數保持不變（Gaia 只在極少數「重複源
   判定」的邊緣案例才會換號），但不是 100% 保證——比對不到不等於「確定
   不是白矮星」，只是「找不到已知白矮星目錄裡的紀錄」。
2. 只查白矮星，不查其他非主序天體（次巨星、前主序離群點等）；A6 的問題
   範圍本來就只針對白矮星。

**跑法**：`python check_white_dwarf_contamination.py`（需要網路，會查
Vizier）。結果印在終端機，不寫檔——真的比對到東西再決定要不要進一步處理
（例如從成員表剔除、或在 `assign_masses()` 加顏色檢查）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
MEMBERS_CSV = HERE / "data" / "cmd_members.csv"
VIZIER_CATALOG = "J/MNRAS/508/3877/maincat"


def main():
    if not MEMBERS_CSV.exists():
        print(f"找不到 {MEMBERS_CSV}，無法比對。", file=sys.stderr)
        sys.exit(1)

    from pipeline.table_compat import Table
    members = Table.read(str(MEMBERS_CSV), format="csv")
    member_ids = set(int(x) for x in members["source_id"])
    print(f"成員表 {len(member_ids)} 顆星，開始查 Vizier "
          f"{VIZIER_CATALOG}（Gentile-Fusillo+2021 Gaia EDR3 白矮星目錄）...")

    try:
        from astroquery.vizier import Vizier
    except ImportError:
        print("需要 astroquery（pip install astroquery）。", file=sys.stderr)
        sys.exit(1)

    # 直接用 ADQL 風格的 source_id IN (...) 查詢會超過 URL 長度限制，改成
    # 整份抓回來後在本地端做集合交集——實測整份約 128 萬列（見上方
    # docstring），row_limit=-1 會真的抓全部，網路傳輸與記憶體都要吃這個
    # 量級，不是原先誤記的 ~359,000（2026-08-13 CodeRabbit review 抓到
    # 這裡的估計數字沒跟著 docstring 更新，容易讓人低估這支腳本的成本）。
    v = Vizier(columns=["GaiaEDR3", "Pwd", "Gmag", "MassH"], row_limit=-1)
    result = v.get_catalogs(VIZIER_CATALOG)
    if not result:
        print("Vizier 查詢沒有回傳任何表格，可能是服務暫時異常。",
              file=sys.stderr)
        sys.exit(1)
    wd_table = result[0]
    wd_ids = np.asarray(wd_table["GaiaEDR3"], dtype=np.int64)

    matched_mask = np.isin(wd_ids, list(member_ids))
    n_match = int(matched_mask.sum())

    print(f"\n目錄共 {len(wd_ids)} 顆已知/候選白矮星。")
    if n_match == 0:
        print("比對結果：0 顆命中。成員表沒有混進這份目錄收錄的白矮星"
              "（受限制 1 的說明，不是 100% 排除，但沒有已知混入的證據）。")
        return

    print(f"比對結果：{n_match} 顆命中，以下是詳細資料：\n")
    hits = wd_table[matched_mask]
    for row in hits:
        sid = int(row["GaiaEDR3"])
        print(f"  source_id={sid}  Pwd={row['Pwd']:.3f}  "
              f"Gmag={row['Gmag']:.2f}  MassH={row['MassH']}")
    print("\n下一步：確認這幾顆星在 `data/cmd_members.csv` 裡的 assign_masses() "
          "產出質量是否明顯不合理（白矮星在主序附近的 G 星等會被誤判成一顆"
          "偏亮的低質量主序星），若確認混入，考慮從成員表剔除或在 "
          "`assign_masses()` 加顏色檢查（見 LIMITATIONS.md A6 的後果段）。")


if __name__ == "__main__":
    main()
