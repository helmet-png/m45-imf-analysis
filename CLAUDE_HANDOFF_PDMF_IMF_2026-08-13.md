# Claude 交接：M45 PDMF → IMF（2026-08-13）

> 請先閱讀本文件，再看 `PETAR_M45_EXPERIMENT.md`、
> `PDMF_IMF_SMOKING_TEST_2026-08-13.md` 與 `WORK_BOARD.md`。
> 本文件中的 synthetic 結果只驗證程式，不是 M45 的物理解答。

## 一句話狀態

LIMEPY 空間外推、REBOUND 動力方向測試、正式 PeTar 參數網格、快照分析、
多 run 彙整、人工粒子防護，以及 component/unresolved-system 定義橋接均已完成；
目前真正缺少的是在協作者已編好的 PeTar 環境跑出 125 Myr 正式快照。

## Git 狀態

- 工作分支：`codex/pdmf-imf-overnight`
- 基底：`main` 的 `4b9de84`
- 本輪 commits：
  - `94d9df4`：LIMEPY 與 REBOUND smoking tests
  - `b1ff999`：正式 PeTar 實驗網格與單 run 分析器
  - `7be9c4c`：PeTar 多 run 不確定度彙整
  - `fce9793`：PeTar raw snapshot 人工粒子防護
  - `d3aa9d2`：component/unresolved-system 定義橋接
- GitHub 尚未 push：本機 GitHub CLI 的舊 token 失效；device OAuth 曾回
  `not_found`。程式與 commits 均安全保留在本地分支。
- 遠端協作者分支 `yutunglan/nbody-env-setup` 已在 Windows x64／MSYS2 編好
  PeTar+BSE、SDAR、FDPS 與 mcluster。不要重新走 WSL 建置。

## 已確認的 M45 資料基準

- `data/cmd_members.csv`：1,078 顆有效成員。
- 0.3–2.5 Msun 擬合範圍：694 顆；membership 加權 689.47 顆。
- 距離：135.48 pc。
- 5.1° 搜尋半徑：12.09 pc。
- 傳統法徑向 MF：`results/step5_mf_radial.csv`。

## LIMEPY 平衡模型結果

- 2,205 個模型全部收斂。
- 最佳模型：`phi0=4, g=1, delta=0.30, rh=4 pc, rt=19.73 pc`。
- GOF：Pearson chi-square=16.36，約 20 dof，p=0.69；deviance p=0.57。
- 5.1° 內各質量段涵蓋率：0.98535、0.98733、0.99004、0.99339。
- PDMF alpha：1.982 → 1.986，所以純平衡空間修正 `delta alpha=+0.004`。
- 5,000 次 bootstrap：中位數 +0.004；95% 區間 0.000–0.014；
  98.64% 的重抽滿足 `|delta alpha|<0.02`。
- 解讀：束縛平衡族群的搜尋半徑漏失很小，但這不包含 tidal tails／
  potential escapers，不能當最終 PDMF→IMF 修正。

主要檔案：

- `pdmf_limepy_smoke.py`
- `pdmf_limepy_bootstrap.py`
- `results/pdmf_limepy_smoke.json`
- `results/pdmf_limepy_bootstrap.json`

## REBOUND 前置驗證結果

- 72 個高精度簡化模型中，52 個通過 `|delta E/E|<1e-3`。
- 通過者中 94.2% 的外圈減內圈 alpha 對比增加；86.5% 的低／高質量
  半徑比增加。
- N=1,024/2,048 共 32 runs，28 個通過能量門檻；通過者分別有 96.4%
  與 92.9% 顯示正確的質量分層方向。
- 解讀：分析量與符號正確；因缺少近距離正則化、恆星演化、原初雙星、
  銀河潮汐與 Gaia selection，REBOUND 數字不可直接校正 M45。

主要檔案：

- `nbody_pdmf_smoke.py`
- `nbody_pdmf_ensemble.py`
- `results/nbody_pdmf_ensemble_largeN.json`

