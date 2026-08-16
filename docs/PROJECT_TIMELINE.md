# M45 IMF 專案進度日誌

整理依據：GitHub 前（8/1–8/8）依 `results/RESULTS_LOG.md` 表格裡**已經記錄好的
明確日期**回填（那份表格自己註明日期原始來源是檔案 mtime，但這裡讀的是表格裡
寫定的日期字串，不是去讀即時的檔案 mtime——checkout／複製後 mtime 會變，
不能拿來當史料來源）；GitHub 後（8/9 起）依實際 git commit 歷史（截至
2026-08-16 共 189 筆，逐日彙整重點，省略純粹的 PR merge／CodeRabbit 小修這類
雜訊，只留下真的改變結論或架構的項目）。這個總數會隨後續 commit 過時，
不必每次都回頭更新，只在整理新的一天時順便核對一下數量級是否合理即可。

---

## GitHub 之前（本機階段）

### 8/1
* `run_pipeline.py` 舊版循序擬合架構首次跑通：第3步年齡/消光、第4步四法雙星判定（前向模型/RUWE/CMD偏移/GaiaNSS）、第5步舊版循序 IMF
* 質量分層首次量到：α(r) 核心(0-1度) 1.77 → 外圍(3-5.1度) 2.29
* pyUPMASK 自洽先驗修正（6,857 顆星成員機率，均等先驗 vs 自洽先驗）

### 8/3
* 舊版 MCMC 四/六參數聯合擬合（`run_joint.py`）——鏈未收斂（τ=822–1454），誤差棒不可信
* q_gamma 輪廓測試：固定 q_gamma 造成 alpha 跨度 0.1（33 倍統計誤差），確認必須當 nuisance
* MH 先驗敏感度掃描（`profile_mh.py`）

### 8/4
* `measure_overconfidence.py`：證實 Poisson-Hess 概似曲率過度自信約 4 倍（切半法 0.106／注入回收 0.144 vs 曲率法只有 0.030）
* 分箱數敏感度測試：**推翻**「換格子數把中心值推動 24–30 倍統計誤差」的錯誤說法，正確結果是冪次 −0.18/−0.22，分箱只是有損壓縮不是資訊損失源
* 切半實驗（前半＋後半兩組獨立擬合）

### 8/5
* `fit_real.py` 第一版出現（item2 系列，config A/C 比較）——後來整個專案的核心擬合腳本

### 8/6
* `fit_real.py --tag _parsec`：PARSEC 版 config A/C 重複結果，貢獻等時線比對的 PARSEC 基準

### 8/7
* `fit_real.py --grid mist`：換 MIST 等時線量系統誤差，恆星演化模型效應：舊模型 0.240、修正模型 0.000

### 8/8
* `traditional_accounting.py` 原始版本（全當單星／CMD 剔除兩變體）
* PARSEC DR2 濾光片版（`p3b_dr2fit`）：拆解出純濾光片效應 0.04（可忽略）

---

## GitHub 之後

### 8/9 —— 上 GitHub，第一批系統性結果
* 初始 commit 推上 GitHub：「M45 疏散星團質量函數的分析選擇誤差預算」
* 補推 `results/` 全部既有計算結果
* **低質量段冪次系統誤差量化**：d(alpha)/d(p) = −0.495±0.111（4.5σ），傳播 Kroupa(2001) 不確定度得到 **0.248**——全專案最大單一誤差項
* 新增 P9（MH 鎖定檢驗），修 P6b 貼牆問題
* 修好 P9/P6b 撞到的三道從未測過的邊界；`inject_lowmass.py` 改成逐次試驗容錯
* Kaggle 多帳號並行派工基礎建設（`kaggle_accounts.py`／`kaggle_sync.py`／`kaggle_queue.py`）

### 8/10 —— 抓到「先驗根本沒被用到」的大 bug
* **更正 P9 的 MIST 結論**：原本以為的異常其實是網格覆蓋不足造成的假象
* **發現 MH 先驗從未被真正使用過**——`config.toml` 宣告的高斯先驗被程式碼寫死覆寫成均勻先驗，全專案結果審查波及範圍
* P6b 完成：低質量段冪次可辨識性驗證通過（p_recovered/p_true 跟隨比值 0.92）
* P9a-redo 乾淨完成：α=2.440±0.180；P9c 完成：MIST 鎖 MH 給出不合理年齡（50–63 Myr），**證實表 4「等時線穩健性」主賣點不成立**
* 傳統法五變體雙星修正比較完成：全部落在 2.37–2.42，文獻解析修正法幾乎無偏
* `LIMITATIONS.md` 待辦逐項體檢，建立 A–D 分類標準

