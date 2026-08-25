# 工作認領表（誰現在在做什麼、還剩什麼沒做）

`CONTRIBUTING.md` 管「怎麼合併」，這份管開始做之前先看這裡，避免兩個人／
兩個 agent 同時做同一件事。這份只放正在執行或還沒執行的工作；已經
達成、結案的事搬到 `WORK_BOARD_DONE.md`（完整規則見 `CONTRIBUTING.md`
零之四）。

## 規則

1. 開始任何預期要花超過一次對話（或會碰共用檔案：`pipeline/`、
   `injection_recovery.py`、`LIMITATIONS.md`、`PAPER_OUTLINE.md`、
   `queue.txt`）的工作之前，先讀完下面的表格，確認沒有人已經在做
   同一件事或高度重疊的事。
2. 開始工作時，把對應行的狀態改成「進行中」，補上開始日期，並在
   下方說明文字的第一句寫明認領人是誰（人類協作者姓名、或哪一種
   agent／哪一台機器）——表格本身沒有獨立的認領人欄位，這句話是
   唯一能讓其他人知道「該去問誰」的地方，漏寫等於規則 1 要求的
   查重無法真的落實。放棄或暫停時改回「尚未進行」並在說明文字補一句
   原因。真的做完時，照 `CONTRIBUTING.md` 零之四把整行連同說明文字
   搬到 `WORK_BOARD_DONE.md`，這裡刪掉——不要用刪除線或「已完成」
   字樣蓋在原本的行上，那樣會讓同一件事的新舊說明混在同一格裡，越堆
   越難讀。要查某任務目前狀態，先看它還在不在這份文件裡；不在了就
   代表已完成，去 `WORK_BOARD_DONE.md` 找完整記錄。
3. 看不出算不算重複、範圍該怎麼分——不要用猜的、也不要因為怕衝突
   就不寫：在說明文字裡寫清楚困惑點，讓開這個任務的人或使用者看到
   後決定怎麼分工。
4. 誰都可以編輯這份文件（人類協作者、Claude、Codex、其他 agent）。
5. 任務名稱後面的括號標對應的 `LIMITATIONS.md` 條目（例如 A1），跟
   `LIMITATIONS.md` 互相參照，完整規則見 `CONTRIBUTING.md` 五之一。
   跟限制清單無關的工作（環境設定、文件整理）不用標。

## 現況說明（不是工作項目，是基礎設施狀態）

**2026-08-23 起使用者決定：本機不再跑計算，全部排到雲端**——
`restart_queue_on_boot.ps1` 已經改成不再自動重啟 `run_queue.py`
（見 PR #116），`queue.txt` 裡剩的待辦項目要排新工作一律改進
`cloud_queue.txt`，不要再假設本機佇列會撿去跑。目前算力池只剩兩個：
Kaggle 多帳號（`kaggle_queue.txt`）與 GCP SSH worker `gcp1`
（`cloud_queue.txt`／`cloud_queue.py`），排新工作前先確認同一件事
沒有同時排在另一個佇列檔裡。

**gcp1 的排隊/監控機制**：`cloud_queue.py` 每輪（預設 60 秒）自動從
`origin/main` 同步 `cloud_queue.txt`，隊員／agent 只要開 PR 加一行
工作、合併，不用碰真實憑證也不用重啟這支程式，見該檔案開頭說明。
`restart_queue_on_boot.ps1`（登入時觸發）＋`M45-QueueWatchdog-15min`
（每 15 分鐘一次）負責偵測到它沒在跑就自動重啟；若某次巡檢發現排程
任務不存在了，重新註冊即可，指令見該腳本開頭註解。

**已知的閒置風險，2026-08-25 實際發生過一次**：D2 敏感度掃描兩批
（`d2_membership_threshold_p06_p07_retry`、`d2_membership_threshold_p05_p08_p09`）
都已經在 gcp1 跑完，但沒有自動合併進 `results/`／提交，也沒有人主動
巡檢，gcp1 因此空等了約 3 小時才被發現、沒有下一項工作可接。**使用者
因此要求：cloud_queue.txt 隨時要有足夠的排隊工作，避免 gcp1 空等；
且要有主動巡檢機制，不能只靠人偶然想起來查**——目前排隊工作見下方
表格，主動巡檢由負責的 Claude session 用排程喚醒定期查
`logs/cloud_queue_done.txt`／`results/` 目錄實際內容（不要假設派工
就等於成功，之前兩次都是看起來已派工但實際沒跑起來，是新 worker
缺本機專屬資料造成的，這個坑以後可能在別的資料檔或依賴上重演）。

**2026-08-25 順帶修好一個一直沒被跑過所以沒人發現的 bug**：
`inject_massdep_fbin.py` 對 `inject_lowmass.py` 匯入一個已經不存在
的 `atomic_savez`（2026-08-20 已收斂進 `scripts/tools/checkpoint.py`
共用版本，這支腳本沒有跟著改），import 階段就會直接炸掉——排進
`cloud_queue.txt` 前 dry-run 才踩到，已修好並驗證過真的能跑到擬合
階段。

## 待辦事項

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| p6_lowmass_v3（A1、A3） | 尚未進行 | 指派時間：2026-08-21 | profile_lowmass.py --procs 8 --n-syn 40000 --repeats 3 --refines 3,3 | results/profile_lowmass.npz |
| p6b_inject_lowmass_v2（A1） | 尚未進行 | 指派時間：2026-08-12 | inject_lowmass.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3 | results/inject_lowmass.npz |
| limepy_radial_crosscheck（A5、B5） | 尚未進行 | 指派時間：2026-08-13 | results/limepy_multimass.npz、results/fit_real_radial_r1_final.npz、results/fit_real_radial_r2_final.npz、results/fit_real_radial_r3_final.npz、results/fit_real_radial_rall_final.npz | results/limepy_radial_crosscheck.json（規劃中的檔名，腳本尚未寫） |
| nbody_prior_from_radial（A5） | 尚未進行 | 指派時間：2026-08-12 | mcluster_sse -N 400 -S 0.3/0.5/0.7（各跑數組，圍繞 pilot 參數 -P 0 -R 2.3 -Q 0.5 擾動） | nbody_setup/ 下的模擬網格輸出（檔名依 nbody_setup/README.md 命名慣例，尚未產生） |
| pdmf_step4_radius_expansion（A5） | 尚未進行 | 指派時間：2026-08-12 | config.toml [target] radius_deg 改為 8–17°；scripts/data_prep/fetch_gaia.py → scripts/drivers/run_pipeline.py 第 1–5 步 | 新的 data/cmd_members.csv 與 results/ 下對應的第 1–5 步輸出（含 pyUPMASK 六格驗證圖） |
| bhac15_isochrone_test（C1、D1） | 尚未進行 | 指派時間：2026-08-16 | fit_real.py --grid bhac15_gaia_logt7.6-8.4.dat --procs 8 --n-syn 40000 --repeats 5 --configs A,C | results/fit_real_bhac.npz（規劃中的檔名，比照 fit_real_dr2.npz 命名慣例） |
| stars_per_cluster_sensitivity（D2） | 尚未進行 | 指派時間：2026-08-25 | scripts/diagnostics/sensitivity_sweep.py --target stars_per_cluster（需要 pyUPMASK/ 環境，這台機器沒有） | 可行性查證結果（若這台機器沒環境，誠實回報做不到，不編造數字）；有環境的機器才能真的量出敏感度數字 |
| extinction_form_test（C5，現役缺陷．優先度高） | 尚未進行 | 指派時間：2026-08-13 | injection_recovery.py --dav-distribution lognormal／truncexp（queue.txt 標籤 c5_davform_lognormal、c5_davform_truncexp） | results/injection_recovery_davform_lognormal.npz、results/injection_recovery_davform_truncexp.npz（規劃中的檔名） |
| pyupmask_completeness_test（C8） | 尚未進行 | 指派時間：2026-08-13 | 尚無腳本；輸入是原始 Gaia 座標範圍內的合成注入星＋真實場星資料 | 尚無腳本；規劃輸出是完整度隨半徑/星等分箱的曲線檔 |
| extra_scatter_sensitivity（C19） | 尚未進行 | 指派時間：2026-08-13 | injection_recovery.py（queue.txt 標籤 c19_extra_scatter_sweep，散布量級參數見 queue.txt 該行） | results/injection_recovery_extra_scatter.npz（規劃中的檔名） |
| configCD_real_data_compare（D10） | 尚未進行 | 指派時間：2026-08-16 | fit_real.py --configs C,D --repeats 5（--repeats 比照既有頭條設定） | results/fit_real_configCD_compare.npz（規劃中的檔名） |
| empirical_ml_relation_test（D11，現役缺陷．優先度中高） | 尚未進行 | 指派時間：2026-08-19 | docs/planning/PLAN_D11_經驗質光關係_可行性評估.md 第三節五項查證（尚未開始） | 五項查證的查證結果（文件更新，尚無獨立輸出檔） |
| mass_dependent_fbin（D14 衍生） | 尚未進行 | 指派時間：2026-08-19 | inject_massdep_fbin.py --contrast 0.0,0.15,0.30（queue.txt 標籤 massdep_fbin） | results/inject_massdep_fbin.npz（規劃中的檔名） |
| praesepe_pr11_close_out（D8、A5） | 尚未進行 | 指派時間：2026-08-20 | PR #11（分支 codex/ngc3532-praesepe-generalization） | PR #11 合併紀錄；Praesepe Tier1／Tier2 結果檔（沿用 cluster_imf_tier1.py／prepare_cluster_tier2.py 既有輸出命名） |
| comaber_tier1（A5、D8） | 尚未進行 | 指派時間：2026-08-19 | cluster_imf_tier1.py（Coma Berenices，checkout commit c631e733de40b7c9110e9c00eab1c8b39b53821a 或其後代 commit） | Coma Berenices 的 Tier1 結果檔（沿用 cluster_imf_tier1.py 既有輸出命名，星團名稱換成 Coma Ber） |
| bp15_bp20_paired_comparison（D12） | 尚未進行 | 指派時間：2026-08-23 | scripts/diagnostics/prepare_bp15_paired_dispatch.py 產生的 offsets 0–4、10 個 job tag（40k、至少 5 個 paired seeds） | scripts/diagnostics/summarize_bp15_formal_paired.py 的彙整輸出 |

