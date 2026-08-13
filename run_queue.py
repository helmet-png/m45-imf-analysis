# -*- coding: utf-8 -*-
"""依序執行 queue.txt 裡的工作，一次一個，不搶核心。

**為什麼需要它**：這幾項工作要跑好幾小時，而且必須循序執行 ——
同時跑兩個八行程的工作會互搶核心，總時間不會變短反而更長。

**可追加**：每跑完一步就**重新讀取** queue.txt，所以工作進行中仍可把新步驟
附加到檔案末端（例如某一步的程式還沒寫完時，先讓前面的跑起來）。

**容錯**：某一步失敗不會中斷整條佇列 —— 記下錯誤、繼續下一步。
無人看顧時中途停住的代價比跑錯一步大。

queue.txt 格式，每行一個工作：

    標籤|要執行的參數（會接在 python 之後）

以 # 開頭的行與空行忽略。已完成的標籤記在 logs/queue_done.txt，
所以重新啟動這支程式不會重跑已完成的步驟。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "queue.txt"
DONE = HERE / "logs" / "queue_done.txt"
LOCK = HERE / "logs" / "run_queue.lock"


def _pid_alive(pid: int) -> bool:
    """Windows 沒有 POSIX 的 os.kill(pid, 0) 探測語意 —— 傳 0 給
    os.kill() 在 Windows 上會呼叫 TerminateProcess(handle, 0)，也就是
    真的把行程殺掉，不是安全的存活探測。改用 tasklist 查詢，不會動到
    目標行程。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
            text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
        return str(pid) in out.stdout
    except Exception:                                 # noqa: BLE001
        return False


def acquire_lock():
    """單例鎖，避免兩個 run_queue.py 同時搶佇列（2026-08-13，CodeRabbit
    review 指出 restart_queue_on_boot.ps1 的「先查行程再啟動」不是原子
    操作，兩個觸發可能都通過檢查、各自啟動一個 runner，同時執行到同一個
    尚未 mark_done() 的 pending 項目）。PowerShell 那邊的檢查留著當快速
    路徑，但真正的防重複要在這裡做——這是唯一每次真正要動佇列的入口。

    用 PID 檔案而非 OS 級 mutex：這個專案只在 Windows 上跑，不需要
    pywin32 這種額外依賴，PID 檔案配合 tasklist 探測就夠用，且容易讀懂。
    """
    LOCK.parent.mkdir(exist_ok=True)
    if LOCK.exists():
        try:
            old_pid = int(LOCK.read_text().strip())
        except ValueError:
            old_pid = None
        if old_pid is not None and _pid_alive(old_pid):
            print(f"偵測到另一個 run_queue.py 正在跑（PID {old_pid}），"
                  f"退出，不搶佇列。", flush=True)
            sys.exit(1)
        print(f"鎖檔案殘留（PID {old_pid} 已不存在，視為上次沒清乾淨），"
              f"視為沒有鎖，繼續。", flush=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")


def read_queue():
    if not QUEUE.exists():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        label, cmd = line.split("|", 1)
        out.append((label.strip(), cmd.strip()))
    return out


def read_done():
    if not DONE.exists():
        return set()
    return {l.split("\t")[0] for l in
            DONE.read_text(encoding="utf-8").splitlines() if l.strip()}


def mark_done(label, status, secs):
    DONE.parent.mkdir(exist_ok=True)
    with open(DONE, "a", encoding="utf-8") as f:
        f.write(f"{label}\t{status}\t{secs:.0f}s\t"
                f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")


def main():
    acquire_lock()
    print(f"佇列執行器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    while True:
        done = read_done()
        pending = [(l, c) for l, c in read_queue() if l not in done]
        if not pending:
            print("佇列已清空，結束。", flush=True)
            return
        label, cmd = pending[0]
        log = HERE / "logs" / f"{label}.log"
        print(f"\n{'='*70}\n[{datetime.now():%H:%M:%S}] 開始 {label}\n"
              f"  python {cmd}\n  輸出 -> {log.name}\n{'='*70}", flush=True)
        t0 = time.time()
        try:
            with open(log, "w", encoding="utf-8") as fh:
                p = subprocess.run([sys.executable, "-u"] + cmd.split(),
                                   cwd=str(HERE), stdout=fh,
                                   stderr=subprocess.STDOUT)
            status = "ok" if p.returncode == 0 else f"exit{p.returncode}"
        except Exception as e:                      # noqa: BLE001
            status = f"error:{type(e).__name__}"
            print(f"  例外：{e}", flush=True)
        secs = time.time() - t0
        mark_done(label, status, secs)
        print(f"[{datetime.now():%H:%M:%S}] {label} 結束：{status}"
              f"（{secs/60:.1f} 分）", flush=True)


if __name__ == "__main__":
    main()