### 8/11 —— 正式走 PR 流程
* **repo 開始要求所有人走 PR**：`CONTRIBUTING.md` 建立，PR #1–#10 陸續合併
* 回填 `results/RESULTS_LOG.md` 規範建立前的全部 27 筆歷史結果
* 訂正「文獻解析修正法＝獨立驗證」的用詞錯誤，發現 alpha 範圍外推問題，該方法降級為案例討論
* 精確率／召回率驗證 CMD 偏移法 vs 前向模型後驗機率兩種雙星偵測法（CMD 法精確率高召回率低，前向模型相反）
* `教學_傳統法誤差核算.md`、`教學_前向模型.md` 兩篇完整教學文件寫成（高一數學到最終結果的完整推導）
* `multi_stage_best()` 精修 bug 第一次修復（後來發現 merge 時遺失，重做了兩次才真正落地）
* `CLAUDE.md`：教學者角色定義、commit 優先權規則
* 多星團 Tier 1 啟動：NGC 3532／Praesepe 的 HR23 成員表已抓取

### 8/12 —— PDMF→IMF 方向啟動，N-body 環境裝好（39 個 commit）
* `WORK_BOARD.md` 建立（工作認領表，避免多 agent 重工）；CodeRabbit 自動審查設定上線
* Kaggle 掛載問題多輪交叉驗證，最終抓到真正根因：路徑寫死成舊格式，不是平台/帳號問題
* 新協作者機器（x64，Yu Tung Lan）加入，完成 pipeline 端到端驗證
* **PDMF→IMF 研究方向啟動**：方法調查、動力學年齡估計、alpha(r) 徑向診斷實驗、四條路線（A 觀測全域／B 經驗校準／C 自跑 N-body／D LIMEPY）規劃定案
* **P10**：修好 `fit_real.py` 寫死均勻先驗的 bug，重新打開高斯 MH 先驗
* `教學_PDMF轉IMF.md` 新增
* `LIMITATIONS.md` 改版：依嚴重程度 A–D 排序、固定格式
* `limepy` 套件名稱訂正（原本誤裝到 PyPI 上同名但完全無關的問卷調查工具）
* **第 5 步（N-body）環境準備完成**：MSYS2/MinGW-w64 編出完整 PeTar＋mcluster，不需要 WSL，Windows 可攜性問題解決

### 8/13 —— 全專案最活躍的一天（58 個 commit）
* N-body 環境進一步驗證，Converse & Stahler (2010) 初始條件參數訂正
* **N-body 第一個 pilot 跑完**：alpha(r) 方向跟觀測一致；隨後 CodeRabbit 抓到密度中心雙重扣減的真 bug 並修正
* **開機/登入自動重啟本機佇列機制建立**（防止重開機浪費算力，起因是曾經浪費 8.5 小時）
* Kaggle 多帳號正式派工啟動（4 項重跑）
* 文件與程式碼依主題重新整理成資料夾結構
* `LIMITATIONS.md` 與 `WORK_BOARD.md` 雙向工作追蹤協議建立
* **PDMF→IMF 第 3 步：LIMEPY 多質量平衡模型**第一次擬合，CodeRabbit 抓到 `Sigmaj` 單位不一致的真 bug，修正後 reduced chi² 從 8.90 降到 **0.75**（擬合品質從差變好）
* B/C/D 類待認領工作全面體檢：解決 2 項、升級 1 項（D7→A6 白矮星污染）、新增 8 項待辦
* **A6**：`assign_masses()` 加顏色一致性檢查，量化白矮星混入影響；順藤查到第二顆高置信度非成員候選星
* 修正 Kaggle 派工從沒建立 `results/` 導致存檔失敗的嚴重 bug

