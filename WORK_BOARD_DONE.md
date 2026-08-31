# 已完成事項存檔

這份只放完全完成的工作。還在進行中、暫停中、或等待交接的工作一律
留在 `WORK_BOARD.md`，標記「進行中」或「尚未進行」，不會出現在這裡
——搬過來就代表任務本身已經做完，不是「做了一部分」或「等後續」。
完整規則見 `CONTRIBUTING.md` 零之四。

每個任務是一列表格（任務名稱、完成日期、輸入參數、輸出參數）加上
底下一段結論文字：這次跑出了什麼、之後會在哪裡被用到、對這個專案
有什麼幫助。不記錄過程細節（誰跑的、卡在哪裡、改了哪些檔案）——
那些屬於當時的工作紀錄，這裡只留結論，需要完整過程的話去查對應
的 PR／commit 歷史。

## 完成事項

**2026-08-23 建立**：從 `WORK_BOARD.md`（當時已經 449 行、歷史紀錄跟
待辦事項混在一起，越來越難看出「現在到底剩什麼還沒做」）拆分出來。
`## 紀錄`／`## 紀錄（續）`兩張表是原封不動搬過來的（append-only 歷史
留痕，不改舊行，規則跟原本一樣，見上面第 1 點）；另外把當時
`WORK_BOARD.md` 待辦表格裡**已經標明完成、但因為文件本身是「只附加
不回頭改」的格式而從沒被劃掉或搬走**的行，一併整理過來歸檔（上面
第 2 點）——這些行本來就已完成，只是舊格式沒有「完成後搬到別的地方」
這個機制。**這是一次性的拆分整理，不代表逐項重新查證過每一行的真實
現況**；個別行內文字裡若提到「還有後續」「仍待做」，那段文字保留
原樣，不代表真的已經沒有任何後續工作，讀備註欄本身的說明為準。

## 紀錄

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|
| 2026-08-11 13:35 | Claude session（本機） | 多星團 Tier1：NGC 3532／Praesepe 起頭 | 暫停（卡住） | `cluster_imf_tier1.py`、`data/hr23_*`，commit `4fd8c67` | 已抓 HR23 成員表並存檔，PARSEC 等時線服務（stev.oapd.inaf.it）連續 6 次 SSL 交握斷線，卡在這裡；`LIMITATIONS.md` 已記錄，含之後要重跑的指令 |
| 2026-08-11 19:31–20:14 | Codex | 多星團通用性驗證：NGC 3532／Praesepe（Tier1 傳統法 + Tier2 前向模型全套） | 完成，PR #11（draft，待審） | `cluster_imf_tier1.py`（延伸）、新增 `prepare_cluster_tier2.py`、`cluster_forward_validation.py`、`MULTICLUSTER_VALIDATION.md`，分支 `codex/ngc3532-praesepe-generalization` | **接續上一行**、不是獨立重做——用本機已快取的等時線網格繞過 PARSEC 卡點（沒有重新呼叫 PARSEC 服務），把 Tier1 沒做完的補完，還加了 Tier2（Gaia crossmatch＋誤差模型＋選擇函數＋完整 JointModel 前向模型）。這條在 PR 審查通過前先標記，之後補結論 |
| 2026-08-12 | Claude session（本機） | 建立本工作認領表，回填上面兩筆已知的重疊/接續紀錄 | 完成 | `WORK_BOARD.md`（新檔） | 起因：使用者發現 Codex 的 PR #11 跟自己稍早的多星團工作動到同一個檔案，追問是否重複；查證後確認是接續而非重工，見上兩行 |
| 2026-08-12 | Claude session（本機，交接給另一台電腦的 agent） | Kaggle dataset 掛載問題根因排查（見 `LIMITATIONS.md`「Kaggle 掛載問題根因排查」一節） | 交接中，等另一台機器用不同帳號接手 | `LIMITATIONS.md`、`kaggle_queue.txt`、`kaggle_sync.py`（已加 in-kernel 等待，不用再改）、`kaggle_accounts.json`（不進版控，新 agent 要自己建） | 本機已排除「純時序」「帳號未驗證」兩個假設；使用者實測發現 Kaggle 網頁版 Notebook Editor 本身卡在「Editor loading」，換瀏覽器/無痕都無效，懷疑是 Kaggle 平台（可能是 Firebase 服務）暫時異常，不是帳號或我們程式的問題，但這個假設也還沒證實。**交接給另一台電腦、用另一個 Kaggle 帳號**測試是為了排除「同一帳號被限制」這個殘餘可能性，兩台機器同時測也能交叉驗證是不是平台性問題。新 agent 開始前**先讀 `LIMITATIONS.md` 那一節的完整診斷過程**，不要重新從頭排查已經排除的假設 |
| 2026-08-12 | Claude session（新機器，x64，接手交接） | Kaggle dataset 掛載問題根因排查（接續上一行） | 進行中，卡在第 2 點需要真人登入操作 | `LIMITATIONS.md`（已補「2026-08-12（新機器接手交接...）」段落）、`kaggle_accounts.json`（本機新增 `justinlan11` 帳號，不進版控） | 匿名瀏覽器測試部分排除第 1 點（平台前端目前渲染正常，但只測到唯讀頁面）；使用者提供第三個帳號 `justinlan11`（API token），用它重跑 `kaggle_smoketest.py`，**撞到跟 helmetalbert／teammate2 一模一樣的錯誤**（`FileNotFoundError: waited 280s...`），且已核對本機產生的 `dataset-metadata.json`／`kernel-metadata.json` 設定正確，排除「我們自己設定寫錯」。三個獨立帳號都一樣，帳號層級限制的可能性進一步降低。**唯一還沒排除、下一步該做的是第 2 點**（網頁手動 Add Input 測試），需要真人登入操作，AI agent 做不到，回報使用者需要親自測試或提供登入方式 |
| 2026-08-12 | Claude session（新機器，x64） | Kaggle dataset 掛載問題根因排查（接續上兩行，**找到真正根因並修好**） | **完成** | `kaggle_sync.py`（`make_kernel()` 的 `base` 路徑修正）、`LIMITATIONS.md`（新增「2026-08-12：真正的根因找到了」一節，回頭訂正「平台異常」「帳號限制」兩個假設） | 使用者親自登入無痕視窗，手動網頁上傳 dataset＋Add Input＋`os.walk('/kaggle/input')`，印出真實路徑是 `/kaggle/input/datasets/<帳號>/<slug>/`，比 `kaggle_sync.py` 原本寫死的 `/kaggle/input/<slug>/` 多兩層。改一行路徑字串，用 `justinlan11` 帳號重跑驗證：修好前等滿 280 秒才 `ERROR`，修好後 **10.7 秒 `COMPLETE`**。純粹是我們自己的路徑 bug，不是 Kaggle 平台問題也不是帳號限制，這兩個假設已在 `LIMITATIONS.md` 回頭訂正。過程中發現的「頁面崩潰了」React 錯誤是使用者瀏覽器擴充功能干擾，跟這個 bug 無關，已在文件中記錄避免以後誤判成同一件事。`kaggle_queue.txt` 現在可以考慮恢復派工，留給使用者/負責的 session 決定 |
| 2026-08-22 | Claude session（本機） | 新增 SSH 雲端運算節點支援（GCP/Oracle 補充算力，環境設定，不對應 LIMITATIONS.md 條目） | 程式完成，等使用者提供 VM 連線資訊後端到端驗證 | 新增 `ssh_workers.py`／`ssh_workers.json.example`／`ssh_sync.py`／`cloud_queue.py`／`docs/reference/CLOUD_WORKERS.md`，分支 `claude/cloud-workers-ssh-2026-08-22`（PR #103） | 使用者評估 Kaggle 平台不穩（見上方 Editor loading 卡死的相關記錄）後決定補充 GCP $300 試用＋Oracle Always Free。**跟 Kaggle 帳號共用同一個「worker」抽象與同一份佇列檔**（`cloud_queue.py`），不是三套分開的 dispatcher；SSH worker 是持久機器，架構刻意跟 Kaggle 的一次性容器不同（git pull 而非整包重傳，見 `ssh_workers.py` 開頭說明）。VM 只用唯讀 Deploy Key 讀 GitHub，不放可寫入憑證，結果一律本機 scp 拉回。`py_compile`／空佇列 dry-run 已驗證，**SSH 路徑本身還沒有真實帳號可以端到端測試**，這部分留給使用者提供連線資訊後續跑 |
| 2026-08-23 | Claude session（本機） | SSH 雲端運算節點端到端驗證（接續上一行） | **完成**，`gcp1`（GCP e2-highcpu-8）已可正式派工 | `docs/reference/CLOUD_WORKERS.md`（新增「已知陷阱」一節）、`cloud_queue.py`（更新驗證狀態說明），`ssh_workers.json`（本機，含真實 IP，不進版控） | 使用者建好 VM（`asia-east1-c`，e2-highcpu-8）並提供連線資訊，實測 `push`→`run`→`status`→`pull` 全部跑通（`kaggle_smoketest.py` 印出 CPU count=8、numpy 正常運作）。過程中踩到一個先前沒預料到的坑：**GCP 依公鑰結尾的名字建帳號，瀏覽器登入帳號跟 `ssh_workers.json` 指定的帳號如果名字不同會是兩個互相隔離的 Linux 帳號**，各自要分別裝 Python 套件、各自要有自己的 GitHub Deploy Key（各踩了一次 `ModuleNotFoundError: No module named 'numpy'` 跟 `Host key verification failed`/`git clone` 卡住），已補進 `CLOUD_WORKERS.md` 並給出避免的做法（第一次就用同一個帳號名稱操作）。GitHub host key 驗證用了已經被使用者手動核對過的同一把 GitHub ED25519 指紋交叉比對，沒有繞過人工核對這一步。**還沒驗證的部分**：目前只測過輕量 smoke test，長時間、高負載的重運算（例如 `--procs 4` 跑好幾小時）還沒實測過，第一次派正式工作時建議觀察一次記憶體用量 |

## 紀錄（續）

