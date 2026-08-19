# -*- coding: utf-8 -*-
"""BHAC15（Baraffe et al. 2015）等時線的下載與轉檔（C1/D1）。

**為什麼需要它**：PARSEC 與 MIST 在低質量前主序段（M45 的年齡主要由這段
收縮軌跡約束）用相似的對流／大氣處理，兩者互相一致不代表沒有共同偏差
（見 LIMITATIONS.md C1/D1）。BHAC15 是專為低質量前主序設計的獨立模型，
能真正測到這個共同偏差有多大。

**已知限制**：BHAC15 只涵蓋到 1.4 M_sun 左右（低質量前主序模型的設計範圍），
不像 PARSEC/MIST 蓋到主序以上。M45 的擬合質量範圍是 0.08–2.50 M_sun，
用 BHAC15 重跑只能驗證低質量段，不能宣稱驗證了全範圍——這是誠實的限制，
不是這支程式的 bug。

**單一金屬量**：官方檔案只有太陽金屬量（Z=0.02）一組，沒有 MH 網格，
下游 `isochrone_at()` 找最近 MH 格點永遠會拿到這一組，MH 這個維度
在用 BHAC15 重跑時形同鎖死。
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from . import net

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "isochrones"
SOURCE_URL = ("https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/"
              "BHAC15_iso.GAIA")
RAW_FILE = CACHE / "BHAC15_iso.GAIA"
CHAIN_NAME = "ens_lyon"  # 見 pipeline/net.py：這個服務也不送中繼憑證

# 下游沿用 PARSEC 的欄位名，轉檔時直接改成同樣的名字。
OUT_COLS = ["logAge", "MH", "Mini", "G_fSBmag", "G_BP_fSBmag", "G_RP_fSBmag"]

_AGE_RE = re.compile(r"!\s+t \(Gyr\)\s*=\s*([\d.]+)")
_HDR_RE = re.compile(r"!\s*M/Ms\s")


def download(force: bool = False) -> Path:
    """下載官方檔案，已存在就直接用。伺服器不送中繼憑證，要用
    extra_chain=True 搭配 chain_name="ens_lyon"（見 pipeline/net.py）；
    憑證鏈本身要先抓過一次，做法比照 setup/setup_ca.ps1 抓 PARSEC。"""
    CACHE.mkdir(exist_ok=True)
    if RAW_FILE.exists() and not force:
        print(f"BHAC15 原始檔已存在：{RAW_FILE.name}"
              f"（{RAW_FILE.stat().st_size:,} bytes）")
        return RAW_FILE
    print(f"下載 {SOURCE_URL} …")
    raw = net.get(SOURCE_URL, timeout=120, extra_chain=True,
                  chain_name=CHAIN_NAME)
    # 原子寫入：上面那個 `RAW_FILE.exists()` 判斷會把任何已存在的檔案當成
    # 「下載完成、可以直接用」，所以絕不能留下截斷的半成品（見 net.atomic_write）
    net.atomic_write(RAW_FILE, raw)
    print(f"寫入 {RAW_FILE}（{len(raw):,} bytes）")
    return RAW_FILE


def _parse(text: str, logage_lo: float, logage_hi: float) -> np.ndarray:
    """解析全部年齡區塊，回傳落在年齡範圍內的資料列
    (logAge, MH=0.0, Mini, G, G_BP, G_RP)。"""
    lines = text.splitlines()
    col_names: list[str] | None = None
    cur_logage: float | None = None
    rows = []
    for line in lines:
        # 有些行（標頭、資料列）前面帶一個空格，match() 從位置 0 開始比對，
        # 先 lstrip() 才不會因為這個空格漏配。
        stripped = line.lstrip()
        m = _AGE_RE.match(stripped)
        if m:
            age_gyr = float(m.group(1))
            cur_logage = np.log10(age_gyr * 1e9)
            continue
        if _HDR_RE.match(stripped):
            col_names = stripped.lstrip("!").split()
            continue
        if cur_logage is None or col_names is None:
            continue
        if not line.strip() or line.lstrip().startswith("!"):
            continue
        if cur_logage < logage_lo - 1e-6 or cur_logage > logage_hi + 1e-6:
            continue
        vals = line.split()
        if len(vals) != len(col_names):
            continue  # 不是資料列（例如分隔線漏被前面的檢查擋掉）
        d = dict(zip(col_names, vals))
        try:
            m_ini = float(d["M/Ms"])
            g = float(d["G"])
            g_bp = float(d["G_BP"])
            g_rp = float(d["G_RP"])
        except (KeyError, ValueError):
            continue
        rows.append((cur_logage, 0.0, m_ini, g, g_bp, g_rp))
    return np.array(rows, float) if rows else np.empty((0, 6))


def build_grid(logage_lo: float, logage_hi: float,
               path: Path = RAW_FILE, out: Path | None = None) -> Path:
    """從官方檔案取出所需年齡範圍，寫成與 PARSEC 同格式的表。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    data = _parse(text, logage_lo, logage_hi)
    if len(data) == 0:
        ages_available = sorted(set(
            f"{float(a):.4f}" for a in _AGE_RE.findall(text)))
        raise ValueError(
            f"沒有取到任何資料，logAge {logage_lo}-{logage_hi} 範圍內"
            f"沒有格點。檔案裡的年齡格點（Gyr）：{ages_available}")
    ages = np.unique(data[:, 0])
    print(f"取用 logAge {logage_lo}-{logage_hi} 範圍內 {len(ages)} 個年齡格點："
          f"{np.round(ages, 3).tolist()}")
    print(f"共 {len(data):,} 列，質量範圍 {data[:,2].min():.3f}"
          f"-{data[:,2].max():.3f} M_sun（BHAC15 只到低質量前主序，"
          f"不蓋過 M45 擬合範圍上限，見 LIMITATIONS.md C1/D1）")

    if out is None:
        out = CACHE / f"bhac15_gaia_logt{logage_lo:g}-{logage_hi:g}.dat"
    with open(out, "w", encoding="utf-8") as f:
        f.write("# BHAC15（Baraffe et al. 2015），由官方 BHAC15_iso.GAIA 轉出\n")
        f.write("# 單一太陽金屬量（Z=0.02），MH 這個維度形同鎖死\n")
        f.write("# 只涵蓋低質量前主序（見檔頭質量範圍），不宣稱蓋過全範圍\n")
        f.write("# " + " ".join(OUT_COLS) + "\n")
        for r in data:
            f.write(f"{r[0]:.4f} {r[1]:.4f} {r[2]:.6f} "
                    f"{r[3]:.6f} {r[4]:.6f} {r[5]:.6f}\n")
    print(f"寫入 {out}（{len(data):,} 列）")
    return out
