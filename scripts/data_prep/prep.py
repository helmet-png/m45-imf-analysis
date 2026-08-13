# -*- coding: utf-8 -*-
"""把 Gaia 原始 CSV 整理成 pyUPMASK 的輸入檔。

座標做 gnomonic（切平面）投影而不是直接用 RA/Dec：在 dec=24 度的地方
RA 一度只有約 0.91 天球度，直接餵會讓天區橫向拉伸，pyUPMASK 用 Ripley's K
檢定空間集中度時會受影響。投影後 x、y 都是真正的角度。
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

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
CLUST_COLS = ["pmRA", "pmDE", "Plx", "e_pmRA", "e_pmDE", "e_Plx"]


K = 4.740470446  # mas/yr -> km/s 的換算常數（乘以距離 pc）


def tangent_plane(ra, dec, ra0, dec0):
    """gnomonic 投影，回傳以 (ra0, dec0) 為原點的 (x, y)，單位為度。"""
    r = np.radians
    dra = r(ra - ra0)
    d, d0 = r(dec), r(dec0)
    cosc = np.sin(d0) * np.sin(d) + np.cos(d0) * np.cos(d) * np.cos(dra)
    x = np.cos(d) * np.sin(dra) / cosc
    y = (np.cos(d0) * np.sin(d) - np.sin(d0) * np.cos(d) * np.cos(dra)) / cosc
    return np.degrees(x), np.degrees(y)


def unit_vectors(ra, dec):
    """ICRS 下的徑向、赤經方向、赤緯方向單位向量，形狀 (N, 3)。"""
    a = np.radians(np.atleast_1d(np.asarray(ra, float)))
    d = np.radians(np.atleast_1d(np.asarray(dec, float)))
    ca, sa, cd, sd = np.cos(a), np.sin(a), np.cos(d), np.sin(d)
    r = np.stack([cd * ca, cd * sa, sd], -1)
    p = np.stack([-sa, ca, np.zeros_like(sa)], -1)
    q = np.stack([-sd * ca, -sd * sa, cd], -1)
    return r, p, q


def expected_pm(ra, dec, ra0, dec0, pmra0, pmde0, plx0, rv0):
    """星團整體空間速度投影到 (ra, dec) 上，一顆成員「應該有」的自行運動。

    星團橫跨數度時，同一個三維速度投影到天區不同位置會得到不同的自行運動。
    M45 整體自行運動高達 50 mas/yr，這個幾何效應在 5 度天區上約 4 mas/yr，
    比它真正的內部速度彌散（約 0.8 mas/yr）還大 5 倍，不扣掉會把星團在速度
    空間糊開。
    """
    r0, p0, q0 = unit_vectors(ra0, dec0)
    r0, p0, q0 = r0[0], p0[0], q0[0]
    # 星團的三維空間速度（ICRS，km/s）
    v = rv0 * r0 + (K * pmra0 / plx0) * p0 + (K * pmde0 / plx0) * q0
    _, p, q = unit_vectors(np.atleast_1d(ra), np.atleast_1d(dec))
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

    src = Path(a.csv)
    if not src.is_absolute():
        src = REPO_ROOT / src
    t = Table.read(src, format="csv")
    n0 = len(t)

    for old, new in RENAME.items():
        if old in t.colnames:
            t.rename_column(old, new)

    # 分群要用的六個欄位缺任何一個就丟掉，不要讓 pyUPMASK 自己去處理缺值
    # （它的 dread 用 logical_or 判斷，只要有一欄有值就留下，不是我們要的行為）
    good = np.ones(len(t), bool)
    for c in CLUST_COLS:
        col = np.asarray(t[c], dtype=float)
        good &= np.isfinite(col)
    t = t[good]
    print(f"讀入 {n0:,} 列，丟掉缺值 {n0 - len(t):,} 列，剩 {len(t):,} 列")

    server = _load_server()
    ra0, dec0 = server.resolve_name(a.target)
    x, y = tangent_plane(np.asarray(t["ra"], float), np.asarray(t["dec"], float),
                         ra0, dec0)
    t["_x"], t["_y"] = x, y
    print(f"投影原點 ({ra0:.5f}, {dec0:.5f})；"
          f"x 範圍 {x.min():.2f}~{x.max():.2f}，y 範圍 {y.min():.2f}~{y.max():.2f} 度")

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

    keep = ["source_id", "_x", "_y", "pmRA", "pmDE", "Plx",
            "e_pmRA", "e_pmDE", "e_Plx", "Gmag", "BP_RP", "RUWE"]
    t = t[[c for c in keep if c in t.colnames]]

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = INPUT_DIR / ((a.name or src.stem) + ".dat")
    t.write(out, format="ascii", overwrite=True)
    print(f"寫入 {out}")


if __name__ == "__main__":
    main()
