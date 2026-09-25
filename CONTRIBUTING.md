# 協作規範（給所有人類與所有 AI agent）

這份是所有要碰這個 repo 的人與 agent 共用的規則。Claude 另外先讀
`CLAUDE.md`，兩份都要遵守。多個 agent（Claude、Codex 等）與多個人
同時在這個 repo 工作，這些規則讓大家能找到彼此跑過的結果、改過的
程式與對應版本。

規則類文件（本檔、`AGENTS.md`、`README.md`、`WORK_BOARD.md`、
`WORK_BOARD_DONE.md`、`LIMITATIONS.md`、`QUEUE_ALERTS.md`、`STATE.md`、
`docs/reference/*`）只寫現在的規則，不寫「哪一天、因為什麼事、改了
什麼」。規則的沿革與起因在 [CHANGELOG.md](CHANGELOG.md)，依文件分節。
新增規則時，需要記錄的理由寫進 `CHANGELOG.md`，不寫進規則本身。

---

## 零、開始新工作前——先查 `WORK_BOARD.md`

預期會跨多次對話、或會碰共用檔案（`pipeline/`、`injection_recovery.py`、
`LIMITATIONS.md`、`PAPER_OUTLINE.md`、`queue.txt`）的工作，開始前先讀
`WORK_BOARD.md`（進行中／尚未進行）與 `WORK_BOARD_DONE.md`（已完成），
確認沒有人正在做或已經做完。舊格式的行不一定寫明「已完成」，所以兩份
都要查。看不出是否重複，就在文件裡直接寫下疑點，不要用猜的。開始時
在 `WORK_BOARD.md` 認領一行，格式見零之四。

**規則文件隨時可能被改，讀過一次不代表現在還適用。** 編輯受規則管控
的檔案（`WORK_BOARD.md`、`WORK_BOARD_DONE.md`、`LIMITATIONS.md`、
`QUEUE_ALERTS.md`）前，先確認 `CONTRIBUTING.md` 與 `AGENTS.md` 各自
是最新版：

1. `git fetch origin main`，比對 `git log -1 --format=%H -- <檔名>`
   與 `origin/main` 的 commit 是否相同。
2. 不同就用 `git diff <上次讀到的 commit>..origin/main -- <檔名>` 只看
   差異，確認相關章節有沒有變。
3. `git status --short -- CONTRIBUTING.md AGENTS.md` 若顯示有未 commit
   的修改，commit hash 比對不到，要直接讀工作目錄裡的檔案。

長對話中途也一樣：不要憑稍早讀過的版本操作，中間可能有 PR 合併改了
格式。

---

## 零之一、自動 PR 審查——CodeRabbit

CodeRabbit 對公開 repo 免費，任何人開 PR 都會自動留一次審查。設定在
`.coderabbit.yaml`（審查語言、排除 `results/`／`data/` 等資料檔、對
`injection_recovery.py`／`pipeline/` 等共用核心的審查提示）。啟用要
repo 擁有者親自做一次：到 https://github.com/apps/coderabbitai 用
GitHub 帳號安裝 App 並選這個 repo（帳號授權，agent 無法代勞），之後
不需要金鑰或額外設定。

- **它是輔助，不取代 PR 與 `WORK_BOARD.md` 流程。** 它抓程式面的問題
  （bug、重複實作、效率），跑不動實際計算；數字對不對仍要靠
  `results/RESULTS_LOG.md` 與人／其他 agent 交叉核對。
- **它不會自動修。** 每則留言要處理後回覆並 resolve，或說明站不住腳的
  理由。它若對已處理的留言誤判、卡住不放，直接在 GitHub UI 手動
  resolve 該討論串。
- **合併不需要它核准**（`required_approving_review_count=0`），任何人
  都能按 merge，合併前自行判斷它的意見要不要處理。
- **「Review completed」綠燈不代表真的審過。** 即使因額度用完沒送出
  正式 Review，commit status 也一樣顯示 `state=success`，從 PR 頁面或
  `gh pr checks` 分不出來。唯一可靠的判定是：最後一則正式 Review 的
  `commit_id` 等於 PR 目前的 head SHA。合併前先跑：
  ```
  scripts/tools/coderabbit_status.sh <PR 編號...>   # 查指定 PR
  scripts/tools/coderabbit_status.sh                # 查全部 open PR
  ```
  輸出的「✅ 已審過且核准」「🔴 已審過但還有意見」「💬 已審過但只是
  留言」代表它看過目前這次 push；「⚠ 還沒有針對目前這個 commit 的
  正式 review」（多半是額度用完）不能當作審過沒問題。
