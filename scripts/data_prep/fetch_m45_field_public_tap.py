#!/usr/bin/env python
"""Fetch the bounded M45 Gaia field without the expensive COUNT query.

======================================================================
【這支程式在做什麼】
======================================================================
fetch_gaia.py 的備用版本，產出同一份 data/m45_r5_g18_plx4.csv。差別：
  - 不需要 gaia-export 專案，只用 Python 標準庫
  - 查詢條件（中心座標、半徑、星等、視差）全部寫死成 M45 的既有設定
  - 預設送到海德堡大學的 Gaia 鏡像站（gaia.ari.uni-heidelberg.de），
    不是 ESA；兩邊是同一份 Gaia DR3 資料
  - 不做計數查詢（ESA 的計數查詢會逾時），直接取最多 20,000 列，
    再用幾道檢查確認取回的資料完整、合理才寫檔
執行方式：python scripts/data_prep/fetch_m45_field_public_tap.py
兩支擇一即可，不需要都跑。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
全部是 Python 標準庫：
  argparse        讀命令列參數
  csv             csv.DictReader 把 CSV 文字讀成「每列一個字典」；
                  csv.DictWriter 寫回 CSV
  json            把結果摘要印成 JSON
  urllib.parse    把查詢參數編碼成網址表單格式
  urllib.request  送出 HTTP POST 請求
  pathlib.Path    處理檔案路徑

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --tap-url  TAP 服務網址，預設海德堡鏡像站
  --output   輸出路徑（相對於 repo 根目錄），預設 data/m45_r5_g18_plx4.csv
寫死的常數：
  TOP = 20000           最多取幾列；M45 實際約 7,000 顆，留足餘裕
  RA_DEG, DEC_DEG       圓錐中心 56.60083°, 24.11389°（跟 config.toml 註解一致）
  RADIUS_DEG = 5.0      圓錐半徑（度）
  G ≤ 18、視差 ≥ 4 mas   寫在查詢語句裡
  FIELDS                要取的欄位，跟 fetch_gaia.py 的 COLUMNS 相同

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 94–116 行｜組查詢語句、送出、取回 CSV
  核心 2｜第 117–130 行｜四道檢查：有資料、沒頂到上限、列數在合理範圍、欄位正確
  核心 3｜第 131–143 行｜寫檔並印出摘要

======================================================================
【(d) 整體流程】
======================================================================
  組出 ADQL 查詢（圓錐 + G≤18 + 視差≥4，最多 20,000 列）
    → POST 到 TAP 服務 → 取回 CSV 文字 → 解析成一列一列
    → 檢查：0 列 → 報錯；≥ 20,000 列（可能被截斷）→ 報錯；
      不在 5,000–10,000 列之間（跟 M45 的已知量級不符）→ 報錯；
      欄位跟要求的不一樣 → 報錯
    → 全部通過才寫成 CSV，並印出列數與查詢條件
"""
from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

# ↓ repo 根目錄（本檔在 scripts/data_prep/，parents[2] = 往上三層）
ROOT = Path(__file__).resolve().parents[2]
# ↓ 預設的 TAP 服務：海德堡大學的 Gaia 鏡像站，"sync" 表示同步查詢
DEFAULT_TAP = "https://gaia.ari.uni-heidelberg.de/tap/sync"
# ↓ 最多取回的列數（防止意外取回整個天區）
TOP = 20000
# ↓ 圓錐中心與半徑，跟既有樣本一致
RA_DEG = 56.60083
DEC_DEG = 24.11389
RADIUS_DEG = 5.0
# ↓ 要取的欄位（意義見 fetch_gaia.py 的 COLUMNS）
FIELDS = [
    "source_id", "ra", "dec", "pmra", "pmdec", "parallax",
    "pmra_error", "pmdec_error", "parallax_error",
    "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp",
    "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
    "phot_rp_mean_flux_over_error", "phot_bp_rp_excess_factor", "ruwe",
    "non_single_star",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap-url", default=DEFAULT_TAP)
    ap.add_argument("--output", default="data/m45_r5_g18_plx4.csv")
    args = ap.parse_args()
    # ═══════════════ 核心 1：組查詢並送出 ═══════════════
    # ↓ ADQL 查詢語句：
    #     SELECT TOP 20000 欄位…          最多取 20,000 列，只取這些欄位
    #     FROM gaiadr3.gaia_source        Gaia DR3 主星表
    #     WHERE 1=CONTAINS(POINT(星的座標), CIRCLE(中心, 半徑))   星落在圓錐內
    #       AND phot_g_mean_mag<=18 AND parallax>=4               星等與視差條件
    query = (
        f"SELECT TOP {TOP} " + ", ".join(FIELDS)
        + " FROM gaiadr3.gaia_source WHERE "
        + f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{RA_DEG},{DEC_DEG},{RADIUS_DEG})) "
        + "AND phot_g_mean_mag<=18 AND parallax>=4"
    )
    # ↓ TAP 協定的標準表單欄位：執行查詢、語言 ADQL、回傳 CSV、查詢內容
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query,
    }).encode("ascii")
    # ↓ 用 POST 送出，最多等 300 秒
    request = urllib.request.Request(args.tap_url, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=300) as response:
        # ↓ "utf-8-sig"：若檔案開頭帶有 BOM 標記，解碼時順便去掉
        text = response.read().decode("utf-8-sig")
    # ↓ 把 CSV 文字讀成一列一列，每列是 {欄位名: 值} 的字典
    rows = list(csv.DictReader(text.splitlines()))
    # ═══════════════ 核心 2：確認資料完整、合理 ═══════════════
    # ↓ 一列都沒有 → 查詢出問題
    if not rows:
        raise RuntimeError("Gaia returned no rows")
    # ↓ 列數頂到 TOP → 可能還有星沒取回來（被截斷），拒絕寫檔
    if len(rows) >= TOP:
        raise RuntimeError(f"Query reached TOP {TOP}; refusing a potentially truncated field")
    # ↓ M45 這組條件已知約 7,000 顆；不在 5,000–10,000 之間代表條件或服務有異
    if not (5000 <= len(rows) <= 10000):
        raise RuntimeError(f"Unexpected M45 field size {len(rows)}; refusing to write")
    # ↓ 回傳的欄位名稱與順序必須跟要求的一模一樣
    returned_fields = list(rows[0])
    if returned_fields != FIELDS:
        raise RuntimeError(f"Unexpected Gaia columns: {returned_fields}")
    # ═══════════════ 核心 3：寫檔 ═══════════════
    out = ROOT / args.output
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    # ↓ 印出摘要（列數、上限、查詢範圍與篩選條件），方便事後核對
    print(json.dumps({
        "status": "complete_bounded_public_tap_query",
        "rows": len(rows), "top_guard": TOP, "output": str(out),
        "query_geometry": {"ra": RA_DEG, "dec": DEC_DEG, "radius_deg": RADIUS_DEG},
        "cuts": {"g_max": 18.0, "parallax_min_mas": 4.0},
    }))


if __name__ == "__main__":
    main()
