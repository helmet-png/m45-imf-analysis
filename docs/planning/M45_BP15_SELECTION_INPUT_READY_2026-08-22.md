# M45 BP15 selection：原始輸入已恢復

日期：2026-08-22  
狀態：**資料抓取完成；BP15 selection 尚未宣告通過**

## 原本卡在哪裡？

BP15 必須在完整星團場與控制場重建 selection，不能只看 16 顆已知候選。
但本機缺少 `data/m45_r5_g18_plx4.csv`，舊抓取程式又會先對 Gaia 的
18 億列資料做精確 `COUNT(*)`，曾被伺服器逾時取消。

## 這次解決了什麼？

新增一個公開、可重現且有硬上限的 Gaia TAP 查詢：

- 固定專案原始查詢所用的 CDS Sesame M45 中心：RA=56.60083°、Dec=24.11389°；
- 半徑 5°；
- `G≤18`、視差 `≥4 mas`；
- 使用 `TOP 20000`，若真的碰到上限就拒絕寫檔，避免靜默截斷；
- 實際取得 6,956 列，沒有碰到上限。

原始 CSV 約 1.64 MB，依專案 `.gitignore` 不上傳；查詢程式與 6,956 列的
執行紀錄已上傳，任何協作者都能重建同一份輸入。

另外修正 `build_selection.py` 對 `selection_probe.py` 的匯入路徑。後者已移到
`scripts/diagnostics/`，舊的頂層匯入在乾淨環境中無法找到。

## 還不能說什麼？

- 不能說 BP15 selection 已通過；目前只恢復了必要原始輸入。
- 不能說 6,983 顆都是成員；這是有天空、星等與視差邊界的完整查詢場。
- 不能直接用舊的 `selection.npz`，因為它明確保存 `thr_bp=20`。
- 沒有重跑 membership、前向模型或 IMF。

## 下一步

以這份完整場建立獨立的 `selection_bp15_smoke.npz`，不得覆寫正式
`data/selection.npz`。驗收順序維持：整體、星等分箱、`G≥17` 紅／藍；
任一項失敗即停止前向模型。

## 可重現材料

- 抓取程式：`scripts/data_prep/fetch_m45_field_public_tap.py`
- 執行紀錄：`results/m45_public_field_fetch_2026-08-22.json`