- **`@coderabbitai resolve` 會一次關掉全部留言**，而且必須以 PR 頂層
  留言送出。只在所有留言都處理完、要一次收尾時用；單一誤判只在 UI
  resolve 那一個討論串，否則會把還沒處理的留言一起關掉。

### 純派工 PR 標題要帶 `[派工]`——CodeRabbit 會跳過

審查額度全 repo 共用。**只改派工清單**（`cloud_queue.txt`、
`kaggle_queue.txt`、`queue.txt` 這類，沒有任何程式、文件、設定變動）的
PR 沒東西可審，卻會吃掉額度。

- 這類 PR 的標題以 `[派工]` 開頭，例如
  `[派工] cloud_queue：方法 B 訓練網格切 16 批派給 senior24`。
  `.coderabbit.yaml` 的 `ignore_title_keywords` 會讓 CodeRabbit 跳過它。
- 只要同一個 PR 還改了程式、`WORK_BOARD.md`、`LIMITATIONS.md`、
  `results/` 或任何其他檔案，就不可以帶這個標記。不確定就不要帶。
- 與身分前綴並用時 `[派工]` 放最前面：`[派工] [Claude] ...`。
- 被跳過的 PR 在 `coderabbit_status.sh` 會顯示「⚠」，這是預期結果；
  合併純派工 PR 不需要 CodeRabbit 核准。
- 漏帶標題而已經被審的 PR 不用補救。

---

## 零之二、文件裡的判斷預設是「當下的想法」，不是決議

規劃類文件（`docs/planning/`、`WORK_BOARD.md` 說明文字、PR 描述，以及
對使用者的回覆）裡的「結論」「判斷」「建議」，預設只代表寫下當下的
想法。這個 repo 由多人多 agent 共同維護，同一份規劃常在短時間內被修正
或推翻。

1. **推理與數字寫完整，只有語氣保留。** 用「初步判讀」「目前傾向於」
   「還沒驗證過」取代「結論是」「必須」「不能」；論證、引用來源與算出
   的數字照常完整交代，不是寫得含糊。
2. **發現判斷站不住腳、有更好做法或被新資訊推翻，任何人都可以直接改**，
   不必先問原作者。改到別人可能同時在動的地方，照第一節處理（有風險就
   讓對方看過再合併）。
3. **判斷內容新舊看文中日期，不看語氣。** 語氣刻意不肯定不代表不可靠；
   舊文件語氣篤定也不代表現在還適用，要看日期與後續訂正紀錄。日期標在
   章節標題或段落開頭即可。
4. **不取代既有的結構化信心標記**：`LIMITATIONS.md` 的 A–D 分級（第五
   節）、規劃文件「已讀原文」vs「WebSearch 摘要未讀原文」的引用標記
   照舊使用。

---

## 零之三、開始新工作前——也要查 `QUEUE_ALERTS.md`

`run_queue.py` 的 Gate B（開跑前檢查）或 Gate C（跑完驗收）沒過時，
佇列會繼續跑下一項，但會寫進 `QUEUE_ALERTS.md`。任何 session 開始碰
這個 repo 前先讀一次，看有沒有「待處理」項目。處理完（或確認不是問題）
把該列狀態改成「已處理」，不要刪掉。格式與 Gate B／C 的收尾方式寫在
`QUEUE_ALERTS.md` 檔頭。

---

## 零之四、`WORK_BOARD.md`（待辦）與 `WORK_BOARD_DONE.md`（已完成）

- `WORK_BOARD.md` 只放進行中或尚未進行的工作，以及認領規則、疑義處理、
  算力池歸屬等使用說明。
- `WORK_BOARD_DONE.md` 只放完全完成的事。

**何時算完成**：驗收標準已達成，或使用者／後續查證已明確結案。文字中
「若要升級還可以做 X」這種選配延伸不影響判定；但寫著「仍待做」「目前
阻塞」「還沒有」「等待交接」「等待驗收」就不算完成。判不出來就留在
待辦——把沒做完的誤標成完成，代價遠大於反過來（別人會以為不用做了）。

**`WORK_BOARD.md` 格式**：一個任務一張單列小表格，底下緊接一段說明
文字，再接下一個任務；不要把所有任務塞進一張大表、說明集中寫在後面。
欄位固定五個：

| 任務名稱 | 狀態 | 開始日期／指派時間 | 輸入參數 | 輸出參數 |
|---|---|---|---|---|

