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

本機、Kaggle 多帳號、GCP SSH worker gcp1 是三個獨立但要互相避開的
算力池（`queue.txt`／`kaggle_queue.txt`／`cloud_queue.txt`），排新
工作前先確認同一件事沒有同時排在另外兩個佇列檔裡。本機用
`restart_queue_on_boot.ps1`（登入時觸發）加
`M45-QueueWatchdog-15min`（每 15 分鐘一次）兩個排程任務互相補位，
偵測到 `run_queue.py`／`cloud_queue.py` 沒在跑就自動重啟；若某次巡檢
發現排程任務不存在了，重新註冊即可，指令見該腳本開頭註解。gcp1
目前派工的 `d2_membership_threshold_p06_p07_retry` 是否已經算完，
以 `logs/cloud_queue_done.txt`／`results/` 目錄實際內容為準，不要
假設已經成功——之前兩次都是看起來已派工但實際沒跑起來，是新
worker 缺本機專屬資料造成的，這個坑以後可能在別的資料檔上重演。

## 待辦事項

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|
| p6_lowmass_v3（A1、A3） | 尚未進行 | 指派時間：2026-08-21 | profile_lowmass.py --procs 8 --n-syn 40000 --repeats 3 --refines 3,3 | results/profile_lowmass.npz |
| p6b_inject_lowmass_v2（A1） | 尚未進行 | 指派時間：2026-08-12 | inject_lowmass.py --procs 8 --n-syn 40000 --trials 3 --refines 3,3 | results/inject_lowmass.npz |
| limepy_radial_crosscheck（A5、B5） | 進行中 | 開始日期：2026-08-24 | results/limepy_multimass.npz、results/fit_real_radial_r1_final.npz、results/fit_real_radial_r2_final.npz、results/fit_real_radial_r3_final.npz、results/fit_real_radial_rall_final.npz | results/limepy_radial_crosscheck.json（正式 `_final` 誤差棒對照） |
| nbody_prior_from_radial（A5） | 尚未進行 | 指派時間：2026-08-12 | mcluster_sse -N 400 -S 0.3/0.5/0.7（各跑數組，圍繞 pilot 參數 -P 0 -R 2.3 -Q 0.5 擾動） | nbody_setup/ 下的模擬網格輸出（檔名依 nbody_setup/README.md 命名慣例，尚未產生） |
| pdmf_step4_radius_expansion（A5） | 尚未進行 | 指派時間：2026-08-12 | config.toml [target] radius_deg 改為 8–17°；scripts/data_prep/fetch_gaia.py → scripts/drivers/run_pipeline.py 第 1–5 步 | 新的 data/cmd_members.csv 與 results/ 下對應的第 1–5 步輸出（含 pyUPMASK 六格驗證圖） |
| bhac15_isochrone_test（C1、D1） | 尚未進行 | 指派時間：2026-08-16 | fit_real.py --grid bhac15_gaia_logt7.6-8.4.dat --procs 8 --n-syn 40000 --repeats 5 --configs A,C | results/fit_real_bhac.npz（規劃中的檔名，比照 fit_real_dr2.npz 命名慣例） |
| sensitivity_sweep_membership_threshold（D2） | 進行中 | 開始日期：2026-08-24 | scripts/diagnostics/sensitivity_sweep.py --target membership_threshold --values 0.5,0.8,0.9 --procs 4 --n-syn 40000 --refines 3,3 | results/sensitivity_membership_threshold.npz（0.6／0.7 兩點已寫入，這批補上 0.5／0.8／0.9） |
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

limepy_radial_crosscheck：認領人：Codex 本機 session（分支
`codex/limepy-radial-crosscheck`）。LIMEPY 多質量平衡模型本身已經擬合完成
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

sensitivity_sweep_membership_threshold：認領人：本機 Claude session，
透過 gcp1（GCP e2-highcpu-8）派工。量成員判定門檻
（membership_threshold）對頭條數字的敏感度，這是 D2 待補齊的敏感度
測試之一。第一批（0.6／0.7）已於 2026-08-24 在 gcp1 實測完成，耗時 600.4
分鐘（約 10 小時），結果見 results/RESULTS_LOG.md 同日期那行：門檻
從現行預設 0.7 放寬到 0.6，成員數 1,297→1,308（測光篩選後 n_obs
1,078→1,087），alpha 完全不變（2.367→2.367，跨度 0.000，對照注入
回收統計誤差 0.144 為 0 倍）。但有重要但書（2026-08-24 CodeRabbit
review 指出）：兩個門檻都沿用同一份用 0.7 樣本迴歸出的
selection.npz，沒有隨門檻重新迴歸選擇函數係數，這個簡化可能讓量出
的敏感度系統性偏低，只能說「固定 selection 係數的條件下，0.6–0.7
沒有偵測到 alpha 變化」，不能下「membership_threshold 不是重要誤差
來源」這種無條件結論，完整訂正見 LIMITATIONS.md D2 同日期段落。剩下
三個門檻（0.5／0.8／0.9）已排入 cloud_queue.txt 等 gcp1 執行，同樣
沿用這份 selection.npz，不會單獨解決上述但書。另一個掃描目標
stars_per_cluster 需要真的重跑 pyUPMASK 聚類，這台機器沒有
pyUPMASK 環境，留給有環境的人。

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

bp15_bp20_paired_comparison：檢查放寬 BP 誤差門檻（BP15 vs 現行
BP20）找回的紅端候選星，納入後對 alpha 頭條數字有沒有實質影響。
派工前置檢查已完成（10 個唯一 job tag、82.2 MB 暫存 payload 已驗證
可被 kernel 讀取），彙整器設計為缺任何配對就拒算平均（fail-closed）。
本機目前缺 kaggle_accounts.json／access token，還沒送出雲端長跑。
先前的探索性 smoke test（3 個 3k paired seeds）顯示 alpha 差仍不
穩定，不能下科學結論，正式比較需要 40k、至少 5 個 paired seeds。
耗時未查證。
