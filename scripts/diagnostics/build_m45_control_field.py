# -*- coding: utf-8 -*-
"""D19 Stage 2：建 M45 自己的 control field，供 P(member) 可靠度 vs G 用。

**問題背景**：`scripts/multicluster/prepare_cluster_tier2.py` 的
`fetch_control_field()` 已經有一個 control field 機制，但只服務
NGC 2632／NGC 3532 兩個 Tier 2 對照星團——M45（Tier 1，本專案主目標）
完全沒有對應的檔案。而且那支函式的目的也不一樣：它查一塊鄰近但獨立
的天區、拿來校準**測光品質選擇函數**（哪些星通過 SNR 門檻），不是拿來
測**成員判定演算法本身**（pyUPMASK 給的 P(member) 準不準）。

D19 Stage 2 要問的問題是：把成員深度從 G<18 延伸到 G<20，pyUPMASK 的
5D 天測分群在暗端還可不可靠？回答這個問題需要一批**已知不是成員、
但混進同一批要餵給 pyUPMASK 的資料裡**的星，跑完之後看 pyUPMASK 給
這些「已知非成員」多高的機率——如果暗端（G→20）這個機率系統性升高，
代表暗端天測雜訊讓演算法沒辦法把真場星跟真成員分開，這就是接縫。

**跟 Tier 2 版本的關鍵差異——這裡不用發新的 TAP 查詢**：M45 自己的
場星樣本 `data/m45_r5_g20_plx4.csv`（5° 錐，G<20，9,278 顆）已經覆蓋
了 Stage 2 需要的全部深度，裡面絕大多數星本來就不是成員（只有 1,078
顆是）。用這份既有資料直接篩「運動學上絕對不可能是成員」的子集，
不需要再打一次 Gaia TAP。

**篩法**：算現有 1,078 顆成員的 (pmra, pmdec, parallax) 中心與離散度，
挑場星裡任一維度偏離中心超過 10 個成員自己的標準差的星，當「已知
非成員」。10σ 是刻意保守的門檻——確保挑到的星裡不會混進任何運動學
邊緣的真成員（例如潮汐尾候選），代價是犧牲一些樣本數，但即使在 10σ
這麼嚴格的門檻下每個 0.5 星等分箱仍有 900+ 顆可用，遠超過需要的量。

用法：
    python scripts/diagnostics/build_m45_control_field.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

FIELD_PATH = HERE / "data" / "m45_r5_g20_plx4.csv"
MEMBERS_PATH = HERE / "data" / "cmd_members.csv"
OUT_PATH = HERE / "data" / "m45_control_field.csv"

SIGMA_MULT = 10.0
MIN_ROWS_PER_BIN = 100
G_BINS = np.arange(16.0, 20.5, 0.5)


def main():
    field = pd.read_csv(FIELD_PATH)
    members = pd.read_csv(MEMBERS_PATH)

    c_pmra, c_pmdec, c_plx = (members["pmra"].median(),
                              members["pmdec"].median(),
                              members["parallax"].median())
    s_pmra, s_pmdec, s_plx = (members["pmra"].std(),
                              members["pmdec"].std(),
                              members["parallax"].std())
    print(f"成員運動學中心：pmra={c_pmra:.3f}±{s_pmra:.3f}, "
          f"pmdec={c_pmdec:.3f}±{s_pmdec:.3f}, "
          f"parallax={c_plx:.3f}±{s_plx:.3f} mas（N={len(members)}）")

    member_ids = set(members["source_id"].astype(np.int64))
    not_member = ~field["source_id"].astype(np.int64).isin(member_ids)

    far = ((field["pmra"] - c_pmra).abs() > SIGMA_MULT * s_pmra) | \
          ((field["pmdec"] - c_pmdec).abs() > SIGMA_MULT * s_pmdec) | \
          ((field["parallax"] - c_plx).abs() > SIGMA_MULT * s_plx)

    control = field[not_member & far].reset_index(drop=True)
    print(f"\ncontrol field：{len(control)} 顆（門檻 {SIGMA_MULT:g}σ，"
          f"場星總數 {len(field)}）")

    print(f"\n{'G 區間':>12}{'control 顆數':>14}")
    ok = True
    for lo, hi in zip(G_BINS[:-1], G_BINS[1:]):
        n = int(((control["phot_g_mean_mag"] >= lo) &
                (control["phot_g_mean_mag"] < hi)).sum())
        flag = "" if n >= MIN_ROWS_PER_BIN else "  <- 不足"
        ok &= n >= MIN_ROWS_PER_BIN
        print(f"  {lo:>4.1f}-{hi:<5.1f}{n:>10d}{flag}")

    control.to_csv(OUT_PATH, index=False)
    print(f"\n寫入 {OUT_PATH.relative_to(HERE)}")
    print("每個分箱都 >= 最低需求" if ok else
          "**警告**：至少一個分箱樣本數不足，Stage 2 分析前要先處理")


if __name__ == "__main__":
    main()