| 日期 | 執行者 | 任務名稱 | 狀態 | 涉及檔案／分支 | 備註 |
|---|---|---|---|---|---|
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步（fetch_gaia → prep → pyUPMASK 第1步 → 第2–5步），跟既有 `results/baseline.dat` 與文件記錄的頭條數字比對，不是新的科學結果 | 進行中 | 先跑到獨立檔名（不直接覆寫 `results/baseline.dat`）比對，一致才決定要不要正式取代；分支 `yutunglan/x64-pipeline-verify` | 這台是 x64（非 ARM64），跟本機 8 核佇列那台不是同一台，不會搶 `queue.txt`。環境建置與 `fetch_gaia.py` 可攜性 bug 已在 PR #15 修好並合併。跟這台機器上同時在跑的 Kaggle 掛載排查（見上面那行）沒有檔案重疊，只是提醒：這台電腦目前有多個 session 同時操作同一個 working directory，git 分支切換偶爾會互相干擾，commit 前務必先確認當下分支 |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 新機器環境驗證：完整跑一次 pipeline 第 0–5 步 | **完成，數字與既有結果一致，未覆寫任何 tracked 結果檔** | 無（`data/`、`results/` 的重跑輸出已 `git checkout --` 復原成 repo 原版） | 逐星比對：兩次跑（同 `random_seed=42`）的 6,956 顆星星集合完全相同，`probs_final` 相關係數 0.9992，P≥0.7 成員數 1,298 vs repo 記錄的 1,297（差 1 顆，落在專案自己記錄的「同種子仍有殘餘隨機性」量級內，pyUPMASK 平行處理沒有被單一種子完全鎖死）。第 2–5 步頭條數字：f_bin=0.45（一致）、四法標記 415/100/58/24（vs 414/100/58/24）、alpha_naive=1.978±0.069（vs 1.980±0.069）、alpha_forward=2.350（一致）、質量分層 α(r) 1.77/2.02/2.12/2.31（vs 1.77/2.01/2.15/2.29）。**結論：pipeline 在獨立的 x64 機器上完全可攜、可重現**，順便在 `prep.py` 修了跟 PR #15 同一種寫死 `gaia-export` 路徑的 bug（`fetch_gaia.py` 那次漏改了這支）。沒有覆寫任何 `results/` 或 `data/` tracked 檔案，這次驗證不影響任何既有結論或數字，所以沒有加 `RESULTS_LOG.md` 條目 |
| 2026-08-12 | Claude session（本機，ARM64 8核） | **PDMF → IMF 這條線**：方法調查、動力學年齡計算、α(r) 梯度實驗、四路線規劃 | 第 1、2 步進行中（第 3–5 步開放認領） | 新增 `PDMF_TO_IMF_PLAN.md`；`fit_real.py` 加 `--radius-range`；`queue.txt` 加 4 個 radial 診斷；分支 `claude/pdmf-to-imf` | 使用者確認「IMF 本來就是專案目標」、四條路線都要做、照合理順序來。**完整計畫與文獻調查見 `PDMF_TO_IMF_PLAN.md`**。關鍵發現：核心-外圍 α 差 0.515，是統計誤差 0.144 的 3.6 倍、比最大系統誤差 0.248 還大，但可能有一部分是雙星比例隨半徑變化的假象（Liu+2025），第 2 步的 radial_r1/r2/r3/rall 就是要分辨這件事。**第 3 步（LIMEPY 多質量平衡模型，純 Python、ARM64 無痛）跟第 5 步（N-body，需要 x64 機器編譯）都還沒人做，跟本機佇列不衝突，歡迎認領** |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | PDMF → IMF 優先度覆核（使用者要求：確認清單完整、把相關項目優先度調到非 A/B 類項目之前） | **完成** | `WORK_BOARD.md`（下面「待認領工作：PDMF → IMF」表新增優先度欄）；`queue.txt` 未變更 | 使用者確認第 13（C21）、14（C22）兩個背景關聯條目**不用一起處理**。逐一核對 `LIMITATIONS.md`（A/B/C/D 分類）、`WORK_BOARD.md`、`queue.txt`、`PDMF_TO_IMF_PLAN.md`、`教學_PDMF轉IMF.md` 後列出完整清單給使用者確認（涵蓋已完成/已排隊/開放認領/背景關聯四類，共 15 項）。**查核結果：`queue.txt` 已經符合「PDMF 相關項目排在非 A/B 類前面」的要求，目前待跑的 `radial_r1/r2/r3/rall` 已經在 A/B 類重跑（`p6_lowmass_v2`／`p11_outlierfrac_v2`）之前，中間沒有非 A/B 類項目，不需要調整順序**。改在「待認領工作：PDMF → IMF」表加優先度欄：第 3 步（LIMEPY）與第 5 步（N-body）標為「可立刻開始」（環境準備／編譯測試不需要等第 2 步結果），第 4 步維持「等第 2 步結果」不變。已確認 `multi_stage_best()` 精修 bug 修復（2026-08-11）確實在目前 `injection_recovery.py` 程式碼中，`queue.txt` 的 radial 診斷都帶 `--refines 3,3`。下一步：向使用者確認要不要開始第 5 步（N-body，這台 x64 機器能做、ARM64 佇列做不到）的環境準備 |
| 2026-08-12 23:30 | Codex session（x64） | PDMF → IMF：LIMEPY 多質量模型環境、逐質量段徑向密度剖面與 smoking test | **進行中** | 分支 `codex/pdmf-imf-overnight`；預計新增獨立環境與診斷腳本，不動 ARM64 `queue.txt` | 使用者要求 PDMF→IMF 優先，至少跑到 2026-08-13 06:00，未完成則持續。先解決 `astro-limepy` 與 SciPy 相容性，再用 `data/cmd_members.csv` 建立模型真正需要的質量分段徑向數密度，不重跑另一台已排定的 `radial_r1/r2/r3/rall`。 |
| 2026-08-12 23:30 | Codex session（x64） | PDMF → IMF：PeTar／替代 N-body 工具鏈可行性與最小 smoking test | **進行中（LIMEPY 後接續）** | 分支 `codex/pdmf-imf-overnight`；不動 ARM64 `queue.txt` | 這台是 AMD64，但未安裝 WSL；先做不改系統設定的工具鏈查核與可重現最小測試。若 PeTar 需要額外系統安裝，先保留可執行環境腳本與明確阻塞證據，再評估純 Python／既有輪子的替代路徑。 |
| 2026-08-13 00:25 | Codex session（x64） | PDMF → IMF：LIMEPY 多質量徑向密度 smoking test | **完成** | `pdmf_limepy_smoke.py`、`requirements-pdmf.txt`、`results/pdmf_limepy_smoke*`、`PDMF_IMF_SMOKING_TEST_2026-08-13.md` | 取代上方 23:30「進行中」狀態。解決 LIMEPY/SciPy 兩項相容問題；2,205 個模型全部收斂；最佳模型 goodness-of-fit 可接受；平衡束縛族群的 5.1° 空間外推只使 α 增加 0.004。沒有重跑 ARM64 的 `radial_r*`。 |
| 2026-08-13 00:25 | Codex session（x64） | PDMF → IMF：N-body 工具鏈與最小 smoking test | **前置驗證完成；正式 PeTar 尚未開始** | `nbody_pdmf_smoke.py`、`nbody_pdmf_ensemble.py`、`requirements-nbody.txt`、`results/nbody_pdmf_*` | 取代上方 23:30「進行中」狀態。本工作區先用原生 Windows REBOUND 跑通已知 IMF→徑向 PDMF 分析鏈及 72 次高精度集合。之後同步發現另一協作者已在分支 `yutunglan/nbody-env-setup` 用 MSYS2/MinGW 編好 PeTar+BSE+mcluster（不需 WSL），所以正式模擬應直接接該環境；REBOUND 結果只作獨立前置驗證，不能定量校正 M45。 |
| 2026-08-13 00:40 | Codex session（x64） | PDMF → IMF：LIMEPY 空間修正 bootstrap | **完成** | `pdmf_limepy_bootstrap.py`、`results/pdmf_limepy_bootstrap*` | 5,000 次逐星重抽，每次重選 735 個結構模型中的最佳解；`Δalpha_spatial` 95% 區間 0.000–+0.014，98.64% 滿足絕對修正小於 0.02。結論仍限定於平衡束縛族群。 |
| 2026-08-13 01:20 | Codex session（x64） | PDMF → IMF：接近觀測樣本量的 N-body 尺度測試 | **完成** | `results/nbody_pdmf_ensemble_largeN*` | N=1,024/2,048 共 32 次，28 次能量通過；通過者 96.4% α 對比增加、92.9% 半徑比增加。訊號隨 N 增大而減弱，符合 relaxation scaling；REBOUND basic O(N²) 約 42 分鐘，正式網格轉 PeTar。 |
| 2026-08-13 01:35 | Codex session（x64） | PDMF → IMF：正式 PeTar M45 參數網格、快照分析器與合成驗證 | **分析流程完成；等待協作者 PeTar 機器跑 125 Myr** | `PETAR_M45_EXPERIMENT.md`、`petar_m45_grid.csv`、`petar_m45_grid.py`、`petar_pdmf_analysis.py`、`results/petar_*` | 逐 ID 分解 survival selection／恆星演化／12.09 pc 視野，使用縮球中心、32 投影、累積與環帶 α；10-run grid 已通過一致性檢查。**更正文獻解讀**：Converse & Stahler 2010 從氣體已驅散後開始，第一批不模擬 embedded gas expulsion；1215 是系統數，中央值須轉為 2369 顆星與 1154 組聯星。合成數字只驗證方向，不是 M45 結果。 |
| 2026-08-13 01:40 | Codex session（x64） | PDMF → IMF：PeTar 多 run 集合彙整與不確定度出口 | **完成（合成管線驗證）；等待正式 run 輸入** | `petar_pdmf_ensemble.py`、`results/petar_pdmf_ensemble_selftest*` | 可彙整任意完成 run 的五項 delta-alpha、16–84% 區間、seed scatter 與投影散布；正式模式預設排除 synthetic 並檢查 run ID/質量範圍，避免把 self-test 混進科學結論。 |
| 2026-08-13 02:00 | Codex session（x64） | PDMF → IMF：PeTar raw snapshot 人工粒子防護 | **完成（官方原始碼規則＋合成測試）** | `petar_pdmf_analysis.py`、`PETAR_M45_EXPERIMENT.md` | raw snapshot 不再把 PeTar 質心／取樣粒子誤當成星；保留真實子系統成員並由 `mass_bk` 還原質量，輸出完整 reader accounting，未知狀態直接拒絕。正式 run 仍須與 status log 的 `N_real`/`N_all` 交叉驗證。 |
| 2026-08-13 02:25 | Codex session（x64） | PDMF → IMF：component／unresolved-system 定義橋接 | **程式與合成驗證完成；等待正式 processed catalogs** | `petar_system_catalog.py`、`pdmf_system_definition_bridge.py`、`results/pdmf_system_definition_bridge_selftest.json` | 可遞迴展平 single/binary/triple/quadruple 並同時計算 component、primary、system-total、photometric beta=2/3/4 修正；前向模型接 primary，傳統質光反推接 photometric。輸入必須明確確認多重度目錄完整，避免漏掉多星系統。 |
| 2026-08-12 | Claude session（新協作者機器，x64，Yu Tung Lan） | 第 5 步（N-body）環境準備：裝 MSYS2/MinGW-w64、編譯 PeTar（含 BSE）+ mcluster，驗證端到端可跑 | **編譯環境完成並已寫成可重現的 `nbody_setup/`；正式模擬仍等第 2 步基準線** | 本機外部工作目錄 `nbody/`（跟這個 repo 平行、不進版控，不是 repo 檔案，內容已釘選 commit 並整理進 `nbody_setup/`）；`WORK_BOARD.md`（第 5 步狀態更新）、`PDMF_TO_IMF_PLAN.md`（第七節新增完整修法記錄）、新增 `nbody_setup/`（`README.md`、`setup_windows_nbody.sh`、兩個 patch、`mingw_compat.c`/`.h`），分支 `yutunglan/nbody-env-setup` | 使用者確認先試 MSYS2/MinGW（不用 WSL，因為這台機器同時有其他 session 在跑，重開機風險太大）。`winget install MSYS2.MSYS2` + `pacman` 裝 `mingw-w64-x86_64-toolchain`／`gcc-fortran`／`cmake`／`gsl`／`autoconf`／`automake`／`libtool`，全程不需要重開機、沒有干擾同機其他 session。Clone FDPS（pin v7.0）、SDAR、PeTar、mcluster 四個 repo 到同一層目錄，commit 已釘選（見 `nbody_setup/README.md`）。**踩到兩個真的 Windows 可攜性問題，都修好了**：(1) PeTar 的 `configure` 其實本來就有 `Cygwin*` 或 `Mingw*` 的 Windows 分支，但 MSYS2 的 `uname` 回傳全大寫 `MINGW64_NT-...`，大小寫不匹配被誤判成不支援的 OS，改一行 case pattern 就過；(2) mcluster 用了 MinGW runtime 沒有的 glibc 擴充函式 `srand48`／`drand48`／`feenableexcept`，寫了一個小型相容層（標準 rand48 LCG 演算法）補上。**驗證**：`petar.omp.avx2`（純重力）與 `petar.omp.avx2.bse`（含 BSE 恆星演化）都編譯成功且能正確執行物理積分——1000 顆星 Plummer 模型測試，能量守恆誤差 ~2.5e-5、角動量守恆誤差 ~1e-10；`mcluster_sse`（Kroupa IMF + Kroupa/Sana 聯星週期分布）也編譯成功，並跑通 `mcluster_sse` → `petar.init` → `petar` 全鏈（100 顆星，25 組聯星，含 BSE，exit code 0）。**兩個外部工具的原始碼修改原本只在本機工作目錄，CodeRabbit review 後已補上釘選 commit + patch 檔進這個 repo 的 `nbody_setup/`，讓別人可以重現，不用重踩一次**。**這批只驗證了「能編譯、能跑」，不代表可以直接開始正式模擬**——正式模擬要等第 2 步觀測基準線出來校準，且 Converse & Stahler (2010) 模擬的是氣體驅離後、已達 virial 平衡的狀態，不含胚胎星團／氣體動力學階段本身（該文獻明講留給未來工作），準備初始條件時要分清楚 |
| 2026-08-13 | Claude session（新協作者機器，x64，Yu Tung Lan） | 第 5 步（N-body）第一個 pilot 模擬：用查證修正過的 Converse & Stahler (2010) 參數跑一次 125 Myr，分析 alpha(r) | **完成，方向跟觀測一致，但明確不是正式結果** | 本機外部工作目錄 `nbody/run_pleiades_pilot/`（不進版控）；`nbody_setup/analyze_alpha_r.py`（新增，可重複使用的分析腳本，已改成用環境變數 `NBODY_INSTALL_PATH` 而非寫死路徑）、`WORK_BOARD.md`（第 5 步狀態更新），分支 `yutunglan/nbody-pilot-run` | 使用者指示「先繼續跑正式模擬」。**初始條件**：`mcluster_sse -N 400 -P 0 -S 0.5 -R 2.3 -Q 0.5 -f 1 -b 0.65 -t 0 -e 0 -Z 0.02 -s 42 -u 1 -C 5`——用 `PDMF_TO_IMF_PLAN.md` 第七節查證修正後的參數（400 顆星、`-b 0.65` 即 65% 的星處於聯星系統，等於 0.5×400×0.65=130 組聯星（260 顆聯星成員）+ 140 個單星系統 = 270 個系統；260 + 140 = 400 顆星，質量分層度 0.5、virial 平衡 Q=0.5），IMF 用這個專案標準的 Kroupa (2001)（**不是**文獻原本用的 lognormal-Salpeter，mcluster 沒有現成對應選項，記在這裡避免以後誤以為完全複製了文獻設定），無潮汐場（簡化，未來要補）。**跑法**：`petar -u 1 -b 130 --bse-metallicity 0.02 -t 125.0 -o 5.0`，用 `nohup ... & disown` 真正 detach 成獨立行程，不受單一指令逾時限制，背景監控輪詢完成（過程中 `pgrep` 在這個 MSYS2 環境不存在，第一版監控腳本誤判「已結束」，改用 `tasklist` 與 log 內容判斷後修正，記錄避免下次重踩）。t=20–25 Myr 有一次真實的強交會/併合事件（1 顆系統被彈出，`N_remove` 從 0 變 1，能量記帳項單步跳到 0.34，但這是 SDAR 演算法正確記錄的物理事件，不是數值錯誤——之後每步的瞬時能量誤差立刻恢復到 ~1e-4 量級，只有累積誤差項留著這次事件的痕跡），模擬順利跑完全程 125 Myr（`FDPS has successfully finished`）。**分析**：用 `petar.data.process -i bse` 正確分離單星／聯星質心（不是直接讀原始 snapshot，避免重複計算聯星成員），質量-半徑用 `pipeline/step5_imf.mle_powerlaw()`（跟這個專案分析真實觀測資料同一套函式）算，質量範圍 0.1–2.0 M☉（跟專案一致），半徑用密度中心距離、依三分位數分箱，排除 >20 pc 的動力學彈射星（125 Myr 中確實有 83/275 顆跑到 20pc 外，其中一顆在 t=125 時已經在 67,080 pc 外——這是強交會彈射的真實產物，不是 bug，但也是提醒 N=400 這種小系統的蒸發率可能偏高，需要在多次重複跑時量化）。**結果：alpha(r) 從核心 0.879±0.158（r<6.5pc）升到外圍 1.316±0.157（r 11–20pc）**，跟 M45 觀測到的質量分層方向（核心 1.77 → 外圍 2.29，一樣核心較平）**定性一致**，是這條路線第一次拿到跟觀測同方向的動力學預測。**CodeRabbit review 抓到一個真的 bug（2026-08-13 修正）**：`analyze_alpha_r.py` 原本對 `.single`/`.binary` 檔案的位置又減了一次 `data.core` 的密度中心，但 `petar.data.process`（`tools/data_process.py`）存檔前內部已經呼叫過 `correctCenter()`，等於重複扣了兩次——實測 `.single` 位置的中位數落在 (0.28, 0.21, 0.07) pc、非常接近原點，不是核心座標 (2.45, -3.50, -2.36)，直接證實這個檔案本來就已經是密度中心座標系。修好後（不再重複扣）重跑分析，alpha(r) 的**方向與量級結論不變**（核心較平、外圍較陡的定性一致仍然成立），但精確數字從舊版的 0.81/0.98/1.37 改為修正後的 0.879/0.934/1.316，這裡記的是修正後的版本。**明確保留態度**：這是單次、270 個系統（少於文獻最佳擬合的~400 個系統，這個文獻數字本身也還沒查證到 Table 1 精度）、Kroupa IMF（非文獻 IMF）、無潮汐場的示範跑，alpha 絕對值不能跟觀測數字比大小或引用，只能看方向；正式版要等第 2 步基準線出來後才能真的定初始條件，且需要多次重複（文獻用 25 次平均）才能報統計誤差。**CodeRabbit 第二輪 review 又抓到兩點**（2026-08-13 一併修正）：(1) `analyze_alpha_r.py` 的徑向分箱每一箱都用 `>=`／`<=` 雙閉區間，理論上會讓剛好落在百分位邊界上的星被兩個相鄰箱重複計數——查了 pinned commit 的 mcluster 原始碼確認 `-b` 定義後，也重新驗證這次跑沒有星剛好卡在邊界（修正後數字不變），但已改成除最後一箱外都用右開區間，避免下次真的踩到；(2) 上面「130 組聯星=65%」原本的寫法容易讓人誤解 65% 是系統數的比例，CodeRabbit 直接查了釘選版本的 mcluster 原始碼確認 `-b` 定義是「星處於聯星的比例」，已改成上面這行更明確的寫法 |
| 2026-08-13 | Claude session（新協作者機器，x64，Yu Tung Lan） | Kaggle 多帳號正式派工啟動：`multi_stage_best()` 精修 bug 修好後最優先的四個重跑（`p2_final2_v3`、`p9a_redo_v2`、`p9c_redo_v2`、`p6b_inject_lowmass_v2`，見上面「待認領工作」表） | **進行中**（`kaggle_queue.py` 已在本機背景啟動，跑到全部完成或逾時為止） | `kaggle_queue.txt`（新增 4 項）、`kaggle_accounts.json`（本機新增 `teammate2`／`helmetalbert`，連同先前的 `justinlan11` 共三個帳號，不進版控）、本機補下載兩個 isochrone 網格（`parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat`、`mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat`，不進版控） | 前提：Kaggle 掛載路徑 bug 已修好（見上面條目與 `KAGGLE_DIAGNOSIS.md`），三個帳號（`justinlan11`／`teammate2`／`helmetalbert`）都已個別用 `kaggle_smoketest.py` 驗證成功（10–23 秒完成，見 `logs/kaggle_queue_done.txt`）才啟動正式派工，不是盲目重新開始。四項工作對應 `WORK_BOARD.md`「待認領工作」清單裡優先度最高的重跑，`--procs` 改成 4（Kaggle 免費 CPU-only 核心數，不是本機 8 核）、`--extra` 帶上 `fit_real.py`／`inject_lowmass.py` 需要的頂層依賴（`measure_overconfidence.py`、`injection_recovery.py`）。帳號欄留空，`kaggle_queue.py` 的槽位模型會自動輪流指派。**這是本機 8 核佇列（`queue.txt`）以外的獨立派工，不會搶那條佇列的算力**，跑完會 pull 結果、視情況 commit 進 `results/` 並更新 `RESULTS_LOG.md`／`LIMITATIONS.md` |
| 2026-08-13 | Claude session（本機） | 把 B/C/D 類尚未認領工作的項目逐一查證／補上腳本（使用者要求） | **完成一輪，詳情見下方新表與各項變更** | `inject_lowmass.py`（加 `--tag`）、新增 `check_white_dwarf_contamination.py`、`check_poisson_vs_multinomial.py`、`scripts/data_prep/gaia_radial_velocity.py`、`LIMITATIONS.md`（新增 A6，刪除已解決的 D7／B4，更新 C3／C20）、`RESOLVED.md`（新增 B4 條目） | 逐條查證結果：**(1) D6 直接修好**——`inject_lowmass.py` 沒有 `--tag`，每次重跑覆寫同一個檔案，加了旗標（跟 `fit_real.py` 同款式），不用再排進待辦。**(2) D7 查出真的有問題，升級成 A6**——用新腳本 `check_white_dwarf_contamination.py` 比對 Gentile-Fusillo+2021 白矮星目錄，`data/cmd_members.csv` 裡 `source_id=66697547870378368` 確認命中（Pwd=0.999），且這顆星的 G=16.586 落在擬合質量範圍內，代表**現在就在每次頭條擬合的樣本裡**，不是假設性風險，見 `LIMITATIONS.md` A6。**(3) B4 查出根本不成立，直接解決**——`check_poisson_vs_multinomial.py` 用代數推導＋數值驗證證明目前 `poisson_loglike()` 的實作（因為 `hess()` 把模型直方圖正規化到總和=1）跟真正的多項分布概似只差一個 theta 無關的常數，argmax／後驗形狀完全相同，已搬進 `RESOLVED.md`。**(4) C3 用 `gaia_radial_velocity.py` 拿 Gaia 官方徑向速度做了第一次真正獨立於自行/視差的成員交叉核對**：499/1078 顆有 RV，中位偏差只 +0.14 km/s（整體一致），但 56 顆（11.2%）偏離 bulk_rv 超過各自誤差棒 5σ，且不能用 Gaia 自己的 `non_single_star` 旗標或 `rv_nb_transits`（transit 數）解釋，是一個目前沒有解釋、但也沒有證據污染現有頭條數字的開放問題，列進待認領工作 `rv_binary_investigate`。**(5) C20 查證途中發現一個誠實的失敗**：想用同一支腳本順便查 C20 的「20 顆判定分歧」，但 `comparison.csv` 重新算出來的分歧集合是 367 顆，跟「20」對不上（定義不同），沒有真的查到那 20 顆，如實記錄在 C20 條目，列進待認領工作 `c20_reconcile_disagree_set`。**(6) C1/D1（BHAC15）、D2（敏感度掃描）、D5（p6b4 邊界補測）、C5（消光分布形式）、C8（pyUPMASK 完整度）、C13（注入回收偏差地板）、C18（顏色相依選擇函數殘留）、C19（自轉/前主序光變額外散布）** 這 8 項評估後認為屬於「真的有事可做，但需要更審慎的設計或較長算力，不適合這次順手寫完」，寫成待認領工作規格（見下表），不是隨便掛個空任務。**(7) 其餘標「尚無認領工作」但後果段本身已寫明是接受/結構性/已決定的條目**（C2、C4、C6、C7、C9、C10、C11、C12、C14、C15、C16、C17、C21、B3 等）**維持原樣不動**——這些條目的 `**後果**` 段落本身就是它們的結論，不是缺工作，硬掰一個工作項目出來會違反「不要為了交差而先生出數字」的原則，見各自條目內文 |
| 2026-08-13 | Claude session（新協作者機器，x64，Yu Tung Lan） | PDMF → IMF 第 3 步：LIMEPY 多質量平衡模型（A5） | 進行中 | 待定，分支 `yutunglan/limepy-step3` | 使用者要求核對 `WORK_BOARD.md` 是否有還沒做的工作、且不能跟目前 Kaggle 正在跑的 4 項重跑（`p2_final2_v3`／`p9a_redo_v2`／`p9c_redo_v2`／`p6b_inject_lowmass_v2`）重疊。核對結果：待辦清單裡其餘項目都已被 Kaggle 或本機 8 核佇列（`queue.txt`）認領，只有第 3 步（LIMEPY）真正還沒人做、且明確標「可立刻開始」，不碰 `fit_real.py`／`inject_lowmass.py`／任何 Kaggle 基礎設施。**已知第 4、5 步的完整驗收標準（跟第 2 步 `radial_r1/r2/r3/rall` 的 α(<r) 比對）要等第 2 步結果才能真的達成**——第 2 步目前還在 ARM64 機器的 `queue.txt` 裡排隊，這條工作會先完成環境建置與模型本身，完整驗收留到第 2 步結果出來後再補 |
| 2026-08-13 | Claude session（新協作者機器，x64，Yu Tung Lan） | PDMF → IMF 第 3 步：LIMEPY 多質量平衡模型（A5，接續上一行） | **環境問題解決、第一次擬合跑完；完整驗收仍等第 2 步結果** | `scripts/diagnostics/limepy_multimass.py`（新增）、`results/limepy_multimass.npz`、`results/RESULTS_LOG.md`、`LIMITATIONS.md`（新增 D9）、`docs/planning/PDMF_TO_IMF_PLAN.md`（第七節補上解法與結果）、`.gitignore`（`.venv_limepy/`），分支 `yutunglan/limepy-step3` | **先解決環境問題**：這台機器 scipy 1.18.0 一樣壞（`nsteps` 型別修好後撞到 `dopri5._solout()` 呼叫慣例改變，跟 ARM64 的 1.17.1 錯法不同），Python 3.14 沒有任何舊版 scipy 的 cp314 wheel（要編譯器裝不起來），改用獨立 venv 釘 `scipy==1.16.3`（唯一測過能跑的版本），King/Woolley/Wilson 三種模型形狀都驗證過收斂。**擬合**：用 `results/step5_imf.npz` 現成的 `masses`（跟第 5 步同一套 `assign_masses()`）配 `data/cmd_members.csv` 的 ra/dec 算投影半徑（跟 `run_pipeline.py` 同一個大圓角距離公式，距離 136 pc），依質量切 3 區間各自算環帶數密度剖面，對 King(g=1) 模型擬合：phi0=3.52、r0=2.49 pc、M=534.9 M_sun，reduced chi^2=8.90（**不算好**，見 `LIMITATIONS.md` D9 完整已知限制）。模型潮汐半徑 r_t=20.16 pc（模型內部量，不等於 `dynamics_estimate.py` 算出的 Jacobi 半徑 12.96 pc，兩者概念不同）。**結果：目前 Gaia 樣本邊緣（11.70 pc）到 r_t 之間，模型預測還有 21.2 M_sun（模型總質量的 4.0%）**。**明確保留態度**：初步、方向性估計，質量區間比例直接沿用觀測 PDMF（可能已被蒸發／分層扭曲，這正是這條路線想解決的問題本身），且還沒有第 2 步 α(<r) 觀測結果能交叉驗證（`radial_r1/r2/r3/rall` 還在 `queue.txt` 排隊），數字不能直接引用 |
| 2026-08-13 | Claude session（新協作者機器，x64，Yu Tung Lan） | PDMF → IMF 第 3 步：LIMEPY 多質量平衡模型（A5、B5，接續上一行，**CodeRabbit 抓到真的 bug 並修好，數字更新**） | **完成，擬合品質從「不算好」變「好」；完整驗收仍等第 2 步結果** | 同上分支追加一個 commit | **真的 bug（2026-08-13 修正）**：`limepy_multimass.py` 第一版把 LIMEPY 算出的 `Sigmaj`（質量面密度，M_sun/pc²）直接跟觀測星數面密度（顆/pc²）比較，單位不一致，卡方擬合沒有意義。修法是把 `Sigmaj` 除以該質量區間平均星質量 `mj` 換成星數面密度，`fit()` 也加了「不收斂就丟例外，不要用無效結果」的防呆（CodeRabbit 同一輪一起抓到的次要建議）。**修好前後差很大，證實 bug 確實存在且影響很大**：reduced chi^2 從 8.90（擬合明顯不好）降到 **0.75**（擬合品質好，代表模型跟資料在誤差範圍內相符）；phi0 從 3.52→3.44、r0 從 2.49→2.50 pc、擬合總質量從 534.9→456.0 M_sun、模型潮汐半徑從 20.16→19.26 pc；**潮汐半徑外質量估計從 21.2 M_sun（4.0%）修正為 14.4 M_sun（3.2%）**。**順便訂正另一個附帶說法**：原本說「King/Woolley/Wilson 三種模型形狀擬合出幾乎一樣的結果」，那是被同一個單位 bug 影響下的假象——修好後三者的 reduced chi^2 分別是 Woolley=1.50、King=**0.75**、Wilson=**0.52**，**Wilson 實際上擬合最好**，只是天文文獻慣例上更常用 King，不是因為它是最佳擬合，這裡仍然用 King 當主要引用結果，但已在腳本 docstring／`LIMITATIONS.md` B5 誠實記錄這個訂正。同步把 `LIMITATIONS.md` 的條目從 D9 移到 B5（CodeRabbit指出這個限制會影響已產出結果的大小，不是一般敏感度測試，B 類「每次計算都在用的未驗證假設」比原本的 D 類更貼切——質量區間比例沿用觀測 PDMF 這個假設確實每次跑都在用）。**這裡記的都是修正後的數字，舊數字（534.9／21.2／4.0%／20.16／reduced chi^2=8.90）不要引用**，完整記錄見 `docs/planning/PDMF_TO_IMF_PLAN.md` 第七節與 `LIMITATIONS.md` B5 |
| 2026-08-13 | Claude session（本機） | `wd_exclude_rerun`（A6）：`assign_masses()` 加顏色一致性檢查、量化白矮星混入對頭條數字的影響 | **完成** | `pipeline/step5_imf.py`（新增 `main_sequence_color()`，`assign_masses()` 加可選 `obs_color`/`color_tol` 參數）、`scripts/drivers/run_pipeline.py`（第 5 步接上 `obs_color`）、新增 `check_wd_exclusion_impact.py`（查證用，不寫檔）、`LIMITATIONS.md`（A6 補上量化結果並標記完成、新增 D9） | 使用者原本要求接續跑 PDMF→IMF 第 4 步，但第 2 步（`radial_r1/r2/r3/rall`）還沒跑完，第 4 步的驗收標準（跟第 2 步比對）目前達不到，且第 4 步成本最高、計畫明訂要等第 2 步結果才投入，跟使用者確認後改做其他不衝突的待認領工作，選了優先度標「高——影響頭條數字」的 A6。**做法**：`assign_masses()` 新增顏色一致性檢查，偏離同 G 星等主序色 >0.4 星等回傳 NaN（門檻依據：白矮星偏離 1+ 星等，遠大於未解析雙星典型偏移 <0.2 星等）。**量化結果**（`check_wd_exclusion_impact.py`）：跟前向模型對齊的質量範圍（0.50–2.50，`traditional_accounting.py` 主表用的範圍）下，只剔除這顆已確認白矮星，alpha 從 2.3949→2.4083（+0.013，遠小於統計誤差 0.118），**白矮星混入對已引用頭條數字的影響可忽略，A6 解決**。`alpha_naive`（舊架構，較寬範圍 0.30–2.50）則剔除 13 顆（alpha −0.018），但其中 12 顆不是這顆白矮星（該白矮星質量 0.276 低於這個範圍下限），成因未查證，誠實列成新的 `LIMITATIONS.md` D9，不強行歸因或忽略 |
| 2026-08-13 | Claude session（本機） | `wd_exclude_rerun`（A6，接續上一行，**CodeRabbit 抓到真的分析錯誤並修好**） | **完成，結論更正** | 同一個 PR（#43）追加一個 commit：`check_wd_exclusion_impact.py`（改成逐顆列出實際剔除的 `source_id`，不再只驗證一顆星）、`LIMITATIONS.md`（A6 補三設定對照表並更正結論、D9 改標題與內容） | **CodeRabbit review 抓到**：上一行「跟前向模型對齊的範圍下只剔除這顆白矮星」是錯的——沒有先確認白矮星的假質量（0.276–0.307，依 isochrone 而定）落不落在 0.50–2.50 範圍內就下結論。**查證後發現這顆白矮星根本不在那個範圍裡**（假質量 0.307 < 下限 0.50），對齊範圍下色檢查真正剔除的是**另一顆星**（`source_id=68409590552589184`，alpha +0.013）。改測第三個設定（`traditional_accounting.py` 附錄的較寬範圍 0.30–2.50，同一條 p2_final2 isochrone）才是白矮星真正進入擬合樣本、被色檢查剔除的設定，alpha −0.0097（遠小於統計誤差 0.067）——**A6 的「解決」結論改立在這個設定上，維持成立，但理由跟上一行寫的不同**。順便發現 `68409590552589184` 在三個測過的設定下都被剔除，是比白矮星本身更一致的異常，改寫 D9 聚焦在這顆星、標優先度中，新增待認領工作 `bright_outlier_investigate` |
| 2026-08-13 | Claude session（本機） | `rv_outlier_member_exclude`（A6，接續上兩行，`wd_exclude_rerun` 的剩餘部分） | **完成** | `pipeline/step5_imf.py`（新增 `CONFIRMED_NON_MEMBER_IDS`／`exclude_confirmed_non_members()`）、`scripts/drivers/run_pipeline.py`（第 4、5 步共用的 `ok` 遮罩接上排除）、`scripts/diagnostics/traditional_accounting.py`（真實資料段接上排除）、`LIMITATIONS.md`（A6 補 RV 星與雙排除合併的量化表、標記全部解決） | 使用者確認第 2 步（`radial_r1/r2/r3/rall`）還沒跑完，改繼續完成 `WORK_BOARD.md` 其他待認領工作，直接接續上兩行的 A6。**做法**：這顆星（`source_id=64895139073954944`）顏色正常，`assign_masses()` 的顏色檢查抓不到，需要另一個機制。原本想比照 `check_giant_subgiant_contamination.py` 做即時重算（讀 `data/astrophys.csv`＋`data/radial_velocity.csv`），但 `data/astrophys.csv` 是本機沒有的檔案，產生腳本 `gaia_astrophys.py` 依賴另一台機器（`helmet-png`）本機的外部 TAP 查詢工具（寫死路徑 `C:\Users\Alber\Claude\gaia-export`），這台機器裝不起來、也不該為了一顆星去改別人機器的路徑設定。改用一個小型、有清楚出處的已確認非成員名單（`CONFIRMED_NON_MEMBER_IDS`，附判定依據：logg=4.00、Teff=3317K、RV 偏離 19.5σ），這正是這個任務原始描述建議的「RV 交叉核對名單」做法，不是隨手刪 `cmd_members.csv`。**量化結果**：這顆星在對齊主表範圍（0.50–2.50）外（假質量 0.482 < 下限），跟白矮星一樣完全不影響那個設定；在 `alpha_naive`（0.30–2.50）與附錄範圍都在範圍內，alpha 位移分別 −0.0013、−0.0009，單獨看都遠小於統計誤差。**兩個排除機制（白矮星顏色檢查＋RV 星名單）一起套用**的合計影響：`alpha_naive` −0.0194、對齊主表 +0.0134（跟只做顏色一致性排除時一樣，因為 RV 星在這個範圍外，這個範圍下顏色檢查真正剔除的是 D9 那顆亮星不是白矮星）、附錄範圍 −0.0106，三者都遠小於各自統計誤差 0.067–0.118，**A6 全部解決** |
| 2026-08-13 | Claude session（本機） | `bright_outlier_investigate`（D9，接續上三行，本機可查部分） | **本機診斷完成，身分仍未確認，交接給下一個能連網路的環境** | 新增 `check_bright_outlier_kinematics.py`，`LIMITATIONS.md`（D9 補本機診斷結果）、`WORK_BOARD.md`（本行、任務描述更新） | 繼續 A6 系列做完後，接著查 D9 那顆亮星（`source_id=68409590552589184`）的身分。**做法**：比照 A6 想先查外部目錄（SIMBAD／Gaia DR3），但這台機器對外部服務的 HTTPS 連線遇到 `CERTIFICATE_VERIFY_FAILED`，連不上，改做 `data/cmd_members.csv` 本身就有、不需要網路的檢查。**結果**：RUWE=1.098（乾淨，不像壞解/雙星）、`non_single_star=0`（Gaia 自己沒標記）、BP/RP 測光超額因子 1.262 落在 Evans+2018 標準品質帶 `[1.032, 1.426]` 內（原本猜測顏色異常來自 BP/RP 測光污染，這個假說沒有支持證據）、pmra 偏離其餘成員 0.8σ／視差偏離 1.2σ（都算一致），**只有 pmdec 明顯偏離（3.9σ 全樣本標準差／4.8σ IQR 穩健離散度）**。**誠實結論**：本機能查的線索都查了，沒找到「測光污染」或「壞解」這種簡單解釋，pmdec 有中等程度的運動學異常，但不足以單獨判定身分，**D9 沒有結案，需要外部目錄交叉比對才能真的確認**，留給下一個能連網路的環境接手，不用重跑這幾項本機診斷 |
| 2026-08-13 | Claude session（本機） | `c20_reconcile_disagree_set`（C20） | **完成** | 新增 `check_c20_disagree_set.py`（重建並寫出 `data/comparison.csv`），`LIMITATIONS.md`（C20 補重建結果並標記完成） | 接著查 C20（原本「20 顆判定分歧」定義對不上 367 顆的懸案）。**做法**：在 `_archive/C_membership_phase_analysis/investigate.py` 的 docstring 跟程式碼裡找到原始定義（`my_prob>=0.99` 且完全不在 HR23 成員表裡，母體是 pyUPMASK 全部候選星，不是篩過的 `cmd_members.csv`），用這個 repo 現有的等價檔案（`results/baseline.dat`＋`data/hr23_Melotte_22.csv`，都不需要網路）重跑，**精確重現「20」**。逐顆核對：18 顆已經被後續篩選流程排除、不在現有樣本裡，剩下 2 顆——`63534390354375040` RV 一致（0.1σ）維持成員，`68409590552589184` 就是 D9 那顆亮星。C20 到此解決 |
| 2026-08-13 | Claude session（本機） | `bright_outlier_investigate`（D9，接續上四行，跟 C20 一起解決） | **完成，確認不是成員** | `pipeline/step5_imf.py`（`CONFIRMED_NON_MEMBER_IDS` 加入這顆星）、`LIMITATIONS.md`（D9 改標題與結論、標記完成） | 查 C20 時發現這顆星就在原始「20 顆判定分歧」裡——HR23 完全沒把它收進成員表。順著這條線查 `data/radial_velocity.csv`：**RV=53.062±0.136 km/s（rv_nb_transits=13），偏離 bulk_rv=5.343 km/s 達 350σ**，遠遠超過任何合理的成員判定門檻。三個獨立證據（顏色遠離主序、HR23 完全沒收、RV 350σ）方向一致，**D9 解決：確認不是 M45 成員**。加進 `CONFIRMED_NON_MEMBER_IDS` 當多一層防護（原本三個測過的設定下已經被顏色檢查排除，加進名單後重跑 `check_wd_exclusion_impact.py` 確認三個設定的合計 alpha 完全沒變，只是排除理由從統計判準升級成有 RV／HR23 硬證據支持） |
| 2026-08-13 | Claude session（本機） | `rv_binary_investigate`（C3） | **完成，結論是「不穩定，依假設而定」** | 新增 `check_rv_binary_fraction.py`，`LIMITATIONS.md`（C3 補蒙地卡羅估計結果並標記完成） | 這台機器連不上外部服務，查不到 M45 現成的分光雙星編目，改用 `f_bin=0.45` + 週期分布做蒙地卡羅估計（隨機軌道相位/傾角下 RV 偏移 >5σ 的機率 × f_bin）。**測了兩個週期分布，答案方向不一致**：`WORK_BOARD.md` 原本點名的 Sana+2012（校準給大質量 O 型雙星，短週期為主）算出雙星本身能解釋 27.2%，綽綽有餘蓋過觀測的 11.2%；但 Sana+2012 物理上不對應 M45 主要是 F-K 矮星這件事，改用更貼近的 Raghavan+2010 太陽型場星週期分布（中位周期~300年，RV 半振幅小很多）只能解釋 6.9%，缺口約 21 顆（56 顆的 4 成）解釋不了。**誠實結論**：11.2% 這個數字能不能完全歸給分光雙星高度依賴週期分布假設，不是一個穩定的答案——不能只挑對「沒有污染源」有利的那個分布就下定論 |
| 2026-08-14 | Claude session（本機） | `selection_color_dependence_fix`（C18） | **完成，結論是「現有一維近似沒有被推翻，不用升級」** | 新增 `check_selection_color_residual.py`，`LIMITATIONS.md`（C18 補回歸結果並標記完成） | 重用 `scripts/diagnostics/selection_probe.load()` 的資料，扣掉已被訊噪比切掉的星，依星等分箱、箱內依顏色細分，把存活率對顏色的關係擬合成連續線性函數（不是只有原本那個「G>=17 紅藍落差 0.014」的單一常數）。**結果**：G>=17 子樣本（n=174，跟原本比較基準一致）斜率 −0.0113±0.2131（0.1σ，不顯著）；換全星等範圍的全樣本（n=1,163，檢定力較高）斜率 −0.0054±0.0070（0.8σ，仍不顯著）。**結論**：換大樣本增加檢定力後，顏色對存活率的斜率依然統計上跟 0 無法區分，現有的星等相依一維近似沒有被數據推翻，沒有證據支持升級成二維（星等+顏色）選擇函數——這是「查過、量化、結論是不需要改」，不是「沒查」 |
| 2026-08-14 | Claude session（新協作者機器，x64，Yu Tung Lan） | Kaggle 多帳號正式派工（接續 2026-08-13 認領的那行，**發現並修好 results/ 目錄 bug，用修好版本重跑**） | **P9c v2 完成；P9a-redo v2 與 headline p2_final2_v3 仍在跑** | `kaggle_sync.py`（`results/` 目錄 bug 修正，PR #46 已合併）、`results/fit_real_fixmh_mist_redo_v2.npz`（新增）、`results/RESULTS_LOG.md` | **發現嚴重 bug**：`fit_real.py`／`inject_lowmass.py` 等全部直接假設 `results/` 資料夾存在才能存檔，本機因為 git 版控本來就有這個資料夾所以沒踩到，但 Kaggle 是全新環境，`kaggle_sync.py` 打包時從沒建立這個資料夾——`p9a_redo_v2` 因此跑了 10.5 小時後才在存檔那步炸掉，等於白算。已在 `make_kernel()` 統一補上 `os.makedirs('results', exist_ok=True)`，小規模測試驗證有效，PR #46 已合併。**原本三個正式跑（`p2_final2_v3`／`p9a_redo_v2`／`p9c_redo_v2`）都是用修好前的舊版本**，`p9a_redo_v2` 確認因此錯誤，另外兩個本機監控逾時放棄但 Kaggle 端還在跑——用修好的程式碼重新推送三項（slug 加 `-fixed` 後綴，避免干擾原本可能還在跑的舊 kernel）：`p2-final2-v3-fixed`（justinlan11）、`p9c-redo-v2-fixed`（helmetalbert，**已完成**，logage=7.733/54.1Myr、alpha=2.102±0.102，見 `RESULTS_LOG.md`）、`p9a-redo-v2-fixed`（teammate2，進行中）。詳見 `KAGGLE_DIAGNOSIS.md` |
| 2026-08-14 | Claude session（新協作者機器，x64，Yu Tung Lan） | Kaggle 多帳號正式派工（接續 2026-08-14 P9c 那行，**P9a-redo v2 完成，A4 表 4 穩健性檢驗定案**） | **P9a-redo v2、P9c v2 都完成；headline p2_final2_v3-fixed 仍在跑** | `results/fit_real_fixmh_parsec_redo_v2.npz`（新增）、`results/RESULTS_LOG.md`、`LIMITATIONS.md`（A4 用乾淨數字更新並訂正、A1 表格回頭標記這兩項已重跑確認） | `p9a-redo-v2-fixed`（teammate2）COMPLETE：logage=8.033/108.0Myr、alpha=2.387±0.108，跟 P9c v2（MIST：54.1Myr、alpha=2.102±0.102）比較，年齡差一倍、alpha 差 1.9 倍合併標準誤（CodeRabbit 訂正：這個比值本身是邊緣證據，p≈0.055，真正支持結論的是年齡差一倍這個更直接的證據），**確認 A4「表 4 穩健性主張（年齡一致）不成立」，非精修 bug 造成的假象**。`p2_final2` 吸收 PARSEC 偏差的機制解釋降級為待驗證假說，見 `LIMITATIONS.md` A4 |
| 2026-08-14 | Claude session（新協作者機器，x64，Yu Tung Lan） | `p6b_inject_lowmass_v2`（A1，另一個並行 session 用 `dispatch_new_accounts_tmp.py` 派給 account5，不是這條分支自己派的） | **已取消，待用修正版重跑** | 無（本行純記錄狀態，不涉及檔案異動） | 查詢 Kaggle 狀態發現是 `CANCEL_ACKNOWLEDGED`（被取消，取消者不明，可能是另一個視窗手動操作）。且這個 kernel 用的是 `kaggle_sync.py` 的 `results/` 目錄 bug 修好**之前**的舊程式碼，就算沒被取消、跑完也會在存檔那一步失敗（跟 `p9a_redo_v2` 舊版本同一個下場）。**下一步**：任何人／任何 session 要拿到這項結果，需要用修好版本（PR #46 之後的 `kaggle_sync.py`）重新推送，不要沿用這個已取消的 kernel |
| 2026-08-15 | Claude session（本機） | headline `p2_final2_v3`（A1、A2，接續 2026-08-14 那兩行）：用尚未合併的 PR #55 `--repeat-offset` 拆到 5 個 Kaggle 帳號、拉回並保存已完成的部分 | **5/10 次重複已拉回並保存，還差 5 次；未合併成最終檔案** | `results/fit_real_p2final_v3_rep0.npz` ～ `rep4.npz`（新增，5 個各 1 次重複的檔案）、`results/RESULTS_LOG.md`，分支 `claude/headline-partial-reps`（rep0 的執行 log 存在本機 `logs/kaggle_p2final2_v3_rep0.log`，該資料夾整個被 `.gitignore`，沒進版控） | 直接用 Kaggle API 查即時狀態（不是看本機過期紀錄）才發現：另一個 session／人已經用 `claude/fit-real-repeat-offset` 分支（PR #55，還沒合併）把卡死的 headline 重跑拆成 5 個 kernel（`p2-final2-v3-rep0`～`rep4`，各 `--repeats 1 --repeat-offset {0..4}`），派給 `justinlan11`／`teammate2`／`helmetalbert`／`account6`／`account7`，**Kaggle 端 5 個全部 COMPLETE**，但沒人拉回來合併，本機也完全沒有這 5 個結果檔案（只存在對應 Kaggle 帳號的 kernel output 裡）。已用 `kernels_output()` 全部拉下來、存進這個分支，避免資料再遺失。**下一步**（交接內容，見 `STATE.md`）：(1) 用 `--repeat-offset 5,6,7,8,9` 各跑 1 次補滿剩下 5 次重複；(2) 10 個 `rep*.npz` 的 `C` 陣列沿 axis=0 串接、另存成 `fit_real_p2final_v3.npz`（不要直接覆寫任何 `rep*.npz`）；(3) 更新 `RESULTS_LOG.md`／`LIMITATIONS.md` A1／A2 那兩行，標記 headline 數字正式重跑完成。**這個分支只負責保存已算出的部分，沒有動 `fit_real.py`／`kaggle_sync.py` 等程式碼**，PR #55 合併與否不影響這裡保存的資料 |
| 2026-08-14 | Claude session（新協作者機器，x64，Yu Tung Lan） | headline `p2_final2_v3`（A1、A2，接續 P9a／P9c 那兩行） | **在 Kaggle 上不可行，需要移到本機佇列** | `KAGGLE_DIAGNOSIS.md`（新增章節說明計算量超過 Kaggle session 上限） | `p2-final2-v3-fixed`（justinlan11）跑了 11.4 小時後被 `CANCEL_ACKNOWLEDGED`——log 顯示 10 次重複只跑完第 1 次（單次耗時 40934 秒），換算 10 次要 100+ 小時，遠超 Kaggle 免費 session 上限（9–12 小時）。跟 P9a-redo／P9c v2（同樣 10 次重複但只用雙階精修 `3,3`，數小時內完成）比較，多一階精修（`3,3,3`）就是差異所在。**這個設定不適合排進 `kaggle_queue.txt`，需要在本機 ARM64 8 核佇列（`queue.txt`）重新排隊**，唯一拿到的單次重複資料點（alpha=2.396）記在 `KAGGLE_DIAGNOSIS.md`，不能當 headline 數字引用。順帶查了 `p6b_inject_lowmass_v2`：先前取消後沒有人重推，已用修好版本補推到 account5（`p6b-inject-lowmass-v2-fixed`） |
| 2026-08-16 | Claude session（新機器，Acer AI 16，x64，Yu Tung Lan） | 交接到新機器：環境建置（Python 3.13 x64、核心套件、`.venv_limepy`、PARSEC 憑證鏈、重新產生兩個 Kaggle 派工用 isochrone 網格檔） | **完成** | 無 repo 內程式碼異動（純本機環境設定），`isochrones/`／`.venv_limepy/`／`certs/` 皆 gitignored | 舊機器（x64 協作機）交接 `STATE.md` 後接手。這台機器原本只有 Windows Store 的 python 空殼，裝了正式版 Python 3.13 x64（`winget install Python.Python.3.13`）並確認架構是 AMD64（不是 ARM64，環境建置不用比照 ARM64 那套坑）。裝齊 numpy/scipy/scikit-learn/astropy/matplotlib/emcee/certifi/astroquery/kaggle CLI，建好 `.venv_limepy`（`scipy==1.16.3` + `astro-limepy`，King 模型驗證過可用）。**`kaggle_accounts.json`（7 組帳號 token）刻意沒有搬，這是憑證，交給使用者自行用安全管道傳輸**，本機目前還不能派 Kaggle 工。順手用 `pipeline.isochrones.download_grid()`／`pipeline.mist.build_grid()` 直接重新產生了 `kaggle_sync.py` 需要的兩個網格檔（`parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat`、`mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat`），不用等 Kaggle 憑證就能備妥。確認 PR #57／#55 都已合併，headline `p2_final2_v3` 仍卡在 5/10 次重複（`RESULTS_LOG.md` 最新一行沒有變化，沒人補完）。N-body（MSYS2/PeTar/mcluster 編譯）刻意沒重建——第 5 步本來就要等第 2 步基準線，工程量大不是當前優先 |
| 2026-08-16 | Claude session（新機器，Acer AI 16，x64） | `radial_r2`（A5，接續 `radial_r1_prelim`，PDMF→IMF 第 2 步最大瓶頸）：本機重跑 | **進行中**（背景執行，預估數小時） | `logs/radial_r2.log`（不進版控），分支 `claude/local-queue-radial` | 這台新機器的 `logs/queue_done.txt` 是空的（gitignored，不會跟著 git pull 過去），**不能直接跑 `run_queue.py`**（會從 `queue.txt` 最上面開始，重跑一堆已經完成且結果已 commit 的舊項目）。改成比對 `results/` 目錄現有的 `.npz` 檔案，確認只有 `fit_real_radial_r1_prelim.npz` 存在，`radial_r2/r3/rall` 都還沒人做，直接照 `queue.txt` 裡的指令單獨執行 `radial_r2`。**第一次嘗試用 Bash 工具的 `run_in_background` 啟動，session 中斷時被連帶砍掉**（只跑了幾秒鐘，log 只有開頭幾行，process 已不存在）——推測是背景行程綁在 agent session 生命週期上，不是真正在 OS 層級脫離。改用 PowerShell `Start-Process`（`-WindowStyle Hidden`，重導向到獨立 log 檔）啟動，這樣產生的行程不掛在任何 shell/agent 行程樹下，理論上能撐過 session 交接；確實撐過本次 session 交接還需要之後驗證。跑完後（`results/fit_real_radial_r2_prelim.npz` 出現）要接著跑 `radial_r3`、`radial_rall`（同樣指令模式，只改 `--radius-range` 與 `--tag`），三個都跑完才能連成 alpha(r) 曲線 |
| 2026-08-16 | Claude session（新機器，Acer AI 16，x64） | `bhac15_isochrone_test`（C1、D1，B/C/D 待認領工作表） | **卡住，外部服務目前連不上，非本機/程式問題** | 無檔案異動 | 正確下載網址是 `https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/`（`WORK_BOARD.md` 舊條目寫的 `phoenix.ens-lyon.fr/Grids/BHAC15/` 是錯的，靠 WebSearch 才找到正確路徑）。分別用 WebFetch（Anthropic 端網路）與本機 `pipeline.net.get()` 測試連線，兩邊都是連線逾時（不是 SSL 握手失敗，也不是 404），同時測了 `phoenix.ens-lyon.fr` 根網域一樣逾時，但 `google.com` 正常，排除本機網路/DNS 問題，判斷是 ENS-Lyon 那台伺服器目前真的連不上（跟本專案先前遇過的 PARSEC 服務暫時性斷線是同一類狀況）。**尚未寫 `build_bhac_grid.py`**，下一個接手的人先重試連線，通了再繼續，不用重查網址 |
| 2026-08-19 | Claude session（本機） | 訂正上一行（`radial_r2`）留下的預約式敘述：`radial_r3`／`radial_rall` 其實已經跑完 | **狀態更新，非新工作** | 無檔案異動（純狀態澄清） | CodeRabbit review 提醒上一行只認領了 `radial_r2`，卻在備註承諾「跑完後接著跑 `radial_r3`、`radial_rall`」，其他 session 可能誤以為這兩項還沒人認領而重複啟動。查證 `results/RESULTS_LOG.md`（第 50、51 行）跟本機 `results/` 目錄：`fit_real_radial_r3_prelim.npz`、`fit_real_radial_rall_prelim.npz` 都已存在，是另一台機器（本機 ARM64 8 核佇列，commit `43c8737` 起）稍早／同時完成並已 commit 的結果，不是上一行那台 Acer AI 16 x64 機器跑出來的。**四項徑向診斷（r1/r2/r3/rall）目前全部已有初步值**，不需要任何人再重跑，PDMF→IMF 第 2 步的下一步是等使用者/教授確認方向後，用完整 `--repeats 5 --refines 3,3` 重跑做正式版（見 `results/RESULTS_LOG.md` 第 51 行的說明），不是重跑這四個初步值 |
| 2026-08-19 | Claude session（本機） | PDMF→IMF 第 2 步（徑向診斷 r1/r2/r3/rall）四項全部完成，確認下游第 3–5 步的探索性工作已解鎖（正式門檻仍受限），安排新解鎖的工作 | **狀態確認＋規劃，未跑任何計算** | `WORK_BOARD.md`（本行＋下方步驟表更新＋新增待認領工作） | 使用者確認 `radial_r1/r2/r3/rall` 四項徑向診斷都已跑完。**這裡指的是既有的 `_prelim` 版本**（單次重複、單階精修：r1=2.10、r2=2.43、r3=2.50、rall=2.43，2026-08-15/16 完成，見 `results/RESULTS_LOG.md`），**不是 `--repeats 5 --refines 3,3` 的正式版——正式版還沒人跑，仍是待認領工作**，下面已列出。既然四個初步值都到齊，第 3、4、5 步原本卡在「等第 2 步結果」的部分現在**有資料可以做探索性對照，但統計上證實梯度為真、可以投入正式工作的那一層門檻還沒滿足**（見下方步驟表逐項說明的兩層門檻），新解鎖的具體工作列在下面步驟表與新增的待認領表，本次核對只更新文件、沒有跑任何計算 |
| 2026-08-19 | Claude session（本機） | 核對 Hobart, Baumgardt & Sweet (2026)（arXiv:2607.17300，Alpha Persei／Pleiades／Praesepe IMF 論文，方法論與本專案高度重疊）：找落差、回溯他們決策的文獻基礎 | **完成，純文件工作，未跑任何計算** | 新增 `docs/planning/PLAN_文獻對照_Hobart2026.md`（完整比較與文獻回溯）、`LIMITATIONS.md`（新增 D11–D14）、`WORK_BOARD.md`（本行＋下面兩個新表） | 使用者提供 PDF（本機 `Downloads/2607.17300v1.pdf`），用 `pdftotext -layout` 抽全文文字（非圖片辨識，抽到完整正文與參考文獻），逐段核對他們的成員判定／等時線／雙星修正／冪律擬合／N-body 五個步驟跟我們現有方法論的差異，並回溯他們每個關鍵數字（卡方門檻、視差/PM 瀰散、搜尋半徑等）在文中引用的原始依據。**找到 4 個新落差（D11–D14，詳見比較文件第四節）**：低質量段無獨立於等時線的經驗質量-光度校驗、亮端完整度無獨立目錄交叉驗證、`f_bin` 只有 Hess 圖一條觀測制約、system MF／stellar MF 定義未在文件明確標註。**也找到我們方法論優於這篇論文的兩處**（金屬量高斯先驗資料驅動、逐星三法雙星交叉比對），已寫進比較文件，論文寫作時可以直接主張。**N-body 的最大洞見**：他們用「中等規模模擬網格＋高斯過程模擬器＋HMC 抽後驗」取代暴力網格搜尋（他們自己算過暴力法要一個世紀），這正好對應我們算力受限（單台 ARM64 8 核）的處境，建議取代下面 PDMF→IMF 第 5 步原本設想的「直接模擬」做法 |
| 2026-08-19 | Claude session（本機） | 訂正 2026-08-17/18 那行的一句話：headline `p2_final2_v3` 的本機版與 Kaggle 分片版**並非「互不衝突」** | **狀態訂正，非新工作** | `queue.txt`（本機 `p2_final2_v3` 那筆註解停用，PR #69） | CodeRabbit review 抓到。上一行寫「本機完整 10 次重複版本，跟 Kaggle 拆分版本並行，互不衝突」——**這句已作廢**。兩者確實不會互相覆寫對方的**分片**檔案，但本機那筆的 `--tag _p2final_v3` 會寫到 `results/fit_real_p2final_v3.npz`，而那正是 Kaggle `rep0`–`rep9` 串接後要存的**正規產物**檔名，兩邊寫同一個檔案、最後留下哪一份取決於誰晚跑完，從檔案本身看不出來；且兩者是同樣 10 次重複、同樣三階精修的同一批工作，本機再算一次純浪費（本機 8 核並沒有快到能無視——`radial_r2` 單次重複就跑了 285 分鐘）。**headline 的正規來源自此固定為 Kaggle 分片**：`rep0`–`rep9` 全部拉回後依 offset 由小到大沿 axis=0 串接成 `results/fit_real_p2final_v3.npz`，每個分片檔與這個正規產物都要記進 `results/RESULTS_LOG.md`。`queue.txt` 那筆改成註解（不是刪除）並寫明理由，避免之後有人看到「headline 沒排在本機佇列」又把它加回來。要重跑 headline 改 `kaggle_queue.txt` |
| 2026-08-19 | Claude session（本機） | D14：確認並標註 `alpha` 對應 system MF 還是 stellar MF | **完成，純文件＋一支診斷腳本，未動任何模型行為** | `PAPER_OUTLINE.md`（新增 3.4 節）、`fit_real.py`（檔頭）、`pipeline/joint_fit.py`（抽樣段落註解）、`LIMITATIONS.md` D14、`scripts/diagnostics/system_vs_stellar_mf.py`（新增），分支 `claude/d14-system-mf-doc` | 逐行核對 `JointModel.synthesise()` 的抽樣順序才下結論，不是照文獻推測：先抽 `n_syn` 個**主星**質量（冪次 = `alpha`，抽樣範圍是等時線網格實際涵蓋的質量區間、不是 config 值），再**獨立**擲 Bernoulli(`f_bin`) 決定誰帶伴星，伴星質量 `m2 = q·m1`（`q ~ q^q_gamma`，**不是抽自 IMF**），最後主星與伴星**流量相加**塌縮成同一個測光點。所以合成星團的一筆是一個**系統**，`alpha` 是 **system MF**（以主星質量標記）的冪次，伴星從未進入被擬合的質量分布。**另外實算了兩種定義的差**（原本只想寫「有小幅差異」，但那種說法對論文比對沒有用）：四百萬次蒙地卡羅、用專案實際參數，stellar MF 恆較陡，f_bin=0.30→+0.046、0.45→+0.066、0.60→+0.085、0.75→+0.102；我們的 `f_bin` 落在 0.45–0.62，量級 +0.05～+0.09，小於統計誤差 0.144 但與數項系統誤差同量級。健全性檢查（只算主星時要把注入的 2.35 原樣量回來）先過了才採信差值。**順帶發現一個沒人記過的簡化**：擲 Bernoulli 那步與質量獨立 = 假設雙星比例不隨質量變化，已新增 `mass_dependent_fbin` 到上面的待認領表 |
| 2026-08-20 | Claude session（本機，Kaggle：teammate2 補跑 `rep9_retry`） | headline `p2_final2_v3`（A1、A2，接續 2026-08-19 那兩行）：`rep9_retry` 完成，10/10 次重複到齊，串接成正規產物 | **完成，headline 數字正式定案** | `results/fit_real_p2final_v3_rep9.npz`（新增，從 Kaggle 拉回）、`results/fit_real_p2final_v3.npz`（新增，10 個 rep 串接後的正規產物）、`results/RESULTS_LOG.md`、`LIMITATIONS.md`（A1／A2 補上 2026-08-20 解除段落） | 依照上方 2026-08-19（CodeRabbit 訂正那行）記錄的正規流程操作：10 個 `rep*.npz` 的 `C` 陣列依 offset 0→9 沿 axis=0 串接、另存成 `fit_real_p2final_v3.npz`（未覆寫任何 `rep*.npz`）。**正式 headline 數字：alpha=2.382±0.068**（population std），logage=8.026（106.2 Myr，10 次完全一致），A_V=0.386±0.032、f_bin=0.568±0.022、dav=0.557±0.048（貼牆於 0.6 附近，預期行為，不是異常）。跟舊版有瑕疵的 headline（α=2.387±0.060）中心值差 0.005，遠小於誤差棒，方向上原本引用的數字沒有被推翻，但這次才是精修 bug＋金屬量先驗兩個修正都套用後的乾淨版本，A1／A2 兩項限制對 headline 本身正式解除 |
| 2026-08-20 | Claude session（本機） | 多星團擴展方向定案（使用者決定）：採用校驗軸 A＋B、放棄正交設計、Praesepe 做、Coma Ber 做、Hyades 先查文獻 | **決定已記錄＋A 的第一個診斷已完成，兩顆星團的執行尚未開始** | 新增 `scripts/diagnostics/check_massrange_crosscal.py`（純診斷不寫檔）、`docs/planning/PLAN_多星團擴展.md`（新增第十二節定案）、`WORK_BOARD.md`（本行＋下方新表），分支 `claude/multicluster-decision-2026-08-20` | 使用者定案內容與完整推理見 `PLAN_多星團擴展.md` 第十二節。**三個查證出來、會影響執行順序的事實**：(1) **放棄正交反而讓共線性變好**——舊四星團組合（含 IC 2602）logage 與 [Fe/H] 的 r=0.784、VIF=2.59，本次選定的 M45＋Praesepe＋Coma Ber 是 r=0.422、VIF=1.22，因為被拿掉的 IC 2602 正是把年齡與金屬量綁在一起那顆；代價是金屬量跨度從 0.32 縮到 0.17 dex、且三顆星團的殘差自由度是 0（**本輪不能宣稱任何 alpha–金屬量迴歸結果**，能做的是 Praesepe vs Coma Ber 的同齡配對比較，兩者年齡只差 0.032 dex(logage)、金屬量差 0.17 dex）。(2) **Praesepe 不是從零開始**——PR #11（Codex，未合併）已跑完 Praesepe 的 Tier1＋Tier2 全套，「Praesepe 做」實際上是審查／修好／重跑／合併 PR #11。(3) **Praesepe 與 Coma Ber 卡在同一張骨牌**——兩者走同一套共用程式碼，也就是 D8 那 4 個正確性問題所在；2026-08-20 查證顯示 Codex 已在 PR #11 分支寫好 4 點修法，但未合併也未重跑，D8 仍是現役缺陷，**整條線的第一張骨牌是 PR #11 而不是任何一顆星團**。A 的第一個數字已經算出來（見下方新表與第十二節 12.6）：把 Hobart+2026 的 Pleiades 分段冪律換算到別人的質量範圍後，M45 文獻間原本 2.01→3.33（跨度 1.3）的分歧大幅收斂，支持「跨研究差異主要來自口徑而非物理」這個假說，但 Pang+2024 的質量範圍尚未查證，不能當已驗證結論 |
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
| 2026-08-23 | Codex | `d8_postmerge_rerun`（D8）：PR #11 合併後多星團結果驗證 | **進行中** | 分支 `codex/d8-postmerge-closeout`；只使用最新 `main` 與已保存控制場／成員資料 | 正式 BP15/BP20 paired 長跑因本機沒有 Kaggle／GCP 私有憑證而阻塞，故轉做 D8。先驗證 NGC 3532 的 G>=17 紅藍 gate（失敗即停止前向），再以 Praesepe 重跑必要的 selection／前向 diagnostic；不覆寫舊結果、不把貼牆輸出寫成 IMF 結論。 |
| 2026-08-23 | Codex | `d8_postmerge_rerun`（D8）：完成合併後多星團結果驗證 | **完成** | `docs/planning/D8_POSTMERGE_MULTICLUSTER_VALIDATION_2026-08-23.md`、四個 `_postmerge` 結果檔，分支 `codex/d8-postmerge-closeout` | NGC 3532 的暗端紅藍 gate 失敗，依規則未跑前向；Praesepe selection 通過，但 B 設定 2/2 次 f_bin=1 貼牆、0 次有效且跳過注入回收。安全機制已實證生效，但兩團皆無新增可引用 IMF。 |
| 2026-08-23 | Claude session（本機） | `gcp1` 第一項正式派工（`d2_membership_threshold_p06_p07_retry`）：修好兩個讓它一直失敗的環境缺口 | **兩個環境缺口已修好，工作已重新排隊；實際計算是否算完見 `WORK_BOARD.md`** | 補傳 3 個 isochrone 網格檔、`data/m45_r5_g18_plx4.csv` 到 `gcp1`（本機操作，不動 repo 程式碼） | 承上一行「已派第一項真正工作」——實際啟動時連續兩次失敗：(1) 執行這支腳本的本機工作目錄（`m45_cloud_workers_wt`，跟主要工作目錄 `m45_membership` 是分開的 worktree）`isochrones/` 從沒放過網格檔，`ensure_static_data()` 本機檢查不到就跳過上傳（設計如此，不是 bug），遠端因此找不到 `parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat`；補傳後解決。(2) 補傳後又在下一步撞到 `data/m45_r5_g18_plx4.csv` 找不到——這個檔案本來就是 `.gitignore` 排除、每台機器要自己重抓的（見 D2 進度說明），本機已經抓過但沒同步到 `gcp1`；直接 scp 過去解決（沒有重跑 `fetch_gaia.py`，因為要另外 clone 一個私有 repo 才能重抓，直接複製本機現成的檔案更快）。這兩個都是「新機器缺這台的本機專屬資料」這一類坑，不是程式邏輯錯誤，之後同一台 worker 不會再踩到 |

