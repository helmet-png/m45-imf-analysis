# -*- coding: utf-8 -*-
"""PARSEC isochrone 的取得、快取與最近格點查詢。

======================================================================
【這支程式在做什麼】
======================================================================
等時線（isochrone）是恆星演化模型的預測：「同一時間出生、年齡相同的一群
星，不同質量的星現在應該有多亮、什麼顏色」。整個專案量質量、量年齡都靠它。

從 CMD 網頁服務 (stev.oapd.inaf.it/cgi-bin/cmd) 下載 isochrone 網格並存在本地。
下載一次之後所有擬合都從快取讀，好處有三：不依賴網路、可重現、對服務友善。

注意 isochrone 一律以 **零消光、絕對星等** 下載。消光與距離模數是擬合階段才
套用的參數，不該烘進快取裡 —— 否則換一組消光就要重新下載。

isochrone_at() 取**最近的格點**，不做內插（理由見該函式的說明，限制見
LIMITATIONS.md C14）。

這個檔案**沒有 main()，不能直接執行**，由別的程式 import 後呼叫：
  - scripts/drivers/run_pipeline.py：用 config.toml 的範圍呼叫 download_grid()
  - scripts/data_prep/build_dr2_grid.py：下載 DR2 濾光片版網格
  - fit_real.py、run_joint.py、traditional_accounting.py 等幾乎所有擬合程式：
    呼叫 load_grid() 讀快取，再用 isochrone_at() 取出一條等時線
  頭條擬合用的網格檔是
  isochrones/parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat
  （定義在 measure_overconfidence.py 的 GRID），範圍跟 config.toml 不同。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  gzip          解壓縮。PARSEC 有時回傳 gzip 壓縮過的檔案
  re            正規表示式：從網頁 HTML 裡找出輸出檔的連結
  pathlib.Path  處理檔案路徑
  urllib.parse  把表單欄位編碼成網址格式（在 download_grid 裡才 import）
第三方套件：
  numpy（np）   np.unique（取不重複值）、np.argmin（最小值的位置）、
                np.abs（絕對值）
本專案其他模組：
  pipeline/net.py          net.post／net.get：送出網路請求。它會補上 PARSEC
                           網站缺少的中繼憑證，讓 HTTPS 驗證能通過（不是關掉驗證）
  pipeline/table_compat.py Table：只用 numpy 實作的簡易表格，取代 astropy 的
                           Table（astropy 的相依套件沒有 ARM64 版，用它就得退回
                           較慢的 x64 模擬）

======================================================================
【(b) 用到的參數與意義】
======================================================================
download_grid() 的參數：
  logage_lo, logage_hi, dlogage
      年齡範圍與間隔，用 log10(年齡/年)。例如 8.0 = 10^8 年 = 100 Myr。
      config.toml [step3_age]：7.0–9.5，間隔 0.05
  mh_lo, mh_hi, dmh
      金屬量 [M/H] 的範圍與間隔。0 = 太陽金屬量，負數 = 金屬較少。
      config.toml：−0.2–0.2，間隔 0.1
  force    True 時無視快取、重新下載
  photsys  濾光片系統：PHOTSYS_GAIA（EDR3/DR3，預設）或 PHOTSYS_GAIA_DR2
isochrone_at() 的參數：
  grid     load_grid() 讀進來的整片網格
  logage   想要的年齡（log10 年）
  mh       想要的金屬量
  age_col, mh_col  網格表格裡年齡、金屬量的欄位名稱
模組常數：
  CACHE      快取資料夾 = repo 根目錄下的 isochrones/
  BASE_FORM  送給 PARSEC 網站的表單固定欄位（模型版本、不加消光等）

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 160–223 行｜download_grid()：組表單 → 送到 PARSEC → 從回應網頁找出
          輸出檔連結 → 下載並存成快取檔
  核心 2｜第 226–249 行｜load_grid()：讀快取檔，找出欄位名稱那一行，讀成表格
  核心 3｜第 252–275 行｜isochrone_at()：從整片網格挑出最接近指定年齡與金屬量的那一條

======================================================================
【(d) 整體流程】
======================================================================
下載（只做一次）：
  指定年齡範圍與金屬量範圍
    → 已有同名快取檔就直接回傳路徑（除非 force）
    → 把範圍填進 PARSEC 網站表單，POST 送出
    → PARSEC 回傳一頁 HTML，裡面有輸出檔連結 → 用正規表示式抓出來
    → 下載輸出檔（必要時解壓縮）→ 存進 isochrones/
之後每次擬合：
  load_grid(快取檔) → 整片網格（每一列 = 某年齡、某金屬量下的一個質量點）
    → isochrone_at(網格, 年齡, 金屬量) → 一條等時線
    → 交給擬合程式加上距離與消光使用
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

import numpy as np

from . import net
from .table_compat import Table

# ↓ ROOT：repo 根目錄（本檔在 pipeline/ 底下，往上一層）
ROOT = Path(__file__).resolve().parent.parent
# ↓ 快取資料夾：所有下載過的等時線網格都存在這裡
CACHE = ROOT / "isochrones"
# ↓ PARSEC 線上產生器的網址
CMD_URL = "https://stev.oapd.inaf.it/cgi-bin/cmd"

# 光度系統。Gaia DR3 沿用 EDR3 的濾光片定義，所以這是 DR3 資料的正確選項。
PHOTSYS_GAIA = "YBC_tab_mag_odfnew/tab_mag_gaiaEDR3.dat"
# DR2 版只有一個用途：MIST v1.2 提供的是 DR2 濾光片，所以拿 PARSEC 的 DR2 版
# 當中介，才能把「濾光片差異」與「恆星演化模型差異」分離開來。
PHOTSYS_GAIA_DR2 = "YBC_tab_mag_odfnew/tab_mag_gaiaDR2weiler.dat"

# ↓ 濾光片系統 → 快取檔名裡的短標籤
PHOTSYS_TAGS = {PHOTSYS_GAIA: "gaiaEDR3", PHOTSYS_GAIA_DR2: "gaiaDR2"}

# 表單的固定欄位。這些值取自 CMD 3.9 的預設值，除非有理由否則不要動。
BASE_FORM = {
    "cmd_version": "3.9",
    # ↓ 恆星演化軌跡用 PARSEC v2.0、不自轉（omegai=0）
    "track_parsec": "parsec_CAF09_v2.0",
    "track_omegai": "0.00",
    "track_colibri": "parsec_CAF09_v1.2S_S_LMC_08_web",
    "track_postagb": "no",
    "n_inTPC": "10",
    "eta_reimers": "0.2",
    "kind_interp": "1",
    "kind_postagb": "-1",
    "photsys_version": "YBC",
    # ↓ 不加星周塵埃
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
    # ↓ 把範圍編進檔名，例如
    #   parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat
    #   同一組範圍永遠對到同一個檔名，快取才找得到
    tag = PHOTSYS_TAGS.get(photsys, "gaiaEDR3")
    return (f"parsec_v2.0_{tag}_logt{logage_lo:g}-{logage_hi:g}"
            f"s{dlogage:g}_mh{mh_lo:g}-{mh_hi:g}s{dmh:g}.dat")


# ═══════════════ 核心 1：向 PARSEC 下載一片網格 ═══════════════
def download_grid(logage_lo: float, logage_hi: float, dlogage: float,
                  mh_lo: float, mh_hi: float, dmh: float,
                  force: bool = False, photsys: str = PHOTSYS_GAIA) -> Path:
    """下載一片 (log 年齡 × [M/H]) 的 isochrone 網格，回傳快取檔路徑。"""
    # ↓ 確保快取資料夾存在
    CACHE.mkdir(exist_ok=True)
    # ↓ 依範圍算出快取檔名
    dest = CACHE / _grid_name(logage_lo, logage_hi, dlogage, mh_lo, mh_hi, dmh,
                              photsys)
    # ↓ 已經下載過就直接用，不重複向網站要資料
    if dest.exists() and not force:
        print(f"isochrone 快取已存在：{dest.name}")
        return dest

    # ↓ 複製一份固定欄位，再填入這次要的範圍
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
    # ↓ 把表單編碼成 "key1=value1&key2=value2…" 的格式，再轉成位元組
    body = urllib.parse.urlencode(form).encode()

    print(f"向 PARSEC 要求網格 logAge {logage_lo}–{logage_hi} (步長 {dlogage})，"
          f"[M/H] {mh_lo}–{mh_hi} (步長 {dmh}) …")
    # ↓ 送出表單。timeout=600 秒：大網格要算很久；
    #   extra_chain=True：補上 PARSEC 缺的中繼憑證
    html, final_url = net.post(CMD_URL, body, timeout=600, extra_chain=True)
    # ↓ 網站回傳的是一頁 HTML，轉成文字
    page = html.decode("utf-8", "replace")

    # 回應頁裡的連結長這樣（注意沒有引號、且是 ../ 兩個點）：
    #   The results are available at <a href=../tmp/output333661306955.dat>
    # ↓ 用正規表示式抓出 "tmp/output….dat" 這段
    m = re.search(r'href=["\']?[./]*(tmp/output[^"\'\s>]+)', page)
    # ↓ 找不到連結代表 PARSEC 回報了錯誤：盡量把錯誤訊息擷取出來再報錯
    if not m:
        err = re.search(r'(?is)<p[^>]*>\s*(.{0,300}?error.{0,300}?)</p>', page)
        raise RuntimeError(
            "PARSEC 沒有回傳輸出檔連結。"
            + (f" 頁面訊息：{re.sub('<[^>]+>', ' ', err.group(1))[:300]}"
               if err else f" 回應開頭：{page[:300]}"))

    # ↓ 組出輸出檔的完整網址並下載
    data_url = f"https://stev.oapd.inaf.it/{m.group(1)}"
    print(f"下載 {data_url}")
    raw = net.get(data_url, timeout=600, extra_chain=True)
    # ↓ 開頭兩個位元組是 1f 8b = gzip 壓縮檔的標記，要先解壓
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    # ↓ 存成快取檔
    dest.write_bytes(raw)
    n_lines = raw.count(b"\n")
    print(f"寫入 {dest}（{len(raw):,} bytes，{n_lines:,} 行）")
    return dest


# ═══════════════ 核心 2：讀快取檔 ═══════════════
def load_grid(path: Path) -> Table:
    """讀 PARSEC 輸出檔。註解以 # 開頭，最後一行註解是欄位名。"""
    names = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        # ↓ 逐行讀檔頭：PARSEC 檔案開頭是一串 # 開頭的說明，
        #   其中最後一行（例如 "# Zini MH logAge Mini … Gmag …"）是欄位名稱
        for line in fh:
            if line.startswith("#"):
                stripped = line.lstrip("#").strip()
                # ↓ 跳過空行與一般說明文字（以這些字開頭的是說明，不是欄位名）；
                #   其餘的行都暫存為欄位名，讀到最後留下的就是最後一行
                if stripped and not stripped.lower().startswith(
                        ("theoretical", "photometry", "parsec", "isochrones",
                         "generated", "warning")):
                    names = stripped.split()
            # ↓ 遇到第一行資料（不以 # 開頭）就停止讀檔頭
            else:
                break
    if names is None:
        raise ValueError(f"{path} 裡找不到欄位名稱那一行註解")
    # ↓ 用找到的欄位名稱，把整個檔案讀成表格（# 開頭的行全部略過）
    t = Table.read(path, format="ascii", comment="#", names=names)
    return t


