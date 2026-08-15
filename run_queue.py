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
STALL_RETRIES = HERE / "logs" / "stall_retries.txt"

# 2026-08-15：radial_r3 第一次執行卡死了 83 分鐘——行程活著、但完全零
# CPU 時間增量、一個 multiprocessing worker 都沒 spawn 出來，得靠人工
# 用 Get-Process 量 CPU 時間才發現。最可能的成因是 Windows 防毒即時掃描
# 卡住新建立的 python.exe（時間點正好接在剛砍掉一串殘留行程之後，這是
# Windows 上 multiprocessing.Pool() 已知會踩的雷，但這次沒有拿到內部
# 堆疊確認，只是症狀吻合，不是鐵證）。無論真正成因是不是防毒，问题的
# 根本是：subprocess.run() 沒有逾時機制，卡死的子行程會讓整條佇列
# 安靜地空等到有人手動發現為止——這才是要修的，不是去猜對這一次的
# 成因。加一個 CPU 時間監看：定期量子行程樹整體的 CPU 時間，長時間
# 零增量就視為卡死，砍掉重試，重試次數寫進這個檔案避免真的壞掉的
# 工作無限重試。
STALL_GRACE_S = 600     # 前 10 分鐘不判定卡死——讀資料、展開 isochrone
                        # 本身就可能要好幾分鐘，不能一開始就誤判
STALL_WINDOW_S = 1200   # CPU 時間連續 20 分鐘零增量才算卡死（不是看
                        # log 有沒有新輸出——有些工作本來就好幾小時才印
                        # 一行，例如 p2_free_lowmass 曾經單次重複跑了
                        # 44 小時，log 沉默不代表沒在算，只有 CPU 時間
                        # 真的不動才是可靠訊號）
STALL_POLL_S = 120      # 每 2 分鐘量一次
MAX_STALL_RETRIES = 2   # 同一個 label 因卡死自動重試最多 2 次，
                        # 第 3 次還卡死就放棄、標記完成並印警告，
                        # 避免真正壞掉的工作在無人看顧時無限重跑

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


