# 雲端 SSH 運算節點（GCP／Oracle／任何 Linux VM）

2026-08-22 新增。跟 `kaggle_sync.py`／`kaggle_queue.py`（Kaggle 帳號當
運算節點）是同一個「worker」抽象的另一種實作，兩者可以同時派工，見
`cloud_queue.py` 開頭的說明。這份文件只講 **VM 那一端要手動做的事**——
本機這一側的程式（`ssh_workers.py`／`ssh_sync.py`／`cloud_queue.py`）
已經寫好，填好 `ssh_workers.json` 就能用，不用再改程式。

## 1. 建 VM（GCP／Oracle 主控台上手動做，帳號申請與信用卡驗證見前面對話）

- GCP：`asia-east1`，`c2-standard-8`（8 vCPU）或 `e2-standard-8`，
  Ubuntu 24.04 LTS，開防火牆允許 SSH（22 埠，預設通常已經有）。
- Oracle：Shape 選 `VM.Standard.A1.Flex`（Ampere ARM），2 OCPU / 12GB
  （目前 Always Free 的上限規格；生效日期沒有查到可靠且能長期維護的
  來源，這裡不寫死日期，實際額度以 Oracle 主控台當下顯示為準）。
  Ubuntu ARM64 image。
  **已知的坑**：Always Free 的 A1 常在特定 region/Availability Domain
  訂不到（"Out of Capacity"），換一個 AD 或 region 重試即可，這是
  Oracle 社群普遍反映的已知現象，不是設定錯誤。

建好後記下**公開 IP**與**登入帳號**（GCP 通常是你 Google 帳號本地化
的名稱；Oracle image 常是 `ubuntu`）。

## 2. VM 上裝環境（SSH 進去手動跑一次）

```bash
sudo apt update && sudo apt install -y python3 python3-pip git
pip3 install --user numpy scipy astropy emcee
```

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

## 3.1 驗證 GitHub 的 host key（第一次 `git clone` 前一定要做）

VM 是全新機器，`~/.ssh/known_hosts` 裡不會有 `github.com` 的紀錄。
`ssh_sync.py push` 第一次會透過**非互動式** SSH 連線在 VM 上跑
`git clone`——非互動連線遇到未知主機不會有地方可以按 yes，只會直接
卡住等輸入或連線失敗，而且如果略過驗證直接關掉 host key 檢查
（`StrictHostKeyChecking=no`），VM 對外那次 git 連線就完全不驗證
GitHub 的身分，等於把「防中間人」這層保護關掉。**兩個做法擇一，跑完
才能開始用 `ssh_sync.py push`**：

- **推薦**：在 VM 上手動跑一次互動式連線，出現 fingerprint 提示時人工
  核對後輸入 `yes`：
  ```bash
  ssh -T git@github.com
  ```
  （這一步一定要真人在場核對，不能改成 accept-new 之類自動接受——
  這裡驗證的是 GitHub 本身的身分，跟 `ssh_workers.py` 對 VM 用
  `accept-new` 是不同的信任情境：VM 是我們自己剛建的，「第一次連線
  照單全收」風險可接受；GitHub 是外部服務，第一次連線就有可能被
  冒充，值得花這一步人工核對。）
- 或：手動把 GitHub 官方公告的 host key fingerprint（見
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints）
  核對後**才**寫進 `~/.ssh/known_hosts`——**先驗證、再寫入，不要反過來**：
  如果先 `>> ~/.ssh/known_hosts` 再核對，一把還沒驗證過的金鑰（萬一是
  中間人攻擊植入的）已經被信任了，之後才做的核對形同虛設，等於沒做這
  一步的防護；而且直接對 `~/.ssh/known_hosts` 跑 `ssh-keygen -lf` 會把
  檔案裡**其他主機**的 fingerprint 也一起列出來，混在一起很難看出哪一行
  才是 GitHub 的。改成先寫到暫存檔、核對過通過才附加進 `known_hosts`：
  ```bash
  ssh-keyscan github.com > /tmp/gh_hostkeys
  ssh-keygen -lf /tmp/gh_hostkeys   # 核對輸出的 fingerprint 跟官方公告一致，通過才繼續下一步
  cat /tmp/gh_hostkeys >> ~/.ssh/known_hosts && rm /tmp/gh_hostkeys
  ```

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
`NEEDED_DATA_FILES`／`NEEDED_ISOCHRONE_GLOBS`）——`push` 這一步本身就
已經把程式碼跟靜態資料都同步完成才會回傳，不是「先跑起來、靜態資料
在背景慢慢傳」，所以底下的 smoke test **是在靜態資料已經同步完之後才
跑**，不是「不用等」。跑成功之後可以用一支輕量腳本先跑一輪 smoke
test，確認整條 push→run→status→pull 的路徑通不通，再把工作排進正式
佇列：

```bash
python ssh_sync.py run --worker gcp1 --script kaggle_smoketest.py --label smoketest
python ssh_sync.py status --worker gcp1 --label smoketest
python ssh_sync.py pull --worker gcp1 --label smoketest
```

（2026-08-23 訂正：`ssh_sync.py run` 只吃 `--worker`／`--script`／
`--args`／`--label` 四個參數，**沒有 `--minimal` 這個頂層旗標**，
`kaggle_smoketest.py` 本身也不解析任何命令列參數——照舊版文件字面加
`--minimal` 會直接得到 argparse 的錯誤。跟 Kaggle 那邊 `kaggle_sync.py`
的 `--minimal`（控制要不要把 `pipeline/`／`data/`／`isochrones/` 一起
打包上傳到 kernel）是不同機制：SSH worker 是持久機器，`push` 已經把
整個 repo 跟靜態資料同步過一次，不需要另外的「精簡打包」選項。如果
之後要指定的腳本本身支援類似 `--minimal` 的自訂旗標，**要用
`--args=值` 的等號寫法**，例如
`python ssh_sync.py run --worker gcp1 --script some_script.py --args=--minimal --label smoketest`
——`--minimal` 是要傳給 `--script` 指定的那支腳本的參數，不是
`ssh_sync.py run` 自己的參數。（2026-08-23 訂正：原本寫
`--args "--minimal"`（空白分隔）看起來合理，但實測會被 argparse
誤判成獨立的 `--minimal` 選項而報錯「expected one argument」——
因為值本身也是 `--` 開頭，argparse 分不清它是 `--args` 的值還是
下一個選項，只有 `--args=值` 這種等號寫法才能明確綁定。）

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
