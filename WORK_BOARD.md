# 工作認領表（誰現在在做什麼）

`CONTRIBUTING.md` 管「怎麼合併」，這份管**「開始做之前先看這裡，避免兩個人／
兩個 agent 同時做同一件事」**。跟 `results/RESULTS_LOG.md` 一樣設計成
**只附加、不改舊行**的格式——多人同時寫幾乎不會撞行，不需要鎖檔案。

**2026-08-23 起：這份只放還沒做完的**（進行中／暫停／交接中／疑義的
紀錄，以及全部「待認領工作」表格）。**已經完成的歷史紀錄搬到了
`WORK_BOARD_DONE.md`**——任務做完時整段歷史會搬過去，這份不會越堆越長、
找不到「現在還有什麼要做」。完整規則（含搬移時機與做法）見
`CONTRIBUTING.md` 零節。

## 欄位

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|

## 紀錄

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|

（2026-08-23：這份文件拆分時，原本累積在這裡的歷史紀錄整批搬去了
`WORK_BOARD_DONE.md`——每一筆搬走的任務最新狀態都已經是「完成」，
不影響現況判斷。開始新工作、或任務狀態還在變動中，直接在這裡加一行。）

## `p6_lowmass_v2` 成本過高、擋住本機佇列（2026-08-21 10:26）——**使用者已決定：移到佇列最後**

**這一節原本記的兩個數字，2026-08-21 覆查時無法佐證，已訂正**（原文
保留在下方引用區塊，不要當成既定事實引用）：

> 原文：本機 `p6_lowmass_v2`（2026-08-20 15:16 啟動）的第 1 次擬合花了
> 67,213 秒 = 18.7 小時（見 `logs/p6_lowmass_v2.log`），15 次合計約
> 280 小時 ≈ 11.7 天。

覆查發現 `logs/p6_lowmass_v2.log` 在本機只有 7 行、**沒有任何一行擬合
完成時間**，且檔案時間（08-20 10:34）早於上面所述的啟動時間（15:16），
無法佐證 67,213 秒這個數字。它可能是對的（log 也可能被後續重啟覆寫），
但在能重新量到之前不當既定事實用。

**可以查證的成本量級**：這項工作是 5 個低質量段冪次 × 3 次重複 =
**15 次擬合**（這是設定本身，確定）。同類工作的單次成本可從
`logs/queue_done.txt` 查到：`radial_r1_final` 5 次重複共 72,814 秒，
平均約 4 小時／次，而那是 355 顆的核心切片；`p6_lowmass_v2` 是全樣本
1,078 顆，單次成本只會更高。15 次的總量級足以讓後面的項目等很久。

**原先列出的三個問題，2026-08-21 覆查後的現況**（只有第 2 項確定成立）：
1. ~~**幾乎不可能跑完**：沒有續傳機制~~ **這一點已不成立**（2026-08-21
   訂正）：`profile_lowmass.py` 已於 PR #85 接上
   `scripts/tools/checkpoint.py`，每次重複算完就存檔，重開機後讀回既有
   進度、不會從頭重算。原文描述的是 2026-08-20 15:16 那個用舊程式碼啟動
   的行程，不是現在 repo 裡的程式碼。**重開機不再等於全部白費**，這一點
   對取捨影響很大，不要再用它當延後的理由。
2. **擋住本機佇列後面的項目**（這一點成立）：`run_queue.py` 循序執行。
   以 `main` 目前的 `queue.txt` 為準，排在它後面的是
   `p11_outlierfrac_v2`／`d1_bhac_check`／`c13_bias_floor_nsyn4x`／
   `d10_config_cd_real`／`c19_extra_scatter_sweep`，共 **6 筆項目
   （5 個相異標籤——`d1_bhac_check` 重複出現兩次，兩行位元組相同，
   第二筆會被 `read_done()` 依標籤去重跳過）**。
   原文寫「8 項」並列出 `c5_davform_lognormal`／`c5_davform_truncexp`，
   但那兩項來自**尚未合併的 PR #87**，`main` 上的 `queue.txt` 目前
   grep 不到（PR #87 合併後才會變成 8 筆）。C5 是**現役缺陷．優先度 高**
   這一點沒有變，只是對應的佇列項目還沒進 `main`。
3. **Kaggle 可行性待確認**（原本寫「Kaggle 也裝不下」）：這一點繫於單次
   擬合時數，而上面說明該數字目前無法佐證，所以整條降級為待確認，**不要
   當成已確認的限制拿去做決策**。方向上仍成立的部分只有：照 `p6b` 那樣
   按軸拆片救不了「單次擬合」本身，只能拆重複次數。

**已確認沒問題的部分**：精修有真的生效（第 1 次的 alpha=2.633 不落在
0.20 的粗網格上），所以這條路線的**方法是對的**。

**使用者已於 2026-08-21 決定採用選項 C**（把這一項移到佇列最後），
已在 PR #96 實作，`queue.txt` 內留有說明。以下四個選項與代價保留作為
當時的決策依據：

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 維持現狀 | 讓它繼續跑 | 持續擋住後面的項目 |
| B. 降重複次數 | 改成 `--repeats 1`（5 次擬合 ≈ 94 小時） | 沒有誤差棒，d(alpha)/d(p) 的斜率不確定度無法量化 |
| **C（已採用）**. 先跑完後面的項目再回頭 | 把這一項移到佇列最後 | A1/A3 這個最大單一系統誤差（0.248）繼續懸著 |
| D. 減少掃描點 | 5 個冪次減成 3 個（0.9/1.3/1.7） | 斜率擬合只剩 3 點，但仍可量方向與量級 |

**不建議的做法**：把 `--refines 3,3` 降回 `--refines 3`——那正是 A1
要修的精修 bug 本身，降回去等於白跑。

**實際執行時的狀態**：移動當下 `p6_lowmass_v2` 還沒開始跑（`run_queue.py`
仍在跑 `radial_r2_final`，`logs/queue_done.txt` 沒有 p6 的紀錄），所以
這次移動是**零損失**，不需要殺掉任何正在跑的東西。

**之後真的要跑它之前**：**一定要先手動把 `results/profile_lowmass.npz`
（2026-08-15 的舊檔、無 manifest、是未精修的粗網格結果）移開**——這是
目前唯一可靠的做法，不要指望程式擋下來。

**為什麼不能指望程式擋**（2026-08-21 訂正，原文誤稱「有兩道保護會擋
下來」）：`main` 上的 `checkpoint.check_manifest()` 目前對無 manifest 的
舊檔仍然只印一行警告就「視為信任沿用」（已用 `git show
origin/main:scripts/tools/checkpoint.py` 核對過），**會直接沿用那批壞
結果**。真正會擋下來的兩道保護都還在**未合併的 PR** 裡：PR #89 把
`check_manifest()` 改成中止、PR #96 讓 `preflight.py --gate c` 在沒有
manifest 時照樣判定量化簽章。**這兩個 PR 合併之前，程式不會攔你。**

## 待認領工作（2026-08-12，`multi_stage_best()` 精修 bug 修好後還沒排的重跑）

背景：`injection_recovery.py` 的 `multi_stage_best()` 曾有精修 bug（見
`LIMITATIONS.md`「`multi_stage_best()` 精修 bug」一節），已修好。受影響
結果裡優先度最高的兩個（`p6_lowmass_v2`、`p11_outlierfrac_v2`）已經在
本機佇列排隊（見下一節），**以下是還沒被任何人排進佇列、任何人／任何
機器都可以認領的重跑**——認領時在上面「紀錄」表加一行，跑完把結果
commit 進 `results/`、`results/RESULTS_LOG.md` 記一行、開 PR。