- 狀態只有「進行中」與「尚未進行」。
- 每個任務只有一張表格、一段說明。狀態改變時直接覆蓋儲存格（開始日期
  一併補上），不用刪除線、不在說明裡疊加多輪更新。
- 任務名稱後的括號只放 `LIMITATIONS.md` 條目代碼（如 `A1`），不放句子。
- 輸入／輸出參數寫物理量（符號與單位），例如「合成星數 N = 40,000 顆」
  「消光量 A_V 掃描上限 1.20 mag」，不寫 `--n-syn 40000` 這類變數名或
  旗標；可重現的指令、旗標、檔名放說明文字。
- 說明文字（標題用任務名稱）寫清楚：要解決什麼問題、用什麼方法（含可
  重現指令）、卡在哪、預計多久。耗時只在有實測依據時寫數字，否則寫
  「未查證」。
- 表格與說明都不用粗體，重點寫進句子本身。

**`WORK_BOARD_DONE.md` 格式**：同樣一個任務一張小表格加一段說明，欄位：

| 任務名稱 | 完成日期 | 輸入參數 | 輸出參數 |
|---|---|---|---|

- 沒有狀態欄與備註欄，不保留執行過程細節（誰做的、卡在哪、改了哪些
  檔案、CodeRabbit 抓到什麼）；過程去查 PR／commit 歷史。
- 說明文字只回答三件事：跑出了什麼（含數字）、之後哪裡會用到（哪個
  任務依賴它、哪份文件引用它）、對專案的幫助（解決了什麼、排除了什麼、
  或確立了哪個基準線）。不重述過程，除非過程本身就是結果（例如「查證
  後發現原假設不成立」）。
- 這份文件不受 CI 的 append-only 檢查約束（見
  `scripts/tools/check_append_only.py`），整理、濃縮、合併重複條目是
  正常維護。真正不能事後精簡的只有 `results/RESULTS_LOG.md`。

**操作**：

1. 任務做完：把 `WORK_BOARD.md` 那一段（表格＋說明）整段剪下，改寫成
   `WORK_BOARD_DONE.md` 的四欄格式與純結論說明（這一步就精簡掉過程），
   依完成順序貼到「完成事項」區尾端，原處刪乾淨。
2. 只是狀態更新（開始、換人、卡住）：直接覆蓋 `WORK_BOARD.md` 的那一段。
3. 一批任務同時完成可歸在同一小節標題下，但每個任務仍各自一張表格＋
   一段說明。
4. 兩份文件開頭互相指向對方。找不到某任務在哪一份，兩份都搜尋任務名稱。

---

## 零之五、senior24／協調 VM 沒有直接的 SSH 存取權

所有 AI agent 預設都沒有能直接連進協調 VM 或 senior24 的 SSH 金鑰。
這是刻意的金鑰隔離，不要嘗試繞過（例如自己跑
`ssh -i ~/.ssh/senior24_key ...`，金鑰不在 agent 環境裡，一定失敗）。

- 存取路徑：使用者（yutunglan11）在瀏覽器開 GCP Console 的「直接透過
  瀏覽器進行 SSH 連線」登入協調 VM；`senior24_key` 只放在協調 VM 上，
  再從那裡 `ssh` 到 senior24（100.96.152.16）。
- Agent 要在遠端執行指令，就把完整指令交給使用者貼上執行，再請使用者
  把輸出文字或截圖貼回來。
- 這個瀏覽器 SSH 分頁容易把「單引號包住、夾雜中文的多行指令」解析錯，
  卡在 `> ` 續行提示卻看似正常結束。交出去的指令寫成單行、用 `&&`
  串接、指令字串不夾中文；說明用另一則訊息講。
- 指令卡住沒輸出時，先請使用者開新分頁重連，不要急著假設指令或連線
  壞了。

---

## 一、分支與 Pull Request——所有人都走 PR

`main` 有保護規則，任何人（含 repo 擁有者）都不能直接 push，再小的
修改也一樣：

1. 開分支，命名 `<你是誰>/<這次要做什麼>`，例如 `claude/p9-redo`、
   `codex/estimator-v2`、`<同學名字>/hyades-tier1`。
2. 在分支上 commit、push。
3. 開 PR 合併回 `main`。PR 的目的是留下可見的變更紀錄，不是審核關卡：
   一般情況自己直接合併；只有判斷有風險（例如改到別人可能同時在動的
   地方）才等別人看過。
4. 合併後刪掉分支。

### 合併衝突

