# 最新同步整理：Codex 上傳與協作者工作（2026-08-13）

本文件比較截至 2026-08-13 的兩條工作線：

- **Codex 分支／草稿 PR #45**：`codex/pdmf-imf-overnight`，目前領先舊共同基底
  6 commits，尚未與最新 `main` 整合。
- **協作者已合入 `main` 的工作**：最新 `main` 為 `777b040`，已包含最新文件、
  LIMEPY、N-body、污染診斷、Kaggle 派工與 review 修正。

> 重要：PR #45 與最新 `main` 顯示無法自動合併。這不是研究結果衝突的證據，而是
> 兩邊同時修改文件、工作板與程式結構；整合時需要逐檔保留雙方內容。

## 一覽表

| 面向 | Codex 最新上傳（PR #45） | 協作者已完成／合入 main | 關係與下一步 |
|---|---|---|---|
| 平衡空間外推 | LIMEPY 2,205 模型、5,000 bootstrap；5.1° 空間修正 `Δα=+0.004` | LIMEPY 多質量平衡模型第一次擬合；另修正 King/Woolley reduced chi-square 標示與 Sigmaj 單位 | **互補但不可直接混合數字**；整合時以 main 的單位／統計修正為基礎，再重跑 Codex 的 coverage grid。 |
| 動力學前向驗證 | REBOUND 72 個高精度 + 32 個大 N 的方向與能量測試；正式 PeTar 10-run grid、分析器與彙整器 | Windows x64 MSYS2/MinGW 已編好 PeTar+mcluster；第一個 N-body pilot 的 `α(r)` 方向符合觀測；`nbody_setup/` 已可重現 | **最直接的接力**：用 main 的已建環境跑 Codex 的 10-run PeTar grid。 |
| PDMF→IMF 定義 | 分離 survival、stellar evolution、finite aperture；新增 component/primary/system-total/photometric bridge | 前向模型、徑向 bin、聯星比例定義與密度中心有 review 修正 | **必須整合**：前向模型取 `primary` correction，傳統單星法取 photometric 系列；不可把 component correction 直接加在 unresolved-system 結果。 |
| PeTar 快照安全 | 排除 artificial particles；恢復 subsystem member 的 `mass_bk`；未知狀態 fail-closed | PeTar 建置與初步環境測試已可重現 | **可直接採用 Codex 防護**，並在正式 run 對照 `N_real/N_all`。 |
| 觀測資料品質 | 提醒 Gaia selection／潮汐尾仍未進 mock catalog | A6 白矮星與非主序污染檢查；`assign_masses()` 加 color consistency；新增 radial velocity；修正邊界重複計數與密度中心 bug | **main 優先**：先將這些觀測修正反映到 PeTar mock selection，再比較模型。 |
| 多星團／普適性 | 尚未把正式 PeTar 推廣到 NGC 3532／Praesepe | Kaggle 多帳號佇列排入四個優先重跑；研究工作板與 limitations 有雙向追蹤 | 先完成 M45 formal run，再依統一 selection／年齡基準擴展。 |
| 文件與交接 | `CLAUDE_HANDOFF_PDMF_IMF_2026-08-13.md`：完整 PeTar 接手說明 | `PAPER_OUTLINE.md`、`LIMITATIONS.md`、`WORK_BOARD.md`、教學文件與目錄重整 | 內容互補；合併時更新交接檔所指的路徑。 |

## Codex 最新上傳：PR #45