## 個別已完成的待認領任務

**這些是原本「待認領工作」表格裡的行，已經完成、但因為原本格式沒有
「完成後搬走」的機制而一直留在原表裡**。整理時保留原始欄位（任務、
起手式、驗收標準），照原表分組。

### Praesepe 前向模型診斷（2026-08-24）

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| praesepe_fbin_wall_residual（D17） | 2026-08-24 | 固定 HR23 年齡與消光、太陽金屬量 PARSEC 單星軌跡；比較對象是 `_postmerge_d8` 保存的 clean CMD | G=10–14 中段殘差對齊；G=14–18 中位偏亮 0.511 mag，支持暗端失配驅動 f_bin=1。細節見 `docs/planning/D17_PRAESEPE_CMD_RESIDUAL_2026-08-24.md` |

### 多星團 selection 診斷（2026-08-24）

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| ngc3532_selection_rootcause（D16） | 2026-08-24 | 已保存的 NGC 3532 Gaia 成員與 `_postmerge` selection 結果，只讀重播品質切割 | 紅側 28/31、藍側 24/32 通過；差異主要來自 BP/RP 超額失敗（紅 3、藍 7）；Fisher 精確檢定 p=0.302，不足以證明普遍色偏。細節見 `docs/planning/D16_NGC3532_SELECTION_ROOTCAUSE_2026-08-24.md` |

