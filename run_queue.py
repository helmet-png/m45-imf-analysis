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

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "queue.txt"
DONE = HERE / "logs" / "queue_done.txt"


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
