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
| **高** | `p2_final2` 重跑（headline 數字！） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --refines 3,3,3 --tag _p2final_v3` | 目前引用的 headline α=2.387±0.060 疊了兩個問題：(1) 精修只做到原意的一半（`--refines 3,3` 在舊 bug 下只等於一階真精修）；(2) 用均勻先驗而非 config 宣告的高斯金屬量先驗（P10，見 `LIMITATIONS.md`）。**兩個問題的程式碼都已於 2026-08-12 修好**，這行指令跑起來會自動套用兩邊的修正（不用額外加旗標），一次重跑同時解決兩個問題，不用分兩次 |
| 中 | P9a-redo v2（MH 鎖定检验，PARSEC） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --tag _fixmh_parsec_redo_v2 --refines 3,3` | 舊結果 α=2.440±0.180 完全沒精修（純粗網格 argmax）。這是表 4 穩健性主張的一半，另一半是下面 P9c |
| 中 | P9c v2（MH 鎖定检验，MIST） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --grid mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat --tag _fixmh_mist_redo_v2 --refines 3,3` | 舊結果 α=2.180±0.098 同樣完全沒精修 |
| 中 | P6b v2（低質量段冪次可辨識性） | `python inject_lowmass.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3` | 舊結果（ratio 0.92）完全沒精修；這個數字決定要不要把低質量段冪次升格成自由參數（`p2_free_lowmass` 已經在跑了，但可辨識性本身的精確度也該補） |
| 低 | `verify_bprperr_off`／`on` 值得懷疑就重跑一次確認 | （同 `queue.txt` 裡的參數，加 `--refines 3,3`） | 這兩個已經在 bug 修好**之後**才跑的（時間戳對得上），大機率沒事，但因為背景長跑程序曾經在其他項目上遇過「模組被即時修改」的競態，還沒 100% 排除，列在這裡給有餘力的人做確認，不急 |

**另外**：PR #11（多星團驗證）已經留言列出 4 個正確性問題（貼牆偵測
被關掉、選擇函數驗證漏掉紅藍分色檢查等），見
<https://github.com/helmet-png/m45-imf-analysis/pull/11#issuecomment-5264701703>——
這也是待認領工作，適合 PR 作者（Codex）或任何人接手修。

## 待認領工作：PDMF → IMF（2026-08-12，見 `PDMF_TO_IMF_PLAN.md` 完整背景）

第 1、2 步（文獻基準線、前向模型徑向診斷）已在做，見上面的「紀錄」。
以下第 3–5 步都還沒人認領，且都跟本機佇列不衝突（第 5 步甚至需要
另一台 x64 機器，本機跑不了）。這三個不是「跑一行指令」等級的任務，
起手式跟驗收標準寫在下面，實際做法留給認領的人判斷。

**2026-08-12（新機器，x64，Yu Tung Lan）優先度覆核**：使用者要求把
PDMF→IMF 這條線的優先度調到非 A/B 類項目之前（見 `LIMITATIONS.md`
開頭的嚴重度分類）。查核範圍是 `queue.txt` 裡**全部**目前真正待跑的
項目（依檔案順序）：`verify_bprperr_on`（B1）、`p2_free_lowmass`
（對應 A3）、`radial_r1/r2/r3/rall`（對應 A5）、`p6_lowmass_v2`
（對應 A3）、`p11_outlierfrac_v2`（對應 B2）——**全部屬於 A 類或
B 類，沒有非 A/B 類項目排在中間，`queue.txt` 已經符合要求，不需要
調整順序**。以下加一欄「優先度」，把第 3、5 步標成「可立刻開始」
（不需要等第 2 步結果，只是環境準備／方法建置，跟第 2 步平行不
衝突），第 4 步維持「等第 2 步結果」：

| 步驟 | 任務 | 優先度 | 起手式 | 驗收標準 | 為什麼 |
|---|---|---|---|---|---|
| 第 3 步 | LIMEPY 多質量平衡模型，反推潮汐半徑外的質量函數 | **可立刻開始**（環境準備不用等第 2 步；ARM64 已知會壞，這台 x64 機器要先自己測一次，不能假設同樣的 scipy 版本問題） | 正確套件是 `pip install astro-limepy`（**不是** `pip install limepy`，那是同名的問卷調查工具，已踩過這個坑）。**已知環境問題（ARM64 機器上）**：scipy 1.17.1 會讓 `limepy.limepy()` 在 `scipy.integrate.ode`（舊版 API）爆掉，`nsteps=1e6` 改 `int(1e6)` 沒解決，需要在獨立 venv 釘舊版 scipy，或等上游改用 `solve_ivp`——先解決這個才能開始（這台 x64 機器的 scipy 版本不一定一樣，需要先測）。之後要準備逐質量段的徑向數密度剖面（不是現成的 `step5_mf_radial.csv`，那是 alpha 不是密度，需要自己從 `data/cmd_members.csv` 的 ra/dec/mass 重新分箱） | 擬合出的多質量模型能重現第 2 步 `radial_r1/r2/r3/rall` 量到的 α(<r)，且對潮汐半徑外的質量函數給出具體數字（不是只有結構參數） | 這是唯一不需要重抓資料就能估計「潮汐半徑外還有多少低質量星」的路線 |
| 第 4 步 | 放大搜尋半徑到 8–17°，重抓 Gaia、重跑成員判定與選擇函數 | **等第 2 步結果**（維持原判斷） | **先等第 2 步（radial 診斷）結果出來再決定要不要投入**——如果 α(<r) 在 r=5° 內已經收斂，這步的急迫性大幅下降。真的要做時起點是 `config.toml` 的 `radius_deg`，改大後整條 pipeline（`fetch_gaia.py` → `run_pipeline.py` 第 1–5 步）要重跑，pyUPMASK 在大半徑下的成員判定沒驗證過，選擇函數也要重建 | 新的 6,956→N 顆全樣本跑出 α，且大樣本下 pyUPMASK 的品質檢查（六格驗證圖）跟現有 5° 版本一樣通過 | 觀測上唯一能給出決定性答案的路線，但成本最高，所以排最後投入 |
| 第 5 步 | N-body 重建 M45 初始狀態（跟 Converse & Stahler 2010 同路線） | **編譯環境已就緒；正式模擬仍等第 2 步的觀測基準線** | **編譯與工具鏈已裝好並驗證（2026-08-12，x64，Yu Tung Lan）**——**不需要 WSL**，MSYS2/MinGW-w64（`winget install MSYS2.MSYS2` + `pacman` 裝工具鏈）就能編出完整 PeTar（含 BSE 恆星演化）+ mcluster，且已跑通 `mcluster_sse` → `petar.init` → `petar` 全鏈（100 顆星測試案例，含 25 組聯星，能量/角動量守恆誤差正常）。**這只代表「能不能編譯、能不能跑」的問題解決了，不代表可以直接開始正式模擬**——正式模擬的初始條件要對照第 2 步（`radial_r1/r2/r3/rall`）的觀測基準線校準，那批結果還沒跑完；且 Converse & Stahler (2010) 本身模擬的是**氣體驅離後、已達 virial 平衡**的星團狀態，不含胚胎星團／氣體動力學階段（該文獻明講這段留給未來工作），準備初始條件時不要把兩者混為一談。完整修法記錄（含兩個踩到的 Windows 可攜性問題）見 `PDMF_TO_IMF_PLAN.md` 第七節與新增的 `nbody_setup/` | 模擬出的 α(r) 跟雙星徑向分布，能跟第 2 步的觀測 α(<r) 與 [Liu+2025 的雙星徑向雙峰分布](https://iopscience.iop.org/article/10.3847/2041-8213/adbe60) 做比較 | 論文原創性賣點，但需要先有觀測基準線才有東西可以比，排最後 |

## 目前已知的固定分工（不用每次都查表）

- **本機 8 核運算佇列**（`queue.txt` / `run_queue.py`，Windows ARM64 這台機器）
  只有這台機器能跑，其他人／agent 不會撞到，不需要在此認領。目前跑到
  `verify_bprperr_off`，後面排 `verify_bprperr_on`、`p2_free_lowmass`、
  `radial_r1`、`radial_r2`、`radial_r3`、`radial_rall`（PDMF→IMF 第 2 步，
  2026-08-12 已插入且已標為優先，**2026-08-12 這條筆記原本漏列這四項，
  已補回**）、`p6_lowmass_v2`、`p11_outlierfrac_v2`。
- 若要在別的機器（Kaggle、同學的電腦、Codex 的環境）重跑本機佇列裡
  同一個腳本、同一組參數，**先在這裡加一行認領**，避免兩邊各自跑一次
  浪費算力、之後也不知道該採哪一份結果。
- **開機/登入自動重啟**（2026-08-13 新增，`restart_queue_on_boot.ps1`）：
  起因是 2026-08-12 21:54 這台機器重開機，直接砍掉了 detached 的
  `run_queue.py` 整棵行程樹，`p2_free_lowmass` 跑到一半被腰斬，一路
  閒置到隔天 02:24 才被使用者發現，浪費 8.5 小時。現在用 Windows
  工作排程器註冊了一個登入時觸發的任務（`M45-QueueRunner-AutoRestart`），
  偵測到 `run_queue.py` 沒在跑就自動重啟，已在跑就略過（不會重複啟動）；
  跑過程碰到的兩個坑（PowerShell 讀中文 .ps1 沒有 BOM 會解析錯誤、
  跟主 log 檔案搶寫入鎖）都修好並記在腳本開頭註解裡。**已知限制**：
  這個排程任務只在**這台機器上**註冊（工作排程器設定不是 git 版控的
  一部分），跟這台機器綁定；`queue.txt` 本身的設計已保證安全（任務
  整批跑完才會 mark_done，中途被砍不會誤判成完成，重啟後從頭重跑
  那一項不會用到殘缺輸出）。**驗證狀態**：直接呼叫腳本本身測過兩種
  分支都正確（值測到已在跑→略過；沒在跑→重啟），但透過工作排程器
  手動觸發測試時行程會卡住不執行（懷疑是這個工具執行環境本身的
  session 限制，不是腳本邏輯問題）——真正的開機/登入觸發沒有實測到，
  下次真的重開機時麻煩順便確認一下 `logs\autorestart.log` 有沒有
  新紀錄。

## 紀錄（續）

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步（fetch_gaia → prep → pyUPMASK 第1步 → 第2–5步），跟既有 `results/baseline.dat` 與文件記錄的頭條數字比對，不是新的科學結果 | 進行中 | 先跑到獨立檔名（不直接覆寫 `results/baseline.dat`）比對，一致才決定要不要正式取代；分支 `yutunglan/x64-pipeline-verify` | 這台是 x64（非 ARM64），跟本機 8 核佇列那台不是同一台，不會搶 `queue.txt`。環境建置與 `fetch_gaia.py` 可攜性 bug 已在 PR #15 修好並合併。跟這台機器上同時在跑的 Kaggle 掛載排查（見上面那行）沒有檔案重疊，只是提醒：這台電腦目前有多個 session 同時操作同一個 working directory，git 分支切換偶爾會互相干擾，commit 前務必先確認當下分支 |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步 | **完成，數字與既有結果一致，未覆寫任何 tracked 結果檔** | 無（`data/`、`results/` 的重跑輸出已 `git checkout --` 復原成 repo 原版） | 逐星比對：兩次跑（同 `random_seed=42`）的 6,956 顆星星集合完全相同，`probs_final` 相關係數 0.9992，P≥0.7 成員數 1,298 vs repo 記錄的 1,297（差 1 顆，落在專案自己記錄的「同種子仍有殘餘隨機性」量級內，pyUPMASK 平行處理沒有被單一種子完全鎖死）。第 2–5 步頭條數字：f_bin=0.45（一致）、四法標記 415/100/58/24（vs 414/100/58/24）、alpha_naive=1.978±0.069（vs 1.980±0.069）、alpha_forward=2.350（一致）、質量分層 α(r) 1.77/2.02/2.12/2.31（vs 1.77/2.01/2.15/2.29）。**結論：pipeline 在獨立的 x64 機器上完全可攜、可重現**，順便在 `prep.py` 修了跟 PR #15 同一種寫死 `gaia-export` 路徑的 bug（`fetch_gaia.py` 那次漏改了這支）。沒有覆寫任何 `results/` 或 `data/` tracked 檔案，這次驗證不影響任何既有結論或數字，所以沒有加 `RESULTS_LOG.md` 條目 |
| 2026-08-12 | Claude session（本機，ARM64 8核） | **PDMF → IMF 這條線**：方法調查、動力學年齡計算、α(r) 梯度實驗、四路線規劃 | 第 1、2 步進行中（第 3–5 步開放認領） | 新增 `PDMF_TO_IMF_PLAN.md`；`fit_real.py` 加 `--radius-range`；`queue.txt` 加 4 個 radial 診斷；分支 `claude/pdmf-to-imf` | 使用者確認「IMF 本來就是專案目標」、四條路線都要做、照合理順序來。**完整計畫與文獻調查見 `PDMF_TO_IMF_PLAN.md`**。關鍵發現：核心-外圍 α 差 0.515，是統計誤差 0.144 的 3.6 倍、比最大系統誤差 0.248 還大，但可能有一部分是雙星比例隨半徑變化的假象（Liu+2025），第 2 步的 radial_r1/r2/r3/rall 就是要分辨這件事。**第 3 步（LIMEPY 多質量平衡模型，純 Python、ARM64 無痛）跟第 5 步（N-body，需要 x64 機器編譯）都還沒人做，跟本機佇列不衝突，歡迎認領** |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | PDMF → IMF 優先度覆核（使用者要求：確認清單完整、把相關項目優先度調到非 A/B 類項目之前） | **完成** | `WORK_BOARD.md`（下面「待認領工作：PDMF → IMF」表新增優先度欄）；`queue.txt` 未變更 | 使用者確認第 13（C21）、14（C22）兩個背景關聯條目**不用一起處理**。逐一核對 `LIMITATIONS.md`（A/B/C/D 分類）、`WORK_BOARD.md`、`queue.txt`、`PDMF_TO_IMF_PLAN.md`、`教學_PDMF轉IMF.md` 後列出完整清單給使用者確認（涵蓋已完成/已排隊/開放認領/背景關聯四類，共 15 項）。**查核結果：`queue.txt` 已經符合「PDMF 相關項目排在非 A/B 類前面」的要求，目前待跑的 `radial_r1/r2/r3/rall` 已經在 A/B 類重跑（`p6_lowmass_v2`／`p11_outlierfrac_v2`）之前，中間沒有非 A/B 類項目，不需要調整順序**。改在「待認領工作：PDMF → IMF」表加優先度欄：第 3 步（LIMEPY）與第 5 步（N-body）標為「可立刻開始」（環境準備／編譯測試不需要等第 2 步結果），第 4 步維持「等第 2 步結果」不變。已確認 `multi_stage_best()` 精修 bug 修復（2026-08-11）確實在目前 `injection_recovery.py` 程式碼中，`queue.txt` 的 radial 診斷都帶 `--refines 3,3`。下一步：向使用者確認要不要開始第 5 步（N-body，這台 x64 機器能做、ARM64 佇列做不到）的環境準備 |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 第 5 步（N-body）環境準備：裝 MSYS2/MinGW-w64、編譯 PeTar（含 BSE）+ mcluster，驗證端到端可跑 | **編譯環境完成並已寫成可重現的 `nbody_setup/`；正式模擬仍等第 2 步基準線** | 本機外部工作目錄 `nbody/`（跟這個 repo 平行、不進版控，不是 repo 檔案，內容已釘選 commit 並整理進 `nbody_setup/`）；`WORK_BOARD.md`（第 5 步狀態更新）、`PDMF_TO_IMF_PLAN.md`（第七節新增完整修法記錄）、新增 `nbody_setup/`（`README.md`、`setup_windows_nbody.sh`、兩個 patch、`mingw_compat.c`/`.h`），分支 `yutunglan/nbody-env-setup` | 使用者確認先試 MSYS2/MinGW（不用 WSL，因為這台機器同時有其他 session 在跑，重開機風險太大）。`winget install MSYS2.MSYS2` + `pacman` 裝 `mingw-w64-x86_64-toolchain`／`gcc-fortran`／`cmake`／`gsl`／`autoconf`／`automake`／`libtool`，全程不需要重開機、沒有干擾同機其他 session。Clone FDPS（pin v7.0）、SDAR、PeTar、mcluster 四個 repo 到同一層目錄，commit 已釘選（見 `nbody_setup/README.md`）。**踩到兩個真的 Windows 可攜性問題，都修好了**：(1) PeTar 的 `configure` 其實本來就有 `Cygwin*` 或 `Mingw*` 的 Windows 分支，但 MSYS2 的 `uname` 回傳全大寫 `MINGW64_NT-...`，大小寫不匹配被誤判成不支援的 OS，改一行 case pattern 就過；(2) mcluster 用了 MinGW runtime 沒有的 glibc 擴充函式 `srand48`／`drand48`／`feenableexcept`，寫了一個小型相容層（標準 rand48 LCG 演算法）補上。**驗證**：`petar.omp.avx2`（純重力）與 `petar.omp.avx2.bse`（含 BSE 恆星演化）都編譯成功且能正確執行物理積分——1000 顆星 Plummer 模型測試，能量守恆誤差 ~2.5e-5、角動量守恆誤差 ~1e-10；`mcluster_sse`（Kroupa IMF + Kroupa/Sana 聯星週期分布）也編譯成功，並跑通 `mcluster_sse` → `petar.init` → `petar` 全鏈（100 顆星，25 組聯星，含 BSE，exit code 0）。**兩個外部工具的原始碼修改原本只在本機工作目錄，CodeRabbit review 後已補上釘選 commit + patch 檔進這個 repo 的 `nbody_setup/`，讓別人可以重現，不用重踩一次**。**這批只驗證了「能編譯、能跑」，不代表可以直接開始正式模擬**——正式模擬要等第 2 步觀測基準線出來校準，且 Converse & Stahler (2010) 模擬的是氣體驅離後、已達 virial 平衡的狀態，不含胚胎星團／氣體動力學階段本身（該文獻明講留給未來工作），準備初始條件時要分清楚 |