### B/C/D 類補齊（2026-08-13 查證過程）

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| ~~`p6b4_boundary_retest`（D5）~~ | 用 `inject_lowmass.py --tag _p6b4_retest`（**已經有 `--tag` 了，不會覆寫原檔**）只補測 `p_true=1.3` 這一組（目前程式碼會測 `P_TRUE_LIST` 全部三組，先跑一次確認能不能只挑一個真值跑，需要的話加個 `--only` 旗標） | 補測的這一筆 logage 沒有再貼到 PARSEC 網格邊界（8.25），若又貼牆，代表這是系統性現象不是單次巧合，要在 D5 裡升級處理方式。**完成**：2026-08-17/18 那筆紀錄確認補測結果已重新套用到 `main`（PR #63） |
| ~~`injection_bias_floor_recheck`（C13）~~ | **已完成，2026-08-23**，見 `LIMITATIONS.md` C13 與 `results/RESULTS_LOG.md` 同日期那行 | alpha 偏差從 −0.050 縮小到 −0.006，證實是蒙地卡羅雜訊，不用再認領。附帶發現 `q_gamma` 偏差沒有跟著縮小，可另開新項目查證 |
| ~~`stick_out_fraction_constraint`（D13，成本高，建議先評估）~~ | 這個任務會牽動 `pipeline/joint_fit.py` 核心概似函數，不建議直接動手改——先寫一份成本評估 | **完成：保留為模型檢查，不直接改似然**（2026-08-20 Codex，見 `docs/planning/ASSESSMENT_CMD_STICKOUT_FBIN_2026-08-20.md`）。真實凸出比例 5.78% 落在模型 5.80%–7.04% 內，目前模型沒有明顯矛盾；若要升格成獨立似然項，先做注入回收 |

