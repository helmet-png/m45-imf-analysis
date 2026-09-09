# N-body PDMF→IMF 正式網格：預先註冊

**狀態**：草案（Phase 0-4 已完成，Phase 5 起（A1 標竿）之前必須先
`git commit` 這份文件並在這裡填上 commit hash——這是本文件存在的
唯一理由：H13（2026-09 審視）指出四個徑向比較是事後才做多重比較
校正，主要統計量、孔徑、質量範圍、seeds 數、驗收門檻都沒有在跑之前
寫死。這份文件把這些數字釘死，之後要改必須留下修改紀錄，不能悄悄換。

**為什麼要做**：把「觀測到的 M45 PDMF」跟「N-body 模擬出的 PDMF」的
差異（Δα）當成 PDMF→IMF 的修正量，需要模擬端跟觀測端用完全相同的
定義（孔徑、質量範圍、選樣退化）才能比較同一個量，見
`scripts/nbody_petar/observe_snapshot.py` 的檔頭說明。

---

## 一、資料鎖定

| 項目 | 值 |
|---|---|
| `data/cmd_members.csv` 產出的 commit | `d65a19888742bd35614033e417ae0b25f817e29c` |
| 本文件對應的程式碼 commit | `7db039d2eca699f6965accfc937af92d299552da`（Phase 1-3：N1-N4 完成） |
| `results/nbody_observed_targets.json` 的 SHA-256 | `bb4d298cde1ef8b6985a88d357df048fa8b1575a21b6c057adfc5380f24ea0a5` |
| 產生指令 | `py scripts/nbody_petar/nbody_summary_stats.py --from-real data/cmd_members.csv` |

`nbody_observed_targets.json` 一旦這樣鎖定，之後任何改動（換等時線、
換召回率曲線、換孔徑定義）都要在這份文件裡記一筆「訂正」並重新產生、
重新記 hash，不能直接覆蓋掉沒有紀錄。

---

## 二、觀測標的（模擬要對上的東西）

| 標的 | 數值 | 來源 |
|---|---|---|
| 孔徑 | **11.68 pc**（樣本實際涵蓋，非查詢半徑） | `data/cmd_members.csv` 自身中位中心量出的最大投影角距 4.928°，見 `petar_pdmf_analysis.py` `DEFAULT_RADII_PC` 旁的推導（Phase 0 訂正，取代先前的 12.09/11.87） |
| 孔徑內成員數（排除 2 顆已確認非成員後） | 1075 | `nbody_observed_targets.json` `n_within.rall_aperture` |
| 累積 N(<r)，1°/2°/3°/全孔徑 | 355 / 733 / 935 / 1075 | 同上 `n_within` |
| 累積 α(<r)，0.5-2.5 M☉，**傳統法**（`step5_imf.mle_powerlaw`） | 2.102 / 2.279 / 2.352 / 2.405 | 同上 `alpha_within`。**注意**：這跟 `RESULTS_LOG.md` 的 `radial_final_reruns`（前向模型，2.0644/2.3889/2.4244/2.3844）**不是同一個估計器**，兩者方向一致但不能互換引用，見第四節 |
| f_bin（全域，CMD 偏移法，門檻 0.375 mag） | 0.058 | 同上 `fbin_global`。遠低於前向模型的 headline 0.568——CMD 偏移法只抓得到質量比接近 1 的雙星，這個落差是已知、預期的方法差異，不是 bug |
| 半質量投影半徑（依星數） | 見 `nbody_observed_targets.json` `half_number_radius_2d_pc` | 同上 |
| 年齡窗 | 100–135 Myr | 前向模型擬合 106.2 Myr／LDB 年齡 125 Myr／Lodieu+2019 白矮星冷卻年齡 132(+26/−27) Myr |
| 外部標竿 1：Converse & Stahler (2010) | N_tot=1215±59、r_v=4.0±0.9 pc、b=0.95±0.08、β=0.5±0.3（Table 1）；N_s(12.3pc)=1256±35、b_unres=0.68±0.02、R_c=2.0±0.1 pc（Table 2） | arXiv:1002.2229，本機 `pypdf` 逐字核對過 Table 1/2，見 `docs/planning/PDMF_TO_IMF_PLAN.md` 的「2026-09 再訂正」一節 |
| 外部標竿 2：Hobart, Baumgardt & Sweet (2026, PASA) | N_sys,ini=1670(+44/−28)、f_bin,ini=0.303±0.012、r_h,ini=4.45(+0.22/−0.33) pc；α_m,star=1.67±0.09、α_h,star=3.33±0.10（轉折 0.24-0.50、0.91-1.20 M☉）；現時 f_bin=0.200±0.008 | doi:10.1017/pasa.2026.10236，本機讀 PDF 全文 Table 5 核對過 |
| 孔徑外逃逸成員（量級對照，非直接比對標的） | 289 顆（>10 pc） | Heyl, Caiazzo & Richer (2022), ApJ 926, 254 |

