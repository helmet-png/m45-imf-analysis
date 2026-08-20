# -*- coding: utf-8 -*-
"""下載 PARSEC 的 Gaia DR2 濾光片版網格（P3）。

**用途**：MIST v1.2 只提供 DR2 濾光片，而我們的 PARSEC 網格是 EDR3。
所以「PARSEC vs MIST」的 alpha 差裡混著兩件事：
  (a) 恆星演化模型不同
  (b) 濾光片定義不同（DR2 與 EDR3 的 G 星等零點與波段形狀都有差）

拿 PARSEC 的 DR2 版當中介就能把兩者分開：

    PARSEC-EDR3  vs  PARSEC-DR2   -> 純濾光片效應（模型相同）
    PARSEC-DR2   vs  MIST-DR2     -> 純模型效應（濾光片相同）

這比查文獻的轉換式估算嚴謹，成本也只是多跑一次擬合。

注意 PARSEC 的欄位名在 DR2 版是 Gmag / G_BPmag / G_RPmag（或 *_fSBmag），
下游程式吃的是 EDR3 版的 G_fSBmag 等名稱，所以轉檔時一併改名。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import isochrones as iso  # noqa: E402

# 下游一律用這三個名字（EDR3 版的欄位名），DR2 版要對應過去。
#
# **DR2 的 BP 有兩套通帶**：G_BPbr（bright，G < 10.87）與 G_BPft（faint）。
# 這是 DR2 特有的校正分界，EDR3 已統一成單一通帶。
# 我們的樣本有 92% 比 G=11 暗（1,295 顆裡只有約 108 顆更亮），
# 所以取 faint 版。這個選擇本身是 DR2-EDR3 比較的一個小系統項，
# 但遠小於兩套通帶之間的差異，且方向已知。
WANT = {"G_fSBmag": ("G_fSBmag", "Gmag", "G_DR2mag"),
        "G_BP_fSBmag": ("G_BPft_fSBmag", "G_BP_fSBmag", "G_BPmag"),
        "G_RP_fSBmag": ("G_RP_fSBmag", "G_RPmag")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logage-lo", type=float, default=7.7)
    ap.add_argument("--logage-hi", type=float, default=8.3)
    ap.add_argument("--dlogage", type=float, default=0.05)
    ap.add_argument("--mh-lo", type=float, default=-0.6)
    ap.add_argument("--mh-hi", type=float, default=0.6)
    ap.add_argument("--dmh", type=float, default=0.05)
    a = ap.parse_args()

    raw = iso.download_grid(a.logage_lo, a.logage_hi, a.dlogage,
                            a.mh_lo, a.mh_hi, a.dmh,
                            photsys=iso.PHOTSYS_GAIA_DR2)
    print(f"\n原始檔：{raw.name}")

    # 讀欄位名那一行，決定要不要改名
    names = None
    with open(raw, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                s = line.lstrip("#").strip()
                if s and not s.lower().startswith(
                        ("theoretical", "photometry", "parsec", "isochrones",
                         "generated", "warning")):
                    names = s.split()
            else:
                break
    print(f"欄位（前 20 個）：{names[:20]}")

    rename = {}
    for want, cands in WANT.items():
        hit = next((c for c in cands if c in names), None)
        if hit is None:
            raise SystemExit(f"找不到 {want} 對應的欄位。實際欄位：{names}")
        if hit != want:
            rename[hit] = want
    print(f"需要改名：{rename or '（無）'}")

    out = raw
    if rename:
        out = raw.with_name(raw.stem + "_renamed.dat")
        newnames = [rename.get(n, n) for n in names]
        with open(raw, "r", encoding="utf-8", errors="replace") as fi, \
                open(out, "w", encoding="utf-8") as fo:
            wrote_hdr = False
            for line in fi:
                if line.startswith("#"):
                    s = line.lstrip("#").strip()
                    if s.split() == names and not wrote_hdr:
                        fo.write("# " + " ".join(newnames) + "\n")
                        wrote_hdr = True
                        continue
                    fo.write(line)
                else:
                    fo.write(line)
        print(f"改名後寫入：{out.name}")

    # 驗證讀取
    import numpy as np
    t = iso.load_grid(out)
    ages = np.unique(np.asarray(t["logAge"], float))
    mhs = np.unique(np.asarray(t["MH"], float))
    print(f"\n驗證：{len(t):,} 列、年齡 {len(ages)} 格、金屬量 {len(mhs)} 格")
    one = iso.isochrone_at(t, 8.10, 0.0)
    g = np.asarray(one["G_fSBmag"], float)
    print(f"  logAge=8.10 MH=0.00：{len(one):,} 點，"
          f"G 絕對星等 {g.min():.2f} – {g.max():.2f}")
    print(f"\n可用檔名：{out.name}")


if __name__ == "__main__":
    main()
