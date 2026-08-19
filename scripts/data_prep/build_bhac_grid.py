# -*- coding: utf-8 -*-
"""下載 BHAC15（Baraffe et al. 2015）等時線並轉成跟現有 PARSEC/MIST 網格
同樣的欄位格式（C1/D1）。

用法（跟 build_mist_grid.py／build_dr2_grid.py 同款式）：
    python scripts/data_prep/build_bhac_grid.py

只涵蓋低質量前主序，用 --logage-lo/--logage-hi 抓 M45 擬合範圍附近的
年齡格點就好，不用抓整個 0.5 Myr–10 Gyr 的範圍。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

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

    bhac.download()
    out = bhac.build_grid(a.logage_lo, a.logage_hi)

    # 立刻用讀取端驗一次，避免格式不合到下游才發現
    from pipeline import isochrones as iso
    t = iso.load_grid(out)
    import numpy as np
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
    if not np.isfinite(mini).all():
        raise ValueError(f"Mini 欄有 {(~np.isfinite(mini)).sum()} 個非數值，"
                         f"解析有問題，不要拿去擬合")
    if not np.isfinite(mh).all():
        raise ValueError("MH 欄有非數值，解析有問題，不要拿去擬合")
    print(f"  質量範圍 {mini.min():.3f} – {mini.max():.3f} M_sun"
          f"（M45 擬合上限 2.50，BHAC15 蓋不過，只能檢驗低質量段）")
    print(f"  金屬量格點 {len(mh)} 個：{', '.join(f'{v:+.2f}' for v in mh)}"
          f"{'（單一值，MH 維度形同鎖死）' if len(mh) == 1 else ''}")

    nearest = iso.isochrone_at(t, 8.03, 0.0)  # M45 大致的 logage
    g = np.asarray(nearest["G_fSBmag"], float)
    print(f"  logAge=8.03（最近格點）：{len(nearest):,} 點，"
          f"G 絕對星等 {g.min():.2f} – {g.max():.2f}")
    print(f"\n可用檔名：{out.name}")


if __name__ == "__main__":
    main()
