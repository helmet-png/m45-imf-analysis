# M45 後續優化建議：既有工作與缺口稽核（2026-09-15）

這份文件把七項外部建議逐一對照目前 GitHub。它是工作規劃，不是新的
科學結果；「已有」只代表程式、結果或待辦已存在，不代表限制已完全解除。

| 建議 | GitHub 現況 | 本次處理 | 判讀 |
|---|---|---|---|
| 用 pyUPMASK 成員機率取代硬切割，IMF 以機率加權 | 已用 pyUPMASK 產生逐星機率，也完成 P 門檻敏感度掃描；但正式 IMF 仍以 P≥0.7 選樣，沒有機率加權估計器 | 新增 `membership_probability_weighted_imf` | 部分已有；缺少機率加權與硬門檻的同資料對照 |
| 分開建模束縛核心與潮汐尾 | A5、`pdmf_step4_radius_expansion`、LIMEPY 與 N-body 規劃已明確記錄核心／外圍不可共用單一球形假設，也已引用 StarGO 類外圍成員工作 | 不新增重複任務 | 已有，但大半徑觀測重建仍未執行 |
| 使用完整 Gaia 天體測量協方差 | 現有輸入保留各維度誤差；程式庫未找到 Gaia 五參數天體測量相關係數被傳入成員模型的證據 | 新增 `gaia_astrometric_covariance_validation` | 缺口 |
| 讓 Jacobi 半徑隨實際軌道位置變化 | 現有 `dynamics_estimate.py` 只算現在位置、平坦轉動曲線下的靜態值；Galpy 支援 PR #205 尚未提供真實 M45 軌道結果 | 新增 `m45_orbit_jacobi_history` | 部分已有；缺少 r_J(t) |
| 改善低質量質量－光度轉換 | PARSEC／MIST、BHAC15、低質量冪次與 D11 經驗質光關係均已有工作或結果 | 不新增重複任務 | 已有；D11 尚未完成逐星校準 |
| 加入更真實的雙星模型 | 質量相依 f_bin 與 q_gamma 已有；RUWE／Gaia RV 目前是外部診斷，尚未與質量相依 q、週期／軌道分布組成一致的觀測模型 | 新增 `binary_population_observable_bridge` | 部分已有；只新增缺失的跨觀測橋接 |
| 擴充 N-body：氣體逸散、初始質量分層、殘骸保留率 | 正式 10-run PeTar 網格已掃初始質量分層，不應重做；目前採氣體逸散後初始條件，緻密殘骸處理則主要沿用文獻假設 | 新增 `nbody_gas_remnant_preregistration`，只涵蓋氣體與殘骸 | 初始質量分層已有；其餘先預註冊，不能直接當成必跑大網格 |

## 新任務的安全順序

1. 先做已認領的 `membership_probability_weighted_imf`，但第一道 gate 是檢查
   pyUPMASK 機率是否校準；未校準的 P 值不能直接被當作「一顆星的真實成員比例」。
2. `gaia_astrometric_covariance_validation` 不需 N-body 長跑，可獨立確認資料欄位、
   pyUPMASK 介面與最小 A/B 測試是否可行。
3. `m45_orbit_jacobi_history` 只積分星團軌道並輸出 r_J(t)，不重跑 PeTar；
   等 PR #205 或等價 Galpy 環境可用後再執行。
4. 雙星跨觀測橋接先做可識別性與資料覆蓋率測試。RUWE、RV 缺值或選擇偏差
   未處理前，不把它們直接轉成雙星機率。
5. 氣體逸散與殘骸保留先寫預註冊：觀測量、參數範圍、停止條件及最低可辨識
   效應都凍結後，才決定是否值得新增昂貴 N-body 網格。

## 不應被誤讀的地方

- 目前並不是用硬性三維 chi-square 取代 pyUPMASK；現況是 pyUPMASK 先產生
  機率，再用 P≥0.7 形成正式樣本。
- 將 P_member 加權不保證更準：若機率未校準，可能只把模型偏差連續化。
- r_J(t) 與 LIMEPY 的模型截斷半徑不是同一個量。
- 正式 PeTar 網格中的初始質量分層已經做過；本次沒有重複新增。
- 所有新增項目目前都是待驗證方法，不能寫成已改善最終 IMF 的科學結論。
