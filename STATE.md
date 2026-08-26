# 專案現況與交接

這份文件只放「現在能長期沿用」的環境備忘與交接 checklist，不放特定
時間點的進度快照——**進度請讀 `WORK_BOARD.md`（待辦）、
`WORK_BOARD_DONE.md`（已完成）、`LIMITATIONS.md`（已知限制）、
`results/RESULTS_LOG.md`（每次新結果）**。這份文件較舊版本記錄過某次
機器交接（2026-08-13～15）的完整過程，該內容已因後續進度而過期，見
[CHANGELOG.md](CHANGELOG.md)；需要回顧當時細節請直接看 git 歷史。

## 換機器／換協作者的 checklist

以下這些東西不進版控（`.gitignore` 排除），`git pull` 不會帶過去，
換機器前要自己決定要不要手動搬：

1. **`kaggle_accounts.json`**（repo 根目錄，gitignored）：Kaggle 帳號
   的 token。**不要把這個檔案的內容貼進對話或 commit 進 git**——要
   繼續派 Kaggle 工，用安全的方式（USB、密碼管理器等）手動搬過去，
   或用同一組 token 重新建立這個檔案。
2. **`isochrones/` 底下的等時線網格檔案**（不進版控，體積大）：本機
   Kaggle／雲端派工需要打包上傳，新機器第一次跑派工前要確認這些
   檔案存在（沒有的話 `kaggle_sync.py`／`cloud_queue.py` 會告訴你
   怎麼補）。
3. **本機 git worktree**（只在該機器磁碟上，新機器不會有）：需要的話
   用 `git worktree add ../<新目錄> <分支>` 重新建立，不用複製。
4. **`.venv_limepy/`**（LIMEPY 專用，釘 `scipy==1.16.3`）與 `nbody/`
   （N-body 外部工作目錄，在 repo 外面）：只有要跑 LIMEPY／N-body
   才需要，重新建置步驟見 `docs/planning/PDMF_TO_IMF_PLAN.md` 第七節。
5. **開新機器／新協作者的第一步**：`git clone` 或 `git pull`，讀
   `WORK_BOARD.md` 確認目前誰在做什麼，讀 `LIMITATIONS.md` 確認已知
   限制，再讀 `results/RESULTS_LOG.md` 最新幾行確認最新結果。
6. 這個 checkout 若還有其他 session／機器未 commit 的修改，先確認
   有沒有人要 commit，不要用 `git checkout --` 之類的指令清掉，除非
   確定那是可以丟的。

## 工作方式要求

完整規則見 `CONTRIBUTING.md`，這裡只列容易忘記的：

- 先確定方法沒有邏輯問題，再產出最終數據，不要為了交出數字繞過問題。
- 每次改動都要開分支 `<身分>/<主題>`，走 PR。
- 每次算出新結果都要主動同步寫進 `results/RESULTS_LOG.md`／
  `LIMITATIONS.md`／`WORK_BOARD.md`，不必等使用者要求。
- 發現任何跟自己無關、正在被其他 session 動的檔案，不要碰，回報就好。
- 舊結論被推翻時，用附加寫入標記「已作廢，見下一行修正」，不要直接
  覆寫或刪除舊的行。
- 多台機器/多個帳號同時派工時，動手前先用 API／CLI 查即時狀態
  （`kernels_status()`／`kernels_output()`），不要只看本機的
  `logs/kaggle_queue_done.txt`。

## 檔案地圖

**必讀**
- `WORK_BOARD.md` / `WORK_BOARD_DONE.md` —— 誰在做什麼、已經完成了什麼
- `LIMITATIONS.md` —— 全部已知限制，A/B/C/D 嚴重度分類
- `docs/planning/PDMF_TO_IMF_PLAN.md` —— PDMF→IMF 主線完整規劃與第七節
  環境建置記錄（LIMEPY／N-body 在 Windows 上的坑都記在這裡）
- `results/RESULTS_LOG.md` —— 每個結果檔案的索引與一句話結論
- `docs/reference/KAGGLE_DIAGNOSIS.md` —— Kaggle 掛載路徑 bug／`results/` 目錄 bug／
  headline 在 Kaggle 上跑不完等基礎設施問題的專門紀錄

**背景**
- `PAPER_OUTLINE.md` —— 論文範圍凍結文件、誤差預算表
- `docs/teaching/` —— 給高中生程度的完整方法論教學
- `README.md` —— 環境建置、每個參數的作用

## 環境備忘（別重新診斷）

- ARM64 原生 Python 在 `%LOCALAPPDATA%\Python\pythoncore-3.14-arm64\python.exe`，
  astropy 裝不起來，已用 `pipeline/table_compat.py` 取代。
- x64 機器 Python 3.14，`astro-limepy` 需要獨立 venv 釘 `scipy==1.16.3`
  （`.venv_limepy/`，不進版控，見 `PDMF_TO_IMF_PLAN.md` 第七節）。
- pyUPMASK 仍需 x64。
- 長時間任務用脫離式背景執行，重導向路徑要用絕對路徑。
- Kaggle 免費 CPU-only notebook：4 顆虛擬核心（`--procs 4`）、session
  上限約 9–12 小時，重設定（如 `--repeats 10 --refines 3,3,3`）單一
  kernel 跑不完，要用 `--repeat-offset` 拆給多個 kernel。
- 新機器架構不確定是 x64 還是 ARM64 時，先跑一次 `README.md` 的環境
  建置章節確認 astropy／pyUPMASK 能不能裝，不要假設跟舊機器一樣。
