<!-- 由 code_map/build_map.py 依 catalog.json 生成，請勿手改 -->

# 前向模型的質量函數斜率 α（M45，0.5 M☉ 以上）

**α = 2.382**　可信度：可引用

## 誤差怎麼讀

- ±0.068：同一份觀測資料換 10 組模型亂數重複擬合的散布，代表重現性，不是統計誤差（LIMITATIONS.md A8）。
- ±0.144：統計誤差，來自注入回收（injection_recovery.py，S3F 情境）。報告時要用這個。
- 低質量段冪次固定在 1.3 造成的系統誤差尚無可引用的值，重跑 p6_lowmass_v3 排在雲端佇列（LIMITATIONS.md A1、A3）。

## 怎麼產生的

```
fit_real.py --procs 4 --n-syn 40000 --repeats 1 --configs C --refines 3,3,3 --tag _p2final_v3 --repeat-offset 0
```

結果檔：[`results/fit_real_p2final_v3.npz`](../../results/fit_real_p2final_v3.npz)

上面的指令把 --repeat-offset 從 0 換到 9 各跑一次，共 10 次，再合併成一個檔。檔案裡的陣列 C 形狀是 (10, 7)：10 次重複 × 7 個參數，第 4 欄（索引 3）是 α。10 次的平均是 2.382、標準差是 0.068。

## 產生它的程式

- [`fit_real.py`](../../fit_real.py)：前向模型對真實資料做多階段網格搜尋，產生頭條 α

## 驗證它的程式

- [`scripts/diagnostics/traditional_accounting.py`](../../scripts/diagnostics/traditional_accounting.py)：傳統法的五種雙星處理變體：在真實資料上量 α，並用假資料量各變體的偏差
- [`injection_recovery.py`](../../injection_recovery.py)：注入回收：用已知答案的假星團測擬合流程，量統計誤差與偏差
- [`profile_lowmass.py`](../../profile_lowmass.py)：掃描固定的低質量段冪次，量它對 α 的影響（系統誤差）

## 相關限制

見 [`LIMITATIONS.md`](../../LIMITATIONS.md) 的 A1、A3、A8。

## 補充

- 量到的是現在的質量函數（PDMF），還不是初始質量函數（IMF）。
- α 描述的是主星質量的分布（PAPER_OUTLINE.md 3.4 節）。
