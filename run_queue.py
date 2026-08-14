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

import ctypes
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

# 這台機器是 ARM64 Snapdragon X，只支援「待命 (S0 低電源閒置)」（Modern
# Standby），沒有傳統的 S1-S3。實測：`powercfg /a` 確認、`powercfg /query`
# 也確認 STANDBYIDLE（睡眠啟動時間）在接電時已經是 0（永不睡眠）、
# 處理器最高狀態已經是 100%——但螢幕關掉、使用者判定為「離開」後，
# Modern Standby 仍會另外把背景行程當成閒置對待，這一層節流**不是**由
# 睡眠計時器控制，關掉睡眠計時器擋不住它。
#
# Windows 官方解法是讓真正在算的行程自己呼叫 SetThreadExecutionState
# 主動宣告「我在做事，別把我當閒置」——ES_SYSTEM_REQUIRED 告訴系統
# 不要因為閒置而降頻/節流這個行程，ES_AWAYMODE_REQUIRED 明確允許螢幕
# 依原本的逾時設定關掉、使用者可以照常判定為離開，但把運算維持在
# 「有人在用」的滿速狀態——這正是這支腳本要的：只有它在跑的時候才
# 撐住滿速，其他時間（腳本沒在跑、或這個 process 結束）系統照舊省電，
# 不需要改全域電源設定去換（改全域設定的代價是沒在跑東西時也一直
# 滿速，浪費電）。旗標帶 ES_CONTINUOUS 讓狀態持續生效，不用每隔幾秒
# 重新宣告一次。
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def keep_system_awake():
    """要求系統別把這個行程當閒置節流，螢幕仍可正常關閉。失敗（例如
    非 Windows 環境，或這台機器的 OEM 電源管理不接受 AWAYMODE 旗標）
    只印警告，不中斷佇列——保持滿速是最佳化，不是佇列能不能跑的前提。"""
    try:
        prev = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
        if not prev:
            print("警告：SetThreadExecutionState 呼叫失敗（回傳 0），"
                  "螢幕關閉後可能還是會被節流。", flush=True)
    except (AttributeError, OSError) as e:
        print(f"警告：無法呼叫 SetThreadExecutionState（{e}），"
              f"螢幕關閉後可能還是會被節流。", flush=True)


def release_system_awake():
    """佇列跑完就把狀態還原成一般——不要讓「保持滿速」這件事在腳本
    結束後還繼續生效，其餘時間系統該怎麼省電就怎麼省電。行程真的
    結束時 Windows 本來就會自動清掉這個宣告，這裡顯式做一次只是
    避免依賴「process 終止時機」這種隱性行為，讓 finally 區塊自己
    講清楚在做什麼。"""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    except (AttributeError, OSError):
        pass


def _pid_alive(pid: int) -> bool | None:
    """回傳 True/False/None —— None 代表探測本身失敗（tasklist 逾時、
    找不到指令等），不能當成 False。

    Windows 沒有 POSIX 的 os.kill(pid, 0) 探測語意 —— 傳 0 給 os.kill()
    在 Windows 上會呼叫 TerminateProcess(handle, 0)，也就是真的把行程
    殺掉，不是安全的存活探測。改用 tasklist 查詢，不會動到目標行程。
    引數是 list 形式（不是 shell=True 的字串），pid 這裡永遠是
    int(LOCK.read_text()) 解析出來的整數，不存在 shell injection 的
    問題——自動掃描工具的 CWE-78 標記是這個模式的通用誤判，不是真的
    有可控字串被組進 shell 命令。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True,
            text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:                                 # noqa: BLE001
        return None
    if out.returncode != 0:
        return None
    return str(pid) in out.stdout


def acquire_lock():
    """單例鎖，避免兩個 run_queue.py 同時搶佇列（2026-08-13，CodeRabbit
    review 指出 restart_queue_on_boot.ps1 的「先查行程再啟動」不是原子
    操作，兩個觸發可能都通過檢查、各自啟動一個 runner，同時執行到同一個
    尚未 mark_done() 的 pending 項目）。PowerShell 那邊的檢查留著當快速
    路徑，但真正的防重複要在這裡做——這是唯一每次真正要動佇列的入口。

    用 PID 檔案而非 OS 級 mutex：這個專案只在 Windows 上跑，不需要
    pywin32 這種額外依賴，PID 檔案配合 tasklist 探測就夠用，且容易讀懂。

    **2026-08-13 第二輪 CodeRabbit review 修正**：第一版是「檢查檔案
    存不存在 -> 寫入」兩步，兩者之間仍有競態窗口（兩個行程都在檢查後
    才寫入，會都以為自己拿到鎖）。改用 os.open(..., O_CREAT | O_EXCL)
    讓「檔案不存在就建立」這件事本身變成單一原子系統呼叫——如果檔案
    已存在，open() 本身就會丟 FileExistsError，不會有中間窗口。
    另外，_pid_alive() 探測失敗時（回傳 None）不能當成「死掉了」處理
    ——原本的寫法在探測失敗時預設 False，等於把「不知道」誤判成
    「安全」，這正是 CodeRabbit 指出的 fail-open 風險。現在探測失敗一律
    fail closed：不確定就當作可能還活著，退出不動佇列，寧可誤判成
    「還在跑」而暫停一次，也不要誤判成「沒在跑」而跑出兩個 runner。
    """
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
                print(f"無法確認鎖檔案（PID {old_pid}）是否還存活"
                      f"（tasklist 探測失敗），保守起見當作還活著，"
                      f"退出，不搶佇列。", flush=True)
                sys.exit(1)
            if alive:
                print(f"偵測到另一個 run_queue.py 正在跑（PID {old_pid}），"
                      f"退出，不搶佇列。", flush=True)
                sys.exit(1)
            # 確定是殘留的死行程鎖檔案：清掉後回到迴圈開頭重試，
            # O_EXCL 保證下一輪的建立動作依然是原子的。
            print(f"鎖檔案殘留（PID {old_pid} 已不存在，視為上次沒清"
                  f"乾淨），清掉重新搶鎖。", flush=True)
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
    """只在鎖確實是自己持有時才刪除——避免刪掉別人剛搶到的鎖（例如
    自己因為某種原因慢了一拍才執行到清理，但鎖早就換人了）。"""
    try:
        if int(LOCK.read_text().strip()) == os.getpid():
            LOCK.unlink()
    except (FileNotFoundError, ValueError, OSError):
        pass


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
    keep_system_awake()
    try:
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
    finally:
        release_system_awake()
        release_lock()


if __name__ == "__main__":
    main()