| 優先度 | 任務（括號＝對應 `LIMITATIONS.md` 條目） | 指令 | 為什麼 |
|---|---|---|---|
| 中 | P9a-redo v2（MH 鎖定检验，PARSEC）（A1、A4） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --tag _fixmh_parsec_redo_v2 --refines 3,3` | 舊結果 α=2.440±0.180 完全沒精修（純粗網格 argmax）。這是表 4 穩健性主張的一半，另一半是下面 P9c |
| 中 | P9c v2（MH 鎖定检验，MIST）（A1、A4） | `python fit_real.py --procs 8 --n-syn 40000 --repeats 10 --configs C --fix-mh 0.0 --grid mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat --tag _fixmh_mist_redo_v2 --refines 3,3` | 舊結果 α=2.180±0.098 同樣完全沒精修 |
| 中 | P6b v2（低質量段冪次可辨識性）（A1） | `python inject_lowmass.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3` | 舊結果（ratio 0.92）完全沒精修；這個數字決定要不要把低質量段冪次升格成自由參數（`p2_free_lowmass` 已經在跑了，但可辨識性本身的精確度也該補） |
| 中 | `verify_bprperr_v2`：off/on 都用相同精修程度重跑（A1、B1） | `verify_bprperr_off`／`on` 已經跑完（2026-08-13 commit），**但這裡先前的判斷是錯的**：逐一核對時間戳後發現 `verify_bprperr_off` 實際在 2026-08-11 10:47:42 開始跑，**早於**同一天 16:57:09 才提交的精修 bug 修正，是完全沒精修的粗網格結果（α=2.420±0.098）；`verify_bprperr_on` 在 18:07:11 才開始，晚於修正時間，但沒帶 `--refines 3,3`，只精修一階（α=2.420±0.078）。兩次精修程度不一樣，不是乾淨對照，兩邊都要用同一組 `--refines 3,3` 重跑一次。**可直接執行的指令**（輸出改用 `_v2` 後綴，不會覆寫既有的 `fit_real_bprperr_off.npz`／`_on.npz`）：<br>`python fit_real.py --procs 8 --n-syn 40000 --repeats 5 --configs C --refines 3,3 --tag _bprperr_off_v2`<br>`python fit_real.py --procs 8 --n-syn 40000 --repeats 5 --configs C --native-bprp-err --refines 3,3 --tag _bprperr_on_v2`<br>跑完後兩個新檔案都要記進 `results/RESULTS_LOG.md` | 兩次中心值剛好都是 2.420（差 0.000），方向上支持「BP/RP 誤差模型選擇對 alpha 影響可忽略」，但精修程度不一致，不能當成已驗證的結論——`verify_bprperr_v2` 是要排除這是不是精修差異造成的巧合 |

**另外**：PR #11（多星團驗證）已經留言列出 4 個正確性問題（貼牆偵測
被關掉、選擇函數驗證漏掉紅藍分色檢查等）（D8、C22），見
<https://github.com/helmet-png/m45-imf-analysis/pull/11#issuecomment-5264701703>——
這也是待認領工作，適合 PR 作者（Codex）或任何人接手修。

## 待認領工作：PDMF → IMF（2026-08-12，見 `PDMF_TO_IMF_PLAN.md` 完整背景）

第 1、2 步（文獻基準線、前向模型徑向診斷）已在做，見上面的「紀錄」。
**2026-08-19 更新：第 2 步的四個初步值（r1/r2/r3/rall）都已到齊**，
下面第 3、4、5 步原本各自標注「等第 2 步結果」的部分現在都有東西
可以對照了——**但這四個值仍是 `_prelim`（單次重複、單階精修）版本，
不是最終數字**，下面每一步用到這些數字時都要清楚標注這一點，不要
當成已經統計上穩健的最終基準線。以下第 3–5 步都還沒人認領，且都
跟本機佇列不衝突（第 5 步甚至需要另一台 x64 機器，本機跑不了）。
這三個不是「跑一行指令」等級的任務，起手式跟驗收標準寫在下面，
實際做法留給認領的人判斷。

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

| 步驟 | 任務（括號＝對應 `LIMITATIONS.md` 條目，全部是 A5） | 優先度 | 起手式 | 驗收標準 | 為什麼 |
|---|---|---|---|---|---|
| 第 3 步 | LIMEPY 多質量平衡模型，反推潮汐半徑外的質量函數（A5） | **模型本身已完成（2026-08-13，`limepy_multimass.npz`，見 `LIMITATIONS.md` B5）——2026-08-19 更新：驗收標準的最後一步（跟第 2 步 α(<r) 對照）現在可以做探索性比對了**，見下方新增待認領表 `limepy_radial_crosscheck`；**但這只是方向性檢查，用的是 `_prelim` 單次無誤差棒版本，正式驗收（判斷模型是否真的「重現」觀測）要等 `radial_final_reruns` 的有誤差棒版本才算數** | 環境問題已解決（獨立 venv 釘 `scipy==1.16.3` + `astro-limepy`），模型本身不用重做 | 擬合出的多質量模型能重現第 2 步 `radial_r1/r2/r3/rall` 量到的 α(<r)，且對潮汐半徑外的質量函數給出具體數字（不是只有結構參數） | 這是唯一不需要重抓資料就能估計「潮汐半徑外還有多少低質量星」的路線 |
| 第 4 步 | 放大搜尋半徑到 8–17°，重抓 Gaia、重跑成員判定與選擇函數（A5） | **2026-08-19 更新：分兩層門檻，只有第一層滿足**——`PDMF_TO_IMF_PLAN.md` 第四節原文是「要等第 2 步證實梯度是真的才投入」，這個條件本身分成 (1) 有資料可看：**已滿足**，`_prelim` 版 α(<r) 到齊（r1(0-1°)=2.10、r2(0-2°)=2.43、r3(0-3°)=2.50、rall(0-5.1°)=2.43）；(2) 梯度統計上證實是真的（不是雜訊）：**還沒滿足**，這四個是單次無誤差棒的初步值，r1→r3 上升後 rall 又降，這個非單調現象本身還不能判斷是真實訊號還是雜訊。**兩份文件（本檔與 `PDMF_TO_IMF_PLAN.md`）在這一點上是一致的：都要求先做下方 `radial_final_reruns` 拿到有誤差棒的版本，才能真的判斷「梯度是否證實為真」，還不能直接投入第 4 步** | 起點是 `config.toml` 的 `radius_deg`，改大後整條 pipeline（`fetch_gaia.py` → `run_pipeline.py` 第 1–5 步）要重跑，pyUPMASK 在大半徑下的成員判定沒驗證過，選擇函數也要重建 | 新的 6,956→N 顆全樣本跑出 α，且大樣本下 pyUPMASK 的品質檢查（六格驗證圖）跟現有 5° 版本一樣通過 | 觀測上唯一能給出決定性答案的路線，但成本最高，所以排最後投入 |
| 第 5 步 | N-body 重建 M45 初始狀態（跟 Converse & Stahler 2010 同路線，**2026-08-19 更新：方法本身建議改採 Hobart et al. 2026 的模擬器路線，見 `PLAN_文獻對照_Hobart2026.md` 第二節 2.5**）（A5） | **探索性模擬不用等第 2 步**（第一個 pilot 已經跑完並拿到初步 α(r)）。**2026-08-19 更新：跟第 4 步同一套兩層門檻**——`PDMF_TO_IMF_PLAN.md` 第五節說「需要先有觀測基準線才有東西可以比」，這個條件的第一層（有基準線可比）**已滿足**（`_prelim` 版四個值到齊），可以拿來做**初步、探索性的校準方向**（見下方 `nbody_prior_from_radial`）；但第二層（基準線本身統計上穩健）**還沒滿足**，正式、投入完整算力的校準版本，仍要等 `radial_final_reruns` 的有誤差棒版本才能做，這一點跟 `PDMF_TO_IMF_PLAN.md` 沒有矛盾 | 編譯與工具鏈已裝好並驗證（見 `nbody_setup/`）。**2026-08-13 已跑第一個 pilot**（400 顆星、270 系統、65% 聯星、Kroupa IMF、質量分層度 0.5、virial 平衡起始、含 BSE 恆星演化，積分 125 Myr）：**alpha(r) 從核心 0.879 升到外圍 1.316**，方向跟 M45 觀測的質量分層方向（核心 1.77 → 外圍 2.29）一致。**2026-08-19 訂正**：這個「方向一致」的比較本身還沒有嚴謹意義——pilot 用的是互斥環帶的 α（`analyze_alpha_r.py` 用 percentile 切三等分），觀測用的是累積 α(<r)（`radial_r1/r2/r3/rall`），兩者定義不同（見下方 `nbody_prior_from_radial` 的說明），在兩邊統一成同一種分箱定義之前，「定性一致」這個講法先降級為「兩條曲線都是遞增的，但嚴格比較還沒做」，不是已確認的一致性。此外單次、小 N、未校準，數值本來就不能直接引用。完整記錄見 `PDMF_TO_IMF_PLAN.md` 第七節、`nbody_setup/` | 模擬出的 α(r) 跟雙星徑向分布，能跟第 2 步的觀測 α(<r) 與 [Liu+2025 的雙星徑向雙峰分布](https://iopscience.iop.org/article/10.3847/2041-8213/adbe60) 做比較 | 論文原創性賣點，但需要先有觀測基準線才有東西可以比，排最後 |

## 待認領工作：第 2 步四項到齊後新解鎖的工作（2026-08-19）

**全部不在本機（x64 8 核桌機）跑**——本機佇列（`queue.txt`）留給
既有排隊項目，這幾項規模較大或需要不同架構／機器，請認領的人在
自己的機器（x64 協作機、Kaggle、或評估過的雲算力，見
[雲算力評估](https://claude.ai/code/artifact/8f3b0148-708e-4ddc-a10d-1870dc39ec83)）上跑，不要排進本機的 `queue.txt`。

| 任務 | 起手式 | 驗收標準 | 為什麼現在能做 |
|---|---|---|---|
| `radial_final_reruns`（A5，最優先——下面兩項都依賴這個） | 用完整設定重跑四項：`fit_real.py --procs 8 --n-syn 40000 --repeats 5 --refines 3,3 --configs C --radius-range 0,1 --tag _radial_r1_final`（r2/r3 比照，半徑範圍改 `0,2`／`0,3`；rall 不帶 `--radius-range`，`--tag _radial_rall_final`）。四項合計單次 prelim 已知耗時 5,298–29,319 秒不等（見 `logs/queue_done.txt`），乘上 5 次重複，四項合計預估數十小時等級，適合排到有很多核心的機器（TWCC／雲端 spot，不是本機） | 四個 `_final` 版本都有統計誤差棒（不是單次無誤差棒），且要明確回答「r3(2.50) > rall(2.43) 這個非單調現象是真實訊號還是統計雜訊」——誤差棒若明顯重疊則是雜訊，若不重疊則是需要解釋的真實現象 | 下面 `limepy_radial_crosscheck` 與「決定要不要投入第 4 步」都需要有統計誤差棒的版本才能下結論，`_prelim` 版本（單次無誤差棒）不夠 |
| `limepy_radial_crosscheck`（A5、B5，對應第 3 步驗收標準） | 讀 `scripts/diagnostics/limepy_multimass.py` 目前的模型輸出（`results/limepy_multimass.npz`），從擬合出的 King 模型（phi0=3.44、r0=2.50 pc）算出模型預測的 α(<r) 在 r1/r2/r3/rall 對應半徑處的值，跟觀測值（prelim：2.10/2.43/2.50/2.43；建議等 `radial_final_reruns` 的 `_final` 版本出來再做，用有誤差棒的版本比較才有意義）並排比較 | 給出模型預測 α(<r) 與觀測 α(<r) 的逐項對照表，量化兩者差距是否在統計誤差內；若明顯不符，要指出可能原因（King 模型是單一質量分層假設，跟真實分層可能不符） | LIMEPY 模型本身已經擬合完成（2026-08-13），只差這一步比對，是第 3 步唯一剩下的動作 |
| `nbody_prior_from_radial`（A5，第 5 步「初步校準」，不是正式版）**2026-08-20：前置的定義不一致已解決，見本列末段** | **開始前先解決一個真的定義不一致的問題**：`fit_real.py --radius-range LO,HI` 算出來的 `radial_r1/r2/r3/rall` 是**累積**α(<r)（0-1°、0-2°、0-3°、全樣本，一層包一層，不是互斥區間）；`nbody_setup/analyze_alpha_r.py` 卻是用 `np.percentile` 切三等分位算**互斥環帶**的 α（0-33%、33-66%、66-100%，各自獨立不重疊）。這兩種是不同的量，不能直接並排比較同一條「α(r)」曲線。**兩個修法選一個，校準目標各自對應，不要混用**：(1) 把 `analyze_alpha_r.py` 的模擬粒子改用累積半徑切法（比照 `radius-range` 的 0-1°/0-2°/0-3° 換算成 pc 後的累積邊界）重新分箱，這種做法的校準目標就是**現成的** `radial_r1/r2/r3/rall`（prelim 或 `_final`）α 值，不用另外算；(2) 把觀測資料也額外用互斥環帶（比照 `analyze_alpha_r.py` 的 percentile 切法）重新分箱一次算出**另一組獨立的**觀測 α，這種做法的校準目標是這組新算出來的環帶 α，**不是**現成的 `radial_r1/r2/r3/rall`（那是累積值，跟環帶模擬結果比會是選項 (1) 沒做完就混用了選項 (2) 的資料）。選定一種、備妥對應的目標值後，設計一組圍繞 pilot 參數（400 顆星、質量分層度 0.5、virial Q=0.5）小幅擾動的網格（例如質量分層度 0.3/0.5/0.7 各跑幾次） | 至少 3–5 組不同初始參數的模擬跑完，且**觀測與模擬用的是同一種半徑分箱定義（累積或互斥擇一，並在結果裡明確標注是哪一種）**，每組跟觀測 α 的擬合優度（例如簡單的殘差平方和）有量化比較，明確標注這是「用 prelim 值做的初步校準方向」不是正式最終校準 | 這是 Hobart et al. 2026 建議的「先用小規模模擬網格摸清方向」路線的起手式，不用等到有大量模擬（他們是 550–942 次）才能開始，先幾組摸清梯度方向即可。**2026-08-20 更新：前置的「定義不一致」已依修法 (1) 解決**（`nbody_setup/analyze_alpha_r.py` 已改成累積投影半徑切法，校準目標就是現成的 `radial_r1/r2/r3/rall`）。動手時發現不一致**不只分箱這一項，總共三項**，三項都已對齊：(1) 分箱：percentile 互斥環帶 -> 累積切法（邊界用觀測角度換算成 pc）；(2) **半徑維度**（本表原本沒寫到）：3D 團心距 -> 投影半徑，因為觀測只量得到投影距離，3D 半徑恆大於投影半徑、直接並排會系統性高估模擬的外圍距離，另加 `--n-projections` 可對多視線平均掉投影雜訊；(3) **質量範圍與估計量**（本表原本沒寫到，**這項最嚴重**）：舊版對 0.1–2.0 M☉ 做 MLE，但觀測端前向模型的 `alpha` **只控制 Kroupa 分段的 m>0.5 段**（m<0.5 固定 1.3），0.1–2.0 跨過 0.5 這個分段點等於把固定段跟要比較的段混在一起，**跟前向模型的 alpha 根本不是同一個量**，已改成 0.5–2.50（下界對齊分段點、上界對齊 `config.toml [step5_imf] mass_max`）。附了 `--self-test`（不需 PeTar 環境即可跑）驗證累積邏輯、投影半徑不大於 3D 半徑、alpha 回收真值，並內建貼牆檢查——第一版 self-test 的合成分層做得太極端，核心片直接撞到 `mle_powerlaw` 的 alpha 下界 0.1，方向斷言因為貼牆而假通過，已改成溫和的統計傾向並加上貼牆斷言攔截。**仍未對齊、改腳本解決不了的差異**：觀測端是前向模型擬合值（含聯星／選擇函數／測光誤差建模）、這裡是對模擬真實質量做直接 MLE，兩者不是同一個估計量，只能當趨勢方向對照；且觀測值仍是 `_prelim` 無誤差棒，`radial_final_reruns`（已排進 Kaggle 佇列 20 分片）跑完前無法判斷差異顯著性。**下一步**：實際跑那組質量分層度 0.3/0.5/0.7 的模擬網格 |

## 待認領工作：B/C/D 類補齊（2026-08-13，見上一行紀錄的查證過程）

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| `bhac15_isochrone_test`（C1、D1） | 官方資料來源是 <https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/>（2026-08-16 已查證：舊網址 `phoenix.ens-lyon.fr/Grids/BHAC15/` 是錯的，見下方「紀錄」表對應行），仿 `build_mist_grid.py`／`build_dr2_grid.py` 的模式寫 `build_bhac_grid.py`，轉成跟現有 PARSEC/MIST 網格同樣的欄位格式，讓 `fit_real.py --grid` 直接可用。BHAC15 只涵蓋低質量前主序（通常到 ~1.4 M☉），要先確認涵蓋範圍夠不夠蓋過 M45 的擬合質量範圍（0.30–2.50 M☉），不夠的話要在文件裡誠實寫「只能驗證低質量段」，不要假裝驗證了全範圍 | 用 BHAC15 重跑跟 P3（`build_dr2_grid.py`）同樣的濾光片/模型效應分解，跟已有的 PARSEC-EDR3/PARSEC-DR2/MIST-DR2 三個數字放在同一張表比較 |
| `sensitivity_sweep`（D2，**部分完成 2026-08-19，見下方說明**） | 寫 `sensitivity_sweep.py`：對 `config.toml` 裡列出的每個未測設定（`pca_dims`、`stars_per_cluster`、`clustering_method`、`inner_loop_runs`、`hess_color_range`／`hess_mag_range`、`min_flux_snr_bp`、`membership_threshold`）各自取 2–3 個鄰近值，跑一次完整 pipeline（或只跑受影響的那幾步，例如 `pca_dims` 只影響第 1 步），記錄頭條 alpha 或成員數怎麼變。**這個任務範圍大**，可以先挑影響面最廣的 1–2 個設定（`membership_threshold`、`stars_per_cluster`）做示範，不用一次做完全部 7 個 | 每個測過的設定都有一個「改動這個值，頭條數字變化多少」的具體數字，寫進 `LIMITATIONS.md` D2 |
| `p6b4_boundary_retest`（D5） | 用 `inject_lowmass.py --tag _p6b4_retest`（**已經有 `--tag` 了，不會覆寫原檔**）只補測 `p_true=1.3` 這一組（目前程式碼會測 `P_TRUE_LIST` 全部三組，先跑一次確認能不能只挑一個真值跑，需要的話加個 `--only` 旗標） | 補測的這一筆 logage 沒有再貼到 PARSEC 網格邊界（8.25），若又貼牆，代表這是系統性現象不是單次巧合，要在 D5 裡升級處理方式 |
| `extinction_form_test`（C5） | 在 `pipeline/joint_fit.py` 的 `synthesise()` 對數常態消光旁邊，做一個可切換的替代分布（例如截尾指數分布），跑一次注入回收比較兩種分布下 A_V 系統誤差有沒有差異。這牽動核心前向模型程式碼，改動前先確認不會影響預設行為（新分布只在明確旗標開啟時生效） | 兩種分布形式下，用同一組合成真值做注入回收，alpha／A_V 的偏差量化比較 |
| `pyupmask_completeness_test`（C8） | 寫一個小規模的合成測試：在原始 Gaia 天測資料座標範圍內，注入已知數量、已知位置的合成「成員星」（自行/視差抽樣自星團分布），混進真實場星資料，重跑 pyUPMASK，量多少比例的注入星被正確判定為成員（召回率），依半徑/質量分箱看召回率有沒有系統性差異 | 給出完整度隨半徑/星等變化的具體曲線，不是只有一個全域數字 |
| `extra_scatter_sensitivity`（C19） | 在合成 CMD 裡疊加一個額外的高斯散布項（代表自轉/前主序光變/黑子的合併效應），散布量級參考文獻對年輕疏散星團光度變異的實測（例如轉動調製造成的 CMD 散布），掃過幾個散布量級，看 alpha 對這項未建模的物理有多敏感 | 給出「散布量級 vs alpha 偏移」的敏感度曲線，不是只回答「有沒有影響」 |
| `configCD_real_data_compare`（D10，2026-08-16 教學對話中使用者追問發現） | 用真實資料跑 `fit_real.py --configs C,D`（其餘旗標完全相同、同一批 `--repeats`），比較兩者的 alpha 中心值與散布。目前「alpha 不受 dav 貼牆位置污染」只在注入回收的合成資料上驗證過，真實資料沒有直接比較過 C 跟 D | C、D 的 alpha 差距要跟兩者各自的統計誤差（散布）比較——差距遠小於合併標準誤，才能確認 headline 數字沒有被 dav 不可辨識這個已知問題間接污染；若差距顯著，要回頭檢視現有 headline 數字，見 `LIMITATIONS.md` D10 |

**D2 進度說明（2026-08-19）**：`scripts/diagnostics/sensitivity_sweep.py` 已寫好，涵蓋兩種目標：
- `--target membership_threshold`：重新套用 `results/baseline.dat` 的成員機率門檻 -> 重跑第 2/3 步 -> 用 config C 跑一次前向模型，量 alpha 敏感度。**流程已驗證可行**（本機用小規模參數試跑通過），但完整掃描需要原始 Gaia 查詢 CSV（`data/m45_r5_g18_plx4.csv`，6,956 顆未篩選），這台機器原本沒有，追查後發現產生它的 `fetch_gaia.py` 依賴另一個私有 repo `github.com/helmet-png/gaia-dr3-export`——已 clone 到 `Documents/` 同層解鎖依賴，但重抓時卡在第一步：`fetch_gaia.py` 會先送一個 `SELECT COUNT(*)` 查詢決定要抓幾筆，這個查詢對 18 億列的 `gaia_source` 做 5 度錐形 + G<=18 + parallax>=4 篩選，**手動重現並拿到完整錯誤內文，確認是 ESA 伺服器端主動取消**：`SQL exception: ERROR: canceling statement due to statement timeout`（等了 183 秒後被砍），不是本機網路或帳號問題，是這個特定 COUNT 查詢在伺服端太重、撞到它自己的 statement timeout。**已知可能的解法**（留給下一個 session，這是 `gaia-dr3-export` 那個獨立 repo 的程式，不在這個專案範圍內改）：跳過精確計數，直接在主查詢用一個夠大的 `TOP`（例如 20000，M45 這個天區遠不會到這個量級）取代 `count_sources()` 那一步。**下一個 session 檢查 `data/m45_r5_g18_plx4.csv` 是否已成功抓到**，有的話直接跑 `python scripts/diagnostics/sensitivity_sweep.py --target membership_threshold`（預設掃 0.5/0.6/0.7/0.8/0.9 五個門檻，`--n-syn 40000 --refines 3,3` 較準，示範用可以先 `--n-syn 5000 --refines 3` 求快），沒有的話重跑 `python scripts/data_prep/fetch_gaia.py --target M45 --radius 5.0 --gmax 18.0 --plxmin 4.0 --force`。

**2026-08-21：阻擋已解除，檔案抓到了**。原因確認是 `count_sources()` 那個
COUNT(*) 查詢在 ESA 端逾時（不是本機網路），主查詢本身不做 COUNT、只取前 N 列
反而跑得動。已幫 `fetch_gaia.py` 加兩個旗標（**改的是本專案的檔案，不是那個
私有 repo**）：`--top` 跳過精確計數（並在取回列數頂到上限時中止、不靜默給
截斷資料），`--ra`／`--dec` 跳過 Sesame 名稱解析。

**`--ra`／`--dec` 不是可有可無**：Sesame 對 M45 回 RA=56.86909，跟
`config.toml [target]` 註解記的 56.60083 差 0.27 度，錐形位置跟著偏——實測
用 Sesame 座標抓到 6,986 顆，既有 `cmd_members.csv` 的 1,078 顆成員有 **2 顆
落到錐形外面**（覆蓋率 99.81%）。改用 config 的座標後抓到 **6,956 顆，跟本表
原本記載的數字完全一致，成員覆蓋率 1,078/1,078 = 100%**。敏感度比較的輸入
天區必須跟原本一致，否則量到的差異會混進「天區不同」這個額外變因。

正確的重抓指令是：
`python scripts/data_prep/fetch_gaia.py --target M45 --ra 56.60083 --dec 24.11389 --radius 5.0 --gmax 18.0 --plxmin 4.0 --top 20000 --force`
（檔案在 `.gitignore` 裡，不進版控，換機器要自己重抓一次。**`--force` 是必要的**：`fetch_gaia.py` 第 120 行對已存在的輸出檔會直接印「已存在，跳過」就結束，不加的話在已經抓過的機器上重跑這行等於什麼都沒做，卻看不出來——2026-08-21 CodeRabbit review 抓到。乾淨的新機器上不帶 `--force` 也會動，但照著這行複製貼上的人多半是想重抓。)

**2026-08-23 更新：端到端驗證跑過了**。用示範規模（`--procs 4 --n-syn 5000 --refines 3 --values 0.7`）實跑一次：先用更小的 `--n-syn 500 --refines 1` 試跑會撞牆（`WallError`：alpha 貼在下界 1.500），換成文件建議的示範規模後正常跑完，`threshold=0.70 → alpha=2.633、logage=8.000、A_V=0.500、lnP=1266.4`，耗時 23,142 秒（約 6.4 小時）——**證實那次撞牆是極端小樣本（n_syn=500）造成的假性失敗，不是腳本問題，整條流程（含上面解掉的資料抓取阻塞）真的能跑通**。單一門檻值還不構成敏感度結論（至少要 2 個門檻才有斜率可看）。**正式規模成本估計**：以 23,142 秒（n_syn=5000）外推，n_syn=40000 單一門檻約 50+ 小時，5 個門檻合計數百小時——跟「第 2 步四項到齊後新解鎖的工作」表上方同樣的機器分配原則，**不適合排本機 8 核佇列**。

**2026-08-23 再更新：已改派到 gcp1**（GCP e2-highcpu-8 SSH worker，見下方紀錄表 2026-08-23 那行），本機 `queue.txt` 這一項已停用避免重複算。正式規模先排 0.6／0.7 兩個門檻當第一批（`cloud_queue.txt` 的 `d2_membership_threshold_p06_p07_retry`），觀察真實耗時後再決定要不要把剩下的 0.5/0.8/0.9 也排進去，不用等本機或 Kaggle 有空。
- `--target stars_per_cluster`：這個設定要真的重跑 pyUPMASK 聚類，不是重新套門檻能測的。這台機器沒有 `pyUPMASK/` 目錄（未驗證能不能跑），腳本會誠實報告做不到，不會編造數字——已內建這個可行性檢查，**不要跳過檢查直接猜答案**。留給有 pyUPMASK 環境的 session。



- **本機 8 核運算佇列**（`queue.txt` / `run_queue.py`，Windows x64 這台機器；
  **2026-08-23 訂正**：2026-08-16 已交接到新機器 Acer AI 16（x64），這裡跟下面
  多處「ARM64」是沿用交接前的舊稱呼沒有更新，不是還在用 ARM64 桌機）
  只有這台機器能跑，其他人／agent 不會撞到，不需要在此認領。**2026-08-13
  更新**：`verify_bprperr_off`／`verify_bprperr_on` 已跑完（結果與精修
  程度不一致的發現見上面 `verify_bprperr_v2` 那一行，不要重複派工），
  目前正在跑 `p2_free_lowmass`，後面排
  `radial_r1`、`radial_r2`、`radial_r3`、`radial_rall`（PDMF→IMF 第 2 步，
  2026-08-12 已插入且已標為優先，**2026-08-12 這條筆記原本漏列這四項，
  已補回**）、`p6_lowmass_v2`、`p11_outlierfrac_v2`。`verify_bprperr_v2`
  不在 `queue.txt` 裡，是新待認領項目，還沒有人排進任何佇列。
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

  **2026-08-21 補上真正的自我復原**：這天 14:13–15:10 之間
  `run_queue.py` 與 `kaggle_queue.py` **同時無聲死掉**（stderr 全空、
  沒有重開機、Python 行程總共只用 1.3 GB 所以不是記憶體問題，死因無從
  證實），一直到排定巡檢才被發現，中間閒置約一小時。追查發現
  `restart_queue_on_boot.ps1` **腳本本身沒問題**（2026-08-18 已擴充成
  同時顧兩個行程），問題出在**工作排程器那個
  `M45-QueueRunner-AutoRestart` 只有「登入時」一個觸發器**——已經登入
  著的狀態下它永遠不會再觸發，等於只防重開機、不防行程中途死掉。

  想直接幫原任務加重複觸發器時被 `Access is denied` 擋下（那個任務要
  管理員權限才能改），改成**另外註冊一個使用者層級的新任務
  `M45-QueueWatchdog-15min`**：跑同一支腳本、每 15 分鐘一次、持續 3650
  天，`-MultipleInstances IgnoreNew` 避免重疊。腳本偵測到行程還活著就
  直接略過，所以重複觸發是安全的 no-op；已實測觸發一次，行程數維持
  2 個沒有被重複啟動。**原本的 `M45-QueueRunner-AutoRestart` 保留不動**，
  兩個併存（一個管開機、一個管中途死掉）。

  踩到的坑記一下免得下次重犯：`New-ScheduledTaskTrigger` 的
  `-RepetitionDuration ([TimeSpan]::MaxValue)` 會產生非法 XML
  （`P99999999DT23H59M59S`），要改用有限長度。

## 待認領工作：對照 Hobart et al. 2026 的鞏固工作（2026-08-19，完整比較見 `docs/planning/PLAN_文獻對照_Hobart2026.md`）

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| `empirical_ml_relation_test`（D11，**現役缺陷．優先度 中高**）**2026-08-21：可行性評估已完成，開工前先做評估文件第三節那五項查證** | **起手式（2026-08-22 CodeRabbit review 訂正順序）：先完成評估文件第三節那五項查證（波段轉換在紅端的適用範圍、食雙星彙編在 M ≲ 0.4 M☉ 的樣本量、消光處理一致性、經驗關係的金屬量覆蓋、dM/dM_V 誤差傳播），優先做前兩項（成本最低、且可能直接否決整條路線），通過後再做其餘三項——五項查證全部完成後才決定是否投入，順序不能反過來**。**「不得蒐集食雙星資料」指下載／整理可拿來擬合的資料集、開始寫實作，不含第二項查證本身需要的文獻盤點（數 Torres+2010／Benedict+2016／Iglesias-Marzoa+2017 裡 M ≲ 0.4 M☉ 有幾顆星）——那是完成第二項查證的必要步驟，不算「開始蒐集」（2026-08-23 CodeRabbit review：原文字面上會把第二項自己需要的動作也禁掉）。五項全過之後才動手：蒐集公開食雙星質量-光度資料（同一批文獻來源：Torres et al. 2010、Benedict et al. 2016、Iglesias-Marzoa et al. 2017，都可公開取得），仿 `pipeline/step5_imf.py` 的 `assign_masses()` 架構寫一條獨立於任何等時線的經驗質量估計路徑（M_V vs mass 的平滑擬合，方法可參考 Hobart et al. 2026 用的 B-spline + GCV 判準，或用更簡單的多項式/樣條，先求有再求精）。**這條關係是 M_V（Johnson V 波段）對質量，不是 Gaia G 波段對質量**——Hobart et al. 2026 明確指出兩者不等價，用顏色相依轉換（Riello et al. 2021 的 Gaia EDR3 光度轉換）把 Gaia 觀測轉成 M_V，這一步的轉換方法、消光處理、金屬量涵蓋範圍、未解析聯星處理、誤差傳播都要先定好並記錄下來，不能直接把 M_V-mass 關係套在 Gaia G/GBP/GRP 上 | 先固定 Gaia→M_V 波段轉換方法、消光處理、誤差傳播鏈；再用這條經驗關係重跑低質量段（<0.5 M☉）alpha，跟 PARSEC／MIST 兩條既有結果放在同一張表比較；alpha 差異要拆解成「質量-光度關係本身的差異」跟「波段轉換/金屬量/未解析聯星造成的額外差異」兩部分分別量化，不能混在一起報一個數字。**2026-08-21 可行性評估**（`docs/planning/PLAN_D11_經驗質光關係_可行性評估.md`，只評估、沒有實作）：質量精度**以 Gaia G 為準時**不是瓶頸（低質量段 dM/dG 不陡，0.05 mag 測光差只造成約 1.55–2.08% 質量誤差，適用 0.30–0.40 M☉）——但**口徑還不對**：經驗關係定義在 M_V，正確導數是 dM/dM_V，本機網格沒有 V 波段算不出來，在補上之前這只是待驗證的預期（2026-08-21 CodeRabbit review）；**目前初步判讀紅端的顏色覆蓋可能是主要風險**（2026-08-22 CodeRabbit review：dM/dM_V 本身還沒驗證前不能寫成定案）——要檢驗的樣本集中在 BP−RP ≈ 2.4–3.5，BP−RP ≥ 2.663（約 M ≤ 0.40 M☉）就佔 51.9%（559/1078） |
| ~~`bright_end_completeness_check`（D12）~~ **2026-08-20 初步查證完成，發現新問題見 LIMITATIONS.md** | 已查 HIPPARCOS+Gaia DR3 交叉比對：Alcyone 完全沒有 Gaia 視差解（資料層級限制，不是 pipeline 問題）；**意外發現 G=4.0–5.2 之間確認是星團成員（視差符合）的星也整批不在 `cmd_members.csv` 裡，範圍比 `g_bright_limit=4.0` 這條線本身更大，根因還沒追到**（需要原始 Gaia 查詢檔或針對這幾顆星的小量查詢，逐步比對 `run_pipeline.py` 第 1、2 步中介輸出） | 已達成基本查證；**新解鎖的下一步**：追出 G=4.0–5.2 這段星消失的具體原因（pyUPMASK 成員機率判定 vs `step2_cmd.py` 測光品質篩選），若是誤判排除，高質量段樣本數可望增加 |
| `d12_bright_end_root_cause`（D12） | 2026-08-20 Codex 完成：`65205373152172032`（G=4.173）在 pyUPMASK 後的 P=0.0017，於 P>=0.7 成員門檻前離開；HIP 17851（G=5.203）P=0.9999 且保留。詳見 `docs/planning/DIAGNOSIS_M45_BRIGHT_END_LOSS_2026-08-20.md`。沒有原始 Gaia 表，未推測未通過成員門檻星的第 2 步測光狀態。 | 完成（最小診斷）；8–10 顆外部亮星的小量 Gaia 欄位查詢仍待做 |
| `d12_bright_external_crosscheck`（D12） | 2026-08-20 Codex 完成：Hipparcos Hp<=6 的 17 顆亮星交叉 Gaia DR3，13 顆取得 Gaia 資料並回查 baseline/CMD。確認至少兩顆 G<4 高 P 星只因亮端切割未進 CMD；G=4.173 的已知例子則在成員門檻前離開。詳見 `docs/planning/M45_HIPPARCOS_BRIGHT_CROSSCHECK_2026-08-20.md`。 | 完成；若要量化對 IMF 的影響，需有外部**成員**目錄後才能做回收率 |
| `d12_bright_hr23_crosscheck`（D12） | 2026-08-21 Codex 完成：以保存的 HR23 M45 快照核對 17 顆 Hipparcos 亮星。HIP 17573 是外部 P=0.749、pipeline P=0.9999、但 G<4 因亮端設定未進 CMD 的明確例子；G=4.173 的低 pipeline-P 星不在此快照，未被誤稱為外部成員。詳見 `docs/planning/M45_BRIGHT_HR23_MEMBERSHIP_CROSSCHECK_2026-08-21.md`。 | 完成；完整外部成員目錄回收率仍待做 |
| `mass_dependent_fbin`（D14 衍生，2026-08-19 做 D14 時發現） | `synthesise()` 裡決定「誰帶伴星」的 Bernoulli(`f_bin`) 與主星質量 `m1` **完全獨立**，等於假設雙星比例不隨質量變化。這是已知簡化但從沒量化過代價。**Torres+2025 對 Pleiades 觀測到的是雙星比例隨半徑呈雙峰**——這支持「雙星比例不是常數」，但半徑相依不等於質量相依，兩者沒有直接證據連結，除非另外查到質量分層或明確的質量-半徑關聯，質量相依性本身仍是**待驗證假設**，不是有直接觀測支持的結論（2026-08-23 CodeRabbit review）。起手式比照 `profile_lowmass.py`：讓 `f_bin` 變成質量的簡單函數（兩段常數或線性內插），注入一個有質量相依性的假資料、用現有的常數 `f_bin` 模型去擬合，量 alpha 被推歪多少。**先做注入回收，不要直接把它升格成自由參數**——dav 的教訓是「參數可以放進模型卻完全不被資料約束」 | 給出「雙星比例質量相依性的強度 vs alpha 偏移」的具體數字；若偏移遠小於統計誤差 0.144 就記為可忽略並結案，不必升格成自由參數。**2026-08-20 進度**：`inject_massdep_fbin.py` 已寫好並排進 `queue.txt`（標籤 `massdep_fbin`，排在 c19_extra_scatter_sweep 之後），照本表要求「先做注入回收、不要直接升格成自由參數」。生成端新增 `JointModel.set_mass_dependent_fbin(contrast, m_break=0.5)`（**只影響生成，不呼叫時逐位元等同原本行為，已實測驗證**），擬合端用完全不變的常數 f_bin 模型。**設計上刻意固定整體雙星比例**：兩段的 f_bin 由樣本比例加權後恰好等於名目 f_bin——**這是寫 `set_mass_dependent_fbin()` 時的設計驗證**（contrast=0.10/0.20/0.30 三種強度下逐星 f_bin 平均都精確等於名目值 0.570，2026-08-20 confirmed），不是正式 sweep 的一部分，否則就同時動了「質量相依性」與「整體雙星比例」兩個變因，量到的 alpha 偏移分不清是哪一個造成的。**正式排入 `queue.txt` 的 sweep 是另一組值：contrast=0.0/0.15/0.30**（標籤 `massdep_fbin`，見上），**目前整組都還沒跑**（`queue.txt` 裡還在排隊，`logs/queue_done.txt` 沒有這個標籤），contrast=0.15 不是已驗證過的數字。**contrast=0 是必要的對照組**——C13 記錄這套注入回收本身的 alpha 偏差地板約 -0.050，跟要測的量級接近，不扣掉地板就無法判讀 |
| `mass_dependent_fbin_smoke`（D14 衍生） | 2026-08-22 Codex 完成 5 個假星團的注入回收：兩個示範性質量相依雙星規則使固定比例模型的 alpha 相對控制組平均偏移 -0.12、-0.21，但範圍跨過正負值（粗網格，僅篩檢）。詳見 `docs/planning/SMOKE_MASS_DEPENDENT_BINARY_FRACTION_2026-08-22.md`。不修改 headline 模型、不重跑既有 M45 結果。 | 已完成：若要升級，先做多種子、固定整體雙星比例且更細網格的注入回收 |
| `d12_hr23_cmd_recall_by_magnitude`（D12） | 2026-08-22 Codex 完成：保存的 HR23 高機率（P≥0.7）M45 快照在 CMD 的總重疊率為 81.9%；G=5.2–16 為 91.9–100%，G=16–18 為 79.5%，G≥18 為 0%（CMD 最暗 G=17.925）。不把 HR23 當真值、不重跑 membership/IMF。詳見 `docs/planning/M45_HR23_CMD_RECALL_BY_MAGNITUDE_2026-08-22.md`。 | 已完成；若要轉成完整度量化，需預先固定外部目錄版本、門檻、天空範圍及品質規則 |
| `mass_dependent_fbin_matched_fast`（D14 衍生） | 2026-08-22 Codex 完成：整體 `f_bin` 固定、60 個共同種子、較細 alpha/f_bin 網格。contrast=0.15 的平均額外 alpha 偏移約 0.000（95% 區間 -0.055 到 +0.055），contrast=0.30 為 +0.042（-0.028 到 +0.111）；平均偏移低於 0.144，但單次散布仍為 0.213/0.268。詳見 `docs/planning/ASSESSMENT_MASS_DEPENDENT_FBIN_MATCHED_FAST_2026-08-22.md`。 | 已完成中成本 gate；正式七參數驗證仍值得跑，優先 contrast=0 與 0.30；不取代 `mass-dep-fbin` 分支 |
| `d12_hr23_recall_stage_trace`（D12） | 2026-08-22 Codex 完成：HR23 P≥0.7 的 529 顆中，433 顆進 CMD、62 顆 baseline P≥0.7 但未進 CMD、34 顆不在 baseline（全為 G≥18）、0 顆因 baseline P<0.7 離開。G=16–18 的後段流失為 45/219（20.5%）。詳見 `docs/planning/M45_HR23_RECALL_STAGE_TRACE_2026-08-22.md`。只追蹤保存檔，未重跑 membership/IMF。 | 已完成定位；精確分解 62 顆的測光品質切割需原始 Gaia 表或小量欄位查詢，目前阻塞 |
| `d12_hr23_lost_quality_fields`（D12） | 2026-08-22 Codex 完成：只查詢已定位的 62 個 Gaia DR3 source_id，依現行 step2 順序重播後，1 顆敗在 G<4、37 顆敗在 BP SNR<20、2 顆敗在 RP SNR<20、22 顆敗在 BP/RP excess 3σ；0 顆原因不明。G=16–18 的 45 顆中 35 顆首先敗在 BP SNR。詳見 `docs/planning/M45_HR23_LOST_QUALITY_REPLAY_2026-08-22.md`。 | 已完成根因分解；下一步若做門檻敏感度，只先檢查品質與回收數，不直接重跑／解讀 IMF |
| `d12_hr23_quality_threshold_sweep`（D12） | 2026-08-22 Codex 完成：候選限定 smoking test。現行 BP20/3σ 回收 0/62；BP15/3σ 回收 16（全為 G=16–18，BP 誤差最大 0.072 mag）；BP10/3σ 回收 24；BP20/5σ 只回收 5。詳見 `docs/planning/M45_HR23_QUALITY_THRESHOLD_SWEEP_2026-08-22.md`。 | 已完成候選篩檢；若要測 BP15/3σ，必須先在完整輸入與控制場重建 selection 並通過暗端紅藍驗證，不能直接重跑／解讀 IMF |
| `d12_bp15_colour_error_gate`（D12） | 2026-08-22 Codex 完成：BP15/3σ 找回的 16 顆 HR23 候選星，BP−RP 顏色誤差中位數 0.062 mag；現有 CMD 同為 G=16–18 的 459 顆是 0.025 mag，候選星約大 2.48 倍。詳見 `docs/planning/M45_BP15_COLOUR_ERROR_GATE_2026-08-22.md`。 | 已完成候選品質 gate；BP15 只能保留為 selection 重建候選，須先量化完整場／控制場污染並通過 G≥17 紅藍驗證，不直接重跑 IMF |
| `d12_bp15_candidate_cmd_sides`（D12） | 2026-08-22 Codex 完成：16 顆 BP15 候選中，10 顆在同 G 局部 CMD 中位數紅側、6 顆在藍側；4 顆達局部最紅 10%、3 顆達最藍 10%，顯示兩側都有尾端，不能只驗證整體回收。詳見 `docs/planning/M45_BP15_CANDIDATE_CMD_SIDES_2026-08-22.md`。 | 已完成候選紅藍篩檢；正式 selection 重建必須預先分開檢查 G≥17 紅／藍，任一側失敗即停止，不重跑 IMF |
| `d12_bp15_candidate_mass_location`（D12） | 2026-08-22 Codex 完成：用已保存 Step 5 的逐星 G−mass 映射近似定位，16 顆 BP15 候選全低於 0.30 M☉（中位 0.173、範圍 0.161–0.219），0 顆進入 alpha 控制的 >0.5 M☉ 段。詳見 `docs/planning/M45_BP15_CANDIDATE_MASS_LOCATION_2026-08-22.md`。 | 已完成質量段 gate；主要價值是低質量完整性／nuisance 測試，不能說對 alpha 完全無影響，仍須 selection 紅藍驗證後才做前向 smoke |
| `d12_bp15_sample_scale`（D12） | 2026-08-22 Codex 完成：若 16 顆候選全被接受，整體 CMD 樣本增加 1.48%、<0.3 M☉ 樣本增加 4.32%、G=16–18 增加 3.49%，>0.5 M☉ alpha 段直接增加 0 顆。詳見 `docs/planning/M45_BP15_SAMPLE_SCALE_2026-08-22.md`。 | 已完成規模 gate；足以支持 selection smoke，但這是假設性上限記帳，未含新增背景污染，不能直接當完整度或 IMF 結論 |
| `d12_bp15_selection_input_restore`（D12） | 2026-08-22 Codex 完成：新增有 TOP 20000 截斷防護的公開 ARI Gaia TAP 查詢，使用專案既有 CDS Sesame 中心取得 M45 5°、G≤18、parallax≥4 mas 的 6,956 列原始場；修正 `build_selection.py` 已移動模組的匯入路徑。詳見 `docs/planning/M45_BP15_SELECTION_INPUT_READY_2026-08-22.md`。 | 原始輸入已恢復；CSV 依 gitignore 不上傳但可重建。下一步建立獨立 BP15 smoke selection，不能覆寫正式 BP20 `data/selection.npz` |
| `d12_bp15_selection_smoke`（D12） | 2026-08-22 Codex 完成：用修正後 6,956 列完整場建立獨立 BP15 selection；整體差 +0.0163、最差星等箱 +0.0451、G≥17 紅藍對比誤差 +0.0846，三項都通過但整體與紅藍餘裕偏小。BP15 相對現有 CMD 淨增 58 顆，現有 1,078 顆零遺失。詳見 `docs/planning/M45_BP15_SELECTION_SMOKE_2026-08-22.md`。 | 低餘裕通過，只解鎖一次 diagnostic 前向 smoke；正式 BP20 不覆寫。若參數貼邊、seed 不一致或 alpha 位移達統計誤差量級即停止 |
| `stick_out_fraction_constraint`（D13，成本高，建議先評估） | 這個任務會牽動 `pipeline/joint_fit.py` 核心概似函數，不建議直接動手改——先寫一份成本評估（要新增什麼似然項、`f_bin` 與 alpha 的簡併目前實際有多嚴重、值不值得為了這個投入架構層級改動），放進 `docs/planning/` 討論後再決定要不要真的做 | 有一份明確的成本/效益評估文件，使用者或後續 session 能據此決定要不要排進時程 |

**另外**：`WORK_BOARD.md` 前面「PDMF → IMF 第 5 步（N-body）」條目的做法設想（目前偏向「直接模擬＋等第 2 步結果再定初始條件」）建議加入 **Hobart et al. 2026 的模擬器路線**當優先評估的候選方案——用中等規模的 N-body 模擬網格（不需要到他們的 550–942 次，先抓幾十到百來次評估可行性）訓練一個機器學習模擬器（Python 生態可用 `scikit-learn` 的 `GaussianProcessRegressor`，或找 `AUTOEMULATE`（Stoffel et al. 2025）本身是否能裝），再用既有的 `emcee` 或改用 HMC 套件（如 `numpyro`）抽初始條件的後驗分布，取代暴力網格搜尋（他們自己算過暴力法對這個維度的參數空間要一個世紀）。這個做法概念上適合我們的算力限制（單台 ARM64 8 核桌機），但實際可行性（訓練資料要多少組模擬才夠、模擬器預測誤差多大）還沒驗證過，先當第 5 步「正式跑」設想中優先評估的候選方案，不是已確定要採用的定論，也不是另開新工作項，是補充第 5 步原本「正式模擬」規劃的一個選項。

## 待認領工作：多星團校驗軸 A＋B（2026-08-20 使用者定案，完整背景見 `PLAN_多星團擴展.md` 第十二節）

**執行順序有硬相依**：`praesepe_pr11_close_out` 是整條線的第一張骨牌
——D8 那 4 個正確性問題的修法目前只存在於 PR #11 分支、不在 `main`。
在它合併之前，任何要真的呼叫共用 pipeline 的工作（Praesepe、Coma Ber
的 Tier 執行）**都不能用 `main`**，必須照 Coma Ber 條目 2026-08-20
那段的規定明確 pin 住 PR #11 的 commit 並在產出裡記錄用的是哪個
commit。`crosscal_massrange_table` 與 `hyades_literature_check` 不碰
共用程式碼、也幾乎不吃算力，可以立刻平行做。

**算力歸屬**：沿用 2026-08-19 那條指示（本機 x64 8 核桌機的
`queue.txt` 留給既有排隊項目），下面需要跑 pipeline 的兩項請排到
其他機器（x64 協作機、Kaggle、或雲算力）。這是延續前一輪的假設，
使用者若要改回本機跑可以直接推翻這條。

| 任務 | 對應 | 起手式 | 驗收標準 |
|---|---|---|---|
| `crosscal_massrange_table`（選項 A，可立刻開始，幾乎不吃算力） | D11 相關、`PLAN_文獻對照_Hobart2026.md` 第五節 | 已有 `scripts/diagnostics/check_massrange_crosscal.py` 做完質量範圍換算（結果見第十二節 12.6）。**剩下的是原文口徑核對**：讀 Pang et al. (2024) 原文，查出他們 M45 那筆 α=2.01±0.09 的擬合質量範圍、MF 定義（`dN/dm` 或 `dN/dlog m`）、雙星處理、估計器、完整度修正，比照本專案對 Tang et al. (2019) 做過的那張表逐欄填 | 交出一張「同一顆 M45、Pang+2024／本專案／Hobart+2026 三方」的口徑對照表，每一欄都標明是查證過還是推測；並明確回答「換算到同一質量範圍後，三方還剩多少差距、那些差距各自對應哪個方法論選擇」。**若查出 Pang 的質量範圍跟 0.30–2.50 差很多，12.6 那個「大幅收斂」的初步判讀要回頭訂正，不是既定結論** |
| `praesepe_pr11_close_out`（選項 B 的第一張骨牌，**其餘兩項星團工作的前置條件**） | D8、A5 | 審查 PR #11（`codex/ngc3532-praesepe-generalization`）目前分支內容，確認 D8 那 4 點的既有修法真的有效（不是只看程式碼，要實際重跑 Praesepe 的 Tier1＋Tier2 驗證），然後合併。注意 PR #11 同時含 NGC 3532，本輪只需要 Praesepe 的部分正確，NGC 3532 可以標記為未驗證但不阻擋合併 | PR #11 合併，且 D8 在 `LIMITATIONS.md` 標記解決（含重跑證據，不是只有程式碼查證）；Praesepe 交出一組可引用的 Tier1／Tier2 數字，並跟 Hobart+2026（α_high PDMF 2.53）、Pang+2024（1.92±0.10）、Khalaj & Baumgardt (2013) 做過口徑對照——**口徑對照是驗收標準的一部分，不是選配** |
| `comaber_tier1`（選項 B，已有獨立條目） | A5、D8 | 見下方「待認領工作：Coma Berenices（Melotte 111）Tier 1 起步」條目的完整起手式，本表不重複。可在 PR #11 合併前起跑，但必須 pin 住 PR #11 的 commit（見該條目 2026-08-20 那段），不能用 `main` | 見該條目 |
| `hyades_literature_check`（選項 B 的候選評估，**只查文獻不執行 pipeline**，可立刻開始） | A5 | 使用者明確指示 Hyades「先查文獻確認」再決定要不要排執行。要查的最少項目：(1) 年齡與其定年法（是否有 LDB 等較模型獨立的量測）；(2) **金屬量與出處**——本專案候選表這一欄目前是「未查」，而第十二節 12.3 的兩個 Hyades 情境用的是假設值不是採用值；(3) 既有 PDMF／MF 測定與其口徑（質量範圍、雙星處理）；(4) Hyades 距離最近（~47 pc）帶來的特殊問題（角展開極大、成員判定與選擇函數是否還適用本專案現有流程） | 交出一份跟第五節候選表同格式的 Hyades 資料列（每格標明出處與是否查證），外加一段明確建議：**排執行 or 不排**，附理由。若建議排執行，要說明它在 M45＋Praesepe＋Coma Ber 之外多帶來什麼（第十二節 12.3 顯示它主要是把殘差自由度從 0 變成 1，金屬量跨度幾乎沒變） |

## 待認領工作：Coma Berenices（Melotte 111）Tier 1 起步（2026-08-19，見 `docs/planning/PLAN_多星團擴展.md` 第五、七節、`docs/planning/PDMF_TO_IMF_PLAN.md` 第八節分層協定）

**背景**：`PLAN_多星團擴展.md` 已把 Coma Ber 列為候選星團（動機一：第三個老年齡星團對照；動機二：金屬量接近太陽），但尚未實際起跑。核對 Hobart et al. 2026 時發現這篇論文的引言直接點名 Coma Ber 是「老年齡疏散星團次太陽質量段變平」的代表案例（引用 Kraus & Hillenbrand 2007、Tang et al. 2019），這兩篇文獻值得當作 Coma Ber 的既有 PDMF 基準線（比照 `PDMF_TO_IMF_PLAN.md` 第一步「文獻基準線」的做法）。**這項工作本次核對只做到規劃，沒有實際查詢 HR23 目錄或跑任何 pipeline**，交給認領的 session 執行。

**前置阻擋條件（2026-08-20 收斂成一項待辦，實際可否起跑以下方同日期
「起手式可以開始」那段為準）**：原本這裡寫「4 個問題各自獨立認領、
修好、補回歸測試」；2026-08-20 查證發現 Codex 已在 PR #11 分支上為這
4 點各寫好對應修法，所以**要做的事收斂成一項：完成
`praesepe_pr11_close_out`（見上一個表）——重跑驗證那些修法有效、
合併 PR #11、D8 在 `LIMITATIONS.md` 標記解決**。在 PR #11 合併之前，
Coma Ber 若要先起跑，必須照下方那段的規定明確 pin 住 PR #11 的
commit，不能用 `main`。

`LIMITATIONS.md` D8 記錄的 4 個 PR #11 已知正確性問題（`allow_wall` 貼牆
偵測被關掉、選擇函數驗證漏掉紅藍分色檢查、SNR 迴歸沒有獨立場星樣本、
`--refresh` 遇 NSS 為 null 會崩潰）**在 D8 標記解決之前，不要用 `main`
跑 Coma Ber 的 Tier 1**——這四個問題都在共用
的 pipeline 程式碼（`cluster_imf_tier1.py`／`prepare_cluster_tier2.py`／
`cluster_forward_validation.py`）裡，若邊跑 Coma Ber 邊修，之後沒辦法
可靠判斷 Coma Ber 的結果差異是星團本身的物理差異，還是同一輪意外
夾帶的程式修正造成的，會污染可追溯性。

**2026-08-20 更新：起手式可以開始，但前置條件不算「已解決」**——查證
PR #11 分支（`codex/ngc3532-praesepe-generalization`）目前內容，發現 Codex
已針對 D8 四項各自寫了對應的程式碼修法（只是讀程式碼查證，沒有重新動手改，
也沒有重跑資料驗證），詳見 `LIMITATIONS.md` D8 同日期段落——**D8 仍標記為
現役缺陷，要等 PR #11 合併並實際重跑 Tier 1 確認數值結果後才能結案**。
`main` 目前不含這四項修法，**任何要跑 Tier 1（含只是 HR23 目錄查證以外、
真的呼叫 `cluster_forward_validation.py`／`prepare_cluster_tier2.py`／
`cluster_imf_tier1.py` 的步驟）都必須明確 checkout commit
`c631e733de40b7c9110e9c00eab1c8b39b53821a` 或保留這四項修法的後代 commit**，
不能直接用 `main`，且要在產出的結果檔／PR 說明裡記錄實際用的 commit。
PR #11 合併後要回頭重新核對 D8、重跑一次驗證確認數值結果，才能把 D8
標記改為已解決。

**起手式**：
0. 開始前先在 `WORK_BOARD.md` 加一行「進行中」認領，避免跟其他
   session／協作者重工——這是第一步，不是最後一步。
1. 確認要用的程式碼版本含 D8 四項修法，**兩條路擇一，不要用 `main`**
   （2026-08-20 訂正：判準只看 PR #11 有沒有合併，不看 D8 有沒有在
   `LIMITATIONS.md` 標記解決——D8 的結案狀態是「真實資料重跑驗證完成」
   的記錄，不是版本選擇的閘門，原本寫成「且」會讓「PR #11 已合併但
   D8 因為還沒重跑驗證而未結案」這個中間狀態卡住、兩條路都不成立，
   CodeRabbit PR #81 review 抓到）：(a) PR #11 已合併 → 直接用合併後的
   `main`，並在產出裡記錄實際用的 commit；(b) PR #11 還沒合併（目前
   狀態）→ 明確 checkout `c631e733de40b7c9110e9c00eab1c8b39b53821a`
   或保留那四項修法的後代 commit，並在產出的結果檔／PR 說明裡記錄
   實際用的 commit。**D8 沒結案本身不阻擋起跑**，只要走 (a) 或 (b)
   之一並記錄清楚即可（見上方 2026-08-20 那段）。
2. 讀 `PDMF_TO_IMF_PLAN.md` 第八節的 Tier1/Tier2 分層協定，Coma Ber（~600–800 Myr）的動力學年齡大機率會觸發 Tier 2（需要動力學校正），起跑前先照第六節公式粗算一次 τ = age / t_rh 確認。
3. 查證 Coma Ber 在 `Hunt & Reffert (2023)` 目錄裡的對應名稱與成員表品質（`PLAN_多星團擴展.md` 第六節的「應該可行但沒驗證過」假設，這是第一個要驗證的環節）。
4. 讀 Kraus & Hillenbrand (2007)、Tang et al. (2019) 兩篇原文（不只摘要），把它們報告的 PDMF 斜率、質量範圍記下來當基準線對照。**Tang et al. (2019, ApJ 877, 12) 已於 2026-08-19 讀原文完成口徑核對，結果見 `PLAN_文獻對照_Hobart2026.md` 第五節與 `PLAN_多星團擴展.md` 對應段落，不用重讀**——結論是他們的 α=0.79±0.16（0.25–2.51 M☉）不能直接跟我們的 headline alpha 比較（樣本含潮汐尾、未做聯星修正），需要重算子樣本或用未修正版本對照。**Kraus & Hillenbrand (2007) 還沒查證**：2026-08-19 收到的 PDF 抓錯論文（使用者給的是同作者同年份的 *ApJ* 662, 413，跟 Coma Ber 無關），Hobart et al. 2026 實際引用的是 ***The Astronomical Journal*, 134, 2340**，需要使用者重新提供正確那篇才能完成這半邊查證，目前只有 Tang 原文轉述的二手數字（α=0.6±0.3，0.1–1.0 M☉）可用，不能當已核對口徑的基準線引用。
5. 仿 `scripts/multicluster/cluster_imf_tier1.py`（NGC 3532／Praesepe 已用過的同一套腳本）跑 Tier 1（誤差核算框架 + 動力學年齡 + 徑向 α(r) 診斷）——用第 1 步選定的那個 commit，D8 四項修法已含在內，不需要再順手處理。

**驗收標準**：Coma Ber 交出跟 `PDMF_TO_IMF_PLAN.md` 第八節表格同樣結構的誤差預算表（原始 PDMF±統計誤差、動力學校正項或上限估計、其餘系統誤差），且頭條 alpha 與 Kraus & Hillenbrand (2007)／Tang et al. (2019) 的既有測定值做過對照。**對照前必須先讀這兩篇原文，逐項列出下面這些欄位、雙方（我們 vs 各篇文獻）分別是什麼，口徑不同就要先在同一個質量範圍/樣本定義下重新對齊才能比較 alpha，不能直接拿不同口徑的數字並排**：
  - MF／PDMF 的確切定義（system MF 還是 stellar MF，見 D14）——Hobart et al. 2026 分別報告兩種，只對齊質量範圍/樣本不足以保證是同一個量
  - 擬合/報告用的質量範圍（M☉ 上下限）
  - 成員樣本定義與空間涵蓋範圍（搜尋半徑、是否含潮汐尾／外圍結構）
  - 完整度修正方式（有沒有做、怎麼做）
  - 聯星處理方式（有沒有修正、修正法）
  - MF 的數學定義（`dN/dm` 還是 `dN/dlog m`）與 alpha 的正負號慣例
  - 分箱方式（分箱數／對數等寬度等）、擬合函數形式、估計器（MLE／貝氏／最小平方等）、不確定度的定義（1σ 信賴區間怎麼算出來的）

一致或不一致都要交代量級與可能原因，不是只列數字不解讀。