## 待辦事項說明

以下逐項說明每個任務具體要解決什麼問題、用什麼方法、目前卡在哪裡；
預計耗時只在有實測依據時才寫具體數字，查不到依據的一律寫「未查證」，
不用感覺湊一個數字。

p6_lowmass_v3：量低質量段冪次 d(alpha)/d(p) 的斜率，這是目前最大
的單一系統誤差來源（0.248，見 LIMITATIONS.md A3）。原本記錄的單次
耗時 18.7 小時無法從本機 log 佐證（log 只有 7 行、沒有任何完成時間戳，
且檔案時間早於宣稱的啟動時間），已訂正為不可信；唯一可查證的成本
量級是規模本身（15 次擬合，全樣本 1,078 顆），對照同量級的
radial_r1_final（5 次重複、355 顆核心切片、實測 72,814 秒即約 4 小時
一次）推算，全樣本單次耗時只會更長，15 次總量級會長期擋住本機循序
佇列，這是使用者已經決定移到佇列最後（選項 C）的原因。跑之前必須
先手動把 results/profile_lowmass.npz（2026-08-15 的舊檔、無 manifest、
未精修）移開，不要指望程式自動擋下來。

p6b_inject_lowmass_v2：驗證低質量段冪次的可辨識性——這個數字
決定要不要把它升格成自由參數。舊結果（p_recovered/p_true 比值 0.92）
是修好 multi_stage_best() 精修 bug 之前跑的，完全沒精修，數字不可信。
Kaggle 上同類工作曾多次重派，但沒有找到明確的完成結論，認領前務必
先查 results/ 與 RESULTS_LOG.md 確認是否已經有可用結果，避免重工。
耗時未查證。

limepy_radial_crosscheck：LIMEPY 多質量平衡模型本身已經擬合完成
（phi0=3.44、r0=2.50 pc），這是第 3 步唯一剩下的驗收動作——把模型
預測的 α(<r) 拿去跟觀測值比對。觀測端的有誤差棒版本（radial_final_reruns）
已於 2026-08-23 全部到齊，不用再等，現在就可以做。耗時未查證，是
純比對計算，不涉及重新跑合成星團，預期是輕量級工作。

nbody_prior_from_radial：N-body 模擬（第 5 步）的初步校準方向，
不是正式版本。前置的三個定義不一致（分箱方式、半徑維度、質量範圍
與估計量）已經解決並寫進 analyze_alpha_r.py，下一步是真正跑一組
圍繞 pilot 參數小幅擾動的模擬網格。pilot 本身（400 顆星、單次）
耗時約需查 nbody_setup/ 下的紀錄，本表未附具體秒數；正式網格是
3–5 組小規模模擬，還不是文獻建議的 550–942 次全網格。

pdmf_step4_radius_expansion：PDMF→IMF 第 4 步，觀測上唯一能給出
「5 度搜尋半徑夠不夠」決定性答案的路線，但成本最高。原本要等
radial_final_reruns 全部到齊才能判斷第二層門檻（梯度統計上是否為真）
是否滿足——這個前提已於 2026-08-23 滿足（r1/r2/r3/rall 全部到齊，
見 LIMITATIONS.md A5），但目前還沒有人依這個結果重新評估是否投入
第 4 步，這一步的「要不要做」判斷本身也還沒有人做。耗時未查證，
涉及整條 pipeline（fetch_gaia.py 到 run_pipeline.py 第 1–5 步）
重跑，且需要重建大半徑下的 pyUPMASK 成員判定與選擇函數，預期是
重量級工作。

bhac15_isochrone_test：BHAC15 等時線的網格轉換與涵蓋範圍確認
已經完成（bhac15_gaia_logt7.6-8.4.dat，170 列、6 個年齡格點），
唯一剩下的是真正跑一次 fit_real.py 拿這個網格算模型效應分解，
跟已有的三個等時線版本（PARSEC-EDR3／PARSEC-DR2／MIST-DR2）放進
同一張比較表。BHAC15 只涵蓋到 0.015–1.4 M_sun，不蓋過 M45 擬合
上限 2.50 M_sun，比較結果要誠實標注只驗證了低質量段。耗時未查證，
量級應與同類 fit_real.py 全量跑（--configs A,C --repeats 5）相當。

stars_per_cluster_sensitivity（D2）：認領人：無。D2 剩下的另一個掃描
目標——stars_per_cluster 需要真的重跑 pyUPMASK 聚類，不是像
membership_threshold 那樣重套門檻就好（membership_threshold 已於
2026-08-25 測完五點，見 WORK_BOARD_DONE.md）。這台機器沒有
pyUPMASK/ 環境，腳本（sensitivity_sweep.py --target
stars_per_cluster）會誠實回報做不到、不編造數字，留給有 pyUPMASK
環境的人或機器認領。D2 問題陳述裡列的其餘設定（pca_dims、
clustering_method、inner_loop_runs、hess_color_range／
hess_mag_range、min_flux_snr_bp）也都還沒做過敏感度測試，同樣
待認領，見 LIMITATIONS.md D2。

extinction_form_test：測消光分布形式（對數常態 vs 截尾指數）對
A_V 系統誤差有沒有影響，這是現役缺陷、優先度高（污染範圍已知，見
LIMITATIONS.md C5）。兩趟注入回收（c5_davform_lognormal／
c5_davform_truncexp，dav 掃到 1.20，比既有 item4_davsweep 的 0.60
更寬）已經寫進本機 queue.txt，但循序佇列還沒輪到，認領前先查
logs/queue_done.txt 確認進度。耗時未查證。

