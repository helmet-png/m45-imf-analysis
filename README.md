# M45（昴宿星團）初始質量函數分析

用 Gaia DR3 資料量出昴宿星團（M45）的**質量函數斜率 α**，也就是「重的星
比輕的星少多少」。整條流程的設計目標是：同一套規則能套到其他星團，
誤差用同一把尺量。

這份 README 是給第一次打開專案的人看的教學，包含五個部分：

1. 專案在做什麼、目前的結果
2. 資料夾地圖：每個資料夾、每個根目錄檔案是做什麼的
3. 設定檔一覽：哪些檔案控制了程式的行為
4. **教學：一個星團從頭跑到尾**，每一步用哪支程式、讀什麼、寫什麼
5. 算力派工、結果存放、文件導覽

逐一解釋 `config.toml` 每個參數的進階說明，在
[docs/reference/CONFIG_REFERENCE.md](docs/reference/CONFIG_REFERENCE.md)。

---

## 1. 專案在做什麼

**要回答的問題**：星團裡不同質量的星各有幾顆？寫成數學是
dN/dm ∝ m^(−α)，α 就是要量的數字。Salpeter（1955）量到 2.35，是今天
仍在用的標準對照值。

**難在哪裡**：望遠鏡分不開靠得很近的兩顆星（未解析雙星）。兩顆星的光
加在一起，看起來像一顆「比較重的星」，傳統做法因此會把 α 量偏。

**本專案的做法（前向模型）**：不去猜哪一顆是雙星，而是在電腦裡生成
一個假星團。生成時把雙星、測光誤差、望遠鏡看不到暗星的效應全部模擬
進去，再調整參數，直到假星團的色光圖最像真的觀測。雙星比例 f_bin
因此變成待解的參數，而不是需要事先剔除的雜訊。

**目前的頭條結果**（工作代號 `p2_final2_v3`，細節與可信度見
[LIMITATIONS.md](LIMITATIONS.md)）：

| 量 | 數值 | 說明 |
|---|---|---|
| 成員星 | 1,297 顆（測光品質篩選後 1,078 顆） | pyUPMASK，成員機率 ≥ 0.7 |
| α（0.5–2.5 M☉，主星質量分布） | **2.382** | 10 次重複的平均 |
| α 的重現性散布 | ±0.068 | 換 10 組模型端亂數，**不是**統計誤差 |
| α 的統計誤差 | ±0.144 | 注入回收測試量出（LIMITATIONS.md A8） |
| 年齡 | log age = 8.026（約 106 Myr） | 受等時線網格解析度限制 |
| 雙星比例 f_bin（q > 0.1） | 0.568 ± 0.023 | 跟文獻比較前要先對齊 q 下限（D24） |

**這個 α 是現時質量函數（PDMF），還不是初始質量函數（IMF）**：樣本只
取半徑 5° 內的星，而星團一億年來的動力學演化會讓重星沉到中心、輕星被
甩到外面。把 PDMF 換算回 IMF 是目前的主線工作（第 4 節第 11 步）。

---

## 2. 資料夾地圖

```
m45-imf-analysis/
├─ README.md            本檔：教學入口
├─ LIMITATIONS.md       所有已知限制的唯一權威清單（A–D 分級）
├─ CONTRIBUTING.md      多人／多 AI 協作規則
├─ CLAUDE.md, AGENTS.md 給 AI 協作者的專案規則
├─ config.toml          第 1–5 步與聯合前向模型的所有可調參數
├─ cloud_queue.txt      雲端派工清單（派工器固定從這個位置同步，不能搬）
│
├─ pipeline/            核心模組（被所有主程式 import）
├─ scripts/
│   ├─ core/            科學主程式：頭條擬合、注入回收、敏感度測試
│   ├─ data_prep/       抓 Gaia 資料、前處理、建選擇函數、建等時線網格
│   ├─ drivers/         串接第 1–3 步、跑 pyUPMASK
│   ├─ diagnostics/     各條限制的查證腳本（每支對應 LIMITATIONS 的某一條）
│   ├─ multicluster/    把同一套方法套到其他星團
│   ├─ nbody_petar/     N-body 模擬（PDMF→IMF）；grids/ 放模擬參數網格
│   ├─ plotting/        繪圖
│   └─ tools/           共用工具：開跑前檢查、續傳、CI 檢查、結果合併
├─ data/                輸入資料（成員表、誤差模型、選擇函數）
├─ results/             所有計算結果；RESULTS_LOG.md 是結果日誌
├─ docs/
│   ├─ paper/           論文大綱、多星團驗證、N-body 預先註冊、已解決的限制
│   ├─ project/         待辦看板、交接、佇列警示、規則沿革（協作管理用）
│   ├─ reference/       方法說明、參數詳解、雲端 worker 設定
│   ├─ teaching/        教學文件（高中程度讀者）
│   ├─ planning/        帶日期的評估與計畫（歷史紀錄）
│   └─ reports/         報告、研究日誌
├─ ops/                 算力派工：雲端／Kaggle／SSH 派工器、本機佇列
├─ setup/               環境安裝：PARSEC 憑證、pyUPMASK、ARM64、N-body 編譯
├─ status_dashboard/    本機進度主控板（網頁介面）
└─ _archive/            已結束階段的舊腳本（不再維護）
```

