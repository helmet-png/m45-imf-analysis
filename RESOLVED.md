# 已解決的限制

從 `LIMITATIONS.md` 分出來的一份，格式仿 `docs/reference/REFUTED.md`。**兩者的差別**：
`docs/reference/REFUTED.md` 記的是「這個說法本來就是錯的」，這裡記的是「這曾經是真的
問題，後來修好了」——問題本身在提出當下是對的，不是誤判，只是後來
透過實際工作解決掉了。

新增規則（見 `CONTRIBUTING.md` 五之一）：`LIMITATIONS.md` 某條需要的
工作全部做完、且重新核對過問題確實解決後，把整條搬到這裡，不要留在
`LIMITATIONS.md` 裡寫「已修正」，也不要直接刪掉不留紀錄。

格式：曾經的問題／怎麼解決的／解決時的關鍵結果／日期。

---

## 已解決清單

### 原 B4：Hess 圖各格當成獨立 Poisson

**曾經的問題**：`poisson_loglike()`（`pipeline/step3_age.py`）把 Hess 圖
每一格當獨立 Poisson 分布計算概似，而各格的觀測次數聯合分布嚴格來說是
多項分布（總星數固定 1,078，格間負相關），直覺上像是多算了一個「總數
也是自由參數」的自由度，論文必須聲明這是近似。

**怎麼解決的**：查證發現這個疑慮不成立，不是「近似但可接受」而是**代數
上完全等價**。原因是 `hess()`（同檔案）回傳直方圖前一定做 `h / h.sum()`，
所以合成星團的 Hess 圖（`mod_h`）與離群成分混合後的 `mix` 恆等於機率
分布、總和永遠精確等於 1，不管參數 theta 是什麼。推導：
`LL_poisson(theta) = LL_multinomial(theta) + n_obs*log(n_obs) - n_obs`，
後面那項是跟 theta 完全無關的常數（見證明與數值驗證腳本
`check_poisson_vs_multinomial.py`）。也就是說目前的實作雖然寫成「逐格
獨立 Poisson」，數學上等同真正的多項分布概似，argmax／梯度／後驗形狀
完全相同，不是近似。這個等價性**依賴 `hess()` 强制正規化到總和為 1**
這個實作細節，`check_poisson_vs_multinomial.py` 留著，之後改動 `hess()`
可以重跑確認等價性還在。

**解決時的關鍵結果**：`check_poisson_vs_multinomial.py` 對 20 組隨機
theta 數值驗證，`LL_poisson - LL_multinomial` 的差值在全部 20 組間的
變化幅度僅 ~1e-12（浮點誤差量級），且精確等於理論常數
`n_obs*log(n_obs) - n_obs`。

**日期**：2026-08-13
