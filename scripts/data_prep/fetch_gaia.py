# -*- coding: utf-8 -*-
"""抓星團天區的 Gaia DR3 資料。

TAP 那層直接沿用 gaia-export 專案的 server.py（含 sync→async fallback），
不另外實作一套。

======================================================================
【這支程式在做什麼】
======================================================================
整條 pipeline 的第一步：向歐洲太空總署（ESA）的 Gaia 資料庫查詢「M45 周圍
一個圓錐範圍內、夠亮、夠近的所有星」，存成一份 CSV。之後的成員分類、色光圖、
擬合全部從這份檔案出發。
執行方式：python scripts/data_prep/fetch_gaia.py --ra 56.60083 --dec 24.11389
（座標取自 config.toml [target] 的註解；要重現既有樣本一定要手動給，見 --ra 的說明）
輸出：data/m45_r5_g18_plx4.csv（約 7,000 顆星）

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse         讀命令列參數
  importlib.util   必要時繞過 Python 的模組快取，從指定路徑重新載入 server.py
  os               讀環境變數 GAIA_EXPORT_PATH
  sys, pathlib     處理 import 路徑與檔案路徑
外部專案 gaia-export 的 server.py（另一個 repo：helmet-png/gaia-dr3-export）：
  server.resolve_name(名稱)
      向 CDS Sesame 名稱解析服務查天體名稱，回傳中心座標 (RA, Dec)
  server.count_sources(params)
      先送一個 "SELECT COUNT(*) …" 查詢，回傳符合條件的星有幾顆
  server.build_adql(params, top=n)
      把查詢條件組成 ADQL 查詢語句（天文資料庫用的 SQL 方言），例如：
        SELECT TOP n source_id, ra, dec, …
        FROM gaiadr3.gaia_source
        WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', 中心RA, 中心Dec, 半徑))
          AND phot_g_mean_mag <= 18 AND parallax >= 4
  server.run_tap_query(adql, "csv")
      送到 ESA 的 TAP 服務執行並取回 CSV。先試「同步」查詢；伺服器逾時
      （HTTP 408）就改走「非同步工作」，送出後輪詢等結果

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --target  天體名稱，預設 M45；用來命名輸出檔，沒給 --ra/--dec 時也用它查座標
  --radius  圓錐半徑（度），預設 5.0；M45 距離下約 11.8 pc
  --gmax    G 星等上限，預設 18.0；比 18 等更暗的星不要（測光品質差）
  --plxmin  視差下限（mas），預設 4.0；視差 4 mas ≈ 距離 250 pc 以內。
            M45 在約 136 pc（視差約 7.4 mas），切掉更遠的背景星可大幅減少雜訊；
            給 0 表示不切
  --force   檔案已存在也重抓
  --ra, --dec  手動指定圓錐中心；重現既有樣本時必須給（見下方說明）
  --top     跳過計數查詢、直接用這個上限取資料（繞過 ESA 計數查詢的逾時）
模組常數：
  COLUMNS   要取回的欄位：編號、位置、自行、視差及誤差（成員分類用）、
            三個波段星等與流量信噪比（色光圖與測光誤差用）、
            RUWE 與 non_single_star（雙星判定用）

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 88–144 行｜_load_server()：找到並載入 gaia-export 的 server.py
  核心 2｜第 203–225 行｜決定輸出檔名與圓錐中心座標
  核心 3｜第 227–263 行｜組查詢、送到 ESA、檢查有沒有被截斷、寫檔

======================================================================
【(d) 整體流程】
======================================================================
  讀參數 → 載入 gaia-export 的 server.py
    → 依參數組出輸出檔名；檔案已存在就結束（除非 --force）
    → 決定圓錐中心：有 --ra/--dec 用手動值，否則用 Sesame 查
    → 組查詢條件（圓錐、G 星等上限、視差下限、要的欄位）
    → 決定要取幾列：有 --top 用它，否則先送計數查詢
    → 組成 ADQL → 送到 ESA → 取回 CSV
    → 用了 --top 而且列數頂到上限 → 可能被截斷，報錯不寫檔
    → 寫入 data/<名稱>_r<半徑>_g<星等>_plx<視差>.csv
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

# ↓ REPO_ROOT：repo 根目錄（本檔在 scripts/data_prep/，往上三層）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# ↓ 輸出資料夾
DATA = REPO_ROOT / "data"


# ═══════════════ 核心 1：載入 gaia-export 的查詢工具 ═══════════════
def _load_server():
    """找到 gaia-export 姊妹專案並匯入它的 server.py，回傳該模組。

    gaia-export（github.com/helmet-png/gaia-dr3-export）不同機器 clone
    的位置不一樣，依序試：環境變數 > 跟這個 repo 同一層的常見資料夾名稱。
    只認有 server.py 的目錄，避免誤選到同名但不對的資料夾；不 fallback
    到任何機器特定的寫死路徑——那種路徑只要剛好存在（哪怕是別的、過期的
    checkout），就會被靜默接受，跑出錯的結果卻不報錯。

    延後到這裡才做（不是 module 頂層），這樣 --help 或單純 import 這個
    檔案不會因為找不到 gaia-export 就整個炸掉。

    `import server` 用的是全域模組名稱，若同一個 process 已經從別的路徑
    載入過 `server`，`sys.modules` 快取可能讓這次拿到錯的 checkout。
    載入後驗證 `server.__file__` 是否真的對到這次選中的路徑，不對就繞過
    快取重新載入。
    """
    # ↓ 候選位置，依優先順序：環境變數 GAIA_EXPORT_PATH，
    #   然後是跟這個 repo 同一層的 gaia-dr3-export、gaia-export 資料夾
    candidates = [os.environ.get("GAIA_EXPORT_PATH")] + [
        REPO_ROOT.parent / name for name in ("gaia-dr3-export", "gaia-export")
    ]
    for c in candidates:
        # ↓ 環境變數沒設時是 None，跳過
        if not c:
            continue
        c = Path(c)
        server_py = c / "server.py"
        # ↓ 資料夾存在、裡面也真的有 server.py 才採用
        if c.is_dir() and server_py.is_file():
            # ↓ 把這個資料夾放到 import 搜尋路徑最前面，再 import server
            sys.path.insert(0, str(c))
            import server
            # ↓ 安全檢查：Python 可能因為快取拿到別處的 server.py。
            #   載入的檔案路徑跟選中的不一樣，就直接從指定路徑重新載入
            if Path(server.__file__).resolve() != server_py.resolve():
                previous = sys.modules.get("server")
                spec = importlib.util.spec_from_file_location("server", server_py)
                server = importlib.util.module_from_spec(spec)
                sys.modules["server"] = server
                try:
                    spec.loader.exec_module(server)
                except Exception:
                    # ↓ 載入失敗就把快取恢復原狀再報錯
                    if previous is None:
                        sys.modules.pop("server", None)
                    else:
                        sys.modules["server"] = previous
                    raise
            return server
    # ↓ 所有候選位置都找不到 → 明確報錯，告訴使用者怎麼設定
    raise FileNotFoundError(
        "找不到 gaia-export 專案（含 server.py 的目錄）。"
        "設定環境變數 GAIA_EXPORT_PATH 指向它，或把它 clone 到跟本 repo 同一層"
        "（github.com/helmet-png/gaia-dr3-export）。"
    )

# 分群要用的三個量＋其誤差；光度與品質欄位供第 2、3 步用，不參與分群。
# flux_over_error 是必要的：前向模型要生成合成星團時，得知道真實觀測的測光
# 誤差有多大才能加上等量級的擾動。星等誤差 = 1.0857 / (flux/flux_error)。
COLUMNS = [
    # ↓ 每顆星的唯一編號與天球座標
    "source_id", "ra", "dec",
    # ↓ 成員分類用的三個量：自行（天球上的移動速度，兩個方向）與視差（距離）
    "pmra", "pmdec", "parallax",
    "pmra_error", "pmdec_error", "parallax_error",
    # ↓ 三個波段的星等與顏色
    "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp",
    # ↓ 流量信噪比：換算測光誤差用
    "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
    "phot_rp_mean_flux_over_error",
    # ↓ BP、RP 流量加總跟 G 流量的比值：太大代表受附近星光污染
    "phot_bp_rp_excess_factor",
    # ↓ 天測擬合品質；明顯大於 1 常代表未解析雙星
    "ruwe",
    # 第 4 步比較雙星判定法要用。non_single_star 是位元遮罩：
    # 1=天測雙星, 2=光譜雙星, 4=食雙星，可相加。
    "non_single_star",
]


def main():
    ap = argparse.ArgumentParser(description="抓 Gaia DR3 星團天區資料")
    ap.add_argument("--target", default="M45", help="天體名稱，用 CDS Sesame 解析")
    ap.add_argument("--radius", type=float, default=5.0, help="錐形半徑（度）")
    ap.add_argument("--gmax", type=float, default=18.0, help="G 星等上限")
    ap.add_argument("--plxmin", type=float, default=4.0,
                    help="視差下限（mas）；給 0 表示不切，對照跑用")
    ap.add_argument("--force", action="store_true", help="已有檔案也重抓")
    ap.add_argument("--ra", type=float, default=None,
                    help="錐形中心 RA（度），跳過 Sesame 名稱解析。"
                         "**要重現既有樣本時一定要用**：Sesame 對 M45 回的是"
                         "RA=56.86909，跟 config.toml [target] 註解裡記的"
                         "56.60083 差 0.27 度，錐形位置跟著偏，實測會讓既有"
                         "cmd_members.csv 的 1,078 顆成員有 2 顆落到新錐形外面。"
                         "做敏感度比較時輸入天區必須跟原本一致，否則量到的差異"
                         "會混進「天區不同」這個額外變因。")
    ap.add_argument("--dec", type=float, default=None,
                    help="錐形中心 Dec（度），跟 --ra 一起給。見 --ra 的說明。")
    ap.add_argument("--top", type=int, default=None,
                    help="跳過 count_sources() 的精確計數，直接用這個上限查。"
                         "**這是為了繞過伺服器端的硬限制，不是效能微調**："
                         "count_sources() 會對 18 億列的 gaia_source 做錐形+"
                         "星等+視差篩選再 COUNT(*)，M45 這組參數實測在 ESA 端"
                         "跑 183 秒後被伺服器自己的 statement timeout 砍掉"
                         "（錯誤是 canceling statement due to statement "
                         "timeout，不是本機網路問題），整條 D2 敏感度掃描因此"
                         "卡住（見 WORK_BOARD.md D2 進度說明）。主查詢本身不做"
                         "COUNT、只取前 N 列，反而跑得動。給值時會檢查實際取回"
                         "的列數有沒有頂到上限，頂到就中止並要求調大，不會靜默"
                         "給出一份被截斷的資料。")
    a = ap.parse_args()
    server = _load_server()

    # ═══════════════ 核心 2：決定輸出檔名與圓錐中心 ═══════════════
    DATA.mkdir(exist_ok=True)
    # ↓ 檔名由參數組成：例如 M45、5 度、G<18、視差>4 → m45_r5_g18_plx4.csv
    tag = a.target.lower().replace(" ", "")
    plx_tag = "noplx" if a.plxmin <= 0 else f"plx{a.plxmin:g}"
    out = DATA / f"{tag}_r{a.radius:g}_g{a.gmax:g}_{plx_tag}.csv"
    # ↓ 已經有這份檔案就不重抓（避免無意間覆蓋既有樣本）
    if out.exists() and not a.force:
        print(f"已存在，跳過：{out.name}（要重抓加 --force）")
        return

    # ↓ --ra、--dec 只給其中一個是錯誤用法，直接報錯
    if (a.ra is None) != (a.dec is None):
        ap.error("--ra 與 --dec 要嘛都給、要嘛都不給（只給一個會靜默用"
                 "Sesame 的另一半座標，錐形中心變成兩個來源的混合）")
    # ↓ 有手動座標就用手動的，否則請 Sesame 依名稱查
    if a.ra is not None:
        ra, dec = a.ra, a.dec
        print(f"{a.target} -> RA={ra:.5f}, Dec={dec:.5f}（手動指定，"
              f"跳過 Sesame）")
    else:
        ra, dec = server.resolve_name(a.target)
        print(f"{a.target} -> RA={ra:.5f}, Dec={dec:.5f}（Sesame 解析）")

    # ═══════════════ 核心 3：查詢 ESA 並寫檔 ═══════════════
    # ↓ 查詢條件：mode="cone" 圓錐查詢；mag_max 星等上限；columns 要的欄位
    params = {
        "mode": "cone", "ra": ra, "dec": dec, "radius": a.radius,
        "mag_max": a.gmax, "columns": COLUMNS,
    }
    # ↓ 視差下限 > 0 才加這個條件
    if a.plxmin > 0:
        params["parallax_min"] = a.plxmin

    # ↓ n：這次最多取幾列。有 --top 就直接用；否則先問伺服器符合條件的有幾顆
    if a.top is not None:
        n = a.top
        print(f"跳過精確計數，直接用上限 {n:,} 查（--top）")
    else:
        n = server.count_sources(params)
        print(f"符合條件：{n:,} 顆")

    # ↓ 組成 ADQL 查詢語句（SELECT TOP n 欄位 FROM gaia_source WHERE 條件）
    adql = server.build_adql(params, top=n)
    print("查詢中…（大天區不切視差時會走 async，可能要數分鐘）")
    # ↓ 送到 ESA 執行，取回 CSV 格式的原始位元組
    data = server.run_tap_query(adql, "csv")
    # ↓ 資料列數 = 換行數 − 1（扣掉第一行欄位名稱）
    rows = data.count(b"\n") - 1
    # 頂到上限就可能被截斷。**先檢查再寫檔**——寫下去之後下游沒有任何一步
    # 看得出這份資料是完整的還是被切一半的，那正是這個專案最怕的
    # 「檔案存在、數字看起來正常、其實不是我們以為的那個」。
    if a.top is not None and rows >= a.top:
        print(f"錯誤：取回 {rows:,} 列，等於或超過 --top {a.top:,} 的上限，"
              f"資料**可能被截斷**。把 --top 調大再跑一次（M45 這組參數的"
              f"實際量級約 7,000 顆，設 20000 有足夠餘裕）。沒有寫檔。",
              flush=True)
        raise SystemExit(1)
    # ↓ 原樣寫成 CSV 檔
    out.write_bytes(data)
    print(f"寫入 {out}（{rows:,} 列，{len(data):,} bytes）")


if __name__ == "__main__":
    main()
