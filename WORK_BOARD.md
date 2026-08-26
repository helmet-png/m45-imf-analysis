# 工作認領表（誰現在在做什麼、還剩什麼沒做）

`CONTRIBUTING.md` 管「怎麼合併」，這份管開始做之前先看這裡，避免兩個人／
兩個 agent 同時做同一件事。這份只放正在執行或還沒執行的工作；已經
達成、結案的事搬到 `WORK_BOARD_DONE.md`（完整規則見 `CONTRIBUTING.md`
零之四）。

## 規則

1. 開始任何預期要花超過一次對話（或會碰共用檔案：`pipeline/`、
   `injection_recovery.py`、`LIMITATIONS.md`、`PAPER_OUTLINE.md`、
   `queue.txt`）的工作之前，先讀完下面每個任務的表格與說明，確認
   沒有人已經在做同一件事或高度重疊的事。
2. 開始工作時，把對應任務的狀態改成「進行中」，補上開始日期，並在
   下方說明文字的第一句寫明認領人是誰（人類協作者姓名、或哪一種
   agent／哪一台機器）——表格本身沒有獨立的認領人欄位，這句話是
   唯一能讓其他人知道「該去問誰」的地方，漏寫等於規則 1 要求的
   查重無法真的落實。放棄或暫停時改回「尚未進行」並在說明文字補一句
   原因。真的做完時，照 `CONTRIBUTING.md` 零之四把整段（表格＋說明
   文字）搬到 `WORK_BOARD_DONE.md`，這裡刪掉——不要用刪除線或
   「已完成」字樣蓋在原本的行上，那樣會讓同一件事的新舊說明混在
   同一格裡，越堆越難讀。要查某任務目前狀態，先看它還在不在這份
   文件裡；不在了就代表已完成，去 `WORK_BOARD_DONE.md` 找完整記錄。
3. 看不出算不算重複、範圍該怎麼分——不要用猜的、也不要因為怕衝突
   就不寫：在說明文字裡寫清楚困惑點，讓開這個任務的人或使用者看到
   後決定怎麼分工。
4. 誰都可以編輯這份文件（人類協作者、Claude、Codex、其他 agent）。
5. 任務名稱後面的括號標對應的 `LIMITATIONS.md` 條目（例如 A1），跟
   `LIMITATIONS.md` 互相參照，完整規則見 `CONTRIBUTING.md` 五之一。
   跟限制清單無關的工作（環境設定、文件整理）不用標。
6. 輸入參數欄寫物理量（符號與單位），不要寫程式裡的變數名稱或指令
   旗標——例如寫「合成星數 N = 40,000 顆」，不要寫「--n-syn 40000」。
   可重現用的實際指令放在下方說明文字裡，欄位只給看得懂物理意義的
   摘要。

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

**2026-08-26 新增：多帳號 GCP 資源池（IAP tunnel + OS Login）**——
起因是 2026-08-25 那次斷線（來源 IP 白名單擋掉，中控機換網路後
就連不上，卡了好幾小時），加上三位隊員都各自申請了自己的 GCP 免費
試用帳號，希望互相共用成一個資源池。維持既有的「集中派工」架構不變
（見上面 gcp1 段落），只是中控機改用 IAP tunnel（不對外開 22 埠，
靠 Google 帳號驗證、不受來源 IP 變動影響）連進隊友各自專案裡的 VM，
且新增自動開關機（`gcp_vm_lifecycle.py`）避免常駐開機把 90 天 $300
的免費額度燒光（e2-highcpu-8 常駐 90 天單台成本已經超過額度，實際
數字見 `docs/reference/CLOUD_WORKERS_IAP_SETUP.md`）。程式面：
`gcp_vm_lifecycle.py`（新增，開關機邏輯）、`iap_tunnel_manager.py`
（新增，常駐維護 tunnel 連線）、`ssh_workers.py`／`ssh_sync.py`／
`cloud_queue.py`（各自小幅擴充，向下相容，沒填 GCP 三個新欄位的
既有 worker 完全不受影響）。VM 擁有者（隊友）跟中控機操作者兩邊各自
要做的手動設定步驟見 `docs/reference/CLOUD_WORKERS_IAP_SETUP.md`，
還沒有真的拿隊友的 GCP VM 實測過（本機沒裝 gcloud，只用假造的設定
值驗證過程式邏輯本身不會 crash），第一次真正加入隊友的 VM 時要留意
可能有沒設想到的坑。

