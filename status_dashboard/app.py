# -*- coding: utf-8 -*-
"""M45 IMF 專案主控板：整合傳統法／前向模型／PDMF→IMF／穩健性診斷四大類
的「哪個步驟底下有哪些程式、程式在幹嘛、現在跑到哪」，取代原本要翻十幾份
`.md` 文件或一直口頭問 Claude 才能拼出全貌的做法。

**設計原則（跟使用者一起定案，2026-08-24）**：
1. 形式選輕量本地網頁，沿用這個使用者其他專案一貫的
   `py app.py → http://localhost:PORT` 模式，不新增框架依賴——內建的
   `http.server` 就夠用，沒有表單提交、沒有需要框架處理的東西。
2. 每次瀏覽器整理頁面，都會對「正在跑」的工作做一次即時探測（重用
   `cloud_queue.py` 的 `probe_slot()`），换取最準確的即時狀態；15 秒內
   重複整理的話沿用快取，不是為了打折這個決策，只是防止手滑連點 F5
   洗爆 worker。
3. 「階段 → 步驟 → 腳本」的對照表（見 stage_map.py）是手動維護的——這個
   專案沒有任何機器可讀的來源能自動生成傳統法／PDMF→IMF／診斷類的分類
   結構（前向模型 5 步勉強可以從 config.toml 的區段名稱對照，但也沒有
   全自動化，第一版先手動建好）。新增任務或腳本要記得回來
   `stage_map.py` 加一筆，這是本設計已知、刻意接受的維護成本，不是
   忘了做。

**已知的路徑落差**：`cloud_queue.py`／`ssh_sync.py` 已經 merge 進這個
repo（PR #121），但目前活著在跑的派工器行程工作目錄還是
`m45_cloud_workers_wt` worktree，`cloud_queue.txt`／
`logs/cloud_queue_done.txt`／`logs/cloud_queue.lock` 這些檔案只存在那裡。
`CLOUD_QUEUE_ROOT` 這個常數就是為了這個落差而存在——等使用者把 worktree
收斂回 main，把這一行改成指向 `REPO_ROOT` 即可，不用動其他程式碼
（`cloud_queue.py` 自己的路徑常數是用它自己的 `__file__` 位置算出來的）。

用法：
    py app.py
瀏覽器開 http://localhost:8866/
"""
from __future__ import annotations

import ast
import ctypes
import html
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import quote_plus, urlsplit

if sys.platform == "win32":
    # 2026-08-26 使用者實際遇到：git.exe（跟 ssh.exe）偶爾會跳出
    # Windows 的「應用程式無法正常啟動...請按一下確定」對話框
    # （0xc0000142）——這台機器是 ARM64、git.exe 是 x64 版靠模擬層跑，
    # 這個 repo 又同時有好幾個 worktree（cloud_queue.py 的、這支主控板
    # 的）在頻繁打同一份共用 .git 物件庫，比一般狀況更容易踩到 git.exe
    # 自己的初始化競態。這支主控板是沒人盯著、雙擊桌面捷徑就丟到背景跑
    # 的服務，子行程崩潰跳互動對話框只會卡在那邊等人點，沒有意義。
    # SetErrorMode(SEM_NOGPFAULTERRORBOX) 讓這個行程跟它開的所有子行程
    # 崩潰時直接安靜結束、不跳對話框——`_git()`／`probe_live()` 這些
    # 呼叫端本來就有檢查 returncode／逾時／例外並優雅降級（顯示「同步
    # 失敗」而不是硬湊資料），這裡只是不要讓 Windows 額外插一個要人手動
    # 關掉的對話框進來。跟 cloud_queue.py 同一輪修的同一個坑。
    ctypes.windll.kernel32.SetErrorMode(0x0002)  # SEM_NOGPFAULTERRORBOX

HERE = Path(__file__).resolve().parent

# 桌面捷徑用 pyw（pythonw.exe）完全隱藏啟動（見這個使用者的
# desktop-shortcut-preference 慣例）——pyw 底下 sys.stdout/stderr 是
# None，任何 print()／traceback 都會直接炸掉整個伺服器。這裡統一轉存到
# 一個 log 檔，不用在每個 print() 呼叫前面各自加 `if sys.stdout:` 判斷。
if sys.stdout is None:
    _log_f = open(HERE / "dashboard_console.log", "a",
                 encoding="utf-8", buffering=1)
    sys.stdout = _log_f
    sys.stderr = _log_f

REPO_ROOT = HERE.parent
# 已知的路徑落差（見檔頭說明）：cloud_queue.py 已經 merge 進這個 repo，
# 但目前活著在跑的派工器工作目錄還是另一個 worktree。**不能硬編死路徑**
# （2026-08-25 CodeRabbit review：原本寫死作者本機的絕對路徑，換一台機器
# checkout 就會 import 失敗，伺服器起不來，桌面捷徑也只會開一個連不上的
# 網址）——改成環境變數，預設值是這個 repo 自己（多數情況下 worktree
# 收斂回 main 之後就是這樣），沒設環境變數、且這個 repo 自己也沒有
# cloud_queue.py 時才需要手動指定。啟動當下就驗證路徑對不對，錯了直接
# 印清楚的錯誤訊息，不要等 import 失敗才留一串看不懂的 traceback。
CLOUD_QUEUE_ROOT = Path(os.environ.get("CLOUD_QUEUE_ROOT", str(REPO_ROOT)))
if not (CLOUD_QUEUE_ROOT / "cloud_queue.py").is_file():
    raise RuntimeError(
        f"找不到 cloud_queue.py：{CLOUD_QUEUE_ROOT}\n"
        "這台機器上 cloud_queue.py 的實際位置可能跟這個 repo 不同（例如"
        "還沒把 worktree 收斂回 main），設定環境變數 CLOUD_QUEUE_ROOT "
        "指到正確的目錄再重新啟動。")

sys.path.insert(0, str(CLOUD_QUEUE_ROOT))
import cloud_queue  # noqa: E402  重用它的 read_queue/read_done/probe_slot/鎖檔邏輯，不重寫
import ssh_sync  # noqa: E402  _get_worker() 會把 remote_dir 的 ~ 展開成絕對路徑
import ssh_workers  # noqa: E402  remote_run()

sys.path.insert(0, str(HERE))
from stage_map import STAGES  # noqa: E402

PORT = 8866
# 監聽位址。預設 127.0.0.1＝只有這台電腦自己連得到，任何人在自己電腦
# 手動 `py app.py` 都不會不小心對外暴露。
#
# **2026-08-31 這裡的設計繞了一圈，記錄下來避免以後又搞錯一次**：
# 8/30 曾經把這個開關整個拿掉、寫死 127.0.0.1，理由是「這個頁面沒有
# 密碼保護，留一個能開放的環境變數本身就是後門」——但部署到協調 VM、
# 實際用 `gcloud compute start-iap-tunnel` 測試時發現**連不上**
# （`[4003: 'failed to connect to backend']`）：IAP tunnel 連的是 VM
# 網卡本身，接不到只綁 127.0.0.1（等於「只有這台機器自己」）的服務。
#
# 重新對照 SSH 的實際做法才發現想錯了：sshd 本來就是綁 `0.0.0.0`（所有
# 網卡）監聽，它的安全性從來不是靠「只聽自己」，而是靠**防火牆只放行
# IAP 的固定來源網段 35.235.240.0/20**（見
# docs/reference/CLOUD_WORKERS_IAP_SETUP.md）——這台協調 VM 的防火牆
# 規則 `allow-iap-ssh` 已經把 8866 也加進去，一樣限定只有 IAP 網段能連。
# 所以「比照 SSH 那樣走 IAP tunnel」正確的做法是**主控板也綁
# `0.0.0.0`，靠同一條防火牆規則守門**，不是綁 127.0.0.1。
#
# **這跟先前拿掉的 dashboard-lan-access 分支不一樣**：那支是讓任何一位
# 隊友在自己電腦上設這個環境變數、搭配 Tailscale 對外開——隊友自己的
# 電腦沒有這條 GCP 防火牆規則保護，等於真的對外露埠。這裡只有協調 VM
# 的 systemd 服務會設這個環境變數（見 dashboard.service 的
# Environment= 那行），且只有這台機器有對應的防火牆限制，兩者不是同一
# 回事。
HOST = os.environ.get("M45_DASH_HOST", "127.0.0.1")
LOCK = HERE / "dashboard.lock"  # 見 acquire_lock()——防止雙擊桌面捷徑（或
                                # 舊行程還沒真的死透就又被啟動一次）疊出
                                # 多個行程搶同一個埠（2026-08-31，使用者
                                # 實際遇到 4 個殘留行程、其中一個殺不掉）
PROBE_CACHE_TTL = 15  # 秒；同一個 label 這段時間內重複整理不重打 SSH
PROBE_MAX_WORKERS = 4    # 同時最多幾個 worker 一起探測
PROBE_DEADLINE_S = 25    # 這次整理頁面，即時探測合計最多等這麼久——
                         # 小於 ssh_sync.poll() 自己單次的 30 秒逾時，
                         # 確保一個連不上的 worker 不會拖累整頁的回應
                         # 時間（2026-08-25 CodeRabbit review）
GIT_SYNC_TIMEOUT_S = 8   # git fetch/pull 單次逾時；離線時最多讓頁面
                         # 多等這麼久，不要無限卡住
_probe_cache: dict[str, tuple[float, dict]] = {}
_restart_pending = False  # 見 sync_repo_from_github()／_self_restart()
GIT_SYNC_COOLDOWN_S = 60  # 這段時間內重複整理頁面，不重打 git（2026-08-26
                          # 使用者遇到 git.exe 偶爾崩潰彈出「應用程式無法
                          # 正常啟動」對話框後加的）——這個 repo 同時有
                          # cloud_queue.py 的 worktree 每 60 秒自己也在打
                          # 同一份共用 .git 物件庫，主控板這邊按到重新
                          # 整理就再連打 4～7 個 git 呼叫，兩邊疊在一起
                          # 對同一份物件庫的併發壓力，是這類初始化競態
                          # 更容易發生的成因之一。冷卻時間刻意跟
                          # cloud_queue.py 的同步週期同一個量級。
_sync_cache: tuple[float, dict] | None = None


# ==================================================================
# 資料層
# ==================================================================

def read_docstring(rel_path: str, external: bool = False,
                   upstream: str | None = None) -> str:
    """讀一支腳本檔頭的 module docstring，原文照搬，不重寫一份說明。

    `external=True` 代表這是**第三方原始碼**（例如 pyUPMASK，見 .gitignore
    「第三方原始碼：用 clone 取得，不納入本 repo」那段）——這種檔案本來
    就不在版控裡，本機沒有 clone 過就是找不到，**這是預期行為，不是路徑
    搬動的錯誤**。原本一律回「路徑可能已經搬動」會把這種正常情況誤報成
    壞掉的索引，讓人跑去找一個根本不存在的 bug（2026-08-26 修正）。
    """
    path = REPO_ROOT / rel_path
    if not path.exists():
        if external:
            src = f"，原始出處：{upstream}" if upstream else ""
            return (f"（第三方套件，依專案慣例不納入版控，需自行 clone 到 "
                    f"{rel_path}{src}。這裡沒有說明是正常的，不是索引壞掉。）")
        return (f"（本機（協調 VM 的 checkout）目前找不到這個檔案："
                f"{rel_path}——可能是路徑搬動了，也可能只是本機還沒同步到"
                f"剛推上 GitHub 的新檔案，過一輪自動同步通常就會出現。上面"
                f"的連結一律連到 GitHub，不受本機有沒有這個檔案影響。）")
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return f"（讀取失敗，語法錯誤：{e}）"
    doc = ast.get_docstring(tree)
    return doc or "（這支腳本沒有檔頭說明）"


