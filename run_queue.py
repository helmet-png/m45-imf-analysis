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
import re
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
TICK_LOG = HERE / "logs" / "watchdog_ticks.log"

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

# 2026-08-16：radial_r3 在加了卡死偵測之後還是連續卡了好幾次（原因見上面
# 2026-08-15 的說明：懷疑是防毒即時掃描卡住剛建立的 python.exe，時間點
# 正好接在砍掉卡死行程樹之後）——而每一次自動重試都是「砍掉、立刻
# 建立新的」，如果真的是防毒掃描的問題，這個「立刻」正好就是會撞進同一個
# 觸發窗口的模式，等於重試機制自己在製造下一次卡死的條件。加一段緩衝，
# 讓砍掉的行程樹跟系統（防毒/檔案控制代碼釋放）有時間收尾，再建立新的，
# 不保證解決（成因本來就沒有內部堆疊能鐵證），但直接對應症狀本身描述的
# 觸發模式，不是憑空的猜測。
STALL_RETRY_SETTLE_S = 30

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
    # **2026-08-20 修**：原本用 text=True 讓 subprocess 自己決定編碼。
    # 這台是中文 Windows，`tasklist` 輸出 cp950（Big5）——平常剛好能解，
    # 但只要環境有 PYTHONUTF8=1（用 UTF-8 去解 Big5 位元組），解碼會在
    # subprocess 內部的讀取執行緒炸掉，`out.stdout` 變成 None，接著
    # `str(pid) in None` 丟 TypeError。**後果比看起來嚴重**：這個函式的
    # 整份設計是「探測失敗要回傳 None 讓呼叫端 fail closed」，但未捕捉的
    # 例外會直接讓 run_queue.py 整個崩掉，fail-closed 完全沒生效——實際
    # 就這樣發生過一次，佇列啟動後立刻死掉、什麼都沒跑。
    # 改成讀 bytes 自己解碼（errors="replace" 保證不會因為編碼失敗），
    # 並把 stdout 是 None 的情況明確當成探測失敗。
    # **2026-08-20 CodeRabbit review 再抓到一個**：解碼修好之後，剩下的
    # 風險在子字串比對本身——用 UTF-8 去解 cp950 時，雙位元組字元的尾
    # 位元組若落在 ASCII 數字範圍，解出來的文字可能剛好含有跟 pid 相符
    # 的數字序列，但那串數字其實不屬於任何欄位（是某個中文字被錯誤解碼
    # 的殘骸）。後果：acquire_lock() 誤判鎖還被別的行程持有而直接
    # sys.exit(1)，整條佇列被無故擋住。改成 `/FO CSV /NH` 拿結構化輸出，
    # 只比對 PID 那一欄，跟主控台語言／編碼完全無關。
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:                                 # noqa: BLE001
        return None
    if out.returncode != 0 or out.stdout is None:
        return None
    text = out.stdout.decode("utf-8", errors="replace")
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split(",")]
        # 沒有相符行程時 tasklist 印的是一行資訊訊息（不是 CSV 資料列，
        # 欄位數不對），所以只認「欄位數對、且 PID 欄能解析成整數」的行。
        if len(parts) >= 2 and parts[1].isdigit() and int(parts[1]) == pid:
            return True
    return False


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
            capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:                                     # noqa: BLE001
        return None
    # 同 _pid_alive() 的理由（見那邊 2026-08-20 的說明）：自己解碼，
    # 不讓編碼問題把「回傳 None＝探測失敗」變成未捕捉例外。這支函式
    # 崩掉會連帶把整個卡死監看迴圈帶走，而它正是用來讓長跑工作可靠的。
    if out.returncode != 0 or out.stdout is None:
        return None
    text = out.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    rows = text.splitlines()
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


