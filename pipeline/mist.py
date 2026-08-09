# -*- coding: utf-8 -*-
"""MIST isochrone 的下載與轉檔，用來量「換一套恆星演化模型」造成的系統誤差。

**為什麼需要它**：注入回收測試在設計上看不到物理錯誤 —— 假資料是同一個生成
模型做的，PARSEC 若有系統偏差，假資料也跟著偏，兩邊一致所以測試會通過。
唯一能量出這一項的方法是換一套獨立的等時線對**同一批真實觀測**重跑，
把差距當系統誤差項。這很可能是目前最大的未量化系統誤差，因為 M45 太年輕、
年齡主要由低質量前主序收縮軌跡約束，那正是各家模型分歧最大的區段。

**為什麼不用網頁表單**：mist.science 的 interp_isos 表單實測會忽略
`output_option=photometry`，不論怎麼送都回傳理論輸出（79 欄、無 Gaia 星等）。
改用官方的打包檔（靜態檔案，152 MB），可靠得多也不必反覆打擾服務。

**必須記錄的兩個差異**（會混進「模型差異」裡）：
1. MIST v1.2 用的是 **Gaia DR2** 濾光片，PARSEC 那份用的是 EDR3。
   兩者的 G 星等差約 0.01–0.03 星等，遠小於我們要找的模型差異，但不是零。
2. MIST 的金屬量格點是 0.25 dex 一階，比 PARSEC 那份的 0.05 粗五倍。
"""
from __future__ import annotations

import re
import tarfile
from pathlib import Path

import numpy as np

from . import net

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "isochrones"
TARBALL_URL = ("https://waps.cfa.harvard.edu/MIST/data/tarballs_v1.2/"
               "MIST_v1.2_vvcrit0.4_UBVRIplus.txz")
TARBALL = CACHE / "MIST_v1.2_vvcrit0.4_UBVRIplus.txz"

# 我們的程式其餘部分沿用 PARSEC 的欄位名，所以轉檔時直接改成同樣的名字，
# 下游一行都不用改。
OUT_COLS = ["logAge", "MH", "Mini", "G_fSBmag", "G_BP_fSBmag", "G_RP_fSBmag"]


def download(force: bool = False) -> Path:
    """下載官方打包檔（約 152 MB），已存在就直接用。"""
    CACHE.mkdir(exist_ok=True)
    if TARBALL.exists() and not force:
        print(f"MIST 打包檔已存在：{TARBALL.name}"
              f"（{TARBALL.stat().st_size:,} bytes）")
        return TARBALL
    print(f"下載 {TARBALL_URL} …（約 152 MB，需要幾分鐘）")
    blob = net.get(TARBALL_URL, timeout=3600)
    TARBALL.write_bytes(blob)
    print(f"寫入 {TARBALL}（{len(blob):,} bytes）")
    return TARBALL


def _feh_from_name(name: str) -> float | None:
    m = re.search(r"feh_([mp])([\d.]+)", name)
    if not m:
        return None
    v = float(m.group(2))
    return -v if m.group(1) == "m" else v


def list_metallicities(path: Path = TARBALL) -> dict:
    """回傳 {[Fe/H]: tar 內的檔名}。"""
    out = {}
    with tarfile.open(path, "r:xz") as tf:
        for m in tf.getmembers():
            if not m.name.endswith(".iso.cmd"):
                continue
            feh = _feh_from_name(Path(m.name).name)
            if feh is not None:
                out[feh] = m.name
    return dict(sorted(out.items()))


def _parse_one(text: str, logage_lo: float, logage_hi: float,
               feh: float) -> tuple[np.ndarray, list[str]]:
    """解析一個 .iso.cmd，回傳落在年齡範圍內的資料列。"""
    lines = text.splitlines()
    hdr_i = None
    for i, l in enumerate(lines[:60]):
        if "log10_isochrone_age_yr" in l:
            hdr_i = i
    if hdr_i is None:
        raise ValueError("找不到欄位名那一行")
    cols = lines[hdr_i].lstrip("#").split()

    def col(*cands):
        for c in cands:
            if c in cols:
                return cols.index(c)
        raise KeyError(f"缺少欄位（試過 {cands}）")

    i_age = col("log10_isochrone_age_yr")
    i_m = col("initial_mass")
    # Gaia 欄位名在不同版本略有差異，逐一試
    i_g = col("Gaia_G_DR2Rev", "Gaia_G_EDR3", "Gaia_G")
    i_bp = col("Gaia_BP_DR2Rev", "Gaia_BP_EDR3", "Gaia_BP", "Gaia_BP_DR2Rev_b")
    i_rp = col("Gaia_RP_DR2Rev", "Gaia_RP_EDR3", "Gaia_RP")

    rows = []
    for l in lines[hdr_i + 1:]:
        if not l.strip() or l.lstrip().startswith("#"):
            continue
        v = l.split()
        a = float(v[i_age])
        if a < logage_lo - 1e-6 or a > logage_hi + 1e-6:
            continue
        rows.append((a, feh, float(v[i_m]), float(v[i_g]),
                     float(v[i_bp]), float(v[i_rp])))
    return np.array(rows, float) if rows else np.empty((0, 6)), cols


def build_grid(logage_lo: float, logage_hi: float,
               mh_lo: float, mh_hi: float,
               path: Path = TARBALL, out: Path | None = None) -> Path:
    """從打包檔取出所需範圍，寫成與 PARSEC 同格式的表。"""
    mets = list_metallicities(path)
    use = {f: n for f, n in mets.items() if mh_lo - 1e-6 <= f <= mh_hi + 1e-6}
    if not use:
        raise ValueError(f"打包檔裡沒有 [Fe/H] 落在 {mh_lo}–{mh_hi} 的檔案。"
                         f"可用的是 {sorted(mets)}")
    print(f"打包檔共 {len(mets)} 個金屬量，取用 {len(use)} 個："
          f"{sorted(use)}")

    chunks = []
    with tarfile.open(path, "r:xz") as tf:
        for feh, name in sorted(use.items()):
            fh = tf.extractfile(name)
            txt = fh.read().decode("utf-8", "replace")
            arr, _ = _parse_one(txt, logage_lo, logage_hi, feh)
            print(f"  [Fe/H]={feh:+.2f}  取到 {len(arr):,} 列")
            if len(arr):
                chunks.append(arr)
    if not chunks:
        raise ValueError("沒有取到任何資料，檢查年齡範圍")
    data = np.vstack(chunks)

    if out is None:
        out = CACHE / (f"mist_v1.2_gaiaDR2_logt{logage_lo:g}-{logage_hi:g}"
                       f"_feh{mh_lo:g}-{mh_hi:g}.dat")
    with open(out, "w", encoding="utf-8") as f:
        f.write("# MIST v1.2 vvcrit0.4 UBVRIplus，由官方打包檔轉出\n")
        f.write("# 注意：Gaia 濾光片是 DR2 版，PARSEC 那份是 EDR3\n")
        f.write("# " + " ".join(OUT_COLS) + "\n")
        for r in data:
            f.write(f"{r[0]:.4f} {r[1]:.4f} {r[2]:.8f} "
                    f"{r[3]:.6f} {r[4]:.6f} {r[5]:.6f}\n")
    print(f"寫入 {out}（{len(data):,} 列）")
    return out