### 對照 Hobart et al. 2026 的鞏固工作（2026-08-19）

| 任務（括號＝對應 `LIMITATIONS.md` 條目） | 起手式 | 驗收標準 |
|---|---|---|
| ~~`bright_end_completeness_check`（D12）~~ | 已查 HIPPARCOS+Gaia DR3 交叉比對 | **2026-08-20 初步查證完成**：Alcyone 完全沒有 Gaia 視差解（資料層級限制，不是 pipeline 問題）；發現 G=4.0–5.2 之間確認是星團成員的星也整批不在 `cmd_members.csv` 裡，後續由 `d12_bright_end_root_cause` 等三行接手查根因，見下面三行 |
| ~~`d12_bright_end_root_cause`（D12）~~ | 2026-08-20 Codex：`65205373152172032`（G=4.173）在 pyUPMASK 後的 P=0.0017，於 P>=0.7 成員門檻前離開；HIP 17851（G=5.203）P=0.9999 且保留 | 完成（最小診斷），詳見 `docs/planning/DIAGNOSIS_M45_BRIGHT_END_LOSS_2026-08-20.md` |
| ~~`d12_bright_external_crosscheck`（D12）~~ | 2026-08-20 Codex：Hipparcos Hp<=6 的 17 顆亮星交叉 Gaia DR3，13 顆取得 Gaia 資料並回查 baseline/CMD | 完成，詳見 `docs/planning/M45_HIPPARCOS_BRIGHT_CROSSCHECK_2026-08-20.md`；確認至少兩顆 G<4 高 P 星只因亮端切割未進 CMD |
| ~~`d12_bright_hr23_crosscheck`（D12）~~ | 2026-08-21 Codex：以保存的 HR23 M45 快照核對 17 顆 Hipparcos 亮星 | 完成，詳見 `docs/planning/M45_BRIGHT_HR23_MEMBERSHIP_CROSSCHECK_2026-08-21.md` |
| ~~`system_stellar_mf_doc`（D14）~~ | 在 `PAPER_OUTLINE.md` 與 `pipeline/joint_fit.py`／`fit_real.py` 相關函式註解裡加一句話，明確說明目前 `alpha`／`binary_fraction` 對應 system MF 還是 stellar MF 空間 | **已完成 2026-08-19**：答案是 **system MF**（主星質量分布的冪次），見 `LIMITATIONS.md` D14 |
| ~~`mass_dependent_fbin_smoke`（D14 衍生）~~ | — | 2026-08-22 Codex 完成 5 個假星團的注入回收：兩個示範性質量相依雙星規則使固定比例模型的 alpha 相對控制組平均偏移 -0.12、-0.21，詳見 `docs/planning/SMOKE_MASS_DEPENDENT_BINARY_FRACTION_2026-08-22.md` |
| ~~`d12_hr23_cmd_recall_by_magnitude`（D12）~~ | — | 2026-08-22 Codex 完成：保存的 HR23 高機率（P≥0.7）M45 快照在 CMD 的總重疊率為 81.9%，詳見 `docs/planning/M45_HR23_CMD_RECALL_BY_MAGNITUDE_2026-08-22.md` |
| ~~`mass_dependent_fbin_matched_fast`（D14 衍生）~~ | — | 2026-08-22 Codex 完成中成本 gate：contrast=0.15 的平均額外 alpha 偏移約 0.000，contrast=0.30 為 +0.042，都低於統計誤差 0.144，詳見 `docs/planning/ASSESSMENT_MASS_DEPENDENT_FBIN_MATCHED_FAST_2026-08-22.md` |
| ~~`d12_hr23_lost_quality_fields`（D12）~~ | — | 2026-08-22 Codex 完成根因分解：只查詢已定位的 62 個 Gaia DR3 source_id，依現行 step2 順序重播後找出每顆星敗在哪個品質切割，詳見 `docs/planning/M45_HR23_LOST_QUALITY_REPLAY_2026-08-22.md` |
| ~~`d12_hr23_quality_threshold_sweep`（D12）~~ | — | 2026-08-22 Codex 完成候選篩檢：現行 BP20/3σ 回收 0/62；BP15/3σ 回收 16，詳見 `docs/planning/M45_HR23_QUALITY_THRESHOLD_SWEEP_2026-08-22.md` |
| ~~`d12_bp15_colour_error_gate`（D12）~~ | — | 2026-08-22 Codex 完成候選品質 gate：BP15/3σ 找回的 16 顆 HR23 候選星顏色誤差中位數比現有 CMD 同星等段大 2.48 倍，詳見 `docs/planning/M45_BP15_COLOUR_ERROR_GATE_2026-08-22.md` |
| ~~`d12_bp15_candidate_cmd_sides`（D12）~~ | — | 2026-08-22 Codex 完成候選紅藍篩檢：16 顆 BP15 候選中，10 顆在紅側、6 顆在藍側，詳見 `docs/planning/M45_BP15_CANDIDATE_CMD_SIDES_2026-08-22.md` |
| ~~`d12_bp15_candidate_mass_location`（D12）~~ | — | 2026-08-22 Codex 完成質量段 gate：16 顆 BP15 候選全低於 0.30 M☉，0 顆進入 alpha 控制的 >0.5 M☉ 段，詳見 `docs/planning/M45_BP15_CANDIDATE_MASS_LOCATION_2026-08-22.md` |
| ~~`d12_bp15_sample_scale`（D12）~~ | — | 2026-08-22 Codex 完成規模 gate：若 16 顆候選全被接受，>0.5 M☉ alpha 段直接增加 0 顆，詳見 `docs/planning/M45_BP15_SAMPLE_SCALE_2026-08-22.md` |
| ~~`d12_bp15_selection_input_restore`（D12）~~ | — | 2026-08-22 Codex 完成：新增有 TOP 20000 截斷防護的公開 ARI Gaia TAP 查詢，取得 M45 6,956 列原始場，詳見 `docs/planning/M45_BP15_SELECTION_INPUT_READY_2026-08-22.md` |
| ~~`d12_bp15_selection_smoke`（D12）~~ | — | 2026-08-22 Codex 完成：用修正後 6,956 列完整場建立獨立 BP15 selection，三項檢查都通過但餘裕偏小，詳見 `docs/planning/M45_BP15_SELECTION_SMOKE_2026-08-22.md` |

