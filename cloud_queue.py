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

**這是 v1**：SSH 這條路徑還沒有被真實運算工作驗證過（`ssh_workers.json`
填好、confirmed 能連上之前，這支程式邏輯上完整但沒有實測過完整一輪
push→run→poll→pull），第一次真的拿去跑重運算時建議先用一個小型
smoke-test 腳本走一輪確認，不要直接派正式工作上去（跟當初
kaggle_smoketest.py 的用法一樣）。

用法：
    python cloud_queue.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
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
    if not DONE.exists():
        return set()
    return {l.split("\t")[0] for l in
            DONE.read_text(encoding="utf-8").splitlines() if l.strip()}


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
                else:
                    print(f"  結果下載失敗，不標記完成——留給下一輪重試",
                         flush=True)
                continue    # 槽位保持空著，可以接新工作
            # error／cancelled：記成終態失敗，不自動重派。
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
            ok, handle = start_slot(name, kind, item)
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

            if slot["phase"] == "cooldown":     # 只有 kaggle 槽位會進到這裡
                if time.time() >= slot["resume_at"]:
                    ok = kaggle_queue.push_kernel_only(
                        slot["work_dir"],
                        kaggle_accounts.env_for(kaggle_accounts.load_accounts()[name]))
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
                mark_done(item["label"], "timeout", time.time() - slot["t0"],
                         name)
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

        if not pending and all(s is None for s in slots.values()):
            print("雲端佇列已清空，結束。", flush=True)
            return
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
