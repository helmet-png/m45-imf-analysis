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
    a = ap.parse_args()
    server = _load_server()

    DATA.mkdir(exist_ok=True)
    tag = a.target.lower().replace(" ", "")
    plx_tag = "noplx" if a.plxmin <= 0 else f"plx{a.plxmin:g}"
    out = DATA / f"{tag}_r{a.radius:g}_g{a.gmax:g}_{plx_tag}.csv"
    if out.exists() and not a.force:
        print(f"已存在，跳過：{out.name}（要重抓加 --force）")
        return

    ra, dec = server.resolve_name(a.target)
    print(f"{a.target} -> RA={ra:.5f}, Dec={dec:.5f}")

    params = {
        "mode": "cone", "ra": ra, "dec": dec, "radius": a.radius,
        "mag_max": a.gmax, "columns": COLUMNS,
    }
    if a.plxmin > 0:
        params["parallax_min"] = a.plxmin

    n = server.count_sources(params)
    print(f"符合條件：{n:,} 顆")

    adql = server.build_adql(params, top=n)
    print("查詢中…（大天區不切視差時會走 async，可能要數分鐘）")
    data = server.run_tap_query(adql, "csv")
    out.write_bytes(data)
    rows = data.count(b"\n") - 1
    print(f"寫入 {out}（{rows:,} 列，{len(data):,} bytes）")


if __name__ == "__main__":
    main()