pyupmask_completeness_test：量 pyUPMASK 成員判定的完整度隨半徑
/星等的變化——目前只有一個全域完整度數字，沒有分箱曲線。做法是
在真實 Gaia 座標範圍內注入已知位置的合成成員星，混進真實場星資料
重跑 pyUPMASK，量召回率。這支測試腳本還沒寫，耗時未查證。

extra_scatter_sensitivity：量自轉調製／前主序光變／黑子等未
建模物理造成的額外亮度散布，對 alpha 有多敏感。已排進 queue.txt
（c19_extra_scatter_sweep），循序佇列還沒輪到，認領前先查
logs/queue_done.txt。耗時未查證。

configCD_real_data_compare：目前「alpha 不受 dav 貼牆位置污染」
只在注入回收的合成資料上驗證過，真實資料從沒直接比較過 config C
跟 D（兩者差別只有 dav 上界）。做法是用真實資料各跑一次，比較
alpha 中心值與統計誤差的差距是否遠小於合併標準誤。耗時未查證，
量級與同類 fit_real.py 全量跑相當。

empirical_ml_relation_test：建一條完全獨立於任何等時線模型的
經驗質量-光度關係，檢查低質量段 alpha 對「用不用等時線」本身敏不
敏感——這是現役缺陷、優先度中高（見 LIMITATIONS.md D11）。可行性
評估已經做完：質量精度以 Gaia G 為準時不是瓶頸，但正確的轉換導數
是 dM/dM_V 不是 dM/dG，本機網格沒有 V 波段算不出來；初步判讀紅端
顏色覆蓋可能是主要風險（要檢驗的樣本過半集中在 BP−RP ≥ 2.663）。
下一步是完成評估文件第三節的五項查證，優先做成本最低、可能直接
否決整條路線的前兩項，全過才能動手蒐集資料、寫實作。耗時未查證。

mass_dependent_fbin：雙星比例是否隨主星質量變化，目前模型假設
是常數，這是已知簡化但沒量化過代價。做法是用注入回收量化「質量
相依雙星比例」對 alpha 的偏移量，不直接升格成自由參數（dav 的教訓
是參數可以放進模型卻完全不被資料約束）。腳本 inject_massdep_fbin.py
已寫好並排進 queue.txt（massdep_fbin），contrast=0.0/0.15/0.30 三組
正式 sweep 目前都還沒跑，循序佇列還沒輪到。耗時未查證。

praesepe_pr11_close_out：整條多星團校驗軸（Praesepe、Coma Ber）
的第一張骨牌——D8 記錄的 4 個正確性問題（貼牆偵測被關掉、選擇函數
驗證漏掉紅藍分色檢查、SNR 迴歸沒有獨立場星樣本、--refresh 遇 NSS
為 null 會崩潰）的修法目前只存在於 PR #11 分支，還沒合併進 main。
需要實際重跑 Praesepe 的 Tier1＋Tier2 驗證確認修法有效（不能只看
程式碼），然後合併；NGC 3532 可以標記為未驗證但不阻擋合併。合併後
D8 才能在 LIMITATIONS.md 標記解決。耗時未查證。

comaber_tier1：Coma Berenices（老年齡、金屬量近太陽的疏散星團）
的 Tier1 起步，補齊多星團校驗軸。前置阻擋條件已收斂成一項：完成
praesepe_pr11_close_out。起手式可以先開始，但在 PR #11 合併之前
必須明確 checkout commit c631e733de40b7c9110e9c00eab1c8b39b53821a（或
保留那四項修法的後代 commit），不能直接用 main，且要在產出裡記錄
實際用的 commit。動手前要讀 Kraus & Hillenbrand (2007)、Tang et al.
(2019) 兩篇原文當基準線——Tang et al. 已核對完成（α=0.79±0.16，
0.25–2.51 M☉，不能直接跟本專案頭條 alpha 比較），Kraus & Hillenbrand
還沒查證（先前收到的 PDF 抓錯論文，需要使用者重新提供正確那篇：
The Astronomical Journal, 134, 2340）。耗時未查證。

