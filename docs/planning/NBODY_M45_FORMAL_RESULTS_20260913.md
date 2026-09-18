# M45 PeTar 正式網格結果（2026-09-13）

## 執行範圍

在 senior24（24 執行緒）完成 10 組 M45 screening grid。每組使用 2,369 顆
component stars、BSE、Z=0.02，從 0 演化到 125 Myr，快照間隔 5 Myr；每組
均執行 `petar.data.gether`、`petar.data.process -i bse`，再以
`petar_pdmf_analysis.py` 比對 `data.0` 與 `data.25`。分析質量範圍為
0.30–2.50 M☉、11.68 pc 孔徑、32 個均勻投影方向。

完整原始快照保留在 senior24 的獨立 run 目錄；本倉庫只提交可重現分析所需的
JSON、profile CSV 與 ensemble 摘要，避免把大型快照加入 Git。

## 驗收

- 10/10 run 的 PeTar exit status 為 0，FDPS 正常完成。
- 10/10 run 的最終 `Error/Total` 絕對值小於 `1e-3`；本批最大值約
  `7.83e-6`。
- 10/10 run 的初始與末態 ID 可配對，沒有來源不明的新 ID。
- 三個 priority-1 中央 seed 的 correction 標準差為 `0.0343`，小於預先註冊
  的 `0.05` 門檻，因此保留其餘七組敏感度結果。

## 結果摘要

`delta_alpha` 定義為測得的 PDMF slope 減去 birth-IMF slope；回推 IMF 時要
把 `correction_to_add_to_pdmf_for_imf` 加回 PDMF slope。

| 集合 | correction 中位數 | 16–84% 範圍 | 標準差 |
|---|---:|---:|---:|
| 中央 3 seeds | +0.1735 | +0.1517–+0.1983 | 0.0343 |
| 完整 10 組 screening grid | +0.1380 | +0.0694–+0.1972 | 0.1175 |

完整 10 組的散布主要反映初始半徑、質量分層、聯星比例與 profile 的敏感度，
不能只報一個沒有誤差的修正值。

## 限制

這批是 component-star mass function 的動力修正，尚未把 unresolved systems、
Gaia 測光／成員選擇函數與銀河潮汐對照整合進最終推論。缺失 ID 也不能單獨
解讀成純逃逸，因為可能包含移除或合併。這些結果適合做科展階段報告與模型
敏感度展示，不應直接宣稱為最終 IMF 測量。

## 產出檔

- `results/m45_central_3seed_ensemble_20260912.json`
- `results/m45_full_10run_ensemble_20260913.json`
- `results/m45_*_pdmf.json` 與對應的 `*_pdmf_profiles.csv`
- `results/m45_central_3seed_ensemble_20260912_runs.csv`
- `results/m45_full_10run_ensemble_20260913_runs.csv`
