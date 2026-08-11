# 結果索引（唯一權威清單）

每次在 `results/` 產生新結果檔案，在這個檔案**尾端**加一行——不要改動
既有的行（附加寫入，低衝突風險）。規則見 `CONTRIBUTING.md` 第二節。

**2026-08-11 補記**：以下是這份規範建立前已經跑過的全部結果，一次性
回填。日期用檔案 mtime，commit hash 是該檔案最後一次變更對應的 commit。
少數幾筆（`bootstrap.npz`）產生腳本已經不在目前程式庫裡，一句話結論
標成「待查證」，不是隨便編一個——這是誠實標記，不是含糊帶過。

| 日期 | 執行者 | 腳本+參數 | commit hash | 結果檔名 | 一句話結論 |
|---|---|---|---|---|---|
| 2026-08-01 | Claude session | `run_pipeline.py`（step3，舊版循序擬合年齡/消光） | 80cb498 | `step3_fit.npz` | 舊版循序擬合架構的年齡/消光解，已被 joint_fit 框架取代，不在目前任何結論中被引用 |
| 2026-08-01 | Claude session | `run_pipeline.py`（step4，四法雙星判定） | 80cb498 | `step4_fit.npz` | 表 2 核心：四種雙星判定法個別標記數（前向模型 472／RUWE 100／CMD偏移 58／GaiaNSS 24），兩兩重疊最高 18% |
| 2026-08-01 | Claude session | `run_pipeline.py`（step4 附帶輸出） | 80cb498 | `step4_binaries.csv` | 1,078 顆星逐星的四種雙星判定旗標（source_id + 四法 0/1） |
| 2026-08-01 | Claude session | `run_pipeline.py`（step5，舊版循序 IMF） | 80cb498 | `step5_imf.npz` | 舊版循序擬合的 IMF 斜率結果，已被 joint_fit 框架取代 |
| 2026-08-01 | Claude session | `run_pipeline.py`（step5 質量分層） | 80cb498 | `step5_mf_radial.csv` | 質量分層 α(r) 隨半徑從 1.77 升到 2.29（相對比較仍可引用，系統誤差在環帶間大致抵消） |
| 2026-08-01 | Claude session | pyUPMASK 自洽先驗修正 | 80cb498 | `prior_corrected.csv` | 6,857 顆星的成員機率（均等先驗 vs 自洽先驗修正），自洽先驗收斂到 0.1867，但對 M45 只改變 3% 成員 |
| 2026-08-01 | Claude session | 早期 bootstrap 分析 | 80cb498 | `bootstrap.npz` | **待查證**：產生腳本已不在目前程式庫，內容含 boots/best_full/corr/dm 四個鍵，具體結論尚未回溯確認 |
| 2026-08-03 | Claude session | `run_joint.py`（MCMC 四/六參數聯合擬合） | 80cb498 | `joint_fit.npz` | 舊版 MCMC 鏈結果，MCMC 未收斂（τ 822–1454），誤差棒/相關矩陣不可引用，只有中心值可參考 |
| 2026-08-03 | Claude session | `run_joint.py` 系列（q_gamma 輪廓測試） | 80cb498 | `profile_qgamma.npz` | 固定 q_gamma 造成 alpha 跨度 0.1（33 倍統計誤差），q_gamma 基本不受資料約束，必須當 nuisance |
| 2026-08-03 | Claude session | `prior_sens.py`（金屬量先驗敏感度，覆寫了較早的 `profile_mh.py` 輸出） | 80cb498 | `profile_mh.npz` | MH 先驗敏感度掃描：峰值在範圍內部（+0.05），資料本身對 MH 有約束力 |
| 2026-08-04 | Claude session | `measure_overconfidence.py` | 80cb498 | `overconfidence.npz` | Poisson-Hess 概似曲率被證實過度自信約 4 倍（切半 0.106／注入回收 0.144 vs 曲率 0.030） |
| 2026-08-04 | Claude session | 分箱數敏感度測試（修正前） | 80cb498 | `bin_scaling_before.npz` | 已推翻「換格子數把中心值推動 24–30 倍統計誤差」的錯誤說法，見 LIMITATIONS.md 第七節 |
| 2026-08-04 | Claude session | 分箱數敏感度測試（修正後） | 80cb498 | `bin_scaling.npz` | 正確結果：σ 對格子數的冪次是 −0.18/−0.22 而非 −0.50，分箱是有損壓縮，不是資訊損失源 |
| 2026-08-04 | Claude session | 切半實驗（前半） | 80cb498 | `verify_split4_half1.npz` | 切半法統計誤差來源之一，已知有兩個缺陷（網格窗太窄、argmax 在平坦概似上遊走），不如注入回收可信 |
| 2026-08-04 | Claude session | 切半實驗（後半） | 80cb498 | `verify_split4_half2.npz` | 同上，切半法給出 σ_α=0.106，比注入回收的 0.144 更不可信 |
| 2026-08-05 | Claude session | `fit_real.py` 早期跑（item2 系列） | 80cb498 | `fit_real.npz` | 早期 config A/C 比較的中間結果，已被後續 item2b/2c 及 p2_final 系列取代 |
| 2026-08-06 | Claude session | `fit_real.py --tag _parsec`（item2c_repeat） | 80cb498 | `fit_real_parsec.npz` | PARSEC 版 config A/C 重複結果，貢獻 P3 等時線比對的 PARSEC 基準 |
| 2026-08-07 | Claude session | `fit_real.py --grid mist... --tag _mist`（item3c_mistfit） | 80cb498 | `fit_real_mist.npz` | MIST 版 config A/C 比較，P3 核心證據之一：恆星演化模型效應舊模型 0.240、修正模型 0.000 |
| 2026-08-08 | Claude session | `traditional_accounting.py`（原始兩變體版，已被 v2 取代） | 80cb498 | `traditional_accounting.npz` | 全當單星／CMD剔除兩變體的早期結果，質量範圍與 isochrone 選擇後來被 P7 訂正 |
| 2026-08-08 | Claude session | `fit_real.py --grid parsec...DR2...`（p3b_dr2fit） | 80cb498 | `fit_real_dr2.npz` | PARSEC DR2 濾光片版，拆解出純濾光片效應 0.04（可忽略，遠低於統計誤差） |
| 2026-08-09 | Claude session | `fit_real.py --fix-mh 0.0`（p9a2_fixmh_parsec，已作廢） | 0b04998 | `fit_real_fixmh_parsec.npz` | PARSEC 鎖 MH 的早期嘗試，5 次裡 2 次 f_bin 精確撞在修好前的舊上界 0.750，α=2.460±0.233 不可信 |
| 2026-08-09 | Claude session | `analyze_lowmass.py`／`check_imf_form.py` | 1773367 | `lowmass_systematic.npz` | 低質量段冪次系統誤差量化：d(alpha)/d(p)=−0.495±0.111，傳播 Kroupa 不確定度得 0.248 系統誤差（全專案最大單一誤差項） |
| 2026-08-09 | Claude session | `fit_real.py --repeats 10 --refines 3,3 --tag _p2final`（p2_final2） | 80cb498 | `fit_real_p2final.npz` | 目前 headline 前向模型數字：α=2.387±0.060，但卡在 P6b+P10 未定案（均勻先驗非文件記載的高斯先驗） |
| 2026-08-10 | Claude session | `fit_real.py --fix-mh 0.0 --repeats 10 --tag _fixmh_parsec_redo`（P9a-redo） | afb39a7 | `fit_real_fixmh_parsec_redo.npz` | PARSEC 鎖 MH 乾淨結果：α=2.440±0.180，logage 8.0–8.1（100–126 Myr，符合公認年齡） |
| 2026-08-10 | Claude session | `fit_real.py --fix-mh 0.0 --grid mist...7.3-8.5... --tag _fixmh_mist_redo`（P9c） | 6095a16 | `fit_real_fixmh_mist_redo.npz` | MIST 鎖 MH 結果：α=2.180±0.098，logage 7.7–7.8（**50–63 Myr，不合理**），證實表 4 穩健性主賣點不成立 |
| 2026-08-10 | Claude session | `inject_lowmass.py --trials 3`（p6b4） | ab574d6 | `inject_lowmass.npz` | 低質量段冪次可辨識性驗證：p_recovered 對 p_true 跟隨比值 0.92（可辨識），但 1/8 筆（p_true=1.3）logage 撞到 PARSEC 網格邊界，該筆標記可疑 |
| 2026-08-10/11 | Claude session | `traditional_accounting.py`（五變體擴充版） | 64412cc | `traditional_accounting_v2.npz` | 五種傳統雙星修正變體真實資料全部落在 2.37–2.42，文獻解析修正法幾乎無偏（+0.003） |
| 2026-08-11 | Claude session | `profile_outlierfrac.py --repeats 3`（P11） | 4fd8c67 | `profile_outlierfrac.npz` | **結果可疑，尚未驗證通過**：12 次執行 alpha 全部精確等於 2.500（散布 0.000），懷疑精修機制沒對 alpha 生效，不能當「已驗證安全」，見 LIMITATIONS.md |
