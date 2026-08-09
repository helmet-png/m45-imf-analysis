# -*- coding: utf-8 -*-
"""下載 MIST 打包檔並轉成與 PARSEC 同格式的網格。

轉出來的檔案欄位名與 PARSEC 完全相同，所以 fit_real.py 只要用 --grid
指過去就能跑，模型程式一行都不用改 —— 這樣「換等時線」才是唯一的變因。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import mist  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logage-lo", type=float, default=7.80)
    ap.add_argument("--logage-hi", type=float, default=8.50)
    ap.add_argument("--mh-lo", type=float, default=-0.50)
    ap.add_argument("--mh-hi", type=float, default=0.50)
    a = ap.parse_args()

    mist.download()
    print("\n打包檔裡的金屬量格點：")
    mets = mist.list_metallicities()
    print("  " + "  ".join(f"{f:+.2f}" for f in sorted(mets)))
    out = mist.build_grid(a.logage_lo, a.logage_hi, a.mh_lo, a.mh_hi)

    # 立刻用讀取端驗一次，避免佇列跑到下一步才發現格式不合
    from pipeline import isochrones as iso
    t = iso.load_grid(out)
    import numpy as np
    ages = np.unique(np.asarray(t["logAge"], float))
    mhs = np.unique(np.asarray(t["MH"], float))
    print(f"\n驗證讀取：{len(t):,} 列")
    print(f"  年齡格點 {len(ages)} 個：{ages.min():.2f} – {ages.max():.2f}")
    print(f"  金屬量格點 {len(mhs)} 個：" + " ".join(f"{v:+.2f}" for v in mhs))
    one = iso.isochrone_at(t, 8.10, 0.0)
    print(f"  logAge=8.10、MH=0.00 那一條有 {len(one):,} 個質量點，"
          f"質量 {np.min(one['Mini']):.3f} – {np.max(one['Mini']):.2f} M☉")


if __name__ == "__main__":
    main()
