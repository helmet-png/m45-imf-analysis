# 雲端 SSH 運算節點（GCP／Oracle／任何 Linux VM）

跟 `kaggle_sync.py`／`kaggle_queue.py`（Kaggle 帳號當運算節點）是同一個
「worker」抽象的另一種實作，兩者可以同時派工，見 `cloud_queue.py` 開頭的
說明。這份文件只講 **VM 那一端要手動做的事**——本機這一側的程式
（`ssh_workers.py`／`ssh_sync.py`／`cloud_queue.py`）已經寫好，填好
`ssh_workers.json` 就能用，不用再改程式。沿革見 [CHANGELOG.md](../../CHANGELOG.md)。

## 1. 建 VM（GCP／Oracle 主控台上手動做）

- GCP：`asia-east1`，**e2-highcpu-8**（8 vCPU/4 實體核心/8GB，比
  c2-standard-8 便宜、記憶體夠但有瞬間解析尖峰，第一次派工先用
  `--procs 4` 觀察），**Ubuntu 26.04 LTS Minimal**（Minimal 變體開機
  更快、預裝套件少，這台機器是純自動化運算節點不需要互動使用；
  `apt install` 照常能用）。開防火牆允許 SSH（22 埠，預設通常已經有）。
  Debian 也完全可以（本 repo 目前實際在用的 VM 是 Debian 13）——兩者都
  是 apt 套件管理，下面的安裝指令原封不動適用。
- Oracle：Shape 選 `VM.Standard.A1.Flex`（Ampere ARM），2 OCPU / 12GB
  （Always Free 上限規格，實際額度以 Oracle 主控台當下顯示為準）。
  Ubuntu ARM64 image。Always Free 的 A1 常在特定 region/Availability
  Domain 訂不到（"Out of Capacity"），換一個 AD 或 region 重試即可，
  這是 Oracle 社群普遍反映的已知現象，不是設定錯誤。

建好後記下**公開 IP**與**登入帳號**（GCP 通常是你 Google 帳號本地化
的名稱；Oracle image 常是 `ubuntu`）。

**GCP 帳號隔離陷阱**：GCP 用公鑰結尾的名字建帳號，帳號之間完全隔離。
瀏覽器主控台的「SSH」按鈕預設用你 Google 帳號本地化的名稱登入（例如
`albertren888`），但 `ssh_workers.json` 裡填的 `user`（例如 `helmet`）
如果是不同名字，GCP 會**另外建一個獨立帳號**，兩個帳號各自有自己的
home 目錄——瀏覽器帳號底下裝的 pip 套件、產生的 deploy key，
`ssh_workers.json` 那個帳號完全看不到，會在 `ssh_sync.py push`
（`git clone` 卡在 Deploy Key 沒登記）跟第一次 `run`
（`ModuleNotFoundError: No module named 'numpy'`）分別各踩一次坑。
**避免的辦法**：從一開始就決定好 `ssh_workers.json` 要填的 `user`，
瀏覽器 SSH 按鈕旁邊的下拉選單選「以自訂使用者名稱開啟」，直接用那個
名字登入，後面第 2、3 步全部在同一個帳號底下做。已經像上面這樣兩個
帳號分岔了也沒關係，兩邊各補一次（`pip3 install`、產生 deploy key＋
登記到 GitHub）就好，不用重建 VM。

## 2. VM 上裝環境（SSH 進去手動跑一次）

