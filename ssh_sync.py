# -*- coding: utf-8 -*-
"""把本專案的計算工作丟到 SSH 遠端節點（GCP／Oracle／任何有 SSH 的 Linux
VM）背景執行，跟 kaggle_sync.py 是同一個角色，但架構故意不一樣——
理由見 ssh_workers.py 開頭的說明（SSH worker 是持久機器，不必每次
重新打包整個資料集）。

**運作方式**：
  1. push：確保 worker 上有這個 repo 的最新程式碼（第一次 git clone，
     之後 git pull），確保靜態資料（data/、isochrones/）都在，缺什麼
     才補傳什麼。
  2. run：用 `setsid bash -c '...; echo $? > logs/<label>.exit'` 讓
     腳本在 SSH 連線斷掉後繼續在背景跑，同時把它包在 bash -c 裡讓
     bash（不是 python3 本身）的 PID 寫進 <label>.pid——bash 只有在
     python3 跑完才會往下執行 echo，所以「這個 PID 還活著」跟「工作
     還沒結束」在整個執行期間是同一件事，不需要額外的心跳機制。
  3. poll：讀 <label>.exit（存在就是跑完了，內容是退出碼）或用
     <label>.pid 探測行程是否還活著。
  4. pull：把 worker 上的 results/ 用 scp 抓回本機。

**這台 VM 只需要「讀」GitHub repo，不需要「寫」**——結果檔一律由本機
scp 拉回來，本機決定要不要 commit，VM 上不放任何能推送的 git 憑證。
完整的 VM 端建置步驟（裝 Python 套件、設定唯讀 Deploy Key）見
docs/reference/CLOUD_WORKERS.md，不在這支程式裡重複一份。

**用法**（跟 kaggle_sync.py 對稱）：
    python ssh_sync.py push  --worker gcp1
    python ssh_sync.py run   --worker gcp1 --script profile_lowmass.py --args "--procs 8 --n-syn 40000" --label lowmass1
    python ssh_sync.py status --worker gcp1 --label lowmass1
    python ssh_sync.py pull  --worker gcp1 --label lowmass1
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import kaggle_sync           # 重用既有的靜態資料白名單，不重複列一份
import ssh_workers

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "cloud_results"

# git@github.com:... 形式的 URL 才吃得到 SSH Deploy Key；本機的 origin
# 通常是 https://github.com/... （方便本機用既有的 GitHub 登入），
# VM 端需要 SSH 形式。這裡從本機 origin 自動換算，不必請使用者手動填。
_GITHUB_HTTPS_PREFIX = "https://github.com/"


def _repo_ssh_url() -> str:
    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=str(HERE), capture_output=True, text=True)
    url = r.stdout.strip()
    if url.startswith(_GITHUB_HTTPS_PREFIX):
        path = url[len(_GITHUB_HTTPS_PREFIX):]
        if path.endswith(".git"):
            path = path[:-4]
        return f"git@github.com:{path}.git"
    return url    # 已經是 ssh 形式或其他 remote，原樣使用


def ensure_repo(w: dict, branch: str = "main") -> bool:
    """VM 上沒有這個 repo 就 clone，有的話就 fetch+checkout+pull。

    回傳是否成功。失敗最常見的原因是 VM 還沒設定 Deploy Key——這裡
    直接把 git 的錯誤訊息印出來，不吞掉，因為那通常就是缺金鑰的
    明確提示（Permission denied (publickey)）。
    """
    remote_dir = w["remote_dir"]
    check = ssh_workers.remote_run(
        w, f"test -d {remote_dir}/.git && echo YES || echo NO", timeout=30)
    if check.returncode != 0:
        print(f"  無法連線到 worker：{(check.stderr or check.stdout).strip()[:300]}")
        return False
    if "YES" in check.stdout:
        cmd = (f"cd {remote_dir} && git fetch origin && "
              f"git checkout {branch} && git pull --ff-only")
    else:
        url = _repo_ssh_url()
        cmd = (f"git clone --branch {branch} {url} {remote_dir}")
    r = ssh_workers.remote_run(w, cmd, timeout=180)
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"  git 同步失敗：{r.stderr.strip()[:500]}")
        if "publickey" in (r.stderr or ""):
            print("  → 看起來是 Deploy Key 沒設好，見 "
                 "docs/reference/CLOUD_WORKERS.md")
        return False
    return True


def ensure_static_data(w: dict) -> bool:
    """補齊 worker 上缺少的靜態資料（isochrones/、data/ 底下不進版控
    的那些檔案）——用 kaggle_sync.py 已經維護的同一份白名單，不重複
    列一次清單（清單漏更新是這個專案踩過的坑，見 kaggle_sync.py
    NEEDED_ISOCHRONE_GLOBS 旁邊 2026-08-10 的說明）。只上傳「本機有、
    worker 上還沒有」的檔案——這是跟 Kaggle 每次全部重傳的關鍵差異，
    VM 是持久機器，資料傳過一次就不必再傳。
    """
    remote_dir = w["remote_dir"]
    ssh_workers.remote_run(
        w, f"mkdir -p {remote_dir}/data {remote_dir}/isochrones", timeout=30)
    ok = True
    for sub, names in (("data", kaggle_sync.NEEDED_DATA_FILES),
                       ("isochrones", kaggle_sync.NEEDED_ISOCHRONE_GLOBS)):
        for name in names:
            local = HERE / sub / name
            if not local.exists():
                continue    # 本機也沒有就不管——跟 kaggle_sync.py 的行為一致
            check = ssh_workers.remote_run(
                w, f"test -f {remote_dir}/{sub}/{name} && echo YES || echo NO",
                timeout=30)
            if check.returncode == 0 and "YES" in check.stdout:
                continue
            print(f"  上傳 {sub}/{name}（worker 上還沒有）...")
            r = subprocess.run(
                ssh_workers.scp_base(w) +
                [str(local), f"{w['user']}@{w['host']}:{remote_dir}/{sub}/{name}"],
                capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                print(f"  上傳失敗：{r.stderr.strip()[:300]}")
                ok = False
    return ok


def push(worker_name: str, branch: str = "main") -> bool:
    workers = ssh_workers.load_workers()
    if worker_name not in workers:
        print(f"找不到 worker {worker_name!r}，登記檔裡有：{list(workers)}")
        return False
    w = workers[worker_name]
    print(f"[{worker_name}] 同步程式碼...")
    if not ensure_repo(w, branch):
        return False
    print(f"[{worker_name}] 檢查靜態資料...")
    return ensure_static_data(w)


def run(worker_name: str, script: str, args: str, label: str) -> bool:
    """啟動背景工作。回傳是否成功送出（不等它跑完——跟 kaggle_sync.py
    的 push 一樣，啟動之後由 cloud_queue.py 或 status 指令另外去查）。"""
    workers = ssh_workers.load_workers()
    w = workers[worker_name]
    remote_dir = w["remote_dir"]
    inner = (f"echo $$ > logs/{label}.pid; "
            f"python3 -u {script} {args}; "
            f"echo $? > logs/{label}.exit")
    cmd = (f"cd {remote_dir} && mkdir -p logs results && "
          f"rm -f logs/{label}.exit logs/{label}.pid && "
          f"setsid bash -c '{inner}' "
          f"> logs/{label}.out 2> logs/{label}.err < /dev/null &")
    r = ssh_workers.remote_run(w, cmd, timeout=30)
    if r.returncode != 0:
        print(f"  啟動失敗：{(r.stderr or r.stdout).strip()[:300]}")
        return False
    return True


def poll(worker_name: str, label: str) -> str:
    """回傳 "running"／"complete"／"error"／"missing"／"unknown"，
    跟 kaggle_queue.py 的 probe_kernel_status() 用同一套詞彙，讓
    cloud_queue.py 可以共用同一套上層判斷邏輯。"""
    workers = ssh_workers.load_workers()
    w = workers[worker_name]
    remote_dir = w["remote_dir"]
    cmd = (
        f"cd {remote_dir} 2>/dev/null || exit 9; "
        f"if [ -f logs/{label}.exit ]; then "
        f"  echo EXIT:$(cat logs/{label}.exit); "
        f"elif [ -f logs/{label}.pid ] && kill -0 $(cat logs/{label}.pid) "
        f"2>/dev/null; then echo RUNNING; "
        f"elif [ -f logs/{label}.pid ]; then echo CRASHED; "
        f"else echo MISSING; fi"
    )
    try:
        r = ssh_workers.remote_run(w, cmd, timeout=30)
    except subprocess.TimeoutExpired:
        return "unknown"
    if r.returncode != 0:
        return "unknown"           # 連不上／查不到，不能當成任何確定結論
    out = r.stdout.strip()
    if out.startswith("EXIT:"):
        code = out[len("EXIT:"):].strip()
        return "complete" if code == "0" else "error"
    if out == "RUNNING":
        return "running"
    if out == "CRASHED":
        # 行程消失但沒有 .exit 檔——多半是 VM 重開機／OOM killer／
        # 手動砍掉，拿不到真正的退出碼，一律當失敗處理讓佇列往下走，
        # 不要無限期卡在這個槽位等一個不會再更新的狀態。
        return "error"
    if out == "MISSING":
        return "missing"
    return "unknown"


def pull(worker_name: str, label: str) -> bool:
    workers = ssh_workers.load_workers()
    w = workers[worker_name]
    remote_dir = w["remote_dir"]
    out_dir = RESULTS_DIR / worker_name
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    ok = True
    for f in (f"logs/{label}.out", f"logs/{label}.err", f"logs/{label}.exit"):
        r = subprocess.run(
            ssh_workers.scp_base(w) +
            [f"{w['user']}@{w['host']}:{remote_dir}/{f}", str(out_dir / f)],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            print(f"  抓 {f} 失敗（可能該檔案不存在）：{r.stderr.strip()[:200]}")
    r = subprocess.run(
        ssh_workers.scp_base(w) +
        ["-r", f"{w['user']}@{w['host']}:{remote_dir}/results/.",
         str(out_dir / "results")],
        capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        print(f"  抓 results/ 失敗：{r.stderr.strip()[:300]}")
        ok = False
    else:
        print(f"  結果存到 {out_dir / 'results'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("push", help="同步程式碼與靜態資料到 worker")
    p1.add_argument("--worker", required=True)
    p1.add_argument("--branch", default="main")
    p1.set_defaults(func=lambda a: sys.exit(0 if push(a.worker, a.branch) else 1))

    p2 = sub.add_parser("run", help="在 worker 上背景啟動一支腳本")
    p2.add_argument("--worker", required=True)
    p2.add_argument("--script", required=True)
    p2.add_argument("--args", default="")
    p2.add_argument("--label", required=True)
    p2.set_defaults(func=lambda a: sys.exit(
        0 if run(a.worker, a.script, a.args, a.label) else 1))

    p3 = sub.add_parser("status")
    p3.add_argument("--worker", required=True)
    p3.add_argument("--label", required=True)
    p3.set_defaults(func=lambda a: print(poll(a.worker, a.label)))

    p4 = sub.add_parser("pull")
    p4.add_argument("--worker", required=True)
    p4.add_argument("--label", required=True)
    p4.set_defaults(func=lambda a: sys.exit(0 if pull(a.worker, a.label) else 1))

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
