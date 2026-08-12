# 工作認領表（誰現在在做什麼）

`CONTRIBUTING.md` 管「怎麼合併」，這份管**「開始做之前先看這裡，避免兩個人／
兩個 agent 同時做同一件事」**。跟 `results/RESULTS_LOG.md` 一樣設計成
**只附加、不改舊行**的格式——多人同時寫幾乎不會撞行，不需要鎖檔案。

## 規則

1. **開始任何預期要花超過一次對話（或會碰共用檔案：`pipeline/`、
   `injection_recovery.py`、`LIMITATIONS.md`、`PAPER_OUTLINE.md`、
   `queue.txt`）的工作之前**，先讀完下面的表格，確認沒有人已經在做
   同一件事或高度重疊的事。
2. 開始工作時，在表格**尾端加一行**，狀態填「進行中」。做完、暫停、
   或放棄時，**再加一行新的**（同任務名稱、狀態改掉），不要回頭改舊行——
   要查某任務目前狀態，從下往上找同名任務最新的一行。
3. **看不出算不算重複、範圍該怎麼分**——不要用猜的、也不要因為怕
   衝突就不寫：直接在表格加一行「疑義」狀態並寫清楚困惑點，讓開這個
   任務的人或使用者看到後決定怎麼分工。這比「先做了再說」風險小。
4. 誰都可以編輯這份文件（人類協作者、Claude、Codex、其他 agent）。

## 欄位

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|

## 紀錄

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|
| 2026-08-11 13:35 | Claude session（本機） | 多星團 Tier1：NGC 3532／Praesepe 起頭 | 暫停（卡住） | `cluster_imf_tier1.py`、`data/hr23_*`，commit `4fd8c67` | 已抓 HR23 成員表並存檔，PARSEC 等時線服務（stev.oapd.inaf.it）連續 6 次 SSL 交握斷線，卡在這裡；`LIMITATIONS.md` 已記錄，含之後要重跑的指令 |
| 2026-08-11 19:31–20:14 | Codex | 多星團通用性驗證：NGC 3532／Praesepe（Tier1 傳統法 + Tier2 前向模型全套） | 完成，PR #11（draft，待審） | `cluster_imf_tier1.py`（延伸）、新增 `prepare_cluster_tier2.py`、`cluster_forward_validation.py`、`MULTICLUSTER_VALIDATION.md`，分支 `codex/ngc3532-praesepe-generalization` | **接續上一行**、不是獨立重做——用本機已快取的等時線網格繞過 PARSEC 卡點（沒有重新呼叫 PARSEC 服務），把 Tier1 沒做完的補完，還加了 Tier2（Gaia crossmatch＋誤差模型＋選擇函數＋完整 JointModel 前向模型）。這條在 PR 審查通過前先標記，之後補結論 |
| 2026-08-12 | Claude session（本機） | 建立本工作認領表，回填上面兩筆已知的重疊/接續紀錄 | 完成 | `WORK_BOARD.md`（新檔） | 起因：使用者發現 Codex 的 PR #11 跟自己稍早的多星團工作動到同一個檔案，追問是否重複；查證後確認是接續而非重工，見上兩行 |
| 2026-08-12 | Claude session（本機，交接給另一台電腦的 agent） | Kaggle dataset 掛載問題根因排查（見 `LIMITATIONS.md`「Kaggle 掛載問題根因排查」一節） | 交接中，等另一台機器用不同帳號接手 | `LIMITATIONS.md`、`kaggle_queue.txt`、`kaggle_sync.py`（已加 in-kernel 等待，不用再改）、`kaggle_accounts.json`（不進版控，新 agent 要自己建） | 本機已排除「純時序」「帳號未驗證」兩個假設；使用者實測發現 Kaggle 網頁版 Notebook Editor 本身卡在「Editor loading」，換瀏覽器/無痕都無效，懷疑是 Kaggle 平台（可能是 Firebase 服務）暫時異常，不是帳號或我們程式的問題，但這個假設也還沒證實。**交接給另一台電腦、用另一個 Kaggle 帳號**測試是為了排除「同一帳號被限制」這個殘餘可能性，兩台機器同時測也能交叉驗證是不是平台性問題。新 agent 開始前**先讀 `LIMITATIONS.md` 那一節的完整診斷過程**，不要重新從頭排查已經排除的假設 |
| 2026-08-12 | Claude session（新機器，x64，接手交接） | Kaggle dataset 掛載問題根因排查（接續上一行） | 進行中，卡在第 2 點需要真人登入操作 | `LIMITATIONS.md`（已補「2026-08-12（新機器接手交接...）」段落）、`kaggle_accounts.json`（本機新增 `justinlan11` 帳號，不進版控） | 匿名瀏覽器測試部分排除第 1 點（平台前端目前渲染正常，但只測到唯讀頁面）；使用者提供第三個帳號 `justinlan11`（API token），用它重跑 `kaggle_smoketest.py`，**撞到跟 helmetalbert／teammate2 一模一樣的錯誤**（`FileNotFoundError: waited 280s...`），且已核對本機產生的 `dataset-metadata.json`／`kernel-metadata.json` 設定正確，排除「我們自己設定寫錯」。三個獨立帳號都一樣，帳號層級限制的可能性進一步降低。**唯一還沒排除、下一步該做的是第 2 點**（網頁手動 Add Input 測試），需要真人登入操作，AI agent 做不到，回報使用者需要親自測試或提供登入方式 |
| 2026-08-12 | Claude session（新機器，x64） | Kaggle dataset 掛載問題根因排查（接續上兩行，**找到真正根因並修好**） | **完成** | `kaggle_sync.py`（`make_kernel()` 的 `base` 路徑修正）、`LIMITATIONS.md`（新增「2026-08-12：真正的根因找到了」一節，回頭訂正「平台異常」「帳號限制」兩個假設） | 使用者親自登入無痕視窗，手動網頁上傳 dataset＋Add Input＋`os.walk('/kaggle/input')`，印出真實路徑是 `/kaggle/input/datasets/<帳號>/<slug>/`，比 `kaggle_sync.py` 原本寫死的 `/kaggle/input/<slug>/` 多兩層。改一行路徑字串，用 `justinlan11` 帳號重跑驗證：修好前等滿 280 秒才 `ERROR`，修好後 **10.7 秒 `COMPLETE`**。純粹是我們自己的路徑 bug，不是 Kaggle 平台問題也不是帳號限制，這兩個假設已在 `LIMITATIONS.md` 回頭訂正。過程中發現的「頁面崩潰了」React 錯誤是使用者瀏覽器擴充功能干擾，跟這個 bug 無關，已在文件中記錄避免以後誤判成同一件事。`kaggle_queue.txt` 現在可以考慮恢復派工，留給使用者/負責的 session 決定 |