## 待辦事項

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| p6_lowmass_v3（A1、A3） | 尚未進行 | 指派時間：2026-08-21 | 合成星數 N = 40,000 顆；重複次數 = 3；精修階數 = 2 階；低質量段冪次 p 的掃描點 5 個 | 低質量段冪次 p 對 α 的關係曲線（斜率 d(alpha)/d(p)） |

p6_lowmass_v3：量低質量段冪次 d(alpha)/d(p) 的斜率，這是目前最大的
單一系統誤差來源（0.248，見 LIMITATIONS.md A3）。指令：
profile_lowmass.py --procs 8 --n-syn 40000 --repeats 3 --refines 3,3
（5 個低質量段冪次 x 3 次重複，共 15 次擬合）。原本記錄的單次耗時
18.7 小時無法從本機 log 佐證（log 只有 7 行、沒有任何完成時間戳，
且檔案時間早於宣稱的啟動時間），已訂正為不可信；唯一可查證的成本
量級是規模本身（15 次擬合，全樣本 1,078 顆），對照同量級的
radial_r1_final（5 次重複、355 顆核心切片、實測 72,814 秒即約 4 小時
一次）推算，全樣本單次耗時只會更長，15 次總量級會長期擋住本機循序
佇列，這是使用者已經決定移到佇列最後（選項 C）的原因。跑之前必須
先手動把 results/profile_lowmass.npz（2026-08-15 的舊檔、無 manifest、
未精修）移開，不要指望程式自動擋下來。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| p6b_inject_lowmass_v2（A1） | 尚未進行 | 指派時間：2026-08-12 | 合成星數 N = 40,000 顆；試驗次數 = 3；精修階數 = 2 階 | 回收低質量段冪次與真值冪次的比值（可辨識性） |

p6b_inject_lowmass_v2：驗證低質量段冪次的可辨識性——這個數字決定
要不要把它升格成自由參數。指令：inject_lowmass.py --procs 8
--n-syn 40000 --trials 3 --refines 3,3。舊結果（p_recovered/p_true
比值 0.92）是修好 multi_stage_best() 精修 bug 之前跑的，完全沒精修，
數字不可信。Kaggle 上同類工作曾多次重派，但沒有找到明確的完成結論，
認領前務必先查 results/ 與 RESULTS_LOG.md 確認是否已經有可用結果，
避免重工。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| nbody_prior_from_radial（A5） | 尚未進行 | 指派時間：2026-08-12 | 恆星數 N = 400 顆；質量分層度 S = 0.3、0.5、0.7（三組）；virial 比 Q = 0.5，圍繞 pilot 參數小幅擾動 | 3–5 組模擬跑完的 α(r) 曲線，跟觀測 α(<r) 的擬合優度比較 |

nbody_prior_from_radial：N-body 模擬（第 5 步）的初步校準方向，不是
正式版本。指令基礎：mcluster_sse -N 400 -S 0.3/0.5/0.7 -P 0 -R 2.3
-Q 0.5（各跑數組）。前置的三個定義不一致（分箱方式、半徑維度、
質量範圍與估計量）已經解決並寫進 analyze_alpha_r.py，下一步是真正
跑一組圍繞 pilot 參數小幅擾動的模擬網格。pilot 本身（400 顆星、
單次）耗時約需查 nbody_setup/ 下的紀錄，本表未附具體秒數；正式網格
是 3–5 組小規模模擬，還不是文獻建議的 550–942 次全網格。第 5 步
「正式跑」的候選方案之一：仿 Hobart et al. 2026 的作法，用中等規模
模擬網格（幾十到百來次，不需要他們的 550–942 次）訓練一個機器學習
模擬器（例如 scikit-learn 的 GaussianProcessRegressor），再用既有的
emcee 或 HMC 套件抽初始條件的後驗分布，取代暴力網格搜尋——這個做法
可行性（訓練資料要多少組模擬才夠、模擬器預測誤差多大）還沒驗證過，
只是優先評估的候選方案，不是定案。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| pdmf_step4_radius_expansion（A5） | 尚未進行 | 指派時間：2026-08-12 | 搜尋半徑 θ 從 5° 放大到 8°–17° | 新的全樣本 α，含大半徑下的完整度驗證 |

