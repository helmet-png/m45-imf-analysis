# 62 顆外部高機率成員為什麼沒有進 CMD？

## 已解決的問題

上一輪已定位出 62 顆星：HR23 外部機率至少 0.7，本專案 baseline 機率也至少 0.7，但最後沒有進 `cmd_members.csv`。

這次只用這 62 個 Gaia source_id，從 Gaia DR3 公開 TAP 服務取得第二步所需的測光欄位，再依目前 `step2_cmd.py` 與 `config.toml` 的順序逐條重播品質切割。62 顆全部都能被現行規則解釋，沒有留下原因不明的星。

## 第一個讓它離開的條件

| 第一個失敗條件 | 星數 | 比例 |
|---|---:|---:|
| G < 4 亮端切割 | 1 | 1.6% |
| G 訊噪比 < 50 | 0 | 0% |
| BP 訊噪比 < 20 | 37 | 59.7% |
| RP 訊噪比 < 20 | 2 | 3.2% |
| BP/RP excess 超出 3σ | 22 | 35.5% |
| 通過全部重播條件 | 0 | 0% |

這是依 pipeline 順序計算的「第一個失敗條件」，所以每顆星只計一次。例如先失敗 BP 訊噪比的星，即使 excess 也不好，仍只放在 BP 那列。

## 亮度依賴

- G=8–12：2 顆，都是 BP/RP excess。
- G=12–16：14 顆，其中 BP 訊噪比 2、RP 訊噪比 2、BP/RP excess 10。
- G=16–18：45 顆，其中 BP 訊噪比 35、BP/RP excess 10。
- G<4：1 顆，符合已知亮端切割。

因此暗端 G=16–18 的主要瓶頸已明確定位為 **BP 測光訊噪比**，不是成員機率。這符合紅色低質量星在 BP 波段較暗的直觀預期，但本檢查只證明規則與數據如何互動，不證明門檻 20 是最佳科學選擇。

## 科學意義

已驗證：目前保存的 62 顆後段流失，可以由現行品質規則完整重現；其中 37 顆首先敗在 BP 訊噪比，22 顆首先敗在 BP/RP excess。

尚未驗證：若放寬 BP 訊噪比或 excess 門檻，新增星的顏色是否可信，以及 selection function 與 alpha 會改變多少。不能僅因 HR23 機率高，就把測光品質不足的星直接加回 CMD。

下一步建議：先做不擬合 IMF 的門檻敏感度表，例如 BP SNR 門檻 10／15／20 與 excess 3σ／5σ，計算可回收星數及顏色誤差分布。只有品質與選擇函數能重新驗證時，才考慮新的完整度方案。

## 可重現材料

- 公開 Gaia 查詢程式：`scripts/data_prep/fetch_hr23_lost_photometry.py`
- 62 顆測光欄位：`data/hr23_passprob_notcmd_gaia_photometry.csv`
- 品質切割重播：`scripts/diagnostics/replay_hr23_lost_quality_cuts.py`
- 逐星結果：`results/hr23_lost_quality_cut_replay.json`

查詢日期為 2026-08-22，來源表為 `gaiadr3.gaia_source`；查詢程式硬性檢查輸入與回傳都必須恰為 62 顆，避免意外擴大資料範圍。