**不進版控、但跑程式需要的本機資料夾**（見 `.gitignore`）：

| 資料夾 | 內容 | 怎麼產生 |
|---|---|---|
| `isochrones/` | 等時線網格（數百 MB） | 第 4 節第 0 步 |
| `pyUPMASK/` | 成員判定外部程式 | `bash setup/setup_pyupmask.sh` |
| `prepared/` | pyUPMASK 的輸入檔 | 第 2 步 |
| `logs/` | 每個工作的執行紀錄、佇列完成紀錄 | 程式自動寫入 |
| `certs/` | PARSEC 網站的憑證鏈 | `setup/setup_ca.ps1` |
| `kaggle_work/`、`kaggle_results/`、`cloud_results/` | 派工的暫存與回傳結果 | 派工器自動寫入 |

---

## 3. 設定檔一覽

程式的行為由下面這些檔案控制。改動之前先知道它影響誰。

| 檔案 | 控制什麼 | 誰會讀它 | 注意事項 |
|---|---|---|---|
| [`config.toml`](config.toml) | 星團座標、成員判定、測光篩選、等時線網格、前向模型的先驗範圍 | `pipeline/config.py` → 幾乎所有主程式 | 各參數的意義與預設值理由見 [CONFIG_REFERENCE](docs/reference/CONFIG_REFERENCE.md) |
| [`cloud_queue.txt`](cloud_queue.txt) | 要派到雲端的工作清單 | `ops/cloud_queue.py`（每 60 秒從 `origin/main` 同步一次） | 改動一律走 PR；**不能搬離根目錄**，派工器寫死這個位置 |
| [`ops/queue.txt`](ops/queue.txt) | 本機序列佇列 | `ops/run_queue.py` | 2026-08-23 起本機不跑計算，保留作紀錄 |
| [`ops/kaggle_queue.txt`](ops/kaggle_queue.txt) | 舊版 Kaggle 專用佇列 | `ops/kaggle_queue.py` | 已由 `cloud_queue.txt` 取代 |
| `kaggle_accounts.json`、`ssh_workers.json`（根目錄） | Kaggle 帳號 token、SSH worker 連線資訊 | `ops/` 底下的派工器 | **憑證，不進版控**；格式照 `ops/*.json.example` |
| [`scripts/nbody_petar/grids/petar_m45_grid.csv`](scripts/nbody_petar/grids/petar_m45_grid.csv) | N-body 正式網格：每一列是一次模擬的初始條件 | `petar_m45_grid.py`、`run_nbody_case.py` | 讀取時自動驗證欄位一致性；改完跑 `python scripts/nbody_petar/petar_m45_grid.py --run-id <id>` 確認 |
| [`scripts/nbody_petar/grids/petar_m45_training_grid.csv`](scripts/nbody_petar/grids/petar_m45_training_grid.csv) | N-body 方法 B（模擬器）的 430 組訓練網格 | `generate_training_grid.py` 產生，`run_training_queue.py` 等讀取 | 由程式產生，不手改 |
| `pyUPMASK/params.ini` | pyUPMASK 分群參數 | pyUPMASK 本身 | `run_variant.py` 會依 `config.toml` 改寫，不手改 |
| [`setup/pyupmask_local.patch`](setup/pyupmask_local.patch) | 對 pyUPMASK 原始碼的三處修改（含 Python 3.12+ 相容） | `setup/setup_pyupmask.sh` | 換 pyUPMASK 版本時要重新確認 |
| [`status_dashboard/categorization.json`](status_dashboard/categorization.json) | 主控板「依步驟看」頁的分類：哪支腳本屬於哪一步 | 主控板、CI 路徑檢查 | 搬腳本時要同步改，CI 會擋 |
| [`.coderabbit.yaml`](.coderabbit.yaml) | 自動程式審查的範圍與各檔案的審查重點 | CodeRabbit | 標題帶 `[免審]` 的 PR 會被跳過 |
| `.github/workflows/` | CI：結果日誌只能新增不能改、主控板路徑存在 | GitHub Actions | |

