# -*- coding: utf-8 -*-
"""C3／C20：拿 Gaia 官方徑向速度做一個真正獨立於自行/視差的成員檢驗。

**為什麼徑向速度是獨立驗證，不是又一次同一份資料**：`pipeline/step1_membership`
的成員判定完全只用自行（pmra/pmdec）與視差（parallax）做群聚分析。徑向速度
是完全不同的觀測量（沿視線的都卜勒位移，不是切向運動），M45 星團有已知的
整體徑向速度（`config.toml` 的 `bulk_rv = 5.343` km/s，取自 HR23）。若一顆星
自行/視差判定為成員，但徑向速度跟星團整體值差很多，代表自行/視差恰好落在
星團範圍內只是巧合（前景/背景場星的機率性重疊），這是 `LIMITATIONS.md` C3
（與 HR23 一致不構成獨立驗證）跟 C20（20 顆判定分歧無法解決）都在等的那種
真正獨立觀測量。

**限制（誠實列出）**：Gaia DR3 的徑向速度只對較亮、且 4,000–14,500 K 之間
的星有效（RVS 光譜儀的涵蓋範圍），M45 大部分是低質量暗星，**預期只有少數
星有徑向速度資料**，不能指望覆蓋全部 1,078／1,297 顆成員，但覆蓋到的部分
仍是有意義的獨立交叉核對，尤其 C20 那 20 顆判定分歧的星只要有一部分覆蓋
到就有用。

跑法：`python scripts/data_prep/gaia_radial_velocity.py`（需要網路，走跟
`gaia_astrophys.py` 相同的 TAP 查詢路徑）。輸出 `data/radial_velocity.csv`，
並在終端機印出（一）全體成員的徑向速度分布是否集中在 bulk_rv 附近、
（二）C20 判定分歧那批星裡，有徑向速度資料的幾顆分別落在哪一側。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\Users\Alber\Claude\gaia-export")

from pipeline import config as cfgmod                          # noqa: E402
from pipeline.table_compat import Table                        # noqa: E402
import server                                                  # noqa: E402

COLS = ["source_id", "radial_velocity", "radial_velocity_error",
        "rv_method_used", "rv_nb_transits"]


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
    for i, sid in enumerate(ids):
        r = rows.get(str(int(sid)))
        if r and r.get("radial_velocity") not in ("", "null", None):
            rv[i] = float(r["radial_velocity"])
            rv_err[i] = float(r["radial_velocity_error"]) if r.get(
                "radial_velocity_error") not in ("", "null") else np.nan

    ok = np.isfinite(rv)
    print(f"\n{ok.sum():,}/{len(ids):,} 顆（{ok.sum()/len(ids)*100:.1f}%）"
          f"有 Gaia 徑向速度。")
    if ok.sum() > 0:
        resid = rv[ok] - bulk_rv
        print(f"  相對 bulk_rv={bulk_rv} km/s 的偏差：中位數 "
              f"{np.median(resid):+.2f}、16-84% 區間 "
              f"[{np.percentile(resid,16):+.2f}, {np.percentile(resid,84):+.2f}] km/s")
        # M45 內部速度彌散約 0.5-1 km/s（文獻量級），偏差遠大於這個範圍的星
        # 值得個別列出，可能是判定錯的成員。
        outlier = ok & (np.abs(rv - bulk_rv) > 5.0)
        if outlier.sum() > 0:
            print(f"\n  偏差 >5 km/s 的星（{outlier.sum()} 顆，可能是自行/視差"
                  f"巧合落入星團範圍的場星，值得個別核對）：")
            for sid, v in zip(ids[outlier], rv[outlier]):
                print(f"    source_id={sid}  RV={v:+.2f} km/s")

    nb_transits = np.full(len(ids), np.nan)
    rv_method = np.array([""] * len(ids), dtype=object)
    for i, sid in enumerate(ids):
        r = rows.get(str(int(sid)))
        if r and r.get("rv_nb_transits") not in ("", "null", None):
            nb_transits[i] = float(r["rv_nb_transits"])
        if r:
            rv_method[i] = r.get("rv_method_used", "")

    dest = HERE / "data" / "radial_velocity.csv"
    Table({"source_id": ids, "radial_velocity": rv,
           "radial_velocity_error": rv_err,
           "rv_nb_transits": nb_transits,
           "rv_method_used": rv_method}).write(
        str(dest), format="csv", overwrite=True)
    print(f"\n寫入 {dest}")

    # C20：判定分歧的 20 顆星，看有幾顆能用 RV 交叉核對。
    comp_path = HERE / "data" / "comparison.csv"
    if comp_path.exists():
        comp = Table.read(str(comp_path), format="csv")
        my_member = np.asarray(comp["my_prob"], float) >= \
            cfg.step1_membership.membership_threshold
        hr23_member = np.asarray(comp["hr23_member"], float) > 0.5
        disagree = my_member != hr23_member
        disagree_ids = set(int(x) for x in
                           np.asarray(comp["source_id"], np.int64)[disagree])
        print(f"\ncomparison.csv 判定分歧共 {disagree.sum()} 顆"
              f"（對應 LIMITATIONS.md C20）。")
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
