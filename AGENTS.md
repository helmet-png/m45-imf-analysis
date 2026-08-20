# AGENTS.md

這份是給 Codex（以及其他非 Claude 的 AI agent）的進入點。

**先讀 `CONTRIBUTING.md`**——那是這個 repo 的通用協作規則，PR 流程、
分支命名、commit 身分標示、`results/RESULTS_LOG.md` 記錄規則、以及
`LIMITATIONS.md` 的撰寫格式與過去犯過的錯，都在裡面，適用於所有人與
所有 agent，不是 Claude 專屬。

`CLAUDE.md` 是 Claude Code 專屬的補充規則（教學者角色定義等），跟你
無關可以不用讀；但如果好奇這個專案怎麼跟 Claude 協作，也可以參考。

一句話摘要（完整規則以 `CONTRIBUTING.md` 為準，這裡不重複）：
- `main` 分支所有人都要走 PR，沒有例外。
- 開分支用 `codex/<這次要做什麼>` 命名。
- commit 訊息結尾加 `Co-Authored-By: Codex <noreply@openai.com>`。
- 開 PR 貼 `by:codex` 標籤。
- 產出新結果檔案要記進 `results/RESULTS_LOG.md`。
- 碰 `LIMITATIONS.md`：先讀 `CONTRIBUTING.md` 第五、六節的格式與教訓，
  再讀 `LIMITATIONS.md` 目前的完整版本（不是只看自己這次的 diff）。
- 開始新工作前先查 `WORK_BOARD.md`，避免跟其他 session／agent 重工。
- 規劃類文件裡寫的「結論」「判斷」，預設只代表寫下當下的想法、不是
  決議——語氣要保留（用「初步判讀」而非「結論是」），但推理過程跟
  數字要寫完整；別人發現站不住腳可以直接改，不用先問（見 `CONTRIBUTING.md`
  零之二）。