---

## 4. 教學：一個星團從頭跑到尾

以 M45 為例。整條流程分成「準備觀測資料」「擬合」「量誤差」「PDMF→IMF」
四段：

```
Gaia DR3 ──抓資料──> 原始星表 ──前處理──> pyUPMASK 輸入
                                            │
                                     成員判定（pyUPMASK）
                                            │
                    成員表 ──測光篩選──> cmd_members.csv ＋ errmodel.npz
                                            │
                               選擇函數 ──> selection.npz
                                            │
       等時線網格 ───────────────> 聯合前向模型擬合（fit_real.py）──> α、年齡、消光、f_bin
                                            │
                     注入回收（injection_recovery.py）──> 統計誤差與偏差
                     傳統法對照（traditional_accounting.py）
                     敏感度測試（profile_*.py、inject_*.py、diagnostics/）
                                            │
                     PDMF→IMF：分半徑擬合、LIMEPY、N-body 模擬
                                            │
                     results/RESULTS_LOG.md、LIMITATIONS.md、docs/paper/PAPER_OUTLINE.md
```

所有指令都在 **repo 根目錄**執行。

### 第 0 步：環境建置

1. **Python 套件**：numpy、scipy、scikit-learn、astropy、matplotlib、emcee、
   certifi、astroquery。ARM64 Windows 機器的安裝方式見
   `setup/setup_arm64.bat`。
2. **PARSEC 憑證**（只做一次）：PARSEC 等時線網站沒有送出中繼憑證，Python
   會連線失敗。這支腳本補上完整憑證鏈，不是關掉驗證：
   ```bash
   powershell -ExecutionPolicy Bypass -File setup/setup_ca.ps1
   ```
3. **pyUPMASK**（成員判定程式，外部專案）：
   ```bash
   bash setup/setup_pyupmask.sh
   ```
4. **gaia-export 姊妹專案**：`fetch_gaia.py` 與 `prep.py` 借用它的 Gaia
   查詢程式碼，路徑由環境變數 `GAIA_EXPORT_PATH` 指定。
5. **等時線網格**：恆星演化模型的查表，把「質量、年齡、金屬量」換算成
   各波段亮度。頭條擬合用的網格這樣產生（存進 `isochrones/`）：
   ```bash
   python -c "from pipeline import isochrones; isochrones.download_grid(7.7, 8.3, 0.05, -0.6, 0.6, 0.05)"
   ```
   MIST、BHAC15、PARSEC DR2 網格（系統誤差比對用）用
   `scripts/data_prep/build_mist_grid.py`、`build_bhac_grid.py`、
   `build_dr2_grid.py` 產生。

### 第 1 步：從 Gaia 抓星團天區的資料

```bash
python scripts/data_prep/fetch_gaia.py --ra 56.60083 --dec 24.11389 --radius 5 --gmax 18 --plxmin 4
```

- **做什麼**：查詢 M45 中心 5° 內、G < 18、視差 > 4 mas 的所有星。
- **讀**：`config.toml` 的 `[target]`、`[step1_membership]` 決定預設值。
  要重現既有樣本，一定要手動給 `--ra/--dec`。
- **寫**：`data/m45_r5_g18_plx4.csv`，約 7,000 顆星。

### 第 2 步：前處理成 pyUPMASK 的輸入格式

```bash
python scripts/data_prep/prep.py data/m45_r5_g18_plx4.csv --target M45 --name m45_raw
```

- **做什麼**：改欄位名、丟掉缺值，再把 RA/Dec 投影成以星團中心為原點
  的平面座標。不投影的話，天區會被橫向拉伸。
