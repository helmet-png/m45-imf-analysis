# 多帳號 GCP 資源池：IAP tunnel + OS Login 設定

2026-08-26 新增，同日再訂正（見下方「中控機是雲端 VM，不是任何人的
筆電」）。解決三個問題：(1) 傳統直連（開防火牆放行某個來源 IP）在
中控機換網路時就整個失效——2026-08-25 因為這樣斷線卡了好幾個小時，
來源 IP 屬於學校的政府網段，之後也不會固定；(2) 三人各自有自己的
GCP 免費試用帳號、各自的 VM，希望互相共用成一個資源池，但不想把
私鑰檔案分給彼此、也不想常駐開機把 $300／90 天的額度燒光；(3) 沒有
人有條件讓自己的筆電 24 小時常開常連網——集中派工需要**某台機器**
一直開著，這台機器不能是任何一個人的筆電。

**中控機是雲端 VM，不是任何人的筆電**：`cloud_queue.py`／
`iap_tunnel_manager.py` 這兩支常駐程式，跑在 GCP **Always Free**
方案送的一台 `e2-micro`（永久免費，不是 90 天試用額度，見「給中控機
操作者做一次」第 0 步）上，用**服務帳戶**（service account）而不是
某個人的 Google 帳號登入——這台 VM 24/7 開著完全不用錢，也不依賴
任何人記得開電腦。**架構其餘部分沒有變**：仍然是
[集中派工](../../cloud_queue.py)——只有這一台協調 VM 真正握有連線
憑證跟派工邏輯，隊員完全不用碰任何憑證，一樣是對 `cloud_queue.txt`
開 PR 加工作。傳統直連的既有 worker（例如 Oracle，沒有 IAP）不受
影響，繼續看 [CLOUD_WORKERS.md](CLOUD_WORKERS.md)。

## 為什麼是這個設計，不是別的

- **不開 22 埠給任何來源 IP**——IAP tunnel 只放行 Google 的 IAP 固定
  網段（`35.235.240.0/20`），連線本身靠協調 VM 的服務帳戶身分驗證，
  不管協調 VM 部署在哪個網路都連得上，也沒有「IP 白名單過期」這種
  故障模式。
- **不共用私鑰檔案**——OS Login 讓 SSH 驗證直接綁 Google 身分（這裡
  是服務帳戶身分），金鑰由 `gcloud` 自動產生／管理，不需要把
  `.pem` 之類的私鑰檔案傳來傳去。誰能連、能連多久，直接在各自 GCP
  專案的 IAM 頁面管控、隨時可以個別撤權。
- **中控機不是任何人的筆電**——用免費的 `e2-micro` 常駐雲端，不
  依賴任何一個人的電腦開著、連著網路，是真正的 24/7，不是「盡力
  而為」。
- **VM 開關權限留在協調 VM 的服務帳戶身上，不留在每個人自己手上**——
  因為維持「集中派工」架構，協調 VM 需要能開/關**隊友的** VM 才能
  自動省額度，所以隊友要把 `compute.instanceAdmin.v1`（建議用 IAM
  條件限縮到單一 VM）授權給協調 VM 的服務帳戶，不是反過來。這是
  比純 SSH 存取更大的信任範圍，隊友要知道這件事再照做。

## 給每個 VM 擁有者做一次（在自己的 GCP 專案）

以下步驟由**每一位 VM 擁有者**在自己的 GCP 專案裡做一次，不是中控機
操作者能代勞的部分——需要各自的 Google 帳號登入 GCP 主控台或
`gcloud`。

### 1. 開 IAP API + 防火牆規則

主控台「API 與服務」啟用 **Identity-Aware Proxy API**，然後「VPC 網路
→ 防火牆」新增一條規則：

- 名稱：`allow-iap-ssh`（或任意）
- 方向：輸入
- 目標：符合網路標籤，或直接套用到全部執行個體
- 來源 IP 範圍：`35.235.240.0/20`（**這是 Google IAP 的固定網段，
  不是任何人的 IP，不會變**）
