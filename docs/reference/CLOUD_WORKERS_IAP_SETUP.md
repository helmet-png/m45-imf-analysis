# 多帳號 GCP 資源池：IAP tunnel + OS Login 設定

2026-08-26 新增。解決兩個問題：(1) 傳統直連（開防火牆放行某個來源
IP）在中控機換網路時就整個失效——2026-08-25 因為這樣斷線卡了好幾個
小時，來源 IP 屬於學校的政府網段，之後也不會固定；(2) 三人各自有
自己的 GCP 免費試用帳號、各自的 VM，希望互相共用成一個資源池，但
不想把私鑰檔案分給彼此、也不想常駐開機把 $300／90 天的額度燒光。

**架構沒有變**：仍然是[集中派工](../../cloud_queue.py)——只有一台
中控機（目前是操作 `cloud_queue.py` 的這台）真正握有連線憑證跟
派工邏輯，隊員完全不用碰任何憑證，一樣是對 `cloud_queue.txt` 開 PR
加工作。這份文件多出來的東西是：中控機怎麼透過 IAP 安全連進**隊友
自己專案裡的 VM**、以及怎麼自動開關機。傳統直連的既有 worker（例如
Oracle，沒有 IAP）不受影響，繼續看 [CLOUD_WORKERS.md](CLOUD_WORKERS.md)。

## 為什麼是這個設計，不是別的

- **不開 22 埠給任何來源 IP**——IAP tunnel 只放行 Google 的 IAP 固定
  網段（`35.235.240.0/20`），連線本身靠中控機操作者自己的 Google
  帳號登入驗證，不管換到哪個網路都連得上，也沒有「IP 白名單過期」
  這種故障模式。
- **不共用私鑰檔案**——OS Login 讓 SSH 驗證直接綁 Google 帳號身分，
  金鑰由 `gcloud` 自動產生／管理，不需要把 `.pem` 之類的私鑰檔案
  傳給操作中控機的人。誰能連、能連多久，直接在各自 GCP 專案的 IAM
  頁面管控、隨時可以個別撤權。
- **VM 開關權限留在中控機操作者手上，不留在每個人自己手上**——
  因為維持「集中派工」架構，中控機需要能開/關**隊友的** VM 才能
  自動省額度，所以隊友要把 `compute.instanceAdmin.v1`（建議用 IAM
  條件限縮到單一 VM）授權給中控機操作者的帳號，不是反過來。這是
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

### 3. 把中控機操作者的 Google 帳號加進 IAM

`OPERATOR_EMAIL` 換成中控機操作者的 Google 帳號：

```bash
# 讓中控機操作者能建立 IAP tunnel
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:OPERATOR_EMAIL" \
  --role="roles/iap.tunnelResourceAccessor"

# 讓中控機操作者能用自己的 Google 身分 SSH 登入（OS Login）
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:OPERATOR_EMAIL" \
  --role="roles/compute.osLogin"

# 讓中控機操作者能開/關這台 VM（自動省額度用）——建議用 --condition
# 限縮到單一 VM，不要整專案的 instanceAdmin。下面這行沒加條件，先求
# 能動；要限縮就照 gcloud 互動提示或
# https://cloud.google.com/iam/docs/conditions-overview 加一個
# resource.name 條件。
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="user:OPERATOR_EMAIL" \
  --role="roles/compute.instanceAdmin.v1"
```

**VM 如果掛了 attached service account 要多加一條**（2026-08-26
CodeRabbit review 指出，先前這裡漏了）：OS Login 對「VM 掛了 service
account」的情況另外要求登入者在那個 service account 上有
`roles/iam.serviceAccountUser`，理由是 SSH 進去等於能以那個 service
account 的身分行動，GCP 每次連線都會檢查這個權限。先用主控台「VM 執行
個體詳細資料」或 `gcloud compute instances describe VM_NAME
--format='value(serviceAccounts[0].email)'` 查有沒有掛 service
account，有的話：

```bash
gcloud iam service-accounts add-iam-policy-binding SERVICE_ACCOUNT_EMAIL \
  --member="user:OPERATOR_EMAIL" \
  --role="roles/iam.serviceAccountUser"
```

新建的 VM 預設會掛「Compute Engine default service account」，多半
會踩到這一條，不要跳過。

### 4. 把連線資訊交給中控機操作者

告訴操作中控機的人這四項：`gcp_project`（你的專案 ID）、`gcp_zone`
（VM 所在區域，例如 `asia-east1-c`）、`gcp_instance`（VM 的執行個體
名稱）、以及你分配到的 `port`（建議照 gcp1=2201、gcp2=2202 這樣依序
排，避免跟其他隊友的 tunnel 撞號——`ssh_workers.json` 是本機檔案，
不進版控，這四項不是機密，用任何管道傳都可以）。

## 給中控機操作者做一次

### 1. 裝 gcloud CLI