- **寫**：`prepared/m45_raw.dat`。

### 第 3 步：成員判定（pyUPMASK）

```bash
python scripts/drivers/run_variant.py --name baseline --input m45_raw.dat
```

- **做什麼**：只用自行與視差（**不看亮度與顏色**），找出在天空與運動
  空間裡比背景更集中的星。重複 25 輪取平均，得到每顆星的成員機率。
  不看顏色是關鍵：後面要用色光圖擬合，成員判定若先用了顏色，等於先
  偷看答案。
- **讀**：`config.toml` 的 `[step1_membership]`（輪數、PCA、亂數種子）。
- **寫**：`results/baseline.dat`（每顆星一列，含成員機率）、`logs/baseline.log`。
- **驗證**：跟 Hunt & Reffert（2023）的獨立成員目錄比對，見
  `docs/reference/COMPARISON.md`。比對表 `data/comparison.csv` 由
  `scripts/diagnostics/check_c20_disagree_set.py` 產生。

### 第 4 步：測光品質篩選與測光誤差模型

```bash
python scripts/drivers/run_pipeline.py --steps 1 2
```

- **做什麼**：
  - 第 1 部分：取成員機率 ≥ 0.7 的星，接回完整測光欄位。
  - 第 2 部分：剔除測光不可靠的星（BP/RP 被星雲汙染、訊噪比太低、亮端
    飽和），並量出「每個星等的測光誤差有多大」。前向模型要用這個誤差
    模型，才能生成跟觀測同等品質的假星。
- **讀**：`config.toml` 的 `[step2_cmd]`。
- **寫**：`data/cmd_members.csv`（1,078 顆星，所有擬合的共同輸入）、
  `data/errmodel.npz`。
- **舊流程說明**：`run_pipeline.py` 的第 3–5 部分是早期的循序擬合，已由
  下面的聯合前向模型取代，結果不再引用。

### 第 5 步：建立選擇函數

```bash
python scripts/data_prep/build_selection.py
```

- **做什麼**：第 4 步的篩選砍得不平均，暗的紅星被砍得比暗的藍星多。
  這支程式把「給定星等與顏色，這顆星會不會被留下」做成模型。前向模型
  生成假星時用同一把刀砍，假星團才能跟觀測比。
- **讀**：`data/m45_r5_g18_plx4.csv`、`data/cmd_members.csv`、`data/comparison.csv`。
- **寫**：`data/selection.npz`。
- **驗收**：建立之前就訂好三項標準，程式會自動檢查（見該檔開頭）。

### 第 6 步：聯合前向模型擬合（頭條數字）

```bash
python scripts/core/fit_real.py --procs 4 --n-syn 40000 --repeats 1 --configs C \
    --refines 3,3,3 --tag _p2final_v3_rep0 --repeat-offset 0
```

- **做什麼**：同時擬合 7 個參數：年齡、消光 A_V、雙星比例 f_bin、IMF
  斜率 α、金屬量 [M/H]、雙星質量比分布 q_gamma、差異消光 dav。每試一組
  參數，就生成 40,000 顆假星，算假星團與真星團色光圖的相似度。作法是
  先在粗網格上找最好的點，再在附近用更細的格距重掃三輪。
- **讀**：`data/cmd_members.csv`、`data/errmodel.npz`、`data/selection.npz`、
  `isochrones/` 的網格、`config.toml` 的 `[joint_fit]`（參數範圍）。
- **寫**：`results/fit_real_<tag>.npz`。
- **模型設定**：`--configs` 有 A／B／C／D 四種，頭條用 C（含選擇函數與
  差異消光）。四種的差別見 `fit_real.py` 開頭說明。
- **頭條的實際跑法**：`--repeat-offset` 0 到 9 各跑一次，分散到不同機器
  （見第 5 節派工）。跑完用下面這支把 10 份結果串起來，算 α 的平均與散布：
  ```bash
  python scripts/tools/concat_p2final_v3.py
  ```
- **開跑前檢查**：加 `--preflight` 只做檢查不擬合，確認網格範圍、輸入檔、
  續傳設定都正確，見 `docs/reference/PREFLIGHT.md`。工作中途被中斷時，
  重跑同一個指令會從上次存檔處接續。