def _process_tree_cpu_ticks(root_pid: int) -> int | None:
    """量 root_pid 這棵行程樹（root 本身 + 所有子孫）目前累積的總 CPU
    時間（核心態+使用者態，單位是 Win32 的 100ns tick，數值本身沒有
    意義，只拿來跟下一次量到的結果比較有沒有變大）。

    用 PowerShell 的 Get-CimInstance 一次列出全系統行程再自己在 Python
    端做親子關係展開，而不是對每個 PID 各查一次——一次查詢的成本跟
    行程數無關，避免樹一大就變成 N 次子行程呼叫，本身又拖慢偵測。

    回傳 None 代表量不到（PowerShell 失敗，或 root_pid 已經不存在了——
    後者通常代表工作剛好在這次輪詢之間自然結束，不算卡死，呼叫端要把
    None 當「先別下判斷」處理，不能當成 0）。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | "
             "Select-Object ProcessId,ParentProcessId,KernelModeTime,"
             "UserModeTime | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:                                     # noqa: BLE001
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    rows = out.stdout.strip().splitlines()
    if len(rows) < 2:
        return None
    children: dict[int, list[int]] = {}
    ticks: dict[int, int] = {}
    for line in rows[1:]:
        parts = [p.strip('"') for p in line.split(",")]
        if len(parts) != 4:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
            k = int(parts[2]) if parts[2] else 0
            u = int(parts[3]) if parts[3] else 0
        except ValueError:
            continue
        ticks[pid] = k + u
        children.setdefault(ppid, []).append(pid)
    if root_pid not in ticks:
        return None
    total = 0
    stack = [root_pid]
    seen = set()
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        total += ticks.get(pid, 0)
        stack.extend(children.get(pid, []))
    return total


def _read_stall_retries() -> dict[str, int]:
    if not STALL_RETRIES.exists():
        return {}
    out = {}
    for line in STALL_RETRIES.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        label, count = line.split("\t", 1)
        try:
            out[label] = int(count)
        except ValueError:
            pass
    return out


def _bump_stall_retry(label: str) -> int:
    counts = _read_stall_retries()
    counts[label] = counts.get(label, 0) + 1
    STALL_RETRIES.parent.mkdir(exist_ok=True)
    with open(STALL_RETRIES, "w", encoding="utf-8") as f:
        for lb, c in counts.items():
            f.write(f"{lb}\t{c}\n")
    return counts[label]


def run_with_stall_watchdog(cmd_list, cwd, log_path, label):
    """跑一個子行程，定期量整棵行程樹的 CPU 時間，長時間零增量就判定
    卡死、砍掉重試（見檔案開頭 STALL_* 常數與 2026-08-15 的說明）。

    回傳 (status, secs, stalled)——stalled=True 時呼叫端要決定這一輪
    要不要重試（由 label 的重試次數決定），不在這支函式裡處理。"""
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd_list, cwd=str(cwd), stdout=fh,
                                stderr=subprocess.STDOUT)
        last_ticks, last_check = None, t0
        stalled = False
        while True:
            try:
                proc.wait(timeout=STALL_POLL_S)
                break                                     # 正常結束
            except subprocess.TimeoutExpired:
                pass
            elapsed = time.time() - t0
            if elapsed < STALL_GRACE_S:
                continue
            ticks = _process_tree_cpu_ticks(proc.pid)
            now = time.time()
            if ticks is None:
                # 量不到不代表卡死（可能剛好行程結束、也可能 PowerShell
                # 這次呼叫失敗），下一輪再量，不要用「量不到」誤判。
                continue
            if last_ticks is not None and ticks <= last_ticks and \
                    now - last_check >= STALL_WINDOW_S:
                print(f"  警告：{label} 過去 {STALL_WINDOW_S/60:.0f} 分鐘"
                      f"整棵行程樹 CPU 時間零增量，判定卡死，砍掉。",
                      flush=True)
                proc.kill()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                stalled = True
                break
            if last_ticks is None or ticks > last_ticks:
                last_ticks, last_check = ticks, now
    secs = time.time() - t0
    if stalled:
        return "stalled", secs, True
    status = "ok" if proc.returncode == 0 else f"exit{proc.returncode}"
    return status, secs, False


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
    """回傳「不用再排進 pending」的標籤集合。**2026-08-16 修正**：
    `stalled_giveup` 不算數——原本任何狀態（含 stalled_giveup）只要出現在
    這個檔案就會被當成「已處理」永久跳過，結果 radial_rall 卡死重試 3 次
    放棄後，被直接當成完成，實際上完全沒有產出結果檔，之後每次重啟都
    悄悄跳過它，得靠人工翻 log 才會發現「這項其實沒跑完」。卡死的根因
    常常是環境性的（防毒掃描、剛砍完一堆殘留行程後系統喚醒的時機這類
    跟程式碼內容無關的偶發因素，見檔案開頭 2026-08-15 的說明），全新
    重啟後值得再給一次機會，不該永久噤聲。exit1／error 這類「真的跑完
    但失敗」維持原本行為（不自動重試，避免真正壞掉的工作卡住佇列）——
    只有 stalled_giveup 這個特例排除在外，讓它留在 pending 讓下次重啟
    自然重跑（配合 mark_stall_giveup() 把重試次數計數器歸零，重跑時
    有完整的 MAX_STALL_RETRIES 次數可用，不會因為計數器沒重置而一卡
    就立刻又放棄）。"""
    if not DONE.exists():
        return set()
    out = set()
    for l in DONE.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        parts = l.split("\t")
        label = parts[0]
        status = parts[1] if len(parts) > 1 else ""
        if status == "stalled_giveup":
            continue
        out.add(label)
    return out


def mark_done(label, status, secs):
    DONE.parent.mkdir(exist_ok=True)
    with open(DONE, "a", encoding="utf-8") as f:
        f.write(f"{label}\t{status}\t{secs:.0f}s\t"
                f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")


def _reset_stall_retry(label: str):
    """放棄自動重試、記錄 stalled_giveup 之後歸零這個標籤的重試計數器
    ——不歸零的話，下次重啟時第一次卡死就會立刻沿用舊計數（已經是
    MAX_STALL_RETRIES），馬上又放棄，等於「多一次重啟機會」形同虛設。
    歸零後下次重啟會有完整 MAX_STALL_RETRIES 次數可以重試，才是
    read_done() 讓它重新排進 pending 這個修正真正想達到的效果。"""
    counts = _read_stall_retries()
    if label not in counts:
        return
    del counts[label]
    STALL_RETRIES.parent.mkdir(exist_ok=True)
    with open(STALL_RETRIES, "w", encoding="utf-8") as f:
        for lb, c in counts.items():
            f.write(f"{lb}\t{c}\n")


def main():
    acquire_lock()
    keep_system_awake()
    # 這一輪 process 生命週期內、已經放棄重試過的標籤——只存在記憶體裡，
    # 不寫檔。read_done() 現在不再把 stalled_giveup 當成「已處理」（見
    # read_done() 的說明），如果沒有這個記憶體集合擋著，giveup 之後迴圈
    # 立刻回到最上面重新選 pending[0]，選到的還是同一個剛放棄的標籤，
    # 會在這個 process 裡卡成無窮重試迴圈——這正是原本設計 giveup 機制
    # 想避免的事。加這個集合讓「這個 process 這輩子不再碰它」，但下次
    # 全新啟動 run_queue.py（新 process，這個集合重新歸零）還是會給
    # 它一次機會，兩件事分開處理才對。
    skip_this_run: set[str] = set()
    try:
        print(f"佇列執行器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
        while True:
            done = read_done()
            pending = [(l, c) for l, c in read_queue()
                       if l not in done and l not in skip_this_run]
            if not pending:
                print("佇列已清空，結束。", flush=True)
                return
            label, cmd = pending[0]
            log = HERE / "logs" / f"{label}.log"
            print(f"\n{'='*70}\n[{datetime.now():%H:%M:%S}] 開始 {label}\n"
                  f"  python {cmd}\n  輸出 -> {log.name}\n{'='*70}", flush=True)
            try:
                status, secs, stalled = run_with_stall_watchdog(
                    [sys.executable, "-u"] + cmd.split(), HERE, log, label)
            except Exception as e:                      # noqa: BLE001
                status, secs, stalled = f"error:{type(e).__name__}", 0.0, False
                print(f"  例外：{e}", flush=True)
            if stalled:
                n = _bump_stall_retry(label)
                if n <= MAX_STALL_RETRIES:
                    print(f"[{datetime.now():%H:%M:%S}] {label} 卡死重試"
                          f"（第 {n}/{MAX_STALL_RETRIES} 次），"
                          f"不標記完成，下一輪佇列會重跑。", flush=True)
                    continue                            # 不 mark_done，留在 pending
                print(f"[{datetime.now():%H:%M:%S}] {label} 連續卡死 "
                      f"{n} 次，這一輪放棄重試，記一筆 stalled_giveup"
                      f"——注意這**不等於**完成，read_done() 不會把這個狀態"
                      f"當成已處理，下次重啟（不是這一輪佇列迴圈裡）會"
                      f"自動再排進 pending 重跑，重試計數器也已歸零。"
                      f"如果重啟後又立刻卡死，才是真的需要人工檢查的訊號。",
                      flush=True)
                status = "stalled_giveup"
                _reset_stall_retry(label)
                skip_this_run.add(label)
            mark_done(label, status, secs)
            print(f"[{datetime.now():%H:%M:%S}] {label} 結束：{status}"
                  f"（{secs/60:.1f} 分）", flush=True)
    finally:
        release_system_awake()
        release_lock()


if __name__ == "__main__":
    main()