**推薦：建一個 venv**——`ssh_workers.json` 的 `python_bin` 欄位就是為了
指到這裡而加的：

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
python3 -m venv ~/m45_venv
~/m45_venv/bin/pip install numpy scipy astropy emcee
```

裝完把 `ssh_workers.json` 裡這個 worker 的 `python_bin` 填成
`"~/m45_venv/bin/python3"`（`~` 會自動展開成遠端 home 目錄）。

**替代做法**（已經用這個方式裝過、正常在跑的 worker 不用重裝）：直接裝
進系統 Python，`python_bin` 留空或設成 `"python3"`：

```bash
pip3 install --break-system-packages numpy scipy astropy emcee
```

Ubuntu 24.04+／Debian 12+ 都預設鎖住系統 Python（PEP 668），
`pip3 install --user` 不夠、會被拒絕，要加 `--break-system-packages`
才裝得進去。這台是專用運算節點、不跟別的專案共用環境，風險低，但終究
是繞過官方建議的隔離機制，**不是首選**——只是不強迫已經這樣裝好、
正常在跑的既有 worker 為了改做法而重來一次。

（`emcee` 只有跑 MCMC 相關腳本才需要，先裝起來比較省事，裝不起來也不
影響網格搜尋類的腳本。）

## 3. 設定唯讀 Deploy Key（讓 VM 能 `git pull`，但不能 `git push`）

VM 上只需要**讀取**這個 repo，不需要寫入權限——刻意不把任何能推送的
GitHub 憑證放到 VM 上，結果檔一律由本機用 `scp` 拉回來。

```bash
# 在 VM 上：
ssh-keygen -t ed25519 -C "m45-imf-worker" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

把印出來的公鑰貼到 GitHub repo 設定：`Settings → Deploy keys → Add
deploy key`，**不要勾選 "Allow write access"**。

## 3.1 驗證 GitHub 的 host key（第一次 `git clone` 前一定要做）

VM 是全新機器，`~/.ssh/known_hosts` 裡不會有 `github.com` 的紀錄。
`ssh_sync.py push` 第一次會透過非互動式 SSH 連線在 VM 上跑
`git clone`——非互動連線遇到未知主機不會有地方可以按 yes，只會直接
卡住等輸入或連線失敗；如果略過驗證直接關掉 host key 檢查
（`StrictHostKeyChecking=no`），VM 對外那次 git 連線就完全不驗證
GitHub 的身分。兩個做法擇一，跑完才能開始用 `ssh_sync.py push`：

- **推薦**：在 VM 上手動跑一次互動式連線，出現 fingerprint 提示時人工
  核對後輸入 `yes`：
  ```bash
  ssh -T git@github.com
  ```
  這一步一定要真人在場核對，不能改成 accept-new 之類自動接受——
  這裡驗證的是 GitHub 本身的身分，跟 `ssh_workers.py` 對 VM 用
  `accept-new` 是不同的信任情境：VM 是自己剛建的，第一次連線照單全收
  風險可接受；GitHub 是外部服務，第一次連線就有可能被冒充。
- 或：手動把 GitHub 官方公告的 host key fingerprint（見
  https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints）
  核對後**才**寫進 `~/.ssh/known_hosts`——先驗證、再寫入，不要反過來：
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
Deploy Key），留空就用 ssh 預設身分。

## 5. 驗證連線

```bash
python ssh_workers.py          # 列出登記的 worker
python ssh_sync.py push --worker gcp1
```

`push` 會自動 `git clone`（第一次）或 `git pull`，並補齊缺少的靜態
資料（`data/`、`isochrones/` 底下的白名單檔案，見 `kaggle_sync.py` 的
`NEEDED_DATA_FILES`／`NEEDED_ISOCHRONE_GLOBS`）——`push` 這一步本身就
已經把程式碼跟靜態資料都同步完成才會回傳。跑成功之後先跑一輪 smoke
test，確認整條 push→run→status→pull 的路徑通不通，再把工作排進正式
佇列：

```bash
python ssh_sync.py run --worker gcp1 --script kaggle_smoketest.py --label smoketest
python ssh_sync.py status --worker gcp1 --label smoketest
python ssh_sync.py pull --worker gcp1 --label smoketest
```

`ssh_sync.py run` 只吃 `--worker`／`--script`／`--args`／`--label`
四個參數，**沒有 `--minimal` 這個頂層旗標**，`kaggle_smoketest.py`
本身也不解析任何命令列參數。跟 Kaggle 那邊 `kaggle_sync.py` 的
`--minimal`（控制要不要把 `pipeline/`／`data/`／`isochrones/` 一起
打包上傳到 kernel）是不同機制：SSH worker 是持久機器，`push` 已經把
整個 repo 跟靜態資料同步過一次，不需要另外的「精簡打包」選項。如果
之後要指定的腳本本身支援類似 `--minimal` 的自訂旗標，**要用
`--args=值` 的等號寫法**，例如
`python ssh_sync.py run --worker gcp1 --script some_script.py --args=--minimal --label smoketest`
——帶 `--` 開頭的值用空白分隔（`--args "--minimal"`）會被 argparse
誤判成獨立選項而報錯「expected one argument」，只有 `--args=值`
這種等號寫法才能明確綁定。