def parse_cloud_done() -> dict[str, dict]:
    """{label: {status, secs, worker, when}}，來自
    cloud_queue.py 的 `logs/cloud_queue_done.txt`（5 欄，含 worker）。
    同一 label 多筆時取最後一筆（append-only，最新的在最後）。"""
    records: dict[str, dict] = {}
    if cloud_queue.DONE.exists():
        for line in cloud_queue.DONE.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 5:
                continue
            label, status, secs, worker, when = parts[:5]
            records[label] = {"status": status, "secs": secs,
                              "worker": worker, "when": when}
    return records


def parse_local_done() -> dict[str, dict]:
    """{label: {status, secs, when}}，來自本機（已停用的）`run_queue.py`
    留下的 `logs/queue_done.txt`（4 欄，沒有 worker 欄）。"""
    records: dict[str, dict] = {}
    path = REPO_ROOT / "logs" / "queue_done.txt"
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            label, status, secs, when = parts[:4]
            records[label] = {"status": status, "secs": secs, "when": when}
    return records


def dispatcher_alive() -> tuple[bool, int | None]:
    """跟 restart_queue_on_boot.ps1 同一套判準：讀鎖檔 PID，查行程還活不活。"""
    if not cloud_queue.LOCK.exists():
        return False, None
    try:
        pid = int(cloud_queue.LOCK.read_text().strip())
    except (ValueError, OSError):
        return False, None
    alive = cloud_queue._pid_alive(pid)
    return bool(alive), pid


# 見 iap_tunnel_manager.py 同一行的說明：CREATE_NO_WINDOW 只存在於
# Windows，直接寫 subprocess.CREATE_NO_WINDOW 在 Linux 上會炸
# AttributeError——2026-08-31 部署到協調 VM（Debian）才踩到，本機
# （Windows）測試從來沒踩過。getattr 給預設值 0 讓非 Windows 平台
# 安全地變成無操作。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args: str) -> subprocess.CompletedProcess:
    """呼叫 git.exe。**一定要帶 `creationflags=CREATE_NO_WINDOW`**：這台
    機器上這個坑已經在 `ssh_workers.py` 的 `remote_run()` 踩過一次
    （2026-08-26，見那支檔案的說明）——`sync_repo_from_github()` 每次
    整理頁面都連續呼叫這支好幾次（fetch／rev-list／status／有時候還有
    pull），伺服器又是用 `pyw`（沒有主控台）跑的，沒有這個旗標的話
    Windows 會幫每一次呼叫各跳一個 git.exe 主控台視窗再消失，變成
    使用者桌面上一串連續閃爍的黑視窗。"""
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=GIT_SYNC_TIMEOUT_S,
                          creationflags=_CREATE_NO_WINDOW)


# 2026-08-31 使用者要求：以後任何新推上 GitHub 的程式，都要能自動被
# 主控板讀取到，不要等人手動回來補 stage_map.py 才看得到。真正的
# 「自動分類進正確的階段/步驟」做不到（stage_map.py 檔頭已經解釋過：
# 沒有機器可讀的來源能判斷一支新腳本屬於傳統法還是 PDMF→IMF 第幾步，
# 這是語意判斷，不是格式判斷）——但「至少讓它出現在主控板上、能點進去
# 看說明」可以做到，而且不需要等分類決定好。做法：用 `git ls-files`
# 列出這個 repo 目前追蹤的所有 .py 檔（只看真的推上 GitHub 的，不是
# 本機隨手建立的暫存檔），扣掉 stage_map.py 裡已經分類過的路徑跟明確
# 排除的目錄，剩下的就是「存在、但還沒被分類進任何階段/步驟」的程式，
# 顯示在頁面最後一個獨立區塊，一樣可以點開看檔頭說明——之後要分類，
# 人只要把路徑從這個清單搬進 stage_map.py 對應的步驟即可，不會漏掉。
_UNINDEXED_EXCLUDE_PREFIXES = (
    "_archive/",       # 已封存的舊工作，刻意不算「現役」程式
    "status_dashboard/",  # 主控板自己，不是專案的分析程式
    "pyUPMASK/",       # 第三方套件，即使某台機器 clone 了也不算本專案程式
)
_UNINDEXED_EXCLUDE_NAMES = {"__init__.py"}  # 空的套件標記檔，沒有內容好看


def discover_unindexed_scripts() -> list[str]:
    """回傳「已經推上 GitHub、但 stage_map.py 裡沒有任何步驟提到」的
    .py 檔路徑清單，已排序。git 呼叫失敗（離線、逾時）時回傳空清單，
    不讓這個附加功能拖垮整頁——這個區塊本來就是錦上添花，不是關鍵
    路徑。"""
    try:
        result = _git("ls-files", "*.py")
    except (subprocess.TimeoutExpired, OSError):
        return []
    if result.returncode != 0:
        return []
    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}

    indexed: set[str] = set()
    for stage in STAGES:
        for step in stage["steps"]:
            indexed.update(step.get("scripts", []))

    unindexed = [
        p for p in tracked
        if p not in indexed
        and Path(p).name not in _UNINDEXED_EXCLUDE_NAMES
        and not p.startswith(_UNINDEXED_EXCLUDE_PREFIXES)
    ]
    return sorted(unindexed)


def sync_repo_from_github() -> dict:
    """`_sync_repo_from_github_uncached()` 加上冷卻時間的外層——見那支
    函式的說明，這裡只處理「多久打一次」。"""
    global _sync_cache
    now = time.monotonic()
    if _sync_cache and now - _sync_cache[0] < GIT_SYNC_COOLDOWN_S:
        return _sync_cache[1]
    result = _sync_repo_from_github_uncached()
    _sync_cache = (now, result)
    return result


def _sync_repo_from_github_uncached() -> dict:
    """每次冷卻時間到了整理頁面，就嘗試把這個 repo 從 `origin/main`
    同步到最新——別人（或別的 session）push 新程式碼、改 docstring、
    加新腳本之後，不用手動 `git pull`，重新整理主控板就看得到
    （2026-08-25 使用者要求）。

    跟 `cloud_queue.py` 的 `sync_queue_file()` 同一個精神：安全第一，
    失敗就跳過用本機現有內容，不讓網路問題擋住整頁。

    **只有「目前在 main 分支、且沒有任何未提交的修改」才真的執行
    `git pull --ff-only`**：這個 repo 是多個 agent／多個 session共用的
    工作目錄（見 CONTRIBUTING.md），常常有人正在某個 feature 分支上做
    一半的事——貿然自動 pull 可能把別人的未提交修改弄丟，或在錯的分支
    上硬套 main 的內容。條件不滿足時只回報「落後幾個 commit」，不動手，
    讓使用者自己判斷要不要手動同步。

    `self_updated` 這個欄位特別標記「這次同步有沒有動到
    `status_dashboard/` 自己的程式碼」——`app.py`／`stage_map.py` 是
    Python 模組，一旦匯入就固定在記憶體裡，改了檔案不會自動重新匯入，
    要真的重啟這個行程才會套用新版（見 `_self_restart()`）。"""
    global _restart_pending
    result = {"synced": False, "ahead": 0, "behind": 0, "branch": None,
             "dirty": None, "error": None, "self_updated": False}
    try:
        result["branch"] = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

        fetch = _git("fetch", "origin", "main")
        if fetch.returncode != 0:
            result["error"] = f"git fetch 失敗：{fetch.stderr.strip()[:200]}"
            return result

        counts = _git("rev-list", "--left-right", "--count", "HEAD...origin/main")
        if counts.returncode == 0 and counts.stdout.split():
            ahead, behind = counts.stdout.split()
            result["ahead"], result["behind"] = int(ahead), int(behind)

        # --untracked-files=no：只在意「有沒有修改過已追蹤的檔案」，不
        # 管工作目錄裡有沒有未追蹤的雜項檔案——2026-09-02 實際踩到：
        # acquire_lock() 自己寫的 status_dashboard/dashboard.lock、
        # 別人手滑留下的殘餘檔案，都會被算進舊版的 --porcelain（含
        # 未追蹤），讓這個判斷永遠卡在「髒」，自動同步從此完全失效、
        # 而且沒有任何錯誤訊息——「落後幾個 commit 不動手」是刻意設計
        # 的保護（怕蓋掉別人真正的未提交修改），但未追蹤的雜項檔案
        # 不构成「別人正在改的東西」，不該一起算進去。
        result["dirty"] = bool(
            _git("status", "--porcelain", "--untracked-files=no").stdout.strip())

        if (result["branch"] == "main" and not result["dirty"]
                and result["behind"] > 0):
            old_head = _git("rev-parse", "HEAD").stdout.strip()
            pull = _git("pull", "--ff-only", "origin", "main")
            if pull.returncode == 0:
                result["synced"] = True
                result["behind"] = 0
                changed = _git("diff", "--name-only", old_head, "HEAD",
                               "--", "status_dashboard")
                result["self_updated"] = bool(changed.stdout.strip())
                if result["self_updated"]:
                    _restart_pending = True
            else:
                result["error"] = f"git pull 失敗：{pull.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        result["error"] = "git 操作逾時（可能沒有網路）"
    except Exception as e:  # noqa: BLE001 — 同步失敗不能讓整頁掛掉
        result["error"] = str(e)
    return result


def _self_restart() -> None:
    """用新的行程重啟整支程式，讓 `git pull` 剛拉下來的
    `status_dashboard/` 新程式碼真的生效，然後結束目前這份（同一個
    Python 行程沒辦法重新匯入已經匯入過的模組）。用背景執行緒延遲一下
    才動手，確保目前這次 HTTP 回應已經送出去給瀏覽器。新行程啟動時
    `main()` 的 `_bind_server()` 有重試，容忍舊行程還沒真正放掉連接埠
    的短暫空窗。"""
    def _do_restart() -> None:
        time.sleep(0.5)
        print("偵測到主控板程式碼更新，重新啟動…", flush=True)
        # 先放掉鎖再生新行程：acquire_lock() 只擋「已經有活著的行程」，
        # 這裡是同一個行程自己交棒，不放掉的話新行程會誤判成重複啟動、
        # 直接退出，變成兩邊都沒有伺服器在跑。
        release_lock()
        subprocess.Popen([sys.executable, str(HERE / "app.py")], cwd=str(HERE),
                         creationflags=_CREATE_NO_WINDOW)
        os._exit(0)
    threading.Thread(target=_do_restart, daemon=True).start()


def _format_timedelta(td: timedelta) -> str:
    total = int(td.total_seconds())
    if total < 0:
        return "未知（時間戳異常）"
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    return f"{h} 小時 {m} 分"


