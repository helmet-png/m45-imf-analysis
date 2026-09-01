# M45 工作板狀態稽核（高中生版）

日期：2026-09-01（Asia/Taipei）

## 為什麼要做這份稽核

工作板的用途是避免不同協作者重複計算。這次只比較 GitHub `main` 上的
`WORK_BOARD.md`、`WORK_BOARD_DONE.md`、`cloud_queue.txt`、
`results/RESULTS_LOG.md` 與相關 PR；沒有重跑任何 IMF 或前向模型。

「結果檔還沒出現在 GitHub」只能證明結果尚未上傳，不能證明雲端機器仍在
運算。以下把已驗證、尚未驗證與需要修正的地方分開寫。

## 已驗證的落差

### 1. C19 已完成，但仍列在待辦

- `WORK_BOARD.md` 仍把 `extra_scatter_sensitivity（C19）` 標成「尚未進行」。
- `results/RESULTS_LOG.md` 已記錄 2026-08-28 的正式輸出
  `results/injection_recovery_c19_scatter.npz`。
- 已記錄的保守判讀是：目前沒有看到 alpha 偏差隨額外散布單調變化，但
  跨試驗散布可能變大；每個量級只有 3 次試驗，不能下強結論。

建議：將 C19 從 `WORK_BOARD.md` 搬到 `WORK_BOARD_DONE.md`，保留上述但書，
並依協作規則同步檢查 `LIMITATIONS.md` 與 `PAPER_OUTLINE.md`。

### 2. P6b 已完成並合併，不應再列為未完成依賴

- PR #152 已於 2026-08-31 合併，merge commit 為
  `618379f1ef7b2aac585d74b5107774d181bc8bf6`。
- `results/RESULTS_LOG.md` 已記錄 P6b 的 9/9 試驗驗收：識別度斜率 0.796，
  bootstrap 95% 範圍 0.593–1.019。
- P6b 支持低質量段冪次可被資料辨識，但不取代 P6 的
  `d(alpha)/d(p)` 正式輪廓。

建議：任何仍寫「P6b 待跑／待驗收」的文字都應更新；P6 本身仍是不同任務。

### 3. p6 已派工，但工作板表格仍寫「尚未進行」

- `cloud_queue.txt` 已有唯一標籤 `p6_lowmass_v3`，指派給 `gcp1`。
- `WORK_BOARD.md` 同時在後文寫明 p6 已排入 gcp1，但表格狀態仍是
  「尚未進行」，兩處互相矛盾。
- GitHub `main` 目前只有舊檔
  `results/profile_lowmass_legacy_no_manifest.npz`，尚無可驗收的正式新檔。

建議：在取得 worker 執行證據前，表格可寫「進行中」並在說明中明確標記
「已派工；實際執行狀態未知」。不要僅因 GitHub 沒有結果就宣稱它仍在跑，
也不要重複派同一標籤。

### 4. BP15/BP20 已進入正式派工，不再是「尚未進行」

- 正式 40k 配對的 offsets 0、1、2 已完成；PR #166 的描述記錄三組
  BP15−BP20 alpha 差為 +0.067、+0.222、+0.044。
- PR #166 於 2026-08-31 合併，只把 offsets 3、4 的四個工作加入
  `cloud_queue.txt`，不是四份結果檔。
- 正式彙整器要求 5 組唯一 offset 全部到齊，缺一組就拒絕計算；因此目前
  仍不能產生正式平均差或科學結論。

建議：將工作板狀態改為「進行中」，說明 offsets 0–2 已完成、3–4 已排隊；
等 5 組到齊後再執行 fail-closed 彙整與 manifest 驗收。

## 尚未驗證

- 本機沒有可用的私有 worker 設定，因此本次無法直接證明 `gcp1` 的 p6
  正在執行、排隊或已失敗。
- 本次沒有取得 offsets 3、4 的 Kaggle 執行狀態；只能確認它們已加入
  GitHub 的 `cloud_queue.txt`。
- 沒有新的正式 p6 結果，因此不能計算 5 個 p 點、3 repeats、斜率或
  不確定度。

## 建議修正順序

1. 先修正 C19 與 P6b 的完成狀態，降低重複計算風險。
2. 將 p6 與 BP15/BP20 表格改成「進行中」，但把 worker 狀態寫成未知，
   直到取得可查證的執行紀錄。
3. BP offsets 3、4 到齊後，使用既有彙整器一次完成五組驗收；不要用三組
   中間值代替正式結論。
4. p6 新檔到齊後再檢查 manifest、完整性、邊界、5×3 結構、斜率與
   不確定度；任何一關沒過都不能寫成 IMF 結論。

## 一句話摘要

目前真正需要避免的不是「算得不夠多」，而是工作板狀態落後造成重複計算，
以及把「已派工」誤寫成「已確認正在運算」。
