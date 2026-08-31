# M45 PeTar 正式實驗規格（2026-08-13）

## 要回答的問題

目前前向模型給的是有限視野內的 PDMF。PeTar 實驗要估計：

1. 0.3–2.5 Msun 的星在 125 Myr 內因逃逸造成多少斜率變化；
2. 恆星演化造成多少斜率變化；
3. 只觀測 5.1 度（以 135.48 pc 換算為 12.09 pc）又造成多少變化；
4. 上述修正對初始半徑、初始質量分層、聯星比例及亂數種子是否穩健。

輸出採用

```text
delta_alpha = alpha_PDMF - alpha_birth_IMF
alpha_IMF = alpha_PDMF - delta_alpha
```

避免正負號混淆。正式分析由 `petar_pdmf_analysis.py` 逐 ID 比對初始與
125 Myr 快照，自動把「survival selection、恆星演化、有限視野」分開。
其中 survival selection 在尚未讀取 escaper/BSE event catalog 時同時包含逃逸、
移除與合併，不能先全部叫做純逃逸。

## 文獻錨點與一項重要更正

Converse & Stahler (2010) 的最佳初始模型為：1,215±59 個**恆星系統**、
virial radius 4.0±0.9 pc、初始系統聯星比例 0.95±0.08、質量分層參數
beta=0.5±0.3，並演化到 125 Myr。

這篇文獻的模擬是從分子雲氣體**已經被驅散之後**開始，不是從 embedded
cluster 裡開始模擬氣體驅離。因此第一批 PeTar 正式實驗不加入氣體勢；若把
氣體驅離加進來，那是另一個更早期、參數更多的研究問題，不能稱為直接重現
Converse & Stahler。

同一篇論文亦指出，在 125 Myr 以前加入 Galactic tide 與 stellar mass loss
對整體演化差異很小。現有協作者環境已具 BSE、尚未建立 Galpy 版本，因此先用
「BSE、無外部潮汐」完成靈敏度網格是合理 smoking test；正式定稿前仍需至少
加一組 Galactic-tide 對照，不能把無潮汐結果當成最終答案。

PeTar 官方範例本身使用 Kroupa IMF、95% primordial binaries、BSE、1000 顆星，
所以現有 `mcluster_sse -> petar.init -> petar` 工具鏈適合這個第一階段。

## 參數轉換，不能直接照抄 1215

文獻的 1,215 是「系統數」，McLuster 的 `-N` 是「恆星顆數」，`-B` 是聯星
系統數。若系統聯星比例是 b，則：

```text
N_binary = round(N_system * b)
N_single = N_system - N_binary
N_star   = N_single + 2*N_binary = N_system + N_binary
```

中央值因此是 1,154 組聯星、61 顆單星、合計 2,369 顆 component stars。
若直接下 `mcluster -N 1215 -b 0.95`，系統數與聯星定義都會錯。

Converse & Stahler 使用 n=3 polytrope 與自己的 beta；McLuster 的 profile/S
不是同一參數化。本次不能宣稱逐參數重現。`petar_m45_grid.csv` 用 McLuster
profile 2、S=0.30 作中央模型，S=0–0.49 作靈敏度範圍；尺度以 Plummer 關係
`r_h/r_v=0.772764` 將 4.0±0.9 pc 轉成約 3.1±0.7 pc 作為搜尋錨點。
這是 screening grid，最後應以 125 Myr 的觀測徑向密度、alpha(r) 和聯星徑向
分布選模型，而不是把 S=0.30 解讀成 beta=0.30。

## 第一批網格

`petar_m45_grid.csv` 共 10 組：

- 中央模型三個 seed（先量隨機散布）；
- 半質量半徑 2.4/3.8 pc；
- McLuster S=0/0.49；
- 系統聯星比例 0.87/0.99；
- 一個 Plummer profile 對照。

全部先跑到 125 Myr，快照間隔 5 Myr。若中央模型三個 seed 的
`delta_alpha` 標準差已大於 0.05，先增加 seed 到至少 8 個，不要急著擴張物理
網格。若小於 0.05，再跑其餘七個一次，挑出能同時符合下列觀測的區域：

- 5.1 度內成員數與總質量；
- 累積 alpha(<r) 與環帶 alpha(r)；
- 逐質量段徑向密度；
- 聯星比例隨半徑的變化。

## 協作者 x64/MSYS2 機器執行步驟

每一列先建立獨立目錄，避免 PeTar 的 `data.*`、`input.par*` 互相覆蓋。以下以
中央模型第一個 seed 為例；執行前用該機器上 `mcluster_sse -h`、`petar -h`
再核對實際版本選項。

```bash
mkdir -p runs/m45_ref_s101
cd runs/m45_ref_s101

mcluster_sse -N 2369 -B 1154 -P 2 -S 0.30 -R 3.10 \
  -f 1 -C 5 -u 1 -s 101 -Z 0.02 -o m45_ref_s101 > mcluster.log

# McLuster 的實際輸出檔名以 mcluster.log 與目錄內容為準；不要猜檔名。
petar.init -s bse -v kms2pcmyr -f input <MCLUSTER_OUTPUT>

export OMP_STACKSIZE=128M
export OMP_NUM_THREADS=8
petar -u 1 -b 1154 --bse-metallicity 0.02 \
  --stellar-evolution 1 --detect-interrupt 1 \
  -t 125.0 -o 5.0 input > petar.log 2>&1

petar.data.gether data
petar.data.process -i bse data.snap.lst
```

`-b 1154` 必須等於這一列的 `n_binaries`。開始長跑前，先在 log 核對：

- input unit 是 Msun、pc、Myr；
- real particle count 是 2,369；
- primordial binary count 是 1,154；
- BSE 已啟用且 Z=0.02；
- 初始快照 time=0，輸出間隔 5 Myr；
- 先跑到 1 Myr 並確認能量與粒子數合理，再續跑 125 Myr。