## 待認領工作（2026-08-12，`multi_stage_best()` 精修 bug 修好後還沒排的重跑）

背景：`injection_recovery.py` 的 `multi_stage_best()` 曾有精修 bug（見
`LIMITATIONS.md`「`multi_stage_best()` 精修 bug」一節），已修好。受影響
結果裡優先度最高的兩個（`p6_lowmass_v2`、`p11_outlierfrac_v2`）已經在
本機佇列排隊（見下一節），**以下是還沒被任何人排進佇列、任何人／任何
機器都可以認領的重跑**——認領時在上面「紀錄」表加一行，跑完把結果
commit 進 `results/`、`results/RESULTS_LOG.md` 記一行、開 PR。

| 優先度 | 任務 | 指令 | 為什麼 |
|---|---|---|---|
| **高** | `p2_final2` 重跑（headline 數字！） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --refines 3,3,3 --tag _p2final_v3` | 目前引用的 headline α=2.387±0.060 是在 bug 修好**之前**跑的，精修只做到原意的一半（`--refines 3,3` 在舊 bug 下只等於一階真精修）。這是整個專案最重要的數字，應該最先重跑確認 |
| 中 | P9a-redo v2（MH 鎖定检验，PARSEC） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --tag _fixmh_parsec_redo_v2 --refines 3,3` | 舊結果 α=2.440±0.180 完全沒精修（純粗網格 argmax）。這是表 4 穩健性主張的一半，另一半是下面 P9c |
| 中 | P9c v2（MH 鎖定检验，MIST） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --grid mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat --tag _fixmh_mist_redo_v2 --refines 3,3` | 舊結果 α=2.180±0.098 同樣完全沒精修 |
| 中 | P6b v2（低質量段冪次可辨識性） | `python inject_lowmass.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3` | 舊結果（ratio 0.92）完全沒精修；這個數字決定要不要把低質量段冪次升格成自由參數（`p2_free_lowmass` 已經在跑了，但可辨識性本身的精確度也該補） |
| 低 | `verify_bprperr_off`／`on` 值得懷疑就重跑一次確認 | （同 `queue.txt` 裡的參數，加 `--refines 3,3`） | 這兩個已經在 bug 修好**之後**才跑的（時間戳對得上），大機率沒事，但因為背景長跑程序曾經在其他項目上遇過「模組被即時修改」的競態，還沒 100% 排除，列在這裡給有餘力的人做確認，不急 |

**另外**：PR #11（多星團驗證）已經留言列出 4 個正確性問題（貼牆偵測
被關掉、選擇函數驗證漏掉紅藍分色檢查等），見
<https://github.com/helmet-png/m45-imf-analysis/pull/11#issuecomment-5264701703>——
這也是待認領工作，適合 PR 作者（Codex）或任何人接手修。

## 目前已知的固定分工（不用每次都查表）

- **本機 8 核運算佇列**（`queue.txt` / `run_queue.py`，Windows ARM64 這台機器）
  只有這台機器能跑，其他人／agent 不會撞到，不需要在此認領。目前跑到
  `verify_bprperr_off`，後面排 `verify_bprperr_on`、`p2_free_lowmass`、
  `p6_lowmass_v2`、`p11_outlierfrac_v2`。
- 若要在別的機器（Kaggle、同學的電腦、Codex 的環境）重跑本機佇列裡
  同一個腳本、同一組參數，**先在這裡加一行認領**，避免兩邊各自跑一次
  浪費算力、之後也不知道該採哪一份結果。

## 紀錄（續）

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步（fetch_gaia → prep → pyUPMASK 第1步 → 第2–5步），跟既有 `results/baseline.dat` 與文件記錄的頭條數字比對，不是新的科學結果 | 進行中 | 先跑到獨立檔名（不直接覆寫 `results/baseline.dat`）比對，一致才決定要不要正式取代；分支 `yutunglan/x64-pipeline-verify` | 這台是 x64（非 ARM64），跟本機 8 核佇列那台不是同一台，不會搶 `queue.txt`。環境建置與 `fetch_gaia.py` 可攜性 bug 已在 PR #15 修好並合併。跟這台機器上同時在跑的 Kaggle 掛載排查（見上面那行）沒有檔案重疊，只是提醒：這台電腦目前有多個 session 同時操作同一個 working directory，git 分支切換偶爾會互相干擾，commit 前務必先確認當下分支 |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步 | **完成，數字與既有結果一致，未覆寫任何 tracked 結果檔** | 無（`data/`、`results/` 的重跑輸出已 `git checkout --` 復原成 repo 原版） | 逐星比對：兩次跑（同 `random_seed=42`）的 6,956 顆星星集合完全相同，`probs_final` 相關係數 0.9992，P≥0.7 成員數 1,298 vs repo 記錄的 1,297（差 1 顆，落在專案自己記錄的「同種子仍有殘餘隨機性」量級內，pyUPMASK 平行處理沒有被單一種子完全鎖死）。第 2–5 步頭條數字：f_bin=0.45（一致）、四法標記 415/100/58/24（vs 414/100/58/24）、alpha_naive=1.978±0.069（vs 1.980±0.069）、alpha_forward=2.350（一致）、質量分層 α(r) 1.77/2.02/2.12/2.31（vs 1.77/2.01/2.15/2.29）。**結論：pipeline 在獨立的 x64 機器上完全可攜、可重現**，順便在 `prep.py` 修了跟 PR #15 同一種寫死 `gaia-export` 路徑的 bug（`fetch_gaia.py` 那次漏改了這支）。沒有覆寫任何 `results/` 或 `data/` tracked 檔案，這次驗證不影響任何既有結論或數字，所以沒有加 `RESULTS_LOG.md` 條目 |
| 2026-08-12 | Claude session（本機，ARM64 8核） | **PDMF → IMF 這條線**：方法調查、動力學年齡計算、α(r) 梯度實驗、四路線規劃 | 第 1、2 步進行中（第 3–5 步開放認領） | 新增 `PDMF_TO_IMF_PLAN.md`；`fit_real.py` 加 `--radius-range`；`queue.txt` 加 4 個 radial 診斷；分支 `claude/pdmf-to-imf` | 使用者確認「IMF 本來就是專案目標」、四條路線都要做、照合理順序來。**完整計畫與文獻調查見 `PDMF_TO_IMF_PLAN.md`**。關鍵發現：核心-外圍 α 差 0.515，是統計誤差 0.144 的 3.6 倍、比最大系統誤差 0.248 還大，但可能有一部分是雙星比例隨半徑變化的假象（Torres+2025），第 2 步的 radial_r1/r2/r3/rall 就是要分辨這件事。**第 3 步（LIMEPY 多質量平衡模型，純 Python、ARM64 無痛）跟第 5 步（N-body，需要 x64 機器編譯）都還沒人做，跟本機佇列不衝突，歡迎認領** |