pdmf_step4_radius_expansion：PDMF→IMF 第 4 步，觀測上唯一能給出
「5 度搜尋半徑夠不夠」決定性答案的路線，但成本最高。做法：改大
config.toml [target] radius_deg，重跑 scripts/data_prep/fetch_gaia.py
→ scripts/drivers/run_pipeline.py 第 1–5 步。原本要等
radial_final_reruns 全部到齊才能判斷第二層門檻（梯度統計上是否為真）
是否滿足——這個前提已於 2026-08-23 滿足（r1/r2/r3/rall 全部到齊，見
LIMITATIONS.md A5），但目前還沒有人依這個結果重新評估是否投入第 4
步，這一步的「要不要做」判斷本身也還沒有人做。耗時未查證，涉及
整條 pipeline 重跑，且需要重建大半徑下的 pyUPMASK 成員判定與選擇
函數，預期是重量級工作。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| bhac15_isochrone_test（C1、D1） | 尚未進行 | 指派時間：2026-08-16 | BHAC15 等時線網格（現有網格檔涵蓋約 40–250 Myr，太陽金屬量）；合成星數 N = 40,000 顆；重複次數 = 5 | 濾光片/模型效應分解比較（跟 PARSEC、MIST 三版對照） |

bhac15_isochrone_test：BHAC15 等時線的網格轉換與涵蓋範圍確認已經
完成（bhac15_gaia_logt7.6-8.4.dat，170 列、6 個年齡格點），唯一剩下
的是真正跑一次 fit_real.py --grid bhac15_gaia_logt7.6-8.4.dat
--procs 8 --n-syn 40000 --repeats 5 --configs A,C 拿這個網格算模型
效應分解，跟已有的三個等時線版本（PARSEC-EDR3／PARSEC-DR2／
MIST-DR2）放進同一張比較表。BHAC15 只涵蓋到 0.015–1.4 M_sun，不
蓋過 M45 擬合上限 2.50 M_sun，比較結果要誠實標注只驗證了低質量段。
耗時未查證，量級應與同類 fit_real.py 全量跑相當。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| stars_per_cluster_sensitivity（D2） | 尚未進行 | 指派時間：2026-08-25 | pyUPMASK 每群星數（`stars_per_cluster`）掃描 | 可行性已查證受阻；有 pyUPMASK 環境的機器才能真的量出敏感度數字 |

stars_per_cluster_sensitivity：D2 剩下的另一個掃描目標——
`stars_per_cluster` 需要真的重跑 pyUPMASK 聚類，不是像
membership_threshold 那樣重套門檻就好（membership_threshold 已測完
五點，見 WORK_BOARD_DONE.md）。可行性查證已經實際執行過並確認受阻：
repo 內沒有 `pyUPMASK/`、沒有 `prepared/` 輸入，`run_variant.py` 也
還沒暴露對應的參數旗標（可行性查證本身已完成，見
WORK_BOARD_DONE.md，過程中順手修好一個無 SciPy 環境時可行性模式
會在檢查前就崩潰的問題）。真正的敏感度數字仍待有 pyUPMASK 環境的人
或機器補齊三項依賴後才能測。D2 問題陳述裡列的其餘設定（pca_dims、
clustering_method、inner_loop_runs、hess_color_range／
hess_mag_range、min_flux_snr_bp）也都還沒做過敏感度測試，同樣待
認領，見 LIMITATIONS.md D2。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| extinction_form_test（C5） | 尚未進行 | 指派時間：2026-08-13 | 消光分布形式（對數常態 vs 截尾指數）；消光量 A_V 掃描上限 1.20 mag | 兩種消光分布形式下 alpha／A_V 系統誤差的量化比較 |

extinction_form_test：測消光分布形式對 A_V 系統誤差有沒有影響，這是
現役缺陷、優先度高（污染範圍已知，見 LIMITATIONS.md C5）。兩趟注入
回收（injection_recovery.py --dav-distribution lognormal／
truncexp，queue.txt 標籤 c5_davform_lognormal、c5_davform_truncexp，
dav 掃到 1.20，比既有 item4_davsweep 的 0.60 更寬）已經寫進本機
queue.txt，但循序佇列還沒輪到，認領前先查 logs/queue_done.txt 確認
進度。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| pyupmask_completeness_test（C8） | 尚未進行 | 指派時間：2026-08-13 | 已知數量、已知位置（自行 μ、視差 π）的合成成員星，混入真實場星資料 | 完整度（召回率）對半徑 r／星等 G 的分箱曲線 |