- 通訊協定與連接埠：`tcp:22`

如果之前有一條「放行某個來源 IP 的 22 埠」規則，這一步之後可以刪掉，
不用兩條並存。

### 2. 開 OS Login

專案層級：

```bash
gcloud compute project-info add-metadata --metadata enable-oslogin=TRUE
```

（也可以只在單一 VM 的 metadata 加這個鍵，效果一樣，差別只是要不要
影響專案裡其他 VM。）

### 3. 把協調 VM 的服務帳戶加進 IAM

**這裡開始要區分兩個不同的「服務帳戶」，不要搞混**：`COORDINATOR_SA`
是協調 VM 附加的服務帳戶（**連線發起方**，見「給協調 VM 操作者做
一次」第 0 步，格式類似
`coordinator@COORDINATOR_PROJECT_ID.iam.gserviceaccount.com`）；
下面第三段提到的「這台 worker VM 掛的 service account」是**另一個、
完全不同的**服務帳戶（**連線目標的身分**，新建 VM 通常預設掛
「Compute Engine default service account」）。兩個服務帳戶通常屬於
不同專案，名字容易撞在一起看混，先弄清楚「誰在連、連去哪裡」再往下做。

`COORDINATOR_SA` 換成協調 VM 那個服務帳戶的完整 email：

```bash
# 讓協調 VM 能建立 IAP tunnel
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:COORDINATOR_SA" \
  --role="roles/iap.tunnelResourceAccessor"

# 讓協調 VM 能用它自己的服務帳戶身分 SSH 登入（OS Login）
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:COORDINATOR_SA" \
  --role="roles/compute.osLogin"
```

**跨專案的服務帳戶授權是很常見的 GCP 用法**（例如授權另一個專案的
服務帳戶讀寫這個專案裡的 bucket），一般不需要額外的組織層級設定；
如果 VM 所在專案被歸在某個限制外部身分的 Google Workspace／Cloud
Identity 組織底下、上面兩行卡在權限錯誤，才需要那個組織的管理員
另外處理，這種情況比較少見，遇到再查不遲。

**開/關這台 VM 的權限，建議用自訂角色（custom role）縮到最小，不要
整包 `compute.instanceAdmin.v1`**：`instanceAdmin.v1` 就算加了
`--condition` 限制到單一 VM，還是能改機型、換磁碟、刪 VM 這些遠超過
「開/關機」需要的操作。

```bash
# 建一個只有「查狀態、開機、關機」三個權限的自訂角色。
# **自訂角色是專案層級的資源，只能授權給同一個專案裡的資源**——三人
# 三個各自獨立的專案，這行指令要在**每一個** VM 擁有者的專案各自跑
# 一次（不是建一次、跨專案共用同一個角色定義），下面 add-iam-policy-
# binding 那行也一樣，YOUR_PROJECT_ID 要照當下在處理的那個專案填。
gcloud iam roles create gcpIapWorkerLifecycle --project=YOUR_PROJECT_ID \
  --title="GCP IAP Worker VM 生命週期" \
  --permissions=compute.instances.get,compute.instances.start,compute.instances.stop \
  --stage=GA

# 用這個自訂角色 + IAM 條件把授權範圍限縮到單一 VM。
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:COORDINATOR_SA" \
  --role="projects/YOUR_PROJECT_ID/roles/gcpIapWorkerLifecycle" \
  --condition="expression=resource.name=='projects/YOUR_PROJECT_ID/zones/YOUR_ZONE/instances/YOUR_INSTANCE',title=limit-to-worker-vm"
```

嫌自訂角色麻煩、先求能動的話，退回原本的簡化版也可以，**但務必加
`--condition` 限縮到單一 VM**，不要在專案層級開放整包
`instanceAdmin.v1`：

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:COORDINATOR_SA" \
  --role="roles/compute.instanceAdmin.v1" \
  --condition="expression=resource.name=='projects/YOUR_PROJECT_ID/zones/YOUR_ZONE/instances/YOUR_INSTANCE',title=limit-to-worker-vm"
