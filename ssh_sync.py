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
     還沒結束」在整個執行期間是同一件事，不需要額外的心跳機制。同時
     touch 一個 results/.start_<label> 時間戳記標記檔，給 pull() 分辨
     這次工作寫出的檔案用（見 pull() 說明）。
  3. poll：讀 <label>.exit（存在就是跑完了，內容是退出碼）或用
     <label>.pid 探測行程是否還活著。
  4. pull：只抓 results/ 底下比 .start_<label> 標記檔新的檔案回本機
     （按 label 過濾，見 pull() 說明），存到本機 cloud_results/<worker>/
     <label>/ 底下，不同 label 不會混在一起。
  5. kill：逾時或需要放棄一個工作時，用 pid 檔確認並終止遠端行程——
     SSH worker 是持久機器，沒真的殺掉行程就釋放槽位、讓佇列重派新
     工作到同一台機器，會跟還沒死的舊行程搶同一份 remote_dir。

**這台 VM 只需要「讀」GitHub repo，不需要「寫」**——結果檔一律由本機
scp 拉回來，本機決定要不要 commit，VM 上不放任何能推送的 git 憑證。
完整的 VM 端建置步驟（裝 Python 套件、設定唯讀 Deploy Key）見
docs/reference/CLOUD_WORKERS.md，不在這支程式裡重複一份。

**用法**（跟 kaggle_sync.py 對稱）：
    python ssh_sync.py push  --worker gcp1
    python ssh_sync.py run   --worker gcp1 --script profile_lowmass.py --args "--procs 8 --n-syn 40000" --label lowmass1
    python ssh_sync.py status --worker gcp1 --label lowmass1
    python ssh_sync.py pull  --worker gcp1 --label lowmass1
    python ssh_sync.py kill  --worker gcp1 --label lowmass1