pyupmask_completeness_test：量 pyUPMASK 成員判定的完整度隨半徑/
星等的變化——目前只有一個全域完整度數字，沒有分箱曲線。做法是在
真實 Gaia 座標範圍內注入已知位置的合成成員星，混進真實場星資料
重跑 pyUPMASK，量召回率。這支測試腳本還沒寫，耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| extra_scatter_sensitivity（C19） | 尚未進行 | 指派時間：2026-08-13 | 額外亮度散布 σ_extra（高斯，代表自轉調製/前主序光變/黑子），掃過幾個量級 | α 對 σ_extra 的敏感度曲線 |

extra_scatter_sensitivity：量自轉調製／前主序光變／黑子等未建模
物理造成的額外亮度散布，對 alpha 有多敏感。已排進
queue.txt（injection_recovery.py，標籤 c19_extra_scatter_sweep，
散布量級參數見 queue.txt 該行），循序佇列還沒輪到，認領前先查
logs/queue_done.txt。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| configCD_real_data_compare（D10） | 尚未進行 | 指派時間：2026-08-16 | config C 與 D（差別僅 dav 上界：0.6 vs 1.2 mag）；重複次數 = 5 | C、D 兩組 α 中心值與統計誤差的比較 |

configCD_real_data_compare：目前「alpha 不受 dav 貼牆位置污染」只在
注入回收的合成資料上驗證過，真實資料從沒直接比較過 config C 跟 D。
指令：fit_real.py --configs C,D --repeats 5（--repeats 比照既有
頭條設定）。做法是用真實資料各跑一次，比較 alpha 中心值與統計誤差
的差距是否遠小於合併標準誤。本機曾嘗試跑這組（config C 完成 2/5
次重複後，因單次耗時從 8.1 小時拉長到 10+ 小時、且本機已停用計算
佇列，手動中止——這 2 次部分結果留在
results/fit_real_d10_cd_compare.npz，非正式數字，不能引用）。正式
版本已排進 cloud_queue.txt 交給 gcp1 執行，但排在佇列較後面，預計
要數天才輪到；認領前注意這組佇列項目目前沒有帶 --tag，輸出路徑
跟本機殘留的部分結果檔同名，執行前建議先確認會不會互相覆寫、或
先把本機殘檔搬開（同類問題 PR #126 修過一次）。耗時未查證，量級與
同類 fit_real.py 全量跑相當。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| empirical_ml_relation_test（D11） | 尚未進行 | 指派時間：2026-08-19 | docs/planning/PLAN_D11_經驗質光關係_可行性評估.md 第三節五項查證（尚未開始） | 五項查證的查證結果（文件更新，尚無獨立輸出檔） |

empirical_ml_relation_test：建一條完全獨立於任何等時線模型的經驗
質量-光度關係，檢查低質量段 alpha 對「用不用等時線」本身敏不敏感
——這是現役缺陷、優先度中高（見 LIMITATIONS.md D11）。可行性評估
已經做完：質量精度以 Gaia G 為準時不是瓶頸，但正確的轉換導數是
dM/dM_V 不是 dM/dG，本機網格沒有 V 波段算不出來；初步判讀紅端顏色
覆蓋可能是主要風險（要檢驗的樣本過半集中在 BP−RP ≥ 2.663）。下一步
是完成評估文件第三節的五項查證，優先做成本最低、可能直接否決整條
路線的前兩項，全過才能動手蒐集資料、寫實作。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| mass_dependent_fbin（D14 衍生） | 尚未進行 | 指派時間：2026-08-19 | 雙星比例對比度 contrast = 0.0、0.15、0.30（三組）；質量斷點 m_break = 0.5 M☉ | α 偏移量對 contrast 的關係 |

mass_dependent_fbin：雙星比例是否隨主星質量變化，目前模型假設是
常數，這是已知簡化但沒量化過代價。指令：inject_massdep_fbin.py
--contrast 0.0,0.15,0.30（queue.txt 標籤 massdep_fbin）。做法是用
注入回收量化「質量相依雙星比例」對 alpha 的偏移量，不直接升格成
自由參數（dav 的教訓是參數可以放進模型卻完全不被資料約束）。腳本
已寫好並排進 queue.txt，正式 sweep 目前都還沒跑，循序佇列還沒輪到。
耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| praesepe_pr11_close_out（D8、A5） | 尚未進行 | 指派時間：2026-08-20 | PR #11（分支 codex/ngc3532-praesepe-generalization）內容審查 | PR #11 合併紀錄；Praesepe Tier1／Tier2 結果檔 |