def _ssh_elapsed(worker: str, label: str) -> str | None:
    """讀遠端 `results/.start_<label>` 標記檔的 mtime 算已耗時（這個標記檔
    本來是 ssh_sync.py 的 pull() 用來分辨新結果的，見該檔案說明，這裡借用
    同一個檔案取得帶日期的正確開始時間——本機 log 只印 HH:MM:SS 沒有日期，
    沒辦法用來算耗時）。連不上、逾時、或標記檔還沒建立就回傳 None，畫面
    上顯示「未知」，不硬湊數字。

    **一定要用 `ssh_sync._get_worker()`，不能直接用
    `ssh_workers.load_workers()`**：後者的 `remote_dir` 可能是 `~/...`
    原樣沒展開，`shlex.quote()` 包成單引號後 `~` 不會被 shell 展開，
    `cd '~/m45_membership'` 會直接找不到目錄失敗（這個坑 ssh_sync.py
    自己的 `_expand_tilde()` 已經踩過、寫了很長的說明，這裡沿用同一個
    解法，不是重新發明）。"""
    try:
        w = ssh_sync._get_worker(worker)
    except Exception:  # noqa: BLE001 — worker 沒登記之類，優雅退回未知
        return None
    cmd = (f"cd {shlex.quote(w['remote_dir'])} 2>/dev/null && "
          f"stat -c %Y {shlex.quote('results/.start_' + label)} 2>/dev/null")
    try:
        r = ssh_workers.remote_run(w, cmd, timeout=15)
    except subprocess.TimeoutExpired:
        return None
    out = r.stdout.strip()
    if not out.isdigit():
        return None
    started = datetime.fromtimestamp(int(out))
    return _format_timedelta(datetime.now() - started)


def _ssh_ping(worker: str) -> dict:
    """單純確認一台 SSH worker（VM）本身連不連得上，不管有沒有工作在
    跑——雲端服務視角關心的是「這台機器是不是真的醒著」，跟步驟視角
    關心的「這個工作跑到哪」是兩個不同的問題（見『雲端服務』頁）。"""
    try:
        w = ssh_sync._get_worker(worker)
    except Exception as e:  # noqa: BLE001 — worker 沒登記之類
        return {"reachable": False, "error": str(e)}
    try:
        r = ssh_workers.remote_run(w, "echo ok", timeout=10)
    except subprocess.TimeoutExpired:
        return {"reachable": False, "error": "連線逾時"}
    if r.returncode == 0 and r.stdout.strip() == "ok":
        return {"reachable": True}
    return {"reachable": False,
           "error": (r.stderr.strip() or f"returncode={r.returncode}")[:200]}


def probe_live(worker: str, kind: str, item: dict) -> dict:
    """即時探測一個「宣稱正在跑」的工作。15 秒快取，防手滑連點洗爆
    worker，不是要打折「每次整理都探測」這個決策。"""
    label = item["label"]
    now = time.time()
    cached = _probe_cache.get(label)
    if cached and now - cached[0] < PROBE_CACHE_TTL:
        return cached[1]

    result = {"status": "unknown", "elapsed": None, "error": None}
    try:
        slot = cloud_queue._kaggle_handle(worker, item) if kind == "kaggle" else {}
        result["status"] = cloud_queue.probe_slot(worker, kind, item, slot)
    except Exception as e:  # noqa: BLE001 — 探測失敗不能讓整頁掛掉，顯示錯誤就好
        result["error"] = f"探測失敗：{e}"

    if kind == "ssh" and result["status"] in ("running", "complete", "error"):
        result["elapsed"] = _ssh_elapsed(worker, label)
    # kind == "kaggle" 目前沒有對應的耗時來源（Kaggle 端沒有同一套標記檔
    # 機制），已知限制，先留空不硬湊。

    _probe_cache[label] = (now, result)
    return result


def _map_probe_state(probe_status: str) -> tuple[str, str | None]:
    """即時探測回傳的字彙（running／complete／error／cancelled／missing／
    unknown）對應到畫面顯示的狀態分類。**只有 `running` 算真正「進行
    中」**（2026-08-25 CodeRabbit review 訂正：原本不管探測回什麼一律顯示
    「進行中」，一個工作明明已經 `missing`／`error` 也會被算進「進行中」
    的統計數字裡）。`complete`／`error`／`cancelled` 代表遠端這輪其實已經
    跑完了，但派工器還沒處理完 `mark_done()`（下載結果、寫 done log 需要
    時間）——這裡不硬湊一筆「已完成」的假紀錄（沒有 secs／worker／when
    這些欄位可用），跟 `missing`／`unknown` 一起歸類成「不確定」，原始
    探測字串放進 note 讓人自己判斷。"""
    if probe_status == "running":
        return "live", None
    if probe_status == "missing":
        return "pending", "遠端目前沒有這個工作的痕跡（可能還沒真的啟動）"
    return "unknown", f"即時探測回傳「{probe_status}」，派工器可能還沒處理完"


def classify_label(label: str, cloud_items: dict, cloud_done: dict,
                   local_done: dict, cloud_workers: dict) -> dict:
    """把一個 queue_label 解析成畫面要顯示的狀態字典，或者（需要即時
    探測時）回傳一個帶 `_probe: True` 的標記字典。優先順序：雲端終態 →
    本機終態（已停用但保留歷史）→ 雲端佇列中（可能需要即時探測）→
    完全找不到。**不牽涉網路**——即時探測的部分特意留給呼叫端
    （`_run_probes()`）集中處理，才能做有上限的併發＋整體時間預算，
    不要每個 label 各自序列化等 SSH 逾時（2026-08-25 CodeRabbit review）。
    """
    rec = cloud_done.get(label)
    if rec and rec["status"] != "push_failed":
        return {"state": "done", "source": "雲端", **rec}

    rec = local_done.get(label)
    if rec and rec["status"] not in ("stalled_giveup", "preflight_fail"):
        return {"state": "done", "source": "本機（已停用）", **rec}

    item = cloud_items.get(label)
    if not item:
        return {"state": "unknown", "note": "沒有排進目前的佇列，也沒有執行紀錄"}

    worker = item["worker"]
    if not worker:
        return {"state": "pending", "note": "已排進佇列，尚未指定 worker"}
    kind = cloud_workers.get(worker)
    if not kind:
        return {"state": "pending", "note": f"worker「{worker}」未登記"}
    return {"_probe": True, "worker": worker, "kind": kind, "item": item}


def _run_concurrent(fns: dict[str, Callable[[], dict]],
                    deadline_s: float = PROBE_DEADLINE_S) -> dict[str, dict]:
    """通用的「有上限併發＋整體時間預算」執行器：`fns` 是
    {key: 零參數 callable}，每個都回傳一個 dict。時間到了還沒回來的 key
    補一筆 `{"status": "unknown", "error": "逾時"}`，不讓任何一次外部
    呼叫（SSH／Kaggle API）卡住整頁的回應時間（2026-08-25 CodeRabbit
    review：原本是逐一同步呼叫，同一個不可達 worker 上排了好幾個標籤的
    話，每個都要各自等 `ssh_sync.poll()` 自己的 30 秒逾時，疊起來要等
    好幾分鐘）。工作狀態的即時探測（`probe_live()`）、閒置 worker 的
    連線探測（`_ssh_ping()`）共用這支，不各自重寫一份併發邏輯。"""
    results: dict[str, dict] = {}
    if not fns:
        return results

    pool = ThreadPoolExecutor(max_workers=PROBE_MAX_WORKERS)
    futures = {pool.submit(fn): key for key, fn in fns.items()}
    deadline = time.monotonic() + deadline_s
    try:
        for fut in as_completed(futures, timeout=max(0.0, deadline - time.monotonic())):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as e:  # noqa: BLE001 — 單一呼叫炸掉不能拖垮其他的
                results[key] = {"status": "unknown", "error": str(e)}
    except FutureTimeoutError:
        pass  # 整體時間預算到了，剩下沒回來的在下面補「逾時」
    finally:
        # 不等還沒做完的執行緒——它們多半卡在 SSH 自己的逾時裡，讓它們
        # 自然結束即可，不影響這次頁面已經要回應了；cancel_futures 只能
        # 取消「還沒真的開始跑」的，正在跑的 SSH 呼叫沒辦法從外面強制
        # 中斷。
        pool.shutdown(wait=False, cancel_futures=True)

    for key in fns:
        if key not in results:
            results[key] = {"status": "unknown",
                            "error": f"整理逾時（超過 {deadline_s:.0f} 秒）"}
    return results


def _probe_fns(to_probe: dict[str, dict]) -> dict[str, Callable[[], dict]]:
    """把 `to_probe`（label -> {worker, kind, item}）轉成 `_run_concurrent()`
    要的 {key: 零參數 callable}，不在這裡實際執行——拆出來是為了讓呼叫端
    可以把這批 callable 跟其他批次（例如 `_ssh_ping()`）合併進同一次
    `_run_concurrent()`，共用同一份時間預算（見 `gather_worker_status()`
    的說明）。"""
    return {label: (lambda info=info: probe_live(info["worker"], info["kind"], info["item"]))
           for label, info in to_probe.items()}


def _post_process_probes(to_probe: dict[str, dict], raw: dict[str, dict]) -> dict[str, dict]:
    """把 `_probe_fns()` 執行完的原始結果，補上 `_map_probe_state()` 分類
    後的顯示用欄位。"""
    results = {}
    for label, info in to_probe.items():
        live = raw.get(label, {"status": "unknown", "error": "沒有探測結果"})
        live.setdefault("elapsed", None)
        state, note = _map_probe_state(live.get("status", "unknown"))
        out = {"state": state, "worker": info["worker"], "kind": info["kind"], **live}
        if note:
            out["note"] = note
        results[label] = out
    return results


def _run_probes(to_probe: dict[str, dict]) -> dict[str, dict]:
    """對 `to_probe`（label -> {worker, kind, item}）裡的每個標籤做即時
    探測，套用 `_run_concurrent()` 的併發＋整體時間預算。"""
    if not to_probe:
        return {}
    raw = _run_concurrent(_probe_fns(to_probe))
    return _post_process_probes(to_probe, raw)


def gather_status(probe: bool = True) -> dict:
    """`probe=False`：跳過所有即時探測（SSH／Kaggle API 呼叫），需要
    探測的 label 一律標成 `state: "checking"`，其餘照舊——2026-09-02
    使用者要求：頁面要先秒開，探測是背景後續的事，不要卡住整頁的回應
    （之前是同一次請求裡做完所有探測才回應，最壞情況等到
    `PROBE_DEADLINE_S`，工作閒置或連線本身較慢時很常見）。首頁走
    `probe=False` 立刻回應，瀏覽器再用小段 JS 打 `/probe-status.json`
    （用 `probe=True`）補上真正的狀態，見 `_PROBE_SCRIPT`。"""
    cloud_workers = cloud_queue.load_all_workers()
    cloud_items = {it["label"]: it for it in cloud_queue.read_queue()}
    cloud_done = parse_cloud_done()
    local_done = parse_local_done()
    alive, pid = dispatcher_alive()

    all_labels = set()
    for stage in STAGES:
        for step in stage["steps"]:
            all_labels.update(step.get("queue_labels", []))

    label_status: dict[str, dict] = {}
    to_probe: dict[str, dict] = {}
    for label in all_labels:
        result = classify_label(label, cloud_items, cloud_done, local_done,
                                cloud_workers)
        if result.get("_probe"):
            to_probe[label] = result
        else:
            label_status[label] = result
    if probe:
        label_status.update(_run_probes(to_probe))
    else:
        label_status.update({label: {"state": "checking", **info}
                            for label, info in to_probe.items()})

    return {
        "alive": alive, "pid": pid,
        "cloud_workers": cloud_workers, "cloud_items": cloud_items,
        "cloud_done": cloud_done, "label_status": label_status,
    }