PR：[**#45 — Add PDMF-to-IMF LIMEPY and N-body validation**](https://github.com/helmet-png/m45-imf-analysis/pull/45)

分支：`codex/pdmf-imf-overnight`  
Commits：`94d9df4`、`b1ff999`、`7be9c4c`、`fce9793`、`d3aa9d2`、`054baad`

### 已完成的研究與程式

1. **LIMEPY 空間 coverage smoke test**
   - 2,205 個多質量平衡模型全部收斂。
   - 最佳模型：`phi0=4`、`g=1`、`delta=0.30`、`rh=4 pc`、`rt=19.73 pc`。
   - 5.1° 內 coverage 約 98.5%–99.3%。
   - 傳統 PDMF alpha 由 1.982 變為 1.986，純平衡空間修正 `Δα=+0.004`。
   - 5,000 bootstrap：95% 區間 0.000–0.014。

2. **REBOUND N-body 前置驗證**
   - 高精度 72 runs：能量通過的 52 runs 中，94.2% 顯示外圈相對內圈的
     alpha 對比增加；86.5% 顯示低／高質量半徑比增加。
   - N=1,024/2,048 的 32 runs：28 runs 通過能量門檻；方向結果一致。
   - 定位：驗證分析鏈方向，不是 M45 的定量修正。

3. **PeTar 正式實驗管線**
   - `petar_m45_grid.csv`：10-run screening grid。
   - `petar_m45_grid.py`：參數與系統數／星數一致性驗證。
   - `petar_pdmf_analysis.py`：按 ID 分解 escape/survival、恆星演化、視野效應；
     支援 32 視線方向與 radial profiles。
   - `petar_pdmf_ensemble.py`：輸出 median、q16–q84、seed scatter，並拒絕
     synthetic、重複 run ID 與不一致 mass range。

4. **PeTar raw snapshot 人工粒子防護**
   - `status>0`：移除 artificial／CM particles。
   - `status=0 && mass_bk=0`：保留 physical single。
   - `status<0 && mass_bk>0`：保留 member 並以 `mass_bk` 還原質量。
   - unknown 狀態：停止，不猜測。

5. **component 與 unresolved-system 定義橋接**
   - `petar_system_catalog.py` 讀取 processed single/binary/triple/quadruple
     catalogs，遞迴展平階層多星系統。
   - `pdmf_system_definition_bridge.py` 同時計算 component、primary、
     system-total、photometric beta=2/3/4 質量函數。
   - 前向模型應接 `primary`；傳統單星質光反推應以 photometric 系列測敏感度。

6. **Claude 交接文件**
   - `CLAUDE_HANDOFF_PDMF_IMF_2026-08-13.md` 提供正式 PeTar 的完整接續順序、
     檢查條件、已知陷阱與自測指令。

### Codex 已知限制

- `+0.004`（LIMEPY）與 `+0.283`（synthetic PeTar sign test）都不是正式 M45
  動力修正值。
- 正式 125 Myr PeTar snapshots 尚未產生。
- Gaia 的 G/color/RUWE/membership/search-radius selection 尚未完整套進 N-body mock。
- PR #45 必須先 rebase/merge 最新 main，解決文件與結構衝突。

## 協作者已合入最新 main 的工作

### A. N-body 與 LIMEPY

- **PeTar 環境已完成**：MSYS2/MinGW 可建置 PeTar+mcluster，不需 WSL；相關檔案在
  `nbody_setup/`。
- **N-body pilot 已完成**：`α(r)` 的方向與觀測一致；目前仍是 pilot，不是完整的
  M45 125 Myr ensemble。
- **LIMEPY 多質量第一次擬合已完成**：相關結果在 `results/limepy_multimass.npz` 與
  `scripts/diagnostics/limepy_multimass.py`。
- **統計與單位 review 修正**：King/Woolley reduced chi-square 標示、Sigmaj 單位、
  分箱邊界重複計數與中心密度雙重扣減均已有修正。

### B. 觀測品質與系統誤差

- `assign_masses()` 已加入顏色一致性檢查，量化白矮星混入影響。
- 新增白矮星與非主序污染檢查；A6 的原先分析錯誤已更正。
- 新增 Gaia radial-velocity 資料與處理腳本。
- `LIMITATIONS.md` 與 `WORK_BOARD.md` 已建立雙向工作追蹤協議，尚未解決的問題有
  明確分類與認領狀態。

### C. 運算與重現性

- Kaggle 多帳號佇列已排入四個優先重跑。
- 加入開機／登入後重啟本機佇列，避免長跑因重開機中斷。
- 目錄重新整理：scripts 依資料準備、診斷、drivers、plotting、multicluster 分類；
  舊 log 已歸檔。
- CodeRabbit review 的多項真實問題與可靠性問題已回應。

### D. 論文與文件

- `PAPER_OUTLINE.md` 已同步 A6/B4/C3 新發現，並加入維護規則。
- `教學_PDMF轉IMF.md` 補充物理問題說明。
- README、CONTRIBUTING、NEXT_PROMPT、WORK_BOARD 與 RESULTS_LOG 持續同步。

## 真正的共同成果與互補性

兩邊不是重複做同一件事，而是剛好形成完整鏈條：

```text
協作者：觀測資料品質 + 可重現 PeTar 環境 + pilot α(r)
                         ↓
Codex：正式 grid + 快照 accounting + PDMF→IMF 定義橋接 + 不確定度彙整
                         ↓
共同下一步：在正式 PeTar 125 Myr run 上，套用與 Gaia 一致的 selection，
              用 alpha(r)／binary radial profile 選模型，再彙整 seeds。
```

## 建議的整合與執行順序

1. 將 PR #45 rebase 到最新 `main`，優先人工處理：`WORK_BOARD.md`、
   `LIMITATIONS.md`、`PAPER_OUTLINE.md`、`results/RESULTS_LOG.md` 與移動過的
   scripts 路徑。
2. 保留 main 的 LIMEPY unit/statistics 修正，再重新執行或移植 Codex 的 coverage
   bootstrap；不要直接比較兩個不同實作的 alpha 數字。
3. 直接使用 `main/nbody_setup/` 的 PeTar 環境執行 Codex 的 priority-1 三個 seeds。
4. 先跑 1 Myr checkpoint，確認能量、`N_real/N_all`、binary/multiple catalogs、
   `reader_accounting`；通過後才續跑 125 Myr。
5. 初態與末態均執行 `petar.data.process`，再用 system catalog 和 definition bridge。
6. 對 forward result 使用 primary correction；對傳統法使用 photometric beta
   系列；將差異列為 binary-definition systematic。
7. 在所有 mock catalog 套用 main 已更新的 mass/color、污染與 selection 規則，再
   跟觀測 alpha(r) 比較。
8. 三個中央 seeds 先用 ensemble 彙整；之後再跑其他七個 sensitivity runs。

## 合併時不得遺失的關鍵規則

- 不可把 raw PeTar artificial particles 當成實體星。
- 不可把 raw `status` 當完整 primordial binary catalog。
- 不可把 component-star correction 直接加到 unresolved-system forward alpha。
- 不可把 LIMEPY 的 `+0.004` 或 synthetic 的 `+0.283` 寫成 M45 最終結論。
- 不可把 1,215 systems 當成 1,215 component stars 直接給 mcluster。
- 正式 run 必須保存 snapshots、status、命令、版本 commit、projection spread 與
  system-catalog metadata。

## 主要檔案

### Codex／PR #45

- `CLAUDE_HANDOFF_PDMF_IMF_2026-08-13.md`
- `PETAR_M45_EXPERIMENT.md`
- `PDMF_IMF_SMOKING_TEST_2026-08-13.md`
- `petar_m45_grid.py`、`petar_pdmf_analysis.py`、`petar_pdmf_ensemble.py`
- `petar_system_catalog.py`、`pdmf_system_definition_bridge.py`

### 最新 main／協作者

- `nbody_setup/README.md`
- `scripts/diagnostics/limepy_multimass.py`
- `results/limepy_multimass.npz`
- `check_white_dwarf_contamination.py`
- `check_giant_subgiant_contamination.py`
- `PAPER_OUTLINE.md`、`LIMITATIONS.md`、`WORK_BOARD.md`

