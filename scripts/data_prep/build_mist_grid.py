# -*- coding: utf-8 -*-
"""下載 MIST 打包檔並轉成與 PARSEC 同格式的網格。

轉出來的檔案欄位名與 PARSEC 完全相同，所以 fit_real.py 只要用 --grid
指過去就能跑，模型程式一行都不用改 —— 這樣「換等時線」才是唯一的變因。

======================================================================
【這支程式在做什麼】
======================================================================
MIST 是另一套獨立的恆星演化模型。拿它取代 PARSEC 對同一批 M45 觀測重跑
擬合，α 變了多少就是「等時線模型選擇」造成的系統誤差。注入回收測試看不到
這一項（假資料跟擬合用的是同一套模型），所以只能用換模型的方式量。

這支程式只是「入口」：真正下載與轉檔的工作在 pipeline/mist.py。
執行方式：python scripts/data_prep/build_mist_grid.py [--logage-lo 7.8 ...]
輸出：isochrones/mist_v1.2_vvcrit0.0_gaiaDR2_logt<範圍>_feh<範圍>.dat

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse      讀命令列參數（--logage-lo 等）
  sys, pathlib  把 repo 根目錄加進 import 路徑，才 import 得到 pipeline/
第三方套件：
  numpy（np）   np.unique（取不重複值）、np.min／np.max
本專案其他模組：
  pipeline/mist.py
      mist.download()          從哈佛 MIST 網站下載官方打包檔
                               （MIST_v1.2_vvcrit0.0_UBVRIplus.txz，約 152 MB），
                               已下載過就沿用
      mist.list_metallicities() 列出打包檔裡有哪些金屬量（每個金屬量一個檔）
      mist.build_grid()        從打包檔裡挑出年齡、金屬量範圍內的資料列，
                               只留 logAge、MH、Mini、G、BP、RP 六欄，
                               寫成跟 PARSEC 快取同格式的表
  pipeline/isochrones.py
      iso.load_grid()／iso.isochrone_at()  用正式的讀取函式把剛寫好的檔案
                               讀回來，確認下游程式讀得懂

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --logage-lo, --logage-hi   年齡範圍（log10 年），預設 7.80–8.50（約 63–316 Myr）
  --mh-lo, --mh-hi           金屬量 [Fe/H] 範圍，預設 −0.50–0.50
  ⚠ MIST 只提供 Gaia **DR2** 濾光片，PARSEC 用的是 EDR3。直接比 PARSEC 與
    MIST 時，差異裡混著「濾光片不同」；要分開兩者需搭配 build_dr2_grid.py。

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 85–93 行｜下載打包檔、列出金屬量、轉出網格檔
  核心 2｜第 95–110 行｜把轉出的檔案讀回來驗證格式

======================================================================
【(d) 整體流程】
======================================================================
  讀參數 → mist.download()（下載或沿用打包檔）
    → 印出打包檔裡有哪些金屬量
    → mist.build_grid()：只取範圍內的資料，寫成 PARSEC 格式
    → 用 isochrones.load_grid() 讀回來，印出列數、年齡格點、金屬量格點，
      並取出 logAge=8.10、MH=0.00 那一條檢查質量範圍
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ↓ HERE：repo 根目錄（本檔在 scripts/data_prep/，往上三層）
HERE = Path(__file__).resolve().parent.parent.parent
# ↓ 把根目錄放進 import 搜尋路徑，下一行才 import 得到 pipeline
sys.path.insert(0, str(HERE))

from pipeline import mist  # noqa: E402


def main():
    # ↓ 定義命令列參數與預設值
    ap = argparse.ArgumentParser()
    ap.add_argument("--logage-lo", type=float, default=7.80)
    ap.add_argument("--logage-hi", type=float, default=8.50)
    ap.add_argument("--mh-lo", type=float, default=-0.50)
    ap.add_argument("--mh-hi", type=float, default=0.50)
    a = ap.parse_args()

    # ═══════════════ 核心 1：下載並轉檔 ═══════════════
    # ↓ 下載官方打包檔（已存在就跳過）
    mist.download()
    print("\n打包檔裡的金屬量格點：")
    # ↓ 回傳 {金屬量: 打包檔裡的檔名}
    mets = mist.list_metallicities()
    print("  " + "  ".join(f"{f:+.2f}" for f in sorted(mets)))
    # ↓ 挑出範圍內的資料，寫成 PARSEC 格式；回傳輸出檔路徑
    out = mist.build_grid(a.logage_lo, a.logage_hi, a.mh_lo, a.mh_hi)

    # ═══════════════ 核心 2：讀回來驗證 ═══════════════
    # 立刻用讀取端驗一次，避免佇列跑到下一步才發現格式不合
    from pipeline import isochrones as iso
    # ↓ 用擬合程式會用的同一個讀取函式讀檔
    t = iso.load_grid(out)
    import numpy as np
    # ↓ 列出檔案裡實際有哪些年齡與金屬量格點
    ages = np.unique(np.asarray(t["logAge"], float))
    mhs = np.unique(np.asarray(t["MH"], float))
    print(f"\n驗證讀取：{len(t):,} 列")
    print(f"  年齡格點 {len(ages)} 個：{ages.min():.2f} – {ages.max():.2f}")
    print(f"  金屬量格點 {len(mhs)} 個：" + " ".join(f"{v:+.2f}" for v in mhs))
    # ↓ 取出一條代表性的等時線（接近 M45 年齡），印出它的質量範圍
    one = iso.isochrone_at(t, 8.10, 0.0)
    print(f"  logAge=8.10、MH=0.00 那一條有 {len(one):,} 個質量點，"
          f"質量 {np.min(one['Mini']):.3f} – {np.max(one['Mini']):.2f} M☉")


if __name__ == "__main__":
    main()
