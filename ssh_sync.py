# -*- coding: utf-8 -*-
"""把本專案的計算工作丟到 SSH 遠端節點（GCP／Oracle／任何有 SSH 的 Linux
VM）背景執行，跟 kaggle_sync.py 是同一個角色，但架構故意不一樣——
理由見 ssh_workers.py 開頭的說明（SSH worker 是持久機器，不必每次
重新打包整個資料集）。

**運作方式**：
  1. push：確保 worker 上有這個 repo 的最新程式碼（第一次 git clone，
     之後 git pull——`data/` 底下的檔案跟著這一步進來，因為它們本來
     就有進版控），確保 isochrones/ 這類真的被 .gitignore 排除、
     git pull 帶不到的靜態資料都在，缺什麼才補傳什麼。
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

import gcp_vm_lifecycle       # GCP worker 派工前自動開機，見該模組說明
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


def _rm_marker_best_effort(w: dict, q_dir: str, marker: str) -> None:
    """刪掉 pull() 用的 `.start_<label>` 標記檔，逾時／連線問題不當一回事——
    這一步只是清潔，失敗頂多留下一個孤兒標記檔（下次同一個 label 的
    run() 一開始就會重新 touch 覆寫），不值得讓 pull() 因為這步失敗。"""
    try:
        ssh_workers.remote_run(
            w, f"cd {q_dir} && rm -f {shlex.quote(marker)}", timeout=30)
    except subprocess.TimeoutExpired:
        pass


# 2026-08-23 CodeRabbit review 訂正：worker 名稱 -> 遠端 $HOME 絕對路徑，
# 每個 worker 在這個行程裡只透過 SSH 查一次、快取在這裡，後面所有函式
# 一律用 _get_worker() 拿已經展開好 `~` 的 worker dict，不要各自重新
# 呼叫 ssh_workers.load_workers() 再各自處理——理由見 _expand_tilde()
# 的說明。2026-08-23 第二輪：原本只展開 remote_dir，後來新增的
# python_bin 欄位（見 ssh_workers.py）一樣可能填 `~/...` 形式，是同一個
# `shlex.quote()` 會擋住 `~` 展開的問題，改成共用同一個展開函式跟同一份
# $HOME 快取，不要重新發明第二套。
_HOME_CACHE: dict[str, str] = {}


def _get_home(worker_name: str, w: dict) -> str:
    """查一次遠端 $HOME 並快取，查不到回傳空字串（呼叫端要自行決定
    退回原樣是否可接受，見 _expand_tilde()）。

    **只快取查詢成功的結果**（2026-08-23 CodeRabbit review：實際踩到
    才發現）：原本不管查詢成功或失敗都寫進 `_HOME_CACHE`，若第一次
    呼叫剛好遇到暫時性的連線問題（例如 SSH 逾時），空字串會被永久
    快取住——`cloud_queue.py` 是常駐行程，之後**這一輪程序活著的
    期間**，同一個 worker 的每一次 `poll()`／`pull()` 都會沿用這個
    空字串、印警告、讓 `remote_dir` 裡的 `~` 保留原樣，導致
    `cd '~/m45_membership'` 每次都失敗（`~` 被 `shlex.quote()` 包住
    後不會被 shell 展開，見上面 `_expand_tilde()` 的說明）——遠端
    工作本身其實還在正常跑，但本機再也偵測不到它跑完，也永遠拉不回
    結果，而且不會有任何看起來像「壞掉」的錯誤訊息，只有反覆印的
    警告，容易被當成雜訊忽略。改成只有查詢真的成功才寫進快取，失敗
    不快取，下一次呼叫會重新嘗試查詢。"""
    if worker_name in _HOME_CACHE:
        return _HOME_CACHE[worker_name]
    try:
        r = ssh_workers.remote_run(w, "echo $HOME", timeout=15)
    except subprocess.TimeoutExpired:
        print(f"  （查詢 {worker_name} 的 $HOME 逾時 15 秒）")
        r = None
    home = ""
    if r is not None:
        if r.returncode == 0:
            home = r.stdout.strip()
        else:
            # 2026-08-23：原本失敗時完全不印 stderr，警告訊息只說「查不到」，
            # 看不出真正原因（連線被拒、逾時、認證失敗都長一樣），除錯只能
            # 用另一個互動式 shell 手動重現——已經踩到一次「手動測都成功、
            # 常駐行程卻每次都失敗」的情況，查不出差異在哪，補上這行。
            print(f"  （查詢 {worker_name} 的 $HOME 失敗，returncode="
                 f"{r.returncode}，stderr={r.stderr.strip()[:200]!r}）")
    if home:
        _HOME_CACHE[worker_name] = home
    return home


def _expand_tilde(worker_name: str, w: dict, path: str) -> str:
    """把 `path` 開頭的 `~` 展開成遠端 home 目錄的絕對路徑，不是 `~` 開頭
    就原樣傳回。

    **為什麼一定要在這裡展開，不能讓 `~` 原樣留著交給後面的呼叫點各自
    處理**：push()／run()／poll()／kill()／pull() 每個呼叫點都會對
    remote_dir（跟現在的 python_bin）做 `shlex.quote()` 再組進遠端指令
    字串，這是對的（避免特殊字元／CWE-78，見 ensure_repo() 的說明）——
    但 `shlex.quote("~/m45_membership")` 的結果是整段用單引號包起來
    （`'~/m45_membership'`），而 `~` 展開是 shell 的**詞法**規則，只在
    參數完全沒被引號包住時才會生效；一旦被單引號包住，bash 會把它當成
    字面上名叫 `~` 的目錄，`cd '~/m45_membership'` 會因為找不到這個字面
    目錄直接失敗。等於每個呼叫點各自 quote 的當下都重新踩進同一個 bug。
    改成在每個 worker 第一次用到時，就用一次 SSH 查出遠端 home 目錄、
    把 `~` 換成絕對路徑，之後快取起來給所有呼叫點共用——絕對路徑本身
    不含 `~`，後面不管哪個呼叫點怎麼 `shlex.quote()` 都不影響展開的結果。
    """
    if path != "~" and not path.startswith("~/"):
        return path
    home = _get_home(worker_name, w)
    if not home:
        print(f"  警告：無法查詢 {worker_name} 的遠端 home 目錄，"
             f"{path!r} 的 ~ 保留原樣，後續指令可能因此失敗")
        return path
    return home if path == "~" else home + path[1:]


def _get_worker(worker_name: str) -> dict:
    """回傳 worker 設定字典，`remote_dir`／`python_bin` 都已經解析成
    絕對路徑（見 `_expand_tilde()`）。除了 push() 因為要組「worker 不
    存在」的友善錯誤訊息、額外自己查了一次 `ssh_workers.load_workers()`
    之外，其餘函式一律從這裡拿 worker dict，不要繞過去重新解析。"""
    workers = ssh_workers.load_workers()
    w = dict(workers[worker_name])
    w["remote_dir"] = _expand_tilde(worker_name, w, w["remote_dir"])
    w["python_bin"] = _expand_tilde(worker_name, w, w["python_bin"])
    return w


def _repo_ssh_url() -> str:
    r = subprocess.run(["git", "remote", "get-url", "origin"],
                       cwd=str(HERE), capture_output=True, text=True,
                       creationflags=ssh_workers.CREATE_NO_WINDOW)
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
    # 2026-08-24 修正：這兩個 remote_run() 呼叫原本沒接
    # subprocess.TimeoutExpired——本機網路短暫異常（實測發生過，見
    # cloud_queue.py 對應的說明）時逾時會讓例外直接往上炸，讓
    # ensure_repo() 沒機會走到自己的「回傳 False」錯誤處置，一路往上
    # 讓呼叫端也沒接住。雖然 cloud_queue.py 現在的主迴圈有整段 try 兜底
    # 不會讓整支程式崩潰，但這裡直接接住能維持 push() 原本「失敗就回傳
    # False」的正確語意，錯誤處置在正確的層級發生，不必依賴外層兜底。
    try:
        check = ssh_workers.remote_run(
            w, f"test -d {q_dir}/.git && echo YES || echo NO", timeout=30)
    except subprocess.TimeoutExpired:
        print("  無法連線到 worker：連線逾時（30 秒）")
        return False
    if check.returncode != 0:
        print(f"  無法連線到 worker：{(check.stderr or check.stdout).strip()[:300]}")
        return False
    if "YES" in check.stdout:
        cmd = (f"cd {q_dir} && git fetch origin && "
              f"git checkout {q_branch} && git pull --ff-only")
    else:
        url = _repo_ssh_url()
        cmd = (f"git clone --branch {q_branch} {shlex.quote(url)} {q_dir}")
    try:
        r = ssh_workers.remote_run(w, cmd, timeout=180)
    except subprocess.TimeoutExpired:
        print("  git 同步逾時（180 秒），本機網路或 VM 可能異常")
        return False
    print(r.stdout.strip())
    if r.returncode != 0:
        print(f"  git 同步失敗：{r.stderr.strip()[:500]}")
        if "publickey" in (r.stderr or ""):
            print("  → 看起來是 Deploy Key 沒設好，見 "
                 "docs/reference/CLOUD_WORKERS.md")
        return False
    return True


def ensure_static_data(w: dict) -> bool:
    """補齊 worker 上缺少或內容過期的靜態資料（isochrones/ 底下不進版控
    的那些網格檔）——用 kaggle_sync.py 已經維護的同一份白名單，不重複
    列一次清單（清單漏更新是這個專案踩過的坑，見 kaggle_sync.py
    NEEDED_ISOCHRONE_GLOBS 旁邊 2026-08-10 的說明）。只上傳「本機有、
    worker 上還沒有／內容不同」的檔案——這是跟 Kaggle 每次全部重傳的
    關鍵差異，VM 是持久機器，資料傳過一次就不必再傳。

    **只處理 isochrones/，不處理 data/**（2026-08-23 修正，使用者實測
    踩到才發現）：`kaggle_sync.NEEDED_DATA_FILES` 列的三個檔案
    （`cmd_members.csv`／`errmodel.npz`／`selection.npz`）其實**都有進
    版控**，跟 isochrones/ 網格檔（真的被 .gitignore 排除、git pull
    帶不到）不是同一類。原本這裡把兩份清單一視同仁，各自 scp 上去——
    但 `ensure_repo()` 的 `git pull` 早就已經帶來這三個檔案的最新版本，
    scp 再蓋一次是多餘的，而且如果本機工作目錄剛好對這幾個檔案有還沒
    commit 的本地修改（多人協作、剛好有其他 session 動過），scp 上去的
    內容會跟 git 記錄的版本不一致，讓 VM 的 git 工作目錄多一筆沒 commit
    的差異——下次 `git pull --ff-only` 若剛好遇到這個檔案在 GitHub 上
    也被改過，可能因為本機修改擋在前面而失敗。改成只信任 git 本身帶來
    的版本，不再用 scp 覆寫任何有進版控的檔案。

    **用 sha256 比對內容，不是只看檔案存不存在**（2026-08-22 CodeRabbit
    review 訂正）：原本只查 `test -f`，只要遠端路徑上有同名檔案就跳過
    上傳——如果本機的 isochrone 網格換了新版本（內容變了、檔名沒變），
    worker 上的舊檔案會永遠不會被換掉，之後在這台 worker 上跑的每個
    工作都在用過期資料算，而且不會有任何錯誤訊息——這正是這個專案已經
    吃過虧的「靜默用錯資料」那類 bug，不是理論風險。sha256 要在本機和
    遠端都算一次，比對雜湊值而不是比對檔案大小／mtime——mtime 在 scp
    傳輸後不一定保留，大小相同但內容不同的機率雖低但不是零。
    """
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    try:
        ssh_workers.remote_run(w, f"mkdir -p {q_dir}/isochrones", timeout=30)
    except subprocess.TimeoutExpired:
        print("  建立 isochrones/ 目錄逾時（30 秒），本機網路或 VM 可能異常")
        return False
    ok = True
    # 2026-08-24 CodeRabbit review 訂正：worker／網路真的不通時，原本會對
    # 白名單裡每一個檔案各自等一輪 sha256sum 逾時（120 秒）再等一輪 scp
    # 上傳逾時（1800 秒），累加起來單次 push() 可能卡住
    # 「檔案數 × 1930 秒」——這段時間裡 cloud_queue.py 主迴圈的
    # `for name, kind in workers.items()` 是同步跑的，等於這個 worker
    # 連不上的這段期間，其他 worker（包含還連得上的）全部要排隊等它，
    # 不是只有這個 worker 自己受影響。第一次遇到連線層級的逾時
    # （sha256sum 或 scp 逾時，不是「檔案內容不同」這種正常業務判斷）
    # 就直接放棄這個 worker 剩下的檔案，當這一輪 push() 失敗，下一輪
    # `cloud_queue.py` 重新嘗試——比每個檔案都賭一次「這次會不會通」
    # 便宜太多，且不影響「已經連得上」時的正常行為。
    connection_ok = True
    for sub, names in (("isochrones", kaggle_sync.NEEDED_ISOCHRONE_GLOBS),):
        for name in names:
            if not connection_ok:
                ok = False
                break
            local = HERE / sub / name
            if not local.exists():
                continue    # 本機也沒有就不管——跟 kaggle_sync.py 的行為一致
            remote_path = f"{remote_dir}/{sub}/{name}"
            q_remote_path = shlex.quote(remote_path)
            # sha256sum 印不出東西（檔案不存在）就當作「跟本機不同」，
            # 一律走上傳分支——不存在本來就該上傳，跟內容不同是同一個
            # 處置，不用分兩種情況判斷。
            #
            # 2026-08-23 CodeRabbit review 訂正：遠端 sha256sum 逾時
            # （原本 30 秒，大檔案在慢速/忙碌的 VM 上算雜湊可能不夠）
            # 原本沒接 subprocess.TimeoutExpired，會讓整支腳本直接炸掉、
            # 卡在這個檔案就不會再往下檢查其他檔案。逾時跟「查不到雜湊」
            # 同樣視為「跟本機不同」處理，一律走上傳分支——誤判成不同
            # 頂多多傳一次，比讓例外整個中斷同步、或誤判成相同讓過期
            # 資料繼續留著沒人發現安全。逾時本身順便拉長到 120 秒，
            # 降低大檔案在正常情況下也被誤判逾時的機率。
            try:
                check = ssh_workers.remote_run(
                    w, f"sha256sum {q_remote_path} 2>/dev/null | cut -d' ' -f1",
                    timeout=120)
                remote_hash = check.stdout.strip() if check.returncode == 0 else ""
            except subprocess.TimeoutExpired:
                print(f"  查詢 {sub}/{name} 遠端雜湊逾時，判斷連線本身"
                     f"有問題，放棄這個 worker 剩下的檔案，下一輪重試")
                connection_ok = False
                ok = False
                continue
            if remote_hash and remote_hash == _sha256(local):
                continue
            print(f"  上傳 {sub}/{name}（worker 上缺少或內容不同）...")
            try:
                r = subprocess.run(
                    ssh_workers.scp_base(w) +
                    [str(local),
                     f"{w['user']}@{w['host']}:{remote_dir}/{sub}/{name}"],
                    capture_output=True, text=True, timeout=1800,
                    creationflags=ssh_workers.CREATE_NO_WINDOW)
            except subprocess.TimeoutExpired:
                print(f"  上傳 {sub}/{name} 逾時（30 分鐘），判斷連線本身"
                     f"有問題，放棄這個 worker 剩下的檔案，下一輪重試")
                connection_ok = False
                ok = False
                continue
            if r.returncode != 0:
                print(f"  上傳失敗：{r.stderr.strip()[:300]}")
                ok = False
    return ok


def push(worker_name: str, branch: str = "main") -> bool:
    workers = ssh_workers.load_workers()
    if worker_name not in workers:
        print(f"找不到 worker {worker_name!r}，登記檔裡有：{list(workers)}")
        return False
    w = _get_worker(worker_name)
    # 填了 GCP 生命週期欄位的 worker，派工前先確保 VM 是開著的（見
    # gcp_vm_lifecycle.py）——沒填的 worker 這裡永遠回傳 True，不影響
    # 既有行為。回傳 False 時語意跟其他連線失敗一樣：這一輪 push()
    # 失敗，cloud_queue.py 既有的重試機制下一輪會再試一次，不用在這裡
    # 額外處理。
    if not gcp_vm_lifecycle.ensure_running(w):
        return False
    print(f"[{worker_name}] 同步程式碼...")
    if not ensure_repo(w, branch):
        return False
    print(f"[{worker_name}] 檢查靜態資料...")
    return ensure_static_data(w)


def run(worker_name: str, script: str, args: str, label: str) -> bool:
    """啟動背景工作。回傳是否成功送出（不等它跑完——跟 kaggle_sync.py
    的 push 一樣，啟動之後由 cloud_queue.py 或 status 指令另外去查）。"""
    w = _get_worker(worker_name)
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
    q_python = shlex.quote(w.get("python_bin") or "python3")
    # results/.start_<label> 是給 pull() 用的時間戳記標記檔（不是真正的
    # 結果檔）——worker 是持久機器，results/ 目錄是所有 label 共用的，
    # 一個 worker 可能陸續跑過很多個 label；pull() 靠這個標記檔的 mtime
    # 分辨「這次要抓的是哪個 label 剛寫出來的檔案」，不然整包 scp 回來
    # 會把其他 label（甚至上一輪同一個 label 的舊檔案）也混進來，見
    # pull() 的說明。這裡在啟動工作的同一個指令裡建立，時間點早於
    # python3 開始寫任何結果，之後 pull() 只抓比它新的檔案就不會漏。
    inner = (f"echo $$ > logs/{q_label}.pid; "
            f"{q_python} -u {q_script} {args}; "
            f"echo $? > logs/{q_label}.exit")
    cmd = (f"cd {q_dir} && mkdir -p logs results && "
          f"rm -f logs/{q_label}.exit logs/{q_label}.pid && "
          f"touch results/.start_{q_label} && "
          f"setsid bash -c {shlex.quote(inner)} "
          f"> logs/{q_label}.out 2> logs/{q_label}.err < /dev/null &")
    # 2026-08-23 實測發現：這個指令本身已經把工作丟到背景並立刻返回
    # （setsid ... &），但送出指令這個動作本身（開一條新 SSH 連線、
    # 認證、執行）偶爾就是要超過 30 秒才回得來——不是工作卡住，是
    # 「送出指令」這一步本身慢。原本沒接 TimeoutExpired，逾時會讓
    # 整支程式當場崩潰，即使背景工作其實已經成功啟動（用 poll() 查
    # 得到，見附帶驗證）。改成逾時視為「送出去了但沒等到確認」，
    # 回傳 True 讓呼叫端用 status()／poll() 另外查證，而不是直接崩潰
    # 掉整個派工流程——寧可事後查證，不要讓一次連線變慢就中止全部。
    try:
        r = ssh_workers.remote_run(w, cmd, timeout=60)
    except subprocess.TimeoutExpired:
        print(f"  送出指令逾時（60 秒），工作可能已經在背景啟動，"
             f"用 status 查證：ssh_sync.py status --worker {worker_name} "
             f"--label {label}", flush=True)
        return True
    if r.returncode != 0:
        print(f"  啟動失敗：{(r.stderr or r.stdout).strip()[:300]}")
        return False
    return True


def poll(worker_name: str, label: str) -> str:
    """回傳 "running"／"complete"／"error"／"missing"／"unknown"，
    跟 kaggle_queue.py 的 probe_kernel_status() 用同一套詞彙，讓
    cloud_queue.py 可以共用同一套上層判斷邏輯。"""
    w = _get_worker(worker_name)
    remote_dir = w["remote_dir"]
    q_label = shlex.quote(label)
    q_dir = shlex.quote(remote_dir)
    # 2026-08-23 CodeRabbit review 訂正：kill -0 原本查的是 <label>.pid
    # 記的那個 PID 本身（bash 的 PID）活不活著。啟動指令是
    # `setsid bash -c '...'`，setsid 會讓這個 bash 成為新 session／
    # process group 的 leader，所以它的 PID 同時也是整個 process group
    # 的 PGID；bash -c 裡面接著跑的 `python3 -u ...` 是同一個 bash
    # 底下的前景指令，沒有另外呼叫 setpgid，預設會沿用同一個 PGID。
    # 用「負的 PID」（`-$pid`）signal 的目標就變成整個 process group
    # 而不是單一行程——查活著與否也一併改成查整個 group，這樣即使
    # bash 本身已經結束但 group 裡還有孤兒行程殘留（例如下面 kill()
    # 曾經只殺掉 bash、python3 變孤兒的那種情況），也查得出來還沒真的
    # 收乾淨，不會誤判成已經結束。
    cmd = (
        f"cd {q_dir} 2>/dev/null || exit 9; "
        f"if [ -f logs/{q_label}.exit ]; then "
        f"  echo EXIT:$(cat logs/{q_label}.exit); "
        f"elif [ -f logs/{q_label}.pid ] && kill -0 -$(cat logs/{q_label}.pid) "
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
    w = _get_worker(worker_name)
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    q_label = shlex.quote(label)
    # 2026-08-23 CodeRabbit review 訂正：原本只對 <label>.pid 記的那個
    # PID（setsid 底下 bash 的 PID）送信號——bash 收到 SIGTERM／SIGKILL
    # 死掉之後，它底下用一般前景指令跑的 python3（以及 python3 自己開的
    # 子行程，例如 multiprocessing worker）不會被連帶終止，會變成孤兒行程
    # 繼續在背景跑，變成 kill() 回報「已確認終止」但其實遠端運算還在
    # 繼續佔用 CPU 的假象。setsid 讓 bash 成為新 process group 的 leader，
    # 它的 PID 同時是 PGID，所以改成對「負的 PID」送信號（`-$pid`），
    # 目標就是整個 process group（bash 本身＋python3＋python3 的子行程，
    # 只要沒有另外呼叫 setpgid 改變自己的 group，預設都在同一個 group
    # 裡），才能真的把這個工作啟動的所有行程一起收乾淨。
    cmd = (
        f"cd {q_dir} 2>/dev/null || exit 9; "
        f"test -f logs/{q_label}.pid || {{ echo NO_PID; exit 0; }}; "
        f"pid=$(cat logs/{q_label}.pid); "
        f"kill -TERM -$pid 2>/dev/null; "
        f"sleep 2; "
        f"kill -0 -$pid 2>/dev/null && kill -KILL -$pid 2>/dev/null; "
        f"sleep 1; "
        f"kill -0 -$pid 2>/dev/null && echo STILL_ALIVE || echo KILLED"
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

    **已知未解決的限制（2026-08-23 CodeRabbit review 指出，決定不動這裡
    的實作，記在這裡而不是假裝解決了）**：時間戳只能分辨「比標記檔新」，
    分不出「是哪個 label 產生的」。如果同一個 worker 上**同時**有兩個
    label 在跑（例如你手動開兩個終端機分別對同一個 worker 呼叫
    `ssh_sync.py run`），一個 label 的 `pull()` 可能會把另一個 label
    在同一時間窗口寫出的檔案也一起抓進來。真正的修法是讓每個 label
    寫進各自專屬的遠端輸出目錄，但這需要改動每支計算腳本本身寫死的
    `results/` 輸出路徑（`fit_real.py`／`profile_lowmass.py` 等全部
    腳本、以及本機／Kaggle 佇列既有的慣例都假設這個路徑），牽動面遠超過
    這支同步工具，不在這次的範圍內處理。**目前的防線是流程上的，不是
    程式上的**：`cloud_queue.py` 的槽位設計保證同一個 worker 同一時間
    只會有一個槽位在跑（見 `main()` 的 `slots` 字典，一個 worker 名稱
    對應一個槽位），透過 `cloud_queue.py` 派工不會踩到這個問題；只有
    繞過佇列、手動對同一個 worker 平行呼叫 `run()` 才會踩到，見
    `docs/reference/CLOUD_WORKERS.md` 的對應警告。
    """
    w = _get_worker(worker_name)
    remote_dir = w["remote_dir"]
    q_dir = shlex.quote(remote_dir)
    q_label = shlex.quote(label)
    out_dir = RESULTS_DIR / worker_name / label
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "results").mkdir(parents=True, exist_ok=True)
    ok = True
    for f in (f"logs/{label}.out", f"logs/{label}.err", f"logs/{label}.exit"):
        try:
            r = subprocess.run(
                ssh_workers.scp_base(w) +
                [f"{w['user']}@{w['host']}:{remote_dir}/{f}", str(out_dir / f)],
                capture_output=True, text=True, timeout=60,
                creationflags=ssh_workers.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            print(f"  抓 {f} 逾時，略過（不影響下面 results/ 的抓取）")
            continue
        if r.returncode != 0:
            print(f"  抓 {f} 失敗（可能該檔案不存在）：{r.stderr.strip()[:200]}")

    marker = f"results/.start_{label}"
    q_marker = shlex.quote(marker)
    # 2026-08-24 第四輪複查訂正：原本用 `test -f marker && find ...`，
    # marker 不存在時 `test -f` 失敗會讓整條 `&&` 鏈以非零狀態結束，跟
    # 下面「查詢本身失敗（逾時／連線斷）」共用同一個 `r.returncode != 0`
    # 分支——但下面 `if not r.stdout.strip()` 那段的註解原本就宣稱這個
    # 分支涵蓋「標記檔遺失」的情況，實際上永遠到不了那裡（marker 遺失
    # 時根本沒有 stdout 可看，在更早的 returncode 分支就 return 了），
    # 註解描述的行為與程式碼實際行為不一致。改用 shell if/else 讓
    # 「marker 不存在」單獨輸出一個可辨識的字串，只要 SSH 能連上、cd
    # 成功，這個分支的 returncode 就固定是 0，不會再被誤判成連線失敗
    # 見 LIMITATIONS.md D18 對這個 bug 完整後果的說明（主要風險是
    # cloud_queue.py 的主迴圈把這個查詢失敗一路重試到 MAX_WAIT_HOURS
    # 逾時，再把一個其實早就成功跑完的工作誤標成 "timeout"）。
    find_cmd = (
        f"cd {q_dir} 2>/dev/null || exit 9; "
        f"if [ -f {q_marker} ]; then "
        f"find results -type f -newer {q_marker} ! -name '.start_*'; "
        f"else echo __NO_MARKER__; fi")
    # 2026-08-23 CodeRabbit review 第三輪：查詢本身失敗（逾時／連線斷）
    # 跟「查詢成功但沒有新檔案」是兩回事，先前兩者都直接回傳初始值
    # ok=True，cloud_queue.py 會把「根本沒查到」誤判成「查了、確定沒
    # 新結果」而寫進 done-log，之後不會再重試下載，結果可能就這樣
    # 遺失。只有查詢真的成功且沒有新檔案，才算「查了、確定沒有」。
    try:
        r = ssh_workers.remote_run(w, find_cmd, timeout=30)
    except subprocess.TimeoutExpired:
        print(f"  查詢 {label} 的 results/ 逾時，保留工作供下一輪重試",
              flush=True)
        return False
    if r.returncode != 0:
        print(f"  查詢 {label} 的 results/ 失敗：{r.stderr.strip()[:200]}",
              flush=True)
        return False
    out = r.stdout.strip()
    if out == "__NO_MARKER__":
        # 標記檔真的不存在（不是查詢失敗）。原本這裡無條件當成「一定是
        # 已經成功 pull 過一次」——但 __NO_MARKER__ 本身分辨不出「真的
        # 已經成功 pull 過」跟「marker 因為其他原因遺失／從沒建立過」
        # 這兩種情況，無條件回傳成功等於在沒有本機證據的情況下就讓
        # cloud_queue.py 把這個工作標成 "ok"，結果可能根本沒被下載過
        # （2026-08-25 CodeRabbit review 抓到）。改成先查本機是否真的
        # 已經有這個 label 的結果檔——那才是「已經成功 pull 過」唯一
        # 站得住腳的證據；沒有本機檔案就不能假設成功，回傳 False 讓
        # 呼叫端保留這個工作、下一輪再查（可能只是 marker 意外遺失，
        # 遠端結果其實還在，需要人工介入確認，而不是悄悄放棄）。
        local_results = out_dir / "results"
        has_local_copy = local_results.is_dir() and any(local_results.iterdir())
        if has_local_copy:
            print(f"  {label} 的標記檔（{marker}）不存在，但本機已有這個"
                 f"label 的結果檔，視為先前已經成功 pull 過、這次沒有"
                 f"新結果（見 LIMITATIONS.md D18）", flush=True)
            return ok
        print(f"  {label} 的標記檔（{marker}）不存在，且本機找不到這個"
             f"label 先前 pull 過的結果檔——無法確認結果是否真的已下載，"
             f"不當成功，保留這個工作供下一輪重試或人工檢查（見"
             f"LIMITATIONS.md D18）", flush=True)
        return False
    if not out:
        # 2026-08-23 修正：沒有新檔案可抓時，原本直接 return，漏了清掉
        # 標記檔——這裡沒有「這次抓失敗要保留基準點重試」的顧慮（根本
        # 沒有東西在抓，下面 if ok: 清標記檔的理由同樣適用），留著不清
        # 只會讓 results/ 底下累積一堆孤兒 .start_<label> 檔案（實測
        # smoke test 這種不寫 results/ 的腳本就會踩到）。清掉失敗
        # （連線問題）不影響回傳值，反正下次 run() 一開始就會重新
        # touch 覆寫，不清也不會造成錯誤結果，只是不夠乾淨。
        print(f"  {label} 目前沒有新的 results/ 檔案可抓（工作還沒寫出"
             f"東西），略過", flush=True)
        _rm_marker_best_effort(w, q_dir, marker)
        return ok
    remote_files = [ln for ln in out.splitlines() if ln.strip()]
    # 理由同 ensure_static_data()：連線層級的逾時發生一次，就別讓剩下
    # 每個檔案都各自再賭一次 30 分鐘（2026-08-24 CodeRabbit review）。
    connection_ok = True
    for rel in remote_files:
        if not connection_ok:
            ok = False
            break
        dest = out_dir / "results" / Path(rel).relative_to("results")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            rr = subprocess.run(
                ssh_workers.scp_base(w) +
                [f"{w['user']}@{w['host']}:{remote_dir}/{rel}", str(dest)],
                capture_output=True, text=True, timeout=1800,
                creationflags=ssh_workers.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            print(f"  抓 {rel} 逾時（30 分鐘），判斷連線本身有問題，"
                 f"放棄剩下的檔案，下一輪重試")
            connection_ok = False
            ok = False
            continue
        if rr.returncode != 0:
            print(f"  抓 {rel} 失敗：{rr.stderr.strip()[:300]}")
            ok = False
    if ok:
        print(f"  結果存到 {out_dir / 'results'}（{len(remote_files)} 個檔案）")
        # 成功抓完才清掉標記檔——清早了、萬一這次有檔案抓失敗要重試，
        # 下一輪 pull 就會找不到基準時間點，把整批檔案都當成「新的」
        # 重抓一次（多花一點頻寬，但不會漏抓，比留著標記檔更安全）。
        _rm_marker_best_effort(w, q_dir, marker)
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