### 第 7 步：量誤差（注入回收）

```bash
python scripts/core/injection_recovery.py --scenarios S3F --trials 9
```

- **做什麼**：用模型生成一批「已知答案」的假觀測，顆數與真資料一樣
  （1,078），再丟進整套擬合流程，看能不能找回答案。找回來的散布就是
  統計誤差（0.144），系統性偏離就是方法偏差。
- **為什麼不用擬合本身給的誤差**：色光圖的概似函數把每一格當成獨立，
  會過度自信。實測 MCMC 給的誤差低估好幾倍，而且從未收斂（LIMITATIONS.md C11）。
- **寫**：`results/injection_recovery_<tag>.npz`。
- **注意**：注入回收用的是同一套模型，所以**看不到模型本身的錯**，例如
  等時線的系統誤差。這類誤差要靠第 9 步的敏感度測試。

### 第 8 步：傳統法對照

```bash
python scripts/diagnostics/traditional_accounting.py
```

- **做什麼**：用文獻最常見的「查等時線把每顆星換成質量，再擬合冪律」
  做法，配五種雙星處理方式（全當單星、色光圖偏移剔除、RUWE 剔除、
  Gaia 雙星目錄剔除、文獻公式修正）。用同一批星、同一把尺量誤差，
  跟前向模型放在同一張表比較。
- **寫**：`results/traditional_accounting*.npz`。

### 第 9 步：敏感度與系統誤差測試

每支程式回答「某個假設如果錯了，α 會移動多少」：

| 程式 | 測試的假設 |
|---|---|
| `scripts/core/profile_lowmass.py` | 低質量段冪次（目前固定），最大的單一系統誤差來源 |
| `scripts/core/profile_outlierfrac.py` | 均勻背景比例（模型沒描述到的星佔多少） |
| `scripts/core/inject_lowmass.py` | 低質量段冪次放自由時，找不找得回真值 |
| `scripts/core/inject_massdep_fbin.py` | 雙星比例若隨質量變化，α 會被推歪多少 |
| `scripts/core/measure_overconfidence.py` | 概似函數過度自信的程度 |
| `scripts/diagnostics/*.py` | 每支對應 LIMITATIONS.md 的一條限制，檔頭寫明是哪一條 |

### 第 10 步：記錄結果

每個新結果都要記：

1. **`results/RESULTS_LOG.md`**：一行一筆，**只能新增、不能修改舊行**，
   CI 會檢查。
2. **`LIMITATIONS.md`**：結果若改變了某條限制的狀態，就更新那一條。
   格式規則見 `CONTRIBUTING.md` 第五、六節。
3. **`docs/paper/PAPER_OUTLINE.md`**：結果若會進論文，同步更新大綱。

### 第 11 步：PDMF → IMF（目前主線）

把「現在看到的質量函數」換算回「出生時的質量函數」。完整規劃見
[docs/planning/PDMF_TO_IMF_PLAN.md](docs/planning/PDMF_TO_IMF_PLAN.md)，
分成三條獨立的路線，彼此交叉驗證：

**(1) 分半徑擬合**：只用某個半徑以內的星重跑第 6 步，看 α 怎麼隨半徑變。
```bash
python scripts/core/fit_real.py --radius-range 0,1 --configs C --repeats 1 --repeat-offset 0 --refines 3,3 --tag _radial_r1_final
```
每組半徑跑 5 次重複（`--repeat-offset` 0–4，分散到不同 worker），再用
`scripts/tools/concat_radial_final.py` 合併。目前結果：核心
（0–1°）α = 2.06，全樣本 2.38，核心偏平，與重星沉到中心的預期一致。

**(2) LIMEPY 平衡模型**：用多質量動力平衡模型預測「只看 5° 以內」會讓
α 偏多少。程式在 `scripts/diagnostics/limepy_*.py`、
`scripts/nbody_petar/pdmf_limepy_*.py`，需要獨立環境 `.venv_limepy`
（scipy 版本衝突）。

**(3) N-body 模擬**：在電腦裡從 M45 出生時的狀態開始，用 PeTar 逐步算
重力演化一億年，看現在的 PDMF 跟出生時的 IMF 差多少。