**逐行文字衝突**（GitHub 標紅擋下）：在自己的分支 `git fetch &&
git rebase origin/main`（或 `git merge origin/main`），逐段解決
`<<<<<<< / ======= / >>>>>>>`，`git add`、commit、push 後繼續合併。

**靜默語意衝突**（改到不同行，git 自動合併成功，但內容互相矛盾）是這個
專案最容易踩的坑。PR 只要碰到 `LIMITATIONS.md` 或 `PAPER_OUTLINE.md`，
合併前要重讀 main 上這兩份的**完整版本**（不只看自己的 diff），確認
新加的結論沒有跟別人剛合併的內容矛盾。PR 若推翻或修改既有結論，在 PR
描述裡寫明改了什麼、為什麼。

---

## 一之一、標註是誰改的——PR 標籤＋commit 前綴

每個 PR 開的時候貼上對應標籤：🔵 `by:claude`、🟣 `by:codex`、
🟢 `by:human`。Commit 標題加前綴，方便 `git log`／blame 搜尋：

```
[Claude] 修好 XXX
[Codex] 新增 YYY
[王小明] 調整 ZZZ
```

---

## 一之二、改既有段落時不要順手重新換行

git 逐行比對。修改段落中間幾個字卻同時重排整段換行，整段就會被判成
刪除＋新增，diff 看不出真正改了什麼，審查等於白審。這是「PR 看不懂在改
什麼」最常見的原因。

1. 修改既有段落時，沒有實質變化的行保持原本的斷行，長短不齊也不要重排。
2. 真的需要大範圍重新排版，開獨立 PR，描述寫明「純格式調整，沒有改變
   實質內容」，不跟新結果或程式修正混在一起。
3. 開 PR 前看一下 diff 大小：只改一個結論卻整份變色，多半是不小心重排
   了，照第 2 點拆開。

---

## 二、結果檔案——每個新結果都記進 `results/RESULTS_LOG.md`

`results/` 進版控，是唯一存放正式結果檔（`.npz`／`.csv` 等）的地方；
`logs/`、`isochrones/`、`kaggle_work/` 等太大或可重建，不進版控。

每產生一個新結果檔，在 `results/RESULTS_LOG.md` **檔尾加一行**（只附加、
不改舊行，兩人同時加行幾乎不會衝突）：

```
| 日期 | 執行者 | 腳本+參數 | commit hash | 結果檔名 | 一句話結論 |
```

執行者寫清楚是誰（「Claude session」「Codex」「王小明」）；commit hash
填**跑結果當下**的 `git rev-parse HEAD`，讓任何人都能對回當時的程式碼。

### 主控板（`status_dashboard/`）

主控板把「傳統法／前向模型／PDMF→IMF／穩健性診斷」四大類的步驟、對應
腳本與執行進度整理在同一頁。三個頁面共用一顆即時搜尋欄：「依步驟看」
（`/`）、「依雲端服務看」（`/workers`）、「時間軸」（`/timeline`，上半部
同步 `WORK_BOARD.md` 待辦，下半部是已完成工作，新到舊排序）。

「階段 → 步驟 → 腳本」對照表 `status_dashboard/stage_map.py` 是手動
維護的索引，沒有來源能自動生成。**新增 `WORK_BOARD.md` 任務或新腳本時，
回來 `stage_map.py` 加一筆**，道理跟「新結果要記進 `RESULTS_LOG.md`」
相同。

主控板只有一份，跟 `cloud_queue.py` 一樣常駐在協調 VM（見
`docs/reference/CLOUD_WORKERS_IAP_SETUP.md`），所有人看到同一份即時狀態。連線方式：

```bash
gcloud compute start-iap-tunnel instance-20260827-035250 8866 \
  --local-host-port=localhost:8866 --zone=us-central1-a \
  --project=project-f6e2d0e1-cd17-4cfb-a9b
```

接著開 `http://localhost:8866/`。Windows 可直接雙擊
`status_dashboard/launch_dashboard.vbs`（或桌面捷徑），會自動開 tunnel、
等連上、開瀏覽器。macOS／Linux 把上面那行存成 script 或 alias，或照
`status_dashboard/open_dashboard.py` 的邏輯自己寫啟動器。

**更新程式**：`app.py` 每次有人重新整理頁面都會自動 `git pull`，PR 合併
進 `main` 後下一次整理頁面就套用新版。`cloud_queue.py` 沒有自動更新，
改了要 SSH 進協調 VM 跑 `git pull && sudo systemctl restart
cloud-queue.service`。

