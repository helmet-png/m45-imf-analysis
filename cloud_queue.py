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


TERMINAL = {"complete", "error", "cancelled"}


def recover_running_slots(workers: dict[str, str]) -> dict[str, dict | None]:
    """開機／重啟時接回還在跑的槽位，理由跟 kaggle_queue.py 的同名函式
    完全一樣（本機失聯不代表遠端沒在跑，見那邊 2026-08-18 的說明）。

    2026-08-22 CodeRabbit review 訂正：原本只認 RUNNING 就接回，其餘
    （complete／error／cancelled／unknown）一律當空槽位讓主迴圈自然
    重派。這對 **complete** 等於把已經算完的結果丟掉重算——跟這個專案
    在 Kaggle 那邊已經踩過、也已經在 `kaggle_queue.py` 的同名函式修過
    的同一種「重複算力」bug，這裡當初沒有照著做，是遺漏不是刻意簡化。
    對 **unknown**（查不到狀態，可能只是網路斷或連線逾時，不代表遠端
    真的沒在跑）一律當空槽位重派，則可能讓兩個行程同時在同一個 worker
    的同一個 remote_dir 裡搶同一個 label 的 logs／results 檔案——這是
    SSH worker（持久機器、無容器隔離）特有的風險，比 Kaggle 只是「白算
    一次」更嚴重。

    改成比照 kaggle_queue.py 的處置：complete 就 pull＋mark_done（不
    重算）；error／cancelled 記成終態失敗（不自動重派——SSH 沒有 Kaggle
    那種已知可重試的 mount race 暫時性失敗模式，保守起見交給人工判斷要
    不要重新排進佇列）；unknown 保留槽位（phase="probe"）讓主迴圈下一輪
    繼續查，這一輪不派新工作。
    """
    done = read_done()
    pending = [it for it in read_queue() if it["label"] not in done]
    slots: dict[str, dict | None] = {name: None for name in workers}
    for name, kind in workers.items():
        for item in pending:
            if item["worker"] not in (None, name):
                continue
            if kind == "kaggle":
                accounts = kaggle_accounts.load_accounts()
                username = accounts[name]["username"]
                slug = item["label"].replace("_", "-")
                kid = f"{username}/m45-imf-run-{slug}"
                env = kaggle_accounts.env_for(accounts[name])
                st = kaggle_queue.probe_kernel_status(kid, env)
                handle = {"kid": kid, "work_dir": HERE / "kaggle_work" / name}
            else:
                st = ssh_sync.poll(name, item["label"])
                handle = {}
            if st == "missing":
                continue    # 這個 worker 沒推過這項，看下一個候選
            if st == "running":
                slots[name] = {"phase": "running", "item": item, "kind": kind,
                               **handle, "t0": time.time(), "retries": 0}
                print(f"復原：{name} 已經在跑 {item['label']}，接回追蹤",
                     flush=True)
                break
            if st == "unknown":
                slots[name] = {"phase": "probe", "item": item, "kind": kind,
                               **handle, "t0": time.time(), "retries": 0}
                print(f"復原：{name} 查 {item['label']} 狀態失敗，這一輪不"
                     f"派新工作，下一輪再查（避免遠端其實正在跑卻被重派"
                     f"洗掉）", flush=True)
                break
            if st == "complete":
                print(f"復原：{name} 的 {item['label']} 在本機失聯期間已經"
                     f"完成，補拉結果並標記完成，不重算", flush=True)
                if fetch_slot(name, kind, item, handle):
                    mark_done(item["label"], "ok", 0, name)
                    continue    # 槽位保持空著，可以接新工作
                # 2026-08-23 CodeRabbit review 訂正：結果下載失敗時原本
                # 直接 continue 放空槽位——遠端其實已經算完，放空槽位會讓
                # 主迴圈把這個 label 當成新工作重派，等於把已經算完的
                # 計算結果丟掉重算一次。改成保留槽位（照抄主迴圈本來就有
                # 的同一套處置，見下面 while 迴圈裡 `status == "complete"
                # and not pulled` 那段），下一輪 probe_slot 會再查到
                # complete，再重試 fetch_slot，只重試下載，不重跑計算。
                print(f"  結果下載失敗，保留槽位讓主迴圈下一輪重試下載"
                     f"（不重跑計算）", flush=True)
                slots[name] = {"phase": "running", "item": item, "kind": kind,
                               **handle, "t0": time.time(), "retries": 0}
                break
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
                slots[name] = {"phase": "cooldown", "item": item, "kind": kind,
                               **handle, "t0": time.time(), "retries": 1,
                               "resume_at": time.time() + wait_s}
                print(f"復原：{name} 的 {item['label']} 遠端狀態為 error，"
                     f"但偵測到 dataset 掛載時序問題（非程式錯誤），{wait_s}s "
                     f"後重推（第 1 次重試），不記成終態失敗", flush=True)
                break
            # error／cancelled（SSH 的錯誤，或非 mount race 的 kaggle 錯誤）：
            # 記成終態失敗，不自動重派。
            print(f"復原：{name} 的 {item['label']} 遠端狀態為 {st}，記成"
                 f"終態失敗，不自動重派", flush=True)
            mark_done(item["label"], st, 0, name)
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
                     f"（{type(e).__name__}: {e}），不標記完成，下一輪"
                     f"重新嘗試派工", flush=True)
                traceback.print_exc()
                continue
            if ok:
                slots[name] = {"phase": "running", "item": item, "kind": kind,
                              **handle, "t0": time.time(), "retries": 0}
            else:
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
                if status not in TERMINAL:
                    continue    # running/missing/unknown：下一輪再看

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
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
