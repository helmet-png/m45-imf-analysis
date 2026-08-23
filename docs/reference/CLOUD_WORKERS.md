# 雲端 SSH 運算節點（GCP／Oracle／任何 Linux VM）

2026-08-22 新增。跟 `kaggle_sync.py`／`kaggle_queue.py`（Kaggle 帳號當
運算節點）是同一個「worker」抽象的另一種實作，兩者可以同時派工，見
`cloud_queue.py` 開頭的說明。這份文件只講 **VM 那一端要手動做的事**——
本機這一側的程式（`ssh_workers.py`／`ssh_sync.py`／`cloud_queue.py`）
已經寫好，填好 `ssh_workers.json` 就能用，不用再改程式。

## 1. 建 VM（GCP／Oracle 主控台上手動做，帳號申請與信用卡驗證見前面對話）

- GCP：`asia-east1`，**e2-highcpu-8**（8 vCPU/4 實體核心/8GB，比
  c2-standard-8 便宜、$300 額度能撐更久，見對話中的定價核算；記憶體
  夠但有瞬間解析尖峰，第一次派工先用 `--procs 4` 觀察），**Ubuntu
  26.04 LTS Minimal**（2026-08-23 訂正——原本寫 24.04 是舊資訊，
  26.04 LTS「Resolute Raccoon」已於 2026-04-23 發布，支援期限更長，
  沒有理由選舊的；Minimal 變體開機更快、預裝套件少，這台機器是純
  自動化運算節點不需要互動使用的便利工具，`apt install` 照常能用，
  差異只在初次手動設定那幾行指令要自己裝，換來更小的攻擊面跟更少
  要追蹤的安全更新），開防火牆允許 SSH（22 埠，預設通常已經有）。
  **Debian 也完全可以**（這個 repo 目前實際在用的 VM 是 Debian 13）——
  兩者都是 apt 套件管理，下面的安裝指令原封不動適用，不用為了這份
  文件的建議特地重建已經好好在跑的 VM。
- Oracle：Shape 選 `VM.Standard.A1.Flex`（Ampere ARM），2 OCPU / 12GB
  （2026-06-15 起 Always Free 的新上限），Ubuntu ARM64 image。
  **已知的坑**：Always Free 的 A1 常在特定 region/Availability Domain
  訂不到（"Out of Capacity"），換一個 AD 或 region 重試即可，這是
  Oracle 社群普遍反映的已知現象，不是設定錯誤。

建好後記下**公開 IP**與**登入帳號**（GCP 通常是你 Google 帳號本地化
的名稱；Oracle image 常是 `ubuntu`）。

## 2. VM 上裝環境（SSH 進去手動跑一次）

```bash
sudo apt update && sudo apt install -y python3 python3-pip git
pip3 install --break-system-packages numpy scipy astropy emcee
```

（Ubuntu 24.04+／Debian 12+ 都預設鎖住系統 Python（PEP 668），
`pip3 install --user` 不夠、會被拒絕，要加 `--break-system-packages`
才裝得進去——這台是專用運算節點、不跟別的專案共用環境，鎖沒有實際
保護作用，加這個旗標比另外建 venv 簡單。）

（`emcee` 只有跑 MCMC 相關腳本才需要，先裝起來比較省事，裝不起來也不
影響網格搜尋類的腳本。）

## 3. 設定唯讀 Deploy Key（讓 VM 能 `git pull`，但不能 `git push`）

VM 上只需要**讀取**這個 repo，不需要寫入權限——刻意不把任何能推送的
GitHub 憑證放到 VM 上（VM 是相對不受本機掌控的第三方主機，把可寫入的
權杖散布出去是不必要的風險面擴大；結果檔一律由本機用 `scp` 拉回來，
`ssh_sync.py`／`cloud_queue.py` 也是這樣設計的，見 `ssh_workers.py`
開頭說明）。

```bash
# 在 VM 上：
ssh-keygen -t ed25519 -C "m45-imf-worker" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

把印出來的公鑰貼到 GitHub repo 設定：`Settings → Deploy keys → Add
deploy key`，**不要勾選 "Allow write access"**。

## 4. 本機設定 `ssh_workers.json`

```bash
cp ssh_workers.json.example ssh_workers.json
```

編輯填入 VM 的 host／user／procs（VM 的 vCPU 數）。`key_path` 是**本機**
連線用的私鑰路徑（登入 VM 帳號的那把，不是上一步 VM 上產生的那把
Deploy Key——兩把鑰匙用途不同：Deploy Key 是 VM 讀 GitHub 用的，
`key_path` 是本機讀 VM 用的），留空就用 ssh 預設身分。

## 5. 驗證連線

```bash
python ssh_workers.py          # 列出登記的 worker
python ssh_sync.py push --worker gcp1
```

`push` 會自動 `git clone`（第一次）或 `git pull`，並補齊缺少的靜態
資料（`data/`、`isochrones/` 底下的白名單檔案，見 `kaggle_sync.py` 的
`NEEDED_DATA_FILES`／`NEEDED_ISOCHRONE_GLOBS`）。跑成功之後可以用一支
輕量腳本先跑一輪 smoke test（`--minimal`，不用等靜態資料傳完）：

```bash
python ssh_sync.py run --worker gcp1 --script kaggle_smoketest.py --label smoketest
python ssh_sync.py status --worker gcp1 --label smoketest
python ssh_sync.py pull --worker gcp1 --label smoketest
```

確認整輪跑得通之後，才把工作排進 `cloud_queue.txt`、跑
`python cloud_queue.py` 正式派工。

## 跟 Kaggle 的差異（為什麼架構不一樣）

| | Kaggle | SSH worker |
|---|---|---|
| 容器生命週期 | 一次性，跑完即消失 | 持久機器 |
| 每次同步 | 整包重新打包上傳 | 只傳缺少/更新的部分（git pull＋差異檔案） |
| 已知失敗模式 | dataset 掛載時序競態（`kaggle_queue.py` 的 `BACKOFFS`） | 目前未知——是新路徑，第一次真的派重運算前建議先觀察一輪 |
| 核數 | 免費 CPU notebook 約 4 vCPU | 依 VM 規格（GCP 8 vCPU／Oracle 2 vCPU） |
| 結果回傳 | `kaggle kernels output` 下載 | `scp` 拉 `results/` 回本機 |
