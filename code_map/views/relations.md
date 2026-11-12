<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->

# 每支程式的上下游

「import」與「被誰 import」是每次從原始碼自動抽出的；讀、寫、呼叫是 catalog.json 裡登記的。標 ※ 的是還沒登記的程式。

## scripts/data_prep/fetch_gaia.py

從 Gaia Archive 抓 M45 周圍 5 度內的星表

- 讀：`ext:Gaia Archive`
- 寫：`data/m45_r5_g18_plx4.csv`
- 呼叫（另開行程執行）：—
- import：—
- 被誰 import：—

## scripts/data_prep/prep.py

把 Gaia 星表整理成 pyUPMASK 的輸入格式（座標做切平面投影）

- 讀：`data/m45_r5_g18_plx4.csv`
- 寫：`prepared/m45_raw.dat`
- 呼叫（另開行程執行）：—
- import：—
- 被誰 import：—

## scripts/drivers/run_variant.py

執行 pyUPMASK，得到每顆星的成員機率

- 讀：`prepared/m45_raw.dat`
- 寫：`results/baseline.dat`
- 呼叫（另開行程執行）：`ext:pyUPMASK`
- import：—
- 被誰 import：—

## scripts/drivers/run_pipeline.py

取成員機率 ≥ 0.7 的星，做測光品質篩選，建立色光圖樣本與測光誤差模型

- 讀：`results/baseline.dat`、`data/m45_r5_g18_plx4.csv`
- 寫：`data/cmd_members.csv`、`data/errmodel.npz`
- 呼叫（另開行程執行）：—
- import：[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/step2_cmd.py`](../../pipeline/step2_cmd.py) ※、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/step4_binaries.py`](../../pipeline/step4_binaries.py) ※、[`pipeline/step5_imf.py`](../../pipeline/step5_imf.py)
- 被誰 import：—

## scripts/data_prep/build_selection.py

量出測光品質篩選在各星等留下多少比例的星（選擇函數）

- 讀：`data/m45_r5_g18_plx4.csv`
- 寫：`data/selection.npz`
- 呼叫（另開行程執行）：—
- import：[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/selection.py`](../../pipeline/selection.py) ※、[`scripts/diagnostics/selection_probe.py`](../../scripts/diagnostics/selection_probe.py) ※
- 被誰 import：—

## pipeline/isochrones.py

下載並快取等時線；依年齡與金屬量取出一條等時線

- 讀：`ext:PARSEC 等時線網頁服務`
- 寫：`isochrones/parsec_*.dat`
- 呼叫（另開行程執行）：—
- import：[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※
- 被誰 import：[`fit_real.py`](../../fit_real.py)、[`injection_recovery.py`](../../injection_recovery.py)、[`notebooks/40_傳統法.py`](../../notebooks/40_傳統法.py)、[`profile_lowmass.py`](../../profile_lowmass.py)、[`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py)、[`scripts/drivers/run_pipeline.py`](../../scripts/drivers/run_pipeline.py)

## pipeline/step5_imf.py

傳統法工具箱：星等查質量、截斷冪律的最大概似擬合

- 讀：—
- 寫：—
- 呼叫（另開行程執行）：—
- import：[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※
- 被誰 import：[`fit_real.py`](../../fit_real.py)、[`notebooks/40_傳統法.py`](../../notebooks/40_傳統法.py)、[`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py)、[`scripts/drivers/run_pipeline.py`](../../scripts/drivers/run_pipeline.py)

## scripts/diagnostics/traditional_accounting.py

傳統法的五種雙星處理變體：在真實資料上量 α，並用假資料量各變體的偏差

- 讀：`data/cmd_members.csv`、`data/errmodel.npz`、`data/selection.npz`、`isochrones/parsec_*.dat`
- 寫：`results/traditional_accounting_v2.npz`
- 呼叫（另開行程執行）：—
- import：[`injection_recovery.py`](../../injection_recovery.py)、[`measure_overconfidence.py`](../../measure_overconfidence.py) ※、[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/joint_fit.py`](../../pipeline/joint_fit.py)、[`pipeline/selection.py`](../../pipeline/selection.py) ※、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/step5_imf.py`](../../pipeline/step5_imf.py)、[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※
- 被誰 import：—

## pipeline/joint_fit.py

前向模型本體：合成含雙星的星團、轉成 Hess 圖、算概似

- 讀：—
- 寫：—
- 呼叫（另開行程執行）：—
- import：[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※
- 被誰 import：[`fit_real.py`](../../fit_real.py)、[`injection_recovery.py`](../../injection_recovery.py)、[`profile_lowmass.py`](../../profile_lowmass.py)、[`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py)

## fit_real.py

前向模型對真實資料做多階段網格搜尋，產生頭條 α

