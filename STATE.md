# 專案現況與交接

**下一輪對話請先讀這份，再依需要讀 `WORK_BOARD.md`（逐日詳細紀錄）、
`LIMITATIONS.md`（已知限制）、`docs/planning/PDMF_TO_IMF_PLAN.md`（目前
主線的完整規劃）。這份文件只給「現在是什麼狀態、接下來能做什麼」，細節
一律去讀上面三份，不要只憑這裡的摘要動手。**

最後更新：2026-08-15（x64 協作機，Yu Tung Lan，**交接給新機器 Acer AI 16**）

> ## ⚠ 2026-08-21 覆查：這份文件已經過期，下面的「現況」不是現況
>
> 這份是 **2026-08-15 的交接快照**，但標題與行文都寫成「現況」，容易被
> 當成最新狀態。2026-08-21 逐項核對後，至少下列三點已經不成立：
>
> | 這份文件說 | 實際狀況（2026-08-21） |
> |---|---|
> | headline `p2_final2` 卡在重跑一半 | **已定案**：`p2_final2_v3` 10/10 次重複，**α = 2.382 ± 0.068**（2026-08-20），A1／A2 對 headline 已解除 |
> | PR #57（`claude/headline-partial-reps`）還沒合併 | **已於 2026-08-15T17:38Z 合併** |
> | 第 2 步只有 `_prelim` 值 | 正式統計版 r1（2.0644 ± 0.1193）與 r3（2.4244 ± 0.0924）已完成；r2 本機跑中、rall 未開始 |
>
> **要看現況請改讀**：`LIMITATIONS.md`（A1／A5 的進度標記已更新到
> 2026-08-21）、`results/RESULTS_LOG.md`（每次新結果都有一行）、
> `WORK_BOARD.md`（誰在做什麼）。這份保留不刪，是因為它記錄了當時的
> 交接脈絡與 Kaggle 派工的排查過程，那些內容仍然有參考價值。

---

## 一句話現況