- 環境：在 Linux worker 上跑 `bash setup/nbody/setup_linux_nbody.sh`，
  編譯 PeTar 與 mcluster（外部專案，版本釘選見 `setup/nbody/README.md`）。
- 方法 A，用正式網格直接量修正量：
  1. `scripts/nbody_petar/petar_m45_grid.py`：驗證網格、產生可重現的指令。
  2. `scripts/nbody_petar/run_nbody_case.py --run-id <id>`：跑一列網格。
     流程是 mcluster 產生初始條件，PeTar 演化，最後存快照。
  3. `petar_system_catalog.py`、`petar_pdmf_analysis.py`：從快照量 α 的變化。
  4. `petar_pdmf_ensemble.py`：彙整多次模擬，給出修正量與不確定度。
- 方法 B，用 GP 模擬器反推初始條件：
  1. `generate_training_grid.py` 產生 430 組訓練網格。
  2. `queue_training_batch.py` 排進雲端佇列。
  3. `build_training_stats.py`、`summarize_training_runs.py` 整理每次模擬的觀測統計量。
  4. `emulator_fit.py`、`emulator_holdout_check.py` 訓練模擬器並驗證。
  5. `emulator_infer.py` 用 M45 的觀測反推初始條件。
- 規則：模擬參數要在看結果之前登記，見
  [docs/paper/NBODY_PREREGISTRATION.md](docs/paper/NBODY_PREREGISTRATION.md)。

### 換一個星團

`config.toml` 的 `[target]` 指定星團。但**目前還做不到「改名字就能跑」**：
每個星團的測光誤差模型與選擇函數都要用自己的資料重新校準。完整前向模型
在 NGC 3532 與 Praesepe 上都出現撞到參數邊界的解（LIMITATIONS.md D16、
D17）。多星團流程分兩級：

| 層級 | 程式 | 做什麼 |
|---|---|---|
| Tier 1 | `scripts/multicluster/cluster_imf_tier1.py` | 用 Hunt & Reffert 2023 現成的成員表與年齡，只跑傳統法 |
| Tier 2 | `scripts/multicluster/prepare_cluster_tier2.py --hr23-name <名稱>` | 回 Gaia 補抓測光，建這個星團自己的誤差模型與選擇函數 |
| Tier 2 | `scripts/multicluster/cluster_forward_validation.py --hr23-name <名稱> --grid <網格>` | 用 M45 的前向模型擬合這個星團，並做注入回收 |

各星團目前通過與未通過的項目見
[docs/paper/MULTICLUSTER_VALIDATION.md](docs/paper/MULTICLUSTER_VALIDATION.md)。

---

## 5. 算力怎麼派

**2026-08-23 起本機不跑計算**，所有工作排進雲端佇列：

1. 開分支，在 `cloud_queue.txt` 末端加一行：
   ```
   標籤|腳本路徑|參數|額外檔案（逗號分隔）|minimal|worker 名稱|最長小時數
   p2_rep0|scripts/core/fit_real.py|--procs 4 --n-syn 40000 --repeats 1 --configs C --tag _rep0|scripts/core/measure_overconfidence.py,scripts/core/injection_recovery.py,scripts/tools/checkpoint.py,scripts/tools/preflight.py|false||60
   ```
   - **標籤**：唯一名稱。完成紀錄以標籤為準，同一個標籤不會重跑。
   - **額外檔案**：Kaggle 會把腳本拍平到單一資料夾，所以腳本 import 的
     其他檔案要列在這裡。SSH worker 有完整 repo，不需要列。
   - **minimal**：`true` 表示不打包 `pipeline/`、資料與等時線網格。
   - **worker**：留空表示給任何有空的 worker。
2. 開 PR、合併。派工器下一輪就會撿到這個工作。
3. 結果回傳到派工機器的 `cloud_results/` 或 `kaggle_results/`，經人工確認
   後 commit 進 `results/`，並記進 `RESULTS_LOG.md`。

派工器本體在 `ops/`：`cloud_queue.py`（主迴圈）、`ssh_sync.py`
（SSH worker）、`kaggle_sync.py`（Kaggle）、`gcp_vm_lifecycle.py`（GCP 自動
開關機）。設定方式見 [docs/reference/CLOUD_WORKERS.md](docs/reference/CLOUD_WORKERS.md)。
進度可以在本機主控板看：雙擊 `status_dashboard/launch_dashboard.vbs`。

