# -*- coding: utf-8 -*-
"""Kaggle 版的 run_queue.py：依序 push -> 等執行完 -> pull，讓 Kaggle 也能像
本機一樣連續排多個工作。

**跟本機佇列的本質差異**：本機一次只有一組 8 核心可搶，所以循序執行是必要的；
Kaggle 這邊循序執行單純是為了先求穩（一次只追蹤一個 kernel 的狀態，
避免同時開多個 kernel 時搞混哪個對應哪個結果），不是資源上的硬限制——
若之後要真正併發（同時掛多個 kernel），把 push 那段改成不等待、批次全部推出去，
再各自輪詢即可，架構不用大改。

格式（每行一個工作，`|` 分隔，跟本機 queue.txt 同精神但欄位不同）：

    標籤|腳本.py|接在腳本後的參數|逗號分隔的額外依賴檔|minimal(true/false，可省略)

例：
    lowmass-ext|profile_lowmass.py|--procs 4 --n-syn 40000 --repeats 3 --slopes 0.6,0.7,1.9,2.0|injection_recovery.py,measure_overconfidence.py|false

已完成的標籤記在 logs/kaggle_queue_done.txt，重新啟動不會重跑；
某一步失敗（push 失敗、kernel ERROR、逾時）會記下狀態、繼續下一步，
不會卡住整條佇列。**執行中可以把新工作追加到 kaggle_queue.txt 末端**，
本執行器每輪都會重新讀檔。

用法：
    python kaggle_queue.py            # 前景跑，會一直印進度直到佇列清空
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "kaggle_queue.txt"
DONE = HERE / "logs" / "kaggle_queue_done.txt"
USERNAME = "helmetalbert"
POLL_SECS = 90
# 免費 CPU notebook 的執行時間上限一般約 9-12 小時，留一點餘裕就中止輪詢
# （不強制砍 kernel，只是本地停止等待，之後可以再手動 pull）。
MAX_WAIT_HOURS = 11


def read_queue() -> list[dict]:
    if not QUEUE.exists():
        return []
    out = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "|" not in line:
            continue
        parts = (line.split("|") + ["", "", ""])[:5]
        label, script, args, extra, minimal = parts
        out.append({
            "label": label.strip(), "script": script.strip(),
            "args": args.strip(), "extra": extra.strip(),
            "minimal": minimal.strip().lower() in ("1", "true", "yes"),
        })
    return out


def read_done() -> set[str]:
    if not DONE.exists():
        return set()
    return {l.split("\t")[0] for l in
            DONE.read_text(encoding="utf-8").splitlines() if l.strip()}


def mark_done(label: str, status: str, secs: float) -> None:
    DONE.parent.mkdir(exist_ok=True)
    with open(DONE, "a", encoding="utf-8") as f:
        f.write(f"{label}\t{status}\t{secs:.0f}s\t"
                f"{datetime.now():%Y-%m-%d %H:%M:%S}\n")


def kernel_id(label: str) -> str:
    slug = label.replace("_", "-")
    return f"{USERNAME}/m45-imf-run-{slug}"


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=str(HERE), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def push(item: dict) -> bool:
    """呼叫 kaggle_sync.py push。用獨立行程而非直接 import，
    這樣就算 push 邏輯本身出例外也不會拖垮這支常駐執行器。
    """
    cmd = [sys.executable, "kaggle_sync.py", "push",
           "--script", item["script"], "--args", item["args"],
           "--username", USERNAME,
           "--slug", item["label"].replace("_", "-")]
    if item["extra"]:
        cmd += ["--extra", item["extra"]]
    if item["minimal"]:
        cmd += ["--minimal"]
    r = run(cmd)
    print(r.stdout[-3000:], flush=True)
    if r.returncode != 0:
        print("--- push 失敗 stderr ---", flush=True)
        print(r.stderr[-3000:], flush=True)
    return r.returncode == 0


def poll_until_done(kid: str) -> str:
    deadline = time.time() + MAX_WAIT_HOURS * 3600
    while time.time() < deadline:
        r = run(["kaggle", "kernels", "status", kid])
        status = (r.stdout + r.stderr).strip()
        print(f"  [{datetime.now():%H:%M:%S}] {status}", flush=True)
        if "COMPLETE" in status:
            return "ok"
        if "ERROR" in status:
            return "error"
        if "CANCEL" in status:
            return "cancelled"
        time.sleep(POLL_SECS)
    return "timeout"


def is_mount_race_failure(label: str) -> bool:
    """判斷剛才的 ERROR 是不是「dataset 還沒真的掛載好」這種暫時性失敗。

    **實測結論（2026-08-09）**：靠估計時間去等 dataset 就緒不可靠——
    連續三次新建 dataset+kernel，就算等到 138 秒、甚至事後手動再等了
    好幾分鐘重推，仍然拿到一模一樣的 FileNotFoundError（對照組：直接用
    API 下載該 dataset，內容與路徑都正確）。這代表 Kaggle 內部「dataset
    metadata 就緒」跟「kernel 執行環境真的掛載到該 dataset」是兩個時間點
    不同、且延遲不穩定的系統，猜一個等待時長無法可靠涵蓋。
    **改用偵測 + 重試**：如果失敗的錯誤訊息是這個特定的「檔案在
    /kaggle/input/ 下找不到」，代表 dataset 這次真的還沒掛好，
    值得重推 kernel 再試一次；若是別的錯誤（腳本本身的邏輯錯誤、
    套件裝不起來等），重推沒有意義，直接判定失敗比較省 quota。
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