完成後分析：

```bash
python petar_pdmf_analysis.py \
  --initial data.0 --final data.25 \
  --reader petar --interrupt-mode bse --snapshot-format ascii \
  --mass-min 0.30 --mass-max 2.50 \
  --radii-pc 2 4 8 12.09 20 --n-projections 32 \
  --output-prefix results/m45_ref_s101_pdmf
```

若實際快照編號不是 25，以 header time=125 Myr 的檔案為準。

中央三個 seed 完成後先彙整；其餘 run 可陸續加進同一指令：

```bash
python petar_pdmf_ensemble.py "results/m45_*_pdmf.json" \
  --grid petar_m45_grid.csv \
  --output-prefix results/petar_pdmf_ensemble
```

彙整器會拒絕 synthetic self-test、重複 run ID 與不一致的質量範圍，並分別
報告 survival selection、恆星演化、有限視野與總修正的 median、16–84% 區間
及標準差；priority=1 的三個中央 seed 會另外報隨機散布。

### 對齊 component 與 unresolved-system 定義

raw snapshot 的 `status` 只描述 PeTar 當下的積分器子系統，不是完整的物理聯星
目錄；不能拿它重建所有 primordial binaries。每個正式 run 應先用
`petar.data.process` 產生同一快照的 single/binary/triple/quadruple 目錄，再轉成
標準 system catalog（沒有某種多重度時省略對應參數）：

```bash
python petar_system_catalog.py \
  --single data.0.single --binary data.0.binary \
  --triple data.0.triple --quadruple data.0.quadruple \
  --time-myr 0 --confirm-complete --output results/m45_ref_s101_t0_systems.npz

python petar_system_catalog.py \
  --single data.25.single --binary data.25.binary \
  --triple data.25.triple --quadruple data.25.quadruple \
  --time-myr 125 --confirm-complete --output results/m45_ref_s101_t125_systems.npz

python pdmf_system_definition_bridge.py \
  --initial results/m45_ref_s101_t0_systems.npz \
  --final results/m45_ref_s101_t125_systems.npz \
  --output results/m45_ref_s101_definition_bridge.json
```

橋接器同時量 component、primary、system-total 與
`L ∝ M^beta`（beta=2,3,4）的 photometric-equivalent alpha。這個專案的前向模型
從 `m1` 抽 IMF，因此接 `primary` 動力修正；傳統單星質光反推則以 photometric
系列做敏感度。不可把 component 修正直接加在 unresolved-system PDMF 上。

`petar_pdmf_analysis.py` 直接讀 raw snapshot 時會依 PeTar 官方
`ArtificialParticleInformation` 規則處理粒子：`status > 0` 的質心與取樣粒子
會移除；`status < 0, mass_bk > 0` 的真實子系統成員會保留，並以 `mass_bk`
還原當下物理質量；unused 粒子會移除。任何未被官方規則涵蓋的組合都會讓
分析中止，不會猜測。JSON 的 `reader_accounting` 必須保留 raw/physical 數量、
移除人工粒子數與還原成員質量數，供每個 run 稽核。

## 驗收門檻

單一 run 只有同時滿足下列條件才進入科學彙整：

1. 初始/末態 ID 唯一，末態沒有來源不明的新 ID；
2. `data.status` 無 NaN、無未解釋的能量跳變；分析輸出的
   `reader_accounting` 與 PeTar status log 的 `N_real`/`N_all` 相容，且沒有
   未辨識的 `status`/`mass_bk` 組合；
3. 0.3–2.5 Msun 至少 100 顆留在 12.09 pc 投影孔徑內；
4. 32 個均勻視線方向的 alpha spread 有記錄；
5. 保存初始與末態快照、`data.status`、完整 command/log、PeTar/SDAR/FDPS commit；
6. 結果記入 `results/RESULTS_LOG.md`，不可只貼終端截圖。
7. system catalog metadata 已確認 single/binary/triple/quadruple 目錄完整；同一
   run 的 component、primary 與 photometric 修正皆已輸出，論文採用值的定義
   必須與觀測方法一致。

## 合成驗證已通過

本機無協作者那套 PeTar binary，因此先用 12,000 顆合成星驗證分析器的方向與
ID accounting。另以含單星、子系統成員、質心、取樣粒子與 unused 粒子的
混合小快照驗證：人工列會排除、成員質量會從 `mass_bk` 還原，未知狀態會
fail closed。物理方向測試刻意讓低質量星較易逃逸、重星更集中，得到：

- birth IMF alpha = 2.321；
- survival selection 後 survivor birth-mass alpha = 2.101（delta=-0.220）；
- 12.09 pc 投影 alpha 中位數 = 2.038（額外 delta=-0.063）；
- 總 `PDMF-IMF=-0.283`，所以回推 IMF 應加 +0.283。

這些數字只驗證程式會在已知效應下產生正確方向，**不是 M45 的物理結果**。
正式數字必須由協作者 PeTar 125 Myr 快照取代。

## 尚未解決

- 用正式 PeTar processed catalogs 取代 system-definition bridge 的合成自測；
- Galactic tide 對照（需 PeTar+Galpy）；
- 觀測選擇函數、Gaia 亮度/品質/成員機率的 mock observation；
- 以觀測 alpha(r) 與聯星徑向分布校準初始 S/profile；
- 至少 8 seeds 的最終不確定度，以及初始 IMF 斜率敏感度。

## 主要依據

- Converse & Stahler (2010), *The Dynamical Evolution of the Pleiades*.
- Küpper et al. (2011), McLuster manual and mass-segregated initial conditions.
- PeTar official documentation and `sample/star_cluster_bse.sh`.
