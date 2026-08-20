# -*- coding: utf-8 -*-
"""C3：拿 Gaia 官方徑向速度做一個真正獨立於自行/視差的成員檢驗。

**為什麼徑向速度是獨立驗證，不是又一次同一份資料**：`pipeline/step1_membership`
的成員判定完全只用自行（pmra/pmdec）與視差（parallax）做群聚分析。徑向速度
是完全不同的觀測量（沿視線的都卜勒位移，不是切向運動），M45 星團有已知的
整體徑向速度（`config.toml` 的 `bulk_rv = 5.343` km/s，取自 HR23）。若一顆星
自行/視差判定為成員，但徑向速度跟星團整體值差很多，代表自行/視差恰好落在
星團範圍內只是巧合（前景/背景場星的機率性重疊），這是 `LIMITATIONS.md` C3
（與 HR23 一致不構成獨立驗證）在等的那種真正獨立觀測量。

**跟 C20 的關係（2026-08-13 CodeRabbit review 後修正）**：這支腳本原本想
順便查 C20（「20 顆判定分歧」）裡有沒有星帶 RV，但 `data/comparison.csv`
用現行門檻重算出的分歧集合是 367 顆，跟 `LIMITATIONS.md` 記錄的原始「20」
對不上（門檻定義不明）。**下面印出的「comparison.csv 現行分歧集合」是這
367 顆，不是 C20 的那 20 顆**，在 `c20_reconcile_disagree_set`（見
`WORK_BOARD.md`）把兩者定義對齊之前，不要把這支腳本的輸出當成查過 C20。

**限制（誠實列出）**：Gaia DR3 的徑向速度只對較亮、且 4,000–14,500 K 之間
的星有效（RVS 光譜儀的涵蓋範圍），M45 大部分是低質量暗星，**預期只有少數
星有徑向速度資料**，不能指望覆蓋全部 1,078／1,297 顆成員，但覆蓋到的部分
仍是有意義的獨立交叉核對。

跑法：`python scripts/data_prep/gaia_radial_velocity.py`（需要網路，走跟
`gaia_astrophys.py` 相同的 TAP 查詢路徑）。輸出 `data/radial_velocity.csv`
（含 `non_single_star`，供重現下面的分組統計），並在終端機印出：
（一）全體成員的徑向速度分布是否集中在 bulk_rv 附近、
（二）用**誤差加權**的顯著離群定義（|RV-bulk_rv|/RV誤差 > 5，不是固定
km/s 門檻）列出離群星，並跟 Gaia 自己的 `non_single_star` 旗標命中率、
`rv_nb_transits`（transit 數）中位數做分組對照，檢查離群是不是能被「已知
天測雙星」或「RV 雜訊較大（transit 少）」解釋掉。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod                          # noqa: E402
from pipeline.table_compat import Table                        # noqa: E402


def _load_server():
    """找到 gaia-export 姊妹專案並匯入它的 server.py，回傳該模組。

    跟 `fetch_gaia.py`／`prep.py` 的 `_load_server()` 同一套邏輯（見該檔
    說明）：只認環境變數 `GAIA_EXPORT_PATH` 與跟本 repo 同層的候選目錄，
    不 fallback 到任何機器特定的寫死路徑（2026-08-13 CodeRabbit review
    指出這支腳本原本寫死 `C:\\Users\\Alber\\...`，換一台機器就會找不到，
    已修好，改成跟其他 `scripts/data_prep/` 腳本同款可攜寫法）。
    """
    repo_root = HERE
    candidates = [os.environ.get("GAIA_EXPORT_PATH")] + [
        repo_root.parent / name for name in ("gaia-dr3-export", "gaia-export")
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

COLS = ["source_id", "radial_velocity", "radial_velocity_error",
        "rv_method_used", "rv_nb_transits", "non_single_star"]


def fetch_rv(ids: np.ndarray) -> dict:
    out_rows = {}
    batch = 500
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        idlist = ",".join(str(int(s)) for s in chunk)
        adql = (f"SELECT {', '.join(COLS)} FROM gaiadr3.gaia_source "
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
              f"累積有徑向速度 "
              f"{sum(1 for r in out_rows.values() if r.get('radial_velocity')):,} 顆",
              flush=True)
    return out_rows


def main():
    cfg = cfgmod.load()
    bulk_rv = getattr(cfg.step1_membership, "bulk_rv", None)
    if bulk_rv is None:
        bulk_rv = 5.343  # HR23，config.toml 未覆寫時的預設查詢值
        print(f"config.toml 沒有設定 bulk_rv，使用 HR23 文獻值 {bulk_rv} km/s "
              f"當比對基準。")

    members = Table.read(str(HERE / "data" / "cmd_members.csv"), format="csv")
    ids = np.asarray(members["source_id"], np.int64)
    print(f"成員星 {len(ids):,} 顆，開始查 Gaia DR3 radial_velocity...")
    rows = fetch_rv(ids)

    rv = np.full(len(ids), np.nan)
    rv_err = np.full(len(ids), np.nan)
    nb_transits = np.full(len(ids), np.nan)
    rv_method = np.array([""] * len(ids), dtype=object)
    non_single_star = np.full(len(ids), np.nan)
    for i, sid in enumerate(ids):
        r = rows.get(str(int(sid)))
        if not r:
            continue
        if r.get("radial_velocity") not in ("", "null", None):
            rv[i] = float(r["radial_velocity"])
            rv_err[i] = float(r["radial_velocity_error"]) if r.get(
                "radial_velocity_error") not in ("", "null") else np.nan
        if r.get("rv_nb_transits") not in ("", "null", None):
            nb_transits[i] = float(r["rv_nb_transits"])
        if r.get("non_single_star") not in ("", "null", None):
            non_single_star[i] = float(r["non_single_star"])
        rv_method[i] = r.get("rv_method_used", "")

    dest = HERE / "data" / "radial_velocity.csv"
    Table({"source_id": ids, "radial_velocity": rv,
           "radial_velocity_error": rv_err,
           "rv_nb_transits": nb_transits,
           "rv_method_used": rv_method,
           "non_single_star": non_single_star}).write(
        str(dest), format="csv", overwrite=True)
    print(f"\n寫入 {dest}")

    ok = np.isfinite(rv)
    print(f"\n{ok.sum():,}/{len(ids):,} 顆（{ok.sum()/len(ids)*100:.1f}%）"
          f"有 Gaia 徑向速度。")
    if ok.sum() == 0:
        return

    resid = rv[ok] - bulk_rv
    print(f"  相對 bulk_rv={bulk_rv} km/s 的偏差：中位數 "
          f"{np.median(resid):+.2f}、16-84% 區間 "
          f"[{np.percentile(resid,16):+.2f}, {np.percentile(resid,84):+.2f}] km/s")

    # 顯著離群定義用**誤差加權**的標準化殘差，不是固定 km/s 門檻——固定
    # 門檻會把「RV 誤差本來就大（暗星、少 transit）」跟「真的偏離」混在
    # 一起。sigma = |RV - bulk_rv| / RV 誤差，> 5 才算顯著離群
    # （2026-08-13 CodeRabbit review 指出舊版固定 5 km/s 門檻卻宣稱是
    # 「5σ」，數字對不上，已改成真的算 sigma）。沒有誤差值的星無法算
    # sigma，不計入離群判定。
    ok_err = ok & np.isfinite(rv_err) & (rv_err > 0)
    sigma = np.full(len(rv), np.nan)
    sigma[ok_err] = np.abs(rv[ok_err] - bulk_rv) / rv_err[ok_err]
    outlier = ok_err & (sigma > 5.0)

    print(f"  {ok_err.sum():,}/{ok.sum():,} 顆同時有 RV 與誤差，可以算"
          f"標準化殘差；其中 {outlier.sum()} 顆（"
          f"{outlier.sum()/max(ok_err.sum(),1)*100:.1f}%）偏離 bulk_rv "
          f"超過各自誤差棒的 5σ：")
    for sid, v, e, s in zip(ids[outlier], rv[outlier], rv_err[outlier],
                            sigma[outlier]):
        print(f"    source_id={sid}  RV={v:+.2f}±{e:.2f} km/s  ({s:.1f}σ)")

    # 分組對照：離群星是不是能用 Gaia 自己的 non_single_star 旗標、或
    # RV 雜訊較大（transit 數少）解釋掉，而不是假設一定是污染。
    ns_ok = ok_err & np.isfinite(non_single_star)
    if ns_ok.sum() > 0:
        base_ns_rate = (non_single_star[ns_ok] != 0).sum() / ns_ok.sum()
        out_ns = outlier & np.isfinite(non_single_star)
        out_ns_rate = ((non_single_star[out_ns] != 0).sum() / out_ns.sum()
                       if out_ns.sum() > 0 else float("nan"))
        print(f"\n  non_single_star!=0 命中率：全體有 RV 的 {ns_ok.sum()} 顆"
              f"裡 {base_ns_rate*100:.1f}%；離群組 {out_ns.sum()} 顆裡 "
              f"{out_ns_rate*100:.1f}%")
    nb_ok = ok_err & np.isfinite(nb_transits)
    if nb_ok.sum() > 0:
        base_nb_med = np.median(nb_transits[nb_ok])
        out_nb = outlier & np.isfinite(nb_transits)
        out_nb_med = (np.median(nb_transits[out_nb])
                     if out_nb.sum() > 0 else float("nan"))
        print(f"  rv_nb_transits 中位數：全體 {base_nb_med:.0f}，"
              f"離群組 {out_nb_med:.0f}")

    # comparison.csv 現行分歧集合——**不是** C20 的 20 顆（見檔頭說明）。
    comp_path = HERE / "data" / "comparison.csv"
    if comp_path.exists():
        comp = Table.read(str(comp_path), format="csv")
        my_member = np.asarray(comp["my_prob"], float) >= \
            cfg.step1_membership.membership_threshold
        hr23_member = np.asarray(comp["hr23_member"], float) > 0.5
        disagree = my_member != hr23_member
        disagree_ids = set(int(x) for x in
                           np.asarray(comp["source_id"], np.int64)[disagree])
        print(f"\ncomparison.csv 用現行門檻重算的分歧集合共 {disagree.sum()} "
              f"顆（跟 LIMITATIONS.md C20 記錄的原始「20」定義不同，見"
              f"檔頭說明，不要當成同一批星）。")
        hit = [(sid, v) for sid, v in zip(ids[ok], rv[ok])
               if int(sid) in disagree_ids]
        if hit:
            print(f"  其中 {len(hit)} 顆有徑向速度資料：")
            for sid, v in hit:
                side = "接近星團" if abs(v - bulk_rv) <= 5.0 else "遠離星團"
                print(f"    source_id={sid}  RV={v:+.2f} km/s  ({side})")
        else:
            print("  這批星裡沒有任何一顆有 Gaia 徑向速度資料——"
                  "在暗星團裡分歧星通常也是暗星，RVS 覆蓋不到，符合預期"
                  "（見腳本開頭的限制說明），不代表方法失敗。")


if __name__ == "__main__":
    main()
