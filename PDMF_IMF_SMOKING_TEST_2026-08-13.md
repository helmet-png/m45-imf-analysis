# PDMF → IMF smoking test（2026-08-13）

## 結論先行

這次完成兩條互補的前置驗證：

1. **LIMEPY 平衡模型**已能在 Windows x64／新版 SciPy 上完整運作，且能合理擬合 M45 四個質量段的徑向數密度。模型估計現有 5.1° 圓形樣本已涵蓋平衡束縛族群的 98.5%–99.3%，因此只做這項空間外推時，分箱 PDMF 斜率由 1.982 變成 1.986，`Δα=+0.004`。
2. **REBOUND N-body 前置測試**證明「已知 IMF → 動力演化 → 內外圈 PDMF」分析鏈能量到預期的質量分層方向。高精度 72 次集合中，52 次符合 `|ΔE/E|<10^-3`；這 52 次裡，94.2% 的外圈減內圈 α 對比增加，86.5% 的低質量／高質量半徑比增加。

這兩項結果**不代表 M45 的 PDMF 已完成轉成 IMF**。LIMEPY 是平衡模型，不包含潮汐尾與 potential escapers；REBOUND 測試沒有銀河潮汐、恆星演化、原初雙星與 Gaia 選擇函數。正式定量修正仍需要 ARM64 佇列的前向徑向結果、擴大半徑成員樣本，以及 PeTar 正式模擬。

## 使用的資料與對位檢查

- `data/cmd_members.csv`：1,078 顆 M45 成員。
- `results/step5_imf.npz`：1,078 筆逐星傳統法系統質量。
- 有效 CMD 列數、成員列數、質量列數三者皆為 1,078，因此質量與天空座標可逐列對位。
- 現行 IMF 擬合範圍 0.3–2.5 M⊙ 內有 694 顆；以 `probs_final` 加權後為 689.47 顆。
- 使用與 `run_pipeline.py` step 5 相同的中心定義：RA 中位數 56.5914°、Dec 中位數 24.1196°。
- 視差零點修正後距離為 135.48 pc；5.1° 對應投影半徑 12.09 pc。

## LIMEPY 方法與結果

### 相容性修正

`astro-limepy==1.3.0` 在 SciPy 1.18.0 有兩個舊介面問題：

- `nsteps=1e6` 是浮點數，新 SciPy 要求整數；
- 新 SciPy 的 DOPRI callback 會多傳一個參數。

`pdmf_limepy_smoke.py` 在執行時安裝局部相容層，不修改使用者的全域 Python 或 SciPy。單質量與多質量投影模型皆實際積分完成、`converged=True`。

### 觀測剖面

質量分成四段：

- 0.30–0.50 M⊙：代表質量 0.389 M⊙；
- 0.50–0.80 M⊙：代表質量 0.602 M⊙；
- 0.80–1.20 M⊙：代表質量 0.958 M⊙；
- 1.20–2.50 M⊙：代表質量 1.532 M⊙。

半徑分成 0–0.5、0.5–1、1–1.5、1.5–2、2–3、3–4、4–5.1°。每格保存原始數量、membership 加權數量、面密度與誤差。

### 網格

三輪迭代、每輪 735 個模型，共 2,205 個模型，全部收斂。搜尋範圍：

- `phi0 = 3…9`
- `g = 0, 1, 2`
- `delta = 0, 0.15, 0.30, 0.45, 0.60`
- `rh = 2, 3, 4, 5, 6, 8, 10 pc`

最佳解：

| 參數 | 值 |
|---|---:|
| 中央無因次位勢 `phi0` | 4 |
| 截斷型態 `g` | 1（King） |
| 質量平衡指數 `delta` | 0.30 |
| 半質量半徑 `rh` | 4.0 pc |
| 模型截斷半徑 `rt` | 19.73 pc |

最佳值沒有落在本次網格邊界。徑向擬合的 Pearson χ²=16.36、近似自由度 20、p=0.69；deviance=18.28、p=0.57；最大單格標準化殘差 2.04σ。以 smoking test 標準看，沒有明顯整體失配。

### 空間涵蓋修正

模型投影在 5.1° 內的比例，從最低質量到最高質量依序為：

`0.98535, 0.98733, 0.99004, 0.99339`

因此：

- 未修正分箱 PDMF：`α=1.982 ± 0.071`
- 只修正平衡族群空間涵蓋後：`α=1.986 ± 0.071`
- `Δα_spatial=+0.004`

這個小修正只表示**模型中的束縛平衡族群**在 5.1° 外不多；不能排除非平衡潮汐尾富含低質量星。模型最外兩個高質量格也較稀疏，因此不應把 0.004 當成最終系統誤差。

### 逐星 bootstrap

`pdmf_limepy_bootstrap.py` 先建立完整 735 個結構模型庫，再把 694 顆有效質量星逐星重抽 5,000 次；每次都重新選擇最佳結構模型，而非固定單一 King 解。