### 8/14 —— 非成員排除定案，表 4 穩健性正式推翻
* `rv_outlier_member_exclude`：A6 全部解決（白矮星＋RV 離群星雙重排除，對頭條數字影響可忽略）
* `bright_outlier_investigate`（D9）身分追查；`c20_reconcile_disagree_set` 重建原始「20 顆判定分歧」定義，順藤解開 D9 身分之謎——**確認是非成員**（RV 偏離 bulk_rv 達 350σ）
* `rv_binary_investigate`（C3）：蒙地卡羅估計分光雙星能解釋多少 RV 離群比例
* `selection_color_dependence_fix`（C18）量化，不需要升級
* P9c v2、P9a-redo v2 乾淨重跑：**A4「表 4 等時線穩健性」正式定案不成立**（年齡差一倍、alpha 差 0.285，1.9 倍合併標準誤）
* headline `p2_final2_v3` 在 Kaggle 上實測不可行（會超過免費 session 上限），改排本機佇列
* `run_queue.py`：關螢幕時要求系統維持滿速運算（keep-awake 機制）
* 推送 `verify_bprperr_off/on` 結果（B1 A/B 對照組）

### 8/15 —— 多星團普適性協定 + 續傳架構
* **多星團普適性研究分層協定**寫進 `PDMF_TO_IMF_PLAN.md` 第八節（Tier 1／Tier 2 架構，為未來擴展到多星團定調）
* `fit_real.py`：加上逐次重複即時存檔，支援中斷後續傳，不再整批重算（起因是 `p2_free_lowmass` 單次重複跑了 44 小時，中斷會全部白工）
* 腳本整理歸類進 `scripts/` 子資料夾
* PR #53：修正 `queue.txt` 漏帶 `--configs C` 的現役 bug（radial_r1 因此多跑 3 倍時間）＋ `fit_real.py` 續傳加設定 manifest 驗證與寫入鎖
* `run_queue.py` 加卡死監看機制（CPU 時間長時間零增量自動偵測、砍掉重試）
* 新的多星團規劃文件 `PLAN_多星團擴展.md`：候選星團挑選、統計檢定力估計、Pang+2024／Li+2026 文獻比對
* 拉回 headline `p2_final2_v3` 已完成的 5/10 次 Kaggle 重複結果，避免資料遺失

### 8/16 —— run_queue.py 卡死根因修好並驗證有效，PDMF→IMF 第 2 步四項全部跑完
* 修正 `stalled_giveup` 被誤判成「完成」的 bug——放棄重試後永久跳過，實際沒有產出結果
* 卡死自動重試前加 30 秒緩衝
* `measure_overconfidence.py`：Pool worker 自己宣告 keep-awake，補上真正燒 CPU 的行程沒被保護的缺口
* `PLAN_多星團擴展.md` 第十一節：MiMO 金屬量方法論查證 + 找到比 MiMO 更大的 Gaia XP 全天星表交叉比對路線
* 新增 D10：config C/D 的 alpha 一致性只在假資料驗證過，真實資料還沒直接比較（教學問答中發現的缺口）
* PR #59 CodeRabbit review 抓到並修好 `run_queue.py` **兩個真 bug**：CPU ticks 基準沒在下降時重設（`multi_stage_best()` 換 Pool 階段時 ticks 真的會暫時下降，舊邏輯誤判成卡死）、`proc.kill()` 在 Windows 上不會砍掉子孫行程（解釋了反覆出現的孤兒 worker BrokenPipeError）
* **實測驗證修正有效**：套用修正後重跑，`radial_r3` 連續近 6 小時沒有再卡死一次（之前規律每 68–98 分鐘卡一次），最終乾淨完成
* **PDMF→IMF 第 2 步徑向診斷四項全部跑完**（config C，單次重複、單階精修，會議前初步方向數字）：r1(0-1°)=2.10、r2(0-2°)=2.43、r3(0-3°)=2.50、rall(全樣本)=2.43——r1→r3 遞增支持核心到外圍的質量分層方向，但 rall 比 r3 低、不是單調，原因未解，需要正式 `--repeats 5 --refines 3,3` 重跑才能判斷是雜訊還是真訊號
* 新增 `docs/PROJECT_TIMELINE.md`（本文件）+ `CONTRIBUTING.md` 五之三定期更新規則