## 正式 PeTar 實驗設計

`petar_m45_grid.csv` 定義 10-run screening grid：中央模型三個 seeds，加上
半質量半徑、初始質量分層、binary fraction 與 profile 敏感度。

重要文獻修正：

- Converse & Stahler (2010) 從氣體已驅散後開始，因此第一輪不能稱為
  embedded gas-expulsion simulation。
- 1,215 是 systems，不是 component stars。
- binary fraction=0.95 時：1,154 binary systems + 61 singles = 2,369 stars。
- 中央 `rh≈3.1 pc`；敏感度值為 2.4、3.8 pc。
- McLuster 的 `S` 與論文 polytrope beta 並非相同物理參數；此網格是
  screening，不是逐字重現論文。

正式規格與指令：`PETAR_M45_EXPERIMENT.md`。

## PeTar 單 run 分析器

`petar_pdmf_analysis.py` 以 component ID 比對初態與末態，將修正拆成：

1. `survival_selection`：末態存活者的 birth masses 相對初始 IMF。
2. `stellar_evolution_after_survival`：相同存活者由 birth mass 變 current mass。
3. `finite_aperture`：套用 12.09 pc 投影孔徑後的額外變化。
4. `total_pdmf_minus_imf`：最終觀測 PDMF alpha − 初始 IMF alpha。
5. `correction_to_add_to_pdmf_for_imf`：上項的負號。

方法包含 shrinking-sphere 中心、32 個均勻視線方向、累積與 annular profiles。

Synthetic sign test（僅程式驗證）：

- birth IMF alpha=2.321
- survival alpha=2.101，delta=-0.220
- 12.09 pc projected alpha=2.038，額外 delta=-0.063
- total PDMF−IMF=-0.283，因此回推修正為 +0.283

## 重要修正：PeTar artificial particles

官方 `ArtificialParticleInformation` 原始碼已核對：

- `status > 0`：artificial particle，包括 CM／取樣粒子，必須移除。
- `status == 0 && mass_bk == 0`：physical single，保留 `mass`。
- `status < 0 && mass_bk > 0`：physical subsystem member，保留並以
  `mass_bk` 還原物理質量。
- `status < 0 && mass_bk < 0`：unused，移除。
- 任何其他組合：fail closed，停止分析。

`petar_pdmf_analysis.py` 已實作並在 JSON 輸出 `reader_accounting`。
正式結果須把該欄與 PeTar status log 的 `N_real`／`N_all` 交叉核對。

## 重要修正：component 與 unresolved-system 不可混用

現有前向模型的 IMF 是從 primary mass `m1` 抽樣，再加入伴星流量。因此它的
動力修正應接 `primary` 定義，不應直接加 component-star correction。

新增：

- `petar_system_catalog.py`：把 `petar.data.process` 的
  single/binary/triple/quadruple catalogs 遞迴展平成標準 system catalog。
- `pdmf_system_definition_bridge.py`：同時計算：
  - component MF
  - primary MF（對應目前 forward model）
  - total-system-mass MF
  - photometric-equivalent MF，使用 `L ∝ M^beta`，beta=2、3、4

注意：raw snapshot 的 `status` 是當下積分器子系統狀態，不是完整的 primordial
binary catalog。物理 system 定義必須使用 `petar.data.process` 輸出的多重星目錄。

合成橋接測試使用 8,000 systems／12,460 components、32 projections；所有
定義皆得到有限結果，階層三合星遞迴分組測試也通過。這些 alpha 數值不能寫成
M45 結論。

## 多 run 彙整

`petar_pdmf_ensemble.py` 會：

- 彙整每種 delta alpha 的 median、q16、q84、sd。
- 另列 priority=1 中央三 seeds 的 scatter。
- 預設拒絕 synthetic 結果。
- 拒絕重複 run ID 與不一致 mass range。

## Claude 接手後的執行順序

