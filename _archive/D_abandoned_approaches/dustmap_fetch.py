# -*- coding: utf-8 -*-
"""取得 M45 方向的三維消光估計。

**為什麼需要**：年齡、金屬量、消光三者在 CMD 上幾乎完全簡併（實測相關係數
±0.95，96.7% 的變異集中在單一方向）。資料只能定出「三者落在某條線上」。
三維塵埃圖提供**與 CMD 無關的第二個約束** —— 它直接說「往這個方向、到這個
距離，累積了多少消光」—— 能把那條線截斷成一段。

**為什麼不用 dustmaps 套件**：它依賴 healpy，而 healpy 在這台機器上
（Windows ARM64，且無 C 編譯器）無法安裝，x64 Python 上也編不起來。

**改用的方法**：Vizier 上有 Lallement 等人的三維消光圖，可用 TAP 查詢，
不需要下載整份資料、也不需要 healpy。這是純 HTTP + numpy，兩個 Python 都能跑。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pipeline import net  # noqa: E402

VIZIER_TAP = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"

# M45
RA, DEC = 56.60083, 24.11389
DIST_PC = 135.5


def vizier(adql):
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER_TAP, data=body,
                                 headers={"User-Agent": net.UA})
    with urllib.request.urlopen(req, timeout=300,
                                context=net.ssl_context()) as r:
        return json.loads(r.read().decode())


def find_tables(keyword):
    """在 VizieR 裡找三維消光圖的資料表。"""
    res = vizier(
        "SELECT table_name, description FROM TAP_SCHEMA.tables "
        f"WHERE description LIKE '%{keyword}%'")
    return res["data"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", action="store_true",
                    help="只搜尋可用的三維消光圖資料表，不查詢")
    a = ap.parse_args()

    if a.search:
        for kw in ("3D extinction", "extinction map", "interstellar reddening"):
            print(f"\n=== 關鍵字：{kw} ===")
            try:
                rows = find_tables(kw)
            except Exception as e:
                print(f"  查詢失敗：{type(e).__name__}: {e}")
                continue
            for name, desc in rows[:12]:
                print(f"  {name}")
                print(f"      {str(desc)[:100]}")
        return

    # M45 的銀道座標
    r, d = np.radians(RA), np.radians(DEC)
    # J2000 -> 銀道座標的標準轉換
    ra_ngp, dec_ngp, l_ncp = np.radians(192.85948), np.radians(27.12825), np.radians(122.93192)
    sb = (np.sin(dec_ngp) * np.sin(d)
          + np.cos(dec_ngp) * np.cos(d) * np.cos(r - ra_ngp))
    b = np.arcsin(sb)
    y = np.cos(d) * np.sin(r - ra_ngp)
    x = (np.cos(dec_ngp) * np.sin(d)
         - np.sin(dec_ngp) * np.cos(d) * np.cos(r - ra_ngp))
    l = l_ncp - np.arctan2(y, x)
    l_deg = np.degrees(l) % 360
    b_deg = np.degrees(b)
    print(f"M45 銀道座標：l = {l_deg:.3f}, b = {b_deg:.3f}")
    print(f"距離 {DIST_PC} pc")
    print(f"\n垂直於銀盤的高度 z = {DIST_PC * np.sin(b):.1f} pc")
    print("（M45 在銀盤下方約 55 pc，已經接近盤面塵埃層的邊緣，")
    print("  所以視線上的塵埃主要集中在前景幾十 pc 之內）")

    print("\n用 --search 尋找 VizieR 上可用的三維消光圖資料表。")


if __name__ == "__main__":
    main()