```

**這台 worker VM 如果掛了 attached service account 要多加一條**——
注意這裡指的是 worker VM 自己掛的那個服務帳戶（跟上面的
`COORDINATOR_SA` 是兩回事，見本節開頭的說明）：OS Login 對「VM 掛了
service account」的情況另外要求登入者（這裡是 `COORDINATOR_SA`）在
那個 worker VM 自己的 service account 上有 `roles/iam.serviceAccountUser`，
理由是 SSH 進去等於能以那個 service account 的身分行動，GCP 每次
連線都會檢查這個權限。先用主控台「VM 執行個體詳細資料」或
`gcloud compute instances describe VM_NAME
--format='value(serviceAccounts[0].email)'` 查這台 worker VM 有沒有
掛 service account，有的話：

```bash
gcloud iam service-accounts add-iam-policy-binding WORKER_VM_SERVICE_ACCOUNT_EMAIL \
  --member="serviceAccount:COORDINATOR_SA" \
  --role="roles/iam.serviceAccountUser"
```

新建的 VM 預設會掛「Compute Engine default service account」，多半
會踩到這一條，不要跳過。

### 4. 把連線資訊交給協調 VM 的操作者

告訴操作協調 VM 的人這四項：`gcp_project`（你的專案 ID）、`gcp_zone`
（VM 所在區域，例如 `asia-east1-c`）、`gcp_instance`（VM 的執行個體
名稱）、以及你分配到的 `port`（建議照 gcp1=2201、gcp2=2202 這樣依序
排，避免跟其他隊友的 tunnel 撞號——`ssh_workers.json` 是協調 VM 上的
本機檔案，不進版控，這四項不是機密，用任何管道傳都可以）。

## 給協調 VM 操作者做一次

**這裡整個流程都在 Linux 上做**：本機（你的筆電）不再需要跑
`cloud_queue.py`／`iap_tunnel_manager.py`，只需要一開始建立協調 VM
時連進去做初始設定，之後平常不用管它。下面的指令直接在協調 VM 的
SSH 終端機（Debian／Ubuntu 的 bash，不是 Windows）裡執行。

### 0. 建立協調 VM（一次性）

在你選定要 host 協調 VM 的那個 GCP 專案（可以是你們三人中任何一個
人的專案，跟哪些專案是「worker」無關）：

1. **先建服務帳戶**：主控台「IAM 與管理 → 服務帳戶 → 建立服務帳戶」，
   取個名字（例如 `coordinator`），不用另外指定角色（要授權的角色
   都是在**其他** worker 專案裡授權給它，見上面「給每個 VM 擁有者
   做一次」第 3 步）。建好後記下它的完整 email，格式類似
   `coordinator@YOUR_PROJECT_ID.iam.gserviceaccount.com`——這個
   email 就是上面 `COORDINATOR_SA` 要填的值。
2. **建 VM**：「Compute Engine → VM 執行個體 → 建立執行個體」：
   - 機型：`e2-micro`（Always Free 只有這個機型免費）
   - 區域：`us-west1`、`us-central1`、`us-east1` 三選一（**只有這
     三區的 e2-micro 是永久免費，選別區會變成計費**，見上面「為
     什麼是這個設計」段落）
   - 開機磁碟：Debian 或 Ubuntu 皆可，用預設的 30GB（含在免費額度
     內，不要調大，超過 30GB 會開始計費）
   - 「身分與 API 存取權」：服務帳戶選第 1 步建的那個，存取範圍選
     「允許完整存取所有 Cloud API」（最省事，這台機器不對外提供
     服務，範圍寬鬆一點不是安全疑慮的重點——真正的存取邊界是
     worker 專案那邊的 IAM 授權，不是這裡的 API 範圍）
   - 防火牆：這台不需要對外提供服務，「允許 HTTP/HTTPS 流量」不用勾

建好後用主控台的「SSH」按鈕（瀏覽器內建終端機）連進去，之後步驟都在
這個終端機裡做。

### 1. 裝 git、python3、gcloud CLI

Debian／Ubuntu 通常已經預裝 `git`／`python3`；`gcloud` 需要另外裝：

```bash
sudo apt update && sudo apt install -y git python3
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
gcloud init
```

`gcloud init` 這一步**不用、也不能**用瀏覽器登入人類帳號——這台 VM
沒有瀏覽器，且我們就是要用附加的服務帳戶身分，不是人類帳號。看到
選擇帳戶的提示時，選已經自動偵測到的服務帳戶（通常會標示
「Compute Engine default service account」或你在第 0 步建的那個
名字），選它、不要另外走 OAuth 登入流程。

### 2. 建立並註冊一把 SSH 金鑰（**要先做這步再查使用者名稱**，
見下一步的說明）

**這裡走的是一般 `ssh`／`scp` 指令連到 tunnel 開的 `localhost:<port>`，
不是 `gcloud compute ssh`**——後者會自動幫你產生、註冊、管理金鑰，
前者不會，OS Login 開了、IAM 也授權了，沒有這一步照樣會在
`ssh_sync.py push` 卡 `Permission denied (publickey)`。用協調 VM
自己的服務帳戶身分建一把專用金鑰：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gcp_iap_operator -C "gcp-iap-coordinator" -N ""
```

