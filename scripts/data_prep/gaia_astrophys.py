# -*- coding: utf-8 -*-
"""從 Gaia DR3 的天體物理參數表取得成員星的消光與金屬量估計。

**為什麼這是打破簡併的正確來源**：
年齡、金屬量、消光在 CMD 上幾乎完全簡併（實測相關係數 ±0.95，96.7% 的變異
集中在單一方向），我們的三個寬波段測光無法把它們分開。

Gaia 的 GSP-Phot 模組用的是每顆星的 **BP/RP 低解析度光譜**（數十個波長點），
資訊量遠大於三個寬波段星等，因此能給出獨立的消光與金屬量估計。
GSP-Spec 則用 RVS 高解析度光譜，金屬量更可靠但只有亮星才有。

相較於三維塵埃圖，這個來源有兩個優勢：
  1. 可用 TAP 依 source_id 直接查，不必下載 FITS 資料立方
  2. 與我們的成員表同源，全銀河涵蓋一致，符合「統一流程」的要求

注意：GSP-Phot 本身也受簡併影響，所以它給的值不是真值，
而是「一個獨立的、資訊量更大的估計」。用它當先驗而非固定值。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline.table_compat import Table  # noqa: E402


def _load_server():
    """找到 gaia-export 姊妹專案並匯入它的 server.py，回傳該模組。

    跟 `fetch_gaia.py`／`gaia_radial_velocity.py`／`prep.py` 的
    `_load_server()` 同一套邏輯：只認環境變數 `GAIA_EXPORT_PATH` 與跟本
    repo 同層的候選目錄，不 fallback 到任何機器特定的寫死路徑——這支腳本
    原本寫死 `C:\\Users\\Alber\\Claude\\gaia-export`，換一台機器就會
    找不到（或更糟：如果那個路徑剛好存在但是別的、過期的 checkout，會被
    靜默接受，跑出錯的結果卻不報錯）。2026-08-13 CodeRabbit review 已在
    `gaia_radial_velocity.py`／`fetch_gaia.py`／`prep.py` 修過同一個問題，
    這支腳本當時漏改，補上跟其他 `scripts/data_prep/` 腳本一致的可攜寫法。
    """
    candidates = [os.environ.get("GAIA_EXPORT_PATH")] + [
        HERE.parent / name for name in ("gaia-dr3-export", "gaia-export")
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
                spec = importlib.util.spec_from_file_location("server", server_py)
                server = importlib.util.module_from_spec(spec)
                sys.modules["server"] = server
                spec.loader.exec_module(server)
            return server
    raise FileNotFoundError(
        "找不到 gaia-export 專案（含 server.py 的目錄）。"
        "設定環境變數 GAIA_EXPORT_PATH 指向它，或把它 clone 到跟本 repo 同一層"
        "（github.com/helmet-png/gaia-dr3-export）。"
    )


server = _load_server()

COLS = [
    "source_id",
    "ag_gspphot", "ag_gspphot_lower", "ag_gspphot_upper",
    "azero_gspphot",
    "mh_gspphot", "mh_gspphot_lower", "mh_gspphot_upper",
    "teff_gspphot", "logg_gspphot",
    "mh_gspspec", "mh_gspspec_lower", "mh_gspspec_upper",
]


def main():
    members = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    ids = np.asarray(members["source_id"], np.int64)
    print(f"成員星 {len(ids):,} 顆")

    # 分批查詢，避免 IN 子句過長
    out_rows = {}
    batch = 500
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        idlist = ",".join(str(int(s)) for s in chunk)
        adql = (f"SELECT {', '.join(COLS)} "
                f"FROM gaiadr3.astrophysical_parameters "
                f"WHERE source_id IN ({idlist})")
        raw = server.run_tap_query(adql, "csv").decode("utf-8", "replace")
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        header = lines[0].split(",")
        for ln in lines[1:]:
            vals = ln.split(",")
            out_rows[vals[0]] = dict(zip(header, vals))
        print(f"  已查 {min(i+batch, len(ids)):,}/{len(ids):,}，"
              f"累積有資料 {len(out_rows):,} 顆", flush=True)

    print(f"\n共 {len(out_rows):,} 顆有天體物理參數 "
          f"({len(out_rows)/len(ids)*100:.1f}%)")

    def col(name):
        v = []
        for sid in ids:
            r = out_rows.get(str(int(sid)))
            x = r.get(name, "") if r else ""
            v.append(float(x) if x not in ("", "null") else np.nan)
        return np.array(v)

    t = Table({"source_id": ids})
    for c in COLS[1:]:
        t[c] = col(c)

    print(f"\n{'欄位':<24}{'有值':>8}{'中位':>10}{'16%':>10}{'84%':>10}")
    for c in ("ag_gspphot", "azero_gspphot", "mh_gspphot", "mh_gspspec"):
        v = np.asarray(t[c], float)
        ok = np.isfinite(v)
        if ok.sum() == 0:
            print(f"{c:<24}{0:>8}")
            continue
        q = np.percentile(v[ok], [16, 50, 84])
        print(f"{c:<24}{int(ok.sum()):>8}{q[1]:>10.4f}{q[0]:>10.4f}{q[2]:>10.4f}")

    dest = HERE / "data" / "astrophys.csv"
    t.write(dest, format="csv", overwrite=True)
    print(f"\n寫入 {dest}")

    ag = np.asarray(t["ag_gspphot"], float)
    ok = np.isfinite(ag)
    if ok.sum() > 20:
        # A_G / A_V 約 0.83（我們 config 用的消光係數）
        av = ag[ok] / 0.83
        q = np.percentile(av, [16, 50, 84])
        print(f"\n由 A_G 換算的 A_V：中位 {q[1]:.3f} "
              f"[{q[0]:.3f}, {q[2]:.3f}]，散布 {np.std(av):.3f}")
        print(f"對照：我們 CMD 擬合給的 A_V 在四參數版是 0.19、六參數版是 0.04，")
        print(f"      而輪廓測試顯示它可以在 0.08–0.32 之間隨金屬量滑動。")

    mh = np.asarray(t["mh_gspphot"], float)
    ok = np.isfinite(mh)
    if ok.sum() > 20:
        q = np.percentile(mh[ok], [16, 50, 84])
        print(f"\nGSP-Phot 金屬量：中位 {q[1]:.3f} [{q[0]:.3f}, {q[2]:.3f}]")
        print(f"對照：我們的六參數擬合給 0.194（貼在先驗上界 0.25 上）")


if __name__ == "__main__":
    main()