def push_kernel_only() -> bool:
    """只重推 kernel，沿用 kaggle_work/ 裡已經上傳過的 dataset。

    build_payload() 只在**開始**新的 push 時清掉 kaggle_work/，跑完不會自動
    清除，所以這裡可以直接對同一份 kaggle_work/ 再喊一次 kernel push，
    不必重新打包、重新上傳 dataset（省時間也省頻寬）。
    """
    r = run(["kaggle", "kernels", "push", "-p", str(HERE / "kaggle_work")])
    print(r.stdout[-1500:], flush=True)
    if r.returncode != 0:
        print(r.stderr[-1500:], flush=True)
    return r.returncode == 0


def pull(kid: str, label: str) -> Path:
    out = HERE / "kaggle_results" / label
    out.mkdir(parents=True, exist_ok=True)
    run(["kaggle", "kernels", "output", kid, "-p", str(out)])
    return out


def main() -> None:
    print(f"Kaggle 佇列執行器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}",
          flush=True)
    while True:
        done = read_done()
        pending = [it for it in read_queue() if it["label"] not in done]
        if not pending:
            print("Kaggle 佇列已清空，結束。", flush=True)
            return
        item = pending[0]
        label = item["label"]
        kid = kernel_id(label)
        print(f"\n{'='*70}\n[{datetime.now():%H:%M:%S}] 開始 {label}"
              f"\n  {item['script']} {item['args']}\n  kernel: {kid}"
              f"\n{'='*70}", flush=True)
        t0 = time.time()
        status = "push_failed"
        if push(item):
            status = poll_until_done(kid)
            pull(kid, label)
            # dataset 掛載時序不穩，偵測到這個特定失敗模式就重推 kernel
            # （沿用同一份已上傳的 dataset，不重新打包），最多重試 4 次、
            # 間隔遞增（60/120/240/480 秒）。真正的程式錯誤不會因為重推
            # 而改變結果，是這個特定失敗模式才值得重試。
            backoffs = [60, 120, 240, 480]
            attempt = 0
            while status == "error" and is_mount_race_failure(label) \
                    and attempt < len(backoffs):
                wait_s = backoffs[attempt]
                attempt += 1
                print(f"  偵測到 dataset 掛載時序問題（非程式錯誤），"
                      f"{wait_s}s 後重推 kernel（第 {attempt} 次重試）",
                      flush=True)
                time.sleep(wait_s)
                if push_kernel_only():
                    status = poll_until_done(kid)
                    pull(kid, label)
                else:
                    status = "error"
                    break
        secs = time.time() - t0
        mark_done(label, status, secs)
        print(f"[{datetime.now():%H:%M:%S}] {label} 結束：{status}"
              f"（{secs/60:.1f} 分）\n", flush=True)


if __name__ == "__main__":
    main()