- `Δα_spatial` 中位數：+0.004
- 68% 區間：+0.001 到 +0.005
- 95% 區間：0.000 到 +0.014
- 91.56% 的重抽結果為正修正
- 98.64% 的結果滿足 `|Δα_spatial|<0.02`

最常被選到的仍是 `phi0=4, g=1, delta=0.3, rh=4 pc`（33.82%），但 bootstrap 也會選到截斷半徑較大的 Wilson 解。即使把這項結構不確定度納入，平衡束縛族群的空間修正仍接近零。近似之處是模型庫建立時固定各質量段總質量；bootstrap 會重抽星與重選結構，但不會為每次重抽重新積分一套多質量模型。

## N-body 前置測試

### REBOUND 與 PeTar 的分工

本輪開始時，這個工作區尚未有 PeTar 可執行檔，因此先用官方原生支援 Windows 的 REBOUND 驗證分析鏈。同步遠端後確認，Yu Tung Lan／Claude 已在另一個工作環境以 MSYS2/MinGW-w64 成功編譯 PeTar（含 BSE）與 mcluster，**不需要 WSL**；其 1,000 星測試能量誤差約 2.5×10^-5，100 星含 25 組雙星的 `mcluster_sse → petar.init → petar` 也已端到端通過，詳見分支 `yutunglan/nbody-env-setup`。

因此 REBOUND 結果定位為 PeTar 前的獨立分析驗證與 N 尺度成本量測，不是正式工具的替代品。正式 M45 模擬應直接接到協作者已完成的 PeTar 環境，避免重複建置。

### 單次收斂測試

- 256 顆，輸入 `α=2.30`，0.3–2.5 M⊙；
- 無原初質量分層的 Plummer 初始條件；
- 跑 10 個初始交越時間；
- leapfrog、softening=0.01 rh、dt=0.001。

結果：

- `|ΔE/E|=4.44×10^-4`，通過 10^-3 門檻；
- 全域樣本的已抽樣 α 在動力演化前後都為 2.157，符合質量不被創造／刪除；
- 內圈 α：2.063 → 1.999；
- 外圈 α：2.254 → 2.327；
- 低／高質量星中位半徑比：1.016 → 1.107。

輸入 α=2.30、實際 256 顆抽樣得到 α=2.157 是有限樣本波動，不是積分器改變 IMF。

### 72 次高精度集合

網格為 `N=128,256,512`、softening=`0.005,0.01,0.02 rh`，每格八個亂數種子，dt=0.0005，共 72 次。

- 全部模擬：α 徑向對比變化中位數 +0.345，93.1% 為正；半徑比變化中位數 +0.118，87.5% 為正。
- 能量通過的 52 次：α 對比變化中位數 +0.334，94.2% 為正；半徑比變化中位數 +0.118，86.5% 為正。
- dt=0.001 集合的 α 對比中位數為 +0.334，dt=0.0005 為 +0.345，主趨勢對時間步具有近似收斂。

近距離遭遇使固定步長 leapfrog 並非每次都通過能量門檻；不能用 REBOUND 這組數字校正 M45。它的價值是確認分析量與方向正確，並證明正式 PeTar 模擬必須使用近距離正則化與逐次能量品質控管。

### 接近觀測樣本量的大 N 集合

另跑 `N=1024,2048`、softening=`0.005,0.01 rh`、每格八個 seed、dt=0.0005，共 32 次。這輪以 REBOUND basic O(N²) 單核心運算約 42 分鐘。

- 32 次中 28 次通過 `|ΔE/E|<10^-3`；
- 能量通過者 96.4% 的 α 徑向對比增加；
- 能量通過者 92.9% 的低／高質量半徑比增加；
- N=1,024 各 softening 的中位 α 對比變化約 +0.15 到 +0.18；
- N=2,048 則約 +0.05 到 +0.11。

固定十個交越時間下，訊號隨 N 增加而變弱，符合 two-body relaxation 約隨 `N/ln N` 變慢的預期。這不是程式失敗，而是正式模擬必須把 M45 的物理交越時間／鬆弛時間換算清楚。42 分鐘只完成 32 個簡化模型也顯示：正式跨參數網格不應再用 basic O(N²) 路線，應轉向 PeTar。

## 文獻對研究設計的直接影響

- Li et al. 的大樣本研究顯示年輕星團的全域 PDMF 可接近 IMF，但也指出嚴格運動學切割可能漏掉高速低質量外圍星、寬鬆切割則會被場星污染；因此「全域」取樣定義比單純年齡門檻重要。
- MiMO catalog 提供 1,232 個星團、163 個 Prime 樣本與後驗資料，可作為多星團候選池及一致的年齡／金屬量參考。
- Praesepe 的文獻年齡約 logAge≈8.9，明顯不同於先前 HR23 參數 logAge=8.539；NGC 3532 文獻年齡也更接近約 400 Myr，而非 238 Myr。先前前向模型把兩團年齡推老，很可能是在揭露輸入年齡問題，不應直接視為方法失敗。
- Praesepe 已知有質量分層與潮汐尾；它適合測「有限搜尋半徑是否把 PDMF 變平」，但必須使用文獻年齡與包含尾部的成員表。