**全部不在本機（x64 8 核桌機）跑**——本機佇列（`queue.txt`）留給
既有排隊項目，這幾項規模較大或需要不同架構／機器，請認領的人在
自己的機器（x64 協作機、Kaggle、或評估過的雲算力，見
[雲算力評估](https://claude.ai/code/artifact/8f3b0148-708e-4ddc-a10d-1870dc39ec83)）上跑，不要排進本機的 `queue.txt`。

| 任務 | 起手式 | 驗收標準 | 為什麼現在能做 |
|---|---|---|---|
| ~~`radial_final_reruns`（A5，最優先——下面兩項都依賴這個）~~ | **已完成，2026-08-23**：r1/r2/r3/rall 四組全部到齊有誤差棒（2.0644±0.1193／2.3889±0.0981／2.4244±0.0924／2.3844±0.0792），配對相減證實 alpha(<r) 在 0–2° 有顯著跳升（p=0.028）、2° 以外到 5° 邊緣無顯著變化（p=0.099、p=0.181），曲線約在 2° 收斂，完整推導見 `LIMITATIONS.md` A5。下方 `limepy_radial_crosscheck`、`nbody_prior_from_radial` 需要的「有誤差棒版本」現在都有了，不用再等 | — | — |
| `limepy_radial_crosscheck`（A5、B5，對應第 3 步驗收標準） | 讀 `scripts/diagnostics/limepy_multimass.py` 目前的模型輸出（`results/limepy_multimass.npz`），從擬合出的 King 模型（phi0=3.44、r0=2.50 pc）算出模型預測的 α(<r) 在 r1/r2/r3/rall 對應半徑處的值，跟觀測值（prelim：2.10/2.43/2.50/2.43；建議等 `radial_final_reruns` 的 `_final` 版本出來再做，用有誤差棒的版本比較才有意義）並排比較 | 給出模型預測 α(<r) 與觀測 α(<r) 的逐項對照表，量化兩者差距是否在統計誤差內；若明顯不符，要指出可能原因（King 模型是單一質量分層假設，跟真實分層可能不符） | LIMEPY 模型本身已經擬合完成（2026-08-13），只差這一步比對，是第 3 步唯一剩下的動作 |
| `nbody_prior_from_radial`（A5，第 5 步「初步校準」，不是正式版）**2026-08-20：前置的定義不一致已解決，見本列末段** | **開始前先解決一個真的定義不一致的問題**：`fit_real.py --radius-range LO,HI` 算出來的 `radial_r1/r2/r3/rall` 是**累積**α(<r)（0-1°、0-2°、0-3°、全樣本，一層包一層，不是互斥區間）；`nbody_setup/analyze_alpha_r.py` 卻是用 `np.percentile` 切三等分位算**互斥環帶**的 α（0-33%、33-66%、66-100%，各自獨立不重疊）。這兩種是不同的量，不能直接並排比較同一條「α(r)」曲線。**兩個修法選一個，校準目標各自對應，不要混用**：(1) 把 `analyze_alpha_r.py` 的模擬粒子改用累積半徑切法（比照 `radius-range` 的 0-1°/0-2°/0-3° 換算成 pc 後的累積邊界）重新分箱，這種做法的校準目標就是**現成的** `radial_r1/r2/r3/rall`（prelim 或 `_final`）α 值，不用另外算；(2) 把觀測資料也額外用互斥環帶（比照 `analyze_alpha_r.py` 的 percentile 切法）重新分箱一次算出**另一組獨立的**觀測 α，這種做法的校準目標是這組新算出來的環帶 α，**不是**現成的 `radial_r1/r2/r3/rall`（那是累積值，跟環帶模擬結果比會是選項 (1) 沒做完就混用了選項 (2) 的資料）。選定一種、備妥對應的目標值後，設計一組圍繞 pilot 參數（400 顆星、質量分層度 0.5、virial Q=0.5）小幅擾動的網格（例如質量分層度 0.3/0.5/0.7 各跑幾次） | 至少 3–5 組不同初始參數的模擬跑完，且**觀測與模擬用的是同一種半徑分箱定義（累積或互斥擇一，並在結果裡明確標注是哪一種）**，每組跟觀測 α 的擬合優度（例如簡單的殘差平方和）有量化比較，明確標注這是「用 prelim 值做的初步校準方向」不是正式最終校準 | 這是 Hobart et al. 2026 建議的「先用小規模模擬網格摸清方向」路線的起手式，不用等到有大量模擬（他們是 550–942 次）才能開始，先幾組摸清梯度方向即可。**2026-08-20 更新：前置的「定義不一致」已依修法 (1) 解決**（`nbody_setup/analyze_alpha_r.py` 已改成累積投影半徑切法，校準目標就是現成的 `radial_r1/r2/r3/rall`）。動手時發現不一致**不只分箱這一項，總共三項**，三項都已對齊：(1) 分箱：percentile 互斥環帶 -> 累積切法（邊界用觀測角度換算成 pc）；(2) **半徑維度**（本表原本沒寫到）：3D 團心距 -> 投影半徑，因為觀測只量得到投影距離，3D 半徑恆大於投影半徑、直接並排會系統性高估模擬的外圍距離，另加 `--n-projections` 可對多視線平均掉投影雜訊；(3) **質量範圍與估計量**（本表原本沒寫到，**這項最嚴重**）：舊版對 0.1–2.0 M☉ 做 MLE，但觀測端前向模型的 `alpha` **只控制 Kroupa 分段的 m>0.5 段**（m<0.5 固定 1.3），0.1–2.0 跨過 0.5 這個分段點等於把固定段跟要比較的段混在一起，**跟前向模型的 alpha 根本不是同一個量**，已改成 0.5–2.50（下界對齊分段點、上界對齊 `config.toml [step5_imf] mass_max`）。附了 `--self-test`（不需 PeTar 環境即可跑）驗證累積邏輯、投影半徑不大於 3D 半徑、alpha 回收真值，並內建貼牆檢查——第一版 self-test 的合成分層做得太極端，核心片直接撞到 `mle_powerlaw` 的 alpha 下界 0.1，方向斷言因為貼牆而假通過，已改成溫和的統計傾向並加上貼牆斷言攔截。**仍未對齊、改腳本解決不了的差異**：觀測端是前向模型擬合值（含聯星／選擇函數／測光誤差建模）、這裡是對模擬真實質量做直接 MLE，兩者不是同一個估計量，只能當趨勢方向對照；且觀測值仍是 `_prelim` 無誤差棒，`radial_final_reruns`（已排進 Kaggle 佇列 20 分片）跑完前無法判斷差異顯著性。**下一步**：實際跑那組質量分層度 0.3/0.5/0.7 的模擬網格 |
| `radial_final_reruns`（A5，最優先——下面兩項都依賴這個） | **2026-08-23 進度：r1／r3／rall 已 5/5 完成，r2 仍 2/5**（見 `LIMITATIONS.md` A5、`results/RESULTS_LOG.md`）。用完整設定補齊 r2：`fit_real.py --procs 8 --n-syn 40000 --repeats 5 --refines 3,3 --configs C --radius-range 0,2 --tag _radial_r2_final`（`--repeat-offset` 依現有進度接續，不要從 0 重算已完成的重複） | 四個 `_final` 版本都有統計誤差棒（不是單次無誤差棒），且要明確回答「r3(2.50) > rall(2.43) 這個非單調現象是真實訊號還是統計雜訊」——**這個子問題已用配對比較解決（跟雜訊一致，未能得到統計支持），見 `LIMITATIONS.md` A5**，剩下的是等 r2 到齊後看完整 α(<r) 曲線是否符合核心到外圍遞增的分層預期 | 下面 `limepy_radial_crosscheck` 與「決定要不要投入第 4 步」都需要有統計誤差棒的完整版本才能下結論 |
| `limepy_radial_crosscheck`（A5、B5，對應第 3 步驗收標準） | 讀 `scripts/diagnostics/limepy_multimass.py` 目前的模型輸出（`results/limepy_multimass.npz`），從擬合出的 King 模型（phi0=3.44、r0=2.50 pc）算出模型預測的 α(<r) 在 r1/r2/r3/rall 對應半徑處的值，跟觀測值並排比較——**建議等 `radial_final_reruns` 全部到齊後再做，用有誤差棒的版本比較才有意義** | 給出模型預測 α(<r) 與觀測 α(<r) 的逐項對照表，量化兩者差距是否在統計誤差內；若明顯不符，要指出可能原因（King 模型是單一質量分層假設，跟真實分層可能不符） | LIMEPY 模型本身已經擬合完成，只差這一步比對，是第 3 步唯一剩下的動作 |
| `nbody_prior_from_radial`（A5，第 5 步「初步校準」，不是正式版） | 前置的三個定義不一致（分箱、半徑維度、質量範圍與估計量）已解決，見 `LIMITATIONS.md` A5 與 `WORK_BOARD_DONE.md`。**下一步：實際跑一組質量分層度 0.3/0.5/0.7 的模擬網格**，圍繞 pilot 參數（400 顆星、質量分層度 0.5、virial Q=0.5）小幅擾動 | 至少 3–5 組不同初始參數的模擬跑完，且觀測與模擬用的是同一種半徑分箱定義（累積），每組跟觀測 α 的擬合優度有量化比較，明確標注這是「用 prelim 值做的初步校準方向」不是正式最終校準 | 這是 Hobart et al. 2026 建議的「先用小規模模擬網格摸清方向」路線的起手式，不用等到有大量模擬才能開始 |

**2026-08-24 附記（不改動上面既有的行，僅附加說明）**：上表 182–184
三行（`radial_final_reruns` 2/5 進度版、`limepy_radial_crosscheck`、
`nbody_prior_from_radial`）是合併衝突留下的**舊版重複內容**，寫於
r2 尚未補齊時；179–181 三行是同一批任務的**現行版本**，寫於 r2 已於
2026-08-23 補齊之後，內容以 179–181 為準。**另外，179 行「alpha(<r)
...統計顯著的跳升（p=0.028）」這個用詞需要訂正**：2026-08-24
CodeRabbit review 指出這是四個檢定共用同一個假說家族卻沒有做多重比較
校正——Holm 校正後 r2−r1 的 p 約 0.084–0.088，不再小於 0.05，是提示性
訊號，不是獨立確認的統計顯著結果。完整訂正見 `LIMITATIONS.md` A5
2026-08-24 段落與 `results/RESULTS_LOG.md` 同日期的訂正行。

**另外**：`WORK_BOARD.md` 前面「PDMF → IMF 第 5 步（N-body）」條目的做法設想（目前偏向「直接模擬＋等第 2 步結果再定初始條件」）建議加入 **Hobart et al. 2026 的模擬器路線**當優先評估的候選方案——用中等規模的 N-body 模擬網格（不需要到他們的 550–942 次，先抓幾十到百來次評估可行性）訓練一個機器學習模擬器（Python 生態可用 `scikit-learn` 的 `GaussianProcessRegressor`，或找 `AUTOEMULATE`（Stoffel et al. 2025）本身是否能裝），再用既有的 `emcee` 或改用 HMC 套件（如 `numpyro`）抽初始條件的後驗分布，取代暴力網格搜尋（他們自己算過暴力法對這個維度的參數空間要一個世紀）。這個做法概念上適合我們的算力限制（單台 x64 8 核桌機），但實際可行性（訓練資料要多少組模擬才夠、模擬器預測誤差多大）還沒驗證過，先當第 5 步「正式跑」設想中優先評估的候選方案，不是已確定要採用的定論，也不是另開新工作項，是補充第 5 步原本「正式模擬」規劃的一個選項。

## 待認領工作：B/C/D 類補齊（2026-08-13，見 `WORK_BOARD_DONE.md` 對應紀錄）

**已完成的項目**（`p6b4_boundary_retest`、`injection_bias_floor_recheck`、
`stick_out_fraction_constraint`）已搬到 `WORK_BOARD_DONE.md`，以下是
還開放的：

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| `bhac15_isochrone_test`（C1、D1） | 官方資料來源是 <https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/>，網格建置已完成（見 `WORK_BOARD_DONE.md` 2026-08-18 那行：`build_bhac_grid.py`、`bhac15_gaia_logt7.6-8.4.dat`）。**剩下的是真正跑一次 `fit_real.py --grid bhac15_gaia_logt7.6-8.4.dat`**，跟 P3（`build_dr2_grid.py`）同樣的濾光片/模型效應分解比較，這步需要 `fit_real.py` 等級的計算量，一直沒排進佇列 | 用 BHAC15 重跑跟 P3 同樣的濾光片/模型效應分解，跟已有的 PARSEC-EDR3/PARSEC-DR2/MIST-DR2 三個數字放在同一張表比較。**BHAC15 只涵蓋到 0.015–1.4 M_sun，不蓋過 M45 擬合上限 2.50 M_sun**，比較結果要誠實標注只驗證了低質量段 |
| `sensitivity_sweep`（D2，**正在跑，見上方「`gcp1` 目前派工進度」**） | `--target membership_threshold` 正式規模（`n_syn=40000`）已改派到 `gcp1`，先跑 0.6／0.7 兩個門檻，觀察真實耗時後再決定要不要把剩下的 0.5/0.8/0.9 也排進去。`--target stars_per_cluster` 需要真的重跑 pyUPMASK 聚類，這台機器沒有 `pyUPMASK/` 環境，留給有環境的 session | 每個測過的設定都有一個「改動這個值，頭條數字變化多少」的具體數字，寫進 `LIMITATIONS.md` D2 |
| `extinction_form_test`（C5，**現役缺陷．優先度 高**） | 兩趟注入回收已排進 `queue.txt`（`c5_davform_lognormal`／`c5_davform_truncexp`，兩者除 `--dav-distribution` 外設定完全相同），**尚未真正跑完**——認領前先查 `logs/queue_done.txt` 確認進度 | 兩種分布形式下，用同一組合成真值做注入回收，alpha／A_V 的偏差量化比較。dav 點涵蓋到 1.20（既有 `item4_davsweep` 只到 0.60，C5 明確要求到 1.20） |
| `pyupmask_completeness_test`（C8） | 寫一個小規模的合成測試：在原始 Gaia 天測資料座標範圍內，注入已知數量、已知位置的合成「成員星」（自行/視差抽樣自星團分布），混進真實場星資料，重跑 pyUPMASK，量多少比例的注入星被正確判定為成員（召回率），依半徑/質量分箱看召回率有沒有系統性差異 | 給出完整度隨半徑/星等變化的具體曲線，不是只有一個全域數字 |
| `extra_scatter_sensitivity`（C19） | 在合成 CMD 裡疊加一個額外的高斯散布項（代表自轉/前主序光變/黑子的合併效應），散布量級參考文獻對年輕疏散星團光度變異的實測，掃過幾個散布量級，看 alpha 對這項未建模的物理有多敏感。已排進 `queue.txt`（`c19_extra_scatter_sweep`），**尚未真正跑完**——認領前先查 `logs/queue_done.txt` | 給出「散布量級 vs alpha 偏移」的敏感度曲線，不是只回答「有沒有影響」 |
| `configCD_real_data_compare`（D10，2026-08-16 教學對話中使用者追問發現） | 用真實資料跑 `fit_real.py --configs C,D`（其餘旗標完全相同、同一批 `--repeats`），比較兩者的 alpha 中心值與散布。目前「alpha 不受 dav 貼牆位置污染」只在注入回收的合成資料上驗證過，真實資料沒有直接比較過 C 跟 D | C、D 的 alpha 差距要跟兩者各自的統計誤差（散布）比較——差距遠小於合併標準誤，才能確認 headline 數字沒有被 dav 不可辨識這個已知問題間接污染；若差距顯著，要回頭檢視現有 headline 數字，見 `LIMITATIONS.md` D10 |

**2026-08-24 附記**：`d10_config_cd_real`（`--configs C,D --repeats 5`，共 10
次擬合）目前正在跑，config C 第 1 次重複已完成（29,217s），第 2 次
重複進行中。**跟 PR #116（`cloud-only-compute`，本機不再自動重啟計算
佇列）的關係**：使用者已確認「先讓 d10 跑完這次再停」——PR #116 暫緩
合併，等 d10 這 10 次擬合全部跑完（`results/fit_real_d10_cd_compare.npz`
出現 `C`、`D` 兩個 key、各 shape (5,7)）才處理本機停用計算的遷移，中途
不要手動中止（`fit_real.py` 的 checkpoint 是每完成一次重複才存檔，
中止當下正在跑的那次重複會直接損失那次的算力，不會保留部分進度）。

**2026-08-24 再更新（使用者進一步確認）**：d10 跑完後**不要**讓
`run_queue.py` 自動接著跑 `queue.txt` 排在後面的下一項（`item2_repeat`
等）——照 PR #116 的方向，d10 是本機最後一項，跑完就照 #116 的做法
停用本機自動重啟。之後 WORK_BOARD 上的工作一律改排 `cloud_queue.txt`
交給 `cloud_queue.py`（gcp1／Kaggle），本機恢復成只保留 `cloud_queue.py`
常駐。

## 待認領工作：對照 Hobart et al. 2026 的鞏固工作（2026-08-19，完整比較見 `docs/planning/PLAN_文獻對照_Hobart2026.md`）

**這個表原本 15 行，13 行（全部 D12／BP15 相關診斷鏈）已完成，見
`WORK_BOARD_DONE.md`「個別已完成的待認領任務」**。以下兩項仍開放：

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| `empirical_ml_relation_test`（D11，**現役缺陷．優先度 中高**） | **起手式：先完成可行性評估文件第三節那五項查證**（波段轉換在紅端的適用範圍、食雙星彙編在 M ≲ 0.4 M☉ 的樣本量、消光處理一致性、經驗關係的金屬量覆蓋、dM/dM_V 誤差傳播），優先做前兩項（成本最低、且可能直接否決整條路線），通過後再做其餘三項——五項查證全部完成後才決定是否投入，順序不能反過來。**「不得蒐集食雙星資料」指下載／整理可拿來擬合的資料集、開始寫實作，不含第二項查證本身需要的文獻盤點**（數 Torres+2010／Benedict+2016／Iglesias-Marzoa+2017 裡 M ≲ 0.4 M☉ 有幾顆星）——那是完成第二項查證的必要步驟，不算「開始蒐集」。五項全過之後才動手：蒐集公開食雙星質量-光度資料，仿 `pipeline/step5_imf.py` 的 `assign_masses()` 架構寫一條獨立於任何等時線的經驗質量估計路徑。**這條關係是 M_V（Johnson V 波段）對質量，不是 Gaia G 波段對質量**——用顏色相依轉換（Riello et al. 2021 的 Gaia EDR3 光度轉換）把 Gaia 觀測轉成 M_V，這一步的轉換方法、消光處理、金屬量涵蓋範圍、未解析聯星處理、誤差傳播都要先定好並記錄下來 | 先固定 Gaia→M_V 波段轉換方法、消光處理、誤差傳播鏈；再用這條經驗關係重跑低質量段（<0.5 M☉）alpha，跟 PARSEC／MIST 兩條既有結果放在同一張表比較；alpha 差異要拆解成「質量-光度關係本身的差異」跟「波段轉換/金屬量/未解析聯星造成的額外差異」兩部分分別量化，不能混在一起報一個數字。**可行性評估已完成**（`docs/planning/PLAN_D11_經驗質光關係_可行性評估.md`）：質量精度以 Gaia G 為準時不是瓶頸，但口徑還不對（正確導數是 dM/dM_V，本機網格沒有 V 波段算不出來）；目前初步判讀紅端的顏色覆蓋可能是主要風險（要檢驗的樣本集中在 BP−RP ≈ 2.4–3.5，BP−RP ≥ 2.663 就佔 51.9%） |
| `mass_dependent_fbin`（D14 衍生，2026-08-19 做 D14 時發現） | `synthesise()` 裡決定「誰帶伴星」的 Bernoulli(`f_bin`) 與主星質量 `m1` **完全獨立**，等於假設雙星比例不隨質量變化。這是已知簡化但從沒量化過代價。**Torres+2025 對 Pleiades 觀測到的是雙星比例隨半徑呈雙峰**——這支持「雙星比例不是常數」，但半徑相依不等於質量相依，兩者沒有直接證據連結，質量相依性本身仍是**待驗證假設**。起手式比照 `profile_lowmass.py`：讓 `f_bin` 變成質量的簡單函數（兩段常數或線性內插），注入一個有質量相依性的假資料、用現有的常數 `f_bin` 模型去擬合，量 alpha 被推歪多少。**先做注入回收，不要直接把它升格成自由參數** | 給出「雙星比例質量相依性的強度 vs alpha 偏移」的具體數字；若偏移遠小於統計誤差 0.144 就記為可忽略並結案，不必升格成自由參數。腳本已寫好並排進 `queue.txt`（標籤 `massdep_fbin`），生成端 `JointModel.set_mass_dependent_fbin(contrast, m_break=0.5)` 已完成並驗證（設計驗證用的 contrast=0.10/0.20/0.30 不是正式 sweep 的一部分）。**正式排入 `queue.txt` 的 sweep 是 contrast=0.0/0.15/0.30，目前整組都還沒跑**（查 `queue.txt`／`logs/queue_done.txt` 確認），contrast=0.15 不是已驗證過的數字。contrast=0 是必要的對照組——C13 記錄這套注入回收本身的 alpha 偏差地板約 -0.050，跟要測的量級接近，不扣掉地板就無法判讀 |

## 待認領工作：多星團校驗軸 A＋B（2026-08-20 使用者定案，完整背景見 `PLAN_多星團擴展.md` 第十二節）

**執行順序有硬相依**：`praesepe_pr11_close_out` 是整條線的第一張骨牌
——D8 那 4 個正確性問題的修法目前只存在於 PR #11 分支、不在 `main`。
在它合併之前，任何要真的呼叫共用 pipeline 的工作（Praesepe、Coma Ber
的 Tier 執行）**都不能用 `main`**，必須照 Coma Ber 條目 2026-08-20
那段的規定明確 pin 住 PR #11 的 commit 並在產出裡記錄用的是哪個
commit。`crosscal_massrange_table` 與 `hyades_literature_check` 已完成
（見 `WORK_BOARD_DONE.md`）。

**算力歸屬**：本機 x64 8 核桌機的 `queue.txt` 留給既有排隊項目，下面
需要跑 pipeline 的兩項請排到其他機器（x64 協作機、Kaggle、或雲算力）。
這是延續前一輪的假設，使用者若要改回本機跑可以直接推翻這條。

| 任務 | 對應 | 起手式 | 驗收標準 |
|---|---|---|---|
| `praesepe_pr11_close_out`（**其餘兩項星團工作的前置條件**） | D8、A5 | 審查 PR #11（`codex/ngc3532-praesepe-generalization`）目前分支內容，確認 D8 那 4 點的既有修法真的有效（不是只看程式碼，要實際重跑 Praesepe 的 Tier1＋Tier2 驗證），然後合併。注意 PR #11 同時含 NGC 3532，本輪只需要 Praesepe 的部分正確，NGC 3532 可以標記為未驗證但不阻擋合併 | PR #11 合併，且 D8 在 `LIMITATIONS.md` 標記解決（含重跑證據，不是只有程式碼查證）；Praesepe 交出一組可引用的 Tier1／Tier2 數字，並跟 Hobart+2026（α_high PDMF 2.53）、Pang+2024（1.92±0.10）、Khalaj & Baumgardt (2013) 做過口徑對照——**口徑對照是驗收標準的一部分，不是選配** |
| `comaber_tier1` | A5、D8 | 見下方「待認領工作：Coma Berenices（Melotte 111）Tier 1 起步」條目的完整起手式，本表不重複。可在 PR #11 合併前起跑，但必須 pin 住 PR #11 的 commit（見該條目 2026-08-20 那段），不能用 `main` | 見該條目 |

## 待認領工作：Coma Berenices（Melotte 111）Tier 1 起步（2026-08-19，見 `docs/planning/PLAN_多星團擴展.md` 第五、七節、`docs/planning/PDMF_TO_IMF_PLAN.md` 第八節分層協定）

**背景**：`PLAN_多星團擴展.md` 已把 Coma Ber 列為候選星團（動機一：第三個老年齡星團對照；動機二：金屬量接近太陽），但尚未實際起跑。核對 Hobart et al. 2026 時發現這篇論文的引言直接點名 Coma Ber 是「老年齡疏散星團次太陽質量段變平」的代表案例（引用 Kraus & Hillenbrand 2007、Tang et al. 2019），這兩篇文獻值得當作 Coma Ber 的既有 PDMF 基準線（比照 `PDMF_TO_IMF_PLAN.md` 第一步「文獻基準線」的做法）。**這項工作本次核對只做到規劃，沒有實際查詢 HR23 目錄或跑任何 pipeline**，交給認領的 session 執行。

**前置阻擋條件**：要做的事收斂成一項：完成 `praesepe_pr11_close_out`（見上一個表）——重跑驗證那些修法有效、合併 PR #11、D8 在 `LIMITATIONS.md` 標記解決。在 PR #11 合併之前，Coma Ber 若要先起跑，必須照下方那段的規定明確 pin 住 PR #11 的 commit，不能用 `main`。

`LIMITATIONS.md` D8 記錄的 4 個 PR #11 已知正確性問題（`allow_wall` 貼牆
偵測被關掉、選擇函數驗證漏掉紅藍分色檢查、SNR 迴歸沒有獨立場星樣本、
`--refresh` 遇 NSS 為 null 會崩潰）**在 D8 標記解決之前，不要用 `main`
跑 Coma Ber 的 Tier 1**——這四個問題都在共用
的 pipeline 程式碼（`cluster_imf_tier1.py`／`prepare_cluster_tier2.py`／
`cluster_forward_validation.py`）裡，若邊跑 Coma Ber 邊修，之後沒辦法
可靠判斷 Coma Ber 的結果差異是星團本身的物理差異，還是同一輪意外
夾帶的程式修正造成的，會污染可追溯性。

**起手式可以開始，但前置條件不算「已解決」**——PR #11 分支
（`codex/ngc3532-praesepe-generalization`）已針對 D8 四項各自寫了對應的
程式碼修法（只是讀程式碼查證，沒有重新動手改，也沒有重跑資料驗證），
詳見 `LIMITATIONS.md` D8——**D8 仍標記為現役缺陷，要等 PR #11 合併並
實際重跑 Tier 1 確認數值結果後才能結案**。`main` 目前不含這四項修法，
**任何要跑 Tier 1（含只是 HR23 目錄查證以外、真的呼叫
`cluster_forward_validation.py`／`prepare_cluster_tier2.py`／
`cluster_imf_tier1.py` 的步驟）都必須明確 checkout commit
`c631e733de40b7c9110e9c00eab1c8b39b53821a` 或保留這四項修法的後代 commit**，
不能直接用 `main`，且要在產出的結果檔／PR 說明裡記錄實際用的 commit。
PR #11 合併後要回頭重新核對 D8、重跑一次驗證確認數值結果，才能把 D8
標記改為已解決。

**起手式**：
0. 開始前先在 `WORK_BOARD.md` 加一行「進行中」認領，避免跟其他
   session／協作者重工——這是第一步，不是最後一步。
1. 確認要用的程式碼版本含 D8 四項修法，**兩條路擇一，不要用 `main`**：
   (a) PR #11 已合併 → 直接用合併後的 `main`，並在產出裡記錄實際用的
   commit；(b) PR #11 還沒合併（目前狀態）→ 明確 checkout
   `c631e733de40b7c9110e9c00eab1c8b39b53821a` 或保留那四項修法的後代
   commit，並在產出的結果檔／PR 說明裡記錄實際用的 commit。**D8 沒
   結案本身不阻擋起跑**，只要走 (a) 或 (b) 之一並記錄清楚即可。
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
| 2026-08-17/18 | Claude session（新機器，Acer AI 16，x64） | 大量收尾工作：`radial_r2/r3/rall` 發現已被另一 session 搶先做完（PR #60），headline 剩 5 次重複、`p6b_inject_lowmass_v2`、`verify_bprperr_v2` 重新派 Kaggle 工，PR #54/#55 重新套用避免衝突 | **多項進行中，見下方分述** | 分支 `claude/repeat-offset-reapply`（PR #62）、`claude/pr54-reapply`（PR #63）、`kaggle_queue.txt`、`logs/queue_done.txt`（本機，不進版控） | 使用者提供 6 組 Kaggle 帳號憑證（寫入本機 `kaggle_accounts.json`，gitignored，已用輕量 API 呼叫驗證有效），要求「繼續跑 Kaggle 跟 work board 剩下工作」。**過程中發現本機 `run_queue.py` 背景行程在機器重開機（Windows 更新，非人為操作）後被砍掉、閒置近 16 小時沒人發現**，重啟後緊接著 `git pull` 才發現 `radial_r2/r3/rall` 已經被另一個 session（PR #60）做完並合併，本機那份重算的 `radial_r2`（285 分鐘跑出來的）確認作廢，`taskkill` 停掉還在跑的 `radial_r3` 避免繼續白算。**PR #55（`--repeat-offset`）核實後發現其實沒合併**（先前 WebFetch 查到的「已合併」是錯的），且分支基於舊版 main、直接合併會蓋掉 main 後來加的續傳/鎖檔/manifest 驗證功能——改成只把核心種子偏移邏輯重新套用到目前 main（`fit_real.py`），同時比照加了 `inject_lowmass.py` 的 `--trial-offset`（解決 `p6b_inject_lowmass_v2` 一直因為 3 個 trial 加起來超過 Kaggle 12 小時上限而失敗的根因），開 PR #62。**PR #54 同樣核實後是「dirty」無法直接合併**（基於更舊的 main），只把其中真正完成的部分（D5 `p6b4_boundary_retest` 補測結果、C5 `--dav-distribution` 截尾指數消光分布的能力＋煙霧測試）重新套用到目前 main，其餘（散落腳本搬移、`run_queue.py` 314 行改動等）main 上已經有更新版本不需要。更新 `kaggle_queue.txt`：移除已定案的 `p9a_redo_v2`／`p9c_redo_v2`，加 headline 剩餘 5 次重複（`--repeat-offset 5,6,7,8,9`）、`p6b_inject_lowmass_v2` 拆 3 個 `--trial-offset`、`verify_bprperr_off_v2`／`on_v2`，用 `kaggle_queue.py` 派工。本機 `run_queue.py` 也重啟，接手 `p6_lowmass_v2`→`p11_outlierfrac_v2`→`p2_final2_v3`（本機完整 10 次重複版本，跟 Kaggle 拆分版本並行，互不衝突）。**踩到一個坑值得記下來**：Kaggle 派工背景執行時切換 git 分支，`kaggle_sync.py` 會打包到當下工作目錄的檔案版本——`p6b` 的 `t0`／`t1` 因此打包到還沒有 `--trial-offset` 的舊版 `inject_lowmass.py`，Kaggle 端 argparse 直接報錯（3.9 分鐘就結束，不是真的算完），已加重試項目並修好，往後派工進行中不要切分支 |
| 2026-08-18 | Claude session（新機器，Acer AI 16，x64） | `bhac15_isochrone_test`（C1、D1，接續上一行，**外部服務恢復、網格建置完成**） | **網格已備妥並驗證；`fit_real.py` 實際比較還沒跑** | 新增 `pipeline/bhac.py`、`scripts/data_prep/build_bhac_grid.py`；`pipeline/net.py` 通用化支援多組憑證鏈（原本寫死只給 PARSEC 用，加 `chain_name` 參數）；`LIMITATIONS.md`（C1／D1 更新） | 重試連線發現伺服器恢復（不再逾時），但卡在跟 PARSEC 當初一樣的憑證鏈缺失問題（`CERTIFICATE_VERIFY_FAILED`），比照 `setup/setup_ca.ps1` 抓 `perso.ens-lyon.fr` 的憑證鏈解決。下載到 `BHAC15_iso.GAIA`（178KB，Gaia 濾光片版本，30 個年齡格點 0.5 Myr–10 Gyr、單一太陽金屬量），寫轉檔程式時踩到一個一次性 bug：檔案裡的標頭行前面帶一個空格，`re.match()` 從位置 0 比對漏配，改成先 `lstrip()` 才解決。轉出 `bhac15_gaia_logt7.6-8.4.dat`（170 列、6 個年齡格點落在 M45 相關範圍），用 `pipeline.isochrones.load_grid()`／`isochrone_at()` 驗證讀取正常。**確認質量範圍只到 0.015–1.4 M_sun**，不蓋過 M45 擬合上限 2.50 M_sun，且只有太陽金屬量一組，MH 維度形同鎖死——這些限制已誠實記在 D1，不是驗證了全範圍。**還沒做的部分**：真正跑一次 `fit_real.py --grid bhac15_gaia_logt7.6-8.4.dat` 跟 P3（`build_dr2_grid.py`）同樣的濾光片/模型效應分解比較，這步需要 `fit_real.py` 等級的計算量，本機當時兩條佇列（`run_queue.py`／`kaggle_queue.py`）都在跑，沒有排進去，留給下一個人接手 |
| 2026-08-20 | Codex | PR #11 多星團控制場／選擇函數續跑（D8） | **完成本輪** | `prepare_cluster_tier2.py`、`cluster_forward_validation.py`、`data/cluster_*_control_field.csv`、分支 `codex/ngc3532-praesepe-generalization` | 使用 ARI Gaia DR3 鏡像補齊控制場；NGC 3532 在 G>=17 紅藍驗證失敗，未跑前向；Praesepe 三項選擇函數檢查通過，但 smoke test 的 2/2 個 B 擬合 f_bin=1 貼邊，安全標為 diagnostic_only、沒有報 IMF。 |
| 2026-08-20 | Codex | stick_out_fraction_constraint（D13）：聯星比例第二制約的成本／效益評估 | 進行中 | 分支 codex/stickout-fbin-assessment；將新增 docs/planning 評估文件 | 接續 Praesepe 前向 smoke test 的 f_bin=1 貼邊現象。只評估凸出星比例如何成為獨立似然項、目前簡併的診斷方式與實作成本；不直接改 pipeline/joint_fit.py，也不重跑既有 IMF。 |
| 2026-08-20 | Codex | stick_out_fraction_constraint（D13）：完成聯星比例第二制約的成本／效益診斷 | **完成：保留為模型檢查，不直接改似然** | `scripts/diagnostics/assess_stickout_fraction.py`、`results/stickout_fraction_assessment_p2final_v3.json`、`docs/planning/ASSESSMENT_CMD_STICKOUT_FBIN_2026-08-20.md`，分支 `codex/stickout-fbin-assessment` | 讀取 M45 headline 已完成的 10 次重複，不重跑 IMF。真實凸出比例 5.78% 落在模型 5.80%–7.04% 內，故目前模型沒有明顯矛盾；但此摘要與 Hess 似然來自同一張 CMD，不能當獨立 binomial likelihood 硬加，否則會重複計數。若要升格，先做注入回收，並改成排他區域或校正的聯合似然。 |
| 2026-08-20 | Codex | crosscal_massrange_table（多星團校驗軸 A）：Pang+2024／本專案／Hobart+2026 的 M45 質量函數口徑對照 | 進行中 | 分支 `codex/stickout-fbin-assessment`；將新增可查證文獻對照表 | D13 完成後接續的低算力工作。優先從原始或正式出版來源核對 Pang+2024 的質量範圍、MF 定義、雙星處理、估計器與完整度；未知資料明確標未知，不把初步的「大幅收斂」當定論。 |
| 2026-08-20 | Codex | crosscal_massrange_table（多星團校驗軸 A）：完成 Pang+2024／本專案／Hobart+2026 的 M45 質量函數口徑核對 | **完成：Pang 質量範圍由未知改為已查證** | `docs/planning/CROSSCAL_M45_PANG_HOBART_2026-08-20.md`、`scripts/diagnostics/check_massrange_crosscal.py`，分支 `codex/stickout-fbin-assessment` | 原始公開 PDF 的 Table 1／註解／Figure 3／方法節確認：Pang M45 是 PDMF、0.28–2.00 M☉、未分箱最大似然+MCMC、以三個 q 分布做聯星校正後採 uniform-q。Hobart PDMF 切到同範圍為 1.952，Pang 為 2.010±0.090；僅能說質量範圍已對齊、中心相近，不能忽略兩者聯星校正不同。 |
| 2026-08-20 | Codex | hyades_literature_check（多星團校驗軸 B）：先查 Hyades 文獻再決定是否排進 pipeline | 進行中 | 分支 `codex/stickout-fbin-assessment`；將新增文獻篩選報告 | 接續已完成 Pang 口徑核對的低算力工作。只從原始／正式來源核對年齡定年、金屬量、既有 MF 口徑與近距離的大角尺度風險；不直接執行 pipeline，也不把文獻數字寫成本專案結果。 |
| 2026-08-20 | Codex | hyades_literature_check（多星團校驗軸 B）：完成文獻篩選與執行決策 | **完成：保留候選，但暫不直接執行** | `docs/planning/HYADES_LITERATURE_SCREEN_2026-08-20.md`，分支 `codex/stickout-fbin-assessment` | 已用原始／正式來源核對 LDB 年齡、光譜金屬量、既有 mass function/聯星研究與 Gaia 空間尺度。Hyades 可增加老年齡、金屬富有的對照點，但現有 5°設定只涵蓋約 4.1 pc，遠小於約 10 pc潮汐尺度；先做 5°／12°／20° 成員與選擇函數 smoke test，通過後才排傳統法。 |
| 2026-08-22 | Codex | M45 BP15 前向模型成對 smoke：建立隔離輸入並檢查 alpha 是否穩定 | **探索完成；正式比較待排程** | `docs/planning/M45_BP15_FORWARD_SMOKE_2026-08-22.md`、`results/bp15_forward_smoke_summary.json` | 三個 3k paired seeds 的 alpha 差仍不穩定，不能下 BP15 科學結論。下一任務應拆到獨立節點，以 40k、至少 5 paired seeds 跑 BP20/BP15；不可把兩邊非配對平均當效果。 |
| 2026-08-23 | Codex | BP15/BP20 正式成對前向比較派工前置檢查 | **完成；等待 Kaggle 登入／帳號分配** | `scripts/diagnostics/prepare_bp15_paired_dispatch.py`、`scripts/diagnostics/summarize_bp15_formal_paired.py`、`results/bp15_formal_paired_dispatch.json`、`docs/planning/M45_BP15_FORMAL_PAIRED_DISPATCH_2026-08-23.md` | 已驗證 BP15 三個隔離輸入存在，生成 offsets 0–4 的 10 個唯一 job tag，明定逐 offset paired 分析與驗收規則；另實際建立 82.2 MB 暫存 Kaggle payload，確認自訂輸入可被 kernel 根目錄讀取。新彙整器 fail-closed：缺任何配對就拒算平均。本機缺 `kaggle_accounts.json`／access token，未送出雲端長跑，也未把派工表誤寫成結果。 |
| 2026-08-21 | Claude session（本機） | `mass_dependent_fbin`（D14 衍生） | 進行中（腳本已寫好並排進本機佇列，等結果） | `inject_massdep_fbin.py`（新檔）、`queue.txt`，分支 `mass-dep-fbin`（PR #86） | 依本文件規則改成「保留原任務列、在尾端新增狀態列」，不再直接改寫既有列（2026-08-21 CodeRabbit review）。腳本已依 review 修正四處：分片檔名帶 `--trial-offset`（否則各分片互相覆寫）、保存 trial id 並只對兩邊都成功的試驗配對相減、不完整批次不下結論且以非零碼結束（避免被佇列記成 ok）、結論只在淨偏移真的小於統計誤差 0.144 時才印 |
| 2026-08-23 | Claude session（本機） | 新增第三個算力來源：GCP SSH worker `gcp1`（e2-highcpu-8） | **完成，已正式派工** | `docs/reference/CLOUD_WORKERS.md`、`ssh_workers.py`／`ssh_sync.py`／`cloud_queue.py`（分支 `claude/cloud-workers-ssh-2026-08-22`，PR #103）、`ssh_workers.json`／`cloud_queue.txt`（本機新增，不進版控） | 使用者建好 GCP VM 後協助完成連線設定：GCP 瀏覽器內建 SSH 建立的帳號跟我們自己金鑰登入的帳號是**兩個不同 Linux 帳號、各自獨立家目錄**（本機憑證、GitHub Deploy Key、裝的套件都要各自處理一次，不會互通，這是踩到才發現的坑，已記進 `CLOUD_WORKERS.md`），另外修好 SSH host-key 驗證、GitHub Deploy Key（需請 repo admin `helmet-png` 加，非 admin 協作者的帳號連 repo Settings 頁面都是 404）。全鏈路 push→run→status→pull 已用 `kaggle_smoketest.py` 驗證通過。**已派第一項真正工作**：`d2_membership_threshold_p06_p07_retry`（D2 敏感度掃描，正式規模 `n_syn=40000`，先跑 0.6／0.7 兩個門檻，見上方 D2 進度說明），本機 `queue.txt` 對應項目已停用避免重複算。**分工原則**：`ssh_workers.json`／`cloud_queue.txt` 都是本機私有設定（不進版控，跟 `kaggle_accounts.json` 同一類），要用 `gcp1` 派工的人自己的機器需要各自設定連線，不能直接沿用這台機器的檔案；要排新工作進 `cloud_queue.txt` 前，先確認同一件事沒有同時排在 `queue.txt`／`kaggle_queue.txt`，避免三邊重複算力（本機、Kaggle、GCP 現在是三個獨立但要互相避開的算力池） |
bp15_bp20_paired_comparison：檢查放寬 BP 誤差門檻（BP15 vs 現行
BP20）找回的紅端候選星，納入後對 alpha 頭條數字有沒有實質影響。
派工前置檢查已完成（10 個唯一 job tag、82.2 MB 暫存 payload 已驗證
可被 kernel 讀取），彙整器設計為缺任何配對就拒算平均（fail-closed）。
本機目前缺 kaggle_accounts.json／access token，還沒送出雲端長跑。
先前的探索性 smoke test（3 個 3k paired seeds）顯示 alpha 差仍不
穩定，不能下科學結論，正式比較需要 40k、至少 5 個 paired seeds。
耗時未查證。