### 多星團校驗軸 A＋B（2026-08-20 使用者定案）

| 任務 | 對應 | 起手式 | 驗收標準 |
| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| 建立工作認領表 | 2026-08-12 | 無（純文件建置） | WORK_BOARD.md |

結論：建立了這個專案的任務追蹤文件，確立多人／多 agent 協作時「開始
前先查、認領後才動手」的慣例，沿用至今。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| sensitivity_sweep_membership_threshold（D2） | 2026-08-25 | 成員機率門檻 P_member = 0.5、0.6、0.7、0.8、0.9（五點）；合成星數 N = 40,000 顆；精修階數 = 2 階 | 五個門檻下 alpha、成員數、n_obs 的完整對照表 |

結論：五個門檻（0.5–0.9）下 alpha 全部是 2.367，logage／A_V／f_bin／
MH／q_gamma／dav 六個參數也逐位元相同，n_obs 與 lnP 隨門檻單調變化，
確認不是快取假象。結果供 `LIMITATIONS.md` D2 引用，但帶兩個但書：
(1) 全程沿用同一份用 0.7 樣本迴歸出的 `selection.npz`，未隨門檻重新
迴歸選擇函數係數；(2) 只做兩階精修，逐位元相同也可能是精修深度不足
以分辨差異，未交叉確認。`stars_per_cluster`（D2 另一掃描目標）需要
pyUPMASK 環境，未完成，已拆成獨立待辦項目留在 `WORK_BOARD.md`。

