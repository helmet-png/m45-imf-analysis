# D2：stars_per_cluster 敏感度掃描可行性查證

## 結論

這台機器目前**不能產生 stars_per_cluster 對 IMF 的敏感度數字**。這不是
計算失敗後猜一個答案，而是正式確認三個必要條件都還缺少：

1. 專案根目錄沒有 `pyUPMASK/` 執行環境。
2. 沒有 `prepared/` 中介輸入檔。
3. `run_variant.py` 尚未提供 `--stars-per-cluster` 旗標，不能把不同值可靠地
   寫入 `params.ini` 並留下可追溯設定。

因此本次只完成「能不能跑」的查證，沒有重跑 pyUPMASK、IMF 或前向模型，
也沒有產生或聲稱任何 alpha 敏感度。

## 實際執行

執行：

```text
python scripts/diagnostics/sensitivity_sweep.py --target stars_per_cluster
```

查證結果：

| 檢查 | 結果 | 影響 |
|---|---|---|
| repo 內 `pyUPMASK/` | 不存在 | 無法重跑成員聚類 |
| repo 內 `prepared/` | 不存在，0 份輸入 | 即使有程式也沒有可餵入的中介資料 |
| Downloads／Documents 中名為 `pyUPMASK` 的目錄 | 未找到 | 沒有可安全沿用的既有安裝 |
| `run_variant.py --stars-per-cluster` | 不存在 | 尚無可重現的參數注入介面 |

## 順手修好的檢查程式問題

原本可行性模式在檢查檔案以前，就先載入只供 membership_threshold 正式
擬合使用的 SciPy／pipeline 模組。在沒有 SciPy 的輕量環境中，它會直接
崩潰，反而無法輸出原本設計好的「缺 pyUPMASK」誠實狀態。

本次把這些科學計算依賴改為只有 membership_threshold 模式才延遲載入。
修正後，stars_per_cluster 模式不需 SciPy 就能完成環境檢查；正式
membership_threshold 路徑的計算邏輯沒有改動。

## 要真正取得敏感度數字，還缺什麼

依順序完成以下 gate，未通過就不應開跑：

1. 取得與本專案版本相容的 `pyUPMASK/`，並用 baseline 設定做一次 smoke test。
2. 從相同 Gaia 原始資料重建 `prepared/` 輸入，確認 baseline 可重現。
3. 在 `run_variant.py` 加入 `--stars-per-cluster`，並驗證輸出 log／manifest
   會記錄實際值。
4. 預先選定少量對照值（例如現行 25 的上下各一點），每個值至少用相同
   seed 配對重跑成員聚類。
5. 每個新成員表都必須重新跑測光篩選與相應選擇函數，再比較 alpha；不能
   沿用 baseline 的成員表或把重新套 membership threshold 當成替代品。

目前狀態是「執行受阻、阻塞原因已驗證」，不是「stars_per_cluster 對
alpha 沒有影響」。
