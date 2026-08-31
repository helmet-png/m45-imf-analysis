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
`cloud_queue.txt`，不要再假設本機佇列會撿去跑。排新工作前先確認同一件事
沒有同時排在另一個佇列檔裡。

**目前算力池（2026-08-29 更新，共 8 個 worker，全部由 `cloud_queue.txt`
統一派工）**：

| worker | 型態 | 核心 | 定位 |
|---|---|---|---|
| `senior24` | SSH | 24 | **最強的節點**，跑佇列裡最重的單一工作 |
| `gcp1` | SSH | 4 | GCP e2-highcpu-8，長期常駐 |
| Kaggle × 6 帳號 | Kaggle | 4 × 6 | 適合能拆成獨立分片的工作 |

`senior24` 是 2026-08-29 新接進來的——隊友（學長）自願提供的 Ubuntu
22.04 機器，AMD 平台 24 個邏輯核心、6 GB RAM、183 GB 可用空間，透過
Tailscale 連線（不需要固定對外 IP，也不用改路由器）。**`procs` 給滿 24**
——原本保守設 16，隊友明說「24 都拿去用」（他那台實體是 32 執行緒，撥
24 個給這個 VM），且實測記憶體確認吃得下才調上去的。

**記憶體才是這台的真正上限，不是核數**：只有 7.3 GB RAM 而且沒有 swap
（超用會直接被 OOM killer 砍掉，不是變慢）。實測 24 個工人全開時，主行程
載入等時線網格 +322 MB、24 個工人合計再 +214 MB，總共約 536 MB，餘裕很大
——因為 Linux fork 的寫時複製讓工人唯讀共享那份大網格，真正送進 Pool 的
模型只有 4 MB。**量測時踩到的陷阱**：先用 `ru_maxrss` 量得 343 MB/工人、
推算 24 個要 8.2 GB 會 OOM，那是假象（RSS 把共享頁面在每個子行程各算一
次）；要看 `/proc/meminfo` 的 MemAvailable 實際變化，兩者差一個數量級。

**接這台時踩到、已經修掉的兩個坑**（都已進 main，換下一台 worker 時
不會再遇到）：(1) 那台是 Python 3.10，而 `pipeline/config.py` 直接
`import tomllib`——那是 3.11 才進標準庫的，整條 pipeline 在讀設定檔就
死掉，已改成找不到就退回 `tomli`；(2) `cloud_queue.py`／`run_queue.py`
用了 `subprocess.CREATE_NO_WINDOW`（Windows 專屬），害雲端協調 VM 一
啟動就 `AttributeError` 崩潰、systemd 重試 5130 次，服務顯示
`active (running)` 卻從未真正派過工，導致 gcp1 閒置逾 20 小時、算完的
結果無人收取，已改成 `getattr(...)` 取值。

**分工原則**：能拆成獨立分片、每片幾小時內跑完的工作（例如帶
`--repeat-offset`／`--trial-offset` 的）優先派 Kaggle，六個帳號可以平行；
不能拆、又特別重的單一工作派 `senior24`；其餘常態工作留給 `gcp1`。
同一時間盡量讓三種算力都有事做，不要讓重工作排隊擋住輕工作。

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
| configCD_real_data_compare（D10） | 已排隊，等 `senior24` 撿（2026-08-29 從 gcp1 改派） | 指派時間：2026-08-16 | config C 與 D（差別僅 dav 上界：0.6 vs 1.2 mag）；重複次數 = 5；`--procs 24` | C、D 兩組 α 中心值與統計誤差的比較 |

configCD_real_data_compare：目前「alpha 不受 dav 貼牆位置污染」只在
注入回收的合成資料上驗證過，真實資料從沒直接比較過 config C 跟 D。
指令：fit_real.py --configs C,D --repeats 5（--repeats 比照既有
頭條設定）。做法是用真實資料各跑一次，比較 alpha 中心值與統計誤差
的差距是否遠小於合併標準誤。本機曾嘗試跑這組（config C 完成 2/5
次重複後，因單次耗時從 8.1 小時拉長到 10+ 小時、且本機已停用計算
佇列，手動中止——這 2 次部分結果留在
results/fit_real_d10_cd_compare.npz，非正式數字，不能引用）。正式
版本已排進 cloud_queue.txt。**2026-08-29 改派給 `senior24`（24 核）
並把 --procs 從 4 提到 24**：這是佇列裡最重的單一工作（2 個 config
× 5 次重複 = 10 次全樣本擬合），留在 4 核的 gcp1 上會擋住它後面所有
東西；改派之後跟留在 gcp1 的 mass_dependent_fbin 平行跑，兩台同時
有事做。改派前已用 `ssh_sync.py status` 確認這個標籤在 gcp1 上是
missing（從沒啟動過），不會造成重複計算。procs 給滿 24 是實測記憶體
（24 個工人全開時合計只多用 214 MB，因為 fork 寫時複製讓大網格共享）
確認吃得下才決定的，不是照核數填，詳見上方「現況說明」的算力池段落。
認領前注意這組佇列項目
目前沒有帶 --tag，輸出路徑跟本機殘留的部分結果檔同名，執行前建議
先確認會不會互相覆寫、或先把本機殘檔搬開（同類問題 PR #126 修過
一次）。耗時未查證，量級與
同類 fit_real.py 全量跑相當。

