# 新對話的開場 prompt

把「===」以下整段複製貼上，當作新對話的第一句話。這份只放長期適用的
開場說明，不放進度快照——進度一律以下面列的文件為準。

===

我在做高中天文專研：用 Gaia DR3 資料求疏散星團 M45 的初始質量函數（IMF）。
請先讀 repo 裡的最新文件再動手，不要憑記憶或舊摘要，也不要預設任何舊
結論是對的——這個專案推翻過好幾個原本以為沒問題的結果。

## 專案位置

- GitHub：`github.com/helmet-png/m45-imf-analysis`（公開 repo）
- 本機：`C:\Users\Alber\Claude\m45_membership\`
- `results/` 整個進版控；`isochrones/`、`kaggle_work/`、`kaggle_results/`、
  原始 Gaia 下載檔不進版控（可重建，見 README.md「環境建置」）。

## 必讀（依序，以 GitHub 上 `main` 的最新版為準）

1. `CLAUDE.md` 與 `CONTRIBUTING.md`：協作規則。
2. `QUEUE_ALERTS.md`：有沒有待處理的佇列警報。
3. `WORK_BOARD.md`（進行中／尚未進行）與 `WORK_BOARD_DONE.md`（已完成）：
   目前的待辦與優先序。
4. `LIMITATIONS.md`：全專案已知限制，最重要的一份。推翻舊說法時要同時
   回頭撤回原處的標記，不能只在新處補一筆。
5. `PAPER_OUTLINE.md`：論文範圍、誤差預算表、全專案結果審查表。審查表
   標「未查」的列是待辦，不代表沒問題。
6. 需要方法論背景時：`docs/teaching/教學_*.md` 與
   `docs/reports/報告_完整說明.md`。

## 工作方式

- 先確定方法沒有邏輯問題，再產出最終數據；不為了交出數字繞過問題。
- 計算不在本機跑：新工作排進雲端佇列（`cloud_queue.py`、Kaggle 多帳號），
  流程見 `CONTRIBUTING.md` 與 `docs/reference/CLOUD_WORKERS.md`。
- 搜尋範圍撞牆時，先查底層資料（isochrone 網格）實際涵蓋到哪，再決定
  要放寬搜尋軸還是重下網格——兩者是不同的問題、不同的修法。
- 每次改動都回報做了什麼、為什麼。算出新結果就主動同步
  `PAPER_OUTLINE.md`、`LIMITATIONS.md`、`results/RESULTS_LOG.md`，
  並 commit、push，不必等我要求。
- 可量化的問題先算出數字再下結論。抽查要說清楚查了什麼、沒查什麼，
  不要用兩筆樣本推廣到全部。