def gather_worker_status(probe: bool = True) -> dict:
    """以雲端服務（worker）為單位，不是以步驟為單位——單純回答「這個
    worker 現在是不是真的在跑」（2026-08-25 使用者要求新增的第二種
    介面）。跟 `gather_status()` 是同一批來源資料的另一種切法，不重複
    定義佇列格式，但因為關心的問題不同，即時探測的對象也不同：這裡
    探測的是「這個 worker 上排定的第一個未完成 label」，`gather_status()`
    探測的是「stage_map.py 裡列出的每個 label」——兩邊在同一個 worker
    同時只有一個槽位在跑的前提下通常會對到同一個工作，但這支函式就算
    stage_map.py 完全沒收錄某個 label，也照樣看得到。

    `probe=False`：跟 `gather_status()` 同一個理由，見那邊的說明——
    跳過所有即時探測，`/workers` 頁面秒開，JS 再補上真正的狀態。"""
    cloud_workers = cloud_queue.load_all_workers()
    cloud_items = {it["label"]: it for it in cloud_queue.read_queue()}
    cloud_done = parse_cloud_done()
    local_done = parse_local_done()

    def _unfinished(label: str) -> bool:
        rec = cloud_done.get(label)
        if rec and rec["status"] != "push_failed":
            return False
        rec = local_done.get(label)
        if rec and rec["status"] not in ("stalled_giveup", "preflight_fail"):
            return False
        return True

    # 一個 worker 同時只會真的跑一個槽位（cloud_queue.py 的槽位式併發
    # 設計），這裡只取排在佇列檔裡第一個還沒完成的 label 當代表。
    assigned: dict[str, dict] = {}
    for label, item in cloud_items.items():
        worker = item["worker"]
        if worker and worker not in assigned and _unfinished(label):
            assigned[worker] = item

    to_probe = {name: {"worker": name, "kind": kind, "item": assigned[name]}
               for name, kind in cloud_workers.items() if name in assigned}
    idle_ssh = [name for name, kind in cloud_workers.items()
               if kind == "ssh" and name not in assigned]

    if not probe:
        # 秒開版：不打任何 SSH／Kaggle API，`to_probe`／`idle_ssh` 裡的
        # worker 一律標成「探測中」，讓 _worker_badge() 顯示佔位樣式，
        # 交給 JS 之後打 /workers-probe.json 補上真正結果。
        workers_out = []
        for name, kind in sorted(cloud_workers.items()):
            if name in to_probe:
                script = assigned[name].get("script") or None
                workers_out.append({"name": name, "kind": kind, "assigned": True,
                                    "state": "checking",
                                    "label": assigned[name]["label"],
                                    "script": script,
                                    "args": assigned[name].get("args") or None})
            elif name in idle_ssh:
                workers_out.append({"name": name, "kind": kind, "assigned": False,
                                    "checking": True})
            else:
                workers_out.append({"name": name, "kind": kind, "assigned": False,
                                    "reachable": None})
        return {"workers": workers_out}

    # 已派工的 worker（要探測工作狀態）跟閒置的 SSH worker（只要 ping）
    # 併成同一次 _run_concurrent() 呼叫，共用同一份 PROBE_DEADLINE_S——
    # 原本分兩次呼叫，各自都用完整預算，最壞情況（兩邊都連不上）整頁
    # 要等兩倍時間才會回應（2026-08-25 CodeRabbit review）。用字首區分
    # 兩批 key，執行完再拆開各自後處理。
    combined_fns: dict[str, Callable[[], dict]] = {}
    combined_fns.update({f"probe:{k}": fn for k, fn in _probe_fns(to_probe).items()})
    combined_fns.update({f"ping:{name}": (lambda n=name: _ssh_ping(n))
                         for name in idle_ssh})
    raw = _run_concurrent(combined_fns) if combined_fns else {}

    raw_probe = {name: raw[f"probe:{name}"] for name in to_probe
                if f"probe:{name}" in raw}
    ping_results = {name: raw[f"ping:{name}"] for name in idle_ssh
                    if f"ping:{name}" in raw}
    probe_results = _post_process_probes(to_probe, raw_probe)

    workers_out = []
    for name, kind in sorted(cloud_workers.items()):
        if name in probe_results:
            r = probe_results[name]
            # 這個 worker 現在跑的腳本，直接從 cloud_queue.txt 那一行讀
            # （2026-09-02 使用者要求）——不查 stage_map.py／
            # categorization.json，佇列檔自己就有 label→script 的對應，
            # 不需要另外維護一份索引才能知道「這個 worker 在跑哪支程式」，
            # 也不會因為新腳本還沒補進索引就看不到連結。
            #
            # args 也一併帶出來（同一次使用者反映）：像
            # p6_lowmass_v3_s13/s15/s17 這種同一支腳本、切成多個 shard
            # 平行跑的工作，光看腳本名稱三個都長一樣（本來就是同一支，
            # 不是 bug），區分靠的是參數（--slopes 1.3/1.5/1.7 這種），
            # 不帶出來的話連結旁邊看不出這幾個 worker 實際在算不同的
            # 東西。
            script = assigned[name].get("script") or None
            workers_out.append({"name": name, "kind": kind, "assigned": True,
                                "label": assigned[name]["label"],
                                "script": script,
                                "args": assigned[name].get("args") or None,
                                **r})
        elif name in ping_results:
            p = ping_results[name]
            # _run_concurrent() 逾時/例外時的補值只有 status/error，沒有
            # reachable；不補的話 _worker_badge() 會落到「Kaggle 閒置」
            # 那個分支，把連不上或探測逾時的機器顯示成正常閒置，剛好
            # 蓋掉這個頁面本來要抓的問題（2026-08-25 CodeRabbit review）。
            if "reachable" not in p:
                p = {"reachable": False,
                    "error": p.get("error", "連線探測未完成")}
            workers_out.append({"name": name, "kind": kind, "assigned": False,
                                **p})
        else:
            # Kaggle 帳號閒置時沒有常駐機器可以探測連線——Kaggle 是無伺服器
            # 的 kernel 執行環境，沒有工作在跑就沒有東西可以 ping。
            workers_out.append({"name": name, "kind": kind, "assigned": False,
                                "reachable": None})
    return {"workers": workers_out}


# ==================================================================
# HTML render（純 HTML + <details>/<summary> 折疊，不用 JS）
# ==================================================================

STATE_LABEL = {
    "done_ok": "已完成", "done_fail": "失敗", "live": "進行中",
    "pending": "待派工", "unknown": "沒有紀錄", "checking": "探測中",
}


def _status_badge(st: dict) -> str:
    state = st["state"]
    if state == "done":
        ok = st.get("status") == "ok"
        cls, text = ("ok", "已完成") if ok else ("fail", f"失敗（{st.get('status')}）")
        detail = f"{st.get('secs', '?')}　worker={st.get('worker', st.get('source', '?'))}　{st.get('when', '')}"
    elif state == "live":
        cls = "live"
        text = f"進行中（{st.get('status', 'unknown')}）"
        bits = [f"worker={st.get('worker')}"]
        if st.get("elapsed"):
            bits.append(f"已耗時 {st['elapsed']}")
        if st.get("error"):
            bits.append(st["error"])
        detail = "　".join(bits)
    elif state == "pending":
        cls, text, detail = "pending", "待派工", st.get("note", "")
    elif state == "checking":
        # 2026-09-02：頁面先秒開、探測結果用 JS 背景補上（見
        # _PROBE_SCRIPT）——這是還沒補上之前的暫時樣子，不是真正的
        # 狀態，所以用問號圖示跟中性配色，不要跟 pending／unknown 的
        # 配色搞混（那兩個是「真的查過、結果就是這樣」）。
        cls, text, detail = "checking", "探測中…", f"worker={st.get('worker', '?')}"
    else:
        cls, text, detail = "unknown", "沒有紀錄", st.get("note", "")
    return (f'<span class="badge {cls}">{html.escape(text)}</span>'
           f'<span class="detail">{html.escape(detail)}</span>')


# ==================================================================
# 說明區塊的排版：把純文字 docstring 轉成「像教科書那樣可讀」的 HTML
#
# 為什麼需要這一段（2026-08-26 使用者要求）：原本的作法是把 docstring
# 整段丟進 <pre>，等於把作者寫的重點、公式、引用的文獻全部壓成同一種
# 灰底等寬字，讀者一眼看不出哪句是結論、哪句是註腳。這個主控板要拿去
# 科展解說，讀者是第一次看到這個專案的人，得先看懂「這一步在幹嘛、
# 憑什麼這樣做」才有意義，所以說明區塊改成三層：
#
#   1. 重點（key_points）——這一步最該記住的兩三句話，人工挑的
#   2. 公式（formula）——這一步真正在算的數學式，附出處與符號說明
#   3. 文獻（refs）——這個做法來自哪一篇論文，可以點進去看原文
#
# 前三層是 stage_map.py 手動維護的（跟「階段→步驟→腳本」對照表同一種
# 「沒辦法自動生成、只能手動維護」的性質，見該檔案開頭說明）；最後才
# 接原本就有的 docstring 原文，並套用下面這個輕量標記轉換讓它好讀。
# ==================================================================

# docstring 裡本來就在用的輕量標記（作者們一直是用 Markdown 的習慣在
# 寫 Python docstring），這裡只認最常出現、且轉換後不會誤傷程式碼的
# 三種：**粗體**、`程式碼`、以及空行分段。**不引入 Markdown 套件**：
# 這個主控板刻意零外部依賴（見檔頭設計原則第 1 點），而且完整 Markdown
# 反而會把 docstring 裡的縮排程式碼片段、表格誤判成別的東西。
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_RE_CODE = re.compile(r"`([^`]+?)`")
# ==螢光標記==：參考版面裡用黃色螢光筆標出「一句話結論」的效果。
# 用兩個等號當標記是 Markdown 生態常見的 highlight 語法，且不會跟
# docstring 裡既有的內容衝突（Python 註解不會出現連續等號夾字）。
_RE_MARK = re.compile(r"==(.+?)==", re.S)
# 純文字裡直接寫出來的 arXiv 編號（專案文件裡很常見，例如
# 「arXiv:2603.15779 指出這個偏差不隨樣本數縮小」），轉成可以點的連結。
_RE_ARXIV = re.compile(r"arXiv:(\d{4}\.\d{4,5})")
# 看起來像這個 repo 裡某支程式的路徑——用來決定 `xxx` 這個行內程式碼
# 要不要順便變成「點了就用 VS Code 開啟」的連結。要求以 .py 結尾，
# 避免把 `f_bin`、`--refines 3,3` 這種一般的行內程式碼誤判成檔案。
_RE_PYPATH = re.compile(r"^[\w./-]+\.py$")


def _code_span(inner: str) -> str:
    """行內 `程式碼` 的呈現：看起來像本 repo 的 .py 路徑就變成可點的
    連結（點了在 GitHub 開啟該檔——見 _doc_url() 的說明，2026-09-02
    起從 vscode://file/ 改過來），其餘維持單純的等寬字樣式。

    這是使用者要的「附上連結，讓我能夠點進去看」在 docstring 內文層級
    的實作——不只步驟標題底下那一排腳本連結可以點，內文提到某支程式時
    也能直接跳過去。"""
    if _RE_PYPATH.match(inner) and (REPO_ROOT / inner).exists():
        return (f'<a class="inline-src" href="{html.escape(_doc_url(inner))}">'
                f'<code>{html.escape(inner)}</code></a>')
    return f"<code>{html.escape(inner)}</code>"