empirical_ml_relation_test：認領人：Codex 本機 session（分支
`codex/d11-empirical-ml-coverage`）。建一條完全獨立於任何等時線模型的
經驗質量-光度關係，檢查低質量段 alpha 對「用不用等時線」本身敏不
敏感——這是現役缺陷、優先度中高（見 LIMITATIONS.md D11）。可行性
評估已經做完：質量精度以 Gaia G 為準時不是瓶頸，但正確的轉換導數
是 dM/dM_V 不是 dM/dG，本機網格沒有 V 波段算不出來；初步判讀紅端
顏色覆蓋可能是主要風險（要檢驗的樣本過半集中在 BP−RP ≥ 2.663）。
下一步是完成評估文件第三節的五項查證，優先做成本最低、可能直接
否決整條路線的前兩項，全過才能動手蒐集資料、寫實作。耗時未查證。

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| empirical_ml_relation_test（D11） | 進行中 | 開始日期：2026-08-26 | Gate 1（Gaia→V 紅端適用性）、Gate 2（低質量食雙星校準星數） | Gate 1：形式範圍通過，科學精度未通過。Gate 2：通過 |

empirical_ml_relation_test：建一條獨立於等時線模型的經驗質量-光度
關係，檢查低質量段 alpha 對「用不用等時線」的敏感度（見
LIMITATIONS.md D11）。查證前兩道 gate：Gate 1（Gaia→Johnson V 紅端
適用性）——Gaia EDR3 官方 G−V 公式的形式涵蓋範圍包含 M45 全部顏色，
但官方文件沒有 BP−RP=2.4–3.5 的 dwarf-only 殘差，紅矮星科學精度尚未
驗證；Pancino et al. (2022) 的 V−G 轉換式列為待驗證候選。Gate 2
（Torres 2010／Benedict 2016／Iglesias-Marzoa 2017 低質量校準星數）
——Benedict 2016 單篇有 39 顆 M<0.4 M☉ 且附 M_V 的分量，三篇文獻尚未
合併成單一已驗證樣本。詳見 `docs/reports/D11_經驗質光關係_覆蓋範圍
查證.md`。尚未建質量表，也未重算 IMF。下一步是補齊逐星資料與紅矮星
轉換殘差。
兩道 gate 都只是文獻前置查證，**還沒有蒐集資料、寫實作或重算 IMF**，
下一步是補齊逐星資料與紅矮星轉換殘差。耗時未查證。

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
結論；目前規劃使用 40k、至少 5 個 paired seeds，正式需求仍待完整驗證。耗時未查證。

## 未來規劃與分工建議（2026-08-26，依 LIMITATIONS.md 現役缺陷優先度排序）

這節是**建議的執行順序跟資源分配**，不是新的待辦項目——所有提到的任務
都已經在上面「待辦事項」表裡，這裡只是把它們按優先度分成三個階段、並
針對現在兩個算力池（gcp1；Kaggle 多帳號，共 6 個帳號）的實際使用狀況給派工建議。
認領某項工作時還是照規則 2 把對應行的狀態改成「進行中」，這節不重複
那些欄位。

**第一階段（現役缺陷．優先度最高，直接影響「這是 PDMF 不是 IMF」這個
最核心的主張）**：
1. `limepy_radial_crosscheck` 補做正式版——B5 的探索性版本
   （2026-08-20，用 `_prelim`）已經做過方向性比對，但 A5 真正的解除
   條件要求用 `radial_final_reruns` 的 `_final` 誤差棒版本重做，這步
   目前還沒有人排。是純比對計算，不需要重新起跑合成星團，任何一台
   閒置的雲端 worker 都能做，優先度最高但成本最低，建議最先認領。
2. `nbody_prior_from_radial` 的初步校準網格——A5 解除條件的另一半
   （第 5 步 N-body 交叉驗證），前置的三個定義不一致已解決，缺的是
   真的跑一組小規模模擬網格。跟第 1 項不衝突，可以平行進行。
