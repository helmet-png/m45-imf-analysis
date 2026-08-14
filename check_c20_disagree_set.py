# -*- coding: utf-8 -*-
"""C20（c20_reconcile_disagree_set）：重建當初「20 顆判定分歧」的定義，
跟 `comparison.csv` 現在重算出的 367 顆對照，搞清楚差在哪裡。

**追查過程**：`_archive/C_membership_phase_analysis/` 底下的
`validate.py`／`disagree.py`／`investigate.py` 是原始分析用的腳本（已
歸檔，但邏輯還在）。`investigate.py` 的 docstring 明講「(2) 我判為成員但
HR23 完全沒收的那 20 顆是什麼來歷」，程式碼定義是：

    disputed = ids[(p >= .99) & ~np.isfinite(hr_p)]

也就是「我的成員機率 >= 0.99」**且**「這顆星完全不在 HR23 的成員表裡
（任何機率都沒有，不是機率低於門檻）」。這是比 C20 條目文字（「20 顆真正
的判定分歧」）更精確的原始定義。

**跟後來的 367 顆不是同一個東西**，差在兩處：
1. `my_id`／`my_prob` 的來源——`validate.py` 用的是 pyUPMASK **原始輸出**
   （所有候選星，含低機率的），不是 `data/cmd_members.csv`（已經用
   `membership_threshold` 篩過、又疊了測光品質篩選的最終樣本）。這個
   repo 現在的等價檔案是 `results/baseline.dat`（6,956 顆，`probs_final`
   欄位）。
2. 門檻與判定方式——原始「20」用「我的機率 >=0.99」+「完全不在 HR23
   名單」，367 顆用的是別的門檻／別的比對方式（不是這支腳本要查的，
   只確認不是同一個定義）。

這支腳本用 `results/baseline.dat`＋`data/hr23_Melotte_22.csv`（本機已有，
不需要網路）重建 `data/comparison.csv`（跟 `validate.py` 原始寫法一致的
欄位），再套用原始「20」的定義，看現在的資料能不能重現「20」這個數字。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main():
    res = Table.read(HERE / "results" / "baseline.dat", format="ascii")
    hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")

    my_id = np.asarray(res["source_id"], np.int64)
    my_p = np.asarray(res["probs_final"], float)
    hr_id = np.asarray(hr["GaiaDR3"], np.int64)
    hr_p = np.asarray(hr["Prob"], float)

    masked = my_p < 0
    print(f"pyUPMASK 原始輸出：{len(my_id):,} 顆（{int(masked.sum())} 顆"
          f"被離群遮罩，機率記為 -1）")
    print(f"HR23 全部成員：{len(hr_id):,} 顆")

    # 跟 validate.py 一致：truth 用 HR23 Prob>=0.5
    ref_id = hr_id[hr_p >= 0.5]
    truth = np.isin(my_id, ref_id)

    hr_prob_map = dict(zip(hr_id.tolist(), hr_p.tolist()))
    hr_p_aligned = np.array([hr_prob_map.get(int(i), np.nan) for i in my_id])

    print(f"\nHR23 Prob>=0.5 成員：{len(ref_id):,} 顆，"
          f"我的樣本中真成員 {int(truth.sum()):,} 顆")

    # 原始「20 顆」定義：我的機率 >=0.99，且完全不在 HR23 名單（任何機率）
    in_hr = np.isfinite(hr_p_aligned)
    disputed = my_id[(my_p >= 0.99) & ~in_hr]
    print(f"\n=== 原始定義重現：my_prob>=0.99 且完全不在 HR23 名單 ===")
    print(f"  {len(disputed)} 顆")
    if len(disputed):
        print(f"  source_id: {disputed.tolist()}")

    # 對照組：367 的定義比較接近「跟 HR23 Prob>=0.5 的判定不一致」，
    # 用 membership_threshold 等級的門檻在全樣本上算（不是 cmd_members.csv）
    print(f"\n=== 對照：my_prob>=0.7（membership_threshold 量級）且跟 "
          f"HR23 Prob>=0.5 不一致 ===")
    disagree_07 = ((my_p >= 0.7) != truth) & ~masked
    print(f"  {int(disagree_07.sum())} 顆（不是 367，因為這裡用的是"
          f"6,956 顆的原始輸出，367 是用 cmd_members.csv 算的，母體"
          f"不同，這裡只是示範門檻/母體選擇有多敏感，不是要重現 367）")

    dest = HERE / "data" / "comparison.csv"
    out = Table({"source_id": my_id, "my_prob": my_p,
                "hr23_member": truth.astype(int), "hr23_prob": hr_p_aligned})
    out.write(dest, format="csv", overwrite=True)
    print(f"\n寫入 {dest}（重建的逐星比對表，欄位跟 validate.py 原始輸出"
          f"一致，可以給 disagree.py／investigate.py 的邏輯繼續用）")


if __name__ == "__main__":
    main()