五步 pipeline 早就跑通。`p2_final2` 前向模型頭條數字目前**卡在重跑一半**：
精修 bug／金屬量先驗修好後的乾淨版本（`p2_final2_v3`）10 次重複裡，5 次
已經在 Kaggle 端跑完並拉回保存（[PR #57](https://github.com/helmet-png/m45-imf-analysis/pull/57)，
`α` 暫時平均 2.379），但**還沒有最終合併檔案，不可引用**。跟表 4 穩健性
相關的 P9a-redo v2／P9c v2 已經定案（見下方 A4）。PDMF→IMF 主線
（`docs/planning/PDMF_TO_IMF_PLAN.md`）仍是專案重心，**2026-08-19
更新：第 2 步（`radial_r1/r2/r3/rall`）四項 `_prelim` 值都已到齊**
（r1=2.10、r2=2.43、r3=2.50、rall=2.43，r1→r3 上升後 rall 又降，
非單調，還不知道是不是雜訊），但這些都是單次無誤差棒的初步值，
統計上穩健的正式版（`--repeats 5 --refines 3,3`）仍待認領，見
`WORK_BOARD.md` 的 `radial_final_reruns`。

---

## PDMF → IMF 五步進度（完整規劃見 `PDMF_TO_IMF_PLAN.md` 第五節）

| 步驟 | 狀態 | 備註 |
|---|---|---|
| 第 1 步：文獻基準線（Li+2026） | **完成** | Δα=0.076（文獻公式代入值） |
| 第 2 步：前向模型逐半徑重跑 α(<r) | **2026-08-19 更新：四項 `_prelim` 值都已到齊**（r1=2.10、r2=2.43、r3=2.50、rall=2.43，非單調待確認），仍不是最終數字 | 正式 `--repeats 5 --refines 3,3` 重跑見 `WORK_BOARD.md` 的 `radial_final_reruns`，明確不排本機 |
| 第 3 步：LIMEPY 多質量平衡模型 | **模型完成並合併**（PR #41），2026-08-19 起可用 `_prelim` 值做探索性交叉驗證（`limepy_radial_crosscheck`），正式驗收仍待 `_final` | King 模型 reduced χ²=0.75，潮汐半徑外估計還有 14.4 M☉（3.2%） |
| 第 4 步：放大搜尋半徑到 8–17° | 2026-08-19 更新：`_prelim` 只能支援探索性判讀（梯度方向看起來還沒收斂），不能支援正式投入決策 | 正式投入決策與驗收要等 `radial_final_reruns` 的有誤差棒 `_final` 結果 |
| 第 5 步：N-body（Converse & Stahler 2010） | 探索性 pilot 已完成，方向與觀測質量分層一致（但比較用的分箱定義不一致，見 `WORK_BOARD.md`），非正式結果 | `_prelim` 只能支援探索性初步校準方向（`nbody_prior_from_radial`），正式 N-body 校準要等 `radial_final_reruns` 的 `_final` 結果 |

---

## 這次（x64，2026-08-13～15）做的事總覽

### 1. Kaggle 多帳號派工：headline 重跑卡了兩天，剛發現有進度沒人拉

- 帳號池目前有 7 個（見下方「Kaggle 帳號」一節），`kaggle_accounts.json`
  **本機檔案、gitignored，不會跟著 git pull 過去新機器**。
- `p9a_redo_v2`／`p9c_redo_v2`（表 4 穩健性檢驗）**已經定案**：兩者一起
  確認「跨 isochrone 年齡穩健性」主張不成立（PARSEC 108.0 Myr vs MIST
  54.1 Myr，α 差 1.9 倍合併標準誤），見 `LIMITATIONS.md` A4。
- headline `p2_final2_v3`（`--repeats 10 --refines 3,3,3`）單一 kernel
  在 Kaggle 免費 session 上限內跑不完（`p2-final2-v3-fixed` 跑 11.4 小時
  只完成 1/10 次重複就被系統取消）。**PR #55**（`claude/fit-real-repeat-offset`，
  **還沒合併**）加了 `--repeat-offset` 旗標，可以把 `--repeats N` 拆到多台
  機器/帳號，各跑一部分、用不同種子，結果串接起來等於一次跑完。
- **2026-08-15 發現**：有人（可能是同學的 session）已經用這個未合併的
  分支把 headline 拆成 5 個 kernel（`p2-final2-v3-rep0`～`rep4`，各
  `--repeat-offset 0,1,2,3,4`），派給 5 個帳號，**Kaggle 端全部
  COMPLETE**，但沒人拉回來合併，本機也完全沒有這些檔案（一查才發現，
  不是猜的——直接用 Kaggle API `kernels_status()`／`kernels_output()`
  查證）。已經拉回來存進 **PR #57**（`claude/headline-partial-reps`），
  避免 kernel 過期後資料遺失。**還差 `--repeat-offset 5,6,7,8,9` 這 5 次
  重複才是完整的 10 次**，10 個 `rep*.npz` 的 `C` 陣列沿 axis=0 串接
  存成 `results/fit_real_p2final_v3.npz` 才是正式 headline 數字。
- `p6b_inject_lowmass_v2`、`verify_bprperr_off_v2`、`verify_bprperr_on_v2`
  三項**都還是失敗狀態**（`CANCEL_ACKNOWLEDGED`），沒人成功重推過。

### 2. N-body pilot、LIMEPY 第 3 步

都已完成並合併（見 `WORK_BOARD.md` 2026-08-13 相關行），這裡不重複。
N-body 需要 x64 機器（PeTar/mcluster 編譯環境），**新機器如果不是 x64，
這條路線的後續模擬要另外處理**；LIMEPY 純 Python，架構無關。

### 3. A6（白矮星/RV 污染排除）、C3/C18/C20/D9 等 B/C/D 類補齊

全部完成，見 `LIMITATIONS.md` 對應條目與 `WORK_BOARD.md` 2026-08-13 那
一批紀錄，不重複列。

### 4. 根目錄腳本整理

`PR #56` 已合併，散落的 `check_*.py`／`build_*_grid.py` 分類進
`scripts/diagnostics/`／`scripts/data_prep/`。刻意沒動 `fit_real.py`
系列、`kaggle_*.py`、`run_queue.py`／`queue.txt`（原因見 PR body）。

---

## 目前開著、還沒處理的 PR

| # | 標題 | 狀態 |
|---|---|---|
| [#57](https://github.com/helmet-png/m45-imf-analysis/pull/57) | 拉回 headline p2_final2_v3 已完成的 5/10 次 Kaggle 重複結果 | 這次新開，等 review／合併 |
| [#55](https://github.com/helmet-png/m45-imf-analysis/pull/55) | `fit_real.py` 加 `--repeat-offset` | 還沒合併，但**已經被拿去用在上面的 headline 拆分派工**——合併前分支上的 code 仍可直接用（worktree `../m45-imf-offset-wt` 已經 checkout 這個分支） |
| [#54](https://github.com/helmet-png/m45-imf-analysis/pull/54) | D5 補測 + C5 核心程式碼（extinction_form_test） | 待 review |
| [#45](https://github.com/helmet-png/m45-imf-analysis/pull/45) | [Codex] PDMF-to-IMF LIMEPY / N-body 驗證 | 待 review，跟這裡的 LIMEPY／N-body 工作可能有重疊，合併前先比對 |
| [#11](https://github.com/helmet-png/m45-imf-analysis/pull/11) | 驗證 NGC 3532 與 Praesepe 多星團通用性 | 開很久了，待 review |

---

## 待辦（依優先序）

1. **完成 headline `p2_final2_v3`**：用 `--repeat-offset 5,6,7,8,9` 補滿
   剩下 5 次重複，跟 PR #57 已拉回的 5 次合併，正式更新
   `RESULTS_LOG.md`／`LIMITATIONS.md` A1／A2。
2. **`radial_final_reruns`**：四項 `_prelim`（r1/r2/r3/rall）已於
   2026-08-19 前完成，待補的是 `--repeats 5 --refines 3,3` 的四項
   正式重跑，見 `WORK_BOARD.md`。
3. 決定 PR #55 要不要合併（現在是「分支上能用但沒進 main」的尷尬狀態，
   建議先合併，headline 拆分派工才有正式依據）。
4. 4 個開著的 PR 找時間 review／合併（見上表）。
5. `p6b_inject_lowmass_v2`／`verify_bprperr_v2` 兩項失敗的 Kaggle 派工，
   要不要重推、還是移回本機佇列，跟 headline 一樣的判斷（單次 kernel
   會不會超過 Kaggle 免費 session 上限）。
6. 其餘不衝突的待認領工作見 `WORK_BOARD.md`「待認領工作：B/C/D 類補齊」表。

---

## 交接到新機器（Acer AI 16）的具體 checklist

**這台 x64 機器上有些東西是本機專屬、`.gitignore` 排除、`git pull` 不會
帶過去的，換機器前要自己決定要不要手動搬：**

1. **`kaggle_accounts.json`**（repo 根目錄，gitignored）：7 個 Kaggle 帳號
   的 token（`justinlan11`／`teammate2`／`helmetalbert`／`account4`～`7`）。
   **不要把這個檔案的內容貼進對話或 commit 進 git**——如果新機器要繼續
   派 Kaggle 工，用安全的方式（USB、密碼管理器等）手動搬過去，或者
   用同一組 token 重新建立這個檔案。`account4`（`thepisnotsure`）先前
   两次 smoke test 都 280 秒逾時失敗，不建議繼續用。
2. **`isochrones/` 底下兩個網格檔案**（不進版控，體積大）：
   `parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat`、
   `mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat`——本機 Kaggle 派工需要
   打包上傳，新機器第一次跑 Kaggle 派工前要確認這兩個檔案存在（沒有的話
   `kaggle_sync.py` 應該會告訴你怎麼補）。
3. **本機 git worktree**（只在這台機器的磁碟上，新機器不會有）：
   - `../m45-imf-offset-wt`（`claude/fit-real-repeat-offset`，PR #55）
   - `../m45-imf-headline-wt`（`claude/kaggle-headline-infeasible`，已合併，可以直接刪）
   - 新機器要做同樣的事，用 `git worktree add ../<新目錄> <分支>` 重新建立即可，不用複製。
4. **`.venv_limepy/`**（LIMEPY 專用，釘 `scipy==1.16.3`）與 `nbody/`（N-body
   外部工作目錄，在 repo 外面）：新機器要跑 LIMEPY／N-body 才需要，重新
   建置步驟見 `docs/planning/PDMF_TO_IMF_PLAN.md` 第七節，不用複製整個
   目錄。
5. **這次 session 對主 checkout（`m45-imf-analysis/`）留下的雜項**：
   `dispatch_new_accounts_tmp.py`、`resume_kaggle_watch_tmp.py`（暫時性
   監控腳本，非 repo 正式檔案）、`m45-imf-run-p2-final2-v3-rep0.log`、
   `results/fit_real_p2final_v3_rep0.npz`～`rep4.npz`（已經進 PR #57，
   本機這幾份是多的，新機器 `git pull` 合併 PR #57 後就有了，這幾個
   本機檔案不用特別搬）。**這個 checkout 目前還有其他 session／機器
   未 commit 的修改**（`fit_real.py`、`pipeline/joint_fit.py`、
   `injection_recovery.py`、`kaggle_queue.txt`——本 session 沒有動它們，
   不確定是誰的，換機器前建議先確認這些改動有沒有人要 commit，不要用
   `git checkout --` 之類的指令清掉，除非你確定那是可以丟的）。
6. **開新機器的第一步**：`git clone` 或 `git pull`，讀這份 `STATE.md`，
   確認 PR #57／#55 有沒有被合併（若已合併，這份文件的「還差 5 次重複」
   可能已經有人接手做完，先看 `RESULTS_LOG.md` 最新幾行再決定要不要重做）。

---

## 工作方式要求（沿用不變）

- 先確定方法沒有邏輯問題，再產出最終數據，不要為了交出數字繞過問題。
- 每次改動都要開分支 `<身分>/<主題>`，走 PR，等 CodeRabbit review 過再合併。
- 每次算出新結果都要主動同步寫進 `results/RESULTS_LOG.md`／
  `LIMITATIONS.md`／`WORK_BOARD.md`，不必等使用者要求。
- 發現任何跟自己無關、正在被其他 session 動的檔案（未提交的修改、
  暫存檔），不要碰，也不用花時間猜是誰改的，回報就好。
- 舊結論被推翻時，用附加寫入標記「已作廢，見下一行修正」，不要直接
  覆寫或刪除舊的行——見 `results/RESULTS_LOG.md`／`WORK_BOARD.md` 的
  既有寫法。
- **多台機器/多個帳號同時派工時，動手前先用 API／CLI 查即時狀態**
  （`kernels_status()`／`kernels_output()`），不要只看本機的
  `logs/kaggle_queue_done.txt`——這次就是本機紀錄檔過期，導致 5 個已經
  跑完的 kernel 放了一天多沒人拉回來。

---

## 檔案地圖

**必讀（比這份新）**
- `WORK_BOARD.md` —— 逐日詳細紀錄與待認領工作清單，這份文件的完整版
- `LIMITATIONS.md` —— 全部已知限制，A/B/C/D 嚴重度分類
- `docs/planning/PDMF_TO_IMF_PLAN.md` —— PDMF→IMF 主線完整規劃與第七節
  環境建置記錄（LIMEPY／N-body 在 Windows 上的坑都記在這裡）
- `results/RESULTS_LOG.md` —— 每個結果檔案的索引與一句話結論
- `KAGGLE_DIAGNOSIS.md` —— Kaggle 掛載路徑 bug／`results/` 目錄 bug／
  headline 在 Kaggle 上跑不完等基礎設施問題的專門紀錄

**背景（較舊，仍有效但已不是專案重心）**
- `PAPER_OUTLINE.md` —— 論文範圍凍結文件、誤差預算表
- `docs/teaching/` —— 給高中生程度的完整方法論教學（含 PDMF→IMF 教學文件）
- `README.md` —— 環境建置、每個參數的作用

---

## 環境備忘（別重新診斷）

- ARM64 原生 Python 在 `%LOCALAPPDATA%\Python\pythoncore-3.14-arm64\python.exe`，
  astropy 裝不起來，已用 `pipeline/table_compat.py` 取代。
- x64 機器 Python 3.14，`astro-limepy` 需要獨立 venv 釘 `scipy==1.16.3`
  （`.venv_limepy/`，不進版控，見 `PDMF_TO_IMF_PLAN.md` 第七節）。
- pyUPMASK 仍需 x64。
- 長時間任務用脫離式背景執行，重導向路徑要用絕對路徑。
- Kaggle 免費 CPU-only notebook：4 顆虛擬核心（`--procs 4`，不是本機的
  8 核）、session 上限約 9–12 小時，`--repeats 10 --refines 3,3,3` 這種
  重設定單一 kernel 跑不完，要用 `--repeat-offset` 拆。
- 新機器如果架構跟這台不同（不確定 Acer AI 16 是 x64 還是 ARM64），
  先跑一次 `README.md` 的環境建置章節確認 astropy／pyUPMASK 能不能裝，
  不要假設跟這台一樣。