**這把金鑰沒有 passphrase**：`ssh_workers.py` 的 `_SSH_OPTS` 開了
`BatchMode=yes`（不彈互動式 prompt），這是為了讓 `cloud_queue.py`
常駐無人值守運作，代價是沒辦法直接換成有 passphrase 的金鑰。這台
協調 VM 本身就是服務帳戶專用、不是人類日常登入的機器，私鑰檔案的
存取權限預設就只有這個 VM 上的使用者能讀（Linux 的 `ssh-keygen`
預設會把私鑰檔案權限設成 `600`，只有擁有者能讀），不需要額外設定；
真正的風險邊界是「誰能 SSH 進這台協調 VM 本身」，這由這台 VM 所在
專案自己的 IAM／OS Login 設定把關，跟人類操作者用筆電時是同一件事，
不因為換成服務帳戶而變得更鬆。

**OS Login 的金鑰是綁在這個服務帳戶的全域 profile，不是個別專案
各自一份清單**：`gcloud compute os-login ssh-keys add` 的
`--project` 只是給這次 API 呼叫用哪個專案的身分驗證脈絡，寫入的
目的地是同一份全域金鑰清單，不是那個專案專屬的副本。這件事有兩個
實際影響：(1) 下面這行**理論上第一次對任何一個專案跑過一次就夠**，
其他專案不見得需要重複註冊；不確定會不會踩到邊界情況（例如某些
gcloud 版本的行為差異），保險起見文件仍建議對每個要加入資源池的
專案各自跑一次——重複註冊同一把公鑰是無害的操作，不會出錯，多跑
不會有壞處。(2) **撤銷／移除這把金鑰是全域生效**，`ssh-keys remove`
會讓這把 key 同時在**所有**用到它的專案失效，不是「只撤某個
worker、其他 worker 不受影響」——如果之後只想讓某一台 VM 不能再被
連，正確做法是去那個 VM 專案的 IAM 拿掉 `COORDINATOR_SA` 的角色
（見上面「把協調 VM 的服務帳戶加進 IAM」），不是靠移除金鑰，移除
金鑰是「這把金鑰完全作廢」的核選項。

對要加入資源池的 VM 擁有者專案，把公鑰註冊進這個服務帳戶自己的
OS Login profile（要先 `gcloud config set project YOUR_PROJECT_ID`
切到那個專案）：

```bash
gcloud compute os-login ssh-keys add \
  --key-file=~/.ssh/gcp_iap_operator.pub \
  --project=YOUR_PROJECT_ID
```