確認整輪跑得通之後，才把工作排進 `cloud_queue.txt`、跑
`python cloud_queue.py` 正式派工。

**不要手動對同一個 worker 平行呼叫兩次 `ssh_sync.py run`**（例如開兩個
終端機視窗、或手動跑的同時 `cloud_queue.py` 也在對它派工）——`pull()`
用時間戳記分辨結果檔屬於哪個 label，兩個 label 同時在跑的話會抓錯
檔案，細節見 `ssh_sync.py` 裡 `pull()` docstring 的「已知未解決的
限制」。透過 `cloud_queue.py` 派工不會踩到這個問題（同一個 worker
同一時間只會佔一個槽位），只有繞過佇列手動平行呼叫才會。

## 跟 Kaggle 的差異（為什麼架構不一樣）

| | Kaggle | SSH worker |
|---|---|---|
| 容器生命週期 | 一次性，跑完即消失 | 持久機器 |
| 每次同步 | 整包重新打包上傳 | 只傳缺少/更新的部分（git pull＋差異檔案） |
| 已知失敗模式 | dataset 掛載時序競態（`kaggle_queue.py` 的 `BACKOFFS`） | 目前未知——是較新路徑，第一次真的派重運算前建議先觀察一輪 |
| 核數 | 免費 CPU notebook 約 4 vCPU | 依 VM 規格（GCP 8 vCPU／Oracle 2 vCPU） |
| 結果回傳 | `kaggle kernels output` 下載 | `scp` 拉 `results/` 回本機 |

## 集中式團隊派工

科展隊員不用拿到任何真實憑證（Kaggle token、VM 的 SSH 私鑰）就能自己
排工作、讓它自動被派到某個帳號或 worker 上執行——真實憑證只放在
`cloud_queue.py` 常駐執行的那台機器。運作方式跟這個 repo既有的協作
流程一致：

**隊員這邊要做的事**（跟平常提 PR 一樣）：
1. `git checkout -b <你的名字>/queue-<簡短描述>`
2. 編輯 `cloud_queue.txt`，在檔案尾端加一行（格式見檔案開頭註解，跟
   `kaggle_queue.txt` 完全相同）：
   ```
   我的實驗|profile_lowmass.py|--procs 4 --n-syn 40000|inject_lowmass.py|false|
   ```
   最後一欄（worker 名稱）留空，交給任何有空的帳號／worker 接；標籤
   （最前面那欄）要取一個目前佇列裡沒出現過的名字，避免跟別人或跟
   `logs/cloud_queue_done.txt`（本機、不進版控）裡已完成的標籤重複。
3. commit、push、開 PR，照 `CONTRIBUTING.md` 的規則自行合併（低風險、
   單純加一行資料，不用等審查）。

**接下來自動發生的事**：跑 `cloud_queue.py` 的那台機器每一輪
（預設 60 秒）都會自動把 `cloud_queue.txt` 從 `origin/main` 同步下來，
PR 一合併，下一輪就會偵測到新工作、找一個閒置的帳號或 worker 開始跑，
不需要另外通知操作那台機器的人。

**還沒自動化的部分**：工作跑完的結果目前還是要靠操作那台機器的人
手動確認、commit 進 `results/`、寫 `results/RESULTS_LOG.md`，才會
讓其他隊員在 `git pull` 之後看到——這步刻意保留人工確認，不自動
commit 未經檢查的結果。想知道自己的工作跑得怎麼樣，目前只能問操作
那台機器的人，還沒有隊員自己能查的狀態頁面。

**這個模式的信任邊界**：能開 PR 改 `cloud_queue.txt` 的人（也就是這個
GitHub repo 的協作者）事實上就能讓運算機器跑任意腳本＋任意參數——
跟這個專案既有的「GitHub repo 存取權限＝信任邊界」模型一致，不是
額外新增的風險，但值得知道：這不是對公開網路開放的系統，是對「已經
是這個 repo 協作者」的人開放。
