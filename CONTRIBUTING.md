# 協作規範（給所有人類與所有 AI agent）

這份文件給**所有**要碰這個 repo 的人與 agent 讀——不只 Claude。若你是
Claude，先讀 `CLAUDE.md`；這份是通用規則，兩者都要遵守。

**目的**：多個 agent（Claude、Codex、其他）與多個人同時在同一個 repo
上工作，需要讓大家對資料共享保持同步、有條理地找到彼此跑過的結果、
改過的程式、以及對應的版本。

---

## 一、分支與 Pull Request——所有人都要走 PR，沒有例外

`main` 分支設了保護規則：**任何人（含 repo 擁有者）都不能直接 push 到
main**，包括修 bug、加一個檔案這種小事也一樣。流程一律是：

1. 開一個新分支，命名 `<你是誰>/<這次要做什麼>`，例如：
   - `claude/p9-redo`（Claude 工作階段）
   - `codex/estimator-v2`（Codex）
   - `<同學名字>/hyades-tier1`（人類協作者）
2. 在分支上工作、commit、push 到這個分支。
3. 開 PR 合併回 `main`。**PR 不強制要求別人 review 才能合併**——
   目的是留下「這裡發生過什麼變更」的可見紀錄，不是設審核關卡。
   除非你自己判斷這次改動有風險（例如改到別人可能同時在動的地方），
   才需要等其他人看過再合併；一般情況下開了 PR 可以自己直接合併。
4. 合併後**刪掉這個分支**，避免分支越積越多。

### 遇到合併衝突怎麼辦

**逐行文字衝突**（GitHub 直接擋下、標紅）：在自己的分支上
`git fetch && git rebase origin/main`（或 `git merge origin/main`），
git 會標出 `<<<<<<< / ======= / >>>>>>>`，逐段決定留哪邊，
`git add` + commit + push 後繼續合併。這是機制性的，不需要額外判斷。

**靜默語意衝突**（改到不同行，git 自動合併不報錯，但內容互相矛盾）——
**這是這個專案最容易踩到的坑，必須額外注意**：任何 PR 只要碰到
`LIMITATIONS.md` 或 `PAPER_OUTLINE.md`，合併前一定要重新讀一次 main
上這兩份文件**目前的完整版本**（不是只看自己這次的 diff），確認自己
新加的結論沒有跟其他人剛合併進去的東西矛盾。這兩份文件本來就有「推翻
舊說法要回頭標記原處，不能只在新處新增」的維護規則，同一個道理套用在
多人協作：**你的 PR 如果推翻或修改了某個既有結論，要在 PR 描述裡明講
改了什麼、為什麼**，讓後面合併的人看得到。

---

## 一之一、標註是誰改的——PR 標籤 + commit 前綴

Repo 已經建好三個彩色 PR 標籤：🔵 `by:claude`、🟣 `by:codex`、🟢 `by:human`。
**每個 PR 開的時候都要貼上對應標籤**，PR 列表上一眼就看得出誰做的。

Commit 標題也統一加前綴，方便 `git log`／blame 直接搜尋：

```
[Claude] 修好 XXX
[Codex] 新增 YYY
[王小明] 調整 ZZZ
```

三層一起用（標籤＋前綴＋git blame 本身）不需要額外工具就有完整的
可視化追蹤。

---

## 二、結果檔案規範——每次算出新結果都要記進 `results/RESULTS_LOG.md`

`results/` 資料夾本來就進版控，這是唯一該存放正式結果檔案（`.npz`／
`.csv` 等）的地方（`logs/`、`isochrones/`、`kaggle_work/` 等不進版控，
太大或可重建）。

**新規則**：每次產生一個新的結果檔案，在 `results/RESULTS_LOG.md`
**檔案尾端加一行**（附加寫入，不要改動既有的行——這是刻意設計成
低衝突風險的格式，兩個人同時加行幾乎不會撞在一起）：

```
| 日期 | 執行者 | 腳本+參數 | commit hash | 結果檔名 | 一句話結論 |
```

執行者填清楚是誰／哪個 agent（例如「Claude session」「Codex」
「王小明」），commit hash 填**跑這個結果當下** `git rev-parse HEAD`
的值，讓任何人事後都能精確對回當時的程式碼版本，不必另外拉 git tag。

---

## 三、Commit 與身分標示

每筆 commit 的訊息裡要能看出是誰／哪個 agent 做的變更：

- 人類協作者：用自己的 GitHub 帳號 commit，訊息正常寫。
- AI agent：commit message 結尾加 `Co-Authored-By: <agent 名稱>
  <noreply 或該 agent 的識別 email>`，例如
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`。
  這樣 `git log` 隨時看得出這筆是哪個 agent 代跑的，不用去問。

---

## 四、遇到不明修改時

如果你發現檔案被改了、但不知道是誰／為什麼——**不需要主動追問或花
token 去猜**，先看 `git log`／PR 紀錄能不能查到；真的看不出來，
且你判斷這個改動可能有問題（跟已知結論矛盾、看起來不完整），
在 `RESULTS_LOG.md` 或對應的 PR 裡留言標記，讓專案擁有者決定要不要
進一步處理。這條跟 `CLAUDE.md` 裡「發現有未知修改時」那條規則是同一件事，
這裡是給非 Claude 的 agent／人看的版本。

---

## 五、快速檢查清單（開 PR 前）

- [ ] 分支名稱有標明是誰／哪個 agent
- [ ] 新結果檔案已經在 `results/RESULTS_LOG.md` 加了一行
- [ ] commit message 有正確的身分標示
- [ ] 若碰到 `LIMITATIONS.md`／`PAPER_OUTLINE.md`：已經重讀過 main
      上的完整版本，確認沒有跟別人的新增內容矛盾