---

## 三、Commit 與身分標示

- 人類協作者：用自己的 GitHub 帳號 commit。
- AI agent：commit message 結尾加 `Co-Authored-By: <agent 名稱與模型>
  <noreply 或該 agent 的識別 email>`，模型名稱填當次實際使用的，例如
  `Co-Authored-By: Claude <當次模型名稱> <noreply@anthropic.com>`。

---

## 四、遇到不明修改時

發現檔案被改了、不知道是誰或為什麼：不用追問或推測來源，先查
`git log`／PR 紀錄。真的查不到，且判斷這個改動可能有問題（跟已知結論
矛盾、看起來不完整），在 `RESULTS_LOG.md` 或對應 PR 留言標記，讓專案
擁有者決定是否處理。`CLAUDE.md`「發現有未知修改時」是同一條規則的
Claude 版本。

---

## 五、`LIMITATIONS.md` 怎麼寫（編輯前必讀）

`LIMITATIONS.md` 是給人看的限制清單，不是工作日誌。依嚴重程度 A–D 排序
（不依類型）。每條固定格式：標題行是編號＋問題名稱，內文只有
`**問題**：` 與 `**後果**：` 兩段。

| 級 | 意義 |
|---|---|
| A | 已引用的數字可能是錯的，或現有主張可能不成立。必須處理 |
| B | 每次計算都在用的未驗證假設。影響數字大小，不改變結論方向 |
| C | 結構性限制，修不掉。論文必須聲明 |
| D | 已知風險，尚未驗證。目前沒有污染現有結果的證據 |

**分級判準**：問「不理它的話，已寫進論文的數字會不會其實是錯的？」
可能會 → A；不會，但每次計算都在用這個未驗證假設 → B；不會，因為本來
就做不到 → C；不會，只是還沒證實 → D。B 與 D 最容易混：B 是已經在用的
假設，D 是還沒做的測試。

**不寫進 `LIMITATIONS.md`**：追查與修正過程、方法論心得（寫在本檔第六
節）、基礎設施故障（`docs/reference/KAGGLE_DIAGNOSIS.md`）、已推翻的說法
與作廢數值（`docs/reference/REFUTED.md`）。問題修好且對應工作全部跑完
確認後，整條搬到 `RESOLVED.md`（見五之一）——不留在原處寫「已修正」，
也不直接刪除，否則下次踩到同一問題時查不到做過的紀錄。

## 五之一、`LIMITATIONS.md` 與 `WORK_BOARD.md` 雙向追蹤

`LIMITATIONS.md` 記「哪裡有問題」，`WORK_BOARD.md` 記「誰在解決」，兩份
要互相標註。

**規則一**：`LIMITATIONS.md` 每條標題行後加括號，列出解決它需要的工作
與是否正在跑：

```
### A1 精修 bug 波及的結果尚未重跑（p2_final2_v3 是、p6_lowmass_v2 否）
```

`是`＝此刻真的在跑（本機佇列、Kaggle、雲端或協作者機器上）；`否`＝已
認領或已排隊但還沒開始，或還沒人認領。沒有任何對應工作的條目（多數 C、
D 類）寫 `（尚無認領工作）`，不要留白。

**規則二**：一項工作完成並上傳（commit／開 PR）後：

1. 把它從對應條目的括號裡刪掉（不是改成「已完成」；括號只列還沒做完
   的）。
2. 括號空了代表所需工作全部做完。這時重讀 `**問題**`／`**後果**`，確認
   新結果真的解決了問題——工作跑完不等於問題解決。確認後整條搬到
   `RESOLVED.md`（格式仿 `docs/reference/REFUTED.md`：曾經的問題／怎麼
   解決／解決時的結果／日期）。沒解決或只解決一部分，括號換成新的工作
   項目，不能清空了事。

**規則三**：在 `WORK_BOARD.md` 開始或更新工作時，任務名稱後的括號列出
它要解決的所有 `LIMITATIONS.md` 條目：

```
| ... | p2_final2 重跑（A1、A2） | ... |
```

跟 `LIMITATIONS.md` 無關的工作（環境設定、文件整理、協作流程）不用加。

**規則四**：改了 `WORK_BOARD.md` 就回頭更新 `LIMITATIONS.md` 對應括號：
新認領 → 加上（填「否」，除非當場開跑）；開始跑 → 「否」改「是」；
做完 → 套用規則二。兩邊都要改，否則兩份文件會各自漂移。

## 五之二、新發現要順手同步 `PAPER_OUTLINE.md`

