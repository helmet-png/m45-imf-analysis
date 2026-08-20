# 歸檔說明

2026-08-09 歸檔，共 24 支腳本。全部已確認**沒有任何核心 pipeline 程式引用它們**
（用 grep 查過 import），移動前後功能不受影響。歸檔理由是階段性任務已完成、
結果已收進 `研究日誌`、`STATE.md`、`LIMITATIONS.md` 等文件，程式本身留著備查。

## B_verification_diagnostics（方法學驗證，已完成）

`verify_twostage.py`（確認多階段搜尋沒卡假峰）、`check_split_walls.py`
（切半實驗貼牆診斷）、`bin_scaling_test.py`（否證「格子灌水」診斷）、
`measure_dav.py`（GSP-Phot 外部約束差異消光，負面結果）、`bootstrap_errors.py`
（失敗方法，已被 injection_recovery.py 取代）、`diagnose_chain.py`（MCMC 收斂診斷，
已被切半+注入回收取代）、`benchmark_arch.py`（ARM64 vs x64 效能對照）。

## C_membership_phase_analysis（成員判定階段，07-31~08-01）

`bulk_params.py`、`check_deproj.py`、`compare_variants.py`、`compare_prob_methods.py`、
`compare_depth.py`、`coverage_analysis.py`、`disagree.py`、`investigate.py`、
`ladder.py`、`prior_fix.py`、`prob_tail.py`、`validate.py`、`global_imf_scope.py`。
結果已收進報告《報告_完整說明.md》第三章。

## D_abandoned_approaches（明確死路）

`dustmap_fetch.py` / `dustmap_query.py`（三維塵埃圖，healpy 裝不起來而放棄，
已改用 Gaia 天體物理參數表）、`download_fine_grid.py` / `download_wide_grid.py`
（一次性 isochrone 下載腳本，功能已併入 `pipeline/isochrones.py`）。

## run_m45.log（2026-08-13 歸檔，最初一次 baseline 執行的完整 log）

專案最早一筆 commit 就有的純文字檔，不是程式——是第 1 步成員判定
（`run_variant.py`）第一次成功執行時的完整終端機輸出：random seed 42、
6,956 顆 Gaia 星、25 輪外圈聚類迭代逐輪記錄，結尾的成員機率門檻統計
（`P>(.5, .75, .9, .95, .99): 1318, 1293, 1264, 1237, 1188`）至今仍是
README 記錄的基準結果來源。沒有任何程式讀取這個檔案，純粹是存證用途。

## 沒有歸檔的（刻意保留在根目錄）

- **E 類（核心 pipeline）**：`config.toml`、`run_pipeline.py`、`pipeline/*`、
  `fetch_gaia.py`、`prep.py`、`run_variant.py`、`fit_real.py`、
  `injection_recovery.py`、`measure_overconfidence.py`、`traditional_accounting.py`、
  `profile_lowmass.py`、`profile_test.py`、`build_selection.py`、
  `selection_probe.py`（後者是前者的依賴）、`build_dr2_grid.py`、
  `build_mist_grid.py`、`run_queue.py`、`queue.txt`、`plots.py`、`plot_step3.py`、
  `plot_step45.py`、`gaia_astrophys.py`、`kaggle_sync.py`。
  **2026-08-09 使用者原指示含 E，但暫緩**：本機背景佇列當時正在跑
  （`p3b_dr2fit`），移走 `pipeline/` 會讓多行程平行搜尋的工人行程找不到模組
  而中斷。等佇列跑完、使用者確認後再處理。
- **F 類（狀態不確定）**：`run_joint.py`、`final_imf.py`——是否還需要待確認。
- **hb_\*.py 與 hb_backup/**：誤植自另一個 fork（IMF 教材匯入 Heptabase 用），
  與本專案無關，等使用者確認目標路徑後搬移，不歸檔在這裡。
