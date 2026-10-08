# Gaia DR3 天體測量協方差稽核（2026-10-07）

## 目的

確認目前 M45 成員判定是否保留並使用 Gaia DR3 的逐星天體測量協方差。本稽核只判定資料與介面是否足以做最小 A/B 測試；不重新跑正式 IMF，也不把協方差使用宣稱為既有成果。

## 已確認的資料流

目前版本化的 M45 資料並未保存協方差欄位：

- `data/m45_control_field.csv` 只含 `pmra`、`pmdec`、`parallax` 與三個各自的誤差，沒有三個相關係數。
- `data/m45_g20_full.dat`／`prepared` 格式只有 12 欄；`prep.py` 的 `CLUST_COLS` 只保留 `pmRA`、`pmDE`、`Plx` 與三個邊際誤差。
- `run_variant.py` 只改寫 pyUPMASK 的重複次數、重抽樣、PCA、種子與 KDEP 設定，沒有協方差參數或逐星矩陣輸入。
- pyUPMASK 本體在 worker provisioning 時另外 clone，並不在本 repo 版控；因此目前沒有可重現的介面證據，證明它能接收逐星 3×3 或 5×5 協方差。

因此，現行正式成員機率沒有「已使用完整 Gaia 協方差」的證據。

## Gaia 端可取得的最小欄位

對本專案目前實際分群的三個運動學量
\((\mu_{\alpha *},\mu_\delta,\varpi)\)，最小 A/B 需要：

- `pmra_error`、`pmdec_error`、`parallax_error`
- `pmra_pmdec_corr`、`parallax_pmra_corr`、`parallax_pmdec_corr`

Gaia DR3 `gaia_source` 資料模型列出這三個相關係數，且說明相關係數範圍為 [-1, 1]。[Gaia DR3 資料模型](https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_main_source_catalogue/ssec_dm_gaia_source.html)

## 已加入的可重現檢查

`scripts/diagnostics/audit_gaia_astrometric_covariance.py` 可對重新下載的 Gaia CSV 檢查欄位、相關係數範圍與每顆星 3×3 相關矩陣是否半正定。它只輸出 JSON 稽核報告，不會改變任何樣本或科學結果。

## 下一個最小 A/B

1. 以相同 M45 ADQL 篩選重新下載原始 Gaia DR3，保留上述三個相關係數。
2. 先用稽核腳本確認欄位覆蓋率與矩陣有效性。
3. 檢查固定版本 pyUPMASK 的輸入程式碼能否讀取逐星協方差；若不能，就停止，不以自行加入的近似方式宣稱「完整協方差」。
4. 只有介面確認可行時，才在相同種子與樣本下比較對角誤差與完整協方差的成員名單差異；結果須先經完整度與校準檢查，才可討論對 IMF 的影響。
