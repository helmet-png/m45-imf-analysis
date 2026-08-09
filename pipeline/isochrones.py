# -*- coding: utf-8 -*-
"""PARSEC isochrone 的取得、快取與內插。

從 CMD 網頁服務 (stev.oapd.inaf.it/cgi-bin/cmd) 下載 isochrone 網格並存在本地。
下載一次之後所有擬合都從快取讀，好處有三：不依賴網路、可重現、對服務友善。

注意 isochrone 一律以 **零消光、絕對星等** 下載。消光與距離模數是擬合階段才
套用的參數，不該烘進快取裡 —— 否則換一組消光就要重新下載。
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np

from . import net
from .table_compat import Table

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "isochrones"
CMD_URL = "https://stev.oapd.inaf.it/cgi-bin/cmd"

# 光度系統。Gaia DR3 沿用 EDR3 的濾光片定義，所以這是 DR3 資料的正確選項。
PHOTSYS_GAIA = "YBC_tab_mag_odfnew/tab_mag_gaiaEDR3.dat"
# DR2 版只有一個用途：MIST v1.2 提供的是 DR2 濾光片，所以拿 PARSEC 的 DR2 版
# 當中介，才能把「濾光片差異」與「恆星演化模型差異」分離開來。
PHOTSYS_GAIA_DR2 = "YBC_tab_mag_odfnew/tab_mag_gaiaDR2weiler.dat"

PHOTSYS_TAGS = {PHOTSYS_GAIA: "gaiaEDR3", PHOTSYS_GAIA_DR2: "gaiaDR2"}

# 表單的固定欄位。這些值取自 CMD 3.9 的預設值，除非有理由否則不要動。
BASE_FORM = {
    "cmd_version": "3.9",
    "track_parsec": "parsec_CAF09_v2.0",
    "track_omegai": "0.00",
    "track_colibri": "parsec_CAF09_v1.2S_S_LMC_08_web",
    "track_postagb": "no",
    "n_inTPC": "10",
    "eta_reimers": "0.2",
    "kind_interp": "1",
    "kind_postagb": "-1",
    "photsys_version": "YBC",
    "dust_sourceM": "nodustM",
    "dust_sourceC": "nodustC",
    "kind_mag": "2",
    "kind_dust": "0",
    # 消光留給擬合階段處理，這裡一律取 0
    "extinction_av": "0.0",
    "extinction_coeff": "constant",
    "extinction_curve": "cardelli",
    "kind_LPV": "1",
    "imf_file": "tab_imf/imf_kroupa_orig.dat",
    "output_kind": "0",       # 0 = isochrone 表格
    "output_evstage": "1",
    "lf_maginf": "-15",
    "lf_magsup": "20",
    "lf_deltamag": "0.5",
    "sim_mtot": "1.0e4",
    "submit_form": "Submit",
}


def _grid_name(logage_lo, logage_hi, dlogage, mh_lo, mh_hi, dmh,
               photsys=PHOTSYS_GAIA) -> str:
    tag = PHOTSYS_TAGS.get(photsys, "gaiaEDR3")
    return (f"parsec_v2.0_{tag}_logt{logage_lo:g}-{logage_hi:g}"
            f"s{dlogage:g}_mh{mh_lo:g}-{mh_hi:g}s{dmh:g}.dat")


def download_grid(logage_lo: float, logage_hi: float, dlogage: float,
                  mh_lo: float, mh_hi: float, dmh: float,
                  force: bool = False, photsys: str = PHOTSYS_GAIA) -> Path:
    """下載一片 (log 年齡 × [M/H]) 的 isochrone 網格，回傳快取檔路徑。"""
    CACHE.mkdir(exist_ok=True)
    dest = CACHE / _grid_name(logage_lo, logage_hi, dlogage, mh_lo, mh_hi, dmh,
                              photsys)
    if dest.exists() and not force:
        print(f"isochrone 快取已存在：{dest.name}")
        return dest

    form = dict(BASE_FORM)
    form.update({
        "photsys_file": photsys,
        "isoc_isagelog": "1",           # 用 log(年齡/yr)
        "isoc_lagelow": f"{logage_lo}",
        "isoc_lageupp": f"{logage_hi}",
        "isoc_dlage": f"{dlogage}",
        "isoc_ismetlog": "1",           # 用 [M/H]
        "isoc_metlow": f"{mh_lo}",
        "isoc_metupp": f"{mh_hi}",
        "isoc_dmet": f"{dmh}",
    })
    import urllib.parse
    body = urllib.parse.urlencode(form).encode()

    print(f"向 PARSEC 要求網格 logAge {logage_lo}–{logage_hi} (步長 {dlogage})，"
          f"[M/H] {mh_lo}–{mh_hi} (步長 {dmh}) …")
    html, final_url = net.post(CMD_URL, body, timeout=600, extra_chain=True)
    page = html.decode("utf-8", "replace")

    # 回應頁裡的連結長這樣（注意沒有引號、且是 ../ 兩個點）：
    #   The results are available at <a href=../tmp/output333661306955.dat>
    m = re.search(r'href=["\']?[./]*(tmp/output[^"\'\s>]+)', page)
    if not m:
        err = re.search(r'(?is)<p[^>]*>\s*(.{0,300}?error.{0,300}?)</p>', page)
        raise RuntimeError(
            "PARSEC 沒有回傳輸出檔連結。"
            + (f" 頁面訊息：{re.sub('<[^>]+>', ' ', err.group(1))[:300]}"
               if err else f" 回應開頭：{page[:300]}"))

    data_url = f"https://stev.oapd.inaf.it/{m.group(1)}"
    print(f"下載 {data_url}")
    raw = net.get(data_url, timeout=600, extra_chain=True)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    dest.write_bytes(raw)
    n_lines = raw.count(b"\n")
    print(f"寫入 {dest}（{len(raw):,} bytes，{n_lines:,} 行）")
    return dest


def load_grid(path: Path) -> Table:
    """讀 PARSEC 輸出檔。註解以 # 開頭，最後一行註解是欄位名。"""
    names = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                stripped = line.lstrip("#").strip()
                if stripped and not stripped.lower().startswith(
                        ("theoretical", "photometry", "parsec", "isochrones",
                         "generated", "warning")):
                    names = stripped.split()
            else:
                break
    if names is None:
        raise ValueError(f"{path} 裡找不到欄位名稱那一行註解")
    t = Table.read(path, format="ascii", comment="#", names=names)
    return t


def isochrone_at(grid: Table, logage: float, mh: float,
                 age_col="logAge", mh_col="MH") -> Table:
    """從網格取出最接近 (logage, mh) 的那一條 isochrone。

    目前取最近格點而非內插。網格夠密時（建議 dlogage <= 0.05）誤差小於
    模型本身的系統差，而且避免了在轉折點附近內插造成的非物理結果 ——
    isochrone 在演化快速的階段形狀變化劇烈，逐點線性內插會產生假特徵。
    """
    ages = np.unique(np.asarray(grid[age_col], float))
    mhs = np.unique(np.asarray(grid[mh_col], float))
    a = ages[np.argmin(np.abs(ages - logage))]
    z = mhs[np.argmin(np.abs(mhs - mh))]
    sel = (np.asarray(grid[age_col], float) == a) & \
          (np.asarray(grid[mh_col], float) == z)
    return grid[sel]
