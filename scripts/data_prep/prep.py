# -*- coding: utf-8 -*-
"""把 Gaia 原始 CSV 整理成 pyUPMASK 的輸入檔。

座標做 gnomonic（切平面）投影而不是直接用 RA/Dec：在 dec=24 度的地方
RA 一度只有約 0.91 天球度，直接餵會讓天區橫向拉伸，pyUPMASK 用 Ripley's K
檢定空間集中度時會受影響。投影後 x、y 都是真正的角度。

======================================================================
【這支程式在做什麼】
======================================================================
成員分類的前一步。pyUPMASK（外部的成員判定程式）對輸入檔有固定要求：
欄位要用它認得的名字、不能有缺值、座標要是平面座標。這支程式負責：
  1. 把 Gaia 欄位名改成 pyUPMASK 用的名字
  2. 丟掉分群用的六個欄位有缺值的星
  3. 把 RA/Dec 投影成以星團中心為原點的平面座標 (x, y)
  4.（選用，正式流程沒開）扣掉星團整體運動造成的透視效應
  5. 只留需要的欄位，寫到 prepared/<名稱>.dat
正式流程的指令（見 README）：
  python scripts/data_prep/prep.py data/m45_r5_g18_plx4.csv --target M45 --name m45_raw
輸出：prepared/m45_raw.dat，再交給 run_variant.py

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, importlib.util, os, sys, pathlib  讀參數、載入 gaia-export、處理路徑
第三方套件：
  numpy（np）
      np.radians／np.degrees  度 ↔ 弧度（三角函數要用弧度）
      np.sin／np.cos          三角函數
      np.stack                把幾個陣列並排成一個多維陣列（組三維向量用）
      np.isfinite             判斷是不是正常數字
      np.ptp                  最大值減最小值（peak-to-peak），印出跨天區變化量
  astropy.table.Table
      Table.read(…, format="csv")  讀 CSV 成表格
      t.rename_column(舊, 新)      改欄位名
      t.write(…, format="ascii")   寫成以空白分隔的純文字表格（pyUPMASK 讀這種）
外部專案 gaia-export 的 server.py：
  server.resolve_name("M45")  用 CDS Sesame 把名稱換成中心座標，當投影原點
  （_load_server() 跟 fetch_gaia.py 同一套找檔邏輯）

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  csv           fetch_gaia.py 產出的 CSV 路徑（必填）
  --target      星團名稱，用來查投影原點，預設 M45
  --name        輸出檔名（不含 .dat），預設沿用 CSV 檔名；正式流程用 m45_raw
  --deproject   開啟透視效應修正（正式流程沒開，見 README：成員名單只差
                3.5%，小於換亂數種子的變化）
  --bulk PMRA PMDE PLX RV  星團整體自行（mas/yr）、視差（mas）、徑向速度
                (km/s)，--deproject 時必填
模組常數：
  INPUT_DIR   輸出資料夾 prepared/
  RENAME      Gaia 欄名 → pyUPMASK 欄名
  CLUST_COLS  pyUPMASK 分群真正用到的六欄：兩個方向的自行、視差及各自誤差
  K = 4.740470446  單位換算常數：自行(mas/yr) × 距離(pc) × K = 切向速度(km/s)
⚠ 投影原點固定用 Sesame 查到的座標（M45 是 RA 56.86909），跟 fetch_gaia.py
  圓錐中心用的 config 座標（56.60083）差 0.27°。這只移動 x、y 的原點，不影響
  自行與視差。

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 157–178 行｜tangent_plane()：RA/Dec → 平面座標 (x, y)
  核心 2｜第 195–214 行｜expected_pm()：算每個位置上「星團成員應有的自行」（只在 --deproject 用）
  核心 3｜第 230–287 行｜main() 的資料處理：改欄名、丟缺值、投影、（扣透視效應）、寫檔

======================================================================
【(d) 整體流程】
======================================================================
  讀 Gaia CSV
    → 欄位改名（pmra→pmRA、parallax→Plx …）
    → 六個分群欄位任何一個缺值就丟掉那顆星
    → 用 Sesame 查星團中心 → 每顆星投影成以中心為原點的 (x, y)，單位度
    →（--deproject 時）算出每個位置的預期自行，從觀測自行扣掉
    → 只留 source_id、x、y、自行、視差、誤差、Gmag、BP_RP、RUWE
    → 寫成 prepared/<名稱>.dat
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

# ↓ repo 根目錄（本檔在 scripts/data_prep/，往上三層）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_server():
    """找到 gaia-export 姊妹專案並匯入它的 server.py，回傳該模組。

    跟 fetch_gaia.py 的 _load_server() 同一套邏輯（見該檔說明），延後到
    緊臨第一次用到 server 之前才呼叫，不要在參數驗證前就可能因為找不到
    gaia-export 而炸掉、蓋掉更該優先顯示的參數錯誤。

    只認環境變數與跟本 repo 同層的候選目錄，不 fallback 到任何機器特定的
    寫死路徑——這種路徑只要剛好存在（哪怕內容是別的、過期的 checkout），
    就會被靜默接受，跑出錯的結果卻不報錯。

    `import server` 用的是全域模組名稱，若同一個 process 已經從別的路徑
    載入過 `server`（例如呼叫端同時載入 fetch_gaia 與 prep 兩個 loader），
    `sys.modules` 快取可能讓這次拿到錯的 checkout。載入後驗證
    `server.__file__` 是否真的對到這次選中的路徑，不對就繞過快取重新載入。
    """
    candidates = [os.environ.get("GAIA_EXPORT_PATH")] + [
        REPO_ROOT.parent / name for name in ("gaia-dr3-export", "gaia-export")
    ]
    for c in candidates:
        if not c:
            continue
        c = Path(c)
        server_py = c / "server.py"
        if c.is_dir() and server_py.is_file():
            sys.path.insert(0, str(c))
            import server
            if Path(server.__file__).resolve() != server_py.resolve():
                previous = sys.modules.get("server")
                spec = importlib.util.spec_from_file_location("server", server_py)
                server = importlib.util.module_from_spec(spec)
                sys.modules["server"] = server
                try:
                    spec.loader.exec_module(server)
                except Exception:
                    if previous is None:
                        sys.modules.pop("server", None)
                    else:
                        sys.modules["server"] = previous
                    raise
            return server
    raise FileNotFoundError(
        "找不到 gaia-export 專案（含 server.py 的目錄）。"
        "設定環境變數 GAIA_EXPORT_PATH 指向它，或把它 clone 到跟本 repo 同一層"
        "（github.com/helmet-png/gaia-dr3-export）。"
    )
# 產到 prepared/，由 run_variant.py 挑一個複製進 pyUPMASK/input/
# （pyUPMASK 會把 input/ 底下每個檔案都跑一遍，不能同時放多份）
INPUT_DIR = REPO_ROOT / "prepared"

# Gaia 欄名 -> pyUPMASK params.ini 用的欄名
RENAME = {
    "pmra": "pmRA", "pmdec": "pmDE", "parallax": "Plx",
    "pmra_error": "e_pmRA", "pmdec_error": "e_pmDE",
    "parallax_error": "e_Plx",
    "phot_g_mean_mag": "Gmag", "bp_rp": "BP_RP", "ruwe": "RUWE",
}
# ↓ pyUPMASK 分群真正用的六欄
CLUST_COLS = ["pmRA", "pmDE", "Plx", "e_pmRA", "e_pmDE", "e_Plx"]


K = 4.740470446  # mas/yr -> km/s 的換算常數（乘以距離 pc）


# ═══════════════ 核心 1：切平面投影 ═══════════════
def tangent_plane(ra, dec, ra0, dec0):
    """gnomonic 投影，回傳以 (ra0, dec0) 為原點的 (x, y)，單位為度。

    直覺：在原點把一張平面貼在天球上，從球心往外看，每顆星投到這張平面上的
    位置就是 (x, y)。原點附近的距離與角度幾乎不失真。
    """
    # ↓ r 只是 np.radians 的簡寫（度 → 弧度）
    r = np.radians
    # ↓ 每顆星與原點的赤經差（弧度）
    dra = r(ra - ra0)
    # ↓ 星與原點的赤緯（弧度）
    d, d0 = r(dec), r(dec0)
    # ↓ cosc = 星與原點之間角距的餘弦（球面三角的標準式），當投影的分母
    cosc = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(dra)
    # ↓ x：往赤經增加方向的平面座標；乘上 cos(d) 正好修正「高赤緯處 RA 一度
    #   比較短」的問題
    x = np.cos(d) * np.sin(dra) / cosc
    # ↓ y：往北（赤緯增加）方向的平面座標
    y = (np.cos(d0) * np.sin(d) - np.sin(d0) * np.cos(d) * np.cos(dra)) / cosc
    # ↓ 換回度
    return np.degrees(x), np.degrees(y)


def unit_vectors(ra, dec):
    """ICRS 下的徑向、赤經方向、赤緯方向單位向量，形狀 (N, 3)。"""
    a = np.radians(np.atleast_1d(np.asarray(ra, float)))
    d = np.radians(np.atleast_1d(np.asarray(dec, float)))
    ca, sa, cd, sd = np.cos(a), np.sin(a), np.cos(d), np.sin(d)
    # ↓ r：從地球指向這顆星的方向（視線方向）
    r = np.stack([cd * ca, cd * sa, sd], -1)
    # ↓ p：在天球上往東（赤經增加）的方向
    p = np.stack([-sa, ca, np.zeros_like(sa)], -1)
    # ↓ q：在天球上往北（赤緯增加）的方向
    q = np.stack([-sd * ca, -sd * sa, cd], -1)
    return r, p, q


# ═══════════════ 核心 2：預期自行（透視效應） ═══════════════
def expected_pm(ra, dec, ra0, dec0, pmra0, pmde0, plx0, rv0):
    """星團整體空間速度投影到 (ra, dec) 上，一顆成員「應該有」的自行運動。

    星團橫跨數度時，同一個三維速度投影到天區不同位置會得到不同的自行運動。
    M45 整體自行運動高達 50 mas/yr，這個幾何效應在 5 度天區上約 4 mas/yr，
    比它真正的內部速度彌散（約 0.8 mas/yr）還大 5 倍，不扣掉會把星團在速度
    空間糊開。
    """
    # ↓ 星團中心那個方向的三個單位向量（只有一個點，所以取 [0]）
    r0, p0, q0 = unit_vectors(ra0, dec0)
    r0, p0, q0 = r0[0], p0[0], q0[0]
    # 星團的三維空間速度（ICRS，km/s）
    # ↓ 三維速度 = 視線速度 × 視線方向 + 東向切向速度 × 東向 + 北向切向速度 × 北向；
    #   切向速度(km/s) = K × 自行(mas/yr) ÷ 視差(mas)（視差 1/距離）
    v = rv0 * r0 + (K * pmra0 / plx0) * p0 + (K * pmde0 / plx0) * q0
    # ↓ 每顆星所在位置的東向、北向單位向量
    _, p, q = unit_vectors(np.atleast_1d(ra), np.atleast_1d(dec))
    # ↓ 把同一個三維速度投到每顆星的東向、北向（內積 @），再換回自行單位 mas/yr
    return (p @ v) * plx0 / K, (q @ v) * plx0 / K


def main():
    ap = argparse.ArgumentParser(description="Gaia CSV -> pyUPMASK 輸入檔")
    ap.add_argument("csv", help="fetch_gaia.py 產出的 CSV")
    ap.add_argument("--target", default="M45", help="用來定投影原點")
    ap.add_argument("--name", default=None, help="輸出檔名（預設沿用 CSV 檔名）")
    ap.add_argument("--deproject", action="store_true",
                    help="扣掉星團整體運動的投影效應（需 --bulk）")
    ap.add_argument("--bulk", nargs=4, type=float, metavar=("PMRA", "PMDE", "PLX", "RV"),
                    help="星團整體 pmRA* pmDE 視差 徑向速度，供 --deproject 使用")
    a = ap.parse_args()
    if a.deproject and not a.bulk:
        ap.error("--deproject 需要一併給 --bulk PMRA PMDE PLX RV")

    # ═══════════════ 核心 3：資料處理 ═══════════════
    # ↓ 相對路徑一律從 repo 根目錄算
    src = Path(a.csv)
    if not src.is_absolute():
        src = REPO_ROOT / src
    # ↓ 讀 Gaia CSV；n0 = 原始列數
    t = Table.read(src, format="csv")
    n0 = len(t)

    # ↓ 欄位改名成 pyUPMASK 認得的名字（有這欄才改）
    for old, new in RENAME.items():
        if old in t.colnames:
            t.rename_column(old, new)

    # 分群要用的六個欄位缺任何一個就丟掉，不要讓 pyUPMASK 自己去處理缺值
    # （它的 dread 用 logical_or 判斷，只要有一欄有值就留下，不是我們要的行為）
    # ↓ good 先全部 True；每檢查一欄，該欄不是正常數字的星就變 False
    good = np.ones(len(t), bool)
    for c in CLUST_COLS:
        col = np.asarray(t[c], dtype=float)
        good &= np.isfinite(col)
    t = t[good]
    print(f"讀入 {n0:,} 列，丟掉缺值 {n0 - len(t):,} 列，剩 {len(t):,} 列")

    # ↓ 查星團中心座標，當投影原點
    server = _load_server()
    ra0, dec0 = server.resolve_name(a.target)
    # ↓ 每顆星投影成平面座標，存成新欄位 _x、_y
    x, y = tangent_plane(np.asarray(t["ra"], float), np.asarray(t["dec"], float),
                         ra0, dec0)
    t["_x"], t["_y"] = x, y
    print(f"投影原點 ({ra0:.5f}, {dec0:.5f})；"
          f"x 範圍 {x.min():.2f}~{x.max():.2f}，y 範圍 {y.min():.2f}~{y.max():.2f} 度")

    # ↓ 只有 --deproject 才做：每顆星的自行扣掉「它所在位置的預期自行」
    if a.deproject:
        pmra0, pmde0, plx0, rv0 = a.bulk
        exp_ra, exp_de = expected_pm(np.asarray(t["ra"], float),
                                     np.asarray(t["dec"], float),
                                     ra0, dec0, pmra0, pmde0, plx0, rv0)
        print(f"投影修正：整體運動 pm=({pmra0:+.2f},{pmde0:+.2f}) "
              f"Plx={plx0:.3f} RV={rv0:+.1f}")
        print(f"  扣除量 pmRA* {exp_ra.min():+.2f}~{exp_ra.max():+.2f}，"
              f"pmDE {exp_de.min():+.2f}~{exp_de.max():+.2f} mas/yr"
              f"（跨天區變化 {np.ptp(exp_ra):.2f} / {np.ptp(exp_de):.2f}）")
        t["pmRA"] = np.asarray(t["pmRA"], float) - exp_ra
        t["pmDE"] = np.asarray(t["pmDE"], float) - exp_de

    # ↓ 只留 pyUPMASK 需要的欄位（有這欄才留）
    keep = ["source_id", "_x", "_y", "pmRA", "pmDE", "Plx",
            "e_pmRA", "e_pmDE", "e_Plx", "Gmag", "BP_RP", "RUWE"]
    t = t[[c for c in keep if c in t.colnames]]

    # ↓ 寫到 prepared/<名稱>.dat
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = INPUT_DIR / ((a.name or src.stem) + ".dat")
    t.write(out, format="ascii", overwrite=True)
    print(f"寫入 {out}")


if __name__ == "__main__":
    main()
