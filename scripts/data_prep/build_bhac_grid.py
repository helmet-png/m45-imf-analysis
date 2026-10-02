# -*- coding: utf-8 -*-
"""下載 BHAC15（Baraffe et al. 2015）等時線並轉成跟現有 PARSEC/MIST 網格
同樣的欄位格式（C1/D1）。

用法（跟 build_mist_grid.py／build_dr2_grid.py 同款式）：
    python scripts/data_prep/build_bhac_grid.py

只涵蓋低質量前主序，用 --logage-lo/--logage-hi 抓 M45 擬合範圍附近的
年齡格點就好，不用抓整個 0.5 Myr–10 Gyr 的範圍。

======================================================================
【這支程式在做什麼】
======================================================================
PARSEC 與 MIST 在低質量、還在收縮的年輕星（前主序）用類似的物理處理，
兩者一致不代表沒有共同偏差。BHAC15 是專門為低質量星設計的獨立模型，
拿它來檢驗這段的共同偏差。代價是它只涵蓋到約 1.4 M☉、只有太陽金屬量一種，
蓋不過 M45 擬合範圍的上限 2.50 M☉（LIMITATIONS.md D1）。

這支程式只是「入口」：真正下載與轉檔的工作在 pipeline/bhac.py。
輸出：isochrones/bhac15_gaia_logt<範圍>.dat

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse      讀命令列參數
  sys, pathlib  把 repo 根目錄加進 import 路徑
第三方套件：
  numpy（np）   np.unique、np.isfinite（檢查是不是正常數字）
本專案其他模組：
  pipeline/bhac.py
      bhac.download()    從 ENS Lyon 網站下載官方檔 BHAC15_iso.GAIA（已有就沿用；
                         網站缺中繼憑證，由 pipeline/net.py 補上）
      bhac.build_grid()  官方檔是「一段年齡、一張表」的格式：逐行讀，遇到
                         「t (Gyr) = …」就記下目前年齡（換成 log10 年），
                         遇到資料列就取出質量 M/Ms 與 G、G_BP、G_RP，
                         金屬量一律填 0（BHAC15 只有太陽金屬量），
                         寫成跟 PARSEC 快取同格式的表
  pipeline/isochrones.py
      iso.load_grid()／iso.isochrone_at()  把轉出的檔案讀回來驗證

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --logage-lo  年齡下限（log10 年），預設 7.60（約 40 Myr）
  --logage-hi  年齡上限，預設 8.40（約 250 Myr）
  （沒有金屬量參數：BHAC15 只有一種金屬量）

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 85–89 行｜下載官方檔並轉成 PARSEC 格式
  核心 2｜第 91–123 行｜讀回來驗證：每一欄都是數值、印出質量與金屬量範圍

======================================================================
【(d) 整體流程】
======================================================================
  讀參數 → bhac.download() → bhac.build_grid()（取範圍內年齡，寫成 PARSEC 格式）
    → isochrones.load_grid() 讀回來
    → 檢查 Mini、MH 兩欄全是數值（不是就報錯，不准拿去擬合）
    → 印出質量範圍（提醒蓋不過 2.50 M☉）與金屬量格點數
    → 取出最接近 logAge=8.03 的那一條，印出 G 星等範圍
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ↓ HERE：repo 根目錄（本檔在 scripts/data_prep/，往上三層）
HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import bhac  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logage-lo", type=float, default=7.60,
                    help="M45 擬合範圍下界附近（約 40 Myr）")
    ap.add_argument("--logage-hi", type=float, default=8.40,
                    help="M45 擬合範圍上界附近（約 250 Myr）")
    a = ap.parse_args()

    # ═══════════════ 核心 1：下載並轉檔 ═══════════════
    # ↓ 下載官方檔（已存在就跳過）
    bhac.download()
    # ↓ 取出年齡範圍內的資料，寫成 PARSEC 格式；回傳輸出檔路徑
    out = bhac.build_grid(a.logage_lo, a.logage_hi)

    # ═══════════════ 核心 2：讀回來驗證 ═══════════════
    # 立刻用讀取端驗一次，避免格式不合到下游才發現
    from pipeline import isochrones as iso
    t = iso.load_grid(out)
    import numpy as np
    # ↓ 列出實際有哪些年齡格點
    ages = np.unique(np.asarray(t["logAge"], float))
    print(f"\n驗證讀取：{len(t):,} 列，年齡格點 {len(ages)} 個："
          f"{ages.min():.2f} – {ages.max():.2f}")
    # Mini／MH 也要真的轉成數值驗一次（CodeRabbit PR #65）：只驗 logAge 的話，
    # 某一欄若因為解析錯誤混進非數值（例如把註解行當成資料列），要到 JointModel
    # 展開 isochrone 時才會炸，而那時已經看不出是網格建置階段的問題。
    # 質量範圍尤其要印出來——BHAC15 只到 1.4 M_sun、蓋不過 M45 擬合上限 2.50，
    # 這是這個網格的已知限制（見 LIMITATIONS.md D1），每次建完都該當場看到。
    mini = np.asarray(t["Mini"], float)
    mh = np.unique(np.asarray(t["MH"], float))
    # ↓ np.isfinite(...).all()：全部都是正常數字才是 True；有任何一個不是就報錯
    if not np.isfinite(mini).all():
        raise ValueError(f"Mini 欄有 {(~np.isfinite(mini)).sum()} 個非數值，"
                         f"解析有問題，不要拿去擬合")
    if not np.isfinite(mh).all():
        raise ValueError("MH 欄有非數值，解析有問題，不要拿去擬合")
    print(f"  質量範圍 {mini.min():.3f} – {mini.max():.3f} M_sun"
          f"（M45 擬合上限 2.50，BHAC15 蓋不過，只能檢驗低質量段）")
    print(f"  金屬量格點 {len(mh)} 個：{', '.join(f'{v:+.2f}' for v in mh)}"
          f"{'（單一值，MH 維度形同鎖死）' if len(mh) == 1 else ''}")

    # ↓ 取出最接近 M45 年齡的那一條，印出 G 絕對星等範圍
    nearest = iso.isochrone_at(t, 8.03, 0.0)  # M45 大致的 logage
    g = np.asarray(nearest["G_fSBmag"], float)
    print(f"  logAge=8.03（最近格點）：{len(nearest):,} 點，"
          f"G 絕對星等 {g.min():.2f} – {g.max():.2f}")
    print(f"\n可用檔名：{out.name}")


if __name__ == "__main__":
    main()
