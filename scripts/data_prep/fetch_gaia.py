# -*- coding: utf-8 -*-
"""抓星團天區的 Gaia DR3 資料。

TAP 那層直接沿用 gaia-export 專案的 server.py（含 sync→async fallback），
不另外實作一套。
"""
import argparse
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = REPO_ROOT / "data"


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

# 分群要用的三個量＋其誤差；光度與品質欄位供第 2、3 步用，不參與分群。
# flux_over_error 是必要的：前向模型要生成合成星團時，得知道真實觀測的測光
# 誤差有多大才能加上等量級的擾動。星等誤差 = 1.0857 / (flux/flux_error)。
COLUMNS = [
    "source_id", "ra", "dec",
    "pmra", "pmdec", "parallax",
    "pmra_error", "pmdec_error", "parallax_error",
    "phot_g_mean_mag", "phot_bp_mean_mag", "phot_rp_mean_mag", "bp_rp",
    "phot_g_mean_flux_over_error", "phot_bp_mean_flux_over_error",
    "phot_rp_mean_flux_over_error",
    "phot_bp_rp_excess_factor",
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

    DATA.mkdir(exist_ok=True)
    tag = a.target.lower().replace(" ", "")
    plx_tag = "noplx" if a.plxmin <= 0 else f"plx{a.plxmin:g}"
    out = DATA / f"{tag}_r{a.radius:g}_g{a.gmax:g}_{plx_tag}.csv"
    if out.exists() and not a.force:
        print(f"已存在，跳過：{out.name}（要重抓加 --force）")
        return

    if (a.ra is None) != (a.dec is None):
        ap.error("--ra 與 --dec 要嘛都給、要嘛都不給（只給一個會靜默用"
                 "Sesame 的另一半座標，錐形中心變成兩個來源的混合）")
    if a.ra is not None:
        ra, dec = a.ra, a.dec
        print(f"{a.target} -> RA={ra:.5f}, Dec={dec:.5f}（手動指定，"
              f"跳過 Sesame）")
    else:
        ra, dec = server.resolve_name(a.target)
        print(f"{a.target} -> RA={ra:.5f}, Dec={dec:.5f}（Sesame 解析）")

    params = {
        "mode": "cone", "ra": ra, "dec": dec, "radius": a.radius,
        "mag_max": a.gmax, "columns": COLUMNS,
    }
    if a.plxmin > 0:
        params["parallax_min"] = a.plxmin

    if a.top is not None:
        n = a.top
        print(f"跳過精確計數，直接用上限 {n:,} 查（--top）")
    else:
        n = server.count_sources(params)
        print(f"符合條件：{n:,} 顆")

    adql = server.build_adql(params, top=n)
    print("查詢中…（大天區不切視差時會走 async，可能要數分鐘）")
    data = server.run_tap_query(adql, "csv")
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
    out.write_bytes(data)
    print(f"寫入 {out}（{rows:,} 列，{len(data):,} bytes）")


if __name__ == "__main__":
    main()