### 3. 對每個要加入資源池的 worker 查 OS Login 使用者名稱

**要在上一步註冊金鑰之後才做這步**：OS Login profile 在還沒註冊過
任何金鑰時，POSIX 帳號資訊可能是空的，這時查使用者名稱會拿到空
字串，填進 `ssh_workers.json` 會直接連不上，且不會有明顯的錯誤訊息
指出「先後順序錯了」這個根本原因：

```bash
gcloud compute os-login describe-profile --format='value(posixAccounts[0].username)'
```

第一次跑可能要先對目標專案跑 `gcloud config set project YOUR_PROJECT_ID`
才查得到那個專案底下的帳號，不同專案可能查到不同格式的使用者名稱
（服務帳戶的 OS Login 使用者名稱通常長得像 `sa_<一串數字>`），屬
正常現象。查到空字串的話，先確認上一步的金鑰真的註冊成功
（`gcloud compute os-login ssh-keys list` 應該看得到），再重查一次。

### 4. 抓這個 repo 的程式碼

repo 是公開的，不需要任何 GitHub 憑證：

```bash
git clone https://github.com/helmet-png/m45-imf-analysis.git ~/m45_membership
cd ~/m45_membership
```

`cloud_queue.py`／`iap_tunnel_manager.py`／`ssh_workers.py`／
`ssh_sync.py`／`gcp_vm_lifecycle.py` 這些常駐派工用到的模組全部只用
Python 標準庫，**不需要 `pip install` 任何套件**——`e2-micro` 只有
1GB 記憶體，不裝 numpy/scipy 這類重量級套件正好，這台機器本來就
不做任何實際運算，只負責發指令、查狀態。

### 5. 填 `ssh_workers.json`

還在 `~/m45_membership` 目錄下：

```bash
cp ssh_workers.json.example ssh_workers.json
nano ssh_workers.json    # 或用你熟悉的編輯器
```

照 [ssh_workers.json.example](../../ssh_workers.json.example) 裡
`gcp1`／`gcp2` 的範例格式，`host` 固定填 `"localhost"`、`key_path`
填上面建立的私鑰路徑（`~/.ssh/gcp_iap_operator`，**不要留空**——
留空會退回 ssh 預設身分，通常沒有註冊過 OS Login，會連不上）、
`user` 填上一步查到的 OS Login 帳號、`port` 用 VM 擁有者分配的埠、
`gcp_project`／`gcp_zone`／`gcp_instance` 填 VM 擁有者給的三項。

### 6. 設定成 systemd 服務，開機常駐、掛了自動重啟

**不用移植 Windows 那套鎖檔案＋工作排程器的 watchdog 邏輯**——
systemd 本身就是行程監督器，`Restart=always` 已經涵蓋「掛了自動
重啟」，比另外寫一支輪詢腳本簡單、可靠：

```bash
sudo tee /etc/systemd/system/cloud-queue.service > /dev/null <<'EOF'
[Unit]
Description=M45 IMF cloud_queue.py dispatcher
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_LINUX_USER/m45_membership
ExecStart=/usr/bin/python3 -u cloud_queue.py
Restart=always
RestartSec=15
User=YOUR_LINUX_USER

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/iap-tunnel-manager.service > /dev/null <<'EOF'
[Unit]
Description=M45 IMF IAP tunnel manager
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/YOUR_LINUX_USER/m45_membership
ExecStart=/usr/bin/python3 -u iap_tunnel_manager.py
Restart=always
RestartSec=15
User=YOUR_LINUX_USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cloud-queue.service
sudo systemctl enable --now iap-tunnel-manager.service
```

`YOUR_LINUX_USER` 換成你 SSH 進來時的使用者名稱（跑 `whoami` 查）、
`/home/YOUR_LINUX_USER/m45_membership` 換成第 4 步 `git clone` 的
實際路徑（如果照上面指令用 `~` 展開通常就是這個路徑）。

