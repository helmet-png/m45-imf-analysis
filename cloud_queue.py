# -*- coding: utf-8 -*-
"""通用版的佇列派工器：**同一份佇列檔、同一個迴圈**，同時把工作派給
Kaggle 帳號（kaggle_queue.py 原本的機制）跟 SSH 遠端節點（GCP／Oracle
等，見 ssh_sync.py）——不是三套各自獨立的 dispatcher，兩種 worker
在這裡是同一個「槽位」抽象底下的兩種實作，之後要加第三種運算來源
（例如另一個雲平台）只需要多寫一個 backend 轉接函式，不必再複製一份
迴圈。

**沿用 kaggle_queue.py 已經驗證過的東西，不重寫**：鎖檔案機制、
done-log 格式、槽位式併發（每個 worker 一個槽位，忙碌槽位每輪只查一次
不阻塞）都直接照抄那支腳本的做法（它是在真實踩過競態條件、卡死、
漏接結果之後才長成現在這樣，重新設計一套沒有理由）。Kaggle 專屬的
「dataset 掛載時序」重試（`BACKOFFS`／`is_mount_race_failure`）也是
直接呼叫 kaggle_queue.py 裡已經有的函式，不重複實作一份——這個失敗
模式是 Kaggle 容器架構特有的，SSH worker（持久機器，資料只傳一次）
不會遇到，所以只在 backend 是 "kaggle" 時才走這段。

**格式**（跟 kaggle_queue.txt 完全相同，故意的——這樣舊的
kaggle_queue.txt 內容可以直接搬過來用，不用重寫）：

    標籤|腳本.py|接在腳本後的參數|逗號分隔的額外依賴檔|minimal(true/false)|worker名稱(可留空)

worker 名稱可以是 `kaggle_accounts.json` 裡的帳號、也可以是
`ssh_workers.json` 裡的 SSH 節點——由 `load_all_workers()` 合併解析，
留空就交給任何有空的槽位。

**驗證狀態**：2026-08-23 已用 `kaggle_smoketest.py` 在真實 GCP VM
（e2-highcpu-8）上完整跑過一輪 push→run→status→pull，機制沒問題
（過程中發現的坑是 GCP 帳號隔離、不是這支程式的邏輯錯誤，見
`docs/reference/CLOUD_WORKERS.md`「已知陷阱」一節）。但這只驗證了
輕量腳本的路徑，**還沒有真正拿去跑過長時間的重運算**（`--procs 4`
以上、跑好幾小時的那種）——第一次派正式工作前，建議先觀察一次記憶體
用量（見 `CLOUD_WORKERS.md` 的 e2-highcpu-8 記憶體尖峰說明），不要
一開始就派滿載工作。

**集中式團隊派工（2026-08-23 新增）**：真實憑證（`kaggle_accounts.json`／
`ssh_workers.json`）只放在跑這支程式的機器上，不會、也不需要分給每個
隊員。隊員自己的機器完全不需要拿到任何 token 或 SSH 私鑰——只要對
`cloud_queue.txt` 開分支、加一行工作、開 PR、合併（照 `CONTRIBUTING.md`
的既有流程），這支程式**每一輪都會自動把 `cloud_queue.txt` 從
`origin/main` 同步下來**（`sync_queue_file()`），不用手動通知、也不用
重啟這支程式，下一輪（預設 60 秒內）就會撿到新工作開始派。反過來說，
**這台機器上的 `cloud_queue.txt` 不要手動編輯**——下一輪同步會被
`origin/main` 上的版本蓋掉，想加工作一律走 PR，維持「誰都可以查看
佇列在跑什麼、誰都不用碰真實憑證」這個集中式模式的核心好處。結果
下載下來後（`cloud_results/`／`kaggle_results/`）目前還是要靠操作這台
機器的人手動 commit 進 `results/`／`results/RESULTS_LOG.md` 才會讓
隊員看到——這步還沒自動化，是刻意的：自動 commit 未經檢查的結果，跟
這個專案「先確認方法沒有邏輯問題再產出最終數據」的原則衝突。

用法：
    python cloud_queue.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import gcp_vm_lifecycle
import kaggle_accounts
import kaggle_queue
import ssh_sync
import ssh_workers
from run_queue import _pid_alive

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "cloud_queue.txt"
DONE = HERE / "logs" / "cloud_queue_done.txt"
LOCK = HERE / "logs" / "cloud_queue.lock"
POLL_SECS = 60
MAX_WAIT_HOURS = 20
# 2026-08-24：ssh_sync.run() 送出啟動指令逾時（60 秒）時會回傳 True、
# 當作「可能已經啟動」建立 running 槽位（見 run() 的說明），但如果那次
# 其實根本沒送達（不是「送達但回應沒收到」），poll() 會一直回傳
# "missing"。原本這種槽位沿用 MAX_WAIT_HOURS（20 小時）才判定逾時釋放
# ——不是無限卡住，但 20 小時對一個從沒真的啟動過的工作太久，這段
# 期間這個 worker 完全派不了別的工作（CodeRabbit review 兩輪都指出
# 這一點，第一輪先記錄下來，這裡實際修掉）。獨立給「missing」一個短
# 很多的專屬逾時，跟「工作真的在跑、只是算很久」用的 MAX_WAIT_HOURS
# 分開——見主迴圈裡 `first_missing_at` 那段的用法。
MISSING_TIMEOUT_S = 900     # 15 分鐘，遠大於單次 poll 間隔（60 秒），
                            # 排除單次查詢時序差的誤判，同時遠短於
                            # MAX_WAIT_HOURS
# 填了 gcp_project/gcp_zone/gcp_instance 的 SSH worker，閒置（沒有槽位
# 在用）超過這個秒數就自動關機省免費額度，見
# maybe_stop_idle_ssh_workers() 跟 gcp_vm_lifecycle.py 開頭的說明。
# 15 分鐘：比單輪 POLL_SECS（60 秒）大很多倍，避免工作剛做完、下一個
# 工作還沒排進來的正常空檔就被誤判成閒置關機。
IDLE_STOP_SECS = 900
# 只用在 backend=="kaggle" 的槽位——理由見檔案開頭說明。
KAGGLE_BACKOFFS = [60, 120, 240, 480]


# ---------------------------------------------------------------- 鎖／佇列
# 跟 kaggle_queue.py 的 acquire_lock()/release_lock() 是同一套邏輯，
# 只是鎖檔案路徑不同（各自的佇列各自上鎖，兩支腳本可以同時跑，
# 只要不共用同一份佇列檔）。

def acquire_lock():
    LOCK.parent.mkdir(exist_ok=True)
    while True:
        try:
            fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                old_pid = int(LOCK.read_text().strip())
            except (ValueError, OSError):
                old_pid = None
            alive = _pid_alive(old_pid) if old_pid is not None else False
            if alive is None:
                print("無法確認鎖檔案是否還存活，保守起見當作還活著，退出。",
                     flush=True)
                sys.exit(1)
            if alive:
                print(f"偵測到另一個 cloud_queue.py 正在跑（PID {old_pid}），"
                     f"退出。", flush=True)
                sys.exit(1)
            print("鎖檔案殘留，清掉重新搶鎖。", flush=True)
            # 2026-08-22 CodeRabbit review 訂正：unlink 前重新讀一次鎖檔
            # 內容，跟剛才判定「PID 已死」時讀到的 old_pid 比對——如果這
            # 段時間裡內容已經變了（另一個行程也判定它殘留並剛重建、或
            # 真的有新行程搶到鎖），代表現在檔案裡的不是我們判定過的那個
            # 死掉的鎖，貿然 unlink 會刪掉別人剛建好的合法鎖（TOCTOU）。
            # 內容沒變才動手清掉，改變了就放棄這次清除、回圈重新走一輪
            # 判斷，不強行搶鎖。
            try:
                current = LOCK.read_text().strip()
            except (FileNotFoundError, OSError):
                current = None
            if current != str(old_pid):
                continue
            try:
                LOCK.unlink()
            except FileNotFoundError:
                pass
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return


def release_lock():
    try:
        if int(LOCK.read_text().strip()) == os.getpid():
            LOCK.unlink()
    except (FileNotFoundError, ValueError, OSError):
        pass


def sync_queue_file(branch: str = "main") -> None:
    """把 `cloud_queue.txt` 從 `origin/<branch>` 同步下來，讓隊員 PR
    合併進去的新工作不用重啟這支程式就會被撿到——集中式團隊派工模式
    的核心機制，見檔案開頭的說明。

    只同步這一個檔案（`git checkout origin/<branch> -- cloud_queue.txt`），
    不對整個工作目錄跑 `git pull`：這台機器可能正在用其他檔案（例如
    `kaggle_accounts.json`／`ssh_workers.json` 不進版控不受影響，但
    `pipeline/`／`config.toml` 這類已經被目前這個 process 讀進記憶體的
    模組，中途整包 pull 也不會讓已載入的程式碼重新生效，反而只會增加
    「跟本機其他未儲存修改衝突」的風險），只精確更新這一個檔案最單純、
    風險最小。

    刻意用 `git checkout origin/<branch> -- <file>` 而不是 `git pull`：
    這台機器上的 `cloud_queue.txt` 本來就不該有本機獨有的修改（見檔案
    開頭「不要手動編輯」的說明），直接用遠端版本蓋過去最單純，不需要
    處理合併衝突的情況。

    同步失敗（離線、git 帳號憑證過期等）只印警告、不中斷派工迴圈——
    沿用本機現有的佇列內容照常運作，只是暫時看不到新加的工作，等下次
    同步成功再撿到，不因為輔助功能失敗就讓派工整個停擺。
    """
    try:
        r = subprocess.run(["git", "fetch", "origin", branch],
                           cwd=str(HERE), capture_output=True, text=True,
                           timeout=30)
        if r.returncode != 0:
            print(f"  同步 {QUEUE.name} 失敗（git fetch：{r.stderr.strip()[:200]}），"
                 f"這輪沿用本機現有內容", flush=True)
            return
        r = subprocess.run(
            ["git", "checkout", f"origin/{branch}", "--", QUEUE.name],
            cwd=str(HERE), capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            print(f"  同步 {QUEUE.name} 失敗（git checkout："
                 f"{r.stderr.strip()[:200]}），這輪沿用本機現有內容",
                 flush=True)
    except subprocess.TimeoutExpired:
        print(f"  同步 {QUEUE.name} 逾時，這輪沿用本機現有內容", flush=True)


def read_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = (line.split("|") + [""] * 6)[:6]
        label, script, args, extra, minimal, worker = parts
        out.append({
            "label": label.strip(), "script": script.strip(),
            "args": args.strip(), "extra": extra.strip(),
            "minimal": minimal.strip().lower() in ("1", "true", "yes"),
            "worker": worker.strip() or None,
        })
    return out


def read_done() -> set[str]:
    """回傳「不用再排進 pending」的標籤集合。

    2026-08-24 修正：**`push_failed` 不算數，不永久噤聲**——實測踩到：
    這台機器（不是 worker）短暫網路中斷（DNS 解不到 github.com、SSH
    連不上 VM）時，`start_slot()` 的 `push()` 會失敗，被 `mark_done()`
    記成 `push_failed`。但這是「連工作都還沒真的開始」的建置階段失敗，
    不是工作本身跑錯——網路一恢復，同一個工作理論上就能正常跑，但原本
    這裡把任何狀態都當「已處理」永久排除，導致網路一恢復，`cloud_queue.py`
    也不會自動重試，卡在「佇列已清空」空等，直到有人發現才手動刪
    `logs/cloud_queue_done.txt` 裡那一行。跟 `run_queue.py` 的
    `read_done()` 排除 `stalled_giveup`／`preflight_fail`（環境性、
    建置階段失敗，不代表工作本身壞掉）是同一個理由、同一個修法——這裡
    當初沒照著做，是遺漏不是刻意簡化。`error`／`cancelled`／`timeout`
    這類「工作真的跑過、有明確失敗結果」的狀態維持原行為（不自動重試，
    避免真正壞掉的工作卡住佇列），只有 `push_failed` 排除在外。
    """
    if not DONE.exists():
        return set()
    out = set()
    for l in DONE.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        parts = l.split("\t")
        label = parts[0]
        status = parts[1] if len(parts) > 1 else ""
        if status == "push_failed":
            continue
        out.add(label)
    return out


def mark_done(label: str, status: str, secs: float, worker: str) -> None:
    DONE.parent.mkdir(exist_ok=True)
    with open(DONE, "a", encoding="utf-8") as f:
        f.write(f"{label}\t{status}\t{secs:.0f}s\t{worker}\t"
               f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")


# ---------------------------------------------------------------- workers

def load_all_workers() -> dict[str, str]:
    """回傳 {worker 名稱: "kaggle"|"ssh"}，兩個登記檔（kaggle_accounts.json、
    ssh_workers.json）合併解析。同一個名稱在兩邊都登記時直接報錯要求
    改名——silently 選一邊只會在之後派工到錯的 backend 時才發現，
    現在擋掉比之後除錯便宜。"""
    out: dict[str, str] = {}
    try:
        for name in kaggle_accounts.load_accounts():
            out[name] = "kaggle"
    except FileNotFoundError:
        pass    # 沒設定 Kaggle 帳號也沒關係，可能只用 SSH worker
    for name in ssh_workers.load_workers():
        if name in out:
            raise ValueError(
                f"worker 名稱 {name!r} 同時出現在 kaggle_accounts.json 跟 "
                f"ssh_workers.json，改一個名字避免混淆")
        out[name] = "ssh"
    return out


# ---------------------------------------------------------------- backend 轉接
# 三個函式是這支腳本唯一「知道 Kaggle 跟 SSH 不一樣」的地方，上面的
# 主迴圈往下都只看抽象的 status 字串，不分 backend。

def start_slot(name: str, kind: str, item: dict) -> tuple[bool, dict]:
    if kind == "kaggle":
        ok, kid, work_dir = kaggle_queue.push(item, name)
        return ok, {"kid": kid, "work_dir": work_dir}
    ok_push = ssh_sync.push(name)
    if not ok_push:
        return False, {}
    ok_run = ssh_sync.run(name, item["script"], item["args"], item["label"])
    return ok_run, {}


def probe_slot(name: str, kind: str, item: dict, slot: dict) -> str:
    """回傳 "running"／"complete"／"error"／"cancelled"／"missing"／"unknown"。"""
    if kind == "kaggle":
        accounts = kaggle_accounts.load_accounts()
        env = kaggle_accounts.env_for(accounts[name])
        return kaggle_queue.probe_kernel_status(slot["kid"], env)
    return ssh_sync.poll(name, item["label"])


def fetch_slot(name: str, kind: str, item: dict, slot: dict) -> bool:
    if kind == "kaggle":
        accounts = kaggle_accounts.load_accounts()
        env = kaggle_accounts.env_for(accounts[name])
        return kaggle_queue.pull(slot["kid"], item["label"], env)
    return ssh_sync.pull(name, item["label"])


def maybe_stop_idle_ssh_workers(workers: dict[str, str],
                                slots: dict[str, dict | None],
                                idle_since: dict[str, float]) -> None:
    """每輪主迴圈尾端呼叫一次。SSH worker 若填了 GCP 生命週期欄位（見
    gcp_vm_lifecycle.is_gcp_managed()），閒置（沒有槽位在用）超過
    IDLE_STOP_SECS 就自動關機省免費額度——理由見 gcp_vm_lifecycle.py
    開頭的說明。這裡只負責關機，開機由 ssh_sync.push() 派工前自動
    觸發（見 gcp_vm_lifecycle.ensure_running()），兩邊不重複判斷
    同一件事：這支函式完全不查「該不該開機」，只查「已經閒置多久」。

    `idle_since` 由呼叫端（main()）在 while True 迴圈外建立、每輪傳
    進來累積，不是這支函式自己的狀態——重啟 cloud_queue.py 會讓計時
    重新歸零，頂多讓某台 VM 多開一段時間，不影響正確性。
    """
    all_workers = ssh_workers.load_workers()
    for name, kind in workers.items():
        if kind != "ssh":
            continue
        w = all_workers.get(name)
        if not w or not gcp_vm_lifecycle.is_gcp_managed(w):
            continue
        if slots[name] is not None:
            idle_since.pop(name, None)
            continue
        started = idle_since.setdefault(name, time.time())
        if time.time() - started < IDLE_STOP_SECS:
            continue
        status = gcp_vm_lifecycle.describe_status(w)
        if status != "RUNNING":
            # 已經不是開著的狀態（自己關了、還在轉換中、查詢失敗）：
            # 不用再關一次，重設計時起點避免每輪都重查一次浪費
            # gcloud API 呼叫。
            idle_since[name] = time.time()
            continue
        if gcp_vm_lifecycle.stop_vm(w):
            idle_since[name] = time.time()


TERMINAL = {"complete", "error", "cancelled"}


def _kaggle_handle(name: str, item: dict) -> dict:
    """組出 Kaggle 槽位需要的 `kid`／`work_dir`，給正常路徑（
    `_probe_and_recover()`）跟例外 fallback 共用（2026-08-24 CodeRabbit
    review 訂正）——原本例外 fallback 手動組的槽位只有
    `{"phase":..., "item":..., "kind":...}`，沒有 `**handle`，
    `kind == "kaggle"` 時下一輪 `probe_slot()` 讀 `slot["kid"]`
    會直接 `KeyError`，而這個 `KeyError` 又被主迴圈自己新加的寬鬆
    `except Exception` 接住、槽位被保留——變成每一輪都重演同一個
    `KeyError`，直到 `MAX_WAIT_HOURS` 到期才被錯記成 `timeout`，這段
    期間這個 worker 完全派不了任何工作。不重複組裝邏輯，兩處呼叫這
    一份。"""
    accounts = kaggle_accounts.load_accounts()
    username = accounts[name]["username"]
    slug = item["label"].replace("_", "-")
    return {"kid": f"{username}/m45-imf-run-{slug}",
           "work_dir": HERE / "kaggle_work" / name}


def _probe_and_recover(name: str, kind: str, item: dict
                       ) -> tuple[dict | None, bool]:
    """查一次 `name` 這個 worker 上有沒有 `item['label']` 已經在跑／跑完
    的痕跡。回傳 `(slot, missing)`：

    - `slot` 是可以直接放進 `slots[name]` 的槽位 dict，或 `None`
      （代表這個 worker 目前空著，呼叫端可以放心當空槽處理）。
    - `missing` 只有在遠端**確實沒有任何這個 label 的痕跡**（探測結果
      是 "missing"）才是 `True`；其餘情況（不管是找到 slot、還是這支
      函式自己已經呼叫過 `mark_done()` 收尾）一律是 `False`。

    **為什麼要分開這兩個訊號（2026-08-24 CodeRabbit review 訂正）**：
    `complete`（已下載）跟終態 `error`／`cancelled` 這幾種情況，這支
    函式自己就已經呼叫 `mark_done()` 把正確的終態寫進 done-log 了，
    回傳的 `slot` 是 `None` 只是代表「沒有槽位要接手」，不是代表「什麼
    都沒查到」。如果呼叫端看到 `slot is None` 就一律再呼叫一次
    `mark_done(..., "push_failed", ...)`，會讓同一個 label 在
    `logs/cloud_queue_done.txt` 裡出現兩筆互相矛盾的紀錄（正確的終態
    +「push_failed」）——`read_done()` 只排除 `push_failed`，所以功能上
    不會真的重派，但稽核紀錄會誤導人。只有 `missing=True`（遠端真的什麼
    都沒有）才是呼叫端可以合理判斷「這次啟動大概沒送達」、自己決定要不
    要標記 `push_failed` 的時機。

    抽成獨立函式給兩個地方共用：(1) `recover_running_slots()` 開機時
    整批查一次；(2) 一般派工迴圈裡 `start_slot()` 失敗或拋例外之後，
    重派前先查一次——啟動失敗的結果其實不明：遠端可能已經收到指令、
    真的開始跑了，只是這裡沒收到確認回應（SSH 連線在指令送達之後、
    回應送回之前斷掉是典型情況）。原本只有復原路徑會做這個查證，一般
    派工失敗後直接讓下一輪重派，可能讓兩個行程搶同一個 worker 的同一份
    `remote_dir`（SSH）或重推同一個 kernel（Kaggle）——兩處分開各寫
    一份判斷邏輯，以後要改判斷準則（例如新增一種終止狀態）得記得兩邊
    都改，容易漏一邊，所以抽成一份。

    查詢本身失敗（`probe_kernel_status()`／`poll()` 回傳 "unknown"，
    或這支函式自己拋出未預期例外，見呼叫端的 try/except）保守當成
    「可能在跑」，回傳 `phase="probe"` 的槽位，不貿然當空、也不是
    `missing`。
    """
    if kind == "kaggle":
        handle = _kaggle_handle(name, item)
        accounts = kaggle_accounts.load_accounts()
        env = kaggle_accounts.env_for(accounts[name])
        st = kaggle_queue.probe_kernel_status(handle["kid"], env)
    else:
        st = ssh_sync.poll(name, item["label"])
        handle = {}
    if st == "missing":
        return None, True
    if st == "running":
        print(f"復原：{name} 已經在跑 {item['label']}，接回追蹤", flush=True)
        return {"phase": "running", "item": item, "kind": kind,
               **handle, "t0": time.time(), "retries": 0}, False
    if st == "unknown":
        print(f"復原：{name} 查 {item['label']} 狀態失敗，這一輪不派新"
             f"工作，下一輪再查（避免遠端其實正在跑卻被重派洗掉）",
             flush=True)
        return {"phase": "probe", "item": item, "kind": kind,
               **handle, "t0": time.time(), "retries": 0}, False
    if st == "complete":
        print(f"復原：{name} 的 {item['label']} 已經完成，補拉結果並"
             f"標記完成，不重算", flush=True)
        if fetch_slot(name, kind, item, handle):
            mark_done(item["label"], "ok", 0, name)
            return None, False
        # 2026-08-23 CodeRabbit review 訂正：結果下載失敗時原本直接
        # 放空槽位——遠端其實已經算完，放空槽位會讓主迴圈把這個 label
        # 當成新工作重派，等於把已經算完的計算結果丟掉重算一次。改成
        # 保留槽位（照抄主迴圈本來就有的同一套處置，見主迴圈裡
        # `status == "complete" and not pulled` 那段），下一輪
        # probe_slot 會再查到 complete，再重試 fetch_slot，只重試
        # 下載，不重跑計算。
        print("  結果下載失敗，保留槽位讓主迴圈下一輪重試下載"
             "（不重跑計算）", flush=True)
        return {"phase": "running", "item": item, "kind": kind,
               **handle, "t0": time.time(), "retries": 0}, False
    if (kind == "kaggle" and st == "error"
           and kaggle_queue.is_mount_race_failure(item["label"])):
        # 2026-08-23 CodeRabbit review 訂正：這裡原本跟下面的
        # error／cancelled 分支合在一起，一律記成終態失敗——但
        # Kaggle 的 dataset 掛載時序競態是已知的暫時性失敗（見
        # is_mount_race_failure() 的說明跟主迴圈裡 status=="error"
        # 那段一樣的處置），本機重啟後接回一個剛好卡在 mount race
        # 的槽位不該直接判死刑，要走跟主迴圈相同的 cooldown 重試
        # 流程，不能因為「這次是在復原路徑上發現的」就少了重試
        # 機會。SSH 沒有這種已知可重試的暫時性失敗模式，所以這段
        # 只在 kind=="kaggle" 時才會進來，SSH 的 error 繼續走下面
        # 的終態失敗處置。
        wait_s = KAGGLE_BACKOFFS[0]
        print(f"復原：{name} 的 {item['label']} 遠端狀態為 error，但偵測到"
             f"dataset 掛載時序問題（非程式錯誤），{wait_s}s 後重推"
             f"（第 1 次重試），不記成終態失敗", flush=True)
        return {"phase": "cooldown", "item": item, "kind": kind,
               **handle, "t0": time.time(), "retries": 1,
               "resume_at": time.time() + wait_s}, False
    # error／cancelled（SSH 的錯誤，或非 mount race 的 kaggle 錯誤）：
    # 記成終態失敗，不自動重派。
    print(f"復原：{name} 的 {item['label']} 遠端狀態為 {st}，記成終態"
         f"失敗，不自動重派", flush=True)
    mark_done(item["label"], st, 0, name)
    return None, False


def recover_running_slots(workers: dict[str, str]) -> dict[str, dict | None]:
    """開機／重啟時接回還在跑的槽位，理由跟 kaggle_queue.py 的同名函式
    完全一樣（本機失聯不代表遠端沒在跑，見那邊 2026-08-18 的說明）。
    判斷邏輯本體在 `_probe_and_recover()`，這裡只負責挑出「哪些 worker
    該查哪個 pending 項目」。

    2026-08-24 CodeRabbit review 訂正：整個函式原本沒有例外保護——
    `kaggle_queue.probe_kernel_status()`／`ssh_sync.poll()`／
    `fetch_slot()` 底下都有 subprocess 呼叫，不是每一個都接住所有可能
    的例外（`ssh_sync.poll()` 只接 `subprocess.TimeoutExpired`），這支
    函式又是在 `main()` 的 `while True:` 主迴圈**開始之前**呼叫一次，
    未捕捉例外會讓 cloud_queue.py 連主迴圈都還沒進去就整支程式當場
    結束——比主迴圈裡的問題更嚴重，因為主迴圈自己那層 try/except 兜底
    完全幫不上忙（還沒執行到那裡）。查詢單一 (name, item) 時發生未預期
    例外，保守當成「查不到、可能在跑」（`phase="probe"`），不讓一個
    worker 的復原查詢失敗拖垮其他 worker 的復原、或讓整支程式起不來。
    """
    done = read_done()
    pending = [it for it in read_queue() if it["label"] not in done]
    slots: dict[str, dict | None] = {name: None for name in workers}
    for name, kind in workers.items():
        for item in pending:
            if item["worker"] not in (None, name):
                continue
            try:
                slot, _missing = _probe_and_recover(name, kind, item)
            except Exception as e:                            # noqa: BLE001
                print(f"復原：查 {name} 的 {item['label']} 狀態時發生未"
                     f"預期例外（{type(e).__name__}: {e}），保守當成"
                     f"可能在跑，下一輪重試", flush=True)
                traceback.print_exc()
                # 2026-08-24 CodeRabbit review 訂正：fallback 槽位一定要
                # 帶齊 kind=="kaggle" 需要的 kid／work_dir，理由見
                # _kaggle_handle() 的說明——這裡再包一層 try 是因為連
                # _kaggle_handle() 本身（讀 kaggle_accounts.json）都有
                # 可能失敗，不能讓「補 handle」這個動作本身變成第二個
                # 沒接住的例外，寧可 handle 缺失也不要讓這層 except 自己
                # 再炸一次。
                handle = {}
                if kind == "kaggle":
                    try:
                        handle = _kaggle_handle(name, item)
                    except Exception:                          # noqa: BLE001
                        pass
                slot = {"phase": "probe", "item": item, "kind": kind,
                       **handle, "t0": time.time(), "retries": 0}
            if slot is not None:
                slots[name] = slot
                break
    return slots


def main() -> None:
    acquire_lock()
    import atexit
    atexit.register(release_lock)

    workers = load_all_workers()
    if not workers:
        print("kaggle_accounts.json 跟 ssh_workers.json 都沒有設定任何 "
             "worker，沒有東西可以派工，結束。", flush=True)
        return
    print(f"雲端佇列執行器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}，"
         f"{len(workers)} 個 worker：{ {n: k for n, k in workers.items()} }",
         flush=True)

    slots = recover_running_slots(workers)
    if any(slots.values()):
        running = [n for n, s in slots.items() if s]
        print(f"復原完成，接回 {len(running)} 個已在跑的槽位：{running}",
             flush=True)

    # 見 maybe_stop_idle_ssh_workers() 的說明：只追蹤填了 GCP 生命週期
    # 欄位的 worker 各自「連續閒置從什麼時候開始」，重啟這支程式會歸零，
    # 不影響正確性。
    idle_since: dict[str, float] = {}

    while True:
        sync_queue_file()
        done = read_done()
        pending = [it for it in read_queue() if it["label"] not in done
                  and it["label"] not in
                  {s["item"]["label"] for s in slots.values() if s}]

        for name, kind in workers.items():
            if slots[name] is not None:
                continue
            idx = next((i for i, it in enumerate(pending)
                       if it["worker"] in (None, name)), None)
            if idx is None:
                continue
            item = pending.pop(idx)
            print(f"\n{'='*70}\n[{datetime.now():%H:%M:%S}] "
                 f"{name}（{kind}）開始 {item['label']}"
                 f"\n  {item['script']} {item['args']}\n{'='*70}", flush=True)
            # 2026-08-24：start_slot() 底下（ssh_sync.py／kaggle_sync.py）有
            # 好幾個 subprocess 呼叫沒有全部接住 subprocess.TimeoutExpired，
            # 網路短暫變慢／中斷時可能整個未捕捉例外往上炸——原本這裡沒接，
            # 一炸就是整支 cloud_queue.py 的 while True 主迴圈死掉，所有
            # worker（不只是剛好network有狀況的那個）全部停擺，需要人工
            # 發現才重啟。改成這裡兜底：任何未預期例外都當成「這個 worker
            # 這一輪失敗，下一輪的 pending 重新算過會再排進去」處理，不讓
            # 一個 worker 的暫時性問題波及其他 worker 或整個派工器。
            try:
                ok, handle = start_slot(name, kind, item)
            except Exception as e:                            # noqa: BLE001
                # 2026-08-24 CodeRabbit review 訂正：這裡接的是 Exception
                # 這麼寬的範圍，不會只有網路逾時，也會接住 KeyError／
                # TypeError 這類程式邏輯錯誤——那種錯誤每一輪都會重演，
                # 只印型別跟訊息、沒有發生位置的話，得另外重現才查得出
                # 是哪一行。印出完整 traceback 讓下次直接定位。
                print(f"  [{name}] 啟動 {item['label']} 時發生未預期例外"
                     f"（{type(e).__name__}: {e}）", flush=True)
                traceback.print_exc()
                ok, handle = False, {}
            if ok:
                slots[name] = {"phase": "running", "item": item, "kind": kind,
                              **handle, "t0": time.time(), "retries": 0}
                continue
            # 2026-08-24 CodeRabbit review 訂正：啟動失敗（不論是乾淨
            # 回傳 False，還是丟例外）的結果其實不明——遠端可能已經收到
            # 指令、真的開始跑了，只是這裡沒收到確認回應（SSH 連線在
            # 指令送達之後、回應送回之前斷掉是典型情況）。原本這裡不管
            # 三七二十一直接標記 push_failed，下一輪就會重派同一個
            # label，可能讓兩個行程搶同一個 worker 的同一份 remote_dir
            # （SSH）或重推同一個 kernel（Kaggle）。重派前先用
            # `_probe_and_recover()`（跟開機復原共用同一套判斷邏輯）
            # 實際查一次遠端狀態，查到真的在跑就接回追蹤，不是假設
            # 沒事而重派。
            try:
                recovered, missing = _probe_and_recover(name, kind, item)
            except Exception as e2:                           # noqa: BLE001
                print(f"  [{name}] 查詢 {item['label']} 是否已啟動時也"
                     f"發生未預期例外（{type(e2).__name__}: {e2}），保守"
                     f"當成可能在跑，下一輪重試", flush=True)
                traceback.print_exc()
                # 理由同 recover_running_slots() 的同類 fallback：帶齊
                # kind=="kaggle" 需要的 kid／work_dir，見 _kaggle_handle()。
                fallback_handle = {}
                if kind == "kaggle":
                    try:
                        fallback_handle = _kaggle_handle(name, item)
                    except Exception:                          # noqa: BLE001
                        pass
                recovered = {"phase": "probe", "item": item, "kind": kind,
                            **fallback_handle, "t0": time.time(),
                            "retries": 0}
                # 查證本身都失敗了，不確定遠端到底有沒有，保守起見不當
                # 「確定沒有」處理——見下面 missing 的用法。
                missing = False
            if recovered is not None:
                slots[name] = recovered
                print(f"  [{name}] {item['label']} 啟動回報失敗，但查到"
                     f"遠端其實已經在跑，接回追蹤而不是重派", flush=True)
            elif missing:
                # 2026-08-24 CodeRabbit review 訂正：只有 _probe_and_recover()
                # 明確回報「遠端真的什麼都沒有」（missing=True）才在這裡標記
                # push_failed。`recovered is None` 也可能是因為那支函式自己
                # 已經呼叫過 mark_done()（complete 已下載、或 error／cancelled
                # 終態）——那種情況下如果這裡又標一次 push_failed，會讓同一個
                # label 在 done-log 裡出現兩筆互相矛盾的紀錄（正確終態 +
                # push_failed），誤導事後查證，即使功能上不影響重派判斷
                # （read_done() 只排除 push_failed）。
                mark_done(item["label"], "push_failed", 0, name)

        for name, slot in list(slots.items()):
            if slot is None:
                continue
            kind = slot["kind"]
            item = slot["item"]
            # 2026-08-24：這整段（cooldown／逾時判斷／probe_slot()／
            # mount race 重試／fetch_slot()）底下的 subprocess 呼叫不是
            # 每一個都接住 subprocess.TimeoutExpired，網路短暫異常時
            # 未捕捉例外會讓整支程式的 while True 主迴圈死掉，所有槽位
            # （包含其他正常的 worker）一起停擺，需要人工發現才重啟——
            # 跟上面「啟動新工作」那段是同一個理由。整段包一層 try，
            # 例外時保留槽位（不清空、不 mark_done）當這一輪「查不到
            # 狀態」處理，跟 probe_slot() 正常回傳 "unknown" 時的既有
            # 處置一致，下一輪自然會再檢查一次，不會遺失正在追蹤的工作。
            # 段落內部原有的 continue 在 try 區塊裡語意不變（continue／
            # break 不受 try/except 影響，仍然作用在最外層的 for 迴圈），
            # 不需要另外抽成函式。
            try:
                if slot["phase"] == "cooldown":  # 只有 kaggle 槽位會進到這裡
                    if time.time() >= slot["resume_at"]:
                        ok = kaggle_queue.push_kernel_only(
                            slot["work_dir"],
                            kaggle_accounts.env_for(
                                kaggle_accounts.load_accounts()[name]))
                        if ok:
                            slot["phase"] = "running"
                        else:
                            mark_done(item["label"], "error",
                                     time.time() - slot["t0"], name)
                            slots[name] = None
                    continue

                elapsed_h = (time.time() - slot["t0"]) / 3600
                if elapsed_h > MAX_WAIT_HOURS:
                    if kind == "ssh":
                        # SSH worker 是持久機器，逾時不能直接放槽位——遠端的
                        # 行程可能還真的在跑，放了槽位讓主迴圈重派，會在同一個
                        # remote_dir 裡跟舊行程搶同一批 logs／results 檔案
                        # （2026-08-22 CodeRabbit review 訂正）。先用 PID 確認
                        # 終止，確認不了就保留槽位、不重派，等人工介入——這跟
                        # Kaggle 不一樣：kernel 是平台自己管的容器，本機沒有
                        # 能力也不需要去「殺」它，逾時單純是本機端放棄追蹤。
                        if not ssh_sync.kill(name, item["label"]):
                            print(f"  [{name}] {item['label']} 逾時但無法確認"
                                 f"遠端行程已終止，保留槽位、不重派，需要人工"
                                 f"介入檢查 worker 上 logs/{item['label']}.pid "
                                 f"對應的行程", flush=True)
                            continue    # 保留槽位，下一輪再試一次終止
                    mark_done(item["label"], "timeout",
                             time.time() - slot["t0"], name)
                    slots[name] = None
                    continue

                status = probe_slot(name, kind, item, slot)
                if status != "missing":
                    # 曾經連續 missing 過、現在變別的狀態了（真的查到
                    # running／terminal），代表那次 missing 只是時序上
                    # 剛好沒同步到，不是真的沒啟動——清掉計時基準，不然
                    # 下次萬一又短暫 missing 會沿用舊的起算時間，提早
                    # 誤判。
                    slot.pop("first_missing_at", None)
                if status == "missing":
                    # 用獨立、短很多的逾時判斷「這個工作是不是根本沒
                    # 送達」，不要沿用給「工作真的在跑、只是算很久」用
                    # 的 MAX_WAIT_HOURS（20 小時）——理由見
                    # MISSING_TIMEOUT_S 旁邊的說明。
                    first_missing = slot.setdefault("first_missing_at",
                                                     time.time())
                    if time.time() - first_missing > MISSING_TIMEOUT_S:
                        print(f"  [{name}] {item['label']} 連續 "
                             f"{MISSING_TIMEOUT_S // 60} 分鐘查不到遠端有"
                             f"這個工作的痕跡，判定啟動指令其實沒送達，"
                             f"釋放槽位讓下一輪重派", flush=True)
                        mark_done(item["label"], "push_failed",
                                 time.time() - slot["t0"], name)
                        slots[name] = None
                    continue
                if status not in TERMINAL:
                    continue    # running／unknown：下一輪再看

                if (kind == "kaggle" and status == "error"
                       and kaggle_queue.is_mount_race_failure(item["label"])
                       and slot["retries"] < len(KAGGLE_BACKOFFS)):
                    wait_s = KAGGLE_BACKOFFS[slot["retries"]]
                    slot["retries"] += 1
                    slot["phase"] = "cooldown"
                    slot["resume_at"] = time.time() + wait_s
                    print(f"  [{name}] 偵測到 dataset 掛載時序問題，{wait_s}s "
                         f"後重推（第 {slot['retries']} 次重試）", flush=True)
                    continue

                pulled = fetch_slot(name, kind, item, slot)
                if status == "complete" and not pulled:
                    print(f"  [{name}] {item['label']} 已完成但結果下載失敗，"
                         f"保留供下一輪重試", flush=True)
                    continue
                secs = time.time() - slot["t0"]
                final = "ok" if status == "complete" else status
                mark_done(item["label"], final, secs, name)
                print(f"[{datetime.now():%H:%M:%S}] [{name}] {item['label']} "
                     f"結束：{final}（{secs/60:.1f} 分）\n", flush=True)
                slots[name] = None
            except Exception as e:                            # noqa: BLE001
                # 理由同上面「啟動新工作」那段的 2026-08-24 訂正。
                print(f"  [{name}] 檢查 {item['label']} 狀態時發生未預期例外"
                     f"（{type(e).__name__}: {e}），保留槽位，下一輪重試",
                     flush=True)
                traceback.print_exc()

        if not pending and all(s is None for s in slots.values()):
            # **不像 kaggle_queue.py 那樣「清空就結束」**（2026-08-23 為
            # 集中式團隊派工模式改的）：隊員隨時可能開 PR 把新工作合併進
            # `cloud_queue.txt`，如果這支程式因為「暫時沒事做」就結束，
            # 之後合併的工作不會有人接，等於要有人一直手動盯著重啟——
            # 違背「隊員不用碰真實憑證也能自由調度」的目標。繼續等待，
            # 靠 sync_queue_file() 下一輪自動撿新工作；真的要停這支程式
            # 用 Ctrl+C。
            print("佇列目前空了，繼續常駐等待新工作（Ctrl+C 結束）。",
                 flush=True)
        # 2026-08-26 CodeRabbit review 訂正：這支函式底下的 gcloud 呼叫
        # 在主迴圈其餘部分的 try/except 保護範圍之外，任何未預期例外
        # （例如環境設定問題、gcloud 輸出格式意外改變）會直接讓整支
        # while True 主迴圈死掉，波及所有 worker（不只是自動開關機
        # 這個功能本身）——理由跟主迴圈其他段落的同類兜底完全一樣。
        try:
            maybe_stop_idle_ssh_workers(workers, slots, idle_since)
        except Exception as e:                            # noqa: BLE001
            print(f"  檢查閒置 VM 是否該關機時發生未預期例外"
                 f"（{type(e).__name__}: {e}），這一輪跳過，下一輪重試",
                 flush=True)
            traceback.print_exc()
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