# ═══════════════ 核心 3：從網格挑出一條等時線 ═══════════════
def isochrone_at(grid: Table, logage: float, mh: float,
                 age_col="logAge", mh_col="MH") -> Table:
    """從網格取出最接近 (logage, mh) 的那一條 isochrone。

    目前取最近格點而非內插。網格夠密時（建議 dlogage <= 0.05）誤差小於
    模型本身的系統差，而且避免了在轉折點附近內插造成的非物理結果 ——
    isochrone 在演化快速的階段形狀變化劇烈，逐點線性內插會產生假特徵。

    ⚠ 副作用：擬合時年齡只能取網格上的值，概似對年齡不是連續可微的，
    所以 HMC 這類需要梯度的取樣器不能直接用（LIMITATIONS.md C14）。
    """
    # ↓ 網格裡出現過的所有年齡（不重複），例如 7.70, 7.75, …, 8.30
    ages = np.unique(np.asarray(grid[age_col], float))
    # ↓ 網格裡出現過的所有金屬量（不重複）
    mhs = np.unique(np.asarray(grid[mh_col], float))
    # ↓ 找最接近的年齡：|網格年齡 − 想要的年齡| 最小的那一個
    a = ages[np.argmin(np.abs(ages - logage))]
    # ↓ 找最接近的金屬量，作法相同
    z = mhs[np.argmin(np.abs(mhs - mh))]
    # ↓ 選出年齡與金屬量都等於這兩個格點值的列，就是那一條等時線
    sel = (np.asarray(grid[age_col], float) == a) & \
          (np.asarray(grid[mh_col], float) == z)
    return grid[sel]