def _inline_markup(escaped: str) -> str:
    """對**已經 HTML 逃逸過**的一行文字套用行內標記。

    順序很重要：一定要先逃逸再套標記，否則我們自己插進去的 <strong>、
    <code> 標籤會被後續的逃逸吃掉變成畫面上的亂碼。
    """
    out = _RE_MARK.sub(lambda m: f'<mark class="hl">{m.group(1)}</mark>', escaped)
    out = _RE_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _RE_CODE.sub(lambda m: _code_span(html.unescape(m.group(1))), out)
    out = _RE_ARXIV.sub(
        lambda m: (f'<a href="https://arxiv.org/abs/{m.group(1)}" '
                   f'target="_blank" rel="noopener">arXiv:{m.group(1)}</a>'),
        out)
    return out


def _render_doc(text: str) -> str:
    """把 docstring 純文字轉成分段、帶行內標記的 HTML。

    刻意保留兩種原文樣貌不動：(1) 明顯是程式碼或資料表的區塊（整段每行
    都以空白開頭），照原樣放進 <pre>，因為那種內容的對齊本身就是資訊；
    (2) 其餘段落轉成 <p>，讓長篇說明可以正常斷行、不再是一整片等寬字。
    """
    if not text:
        return ""
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for block in blocks:
        lines = block.split("\n")
        indented = [ln for ln in lines if ln.strip()]
        if indented and all(ln.startswith(("    ", "\t")) for ln in indented):
            out.append(f'<pre class="doc-pre">{html.escape(block)}</pre>')
            continue
        escaped = html.escape(block)
        out.append(f'<p class="doc-p">{_inline_markup(escaped)}</p>')
    return "".join(out)


def _render_key_points(points: list[str]) -> str:
    """「重點」區塊：這一步最該先看懂的幾句話。手動挑的，不是自動摘要
    ——自動摘要在這種內容上只會抓到最長的句子，不是最重要的句子。"""
    if not points:
        return ""
    items = "".join(f"<li>{_inline_markup(html.escape(p))}</li>" for p in points)
    return ('<div class="callout kp"><div class="callout-h">重點</div>'
            f'<ul class="kp-list">{items}</ul></div>')


def _render_prereq(items: list[str]) -> str:
    """「這裡用到的新名詞」區塊。

    這個專案的讀者是高一升高二的學生（也是實際在做這個科展的人），
    課程上還沒教到機率分布、最大概似估計、微積分這些東西。與其假裝
    讀者都懂、或是整段避開不講，不如==把超出高中課程的名詞單獨挑出來，
    用一兩句話接回已經學過的概念==（對數、星等、赫羅圖、平均與標準差
    都是高一地科／數學就有的）。這比在正文裡塞一堆括號註解好讀。
    """
    if not items:
        return ""
    lis = "".join(f"<li>{_inline_markup(html.escape(x))}</li>" for x in items)
    return ('<div class="callout pq"><div class="callout-h">這裡用到的新名詞</div>'
            f'<ul class="kp-list">{lis}</ul></div>')


def _render_formula(formulas: list[dict]) -> str:
    """「公式」區塊：這一步真正在算什麼。

    用純文字數學式（不是 LaTeX 排版）——這個主控板不載入 MathJax 之類的
    外部函式庫（零外部依賴原則，而且 CSP 也擋外部資源），所以公式以
    等寬字呈現，符號說明列在下方。這樣在科展現場用筆電離線開也一定看得到。
    """
    if not formulas:
        return ""
    rows = []
    for f in formulas:
        bits = [f'<pre class="formula-expr">{html.escape(f["expr"])}</pre>']
        # 「公式意義／輸入項／輸出項」三段式拆解（2026-08-26 使用者指定的
        # 版面）——把一條式子拆成「它在講什麼、餵什麼進去、吐什麼出來」，
        # 讀者不用先看懂符號就能知道這一步在資料流裡的位置。三個欄位都
        # 是選填，只有 meaning 沒填時才退回舊的單段 where 敘述。
        for key, lab in (("plain", "白話說"), ("meaning", "公式意義"),
                         ("inputs", "輸入項"), ("outputs", "輸出項")):
            if f.get(key):
                bits.append(
                    f'<p class="formula-field"><span class="ff-lab">{lab}</span>'
                    f'{_inline_markup(html.escape(f[key]))}</p>')
        if f.get("where"):
            bits.append(f'<p class="formula-where">{_inline_markup(html.escape(f["where"]))}</p>')
        if f.get("source"):
            bits.append(f'<p class="formula-src">出處：{_inline_markup(html.escape(f["source"]))}</p>')
        rows.append('<div class="formula-item">' + "".join(bits) + "</div>")
    return ('<div class="callout fm"><div class="callout-h">公式</div>'
            + "".join(rows) + "</div>")


def _ref_url(ref: dict) -> str:
    """一筆文獻的連結。

    **這份資料要拿去科展，連結指到錯的論文比沒有連結更糟**，所以只用
    三種一定不會指錯的形式，優先序由上而下：

    1. `arxiv`：直接連 arxiv.org/abs/<編號>。精確、可驗證，點進去就是
       全文，可以直接跳到需要的章節。
    2. `bibstem`＋`volume`＋`page`（＋`year`）：組一個**精確的 ADS 查詢**
       （例如 bibstem:"MNRAS" volume:"322" page:"231" year:2001）。
       這種查詢在天文文獻裡幾乎必然只命中一篇，等於直接落到那篇論文。
    3. 都沒有時：退回用引用字串本身去 ADS 搜尋。

    **刻意不自己拼 ADS bibcode**（例如 2001MNRAS.322..231K）：bibcode 是
    19 個字元、靠位置對齊的編碼，少一個點就會靜默地連到**另一篇**論文
    ——而且看起來完全正常，是最難被發現的一種錯。用查詢式換來的代價
    只是多一次點擊，但保證不會指錯。
    """
    if ref.get("arxiv"):
        return f"https://arxiv.org/abs/{ref['arxiv']}"
    if ref.get("bibstem") and ref.get("volume") and ref.get("page"):
        # 精確查詢：期刊代號＋卷＋頁（＋年）在天文文獻裡幾乎必然只命中
        # 一篇，等於直接落到那篇論文，但沒有拼錯 bibcode 的風險。
        q = (f'bibstem:"{ref["bibstem"]}" volume:"{ref["volume"]}" '
             f'page:"{ref["page"]}"')
        if ref.get("year"):
            q += f' year:{ref["year"]}'
        return "https://ui.adsabs.harvard.edu/search/q=" + quote_plus(q)
    return ("https://ui.adsabs.harvard.edu/search/q="
            + quote_plus(ref["cite"]))


GITHUB_REPO = "https://github.com/helmet-png/m45-imf-analysis"


def _doc_url(rel_path: str, line: int | None = None) -> str:
    """本專案自己文件的 GitHub 連結（可帶行號錨點）。

    用 GitHub 網址而不是 VS Code 的 file URI，是因為文獻對照這一欄的用途
    是「科展現場給人看、或傳連結給隊友」——GitHub 連結在別人的手機、
    別台電腦都打得開，`vscode://` 只有自己這台裝了 VS Code 的機器有用。
    行號錨點（#L123）讓人==點下去直接落在講這件事的那一段==，不用自己
    在幾百行的文件裡找。
    """
    anchor = f"#L{line}" if line else ""
    return f"{GITHUB_REPO}/blob/main/{rel_path}{anchor}"