"""
from __future__ import annotations

import argparse
import hashlib
import shlex
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
    # remote_dir／branch／url 全部組進遠端 shell 指令字串前先 shlex.quote()——
    # remote_dir 來自本機 ssh_workers.json（使用者自己填的登記檔），branch
    # 來自 CLI 參數，兩者理論上都是「本機使用者自己打的」，但一旦這支腳本
    # 被 cloud_queue.py 這類自動化流程呼叫、或有人在路徑裡不小心留了空白／
    # 特殊字元，不加引號會讓字串被拆成多個指令甚至被當成額外指令執行
    # （CWE-78）。加 shlex.quote() 不改變正常值（純英數路徑）的行為，只在
    # 有特殊字元時提供防護，成本為零。
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    q_branch = shlex.quote(branch)
    check = ssh_workers.remote_run(
        w, f"test -d {q_dir}/.git && echo YES || echo NO", timeout=30)
    if check.returncode != 0:
        print(f"  無法連線到 worker：{(check.stderr or check.stdout).strip()[:300]}")
        return False
    if "YES" in check.stdout:
        cmd = (f"cd {q_dir} && git fetch origin && "
              f"git checkout {q_branch} && git pull --ff-only")
    else:
        url = _repo_ssh_url()
        cmd = (f"git clone --branch {q_branch} {shlex.quote(url)} {q_dir}")
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
    """補齊 worker 上缺少或內容過期的靜態資料（isochrones/、data/ 底下
    不進版控的那些檔案）——用 kaggle_sync.py 已經維護的同一份白名單，
    不重複列一次清單（清單漏更新是這個專案踩過的坑，見 kaggle_sync.py
    NEEDED_ISOCHRONE_GLOBS 旁邊 2026-08-10 的說明）。只上傳「本機有、
    worker 上還沒有／內容不同」的檔案——這是跟 Kaggle 每次全部重傳的
    關鍵差異，VM 是持久機器，資料傳過一次就不必再傳。

    **用 sha256 比對內容，不是只看檔案存不存在**（2026-08-22 CodeRabbit
    review 訂正）：原本只查 `test -f`，只要遠端路徑上有同名檔案就跳過
    上傳——如果本機的 isochrone 網格或 `data/` 底下的檔案換了新版本
    （內容變了、檔名沒變，例如重新產生同一份 errmodel.npz），worker 上
    的舊檔案會永遠不會被換掉，之後在這台 worker 上跑的每個工作都在用
    過期資料算，而且不會有任何錯誤訊息——這正是這個專案已經吃過虧的
    「靜默用錯資料」那類 bug，不是理論風險。sha256 要在本機和遠端都算
    一次，比對雜湊值而不是比對檔案大小／mtime——mtime 在 scp 傳輸後不
    一定保留，大小相同但內容不同的機率雖低但不是零。
    """
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    ssh_workers.remote_run(
        w, f"mkdir -p {q_dir}/data {q_dir}/isochrones", timeout=30)
    ok = True
    for sub, names in (("data", kaggle_sync.NEEDED_DATA_FILES),
                       ("isochrones", kaggle_sync.NEEDED_ISOCHRONE_GLOBS)):
        for name in names:
            local = HERE / sub / name
            if not local.exists():
                continue    # 本機也沒有就不管——跟 kaggle_sync.py 的行為一致
            remote_path = f"{remote_dir}/{sub}/{name}"
            q_remote_path = shlex.quote(remote_path)
            # sha256sum 印不出東西（檔案不存在）就當作「跟本機不同」，
            # 一律走上傳分支——不存在本來就該上傳，跟內容不同是同一個
            # 處置，不用分兩種情況判斷。
            check = ssh_workers.remote_run(
                w, f"sha256sum {q_remote_path} 2>/dev/null | cut -d' ' -f1",
                timeout=30)
            remote_hash = check.stdout.strip() if check.returncode == 0 else ""
            if remote_hash and remote_hash == _sha256(local):
                continue
            print(f"  上傳 {sub}/{name}（worker 上缺少或內容不同）...")
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
    # label／script／remote_dir 都是識別字串，用 shlex.quote() 包起來，
    # 避免 cloud_queue.txt 裡的值（逗號分隔欄位，來源是人手工編輯的佇列
    # 檔）不小心帶了空白或 shell 特殊字元時被當成額外指令執行。
    # args 刻意不整串 quote——它本來就是要被遠端 shell 拆成多個獨立參數
    # 的（例如 "--procs 8 --n-syn 40000"），quote 整串會讓它變成單一個
    # 參數傳給 python3，語意就錯了。但這代表 args 裡的內容（尤其是單引號）
    # 仍然會被遠端 shell 解讀，所以外層改用 shlex.quote(inner) 而不是手動
    # 拼 `'{inner}'`——這樣即使 args 裡剛好出現單引號，也不會提早跳出
    # bash -c 的引號、讓後面的字串被當成獨立指令執行。
    q_label = shlex.quote(label)
    q_script = shlex.quote(script)
    q_dir = shlex.quote(remote_dir)
    # results/.start_<label> 是給 pull() 用的時間戳記標記檔（不是真正的
    # 結果檔）——worker 是持久機器，results/ 目錄是所有 label 共用的，
    # 一個 worker 可能陸續跑過很多個 label；pull() 靠這個標記檔的 mtime
    # 分辨「這次要抓的是哪個 label 剛寫出來的檔案」，不然整包 scp 回來
    # 會把其他 label（甚至上一輪同一個 label 的舊檔案）也混進來，見
    # pull() 的說明。這裡在啟動工作的同一個指令裡建立，時間點早於
    # python3 開始寫任何結果，之後 pull() 只抓比它新的檔案就不會漏。
    inner = (f"echo $$ > logs/{q_label}.pid; "
            f"python3 -u {q_script} {args}; "
            f"echo $? > logs/{q_label}.exit")
    cmd = (f"cd {q_dir} && mkdir -p logs results && "
          f"rm -f logs/{q_label}.exit logs/{q_label}.pid && "
          f"touch results/.start_{q_label} && "
          f"setsid bash -c {shlex.quote(inner)} "
          f"> logs/{q_label}.out 2> logs/{q_label}.err < /dev/null &")
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
    q_label = shlex.quote(label)
    q_dir = shlex.quote(remote_dir)
    cmd = (
        f"cd {q_dir} 2>/dev/null || exit 9; "
        f"if [ -f logs/{q_label}.exit ]; then "
        f"  echo EXIT:$(cat logs/{q_label}.exit); "
        f"elif [ -f logs/{q_label}.pid ] && kill -0 $(cat logs/{q_label}.pid) "
        f"2>/dev/null; then echo RUNNING; "
        f"elif [ -f logs/{q_label}.pid ]; then echo CRASHED; "
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


def kill(worker_name: str, label: str) -> bool:
    """終止 worker 上 label 對應的背景行程（先 SIGTERM，等一下還活著
    再 SIGKILL），回傳「能不能確認行程已經不在跑了」——不是「有沒有送出
    信號」。呼叫端（cloud_queue.py 的逾時處理）要拿這個回傳值決定能不能
    安全釋放槽位：**不能確認就不能放，放了會讓佇列在同一個 worker 上
    重派一個新工作，跟還沒真正死掉的舊行程搶同一份 remote_dir、同一批
    logs/results 檔案**，這是 SSH worker（持久機器，沒有 Kaggle 那種
    容器隔離）特有的風險，Kaggle 那邊逾時直接放槽位沒有這個問題。"""
    workers = ssh_workers.load_workers()
    w = workers[worker_name]
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    q_label = shlex.quote(label)
    cmd = (
        f"cd {q_dir} 2>/dev/null || exit 9; "
        f"test -f logs/{q_label}.pid || {{ echo NO_PID; exit 0; }}; "
        f"pid=$(cat logs/{q_label}.pid); "
        f"kill -TERM $pid 2>/dev/null; "
        f"sleep 2; "
        f"kill -0 $pid 2>/dev/null && kill -KILL $pid 2>/dev/null; "
        f"sleep 1; "
        f"kill -0 $pid 2>/dev/null && echo STILL_ALIVE || echo KILLED"
    )
    try:
        r = ssh_workers.remote_run(w, cmd, timeout=30)
    except subprocess.TimeoutExpired:
        return False    # 連逾時都連不上，無法確認，保守回傳「沒殺掉」
    if r.returncode != 0:
        return False    # 連不上 worker，同樣無法確認
    out = r.stdout.strip()
    # NO_PID：從沒建立過 pid 檔或已經被 poll() 判定過的舊工作，沒有
    # 行程可殺，等同已經確認不在跑。KILLED：兩次訊號後確認真的死了。
    return out in ("NO_PID", "KILLED")


def pull(worker_name: str, label: str) -> bool:
    """把 worker 上屬於這個 label 的結果抓回本機。

    本機端按 `{worker}/{label}` 分開存放（跟 kaggle_queue.py 的
    `kaggle_results/{label}/` 對稱），不會因為同一個 worker 陸續跑過
    多個 label 而互相覆蓋。

    **遠端端也要按 label 過濾，不能整包 scp `results/` 回來**
    （2026-08-22 CodeRabbit review 訂正）：SSH worker 是持久機器，
    `results/` 是所有在這台機器上跑過的 label 共用的目錄，跟 Kaggle
    每個 kernel 各自有獨立輸出容器不一樣。原本的寫法每次 pull 都把
    整個 results/ 目錄複製回來，如果同一個 worker 上還有其他 label
    的結果（甚至只是還沒清掉的舊檔案），會被一起抓進這次 pull 的資料夾，
    事後分不出哪個檔案屬於哪次工作——這正是這個專案已經吃過虧的「結果
    混在一起分不清楚」那類 bug 的同一種模式。改成用 run() 啟動時建立的
    `results/.start_<label>` 時間戳記標記檔，只挑「比它新」的檔案傳
    回來（`find ... -newer`），排除標記檔本身。
    """
    workers = ssh_workers.load_workers()
    w = workers[worker_name]
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    q_label = shlex.quote(label)
    out_dir = RESULTS_DIR / worker_name / label
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

    marker = f"results/.start_{label}"
    find_cmd = (
        f"cd {q_dir} && test -f {shlex.quote(marker)} && "
        f"find results -type f -newer {shlex.quote(marker)} "
        f"! -name '.start_*'")
    r = ssh_workers.remote_run(w, find_cmd, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        print(f"  {label} 目前沒有新的 results/ 檔案可抓（標記檔遺失或"
             f"工作還沒寫出東西），略過", flush=True)
        return ok
    remote_files = [ln for ln in r.stdout.strip().splitlines() if ln.strip()]
    for rel in remote_files:
        dest = out_dir / "results" / Path(rel).relative_to("results")
        dest.parent.mkdir(parents=True, exist_ok=True)
        rr = subprocess.run(
            ssh_workers.scp_base(w) +
            [f"{w['user']}@{w['host']}:{remote_dir}/{rel}", str(dest)],
            capture_output=True, text=True, timeout=1800)
        if rr.returncode != 0:
            print(f"  抓 {rel} 失敗：{rr.stderr.strip()[:300]}")
            ok = False
    if ok:
        print(f"  結果存到 {out_dir / 'results'}（{len(remote_files)} 個檔案）")
        # 成功抓完才清掉標記檔——清早了、萬一這次有檔案抓失敗要重試，
        # 下一輪 pull 就會找不到基準時間點，把整批檔案都當成「新的」
        # 重抓一次（多花一點頻寬，但不會漏抓，比留著標記檔更安全）。
        ssh_workers.remote_run(
            w, f"cd {q_dir} && rm -f {shlex.quote(marker)}", timeout=30)
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

    p5 = sub.add_parser("kill", help="終止 worker 上一個背景工作")
    p5.add_argument("--worker", required=True)
    p5.add_argument("--label", required=True)
    p5.set_defaults(func=lambda a: sys.exit(0 if kill(a.worker, a.label) else 1))

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