主要資料來源：

- Li et al. 2026, [Evolution of the stellar mass function](https://arxiv.org/html/2606.05762v1)
- [MiMO open-cluster catalog](https://arxiv.org/abs/2510.23374)
- [NGC 3532 unresolved binaries](https://arxiv.org/abs/2008.04684)
- [Praesepe radial binaries and mass segregation](https://academic.oup.com/mnras/article/528/4/6211/7604627)
- [Praesepe tidal tails and N-body model](https://arxiv.org/abs/2509.24584)
- [PeTar official documentation](https://lwang-astro.github.io/PeTar/)
- [AMUSE Windows installation requirements](https://amuse.readthedocs.io/en/main/install/installing.html)
- [REBOUND official repository](https://github.com/hannorein/rebound)

## 分工同步

### 其他協作者已完成／正在跑

- Claude／ARM64：完成 PDMF→IMF 文獻與動力學規劃，加入 `fit_real.py --radius-range`。
- Claude／ARM64：已排 `radial_r1/r2/r3/rall` 四個前向模型徑向診斷；本輪沒有重複執行。
- Yu Tung Lan／x64：驗證完整 M45 pipeline 可跨 x64 重現；6,956 星樣本與主要 α 結果和 repo 基準一致。
- Yu Tung Lan／x64：完成 PDMF 工作優先度覆核。
- Yu Tung Lan／x64：以 MSYS2/MinGW-w64 編譯 PeTar（含 BSE）、FDPS v7.0、SDAR 與 mcluster，完成 1,000 星守恆測試及含雙星端到端測試；分支 `yutunglan/nbody-env-setup`。

### 本輪 Codex 完成

- 解決 LIMEPY 1.3.0 與 SciPy 1.18.0 的兩項相容性問題。
- 建立逐質量段徑向面密度與誤差表。
- 跑完 2,205 個多質量 LIMEPY 模型與三輪空間修正迭代。
- 新增擬合殘差與 goodness-of-fit 檢查。
- 建立 Windows 原生 REBOUND PDMF 前置測試。
- 跑單次能量收斂與兩組 72 次 N-body 集合。
- 保留所有網格、逐次模擬與摘要，供他人重算或審查。

## 尚未解決與優先順序

1. **等待四個前向模型徑向診斷**：判斷傳統法 α(r) 梯度有多少來自雙星比例徑向變化。
2. **擴大 Gaia 搜尋半徑到至少 8°，最好覆蓋已知尾部**：這是驗證 LIMEPY 沒有建模到的 potential escapers／潮汐尾的關鍵觀測。
3. **在已完成的 MSYS2/MinGW PeTar 環境開始正式 M45 模擬**：不用重建 WSL；先合併／讀取 `yutunglan/nbody-env-setup` 的環境紀錄，然後採 N≈1,200–1,500、初始雙星比例約 95%、embedded cluster＋氣體驅離、積分到 125 Myr。
4. **正式 PeTar 網格**：至少跨初始質量、半質量半徑、軌道、雙星比例與亂數種子；每次都要做能量與收斂篩選。
5. **NGC 3532／Praesepe 重跑年齡基準**：用文獻或 MiMO 年齡先驗，不再把 HR23 年齡當固定真值。
6. **把選擇函數放回動力模型**：模擬星要經過與 Gaia 相同的 G、顏色、RUWE、membership 與搜尋半徑切割後再比較 PDMF。

## 重跑方式

```text
python -m venv .venv-pdmf
.venv-pdmf\Scripts\python -m pip install -r requirements-pdmf.txt
.venv-pdmf\Scripts\python pdmf_limepy_smoke.py
.venv-pdmf\Scripts\python pdmf_limepy_bootstrap.py --trials 5000

.venv-pdmf\Scripts\python -m pip install -r requirements-nbody.txt
.venv-pdmf\Scripts\python nbody_pdmf_smoke.py --dt 0.001
.venv-pdmf\Scripts\python nbody_pdmf_ensemble.py --dt 0.0005
```

正式結果檔：

- `results/pdmf_limepy_smoke.json`
- `results/pdmf_limepy_smoke_grid.csv`
- `results/pdmf_limepy_smoke_radial_profile.csv`
- `results/pdmf_limepy_bootstrap.json`
- `results/pdmf_limepy_bootstrap_models.csv`
- `results/pdmf_limepy_bootstrap_trials.csv`
- `results/nbody_pdmf_smoke.json`
- `results/nbody_pdmf_smoke_timeseries.csv`
- `results/nbody_pdmf_ensemble_dt0005.json`
- `results/nbody_pdmf_ensemble_dt0005_runs.csv`
- `results/nbody_pdmf_ensemble_dt0005_summary.csv`
- `results/nbody_pdmf_ensemble_largeN.json`
- `results/nbody_pdmf_ensemble_largeN_runs.csv`
- `results/nbody_pdmf_ensemble_largeN_summary.csv`