### 7. 確認能連上

```bash
systemctl status cloud-queue.service iap-tunnel-manager.service
journalctl -u cloud-queue.service -f
```

`systemctl status` 應該顯示 `active (running)`；`journalctl -f`
即時看 log，正常應該會看到「雲端佇列執行器啟動」之類的訊息，過一輪
（60 秒）看到嘗試對已登記的 worker 派工／查狀態。第一次連線如果
worker VM 剛好是關機狀態，`push()` 會自動觸發開機（見
[gcp_vm_lifecycle.py](../../gcp_vm_lifecycle.py)），這一輪失敗、
下一輪（60 秒後）自然接上，是正常現象，不代表設定錯誤。

想手動測試單一 worker（不透過常駐服務），可以先
`sudo systemctl stop cloud-queue.service` 暫停常駐派工，再手動跑
`python3 ssh_sync.py push --worker gcp2`，測完別忘了
`sudo systemctl start cloud-queue.service` 恢復常駐。

## 自動開關機的行為

- **開機**：`cloud_queue.py` 要派工給某個 worker 之前，`ssh_sync.push()`
  會先查那台 VM 是不是 `RUNNING`，不是就發開機指令，這一輪當作沒準備
  好、下一輪（60 秒後）再檢查——不會卡住其他 worker 同一輪的派工。
- **關機**：`cloud_queue.py` 主迴圈每輪尾端檢查，某個 worker 連續閒置
  （沒有槽位在用）超過 15 分鐘就自動關機，見
  [cloud_queue.py](../../cloud_queue.py) 的 `IDLE_STOP_SECS`。
- 這兩件事都只對填了 `gcp_project`／`gcp_zone`／`gcp_instance` 三個
  欄位的 worker 生效，沒填的 worker（例如固定開著的 Oracle VM）完全
  不受影響。

## 已知限制（誠實列出，不是隱藏起來）

- **單點故障減輕了，但沒有完全解決**：資源池還是靠協調 VM 那一台跑
  `cloud_queue.py`，比起某個人的筆電，雲端 e2-micro 24/7 開著、不
  依賴任何人記得開機，可靠度好很多；但協調 VM 所在的**那個 GCP
  專案**如果被停權、或那個帳戶的免費額度／Always Free 資格出問題，
  全隊還是會一起派不了工——沒有做「協調 VM 本身也有備援」這件事。
- **`COORDINATOR_SA` 的權限範圍變大**：第 3 步不管是用自訂角色還是
  退回簡化版的 `compute.instanceAdmin.v1`，都是把「開/關某台 VM」的
  能力授權給協調 VM 的服務帳戶——如果漏了 `--condition` 限縮到單一
  執行個體，簡化版會等同能開關該專案下的任何 VM，授權前務必先設定
  條件限縮範圍。
- **免費試用不是只看 90 天，$300 額度先用完一樣會提前結束**：
  GCP 的 Free Trial 是「90 天
  或 $300 Welcome credit 用完，兩個條件哪個先到就先結束」，不是單純
  等 90 天——如果 VM 常駐時間比預期長、或有其他工作也在燒同一份額度，
  可能不到 90 天額度就先見底，資源池會**沒有預警地**提前失去那台
  VM。本文件沒有處理「額度到期後怎麼辦」，也沒有做額度監控，VM
  擁有者要自己不定期到 GCP 主控台「帳單」頁面看剩餘額度，快用完或
  90 天將到時提前規劃（續約、換成 Always Free 規格、或整個移掉那個
  worker）。**試用結束後不是立刻整個消失**：GCP 會先把試用帳單
  帳戶關閉、VM 這類資源停止運作，
  接下來有 **30 天寬限期**可以升級成付費帳單帳戶救回來；30 天內沒
  升級，資源與資料就會進入永久刪除流程——所以「VM 突然連不上」不代表
  資料已經沒了，還有窗口期補救，但不要拖到超過 30 天才處理。