def _render_refs(refs: list[dict]) -> str:
    """「文獻出處」區塊：這一步的做法是從哪篇論文來的、負責哪一部分。

    內容全部來自專案自己已經核對過的兩張文獻對照表（`docs/teaching/
    教學_傳統法誤差核算.md` 第十節、`docs/teaching/教學_前向模型.md`
    第十節），不是這支程式另外去生成的——那兩張表是有人實際讀過原文
    才寫下來的，這裡只負責把它們接到對應的步驟旁邊、讓人點得到。
    """
    if not refs:
        return ""
    rows = []
    for r in refs:
        url = html.escape(_ref_url(r))
        cite = html.escape(r["cite"])
        role = _inline_markup(html.escape(r.get("role", "")))
        # 第三欄：連到本專案自己文件裡討論這篇的那一段。使用者要的是
        # 「點下去看到段落」——外部論文連結只能到論文首頁，真正解釋
        # 「我們為什麼引這篇、用在哪」的是專案自己的教學文件。
        local = ""
        if r.get("doc"):
            durl = html.escape(_doc_url(r["doc"], r.get("doc_line")))
            local = (f'<a href="{durl}" target="_blank" rel="noopener">'
                     f'本專案說明 ↗</a>')
        rows.append(
            f'<tr><td class="ref-cite">'
            f'<a href="{url}" target="_blank" rel="noopener">{cite}</a></td>'
            f'<td class="ref-role">{role}</td>'
            f'<td class="ref-local">{local}</td></tr>')
    return ('<div class="callout rf"><div class="callout-h">文獻出處</div>'
            '<table class="ref-table"><thead><tr><th>文獻</th>'
            '<th>在這一步負責什麼</th><th></th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def _render_core(core: dict | None) -> str:
    """「核心程式碼」區塊：這一步幾十支檔案裡，真正做事的是哪一個函式。

    使用者的原話是「說明出程式中最核心的程式碼，並附上連結，讓我能夠
    點進去看」。用 `_doc_url()` 的 GitHub 行號錨點（`#L123`）直接連到
    該函式的**那一行**，不是只開啟檔案讓人自己找（2026-09-02 起改用
    GitHub 連結，見 `_doc_url()` 說明——原本用 `vscode://` 只有本機
    裝了 VS Code 才打得開，主控板搬到協調 VM 之後，`vscode://` 指向的
    是協調 VM 自己的檔案路徑，根本不是看的人電腦上的任何東西）。
    """
    if not core:
        return ""
    rel, line = core["file"], core.get("line")
    uri = _doc_url(rel, line)
    where = f"{rel}:{line}" if line else rel
    why = _inline_markup(html.escape(core.get("why", "")))
    return ('<div class="callout cr"><div class="callout-h">核心程式碼</div>'
            f'<p class="core-fn"><a class="inline-src" href="{html.escape(uri)}">'
            f'<code>{html.escape(core["name"])}</code>'
            f'<span class="core-where">{html.escape(where)}</span> ↗</a></p>'
            f'<p class="doc-p">{why}</p></div>')


def _slugify(rel_path: str) -> str:
    """檔案路徑轉成能當 HTML id 用的字串（給「未分類程式」區塊的錨點
    用）——路徑分隔符號跟點都不是合法 id 的一部分，全部換成連字號。"""
    return "script-" + re.sub(r"[^A-Za-z0-9_-]+", "-", rel_path)


def _render_script_block(script: str, external: bool = False,
                         upstream: str | None = None) -> str:
    """一支腳本的連結＋可收合檔頭說明，抽成共用函式（2026-08-31）——
    原本只有「階段/步驟」底下的腳本會這樣印，現在「未分類程式」區塊
    （見 discover_unindexed_scripts()）也要用同一種呈現方式，不要
    複製貼上兩份長得一樣的邏輯。"""
    doc = read_docstring(script, external=external, upstream=upstream)
    exists = (REPO_ROOT / script).exists()
    # 2026-09-02 起連結一律指向 GitHub（見 _doc_url() 說明），不再要求
    # 本機（協調 VM 的 checkout）先有這個檔案才給連結——GitHub 才是
    # 權威來源，本機落後一步是常態（例如 PR 剛合併，下一輪自動同步
    # 還沒跑到），舊邏輯會因此完全不給連結、讓使用者以為程式不存在，
    # 但其實只是連結生成方式（vscode://file/ 指向本機路徑）本身就有
    # 問題：主控板搬到協調 VM 之後，那個路徑對看的人來說完全是別台
    # 機器上的東西，不管本機找不找得到檔案都一樣打不開。
    if external and upstream:
        link = (f'<span class="script-link missing"><code>'
                f'{html.escape(script)}</code></span>'
                f'<a class="upstream-link" href="{html.escape(upstream)}" '
                f'target="_blank" rel="noopener">第三方套件，看上游原始碼 ↗</a>')
    else:
        note = ("" if exists else
               '<span class="script-link-note">（本機尚未同步到這個檔案，'
               '連結仍指向 GitHub 上的版本）</span>')
        link = (f'<a class="script-link" href="{html.escape(_doc_url(script))}">'
                f'<code>{html.escape(script)}</code> ↗</a>{note}')
    return ('<div class="script-block">' + link
            + '<details class="doc-details"><summary>程式檔頭原文說明</summary>'
            f'<div class="doc">{_render_doc(doc)}</div></details></div>')


_BUCKET_ORDER = [
    ("live", "live", "進行中"),
    ("pending", "pending", "待派工"),
    ("done_fail", "fail", "失敗"),
    ("unknown", "unknown", "不確定"),
    ("done_ok", "ok", "已完成"),
]


def _label_bucket(st: dict) -> str:
    state = st["state"]
    if state == "done":
        return "done_ok" if st.get("status") == "ok" else "done_fail"
    return state  # "live" / "pending" / "unknown"


def _step_summary_badge(step: dict, label_status: dict) -> tuple[str, str] | None:
    """把一個步驟底下所有 queue_labels 的狀態濃縮成一個徽章，給左側
    導覽列用——優先順序：進行中 > 待派工 > 失敗 > 不確定 > 已完成，
    只要有一個 label 在跑，這個步驟在導覽列就該亮起來，不用點進去才
    看得到。沒有 queue_labels 的步驟（傳統法、PDMF→IMF 前幾步這種手動
    或還沒排進佇列的）回傳 None，導覽上不掛徽章。"""
    labels = step.get("queue_labels", [])
    buckets = {_label_bucket(label_status[label]) for label in labels
              if label in label_status}
    if not buckets:
        return None
    for key, cls, text in _BUCKET_ORDER:
        if key in buckets:
            return cls, text
    return None


def _sync_banner(sync: dict) -> str:
    """把 `sync_repo_from_github()` 的結果轉成頁面頂端的一行狀態說明——
    （2026-08-25 使用者要求「以後新程式碼刷到 GitHub 要怎麼自動更新」）
    誠實區分四種情況，不要讓「同步失敗」「沒同步（保護未提交的修改）」
    「已經是最新」看起來像同一回事。"""
    if sync.get("error"):
        return (f'<p class="warn-text">跟 GitHub 同步失敗：'
                f'{html.escape(sync["error"])}（沿用本機現有內容）</p>')
    if sync.get("self_updated"):
        return ('<p class="warn-text">已從 origin/main 拉到最新，其中'
               '主控板自己的程式碼也有更新，即將自動重啟套用——這一輪'
               '畫面可能還是舊版，幾秒後重新整理一次即可。</p>')
    if sync.get("synced"):
        return '<p class="note">剛從 origin/main 同步到最新。</p>'
    if sync.get("behind"):
        reason = "有未提交的修改" if sync.get("dirty") else f'不在 main（目前在 {sync.get("branch")}）'
        return (f'<p class="note">本機落後 origin/main {sync["behind"]} 個'
                f' commit，沒有自動同步（{reason}，怕弄丟正在做的東西）'
                '——要看最新內容請自己手動 git pull。</p>')
    return ""


def render_html(status: dict, sync: dict | None = None) -> str:
    cloud_items = status["cloud_items"]
    cloud_done = status["cloud_done"]
    label_status = status["label_status"]

    done_ok = sum(1 for s in label_status.values()
                 if s["state"] == "done" and s.get("status") == "ok")
    done_fail = sum(1 for s in label_status.values()
                    if s["state"] == "done" and s.get("status") != "ok")
    live_n = sum(1 for s in label_status.values() if s["state"] == "live")
    pending_n = sum(1 for s in label_status.values() if s["state"] == "pending")
    unmatched_cloud = [lb for lb in cloud_items if lb not in label_status
                       and lb not in cloud_done]

    parts = []
    parts.append(f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>M45 IMF 專案主控板</title>
<style>
{_CSS}
</style></head><body>
<h1>M45 IMF 專案主控板</h1>
{_NAV}
<p class="sub">依步驟看——整理時間：{datetime.now():%Y-%m-%d %H:%M:%S}
（重新整理頁面 = 重新讀取所有來源檔案 + 跟 GitHub 同步 + 對進行中工作
即時探測；點程式名稱在 VS Code 開啟；左側導覽只是跳到對應段落，
右邊全部內容一次展開，不用逐層點開；左右欄寬度可以拖曳中間的分隔線
調整）</p>
{_sync_banner(sync or {})}

<div class="summary">
  <div class="pill {'alive' if status['alive'] else 'dead'}">
    派工器：{'存活（PID ' + str(status['pid']) + '）' if status['alive'] else '沒有在跑'}
  </div>
  <div class="pill">已完成 {done_ok}</div>
  <div class="pill {'warn' if done_fail else ''}">失敗 {done_fail}</div>
  <div class="pill {'live' if live_n else ''}">進行中 {live_n}</div>
  <div class="pill">待派工 {pending_n}</div>
</div>
""")

    if unmatched_cloud:
        parts.append('<p class="warn-text">cloud_queue.txt 裡有 '
                     + html.escape(str(len(unmatched_cloud)))
                     + ' 筆標籤沒對到 stage_map.py 的任何步驟（可能是還沒'
                       '補進索引的新工作）：<code>'
                     + html.escape(", ".join(unmatched_cloud)) + '</code></p>')

    # 左側導覽（純錨點跳轉，不重新整理頁面）跟右側內容分開組，最後
    # 再拼成 .layout 的兩欄——導覽列只負責「跳去哪」，實際內容全部
    # 已經展開在右邊，符合「不用手動展開、盡量看到全部」的要求。
    nav_parts = ['<nav class="tree" id="tree-pane">']
    content_parts = ['<div class="content">']

    for si, stage in enumerate(STAGES):
        stage_id = f"stage-{si}"
        nav_parts.append(f'<a class="tree-stage" href="#{stage_id}">'
                         f'{html.escape(stage["name"])}</a><ul>')
        content_parts.append(f'<section class="stage-block" id="{stage_id}">'
                             f'<h2>{html.escape(stage["name"])}</h2>')

        for ti, step in enumerate(stage["steps"]):
            step_id = f"step-{si}-{ti}"
            badge = _step_summary_badge(step, label_status)
            badge_html = (f'<span class="badge {badge[0]} tree-badge">{badge[1]}</span>'
                         if badge else "")
            nav_parts.append(f'<li><a href="#{step_id}">'
                             f'{html.escape(step["name"])}{badge_html}</a></li>')

            content_parts.append(f'<article class="step-block" id="{step_id}">'
                                 f'<h3>{html.escape(step["name"])}</h3>')
            if step.get("note"):
                content_parts.append(f'<p class="note">{html.escape(step["note"])}</p>')
            for label in step.get("queue_labels", []):
                st = label_status.get(label)
                if st is None:
                    continue
                content_parts.append(
                    f'<div class="status-row" data-label="{html.escape(label)}">'
                    f'<code>{html.escape(label)}</code>'
                    f'<span class="status-badge-slot">{_status_badge(st)}</span></div>')

            # 人工整理的解說層，順序是刻意的：先看「重點」知道這一步在
            # 幹嘛，再看「公式」知道實際在算什麼，再看「文獻出處」知道
            # 憑什麼這樣算，最後才是「核心程式碼」跳進實作。原始
            # docstring 排在這些之後（見下面的 script 迴圈），當作想深入
            # 時的延伸閱讀，不是第一眼就要讀完的東西。
            #
            # 包在同一個 <details> 裡（2026-08-31 使用者要求可收合）：
            # 預設展開（跟 script 的 doc-details 相反——那個是延伸閱讀，
            # 這個是主要內容，第一眼就該看到，只是想收起來清空間時
            # 收得起來）。五個 _render_* 沒內容時各自回傳空字串，先組出
            # 內容再判斷是否為空，沒有任何一段有東西就不要印出空殼
            # <details>（大部分「穩健性/敏感度診斷」的步驟目前都還沒
            # 補這層說明）。
            teach_html = "".join([
                _render_key_points(step.get("key_points", [])),
                _render_prereq(step.get("prereq", [])),
                _render_formula(step.get("formula", [])),
                _render_refs(step.get("refs", [])),
                _render_core(step.get("core")),
            ])
            if teach_html:
                content_parts.append(
                    '<details class="teach-details" open>'
                    '<summary>教學說明（重點／公式／文獻出處／核心程式碼）</summary>'
                    f'{teach_html}</details>')

            for script in step.get("scripts", []):
                ext = script in step.get("external", {})
                upstream = step.get("external", {}).get(script)
                content_parts.append(_render_script_block(script, ext, upstream))
            content_parts.append("</article>")

        nav_parts.append("</ul>")
        content_parts.append("</section>")

    # 「未分類程式」：git 上有、但 stage_map.py 沒有任何步驟提到的 .py
    # 檔（2026-08-31 使用者要求「以後所有程式都要能自動進主控板」）。
    # 跟上面四大階段平行的第五個區塊，不是塞進某個既有階段底下——這批
    # 東西的共同點只有「還沒分類」，硬塞進某個階段反而是另一種誤導。
    unindexed = discover_unindexed_scripts()
    if unindexed:
        nav_parts.append('<a class="tree-stage" href="#stage-unindexed">'
                         f'未分類程式（{len(unindexed)}）</a><ul>')
        content_parts.append('<section class="stage-block" id="stage-unindexed">'
                             '<h2>未分類程式</h2>'
                             '<p class="note">這些 .py 檔已經在 GitHub 上，但還沒有人'
                             '把它們歸進上面哪個階段/步驟——多半是新腳本、或現有'
                             '步驟改了實作但忘記回頭更新 stage_map.py。要分類，把'
                             '路徑從這裡搬進 <code>status_dashboard/stage_map.py</code>'
                             '對應步驟的 <code>scripts</code> 清單即可（見'
                             ' CONTRIBUTING.md 第二節）。</p>')
        for script in unindexed:
            nav_parts.append(f'<li><a href="#{html.escape(_slugify(script))}">'
                             f'<code>{html.escape(script)}</code></a></li>')
            content_parts.append(
                f'<article class="step-block" id="{html.escape(_slugify(script))}">'
                + _render_script_block(script) + "</article>")
        nav_parts.append("</ul>")
        content_parts.append("</section>")

    nav_parts.append("</nav>")
    content_parts.append("</div>")

    parts.append('<div class="layout" id="layout">')
    parts.extend(nav_parts)
    parts.append('<div class="resizer" id="resizer"></div>')
    parts.extend(content_parts)
    parts.append("</div>")

    parts.append(_RESIZE_SCRIPT)
    parts.append(_PROBE_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


# 左右欄寬度可拖曳（2026-08-25 使用者要求，像 IDE 的側欄一樣）。純
# vanilla JS，沒有外部依賴；寬度存 localStorage，下次整理頁面／換頁
# 還記得（不然每次都要重拖一次，形同沒有這個功能）。這是主控板第一個
# 用到 JS 的地方——拖曳互動沒辦法用純 HTML/CSS 做到，其餘所有「不用
# 手動展開」的需求都還是靠伺服器端 render + <details>，能不用 JS 就
# 不用；`_PROBE_SCRIPT`（見下面）是第二個，理由同樣是純 HTML/CSS
# 做不到「頁面先秒開、探測結果晚一點自己冒出來」這件事。
_RESIZE_SCRIPT = """
<script>
(function () {
  var tree = document.getElementById("tree-pane");
  var resizer = document.getElementById("resizer");
  var layout = document.getElementById("layout");
  if (!tree || !resizer || !layout) return;
  var saved = localStorage.getItem("m45DashTreeWidth");
  if (saved) tree.style.width = saved + "px";
  var dragging = false;
  resizer.addEventListener("mousedown", function () {
    dragging = true;
    document.body.style.userSelect = "none";
  });
  document.addEventListener("mousemove", function (e) {
    if (!dragging) return;
    var rect = layout.getBoundingClientRect();
    var w = e.clientX - rect.left;
    var min = 160, max = rect.width - 300;
    if (w < min) w = min;
    if (w > max) w = max;
    tree.style.width = w + "px";
  });
  document.addEventListener("mouseup", function () {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    localStorage.setItem("m45DashTreeWidth", parseInt(tree.style.width, 10));
  });
})();
</script>
"""

# 頁面先秒開（server 端跳過即時探測，見 gather_status(probe=False)），
# 載入後這段 JS 打 /probe-status.json 補上真正的狀態（2026-09-02 使用者
# 要求）。回傳的是算好的 badge HTML 片段（見 _probe_status_json()），
# 這裡只負責找到對應的 .status-badge-slot 塞進去，不重算任何邏輯——
# 「怎麼畫一個 badge」只在 Python 維護一份。找不到對應 data-label 的
# 項目（理論上不會發生，兩邊資料同一次請求算出來的）直接跳過，不報錯。
_PROBE_SCRIPT = """
<script>
(function () {
  fetch("/probe-status.json").then(function (r) { return r.json(); })
    .then(function (data) {
      document.querySelectorAll(".status-row[data-label]").forEach(function (row) {
        var frag = data[row.dataset.label];
        if (frag === undefined) return;
        var slot = row.querySelector(".status-badge-slot");
        if (slot) slot.innerHTML = frag;
      });
    })
    .catch(function () { /* 探測失敗就維持「探測中」的樣子，不彈錯誤 */ });
})();
</script>
"""


_NAV = ('<nav class="nav"><a href="/">依步驟看</a>'
       '<a href="/workers">依雲端服務看</a></nav>')


def _worker_label_html(w: dict) -> str:
    """label 本身＋（有的話）它對應程式的可點連結＋執行參數。程式路徑
    跟參數直接來自 cloud_queue.txt 那一行（見 gather_worker_status()），
    不查任何索引。

    參數要一起顯示：像 p6_lowmass_v3_s13/s15/s17 這種同一支腳本切成
    多個 shard 平行跑的工作，光看腳本名稱三個都一樣（本來就是同一支，
    不是 bug），區分靠的是參數（--slopes 1.3/1.5/1.7），不顯示的話
    連結旁邊完全看不出這幾個 worker 實際在算不同的東西
    （2026-09-02 使用者反映）。"""
    label_html = html.escape(w["label"])
    script = w.get("script")
    if not script:
        return label_html
    args = w.get("args")
    args_html = (f'<code class="worker-args">{html.escape(args)}</code>'
                if args else "")
    return (f'{label_html}'
           f'<a class="script-link worker-script-link" '
           f'href="{html.escape(_doc_url(script))}"><code>'
           f'{html.escape(script)}</code> ↗</a>{args_html}')


def _worker_badge(w: dict) -> str:
    """`text` 這裡是**已經處理過逃逸**的 HTML 片段，不是純文字——
    `_worker_label_html()` 會內嵌一個真的 `<a>` 連結，所以組完之後
    不能再對 `text` 整段 `html.escape()`（那樣會把連結標籤逃逸成看得到
    的文字，不會真的變成連結）。純文字分支（閒置/連不上）本身是寫死
    的字面字串，不含使用者或外部資料，不逃逸也安全。`detail` 仍然是
    純文字，維持原本逐一逃逸。"""
    if w["assigned"]:
        state = w["state"]
        if state == "checking":
            cls = "checking"
            text = f"排定了 {_worker_label_html(w)}，探測中…"
            detail = ""
        elif state == "live":
            cls, text = "live", f"執行中：{_worker_label_html(w)}"
            bits = []
            if w.get("elapsed"):
                bits.append(html.escape(w["elapsed"]))
            if w.get("error"):
                bits.append(html.escape(w["error"]))
            detail = "　".join(bits)
        else:
            cls = "unknown"
            text = f"排定了 {_worker_label_html(w)}，但探測結果是「{html.escape(str(w.get('status', '?')))}」"
            detail = html.escape(w.get("note", w.get("error", "")))
    elif w.get("checking"):
        cls, text, detail = "checking", "探測中…", ""
    elif w.get("reachable") is True:
        cls, text, detail = "ok", "閒置中（機器連得上）", ""
    elif w.get("reachable") is False:
        cls, text, detail = "fail", "連不上", html.escape(w.get("error", ""))
    else:
        cls, text, detail = "pending", "閒置中", "Kaggle 沒有常駐機器，沒有工作時無法探測連線"
    return (f'<span class="badge {cls}">{text}</span>'
           f'<span class="detail">{detail}</span>')


def render_workers_html(status: dict) -> str:
    """以雲端服務（worker）為單位的第二種介面——單純回答「這個 worker
    現在是不是真的在跑」，不是「哪個研究步驟做到哪」（見
    `gather_worker_status()` 說明）。"""
    workers = status["workers"]
    running_n = sum(1 for w in workers if w["assigned"] and w.get("state") == "live")
    reachable_n = sum(1 for w in workers if not w["assigned"] and w.get("reachable"))

    parts = [f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>M45 IMF 專案主控板 — 雲端服務</title>
<style>
{_CSS}
</style></head><body>
<h1>M45 IMF 專案主控板</h1>
{_NAV}
<p class="sub">依雲端服務看——整理時間：{datetime.now():%Y-%m-%d %H:%M:%S}
（每個 worker 即時探測：有排工作的查工作狀態，SSH 閒置機器單純
ping 一下確認連得上；Kaggle 帳號閒置時沒有常駐機器可以探測）</p>

<div class="summary">
  <div class="pill {'live' if running_n else ''}">正在跑 {running_n}</div>
  <div class="pill">閒置且連得上 {reachable_n}</div>
  <div class="pill">worker 總數 {len(workers)}</div>
</div>
"""]

    if not workers:
        parts.append('<p class="note">沒有登記任何 worker'
                     '（kaggle_accounts.json／ssh_workers.json 都是空的）。</p>')

    for w in workers:
        parts.append(
            f'<div class="worker-row" data-worker="{html.escape(w["name"])}">'
            f'<strong>{html.escape(w["name"])}</strong>'
            f'<span class="kind">（{html.escape(w["kind"])}）</span>'
            f'<span class="worker-badge-slot">{_worker_badge(w)}</span></div>')

    parts.append(_WORKERS_PROBE_SCRIPT)
    parts.append("</body></html>")
    return "".join(parts)


# 跟 _PROBE_SCRIPT 同一個理由、同一套做法，見那邊的說明——這裡對應的
# 是 .worker-row[data-worker] / .worker-badge-slot，資料來源是
# /workers-probe.json。
_WORKERS_PROBE_SCRIPT = """
<script>
(function () {
  fetch("/workers-probe.json").then(function (r) { return r.json(); })
    .then(function (data) {
      document.querySelectorAll(".worker-row[data-worker]").forEach(function (row) {
        var frag = data[row.dataset.worker];
        if (frag === undefined) return;
        var slot = row.querySelector(".worker-badge-slot");
        if (slot) slot.innerHTML = frag;
      });
    })
    .catch(function () { /* 探測失敗就維持「探測中」的樣子，不彈錯誤 */ });
})();
</script>
"""


_CSS = """
.nav { margin: 0.3em 0 1em; font-size: 0.9em; }
.nav a { margin-right: 1em; }
.worker-row { border: 1px solid #999; border-radius: 4px; padding: 0.6em 0.9em;
             margin-bottom: 0.6em; }
.worker-row .kind { color: #777; font-size: 0.85em; margin-right: 0.6em; }
:root { color-scheme: light dark; }
body { font-family: -apple-system, "Microsoft JhengHei", sans-serif;
      max-width: 1400px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }
h1 { font-size: 1.4em; margin-bottom: 0.2em; }
.sub { color: #777; font-size: 0.85em; margin-top: 0; }
.summary { display: flex; gap: 0.6em; flex-wrap: wrap; margin: 1em 0 1.5em; }
.pill { border: 1px solid #888; border-radius: 3px; padding: 0.3em 0.7em;
       font-size: 0.9em; }
.pill.alive { border-color: #2a7; }
.pill.dead { border-color: #c33; }
.pill.warn { border-color: #c33; }
.pill.live { border-color: #a70; }
.warn-text { border: 1px solid #c33; padding: 0.5em 0.8em; font-size: 0.85em; }

/* 左側導覽（純錨點跳轉）＋右側全展開內容，兩欄式版面
   （2026-08-25 依使用者要求重做：原本巢狀 <details> 每層都要點開才
   看得到下一層，改成右邊一次全部展開，左邊只是跳轉捷徑）。*/
.layout { display: flex; align-items: flex-start; }
.tree { flex: 0 0 auto; width: 260px; position: sticky; top: 1em;
       max-height: calc(100vh - 2em); overflow-y: auto; font-size: 0.85em; }
.tree-stage { display: block; font-weight: 600; margin-top: 1em;
             text-decoration: none; }
.tree-stage:first-child { margin-top: 0; }
.tree ul { list-style: none; margin: 0.2em 0 0; padding-left: 0.8em; }
.tree li { margin: 0.2em 0; }
.tree li a { text-decoration: none; display: flex; align-items: baseline;
            gap: 0.4em; }
.tree-badge { font-size: 0.75em; padding: 0 0.4em; }
/* 拖曳分隔線，寬度可調（2026-08-25 使用者要求，像 IDE 側欄一樣）——
   純 CSS 只能做外觀，實際拖曳邏輯在 _RESIZE_SCRIPT 那段 JS。 */
.resizer { flex: 0 0 auto; width: 6px; margin: 0 0.8em; cursor: col-resize;
          background: rgba(128,128,128,0.15); border-radius: 3px;
          align-self: stretch; }
.resizer:hover { background: rgba(128,128,128,0.35); }
.content { flex: 1 1 auto; min-width: 0; }

.stage-block { border-top: 2px solid #999; padding-top: 0.6em; margin-top: 1.5em; }
.stage-block:first-child { margin-top: 0; }
.stage-block h2 { font-size: 1.15em; margin-bottom: 0.2em; }
.step-block { border-left: 2px solid #ccc; margin: 1em 0 1em 0.3em;
             padding: 0.2em 0 0.2em 0.9em; scroll-margin-top: 1em; }
.step-block h3 { font-size: 1em; margin: 0 0 0.3em; }
.note { font-size: 0.85em; color: #777; margin: 0.3em 0; }
.status-row { font-size: 0.85em; margin: 0.2em 0; }
.status-row code { margin-right: 0.5em; }
.script-block { margin: 0.5em 0 0.5em 0.6em; }
.script-link { font-size: 0.9em; text-decoration: none; }
.worker-script-link { margin-left: 0.5em; font-size: 0.85em; }
.worker-args { margin-left: 0.5em; font-size: 0.78em; color: #888; }
.script-link:hover { text-decoration: underline; }
/* 教學說明（重點／公式／文獻／核心程式碼）整層可收合，預設展開
   （2026-08-31 使用者要求）——跟下面 docstring 那個收合是同一種
   <details>，差別只在預設狀態：docstring 是延伸閱讀所以預設收合，
   這裡是主要內容所以預設展開，只是想清空間時收得起來。 */
.teach-details > summary { cursor: pointer; font-size: 0.82em; color: #666;
                           font-weight: 600; margin: 0.4em 0 0.2em; }
/* 說明（docstring）可收合，預設展開（2026-08-25 使用者要求）——
   跟 stage/step 層不一樣：那兩層拿掉了折疊，這裡是特意留著，因為
   docstring 常常很長，看不看得由使用者自己決定，不是一定要展開。 */
.doc-details summary { cursor: pointer; font-size: 0.8em; color: #777;
                       margin-top: 0.3em; }
.doc { font-size: 0.85em; background: rgba(128,128,128,0.06);
      padding: 0.6em 0.9em; border-radius: 3px; margin: 0.3em 0 0; }
.doc-p { margin: 0.5em 0; line-height: 1.75; }
.doc-pre { white-space: pre-wrap; font-family: Consolas, monospace;
          font-size: 0.95em; background: rgba(128,128,128,0.10);
          padding: 0.5em 0.7em; border-radius: 3px; margin: 0.5em 0;
          overflow-x: auto; }
.script-link.missing { font-size: 0.9em; color: #999; }
.script-link-note { font-size: 0.8em; color: #999; margin-left: 0.4em; }
.upstream-link { font-size: 0.8em; margin-left: 0.6em; }

/* 解說層（重點／公式／文獻／核心程式碼）——2026-08-26 使用者要求把
   說明做成「像文獻或教學文件」的可讀性。四塊各給一個左側色條，讓人
   掃過去就知道這段是哪一類資訊，不用讀完才分辨。 */
.callout { border-left: 3px solid #888; padding: 0.1em 0 0.1em 0.9em;
          margin: 0.8em 0 0.8em 0.3em; }
.callout-h { font-size: 0.78em; font-weight: 600; letter-spacing: 0.08em;
            color: #777; margin-bottom: 0.3em; }
.callout.kp { border-left-color: #2a7; }
.callout.fm { border-left-color: #47c; }
.callout.rf { border-left-color: #a70; }
.callout.cr { border-left-color: #c47; }
.callout.pq { border-left-color: #7a5; }
.kp-list { margin: 0.2em 0; padding-left: 1.2em; font-size: 0.88em;
          line-height: 1.7; }
.kp-list li { margin: 0.25em 0; }
.formula-item { margin: 0.5em 0 0.8em; }
.formula-expr { font-family: Consolas, monospace; font-size: 0.9em;
               background: rgba(70,120,200,0.10); padding: 0.6em 0.8em;
               border-radius: 3px; margin: 0 0 0.3em; white-space: pre-wrap;
               overflow-x: auto; }
.formula-field { font-size: 0.84em; margin: 0.3em 0; line-height: 1.7; }
.ff-lab { display: inline-block; font-weight: 600; color: #47c;
         margin-right: 0.5em; font-size: 0.92em; }
mark.hl { background: rgba(255,214,0,0.35); color: inherit;
         padding: 0.05em 0.15em; border-radius: 2px; }
.formula-where, .formula-src { font-size: 0.82em; color: #777;
                              margin: 0.2em 0; line-height: 1.65; }
.ref-table { border-collapse: collapse; font-size: 0.82em; width: 100%;
            margin: 0.2em 0; }
.ref-table th { text-align: left; font-weight: 600; color: #777;
               border-bottom: 1px solid rgba(128,128,128,0.35);
               padding: 0.25em 0.6em 0.25em 0; font-size: 0.95em; }
.ref-table td { vertical-align: top; padding: 0.3em 0.6em 0.3em 0;
               border-bottom: 1px solid rgba(128,128,128,0.15);
               line-height: 1.6; }
.ref-cite { white-space: normal; min-width: 12em; }
.ref-role { color: #777; }
.ref-local { white-space: nowrap; font-size: 0.95em; }
.core-fn { margin: 0.2em 0 0.4em; font-size: 0.9em; }
.core-where { color: #888; font-size: 0.85em; margin-left: 0.6em; }
.inline-src { text-decoration: none; }
.inline-src:hover { text-decoration: underline; }
.badge { border-radius: 3px; padding: 0.05em 0.5em; font-size: 0.85em;
        margin-right: 0.5em; }
.badge.ok { background: rgba(34,170,102,0.2); }
.badge.fail { background: rgba(204,51,51,0.2); }
.badge.live { background: rgba(200,140,0,0.2); }
.badge.pending { background: rgba(128,128,128,0.15); }
.badge.unknown { background: rgba(128,128,128,0.1); }
.badge.checking { background: rgba(128,128,128,0.1); font-style: italic; }
.detail { color: #777; font-size: 0.85em; }
code { font-family: Consolas, monospace; }

@media (max-width: 900px) {
  .layout { flex-direction: column; }
  .tree { position: static; max-height: none; width: 100% !important; }
  .resizer { display: none; }
}
"""


# ==================================================================
# 伺服器
# ==================================================================

# sync 只做一次、兩個路由共用——workers 頁不特別顯示同步狀態，但一樣
# 從這次同步受益（資料層讀的是同一份 REPO_ROOT）。
def _probe_status_json() -> str:
    """`/` 頁面秒開後，JS 拿這個補上真正的探測結果（2026-09-02 使用者
    要求）。回傳 {label: 這個 label 現在該顯示的 badge HTML} ——直接
    回傳算好的 HTML 片段，不是原始狀態資料，是為了讓 badge 怎麼畫這件
    事只在 Python（`_status_badge()`）維護一份，不要在 JS 那邊重寫一次
    同樣的邏輯、之後兩邊各自改各自的、越改越不同步。"""
    status = gather_status(probe=True)
    label_status = status["label_status"]
    fragments = {label: _status_badge(st) for label, st in label_status.items()}
    return json.dumps(fragments, ensure_ascii=False)


def _workers_probe_json() -> str:
    """`/workers` 頁面版的 `_probe_status_json()`，同一個理由。"""
    status = gather_worker_status(probe=True)
    fragments = {w["name"]: _worker_badge(w) for w in status["workers"]}
    return json.dumps(fragments, ensure_ascii=False)


_ROUTES = {
    "/": lambda sync: render_html(gather_status(probe=False), sync),
    "/workers": lambda sync: render_workers_html(gather_worker_status(probe=False)),
    "/probe-status.json": lambda sync: _probe_status_json(),
    "/workers-probe.json": lambda sync: _workers_probe_json(),
}

# 上面兩個 .json 路由回傳的是 application/json，不是 text/html——
# do_GET() 用副檔名判斷，不用另外開一份路由表。
_JSON_ROUTES = {"/probe-status.json", "/workers-probe.json"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — 覆寫標準函式庫的命名慣例
        # 路由比對前要先去掉查詢字串（?key=value）——之前是直接拿
        # self.path 整段比對，2026-08-31 部署到協調 VM 後透過 Cloud
        # Shell Web Preview／IAP tunnel 測試時發現打不開：Web Preview
        # 開網址時會自動加 ?authuser=0，self.path 變成
        # "/?authuser=0"，對不到 _ROUTES 裡的 "/"，直接回 404。
        # 一般瀏覽器直接打開網址不會加這種參數，本機測試一直沒踩到。
        path = urlsplit(self.path).path
        route = _ROUTES.get(path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        is_json = path in _JSON_ROUTES
        try:
            sync = sync_repo_from_github()
            body = route(sync).encode("utf-8")
        except Exception as e:  # noqa: BLE001 — 任何未預期例外都不該讓伺服器整個掛掉
            import traceback
            traceback.print_exc()
            if is_json:
                body = json.dumps({"_error": str(e)}).encode()
            else:
                body = (f"<pre>整理狀態時發生錯誤：\n{html.escape(str(e))}\n\n"
                        "看主控台的完整 traceback。</pre>").encode()
        self.send_response(200)
        content_type = "application/json; charset=utf-8" if is_json else "text/html; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        if _restart_pending:
            _self_restart()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{datetime.now():%H:%M:%S}] " + fmt % args, flush=True)


def _bind_server(retries: int = 10, delay: float = 0.5) -> ThreadingHTTPServer:
    """自動重啟（見 `_self_restart()`）時，新行程可能在舊行程真正放掉
    連接埠前就先啟動，短暫重試等它讓出來，而不是直接炸掉。"""
    for attempt in range(retries):
        try:
            return ThreadingHTTPServer((HOST, PORT), Handler)
        except OSError:
            if attempt == retries - 1:
                raise
            time.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


def acquire_lock() -> None:
    """單一實例鎖，跟 `cloud_queue.py` 的 `acquire_lock()` 同一套邏輯
    （2026-08-31 補上）——起因：`launch_dashboard.vbs` 每次雙擊都無條件
    `pyw app.py`，不會檢查是不是已經有一份在跑。`ThreadingHTTPServer`
    預設 `allow_reuse_address=True`，同一個埠被第二個行程綁上時 Windows
    不會報錯擋下來，於是同一頁面背後疊了好幾個互相搶連線的行程，其中
    有的還會因為 pyw 沒主控台、使用者連 PID 是哪個都看不到、殺不掉
    （見 taskkill 對某個殘留行程回報「拒絕存取」的實際案例）。

    偵測到活著的舊行程就直接結束，讓 `launch_dashboard.vbs` 後面那行
    `sh.Run "http://127.0.0.1:8866/"` 開瀏覽器連到那個既有行程即可，
    不是錯誤，所以用 exit code 0。鎖檔案殘留但行程已死（例如上次被
    taskkill /F 或斷電）視為正常，直接接手。"""
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            old_pid = int(LOCK.read_text().strip())
        except (ValueError, OSError):
            old_pid = None
        alive = cloud_queue._pid_alive(old_pid) if old_pid is not None else False
        if alive:
            print(f"偵測到主控板已經在跑（PID {old_pid}），這次啟動結束，"
                 f"改開瀏覽器連過去。", flush=True)
            sys.exit(0)
        print("鎖檔案殘留但行程已經不在了，清掉重新接手。", flush=True)
        try:
            LOCK.unlink()
        except FileNotFoundError:
            pass
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def release_lock() -> None:
    try:
        if int(LOCK.read_text().strip()) == os.getpid():
            LOCK.unlink()
    except (FileNotFoundError, ValueError, OSError):
        pass


def main() -> None:
    acquire_lock()
    server = _bind_server()
    url = f"http://127.0.0.1:{PORT}/"
    print(f"M45 IMF 主控板啟動：{url}（Ctrl+C 結束）", flush=True)
    if HOST != "127.0.0.1":
        print(f"注意：監聽位址是 {HOST}，這台機器的網卡連得到這個服務"
              f"（不是只有這台自己）。這個頁面沒有密碼保護，只能靠防火牆"
              f"擋——確認擋住的來源網段是正確的，不要在沒有對應防火牆"
              f"規則的機器上這樣設。", flush=True)
    # 開瀏覽器交給桌面捷徑用的 launch_dashboard.vbs 負責（sh.Run 那行），
    # 這裡不重複開，避免透過捷徑啟動時跳出兩個分頁。直接用
    # `py app.py` 手動跑的話，自己貼網址開就好。
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        release_lock()


if __name__ == "__main__":
    main()
