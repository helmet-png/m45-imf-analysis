# -*- coding: utf-8 -*-
"""Kaggle 版的 run_queue.py，2026-08-09 改版：多帳號同時派工。

**跟第一版的差異**：第一版一次只追蹤一個 kernel（省事但循序），
現在有多個成員的帳號，各自的 CPU 額度互不相干，所以改成「有幾個帳號就有
幾個同時在跑的槽位」——佇列裡的待辦工作會盡量塞滿所有閒置的帳號，
而不是一個一個排隊等。

**運作方式**：每個帳號是一個槽位。每輪迴圈：
  1. 把還沒開始的工作，指派給目前閒置的帳號（可在 queue 檔用第六欄位
     指定「這項工作一定要用哪個帳號」，留白就是誰有空給誰）。
  2. 對每個忙碌中的槽位查一次狀態（不是本來就阻塞等它跑完，而是每輪
     檢查一次就繼續看別的槽位）——這樣才能真正併發，不會被其中一個
     卡住的工作拖住其他帳號。
  3. 完成或失敗的槽位釋放出來，可以接下一項待辦。

格式（每行一個工作，`|` 分隔）：

    標籤|腳本.py|接在腳本後的參數|逗號分隔的額外依賴檔|minimal(true/false)|指定帳號(可留空)

例：
    lowmass-ext|profile_lowmass.py|--procs 4 --n-syn 40000|inject.py,inj2.py|false|teammate1

已完成的標籤記在 logs/kaggle_queue_done.txt，重新啟動不會重跑；
某一步失敗（push 失敗、kernel ERROR、逾時）會記下狀態、釋放槽位接下一項，
不會卡住整條佇列。**執行中可以把新工作追加到 kaggle_queue.txt 末端**，
本執行器每輪都會重新讀檔。

**帳號登記**：見 kaggle_accounts.py / kaggle_accounts.json.example。
找不到 kaggle_accounts.json 時退回單一帳號（原本的行為，不影響舊用法）。

用法：
    python kaggle_queue.py            # 前景跑，會一直印進度直到佇列清空
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import kaggle_accounts
from run_queue import _pid_alive  # 單例鎖用，見 acquire_lock() 的說明

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "kaggle_queue.txt"
DONE = HERE / "logs" / "kaggle_queue_done.txt"
LOCK = HERE / "logs" / "kaggle_queue.lock"
POLL_SECS = 60
# 免費 CPU notebook 的執行時間上限文件說約 9-12 小時，但 2026-08-19 實測
# --refines 3,3,3 的 headline recipe 單次重複跑了 62544-62604 秒
# （~17.4 小時）才 COMPLETE——原本設 11 小時太保守，導致本機輪詢器在
# kernel 快完成前就放棄，差點漏接 4 個已經算完的結果（靠人工事後查證
# 才補救回來，見 check_status_once() 呼叫處的說明）。調高到 20 小時，
# 並且逾時放棄前一律最後補查一次狀態、COMPLETE 就照樣 pull，兩道防線
# 一起降低漏接風險（不強制砍 kernel，只是本地停止等待，逾時後仍可以
# 再手動 pull）。
MAX_WAIT_HOURS = 20
# dataset 掛載時序不穩，偵測到那個特定失敗模式就重推 kernel，
# 間隔遞增（不是猜一個固定等待時長，見 is_mount_race_failure 的說明）。
BACKOFFS = [60, 120, 240, 480]


def acquire_lock():
    """單例鎖，避免兩個 kaggle_queue.py 同時搶佇列——跟 run_queue.py 的
    acquire_lock() 同一個理由、同一套寫法（O_CREAT|O_EXCL 原子建立，PID
    存活探測失敗一律 fail closed）：2026-08-18 這台機器重開機後，
    restart_queue_on_boot.ps1 的行程比對（比對啟動指令列裡的絕對路徑）
    因為手動用相對路徑啟動過一次而漏配，誤判成「沒在跑」又重啟了一份，
    兩個 kaggle_queue.py 同時活著（只是還沒真的撞在一起做出壞事就先發現
    並砍掉了）。當時 run_queue.py 自己因為有這個鎖而安全退出，
    kaggle_queue.py 沒有，這裡補上，讓保護不再只靠 PowerShell 那邊的
    快速路徑檢查。"""
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
                print(f"偵測到另一個 kaggle_queue.py 正在跑（PID {old_pid}），"
                      f"退出，不搶佇列。", flush=True)
                sys.exit(1)
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
    """只在鎖確實是自己持有時才刪除——避免刪掉別人剛搶到的鎖。"""
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
        label, script, args, extra, minimal, account = parts
        out.append({
            "label": label.strip(), "script": script.strip(),
            "args": args.strip(), "extra": extra.strip(),
            "minimal": minimal.strip().lower() in ("1", "true", "yes"),
            "account": account.strip() or None,
        })
    return out


def read_done() -> set[str]:
    if not DONE.exists():
        return set()
    return {l.split("\t")[0] for l in
            DONE.read_text(encoding="utf-8").splitlines() if l.strip()}


def mark_done(label: str, status: str, secs: float, account: str) -> None:
    DONE.parent.mkdir(exist_ok=True)
    with open(DONE, "a", encoding="utf-8") as f:
        f.write(f"{label}\t{status}\t{secs:.0f}s\t{account}\t"
                f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")


def run(cmd: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(HERE), capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          env=env)


def push(item: dict, account_name: str) -> tuple[bool, str, Path]:
    """呼叫 kaggle_sync.py push（用獨立行程，出例外不會拖垮這支常駐執行器）。

    回傳 (是否成功, kernel id, work_dir)。kid 用跟 kaggle_sync.py 相同的
    公式算出來，而不是解析它印出的文字 —— 少一層字串解析就少一種脆弱點。
    """
    slug = item["label"].replace("_", "-")
    cmd = [sys.executable, "kaggle_sync.py", "push",
           "--script", item["script"], "--args", item["args"],
           "--account", account_name, "--slug", slug]
    if item["extra"]:
        cmd += ["--extra", item["extra"]]
    if item["minimal"]:
        cmd += ["--minimal"]
    r = run(cmd)
    print(r.stdout[-3000:], flush=True)
    if r.returncode != 0:
        print("--- push 失敗 stderr ---", flush=True)
        print(r.stderr[-3000:], flush=True)
    accounts = kaggle_accounts.load_accounts()
    username = accounts[account_name]["username"]
    kid = f"{username}/m45-imf-run-{slug}"
    work_dir = HERE / "kaggle_work" / account_name
    return r.returncode == 0, kid, work_dir


# probe_kernel_status() 的回傳值裡代表「kernel 真的跑完了」的那幾個。
TERMINAL = {"complete", "error", "cancelled"}


def probe_kernel_status(kid: str, env: dict) -> str:
    """查一次 kernel 狀態，把「還在跑」「不存在」「查不到」三種情況分開。

    2026-08-19 CodeRabbit PR #66 指出：原本 check_status_once() 對這三種
    情況一律回傳 None，呼叫端只能一律當成「還在跑，下一輪再看」。在主迴圈
    裡那是安全的，但在 recover_running_slots() 裡不是——「不存在」要讓槽位
    空著去派新工作，「查不到」（網路斷、憑證過期、被限流）則絕對不能，那會
    讓復原邏輯誤判成沒人在跑而重推，把遠端已經跑了十幾小時的進度洗掉。

    實測 `kaggle kernels status` 的輸出（2026-08-19）：
      存在   -> returncode 0，stdout 有 `has status "KernelWorkerStatus.XXX"`
      不存在 -> returncode 1，stderr 是 `Cannot access kernel ...`
                （訊息自稱是權限問題，但實際上打錯 slug 也是這一句）
    其他非零退出碼一律歸到 "unknown"，由呼叫端決定要不要保守處理。

    回傳 "running"／"complete"／"error"／"cancelled"／"missing"／"unknown"。
    """
    r = run(["kaggle", "kernels", "status", kid], env=env)
    text = (r.stdout + r.stderr).strip()
    if r.returncode == 0 and "has status" in text:
        if "COMPLETE" in text:
            return "complete"
        if "ERROR" in text:
            return "error"
        if "CANCEL" in text:
            return "cancelled"
        return "running"        # RUNNING／QUEUED 等尚未結束的狀態
    if "Cannot access kernel" in text or "wrong kernel slug" in text:
        return "missing"
    print(f"  查詢 {kid} 狀態失敗（rc={r.returncode}）：{text[:300]}",
          flush=True)
    return "unknown"


def check_status_once(kid: str, env: dict) -> str | None:
    """查一次狀態，不阻塞等待。回傳 "ok"/"error"/"cancelled"（終止狀態）
    或 None（還在排隊或執行中，或這次查不到——都是「先不要下結論」）。
    """
    st = probe_kernel_status(kid, env)
    if st == "complete":
        return "ok"
    if st in ("error", "cancelled"):
        return st
    return None


def is_mount_race_failure(label: str) -> bool:
    """判斷剛才的 ERROR 是不是「dataset 還沒真的掛載好」這種暫時性失敗。

    **實測結論（2026-08-09）**：dataset API 回報 ready 之後，kernel 執行環境
    真的掛載到該 dataset 還有額外、且不穩定的延遲——曾經連等 138 秒、
    事後手動再等數分鐘都還是失敗過，猜一個等待時長無法可靠涵蓋。
    改用偵測 + 重試：錯誤訊息是這個特定的「檔案在 /kaggle/input/ 下
    找不到」，代表 dataset 這次真的還沒掛好，值得重推；若是別的錯誤
    （腳本邏輯錯、套件裝不起來），重推沒有意義，直接判定失敗省 quota。
    """
    out = HERE / "kaggle_results" / label
    for f in out.glob("*.log"):
        try:
            events = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            continue
        for e in events:
            d = e.get("data", "")
            if "FileNotFoundError" in d and "/kaggle/input/" in d:
                return True
    return False


def recover_running_slots(accounts: dict, envs: dict) -> dict[str, dict | None]:
    """開機時的復原：掃描所有還沒標記完成的待辦項目，看有沒有帳號已經在
    Kaggle 端跑著對應的 kernel（2026-08-18 這台機器連續遇到兩次非預期
    重開機——本機重開機／agent session 中斷不會影響 Kaggle 端已經在跑的
    kernel，只會讓這支輪詢器失去追蹤；重開這支腳本若直接對每個閒置帳號
    重推，等於中斷已經跑了一段時間的進度，白算掉）。找到 RUNNING／QUEUED
    的就接回槽位，不重推；找不到才照原本流程當作全新工作處理。

    2026-08-19 CodeRabbit PR #66 補了兩個原本會漏掉的情況：
      * **遠端已經跑完**（COMPLETE／ERROR／CANCELLED）：本機失聯期間 kernel
        自己結束了。原本只認 RUNNING／QUEUED，會留下空槽位，主迴圈接著把
        同一個 label 重推一次——COMPLETE 的話等於把已經算完的結果丟掉重算。
        改成 COMPLETE 就照正常流程 pull + mark_done；ERROR／CANCELLED
        **不標 done**，讓主迴圈照既有的重推/重試邏輯處理（那是這支腳本本來
        就有的失敗處置，不該在復原路徑另立一套）。
      * **狀態查不到**（網路斷、憑證過期、被限流）：這跟「kernel 不存在」
        看起來都像沒東西在跑，但處置相反。查不到時**佔住槽位**這一輪不派
        新工作，下一輪再查；寧可慢一輪，也不要在遠端其實正在跑的情況下重推。
    """
    done = read_done()
    pending = [it for it in read_queue() if it["label"] not in done]
    slots: dict[str, dict | None] = {name: None for name in accounts}
    for name in accounts:
        for item in pending:
            if item["account"] not in (None, name):
                continue
            slug = item["label"].replace("_", "-")
            username = accounts[name]["username"]
            kid = f"{username}/m45-imf-run-{slug}"
            st = probe_kernel_status(kid, envs[name])
            if st == "missing":
                continue        # 這個帳號沒推過這項，繼續看下一項
            if st == "unknown":
                # 查不到就保守處理：佔住槽位、這一輪不派新工作。
                # phase="probe" 不帶 kid，主迴圈的忙碌槽位檢查會跳過它，
                # 下一輪復原式查詢由 main() 的 requeue 邏輯重來。
                slots[name] = {
                    "phase": "probe", "item": item, "kid": kid,
                    "work_dir": HERE / "kaggle_work" / name,
                    "t0": time.time(), "retries": 0,
                }
                print(f"復原：{name} 查 {item['label']}（{kid}）狀態失敗，"
                      f"這一輪不派新工作，下一輪再查（避免遠端其實正在跑"
                      f"卻被重推洗掉）", flush=True)
                break
            if st == "running":
                slots[name] = {
                    "phase": "running", "item": item, "kid": kid,
                    "work_dir": HERE / "kaggle_work" / name,
                    "t0": time.time(), "retries": 0,
                }
                print(f"復原：{name} 已經在跑 {item['label']}（{kid}），"
                      f"接回追蹤、不重推", flush=True)
                break
            if st == "complete":
                print(f"復原：{name} 的 {item['label']}（{kid}）在本機失聯"
                      f"期間已經 COMPLETE，補拉結果並標記完成，不重算",
                      flush=True)
                if pull(kid, item["label"], envs[name]):
                    mark_done(item["label"], "ok", 0, name)
                else:
                    print(f"  結果下載失敗，不標記完成——留給主迴圈重試",
                          flush=True)
                continue        # 槽位保持空著，可以接新工作
            # error／cancelled：不標 done，讓主迴圈照既有失敗處置重推
            print(f"復原：{name} 的 {item['label']}（{kid}）遠端狀態為 "
                  f"{st}，交回主迴圈照既有重試流程處理", flush=True)
    return slots


def push_kernel_only(work_dir: Path, env: dict) -> bool:
    """只重推 kernel，沿用該帳號 work_dir 裡已經上傳過的 dataset。"""
    r = run(["kaggle", "kernels", "push", "-p", str(work_dir)], env=env)
    print(r.stdout[-1500:], flush=True)
    if r.returncode != 0:
        print(r.stderr[-1500:], flush=True)
    return r.returncode == 0


def pull(kid: str, label: str, env: dict) -> bool:
    """下載 kernel 輸出。回傳是否成功。

    2026-08-19 CodeRabbit PR #66 指出：原本丟掉 `kaggle kernels output` 的
    回傳碼，呼叫端無論下載成功與否都接著 mark_done()——DONE 檔一寫下去就
    不會再重試，等於一次網路中斷就永久丟掉一個已經算完的 kernel 的結果。
    這在這個專案不是假設性風險：rep5 的下載就曾經因為 IncompleteRead 中斷
    過，當時是人工發現才補拉的。
    """
    out = HERE / "kaggle_results" / label
    out.mkdir(parents=True, exist_ok=True)
    r = run(["kaggle", "kernels", "output", kid, "-p", str(out)], env=env)
    if r.returncode != 0:
        print(f"  下載 {kid} 輸出失敗（rc={r.returncode}）："
              f"{(r.stderr or r.stdout)[-500:]}", flush=True)
        return False
    return True


def main() -> None:
    acquire_lock()
    import atexit
    atexit.register(release_lock)  # 涵蓋正常結束、例外、sys.exit()

    accounts = kaggle_accounts.load_accounts()
    print(f"Kaggle 佇列執行器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}，"
          f"{len(accounts)} 個帳號同時派工：{list(accounts)}", flush=True)
    envs = {name: kaggle_accounts.env_for(info)
            for name, info in accounts.items()}

    # slots[帳號名] = None（閒置）或一個描述目前工作狀態的 dict。
    # 啟動時先掃一輪，接回任何帳號已經在 Kaggle 端跑著的 kernel，
    # 不要無條件當成全新一輪、把還在跑的進度重推掉。
    slots = recover_running_slots(accounts, envs)
    if any(slots.values()):
        running = [n for n, s in slots.items() if s]
        print(f"復原完成，接回 {len(running)} 個已在跑的槽位：{running}",
              flush=True)

    while True:
        done = read_done()
        pending = [it for it in read_queue() if it["label"] not in done
                   and it["label"] not in
                   {s["item"]["label"] for s in slots.values() if s}]

        # 1) 把待辦工作塞進閒置的帳號槽位
        for name in accounts:
            if slots[name] is not None:
                continue
            idx = next((i for i, it in enumerate(pending)
                       if it["account"] in (None, name)), None)
            if idx is None:
                continue
            item = pending.pop(idx)
            print(f"\n{'='*70}\n[{datetime.now():%H:%M:%S}] "
                  f"帳號 {name} 開始 {item['label']}"
                  f"\n  {item['script']} {item['args']}\n{'='*70}",
                  flush=True)
            ok, kid, work_dir = push(item, name)
            if ok:
                slots[name] = {"phase": "running", "item": item, "kid": kid,
                              "work_dir": work_dir, "t0": time.time(),
                              "retries": 0}
            else:
                mark_done(item["label"], "push_failed", 0, name)

        # 2) 檢查每個忙碌槽位（各只查一次，不阻塞等待，才能真正併發）
        for name, slot in list(slots.items()):
            if slot is None:
                continue
            if slot["phase"] == "probe":
                # 復原時狀態查不到而暫時佔住的槽位（見 recover_running_slots）。
                # 每一輪重查一次，查得到就照結果轉正常流程；還是查不到就繼續
                # 佔著——「查不到」代表我們無從判斷遠端到底有沒有在跑，這種
                # 情況下派新工作的風險（重推洗掉進度）遠大於慢一輪的代價。
                # 持續查不到通常是憑證過期或網路斷，屬於要人介入的狀況，
                # 每一輪都印出來讓它顯眼。
                st = probe_kernel_status(slot["kid"], envs[name])
                if st == "missing":
                    print(f"  [{name}] {slot['item']['label']} 確認遠端沒有這個"
                          f"kernel，釋放槽位、照正常流程派工", flush=True)
                    slots[name] = None
                elif st == "running":
                    slot["phase"] = "running"
                    slot["t0"] = time.time()
                    print(f"  [{name}] {slot['item']['label']} 查到遠端正在跑，"
                          f"接回追蹤", flush=True)
                elif st in TERMINAL:
                    if st == "complete":
                        if pull(slot["kid"], slot["item"]["label"], envs[name]):
                            mark_done(slot["item"]["label"], "ok", 0, name)
                        else:
                            print(f"  [{name}] 結果下載失敗，保留工作供下一輪"
                                  f"重試", flush=True)
                            continue
                    slots[name] = None
                else:
                    print(f"  [{name}] {slot['item']['label']} 狀態仍查不到，"
                          f"繼續佔住槽位（若持續如此請檢查憑證與網路）",
                          flush=True)
                continue

            if slot["phase"] == "cooldown":
                if time.time() >= slot["resume_at"]:
                    ok = push_kernel_only(slot["work_dir"], envs[name])
                    if ok:
                        slot["phase"] = "running"
                    else:
                        mark_done(slot["item"]["label"], "error",
                                 time.time() - slot["t0"], name)
                        slots[name] = None
                continue

            elapsed_h = (time.time() - slot["t0"]) / 3600
            if elapsed_h > MAX_WAIT_HOURS:
                # 2026-08-19 教訓：這個 recipe（--refines 3,3,3）單次重複
                # 實測跑了 62544-62604 秒（~17.4 小時）才真的 COMPLETE，
                # 遠超 MAX_WAIT_HOURS=11——本機輪詢器直接放棄不拉結果，
                # 差點漏接 4 個已經算完的 kernel（rep5-8），只是剛好人工
                # 事後查證才發現。逾時放棄前，最後再查一次狀態，COMPLETE
                # 就照正常流程 pull，不要平白丟掉可能剛好算完的結果。
                final_status = check_status_once(slot["kid"], envs[name])
                if final_status is not None:
                    pulled = pull(slot["kid"], slot["item"]["label"],
                                  envs[name])
                    if final_status == "ok" and not pulled:
                        # 已經 COMPLETE 卻拉不下來：**絕對不能 mark_done**，
                        # 那會讓這個算完的 kernel 永遠不再被重試。留在槽位裡
                        # 下一輪重拉（逾時判斷會再次成立，所以是每輪重試一次）。
                        print(f"[{datetime.now():%H:%M:%S}] [{name}] "
                              f"{slot['item']['label']} 已 COMPLETE 但結果"
                              f"下載失敗，保留工作供下一輪重試", flush=True)
                        continue
                    mark_done(slot["item"]["label"], final_status,
                             time.time() - slot["t0"], name)
                    print(f"[{datetime.now():%H:%M:%S}] [{name}] "
                          f"{slot['item']['label']} 逾時前最後一查，其實已經"
                          f"結束：{final_status}，已補拉結果", flush=True)
                else:
                    mark_done(slot["item"]["label"], "timeout",
                             time.time() - slot["t0"], name)
                slots[name] = None
                continue

            status = check_status_once(slot["kid"], envs[name])
            if status is None:
                continue    # 還在跑，下一輪再看

            pulled = pull(slot["kid"], slot["item"]["label"], envs[name])
            if status == "ok" and not pulled:
                # 同上：算完了但結果沒拉下來，不標記完成，下一輪重拉。
                # 只對 "ok" 這樣做——"error"／"cancelled" 拉的是 log 不是
                # 結果，拉不到不該讓槽位卡住不放。
                print(f"  [{name}] {slot['item']['label']} 已 COMPLETE 但"
                      f"結果下載失敗，保留工作供下一輪重試", flush=True)
                continue
            if (status == "error" and is_mount_race_failure(slot["item"]["label"])
                    and slot["retries"] < len(BACKOFFS)):
                wait_s = BACKOFFS[slot["retries"]]
                slot["retries"] += 1
                slot["phase"] = "cooldown"
                slot["resume_at"] = time.time() + wait_s
                print(f"  [{name}] 偵測到 dataset 掛載時序問題（非程式錯誤），"
                      f"{wait_s}s 後重推 kernel（第 {slot['retries']} 次重試）",
                      flush=True)
            else:
                secs = time.time() - slot["t0"]
                mark_done(slot["item"]["label"], status, secs, name)
                print(f"[{datetime.now():%H:%M:%S}] [{name}] "
                      f"{slot['item']['label']} 結束：{status}"
                      f"（{secs/60:.1f} 分）\n", flush=True)
                slots[name] = None

        if not pending and all(s is None for s in slots.values()):
            print("Kaggle 佇列已清空，結束。", flush=True)
            return
        time.sleep(POLL_SECS)


if __name__ == "__main__":
    main()
