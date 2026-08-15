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

---

## 2026-08-14：重量級設定（`--repeats 10 --refines 3,3,3`）在 Kaggle 上不可行

修好 `results/` 目錄 bug 後，用修好版本重推了 `p2-final2-v3-fixed`
（任務名稱 `p2_final2_v3`，headline 數字，config C，
`--repeats 10 --refines 3,3,3`，justinlan11 帳號）。**跑了約 11.4
小時，pull 回來的 log 顯示 10 次重複裡只跑完第 1 次**（`logage=8.026`、
`alpha=2.396`、耗時 40934 秒 ≈ 11.37 小時**單次重複**），之後被系統
標記 `CANCEL_ACKNOWLEDGED`。**這個狀態只能確認 kernel 被取消了，取消
原因未明**——沒有拉到 Kaggle 的 event log，「平台自己依 session 時間
上限中止」只是推測（跟已觀察到的耗時量級一致，但不是唯一可能，也
可能是有人手動取消），不要當成已證實的事實引用。

**換算**：單次重複要 11.4 小時，10 次重複要 100+ 小時，遠遠超過
Kaggle 免費 CPU-only notebook 的單次 session 上限（約 9–12 小時）。
**`--refines 3,3,3`（三階精修）比 P9a-redo／P9c v2 用的 `--refines 3,3`
（雙階）貴很多**，這兩個各自跑 10 次重複只花數小時就完成，差別就在
多一階精修。

**結論：這個特定設定（三階精修 + 10 次重複）在 Kaggle 上不可行**，
不是掛載問題也不是 `results/` bug，是純粹的計算量超過單次 session
能負擔的上限。這種等級的重跑應該在本機 8 核佇列（`queue.txt`，
Windows ARM64 機器）上做，不要再排進 `kaggle_queue.txt`。

**唯一拿到的資料**（不是完整結果，只有 1/10 次重複，不能引用當
headline 數字）：logage=8.026（106.2 Myr）、A_V=0.359、f_bin=0.602、
**alpha=2.396**、MH=−0.022、q_gamma=−0.867、dav=0.500——跟先前記錄的
舊 headline（α=2.387±0.060）同量級，方向上沒有意外，但單次重複沒有
統計意義，不能取代真正的重跑。

**2026-08-15 補充：`CANCEL_ACKNOWLEDGED` 的原因已確認，不再是推測**。
另一個工作（`p6b_inject_lowmass_v2-fixed`，`inject_lowmass.py`，
`--trials 3 --refines 3,3`，account5）同樣被取消，這次 log 完整拉到
了明確的錯誤訊息：

```
nbclient.exceptions.CellTimeoutError: A cell timed out while it was
being executed, after 43200 seconds.
```

**43200 秒 = 12 小時整**——Kaggle notebook 執行框架（`nbclient`）本身
對單一 cell 有硬性 12 小時逾時，這就是兩個工作都被取消的確切原因，
不是猜測、不是帳號或平台不穩。`p6b` 的 log 顯示只跑完 3 次試驗裡的
第 1 次（`p_true=0.9 trial1`，耗時 30931 秒 ≈ 8.6 小時）就撞到這道牆
——**代表這個 12 小時限制不只擋掉 headline 這個特別重的設定，連
`inject_lowmass.py` 這種相對輕量的設定也擋不過去**，Kaggle 免費
CPU-only notebook 對這整類 `n_syn=40000` 等級的正式跑而言，額度都
偏緊。

**下一步**：
1. `p2_final2_v3`（headline，A1+A2 兩個修正一起套用）已改用
   `--repeat-offset`（見另一個 PR）拆成 5 個帳號各跑 1 次重複平行進行
   ——單次重複 11.4 小時仍在 12 小時內，應該能個別完成，不用再排本機
   佇列的完整 10 次重複（`p2_final2_v3_timing` 那個單次時間門檻仍保留
   在 `queue.txt`，當作跟本機速度的對照組）。
2. `p6b_inject_lowmass_v2`：`inject_lowmass.py` 目前沒有等價的
   `--repeat-offset`／trial 偏移機制，這個 12 小時的牆還沒解決，
   需要之後補上類似的拆分機制，或改在本機佇列跑。
