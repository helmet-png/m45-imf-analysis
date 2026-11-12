<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->

# 依層級

外層呼叫內層：實驗 → 步驟 → 函式庫。函式庫沒有 main()，不能直接執行。

## 函式庫：只有計算，由別的程式 import

| 程式 | 做什麼 | 其他標籤 |
|---|---|---|
| [`pipeline/isochrones.py`](../../pipeline/isochrones.py) | 下載並快取等時線；依年齡與金屬量取出一條等時線 | PDMF 擬合、科學、共用、可引用 |
| [`pipeline/step5_imf.py`](../../pipeline/step5_imf.py) | 傳統法工具箱：星等查質量、截斷冪律的最大概似擬合 | PDMF 擬合、科學、傳統法、可引用 |
| [`pipeline/joint_fit.py`](../../pipeline/joint_fit.py) | 前向模型本體：合成含雙星的星團、轉成 Hess 圖、算概似 | PDMF 擬合、科學、前向模型、可引用 |

## 步驟：讀檔 → 計算 → 寫檔，流程裡固定執行一次

| 程式 | 做什麼 | 其他標籤 |
|---|---|---|
| [`scripts/data_prep/fetch_gaia.py`](../../scripts/data_prep/fetch_gaia.py) | 從 Gaia Archive 抓 M45 周圍 5 度內的星表 | 取得資料、科學、共用、可引用 |
| [`scripts/data_prep/prep.py`](../../scripts/data_prep/prep.py) | 把 Gaia 星表整理成 pyUPMASK 的輸入格式（座標做切平面投影） | 成員判定、科學、共用、可引用 |
| [`scripts/drivers/run_variant.py`](../../scripts/drivers/run_variant.py) | 執行 pyUPMASK，得到每顆星的成員機率 | 成員判定、科學、共用、可引用 |
| [`scripts/drivers/run_pipeline.py`](../../scripts/drivers/run_pipeline.py) | 取成員機率 ≥ 0.7 的星，做測光品質篩選，建立色光圖樣本與測光誤差模型 | 色光圖與測光品質、科學、共用、可引用 |
| [`scripts/data_prep/build_selection.py`](../../scripts/data_prep/build_selection.py) | 量出測光品質篩選在各星等留下多少比例的星（選擇函數） | 色光圖與測光品質、科學、共用、可引用 |
| [`scripts/nbody_petar/generate_training_grid.py`](../../scripts/nbody_petar/generate_training_grid.py) | 在 6 維初始條件空間抽出 430 組 N-body 模擬的設定 | N-body 模擬、科學、N-body、進行中 |
| [`scripts/nbody_petar/run_training_queue.py`](../../scripts/nbody_petar/run_training_queue.py) | 逐列執行訓練網格裡的每個 N-body 模擬，可中斷續跑 | N-body 模擬、科學、N-body、進行中 |
| [`scripts/nbody_petar/run_nbody_case.py`](../../scripts/nbody_petar/run_nbody_case.py) | 執行一個 N-body 模擬的完整外部程式鏈，並檢查能量守恆 | N-body 模擬、科學、N-body、進行中 |

## 實驗：用不同參數重複執行的擬合或測試

| 程式 | 做什麼 | 其他標籤 |
|---|---|---|
| [`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py) | 傳統法的五種雙星處理變體：在真實資料上量 α，並用假資料量各變體的偏差 | PDMF 擬合／驗證與誤差、科學、傳統法、可引用 |
| [`fit_real.py`](../../fit_real.py) | 前向模型對真實資料做多階段網格搜尋，產生頭條 α | PDMF 擬合、科學、前向模型、可引用 |
| [`injection_recovery.py`](../../injection_recovery.py) | 注入回收：用已知答案的假星團測擬合流程，量統計誤差與偏差 | 驗證與誤差、檢查、前向模型、可引用 |
| [`profile_lowmass.py`](../../profile_lowmass.py) | 掃描固定的低質量段冪次，量它對 α 的影響（系統誤差） | 驗證與誤差、檢查、前向模型、進行中 |
| [`scripts/nbody_petar/emulator_fit.py`](../../scripts/nbody_petar/emulator_fit.py) | 用所有模擬的統計量訓練高斯過程模擬器（正式推論尚未實作） | PDMF → IMF、科學、N-body、探索性 |
| [`notebooks/40_傳統法.py`](../../notebooks/40_傳統法.py) | 教學用：傳統法從成員星表到 α 的最短路徑，並跟正式結果檔比對 | PDMF 擬合、檢查、傳統法、可引用 |

## 不適用

- [`code_map/build_map.py`](../../code_map/build_map.py)：讀 catalog.json，生成程式地圖的所有頁面並做檢查
- [`cloud_queue.py`](../../cloud_queue.py)：把 cloud_queue.txt 裡的工作派到雲端機器執行並取回結果
