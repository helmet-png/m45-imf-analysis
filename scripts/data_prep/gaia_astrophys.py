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

======================================================================
【這支程式在做什麼】
======================================================================
拿 cmd_members.csv 裡每顆成員星的 source_id，向 Gaia 的「天體物理參數表」
（gaiadr3.astrophysical_parameters）查這顆星的消光、金屬量、溫度、表面重力，
存成 data/astrophys.csv，並印出整個星團的中位數。
執行方式：python scripts/data_prep/gaia_astrophys.py
輸出用途：check_giant_subgiant_contamination.py 用其中的 logg（表面重力）
找出混進成員表的巨星，結果寫進 pipeline/step5_imf.py 的非成員名單。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  importlib.util, os, sys, pathlib   載入 gaia-export、處理路徑
第三方套件：
  numpy（np）  np.percentile（取 16、50、84 百分位）、np.isfinite、np.std
本專案其他模組：
  pipeline/table_compat.py  Table：只用 numpy 實作的簡易表格
外部專案 gaia-export 的 server.py：
  server.run_tap_query(adql, "csv")  送 ADQL 查詢到 ESA，取回 CSV 位元組
  ⚠ 這支在檔案被 import 時就載入 server.py（_load_server() 定義下方那行 server = _load_server()），
    跟其他 data_prep 程式「用到時才載入」的作法不同

======================================================================
【(b) 用到的參數與意義】
======================================================================
沒有命令列參數。寫死的值：
  batch = 500   每次查詢最多放 500 個 source_id（避免查詢語句太長）
  0.83          A_G / A_V，用來把 G 波段消光換成 V 波段消光（同 config 的 ext_coeff_g）
COLS（要查的欄位）：
  ag_gspphot（及上下界）  G 波段消光 A_G
  azero_gspphot           550 nm 處的消光 A_0（大致等於 A_V）
  mh_gspphot（及上下界）  金屬量（由低解析度光譜估）
  teff_gspphot            有效溫度
  logg_gspphot            表面重力；主序星約 4–5，巨星明顯較低
  mh_gspspec（及上下界）  金屬量（由高解析度光譜估，只有亮星有）
⚠ 結尾印出的「對照：四參數版 0.19、六參數版 0.04、六參數擬合 MH 0.194」
  是寫這支程式當時的舊擬合結果，不是目前的頭條數字（目前見 fit_real.py）。

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 144–177 行｜分批查詢 Gaia 天體物理參數表
  核心 2｜第 179–207 行｜整理成表格、印統計、寫檔
  核心 3｜第 209–227 行｜把 A_G 換成 A_V、印出跟擬合結果的對照

======================================================================
【(d) 整體流程】
======================================================================
  讀 data/cmd_members.csv 的 source_id
    → 每 500 個組一個「SELECT … WHERE source_id IN (…)」查詢 → 送出 → 解析 CSV
    → 累積成 {source_id: 那一列} 的字典
    → 依成員順序排成表格（查不到的星填 NaN）
    → 印出消光、金屬量的中位數與 16–84% 範圍
    → 寫 data/astrophys.csv
    → A_G ÷ 0.83 換成 A_V，印出分布；印出金屬量分布
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

# ↓ repo 根目錄（本檔在 scripts/data_prep/，往上三層），加進 import 路徑
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


# ↓ 檔案一被 import 就載入 gaia-export（找不到會直接報錯）
server = _load_server()

# ↓ 要向 Gaia 查的欄位（意義見檔頭 (b)）
COLS = [
    "source_id",
    "ag_gspphot", "ag_gspphot_lower", "ag_gspphot_upper",
    "azero_gspphot",
    "mh_gspphot", "mh_gspphot_lower", "mh_gspphot_upper",
    "teff_gspphot", "logg_gspphot",
    "mh_gspspec", "mh_gspspec_lower", "mh_gspspec_upper",
]


def main():
    # ═══════════════ 核心 1：分批查詢 ═══════════════
    # ↓ 成員星的 source_id（64 位元整數）
    members = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    ids = np.asarray(members["source_id"], np.int64)
    print(f"成員星 {len(ids):,} 顆")

    # 分批查詢，避免 IN 子句過長
    # ↓ out_rows：{source_id 字串: {欄位名: 值字串}}
    out_rows = {}
    batch = 500
    # ↓ 每次取 500 個 id：i = 0, 500, 1000, …
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        # ↓ 組成 "id1,id2,…" 放進 IN (…) 條件
        idlist = ",".join(str(int(s)) for s in chunk)
        adql = (f"SELECT {', '.join(COLS)} "
                f"FROM gaiadr3.astrophysical_parameters "
                f"WHERE source_id IN ({idlist})")
        # ↓ 送出查詢，取回 CSV 文字
        raw = server.run_tap_query(adql, "csv").decode("utf-8", "replace")
        # ↓ 去掉空行；第一行是欄位名，少於 2 行代表這批沒有任何資料
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        header = lines[0].split(",")
        # ↓ 每一行用逗號切開，跟欄位名配對成字典，以 source_id 為鍵存起來
        for ln in lines[1:]:
            vals = ln.split(",")
            out_rows[vals[0]] = dict(zip(header, vals))
        print(f"  已查 {min(i+batch, len(ids)):,}/{len(ids):,}，"
              f"累積有資料 {len(out_rows):,} 顆", flush=True)

    print(f"\n共 {len(out_rows):,} 顆有天體物理參數 "
          f"({len(out_rows)/len(ids)*100:.1f}%)")

    # ═══════════════ 核心 2：整理、統計、寫檔 ═══════════════
    def col(name):
        # ↓ 依成員順序取出某個欄位；查不到這顆星或值是空的就填 NaN
        v = []
        for sid in ids:
            r = out_rows.get(str(int(sid)))
            x = r.get(name, "") if r else ""
            v.append(float(x) if x not in ("", "null") else np.nan)
        return np.array(v)

    # ↓ 組成表格：source_id 加上 COLS 其餘每一欄
    t = Table({"source_id": ids})
    for c in COLS[1:]:
        t[c] = col(c)

    # ↓ 印出四個主要欄位：有值的星數、中位數、16%、84% 百分位
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

    # ═══════════════ 核心 3：換算 A_V 並印出對照 ═══════════════
    ag = np.asarray(t["ag_gspphot"], float)
    ok = np.isfinite(ag)
    if ok.sum() > 20:
        # A_G / A_V 約 0.83（我們 config 用的消光係數）
        # ↓ A_V = A_G ÷ 0.83
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