1. 切到或 cherry-pick `codex/pdmf-imf-overnight` 的五個 commits。
2. 在 `yutunglan/nbody-env-setup` 已編好的機器執行：

   ```bash
   python petar_m45_grid.py --validate
   python petar_m45_grid.py --priority 1 --render-commands
   ```

3. 先完成中央模型三 seeds 的 1 Myr checkpoint；檢查能量、粒子數、binary
   數與輸出格式，再續跑 125 Myr。
4. 每個 run 用 `petar_pdmf_analysis.py` 做 component-ID 動力分解。
5. 每個初／末快照執行 `petar.data.process`，並用 `petar_system_catalog.py`
   匯出完整 system catalog。
6. 執行 `pdmf_system_definition_bridge.py`；前向模型採 `primary` correction，
   傳統法以 photometric beta=2/3/4 範圍作敏感度。
7. 三個中央 seeds 完成後立刻用 `petar_pdmf_ensemble.py` 彙整，不必等完 10 runs。
8. 通過驗收後再跑另外七個 sensitivity runs。

## 正式結果最低驗收條件

- 初態／末態 component ID 唯一，末態無來源不明新 ID。
- `reader_accounting` 與 `N_real/N_all` 相容。
- `data.status` 無 NaN，無未解釋能量跳變。
- 0.3–2.5 Msun 在 12.09 pc 孔徑內至少 100 個物件。
- 保存 32 projections 的 alpha spread。
- system catalog 確認所有非空的 single/binary/triple/quadruple 檔均已納入。
- 保存初／末快照、status、完整 command/log、PeTar/SDAR/FDPS commits。
- 結果寫入 `results/RESULTS_LOG.md`，不可只留終端截圖。

## 尚未解決

1. 正式 PeTar 125 Myr runs 尚未執行，因此目前沒有可信的 M45 動力修正值。
2. system-definition bridge 尚待正式 processed catalogs 驗證。
3. Gaia G／color／RUWE／membership／搜尋半徑 selection 尚未完整套到 mock catalog。
4. Galactic tide 對照尚未跑。
5. 尚未用觀測 alpha(r) 與 binary radial distribution 排序 S/profile 模型。
6. 最終至少需要 8 seeds 與初始 IMF slope sensitivity。
7. 潮汐尾／potential escapers 仍需更大搜尋半徑觀測資料驗證。

## 不要做的事

- 不要把 synthetic `+0.283` 當成 M45 修正。
- 不要把 LIMEPY `+0.004` 解讀為潮汐尾修正。
- 不要把 REBOUND 的 alpha 變化當正式 M45 結果。
- 不要使用 `mcluster -N 1215 -b 0.95` 直接代表 1,215 systems。
- 不要把 component correction 與已含 unresolved binaries 的 forward alpha 直接相加。
- 不要用 raw PeTar `status` 重建完整物理 binary catalog。
- 不要重建 WSL PeTar；先使用已存在的 MSYS2/MinGW 環境。

## 快速自測

```bash
python -m py_compile petar_pdmf_analysis.py petar_pdmf_ensemble.py \
  petar_m45_grid.py pdmf_system_definition_bridge.py petar_system_catalog.py

python petar_pdmf_analysis.py --self-test \
  --output-prefix results/petar_pdmf_analysis_selftest

python petar_pdmf_ensemble.py results/petar_pdmf_analysis_selftest.json \
  --allow-synthetic --output-prefix results/petar_pdmf_ensemble_selftest

python petar_system_catalog.py --self-test

python pdmf_system_definition_bridge.py --self-test \
  --output results/pdmf_system_definition_bridge_selftest.json
```

## 主要閱讀順序

1. `CLAUDE_HANDOFF_PDMF_IMF_2026-08-13.md`（本文件）
2. `PETAR_M45_EXPERIMENT.md`
3. `PDMF_IMF_SMOKING_TEST_2026-08-13.md`
4. `WORK_BOARD.md`
5. `results/RESULTS_LOG.md`
6. `PDMF_TO_IMF_PLAN.md`