- 讀：`data/cmd_members.csv`、`data/errmodel.npz`、`data/selection.npz`、`isochrones/parsec_*.dat`
- 寫：`results/fit_real*.npz`
- 呼叫（另開行程執行）：—
- import：[`injection_recovery.py`](../../injection_recovery.py)、[`measure_overconfidence.py`](../../measure_overconfidence.py) ※、[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/joint_fit.py`](../../pipeline/joint_fit.py)、[`pipeline/selection.py`](../../pipeline/selection.py) ※、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/step5_imf.py`](../../pipeline/step5_imf.py)、[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※、[`scripts/tools/checkpoint.py`](../../scripts/tools/checkpoint.py) ※、[`scripts/tools/preflight.py`](../../scripts/tools/preflight.py) ※
- 被誰 import：—

## injection_recovery.py

注入回收：用已知答案的假星團測擬合流程，量統計誤差與偏差

- 讀：`data/cmd_members.csv`、`data/errmodel.npz`、`data/selection.npz`、`isochrones/parsec_*.dat`
- 寫：`results/injection_recovery*.npz`
- 呼叫（另開行程執行）：—
- import：[`measure_overconfidence.py`](../../measure_overconfidence.py) ※、[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/joint_fit.py`](../../pipeline/joint_fit.py)、[`pipeline/selection.py`](../../pipeline/selection.py) ※、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※、[`scripts/tools/checkpoint.py`](../../scripts/tools/checkpoint.py) ※、[`scripts/tools/preflight.py`](../../scripts/tools/preflight.py) ※
- 被誰 import：[`fit_real.py`](../../fit_real.py)、[`profile_lowmass.py`](../../profile_lowmass.py)、[`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py)

## profile_lowmass.py

掃描固定的低質量段冪次，量它對 α 的影響（系統誤差）

- 讀：`data/cmd_members.csv`、`data/errmodel.npz`、`data/selection.npz`、`isochrones/parsec_*.dat`
- 寫：`results/profile_lowmass*.npz`
- 呼叫（另開行程執行）：—
- import：[`injection_recovery.py`](../../injection_recovery.py)、[`measure_overconfidence.py`](../../measure_overconfidence.py) ※、[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/joint_fit.py`](../../pipeline/joint_fit.py)、[`pipeline/selection.py`](../../pipeline/selection.py) ※、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※、[`scripts/tools/checkpoint.py`](../../scripts/tools/checkpoint.py) ※、[`scripts/tools/preflight.py`](../../scripts/tools/preflight.py) ※
- 被誰 import：—

## scripts/nbody_petar/generate_training_grid.py

在 6 維初始條件空間抽出 430 組 N-body 模擬的設定

- 讀：—
- 寫：`petar_m45_training_grid.csv`
- 呼叫（另開行程執行）：—
- import：[`scripts/nbody_petar/petar_m45_grid.py`](../../scripts/nbody_petar/petar_m45_grid.py) ※
- 被誰 import：—

## scripts/nbody_petar/run_training_queue.py

逐列執行訓練網格裡的每個 N-body 模擬，可中斷續跑

- 讀：`petar_m45_training_grid.csv`
- 寫：`runs_training/queue_progress.json`
- 呼叫（另開行程執行）：`scripts/nbody_petar/run_nbody_case.py`
- import：[`scripts/nbody_petar/petar_m45_grid.py`](../../scripts/nbody_petar/petar_m45_grid.py) ※
- 被誰 import：—

## scripts/nbody_petar/run_nbody_case.py

執行一個 N-body 模擬的完整外部程式鏈，並檢查能量守恆

- 讀：`petar_m45_training_grid.csv`
- 寫：`runs_training/*/result.json`
- 呼叫（另開行程執行）：`ext:mcluster_sse`、`ext:PeTar`
- import：[`scripts/nbody_petar/petar_m45_grid.py`](../../scripts/nbody_petar/petar_m45_grid.py) ※
- 被誰 import：—

## scripts/nbody_petar/emulator_fit.py

用所有模擬的統計量訓練高斯過程模擬器（正式推論尚未實作）

- 讀：`runs_training/*/observed.stats.json`、`petar_m45_training_grid.csv`、`results/nbody_observed_targets.json`
- 寫：—
- 呼叫（另開行程執行）：—
- import：—
- 被誰 import：—

## notebooks/40_傳統法.py

教學用：傳統法從成員星表到 α 的最短路徑，並跟正式結果檔比對

- 讀：`data/cmd_members.csv`、`isochrones/parsec_*.dat`、`results/traditional_accounting_v2.npz`
- 寫：—
- 呼叫（另開行程執行）：—
- import：[`measure_overconfidence.py`](../../measure_overconfidence.py) ※、[`pipeline/config.py`](../../pipeline/config.py) ※、[`pipeline/isochrones.py`](../../pipeline/isochrones.py)、[`pipeline/step3_age.py`](../../pipeline/step3_age.py) ※、[`pipeline/step5_imf.py`](../../pipeline/step5_imf.py)、[`pipeline/table_compat.py`](../../pipeline/table_compat.py) ※
- 被誰 import：—

## code_map/build_map.py

讀 catalog.json，生成程式地圖的所有頁面並做檢查

- 讀：`code_map/catalog.json`
- 寫：—
- 呼叫（另開行程執行）：—
- import：—
- 被誰 import：—

## cloud_queue.py

把 cloud_queue.txt 裡的工作派到雲端機器執行並取回結果

- 讀：`cloud_queue.txt`
- 寫：`logs/cloud_queue_done.txt`
- 呼叫（另開行程執行）：—
- import：[`gcp_vm_lifecycle.py`](../../gcp_vm_lifecycle.py) ※、[`kaggle_accounts.py`](../../kaggle_accounts.py) ※、[`kaggle_queue.py`](../../kaggle_queue.py) ※、[`run_queue.py`](../../run_queue.py) ※、[`ssh_sync.py`](../../ssh_sync.py) ※、[`ssh_workers.py`](../../ssh_workers.py) ※
- 被誰 import：—