### PDMF → IMF 第 3 步（LIMEPY 多質量平衡模型）

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| Kaggle dataset 掛載問題根因排查 | 2026-08-12 | 無（除錯過程） | kaggle_sync.py 路徑修正 |

結論：找到 Kaggle 派工一直掛載失敗的真正原因——路徑字串少算了兩層
目錄（`/kaggle/input/<slug>/` 應為 `/kaggle/input/datasets/<帳號>/<slug>/`），
改一行修好。解除了此前誤判「Kaggle 平台異常」「帳號被限制」兩個
假設，讓後續所有 Kaggle 多帳號派工得以穩定運作。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| GCP SSH worker（gcp1）建置與驗證 | 2026-08-23 | GCP e2-highcpu-8 VM（8 核） | ssh_workers.py、cloud_queue.py、CLOUD_WORKERS.md |

結論：建好第三個獨立算力池（本機、Kaggle 之外），push→run→status→pull
全鏈路驗證通過，之後用於派送 D2 敏感度掃描等正式規模計算。記錄了
GCP 瀏覽器登入帳號與金鑰登入帳號是兩個獨立 Linux 帳號、需分別設定
的坑，避免下次重踩。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| 新機器環境可攜性驗證（x64） | 2026-08-12 | 完整 pipeline 第 0–5 步 | 比對結果（未寫入 results/） |

結論：在獨立的 x64 機器上重跑整條 pipeline，6,956 顆星樣本完全相同、
alpha 等頭條數字落在既有結果的隨機性範圍內，確認 pipeline 不依賴
特定機器架構、可攜、可重現。順便修好一個路徑寫死的可攜性 bug。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| PDMF→IMF 優先度覆核 | 2026-08-12 | queue.txt、LIMITATIONS.md 現有排程 | WORK_BOARD.md 優先度欄 |

結論：確認 queue.txt 既有順序已符合「PDMF 相關項目排在非 A/B 類前面」
的要求，不需要調整；為第 3、5 步標上「可立刻開始」（不需等第 2 步
結果）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| PDMF→IMF 第 2 步：徑向初步值到齊 | 2026-08-16 | 搜尋半徑 r = 1°、2°、3°、全樣本（5.1°），單次無誤差棒 | α(<r) = 2.10／2.43／2.50／2.43 |

結論：四個累積半徑的初步 α 值全部到齊，方向支持核心到外圍的質量
分層（跟傳統法一致），解鎖第 3–5 步的探索性（非正式）工作。正式、
有誤差棒的版本後續由 radial_final_reruns 補上（已完成，見下）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| radial_final_reruns：徑向 α(<r) 正式統計版 | 2026-08-23 | 合成星數 N = 40,000 顆；重複次數 = 5；精修階數 = 2 階；半徑 r = 1°、2°、3°、全樣本 | α(<r) 四點皆帶誤差棒：2.0644±0.1193／2.3889±0.0981／2.4244±0.0924／2.3844±0.0792 |

結論：PDMF→IMF 第 2 步的正式版本，四個半徑都有統計誤差棒。配對
比較顯示 0–2° 有提示性但未通過多重比較校正的跳升（Holm 校正後
p≈0.084–0.088），2° 以外到樣本邊緣無顯著變化，α(<r) 曲線約在 2°
收斂。這是 limepy_radial_crosscheck、nbody_prior_from_radial、
pdmf_step4_radius_expansion（皆仍開放，見 WORK_BOARD.md）共同依賴
的觀測基準線，也是 LIMITATIONS.md A5 的核心數據。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| headline 數字正式定案（p2_final2_v3） | 2026-08-20 | 合成星數 N = 40,000 顆；重複次數 = 10；精修階數 = 3 階 | α = 2.382 ± 0.068 |

結論：這是目前論文引用的頭條 IMF 冪次，精修 bug 與金屬量先驗兩項
修正都套用後的乾淨版本（取代先前有瑕疵的 2.387±0.060，中心值差
0.005，遠小於誤差棒，方向沒有被推翻）。同一批交叉驗證也確認 P9a
（PARSEC 鎖 MH：α=2.387±0.108）與 P9c（MIST 鎖 MH：α=2.102±0.102）
年齡相差一倍，推翻了原本表 4 聲稱的「跨等時線年齡一致」穩健性主張
（LIMITATIONS.md A4），這點在論文寫作時要一併訂正。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| limepy_radial_crosscheck（A5、B5） | 2026-08-25 | r1/r2/r3/rall 四段正式五次擬合結果、LIMEPY 多質量模型預測 | 模型 alpha 在 r1/r2/r3/rall 為 1.738/1.958/2.061/2.124，觀測為 2.064/2.389/2.424/2.384，模型低估 0.326/0.431/0.363/0.260（觀測五次樣本散布的 2.73–4.40 倍）；核心到 r2 上升方向一致，2° 外模型仍升而觀測趨平 |

結論：診斷完成，模型端誤差棒仍未建立，屬高資訊價值診斷而非正式否決；模型與觀測共用成員、估計器不同，見 LIMITATIONS.md B5。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| B/C/D 類待辦逐一查證（八項） | 2026-08-13 | LIMITATIONS.md 既有 C/D 類條目 | LIMITATIONS.md A6 新增、B4／D7 結案、8 項正式列為待辦 |

結論：白矮星污染（原 D7）查證後屬實、升級為 A6（會影響頭條數字）；
Poisson 似然函數的疑慮（B4）查證後不成立、直接結案；RV 交叉核對
發現 56 顆星（11.2%）偏離團體速度超過 5σ 但成因不明，留為開放問題；
「20 顆判定分歧」（C20）的原始定義因樣本篩選流程改變而對不上目前
367 顆，如實記錄查證失敗，不強行湊數字。其餘 8 項（含 D2、C5、C8、
C19 等）正式寫成待辦規格，現在都在 WORK_BOARD.md 上。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| A6：白矮星與 RV 離群星排除 | 2026-08-13 | 顏色一致性檢查（偏離主序色 >0.4 星等）；RV 交叉核對名單 | α 位移量化表（三種質量範圍設定） |

結論：新增顏色檢查與已確認非成員名單，排除一顆混入樣本的白矮星與
一顆 RV 偏離團體速度多個 σ 的離群星。量化後兩者合計對頭條 alpha 的
影響全部遠小於統計誤差（0.067–0.118），A6 全部解決——現有頭條數字
已排除這兩個已知污染源。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D9／C20：亮星離群值身分確認 | 2026-08-13 | Gaia DR3 顏色、HR23 成員表、徑向速度 | source_id 68409590552589184 確認非成員 |

結論：三個獨立證據方向一致（顏色遠離主序、HR23 完全未收錄、RV 偏離
團體速度 350σ）確認這顆星不是 M45 成員，已加入排除名單。順帶重建
了 C20「20 顆判定分歧」的原始 1999 年定義，對上其中一顆正是這裡查
的離群星。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| C3：分光雙星對 RV 離群比例的解釋力 | 2026-08-13 | 雙星比例 f_bin = 0.45；週期分布（Sana+2012 對照 Raghavan+2010） | 蒙地卡羅估計：27.2%（Sana）vs 6.9%（Raghavan） |

結論：觀測到 11.2% 的星偏離團體 RV 超過 5σ，能不能完全歸給已知
分光雙星高度依賴週期分布假設——用更符合 M45 主序星型別的
Raghavan+2010 分布只能解釋 6.9%，缺口解釋不了。誠實記錄為「不穩定，
依假設而定」，不是找到污染源，留給後續有更好雙星編目時再查。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| BHAC15 等時線網格建置 | 2026-08-18 | BHAC15_iso.GAIA 原始檔（Gaia 濾光片版本） | bhac15_gaia_logt7.6-8.4.dat（170 列、6 個年齡格點） |