每次因新發現編輯 `LIMITATIONS.md` 或 `WORK_BOARD.md`（新增限制、從括號
刪掉工作、搬到 `RESOLVED.md`），**當場**讀 `PAPER_OUTLINE.md` 中邏輯上
相關的章節，確認兩件事：

1. **資訊是否過時**：引用的數字、方法描述、既有結論是否被推翻或需要
   補警語。
2. **方向是否要修正**：新發現會不會動搖某章節的主賣點或敘事（例如
   「模型對等時線選擇穩健」若其實是別的機制造成的表面現象，就照實
   改寫，不因為是主賣點而迴避）。

需要改就直接改，不必等使用者開口。不必通篇重讀（400 多行），但範圍
不確定時寧可多查一節。

## 五之三、`docs/PROJECT_TIMELINE.md` 定期更新

這份是逐日進度日誌，給使用者快速回顧哪天做了什麼、發現了什麼。只記
改變結論、抓到 bug、架構調整的事，略過單純的 PR merge、CodeRabbit 小修；
格式維持「日期＋條列重點」。有實質進度的那天結束前（或下次有人碰這份
文件時）補上當天一節；發現舊內容已過時就直接訂正。不需要回頭重寫更早
的日期。

---

## 六、已經犯過、不要再犯的錯

1. **撞牆先查底層資料實際涵蓋到哪，不要反射性放寬搜尋軸。** 放寬只在
   「網格有資料但軸設太窄」時有用；網格沒那段資料時，放寬只會擴大簡併
   平坦區，argmax 報出的「最佳值」是由搜尋軸邊界決定的。
   （`pipeline/joint_fit.py` 載入時會比對搜尋軸與網格實際涵蓋並印警告，
   警告要真的去看。）
2. **先驗、搜尋軸、網格實際涵蓋，三層邊界必須一致。** 曾經三層各自寫死
   成 0.60 ＞ 0.40 ＞ 0.336，互不知道彼此。
3. **抽查兩三筆就推論「其他應該沒事」是錯的。** 系統性掃描全部，再對
   候選逐一人工核對（自動掃描也會有假警報）。
4. **診斷腳本的設定不可直接複製到產出論文數字的腳本。** 關掉先驗適合
   觀察概似本身，不適合產出最終數字。
5. **結果檔案不可被重跑覆寫。** 固定檔名的 `np.savez` 會讓前一次的完整
   參數向量永久消失，事後無法核對邊界。輸出檔名要帶 tag。
6. **兩個現象同時出現，不要假設同一成因**，先個別驗證（案例見
   `docs/reference/KAGGLE_DIAGNOSIS.md`）。
7. **懷疑外部服務前，先確認自己組出來的路徑與參數字串。** 100% 重現的
   失敗是確定性的程式 bug，不是平台不穩。
8. **改了搜尋／精修演算法，要驗證每一階真的執行了。** 回傳值若全部落在
   粗網格格點上，代表精修根本沒跑。
9. **狀態查證時，文件裡有對應的舊敘述就當場改掉。** 只在新地方補一筆會
   讓文件自相矛盾，下次讀到過時那半會走錯方向。

---

## 七、開 PR 前快速檢查

- [ ] 分支名稱標明是誰／哪個 agent
- [ ] 只改派工清單的 PR：標題以 `[派工]` 開頭；還改了其他檔案就不帶
      （零之一）
- [ ] 新結果檔案已在 `results/RESULTS_LOG.md` 加一行
- [ ] commit message 有正確的身分標示
- [ ] 碰到 `LIMITATIONS.md`／`PAPER_OUTLINE.md`：已重讀 main 上的完整
      版本，確認沒有跟別人的新內容矛盾
- [ ] 編輯 `LIMITATIONS.md`：條目照第五節的格式與分級
- [ ] 編輯 `WORK_BOARD.md`：任務名稱標了對應條目，且已同步
      `LIMITATIONS.md` 括號狀態（五之一）
- [ ] 新增 `WORK_BOARD.md` 任務或 pipeline 相關腳本：已在
      `status_dashboard/stage_map.py` 加一筆（第二節）
- [ ] 某條 `LIMITATIONS.md` 因這次工作完全解決：已搬到 `RESOLVED.md`
- [ ] 有新發現或推翻舊說法：已檢查 `PAPER_OUTLINE.md` 相關章節（五之二）
- [ ] 編輯了規則類文件：沒有加入帶日期的沿革敘事，理由寫在
      `CHANGELOG.md`
