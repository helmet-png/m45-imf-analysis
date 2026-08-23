# M45 BP15 正式成對前向比較：派工前置檢查

日期：2026-08-23  
狀態：**已準備；等待 Kaggle 登入／帳號分配，不會自動送出長跑。**

## 為什麼要先做這張派工表？

昨天的兩組小型測試顯示：只跑一次時，電腦自己抽到的隨機合成星就足以讓
BP15−BP20 的 alpha 差值改變正負號。因此正式比較的單位不是「五次 BP20」和
「五次 BP15」各自平均，而是五個一對一的比較：同一個 random seed 下，唯一改變
的是 BP S/N 門檻與相應的 selection／誤差模型。

## 已準備的 10 個工作

- offsets：0、1、2、3、4；每個 offset 有一個 BP20 和一個 BP15。
- 每項：`n_syn=40000`、config C、`refines=3,3`、單次 repeat、4 CPU。
- BP15 的三個隔離輸入已存在並由腳本檢查：成員 CSV、誤差模型、selection model。
- 每項有獨立 output tag，因此不會覆寫正式 headline 或彼此覆寫。

可機讀派工表：`results/bp15_formal_paired_dispatch.json`。
產生／驗證方法：

```text
.venv_forward\Scripts\python.exe scripts\diagnostics\prepare_bp15_paired_dispatch.py --write
```

## 還不能做的事

本機沒有 `kaggle_accounts.json` 或 Kaggle access token，因此目前不能替使用者安全
送出雲端作業。這次並沒有假裝工作已在雲端開始。

登入恢復後，先將每一個 job 分配到可用帳號；BP15 job 要連同派工表列出的三個
`results/` 輸入檔加入 kernel payload。每個 job 回傳完整 NPZ 後才可進入彙整。

## 預先寫好的判讀規則

1. 依 offset 配對，算每一對 `alpha_BP15 - alpha_BP20`。
2. 報告五個差值、差值平均與 paired standard error。
3. 若方向仍大量翻轉，結論是「尚未測出穩定 BP15 效果」；不是把平均硬說成偵測。
4. 即使有差異，這也是選擇門檻診斷，不會取代正式 BP20 headline。