---

## 三、初始條件空間（方法 A／方法 B 共用）

- `N_sys`：1200–1700（C&S 2010 與 Hobart+2026 的聯集範圍）
- `f_bin,ini`：0.30–0.95（**兩篇文獻差 3 倍，這本身是要報告的系統誤差，
  不是要調和的分歧**）
- `r_h,ini`：2.4–4.5 pc（C&S r_v=4.0 pc → r_h≈3.1 pc；Hobart r_h=4.45 pc）
- 質量分層 `S`（McLuster 慣例，非 C&S 的 β）：0–0.5
- 密度剖面：Plummer（McLuster `-P 0`）／King-like（`-P 2`，對應 C&S 的
  n≈3 多方球，W₀≈1.4）
- Virial ratio `Q`：0.5（固定，McLuster 慣例的 virial 平衡起始態；
  之前 `WORK_BOARD.md` 出現過另一組 N=400/Q=0.5/S=0.3,0.5,0.7 的網格，
  跟這裡不一致，**以這份文件為準**，那組視為已作廢的草案）
- IMF 高質量段 `α_in`：{1.9, 2.3, 2.7}（McLuster `-f 2` 自訂冪律）；
  低質量段固定 1.3（主），0.84（Moraux 2003，敏感度組）
- 銀河軌道：`scripts/nbody_petar/m45_orbit_init.py` 算出的
  t=−125 Myr 銀心直角座標（`--galpy-set MWPotential2014`）
- 恆星演化：`--stellar-evolution 1 --bse-metallicity 0.02`
  （mcluster `-Z 0.02` 一致）

---

## 四、統計量定義（凍結，之後不能悄悄改）

`scripts/nbody_petar/nbody_summary_stats.py` 算出的向量，真實與模擬
共用同一支程式：

1. N(<r)：1°/2°/3°/全孔徑（換算 pc）4 維
2. α(<r)：**傳統法**（`step5_imf.assign_masses` + `mle_powerlaw`，
   0.5–2.5 M☉），4 維——選傳統法不選前向模型純粹是算力考量（前向模型
   一次擬合要數小時，正式網格要跑 ~85-350+ 次，前向模型不可行），
   讀者比對數字時要記得這不是 `radial_final_reruns` 的前向模型定義
3. f_bin：全域 + 4 環帶，CMD 偏移法（門檻 0.375 mag），5 維
4. r_h,2D（依星數）：1 維
5. 逐質量段（0.3-0.5／0.5-1.0／1.0-2.5 M☉）× 4 環帶數密度：12 維

共 26 維。

---

## 五、驗收門檻

| 項目 | 門檻 |
|---|---|
| S2（純重力，無恆星演化/潮汐）能量守恆 | \|ΔE/E₀\| < 1e-4 |
| A2/正式網格能量守恆 | \|ΔE/E₀\| < 1e-3 |
| A1 標竿重現 C&S 2010 Table 2 | N_s、b_unres、R_c 在 C&S 誤差 2σ 內 |
| Δα 對 α_in 的線性檢定 | \|Δα(α_in=2.7) − Δα(α_in=1.9)\| < 0.05 才允許常數加法，否則要用內插 |
| Seeds 數 | A 類每個設定至少 4 seeds，A1 標竿 5 seeds |

## 六、方法 A／方法 B 的抉擇（S4 之後）

以 8 執行緒單 run wall time 為準：
- ≤ 1 小時 → 直接做方法 B（≥350 runs，A 的 85 個 run 全部併入訓練集）
- 1–3 小時 → 先做完方法 A（~85 runs），B 排後續
- > 3 小時 → 只做方法 A，方法 B 降級為 3 維版（α_in、r_h,ini、f_bin,ini）

這個決策點尚未觸發——S0-S4 需要在真正的 Linux 機器上執行
（`nbody_setup/setup_linux_nbody.sh`），本文件寫成的當下這一步還沒有
實測資料。

---

## 七、修改紀錄

（之後任何偏離本文件定案內容的改動記在這裡，不要直接覆蓋上面的定案，
沿用 `CONTRIBUTING.md` 的協作精神：語氣誠實記錄，不是為了好看而改
既有內容。）

- 2026-09-09：初版。