---

## 6. 結果放在哪裡

所有結果都在 `results/`，檔名規則是「產生它的程式＋標籤」：

| 檔名樣式 | 來源 |
|---|---|
| `fit_real_<tag>.npz` | 第 6 步聯合前向模型（`fit_real_p2final_v3*.npz` 是頭條） |
| `injection_recovery_<tag>.npz` | 第 7 步注入回收 |
| `traditional_accounting*.npz` | 第 8 步傳統法 |
| `profile_*`、`inject_*` | 第 9 步敏感度測試 |
| `m45_*_pdmf*.json`、`nbody_*` | 第 11 步 N-body |
| `nbody_training_runs/` | N-body 方法 B 的 430 組訓練資料摘要 |
| `cluster_*` | 多星團 |

每個結果代表什麼、用什麼參數跑的，查 [results/RESULTS_LOG.md](results/RESULTS_LOG.md)。

---

## 7. 文件導覽

| 想知道 | 看這裡 |
|---|---|
| 結果有哪些已知問題、可不可以引用 | [LIMITATIONS.md](LIMITATIONS.md) |
| 論文會寫什麼、新穎性在哪 | [docs/paper/PAPER_OUTLINE.md](docs/paper/PAPER_OUTLINE.md) |
| 已經解決的問題 | [docs/paper/RESOLVED.md](docs/paper/RESOLVED.md) |
| 現在誰在做什麼、還有哪些待辦 | [docs/project/WORK_BOARD.md](docs/project/WORK_BOARD.md) |
| 佇列的開跑前檢查或驗收沒過 | [docs/project/QUEUE_ALERTS.md](docs/project/QUEUE_ALERTS.md) |
| 參數為什麼這樣設 | [docs/reference/CONFIG_REFERENCE.md](docs/reference/CONFIG_REFERENCE.md) |
| 成員判定方法、與前人做法對照 | [docs/reference/METHODS.md](docs/reference/METHODS.md)、[docs/reference/COMPARISON.md](docs/reference/COMPARISON.md) |
| 試過但被推翻的做法 | [docs/reference/REFUTED.md](docs/reference/REFUTED.md) |
| 用高中程度從頭理解方法 | [docs/teaching/](docs/teaching/) |
| 協作規則（開分支、PR、commit） | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## 8. 2026-11 目錄重整對照表

2026-11 把根目錄的檔案依用途分進資料夾。舊文件（`docs/planning/`、
`docs/reports/`、`results/RESULTS_LOG.md` 等歷史紀錄）提到的舊路徑沒有
改寫，用這張表對照：

| 舊位置 | 新位置 |
|---|---|
| `fit_real.py`、`injection_recovery.py`、`inject_lowmass.py`、`inject_massdep_fbin.py`、`measure_overconfidence.py`、`profile_lowmass.py`、`profile_outlierfrac.py` | `scripts/core/` |
| `cloud_queue.py`、`run_queue.py`、`kaggle_*.py`、`ssh_*.py`、`gcp_vm_lifecycle.py`、`iap_tunnel_manager.py`、`queue.txt`、`kaggle_queue.txt`、`*.json.example`、`restart_queue_on_boot.ps1`、`run_hidden.vbs` | `ops/` |
| `PAPER_OUTLINE.md`、`MULTICLUSTER_VALIDATION.md`、`NBODY_PREREGISTRATION.md`、`RESOLVED.md` | `docs/paper/` |
| `WORK_BOARD.md`、`WORK_BOARD_DONE.md`、`STATE.md`、`NEXT_PROMPT.md`、`QUEUE_ALERTS.md`、`CHANGELOG.md` | `docs/project/` |
| `petar_m45_grid.csv`、`petar_m45_training_grid.csv` | `scripts/nbody_petar/grids/` |
| `nbody_setup/` | `setup/nbody/`（`analyze_alpha_r.py` 移到 `scripts/nbody_petar/`） |
| 舊 README 的參數說明 | `docs/reference/CONFIG_REFERENCE.md` |

搬遷由 `scripts/tools/restructure_repo.py` 執行。`cloud_queue.txt`、
`config.toml` 和憑證檔（`kaggle_accounts.json`、`ssh_workers.json`）
刻意留在根目錄：派工器與既有機器的設定都寫死這些位置。