def _write_stall_retries(counts: dict[str, int]):
    """2026-08-16 CodeRabbit review 抓到：原本直接 `open(..., "w")` 覆寫，
    不是原子操作——寫到一半被中斷（跟這支腳本本來就在防的「行程被砍掉」
    是同一類風險）會留下空檔或半截內容，`_read_stall_retries()` 讀到的
    次數會憑空歸零或亂掉，讓某個 label 的重試計數不準（可能因此提早
    或延後觸發 giveup）。改成跟 `fit_real.py` 的 `atomic_savez()`、
    `acquire_lock()` 同一套邏輯：寫暫存檔、flush+fsync 確保真的落盤，
    再用 `os.replace()` 原子性換過去。"""
    STALL_RETRIES.parent.mkdir(exist_ok=True)
    tmp_path = STALL_RETRIES.with_name(STALL_RETRIES.name + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            for lb, c in counts.items():
                f.write(f"{lb}\t{c}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, STALL_RETRIES)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _bump_stall_retry(label: str) -> int:
    counts = _read_stall_retries()
    counts[label] = counts.get(label, 0) + 1
    _write_stall_retries(counts)
    return counts[label]


def _kill_process_tree(pid: int):
    """2026-08-16 CodeRabbit review 抓到：Windows 上 `proc.kill()` 只會
    終止 root process 本身，不會連帶終止子孫行程——`fit_real.py` 底下
    用 `multiprocessing.Pool` 開出來的工人是孫行程（`fit_real.py` 的
    子行程），`proc.kill()` 砍掉的只有 `fit_real.py` 這一層，工人全部
    變成孤兒，繼續佔用 CPU／核心，直到它們自己因為管道斷線
    （`BrokenPipeError`，parent 已死）跳例外才會自然結束——這正是這次
    session 好幾次觀察到「砍掉重試後 log 裡一堆 BrokenPipeError」的
    根因，不只是重試時機的問題。改用 `taskkill /PID <pid> /T /F`
    （`/T` 連子孫行程樹一起砍、`/F` 強制），這是 Windows 官方提供、
    專門處理行程樹終止的工具，比自己在 Python 端遞迴列舉子行程再逐一
    kill 可靠。失敗（例如 taskkill 本身不存在、行程已經自然結束）就
    退回 `proc.kill()`，至少把 root process 砍乾淨，不讓例外中斷整個
    watchdog。"""
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:                                     # noqa: BLE001
        pass


def _log_tick(label: str, ticks, delta, note: str = "") -> None:
    """把每次輪詢量到的 CPU tick 附加寫進 logs/watchdog_ticks.log。

    2026-08-20 加入：稍早追查 radial_r3 反覆卡死時，發現完全沒有留下
    輪詢過程的數值記錄，只有「判定卡死」那一行結論，事後沒辦法回頭看
    卡死前 tick 是怎麼變化的（是真的長時間持平、還是踩到 2026-08-16
    修掉的那個「下降誤判」bug）。這支函式本身不影響卡死判斷邏輯，純粹
    留痕，讓下次真的卡死時能回頭看趨勢，不用只靠猜。用純 append 寫入，
    這個檔案會持續長大，不做輪替——量不大（一行約 60-80 bytes，一個
    多小時的工作撐死幾百行），需要時再手動清。"""
    try:
        TICK_LOG.parent.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        delta_str = "?" if delta is None else str(delta)
        with open(TICK_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{label}\tticks={ticks}\tdelta={delta_str}"
                    f"\t{note}\n")
    except OSError:
        pass                    # 留痕是輔助功能，寫檔失敗不該讓監看中止


def _preflight_ok(label: str, cmd: str) -> bool:
    """派工前先讓目標腳本自己做一次開跑前檢查（見 scripts/tools/preflight.py）。

    只對已經支援 `--preflight` 的腳本生效；其他腳本一律放行（回傳 True），
    **不是因為它們安全，是因為還沒有幫它們做這個功能**——涵蓋差異寫在
    `docs/reference/PREFLIGHT.md`，不要把「放行」讀成「檢查過了」。
    """
    # 續傳能力（B3）判斷邏輯本體在 scripts/tools/preflight.py 的
    # _has_resume()，這裡不重複實作一份——兩份 pattern 若之後改名/加條件
    # 會不同步，其中一份會給出錯誤的「有續傳保護」結論（2026-08-20
    # CodeRabbit review）。延後到函式內才 import（不放模組層級）是為了
    # 避開循環匯入：preflight.py 的 gate_b() 也會 `import run_queue`。
    tools_dir = str(HERE / "scripts" / "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import preflight                                         # noqa: PLC0415

    script = cmd.split()[0]
    if not preflight._has_resume(script):
        # 警告不阻擋：這類腳本在沒被中斷時是會正常跑完的，直接擋掉
        # 等於永遠不讓它跑。但這台機器過去四天被強制重開機 4 次，
        # p6_lowmass_v2 因此連續四天每次都從頭重算、一次都沒完成，
        # 所以派工的人要知道自己在賭什麼。根治是幫這些腳本補上
        # fit_real.py 那套逐次存檔＋manifest 續傳。
        print(f"  注意：{script} 沒有續傳機制，中途被砍（重開機／卡死"
              f"重試）就得從頭重算——這台機器有非預期重開機的前科",
              flush=True)
    if script != "fit_real.py":
        return True
    try:
        # 子行程要用 UTF-8 輸出，否則中文 Windows 下它會寫 cp950 到管線，
        # 這邊以 utf-8 解出來全是亂碼，下面用開頭字串挑警告行就全部挑不到
        #（訊息沒消失，但沒人看得懂＝等於沒有警告）。只影響這個子行程，
        # 不會像整個 process 設 PYTHONUTF8 那樣連帶弄壞 tasklist 的解碼。
        env = {**os.environ, "PYTHONUTF8": "1"}
        r = subprocess.run([sys.executable, script, *cmd.split()[1:],
                            "--preflight"], cwd=str(HERE), env=env,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
    except Exception as e:                                   # noqa: BLE001
        # 檢查本身壞掉不該擋住正事——印出來讓人看到，然後照常跑。
        print(f"  開跑前檢查無法執行（{type(e).__name__}: {e}），照常開跑",
              flush=True)
        return True
    for ln in (r.stdout or "").splitlines():
        if ln.strip().startswith(preflight.STATUS_PREFIXES):
            print(f"  {ln.strip()}", flush=True)
    if r.returncode != 0:
        print(f"  開跑前檢查不通過（退出碼 {r.returncode}），跳過 {label}，"
              f"不浪費機時。修好後把 logs/queue_done.txt 裡那一行刪掉即可"
              f"重新排隊。", flush=True)
        return False
    return True


def _postflight(label: str, cmd: str) -> None:
    """跑完立刻驗收產出（Gate C）。只印警告、不改變佇列流程——結果檔已經
    寫出來了，這裡的價值是「當天就看到問題」而不是幾週後才發現（P11 那
    12 次全部等於 2.500 的簽章在檔案裡躺了很久沒人看）。"""
    # 同時吃 `--tag value` 與 `--tag=value` 兩種 argparse 都接受的形式，
    # 原本只吃空白分隔那種，`=` 形式會讓 m 是 None 而整支函式靜默 return——
    # 使用者會以為「這次沒有 Gate C 警告」，其實是驗收根本沒有跑
    # （2026-08-20 CodeRabbit review）。
    m = re.search(r"--tag[=\s]+(\S+)", cmd)
    if cmd.split()[0] != "fit_real.py" or not m:
        return
    npz = HERE / "results" / f"fit_real{m.group(1)}.npz"
    if not npz.exists():
        return
    try:
        tools_dir = str(HERE / "scripts" / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        import preflight                                     # noqa: PLC0415
        fails = preflight.gate_c(npz, verbose=False)
    except Exception as e:                                   # noqa: BLE001
        print(f"  產出驗收無法執行（{type(e).__name__}: {e}）", flush=True)
        return
    for f in fails:
        print(f"  產出驗收警告：{f}", flush=True)
    if not fails:
        print(f"  產出驗收通過：{npz.name}", flush=True)


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
                # **2026-08-16 CodeRabbit 又抓到一個邊界情況**：如果連續
                # 好幾輪都量不到（`last_check` 停在最後一次量到的時間
                # 沒有更新），中間經過的時間可能已經超過 STALL_WINDOW_S，
                # 下一次量到剛好等於 `last_ticks` 的值時會立刻判定卡死
                # ——但這段期間其實完全沒有兩次「量得到」的結果可以互相
                # 比較，不能算「確認零增量」。把 `last_ticks` 重設成
                # `None`，讓下一次量到的結果重新走「初始化基準」那條路
                # （見下面 `if last_ticks is None or ...`），需要之後再
                # 連續 STALL_WINDOW_S 秒量到不變的值才會判定卡死。
                _log_tick(label, None, None, "量不到（行程剛結束或 PowerShell 呼叫失敗）")
                last_ticks = None
                continue
            # **2026-08-16 CodeRabbit review 抓到的真 bug**：原本
            # `ticks <= last_ticks` 把「減少」也當成「零增量」——
            # `_process_tree_cpu_ticks()` 只加總目前還活著的子孫行程，
            # `multi_stage_best()` 每個精修階段都重開一次 Pool，舊工人
            # 結束、新工人還沒起來的空窗期，總 ticks 可能真的往下掉。
            # 原本的邏輯不會在下降時重設 `last_check`，如果這段爬升期
            # 恰好接近 `STALL_WINDOW_S`，會把「正常在算，只是換了一批
            # 工人」誤判成卡死——這可能是這次 session 追查到的部分卡死
            # 事件的真正成因，不只是猜測的防毒掃描。改成：**只要
            # ticks 有任何變化（不論升降）就重設基準跟計時**，只有
            # ticks 連續 `STALL_WINDOW_S` 秒完全沒變（不是「沒有增加」）
            # 才判定卡死——這才是註解原本講的「CPU 時間真的不動」。
            if last_ticks is None or ticks != last_ticks:
                delta = None if last_ticks is None else ticks - last_ticks
                _log_tick(label, ticks, delta, "初始化基準" if last_ticks is None else "")
                last_ticks, last_check = ticks, now
                continue
            flat_s = now - last_check
            _log_tick(label, ticks, 0, f"持平 {flat_s:.0f}s")
            if flat_s >= STALL_WINDOW_S:
                print(f"  警告：{label} 過去 {STALL_WINDOW_S/60:.0f} 分鐘"
                      f"整棵行程樹 CPU 時間零增量，判定卡死，砍掉。",
                      flush=True)
                _kill_process_tree(proc.pid)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()                    # taskkill 沒成功時的最後防線
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        pass
                stalled = True
                break
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
        label, cmd = label.strip(), cmd.strip()
        # `label|`（沒有指令）會讓下游 cmd.split()[0] IndexError——
        # 在來源這裡一次擋掉，兩個呼叫端（_preflight_ok／_postflight）
        # 都不用各自防禦（2026-08-20 CodeRabbit review）。
        if not cmd:
            print(f"警告：queue.txt 裡 {label!r} 這行沒有指令，略過。",
                  flush=True)
            continue
        out.append((label, cmd))
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
    就立刻又放棄）。

    **2026-08-20 加入 preflight_fail 同一個理由**：開跑前檢查沒過（設定
    寫錯、依賴檔案缺失這類）常常是人工修好設定或補齊檔案就能解決的，
    跟 exit1（程式碼本身邏輯或資料真的有問題）不是同一類。若也永久噤聲，
    修好之後還得手動去 logs/queue_done.txt 刪那一行才會重跑，等於重新
    製造一次「隱形失敗」。這一輪迴圈裡不會無窮重試——main() 的
    skip_this_run 已經擋住同一輪重新選中同一個標籤，這裡只影響「下次
    重啟」會不會再給機會（2026-08-20 CodeRabbit review）。"""
    if not DONE.exists():
        return set()
    out = set()
    for l in DONE.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        parts = l.split("\t")
        label = parts[0]
        status = parts[1] if len(parts) > 1 else ""
        if status in ("stalled_giveup", "preflight_fail"):
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
    _write_stall_retries(counts)


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
            if not _preflight_ok(label, cmd):
                # 開跑前檢查沒過就不要燒好幾個小時（動機見 scripts/tools/
                # preflight.py 檔頭：白跑的 86.6 機時裡有 74.9h 是「跑完
                # exit 0 但算法不是我們以為的那個」）。記一筆 preflight_fail
                # 讓它不會在這一輪迴圈裡被重新選中，人工修好設定後
                # 從 logs/queue_done.txt 刪掉那一行就會重新排進 pending。
                mark_done(label, "preflight_fail", 0.0)
                skip_this_run.add(label)
                continue
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
                          f"不標記完成，緩衝 {STALL_RETRY_SETTLE_S} 秒後"
                          f"重跑。", flush=True)
                    time.sleep(STALL_RETRY_SETTLE_S)
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
            if status == "ok":
                _postflight(label, cmd)
    finally:
        release_system_awake()
        release_lock()


if __name__ == "__main__":
    main()
