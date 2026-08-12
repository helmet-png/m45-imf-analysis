# Kaggle 派工：掛載路徑與已解決的故障

從 `LIMITATIONS.md` 分出來的一份。這是基礎設施操作紀錄，不是科學限制，
所以不放在 `LIMITATIONS.md`。**問題已在 2026-08-12 解決**，保留這份是為了
記住正確的掛載路徑格式，以及一次會重演的判斷錯誤。

---

## 掛載路徑格式（會踩的坑）

Kaggle 現在把 dataset 掛在：

```
/kaggle/input/datasets/<擁有者帳號>/<dataset-slug>/
```

比舊格式 `/kaggle/input/<dataset-slug>/` **多兩層**（`datasets/` 加擁有者
帳號）。`kaggle_sync.py` 的 `make_kernel()` 原本寫死舊格式，所以
`_wait_input()` 檢查的路徑從來不是真正掛載的位置。

修正（`kaggle_sync.py:162`）：

```python
base = "/kaggle/input/datasets/" + username + "/m45-imf-" + slug + "/"
```

`kaggle_queue.py` 的 `is_mount_race_failure()` 只比對子字串 `/kaggle/input/`，
不受路徑深度影響，不需要改。

驗證：修好前每次都等滿 280 秒才 `ERROR`；修好後 10.7 秒找到檔案、狀態
直接 `COMPLETE`。

---

## 這個 bug 影響過的派工

`p9a_more_reps`、`p6_lowmass_ext_retry`、`p9a_redo`、`p9c_mist_redo`、
`mount_fix_test`、`mount_fix_retest`。

全部都是「執行失敗、沒有產出任何數字」，不是「產出被污染的錯誤數字」，
**不影響任何已引用的結果**。損失只有重試時間與 Kaggle quota。

---

## 被排除的三個錯誤假設

| 假設 | 為什麼被排除 |
|---|---|
| 時序競態，等久一點就好 | in-kernel 原地等 280 秒完全沒等到，1KB 單一檔案沒有理由要等這麼久 |
| 帳號未完成手機驗證 | 已驗證的 `helmetalbert` 重測 5 次，結果與未驗證時完全一樣 |
| Kaggle 平台異常（Firebase） | 三個獨立帳號、三台機器、100% 重現——確定性的程式碼 bug 不會是機率性的平台不穩 |

**「Editor loading 卡死」跟掛載問題無關**：那是使用者瀏覽器擴充功能干擾
React 頁面，無痕視窗就正常。兩件事只是時間上湊巧同時出現。

---

## 其他

- 跨專案通用寫法在 `~/.claude/kaggle-compute-howto.md`（那是本機
  `~/.claude/` 底下的全域檔案，不在這個 repo 裡，其他機器的 agent 讀不到，
  需要另外建置）。
- 恢復派工與否、恢復哪些項目，由使用者或負責的 session 決定。