3. `extinction_form_test`（C5，現役缺陷．優先度高）——已排入 gcp1 佇列
   （`c5_davform_lognormal`／`c5_davform_truncexp`），不用重新排，等它
   跑完直接看結果、寫進 LIMITATIONS.md C5。

**第二階段（現役缺陷．優先度中高，各自獨立不互相依賴，可以分給不同人
／機器同時做）**：
4. `empirical_ml_relation_test`（D11）——可行性評估已完成，下一步是
   評估文件第三節的五項查證，優先做前兩項（成本最低、可能直接否決
   整條路線）。純文獻查證＋小規模驗證，不需要重量級算力。
5. NGC 3532 暗端選擇函數失敗（D16）與 Praesepe `f_bin` 貼牆（D17）
   ——PR #123／#124（Codex）已經分別診斷出根本原因（NGC 3532：紅藍
   誤差差非顏色相依的普遍現象，控制場本身的代表性才是問題；
   Praesepe：暗端 CMD 形狀失配 0.511 mag 中位數把 f_bin 推到上界），
   這兩個 PR 合併後，D16／D17 的「下一步」要跟著更新成這兩個診斷的
   後續修正動作（NGC 3532 要重新檢查控制場代表性本身；Praesepe 要
   查暗端形狀失配的來源——年齡/消光/距離模數系統誤差，還是等時線
   本身在這個質量段不準）。**這兩項建議認領前先看 PR #123／#124
   合併後的最新診斷內容，不要照這節寫的（可能已過期）舊描述動手**。
6. `bhac15_isochrone_test`（D1）——網格已備妥，但 2026-08-21 記錄
   「正式規模比較已跑、但撞牆無法產出可信數字」，這代表單純重跑
   同一個指令不會有用，需要先查證撞牆的原因（等時線涵蓋範圍不夠、
   還是擬合設定本身的問題）才能真的解掉 D1。

**第三階段（結構性補強與敏感度測試；`p6_lowmass_v3` 目前尚未證明會
改變頭條中心值，但可能改變誤差預算與 alpha 的解讀——LIMITATIONS.md
A3 已記錄低質量段冪次固定是目前最大的單一系統誤差來源，這一項完成
前不能宣稱「不影響結論」；論文也需要誠實揭露這些還沒測過）**：
7. `p6_lowmass_v3`、`mass_dependent_fbin`——已經排在 gcp1 佇列裡
   （依序執行）；`configCD_real_data_compare` 改派到 senior24
   平行跑。三項都不用額外動作，跑完後直接寫結果進 LIMITATIONS.md
   對應條目。
8. `p6b_inject_lowmass_v2` 的 Kaggle 三分片（`justinlan11`／
   `teammate2`／`helmetalbert`）——已經排進 `cloud_queue.txt`（見
   PR #136），還有 `account5`／`account6`／`account7` 三個 Kaggle
   帳號閒置，可以用來認領第一、二階段裡不需要 gcp1 大算力的項目
   （例如 `stars_per_cluster_sensitivity` 如果找得到有 pyUPMASK
   環境的機器、或 `extra_scatter_sensitivity`、`pyupmask_completeness_test`
   寫完腳本後）。
9. 多星團驗證軸（`praesepe_pr11_close_out` → `comaber_tier1`）——
   這條線本身有硬相依，PR #11 現在已經合併進 main（見 D8 已解決），
   所以 `praesepe_pr11_close_out` 剩下的其實只是「拿 PR #123／#124
   的診斷結果，決定 Praesepe／NGC 3532 現在的狀態算不算數」，不是
   「合併 PR #11」這件事本身（那已經做完了，這行任務描述已過期，
   認領前先讀 D8／D16／D17 現在的內容）。`comaber_tier1` 要等前一項
   確認完才能真的動手，且動手前還缺 Kraus & Hillenbrand (2007) 的
   正確原文（The Astronomical Journal, 134, 2340），需要使用者提供。
10. `bp15_bp20_paired_comparison`——派工前置檢查已完成，缺的是
    Kaggle 帳號憑證真的送出正式規模長跑，現在 Kaggle 帳號已經在用
    （見第 8 點），排隊順序上可以排在 p6b 三分片後面。

**沒有列進以上三階段、但 LIMITATIONS.md 裡還開著、目前無人認領的
「尚無認領工作」項目**（C2、C4、C6、C7、C9–C12、C14–C17、C21、B2–B4、
D3、D4、D13）：這些是已知但沒有列優先度的結構性限制，不建議現在主動
排時間投入——優先度排序見 LIMITATIONS.md 本身的分級（C 類是「修不掉、
論文必須聲明」，D 類是「已知風險、尚未驗證但沒有污染現有結果的證據」），
等第一、二階段的現役缺陷都解決、或有人主動想認領才處理。