Windows：到 https://cloud.google.com/sdk/docs/install 下載安裝程式
（若這台機器是 ARM64／Snapdragon X，優先找有沒有 ARM64 原生版，沒有
就裝 x64 版走模擬——`gcloud` 本身是輕量的 Python/殼層包裝，不是算力
密集工作，模擬開銷可忽略，不像 numpy/scipy 那種數值運算差幾十倍）。
裝完：

```bash
gcloud init
gcloud auth login
```

用**中控機操作者自己的** Google 帳號登入（每個 VM 擁有者第 3 步加的
就是這個帳號）。

### 2. 對每個要加入資源池的 worker 查 OS Login 使用者名稱

```bash
gcloud compute os-login describe-profile --format='value(posixAccounts[0].username)'
```

第一次跑可能要先對目標專案跑 `gcloud config set project YOUR_PROJECT_ID`
才查得到那個專案底下的帳號，不同專案可能查到不同格式的使用者名稱
（例如 `你的帳號_gmail_com`），屬正常現象。

### 3. 建立並註冊一把 SSH 金鑰（2026-08-26 CodeRabbit review 補上，
先前這裡漏了這一步）

**這裡走的是一般 `ssh`／`scp` 指令連到 tunnel 開的 `localhost:<port>`，
不是 `gcloud compute ssh`**——後者會自動幫你產生、註冊、管理金鑰，
前者不會，OS Login 開了、IAM 也授權了，沒有這一步照樣會在
`ssh_sync.py push` 卡 `Permission denied (publickey)`。中控機操作者
自己建一把專用金鑰（可以所有 worker 共用同一把，不用每台 VM 各自
一把）：

```bash
ssh-keygen -t ed25519 -f ~/.ssh/gcp_iap_operator -C "gcp-iap-operator" -N ""
```

對**每一個**要加入資源池的 VM 擁有者專案，把公鑰註冊進中控機操作者
自己的 OS Login profile（要先 `gcloud config set project
YOUR_PROJECT_ID` 切到那個專案）：

```bash
gcloud compute os-login ssh-keys add \
  --key-file=~/.ssh/gcp_iap_operator.pub \
  --project=YOUR_PROJECT_ID
```

### 4. 填 `ssh_workers.json`

照 [ssh_workers.json.example](../../ssh_workers.json.example) 裡
`gcp1`／`gcp2` 的範例格式，`host` 固定填 `"localhost"`、`key_path`
填上一步建立的私鑰路徑（例如 `~/.ssh/gcp_iap_operator`，**不要留空**
——留空會退回 ssh 預設身分，通常沒有註冊過 OS Login，會連不上）、
`user` 填上一步查到的 OS Login 帳號、`port` 用 VM 擁有者分配的埠、
`gcp_project`／`gcp_zone`／`gcp_instance` 填 VM 擁有者給的三項。

### 5. 啟動 IAP tunnel 常駐管理器

```bash
python iap_tunnel_manager.py
```

正常應該會看到「開啟 gcp1 的 IAP tunnel」之類的訊息。這支程式要
**常駐**——正常情況下不用手動啟動，Windows 排程會在登入時自動啟動並
在掛掉時自動重啟（見 `restart_queue_on_boot.ps1`），跟 `cloud_queue.py`
共用同一套機制。

### 6. 確認能連上

```bash
python ssh_workers.py
```

會列出所有登記的 worker；再跑一次 `python ssh_sync.py push --worker gcp2`
（換成剛加的 worker 名稱）確認能正常 `git clone`／`git pull`。第一次
連線如果 VM 剛好是關機狀態，`push` 會自動觸發開機（見
[gcp_vm_lifecycle.py](../../gcp_vm_lifecycle.py)）並回報「這一輪還沒
準備好」，等下一輪（`cloud_queue.py` 主迴圈的話是 60 秒後）自然會
接上，不代表設定錯誤。

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

- **單點故障沒有解決**：資源池還是靠中控機那一台跑 `cloud_queue.py`，
  那台機器沒開、沒連網，全隊都派不了工。這是延續現有「集中派工」架構
  的既有取捨，不是這次改動新增的風險，但也沒有一併解決。
- **中控機操作者的權限範圍變大**：第 3 步授予的 `compute.instanceAdmin.v1`
  能開關 VM，如果沒有用 IAM 條件限縮到單一執行個體，等同能開關該
  專案下的任何 VM——授權前務必先設定條件限縮範圍。
- **免費試用不是只看 90 天，$300 額度先用完一樣會提前結束**
  （2026-08-26 CodeRabbit review 補上）：GCP 的 Free Trial 是「90 天
  或 $300 Welcome credit 用完，兩個條件哪個先到就先結束」，不是單純
  等 90 天——如果 VM 常駐時間比預期長、或有其他工作也在燒同一份額度，
  可能不到 90 天額度就先見底，資源池會**沒有預警地**提前失去那台
  VM。本文件沒有處理「額度到期後怎麼辦」，也沒有做額度監控，VM
  擁有者要自己不定期到 GCP 主控台「帳單」頁面看剩餘額度，快用完或
  90 天將到時提前規劃（續約、換成 Always Free 規格、或整個移掉那個
  worker）。
