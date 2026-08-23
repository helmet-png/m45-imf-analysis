# M45 BP15 selection smoking test

日期：2026-08-22  
狀態：**三項門檻皆通過，但餘裕偏小；只允許下一個低成本 smoke**

## 這次真正做了什麼？

用完整的 6,956 列 M45 Gaia 原始場，建立一份**獨立**的 BP 訊噪比 15
selection model。正式 `data/selection.npz`（BP20）沒有被覆寫；新模型存於
`results/selection_bp15_smoke.npz`。

成員機率沿用已保存 baseline 的 `P≥0.7`，沒有重跑 membership。品質切割為：
G SNR≥50、BP SNR≥15、RP SNR≥20、BP/RP excess 3σ、G≥4。

## 資料一致性檢查

第一次抓取草稿用了近似中心，source-id accounting 發現現有 CMD 有 1 顆不在
新星場。追查後改回專案文件記錄的 CDS Sesame 中心
RA=56.60083°、Dec=24.11389°，重新下載得到原本預期的 6,956 列；最後：

- 現有 CMD 1,078 顆全部存在並通過 BP15 流程；
- BP15 額外通過 58 顆；
- 淨增加 58 顆，沒有因查詢邊界遺失現有成員。

科學結果只使用修正後的 6,956 列版本。

## 三項驗證

用 2,000 次蒙地卡羅平均比較觀測存活率與 selection model 預測：

| 驗證 | 門檻 | 結果 | 判定 |
|---|---:|---:|---|
| 整體存活率差 | `<0.02` | +0.0163 | 通過，餘裕 0.0037 |
| 最差 G 星等分箱差 | `<0.08` | +0.0451（G=17–18） | 通過 |
| G≥17 紅−藍對比誤差 | `<0.10` | +0.0846 | 通過，餘裕 0.0154 |

暗端紅側仍是最弱處：紅側存活率被模型高估 0.0874，藍側只高估 0.0028。
因此這不是「非常穩健地通過」，而是**低餘裕通過**。

## 能下的結論

已驗證：BP15 selection model（三波段星等＋BP-RP 顏色係數＋excess curve，不是一維）在預先使用的三項 smoking-test 門檻下
沒有失敗，因此可以進入下一個成本受控的前向模型 smoke。

不能下的結論：

- 不能把這 58 顆全部叫做外部確認成員；其中只有部分與 HR23 候選重疊。
- 沒有重新估計 membership，所以不能量化放寬品質門檻後的完整背景污染。
- 沒有證明正式 alpha 不變；也沒有重跑 IMF。
- 紅側誤差接近門檻，任何前向結果都必須標為診斷性，不能取代頭條 BP20。

## 下一步 gate

只允許一次小型、明確標成 diagnostic 的前向 smoke，並與 BP20 用相同設定比較。
若 f_bin、dav 或 alpha 貼邊、不同 seed 方向不一致，或 alpha 位移達現有統計誤差
量級，就停止，不升格為正式結果。

## 可重現材料

- 程式：`scripts/diagnostics/build_bp15_selection_smoke.py`
- 摘要：`results/selection_bp15_smoke.json`
- 獨立模型：`results/selection_bp15_smoke.npz`