結論：解除外部服務連線與憑證鏈問題後，成功下載並轉換 BHAC15 等時線
網格，涵蓋質量範圍 0.015–1.4 M_sun（不蓋過 M45 擬合上限 2.50
M_sun，只能驗證低質量段）。真正跑一次 fit_real.py 拿這個網格算模型
效應分解、跟 PARSEC／MIST 對照，仍是開放工作（bhac15_isochrone_test，
見 WORK_BOARD.md）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| C18：選擇函數是否需要顏色維度 | 2026-08-14 | 存活率對顏色的迴歸（n=1,163，全星等範圍） | 迴歸斜率 −0.0054±0.0070（0.8σ，不顯著） |

結論：換大樣本增加檢定力後，顏色對存活率的斜率仍與零無法區分，
現有的星等相依一維選擇函數近似沒有被數據推翻，不需要升級成二維
（星等+顏色）版本。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| PDMF→IMF 第 3 步：LIMEPY 多質量平衡模型 | 2026-08-13 | King 模型（g=1），觀測質量分層剖面 | φ0=3.44、r0=2.50 pc，reduced χ²=0.75 |

結論：擬合品質良好的多質量平衡模型，估計潮汐半徑外還有約 14.4
M_sun（模型總質量 3.2%）的低質量星未被目前樣本涵蓋。修好一個單位
不一致的 bug 後數字才穩定（原始版本 reduced χ²=8.90，質量估計
21.2 M_sun，不可信）。跟第 2 步觀測 α(<r) 的正式交叉比對仍是開放
工作（limepy_radial_crosscheck，見 WORK_BOARD.md）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| N-body 環境建置（PeTar/MSYS2/mcluster） | 2026-08-12 | PeTar、SDAR、FDPS、mcluster（原始碼編譯） | 可重現的編譯腳本與 patch（nbody_setup/） |

結論：在 Windows 上（MSYS2/MinGW，不需 WSL）成功編譯 PeTar（含 BSE
恆星演化）與 mcluster，修好兩個真實的可攜性 bug（uname 大小寫誤判、
缺少 glibc 擴充函式），驗證能量與角動量守恆在合理範圍。解鎖 N-body
模擬工作（nbody_prior_from_radial，見 WORK_BOARD.md）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| N-body 第一個 pilot 模擬 | 2026-08-13 | 恆星數 N = 400 顆；質量分層度 S = 0.5；virial 比 Q = 0.5；積分時間 125 Myr | α(r)：核心 0.879±0.158 → 外圍 1.316±0.157 |

結論：第一次拿到跟觀測同方向的動力學預測（核心較平、外圍較陡），
但只是單次、無潮汐場、非文獻 IMF 形式的示範跑，不能引用絕對值。
正式校準版本（多次重複、對齊觀測基準線）仍是開放工作
（nbody_prior_from_radial）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| PeTar 分析管線工具鏈 | 2026-08-13 | 合成 PeTar 快照資料 | 快照分析器、多 run 彙整器、component 定義橋接（均已自我測試） |

結論：建好完整的 PeTar 輸出分析管線（quantile 彙整、raw snapshot
人工粒子防護、single/binary/component 質量定義橋接），已用合成資料
驗證正確性，等待正式長時間模擬的真實輸入。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D14：確認 alpha 對應 system MF 還是 stellar MF | 2026-08-19 | JointModel.synthesise() 抽樣邏輯逐行核對 | 確認為 system MF，兩種定義差 +0.05～+0.10 |

結論：頭條 alpha 是主星（system）質量分布的冪次，不是恆星
（stellar）質量分布——伴星從未進入被擬合的質量分布。量化兩種定義
的差異落在專案 f_bin 範圍（0.45–0.62）內約 +0.05 到 +0.10，小於
統計誤差但與數項系統誤差同量級，論文需明確標註用的是哪一種定義。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| 文獻對照：Hobart, Baumgardt & Sweet (2026) | 2026-08-19 | 對方論文全文（方法論逐段核對） | 4 個新落差（D11–D14）、2 個本專案優勢 |

結論：找到本專案原本沒發現的 4 個方法論缺口（無獨立於等時線的質光
校驗、無獨立亮端完整度交叉驗證、f_bin 只有單一觀測制約、MF 定義
未明文標註），也確認本專案在金屬量先驗與雙星交叉比對兩處優於這篇
論文。他們用機器學習模擬器取代暴力 N-body 網格搜尋的做法，被採納
為本專案第 5 步的建議路線。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| 多星團擴展方向定案 | 2026-08-20 | 候選星團年齡／金屬量共線性分析 | 校驗軸 A＋B（Praesepe、Coma Ber、Hyades 候選） |

結論：使用者定案採用校驗軸 A＋B、放棄原訂正交設計（放棄後反而讓
年齡-金屬量共線性從 VIF=2.59 降到 1.22）。查證發現 Praesepe 已有
未合併的 PR #11 完成大半工作，且 Praesepe 與 Coma Ber 共用的程式碼
就是 D8 記錄的 4 個正確性問題所在，整條校驗軸的第一張骨牌是合併
PR #11（praesepe_pr11_close_out，見 WORK_BOARD.md），不是任何一顆
星團本身。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| crosscal_massrange_table：Pang+2024 口徑核對 | 2026-08-20 | Pang et al. (2024) 原文 Table 1／方法節 | Pang 質量範圍 0.28–2.00 M☉，α=2.010±0.090 |

結論：核對原文後確認 Pang 的質量範圍與定義，換算到同一質量範圍後
跟 Hobart 重新處理的數字（1.952）相近，支持「跨研究 IMF 差異主要
來自口徑選擇而非物理」的假說，但兩者的聯星修正方法不同，不能忽略
這個殘餘差異。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| hyades_literature_check：Hyades 候選文獻篩選 | 2026-08-20 | LDB 年齡、光譜金屬量、既有 MF 測定文獻 | 保留候選，暫不執行 |

結論：Hyades 可增加老年齡、金屬富有的對照點，但現有 5° 搜尋半徑
只涵蓋約 4.1 pc，遠小於其約 10 pc 潮汐半徑，建議先做多半徑
（5°／12°／20°）的成員與選擇函數 smoke test，通過後才排入正式
執行序列，目前尚未執行。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D8：PR #11 控制場／選擇函數續跑 | 2026-08-20 | ARI Gaia DR3 鏡像（控制場資料） | NGC 3532 未過紅藍驗證；Praesepe 通過但貼牆 |

結論：補齊控制場資料後，NGC 3532 在暗端紅藍驗證失敗（安全機制正確
攔下，未跑前向模型）；Praesepe 通過選擇函數三項檢查，但二元擬合
2/2 次都貼在 f_bin=1 上界，安全標記為僅供診斷、不計入 IMF 結論。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D8：PR #11 合併後多星團驗證 | 2026-08-23 | main 分支合併後的程式碼；NGC 3532、Praesepe 既有資料 | 兩團驗證結果（見結論） |

結論：確認 PR #11 合併後，安全機制在真實資料上依然正確運作——
NGC 3532 一樣在暗端紅藍 gate 失敗（正確攔下），Praesepe 一樣在
二元擬合貼牆（正確標記 diagnostic only）。兩團都還沒有新增可引用
的 IMF 結果，但驗證了合併後程式碼行為正確。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| gcp1 新 worker 環境缺口修復 | 2026-08-23 | isochrone 網格檔、快取的 Gaia 查詢 CSV | gcp1 可正式執行 D2 敏感度掃描 |

結論：gcp1 首次派工連續兩次卡在「新機器沒有這台專屬的本機資料」
（isochrone 網格檔、gitignore 排除的 Gaia 查詢快取），非程式邏輯
錯誤，補傳檔案後解決。同一類坑之後在別台新 worker 上還可能重演，
但這台 worker 本身不會再踩到。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D13：聯星比例第二制約（stick-out fraction）成本評估 | 2026-08-20 | headline 頭條 10 次重複的 CMD 凸出星比例 | 真實 5.78% 落在模型預測 5.80–7.04% 內 |

結論：目前模型沒有明顯矛盾，不需要把凸出星比例升格成獨立似然項
（升格會跟既有 Hess 似然重複計數同一批資料）。保留為模型健全性
檢查，若要升格需先做注入回收。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| mass_dependent_fbin_smoke：質量相依雙星比例初步篩檢 | 2026-08-22 | 5 個合成星團；contrast 兩組示範性規則 | alpha 平均偏移 −0.12、−0.21（粗網格） |

結論：初步篩檢顯示質量相依雙星比例確實可能推動 alpha，量級不可
忽略，動機支持做更嚴謹的後續測試（見下一行 matched_fast）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| mass_dependent_fbin_matched_fast：質量相依雙星比例精細測試 | 2026-08-22 | 60 個配對種子；contrast = 0.15、0.30，整體 f_bin 固定 | alpha 平均偏移 0.000（contrast=0.15）、+0.042（contrast=0.30） |

結論：控制整體雙星比例不變後，質量相依性造成的平均 alpha 偏移都
遠小於統計誤差 0.144，初步不像是主要系統誤差，但單次實現的散布
（0.21–0.27）仍大，正式的七參數驗證仍值得跑、且不取代
mass-dep-fbin 分支正在進行的正式版本（見 WORK_BOARD.md
mass_dependent_fbin）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| BP15 前向模型初步 smoke test | 2026-08-22 | 合成星數 N = 3,000 顆；配對種子 3 組 | alpha 差異在小樣本下不穩定 |

結論：確立了正式比較需要的最低規模門檻（40k 合成星、至少 5 組配對
種子），小樣本結果本身不能下科學結論。正式成對比較仍是開放工作
（bp15_bp20_paired_comparison，見 WORK_BOARD.md）。

## D12：HR23 亮端與紅端選擇函數診斷鏈

以下一系列診斷共同回答「亮端與紅端有沒有系統性漏收成員星」，逐項
完成後才進到下一項，最後停在「BP15（放寬的 BP 誤差門檻）選擇函數
本身建置完成，但正式前向模型比較仍待執行」。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D12 亮端完整度初步查證 | 2026-08-20 | HIPPARCOS + Gaia DR3 交叉比對 | 發現 G=4.0–5.2 星整批不在 cmd_members.csv |

結論：確認 Alcyone 缺 Gaia 視差解是資料層級限制；意外發現一段
亮端星系統性缺失，範圍比原本已知的星等截斷更大，觸發後續根因
追查（下面幾行）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D12 亮端消失根因定位 | 2026-08-20 | pyUPMASK 成員機率、Hipparcos 交叉比對 | 定位到兩類消失原因（見結論） |

結論：確認至少兩類機制造成亮端星消失——部分星是 pyUPMASK 判定
機率過低（P<0.7 門檻前離開），部分星只是被亮端測光截斷排除、跟
成員判定本身無關。兩類消失原因確認為不同機制，不是同一個 bug。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D12 紅端回收率完整鏈路分析 | 2026-08-22 | HR23 高機率（P≥0.7）成員快照，逐步驟重播 | 回收率依星等分箱，G=16–18 段流失最多（79.5%） |

結論：把 HR23 成員在 pipeline 每一步的流失位置逐步定位，發現暗端
（G=16–18）主要敗在 BP 訊噪比門檻（SNR_BP<20），量化了現行門檻
排除掉多少疑似真成員。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D12：放寬 BP 門檻（BP15）候選評估 | 2026-08-22 | BP 誤差門檻從 SNR_BP=20 放寬到 15 | 16 顆候選星，全數低於 0.30 M☉ |

結論：放寬門檻能找回 16 顆疑似真成員，但顏色誤差比現有樣本同星等
段大 2.48 倍、且全部落在 alpha 擬合控制的 >0.5 M☉ 段之外——即使
全數接受，對 alpha 頭條數字的直接影響是零顆，主要價值是低質量段
完整度而非頭條數字修正。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| D12：BP15 選擇函數重建與驗證 | 2026-08-22 | 6,956 列原始 Gaia 場（TOP 20000 截斷防護重新查詢） | 獨立 BP15 selection.npz，三項檢查通過但餘裕偏小 |

結論：BP15 版本的選擇函數已建置並通過驗證（整體、最差星等箱、
紅藍對比誤差三項門檻都過，但餘裕不大），相對現有 CMD 淨增 58 顆、
零遺失。這是 bp15_bp20_paired_comparison（見 WORK_BOARD.md）能夠
執行正式前向模型比較的前置條件，現已具備。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| stars_per_cluster_sensitivity：D2 可行性查證 | 2026-08-25 | pyUPMASK 每群星數（`stars_per_cluster`）敏感度掃描的可行性檢查 | 確認執行受阻：repo 缺 `pyUPMASK/`、缺 `prepared/` 輸入，`run_variant.py` 也未暴露對應的參數旗標 |

結論：實際執行過才確認這項掃描目前做不到，不是「沒有影響」而是
「執行受阻，阻塞原因已驗證」——跟 `membership_threshold` 不同，
`stars_per_cluster` 需要真的重跑 pyUPMASK 聚類，這台機器缺三項
必要依賴。順手修好一個無 SciPy 環境時可行性檢查本身會在檢查前
就崩潰的問題。真正的敏感度數字仍是開放工作，留給有 pyUPMASK
環境的機器認領（見 `WORK_BOARD.md`）。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| p6b4_boundary_retest：D5 貼牆補測 | 2026-08-13 | `p_true = 1.3` 單次試驗 | logage=8.133（安全落在網格內部），未再貼牆 |

結論：補測後沒有重現原本那筆貼牆，支持「原本是單次試驗隨機波動」
的解讀，`p6b4` 核心的「可辨識」結論（p_recovered 跟隨 p_true、
ratio ~0.92）不受影響。完整記載見 `LIMITATIONS.md` D5。

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|
| injection_bias_floor_recheck：C13 偏差地板複查 | 2026-08-23 | 合成星數 N = 160,000 顆（4 倍於預設）；情境 S1；試驗次數 = 3 | alpha 偏差 −0.006（3 次跨試散布 0.048） |

結論：把合成星數提高 4 倍後，alpha 偏差地板從原本記載的 −0.050
大幅縮小到 −0.006，證實地板主要是蒙地卡羅雜訊、不是另有系統性
成因。附帶發現 `q_gamma` 偏差 −0.181 沒有跟著縮小，可能有獨立於
樣本量的偏移機制，留待另外查證。完整記載見 `LIMITATIONS.md` C13。