praesepe_pr11_close_out：整條多星團校驗軸（Praesepe、Coma Ber）的
第一張骨牌——D8 記錄的 4 個正確性問題（貼牆偵測被關掉、選擇函數
驗證漏掉紅藍分色檢查、SNR 迴歸沒有獨立場星樣本、--refresh 遇 NSS
為 null 會崩潰）的修法目前只存在於 PR #11 分支，還沒合併進 main。
需要實際重跑 Praesepe 的 Tier1＋Tier2 驗證確認修法有效（不能只看
程式碼），然後合併；NGC 3532 可以標記為未驗證但不阻擋合併。合併後
D8 才能在 LIMITATIONS.md 標記解決。交出的 Tier1／Tier2 數字要跟
Hobart+2026（α_high PDMF 2.53）、Pang+2024（1.92±0.10）、
Khalaj & Baumgardt (2013) 做過口徑對照，這是驗收標準的一部分。
規模較大，建議排到 x64 協作機、Kaggle 或雲算力，不要排進本機
queue.txt。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| comaber_tier1（A5、D8） | 尚未進行 | 指派時間：2026-08-19 | Coma Berenices 星團（年齡約 600–800 Myr）；checkout commit c631e733de40b7c9110e9c00eab1c8b39b53821a 或其後代 | Coma Berenices 的 α、動力學年齡 τ、誤差預算表 |

comaber_tier1：Coma Berenices（老年齡、金屬量近太陽的疏散星團）的
Tier1 起步，補齊多星團校驗軸。指令基礎：cluster_imf_tier1.py（比照
NGC 3532／Praesepe 用過的同一套腳本）。前置阻擋條件已收斂成一項：
完成 praesepe_pr11_close_out。起手式可以先開始，但在 PR #11 合併
之前必須明確 checkout commit c631e733de40b7c9110e9c00eab1c8b39b53821a
（或保留那四項修法的後代 commit），不能直接用 main，且要在產出裡
記錄實際用的 commit。動手前要讀 Kraus & Hillenbrand (2007)、Tang
et al. (2019) 兩篇原文當基準線——Tang et al. 已核對完成（α=0.79±0.16，
0.25–2.51 M☉，不能直接跟本專案頭條 alpha 比較），Kraus & Hillenbrand
還沒查證（先前收到的 PDF 抓錯論文，需要使用者重新提供正確那篇：
The Astronomical Journal, 134, 2340）。動力學年齡大機率會觸發
PDMF_TO_IMF_PLAN.md 第八節的 Tier 2（需要動力學校正），起跑前先粗算
一次 τ = age / t_rh 確認。交出的誤差預算表要跟這兩篇原文逐項對齊
質量範圍、樣本定義、完整度修正、聯星處理、MF 定義（system 還是
stellar，見 D14）後才能比較 alpha，不能直接並排不同口徑的數字。
規模較大，建議排到 x64 協作機、Kaggle 或雲算力，不要排進本機
queue.txt。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| bp15_bp20_paired_comparison（D12） | 尚未進行 | 指派時間：2026-08-23 | BP 誤差門檻 SNR_BP = 15 vs 20（現行）；合成星數 N = 40,000 顆；至少 5 組配對種子 | BP15 vs BP20 逐 offset 配對後的 α 差異 |

bp15_bp20_paired_comparison：檢查放寬 BP 誤差門檻（BP15 vs 現行
BP20）找回的紅端候選星，納入後對 alpha 頭條數字有沒有實質影響。
派工前置檢查已完成（scripts/diagnostics/prepare_bp15_paired_dispatch.py
產生的 10 個唯一 job tag、82.2 MB 暫存 payload 已驗證可被 kernel
讀取），彙整器（scripts/diagnostics/summarize_bp15_formal_paired.py）
設計為缺任何配對就拒算平均（fail-closed）。本機目前缺
kaggle_accounts.json／access token，還沒送出雲端長跑。先前的探索性
smoke test（3 個 3k paired seeds）顯示 alpha 差仍不穩定，不能下科學
結論，正式比較需要 40k、至少 5 個 paired seeds。耗時未查證。
