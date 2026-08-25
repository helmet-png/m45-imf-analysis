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
import html
import os
import shlex
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

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
PROBE_CACHE_TTL = 15  # 秒；同一個 label 這段時間內重複整理不重打 SSH
PROBE_MAX_WORKERS = 4    # 同時最多幾個 worker 一起探測
PROBE_DEADLINE_S = 25    # 這次整理頁面，即時探測合計最多等這麼久——
                         # 小於 ssh_sync.poll() 自己單次的 30 秒逾時，
                         # 確保一個連不上的 worker 不會拖累整頁的回應
                         # 時間（2026-08-25 CodeRabbit review）
_probe_cache: dict[str, tuple[float, dict]] = {}


# ==================================================================
# 資料層
# ==================================================================

def read_docstring(rel_path: str) -> str:
    """讀一支腳本檔頭的 module docstring，原文照搬，不重寫一份說明。"""
    path = REPO_ROOT / rel_path
    if not path.exists():
        return f"（找不到檔案，路徑可能已經搬動：{rel_path}）"
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


def _run_probes(to_probe: dict[str, dict]) -> dict[str, dict]:
    """對 `to_probe`（label -> {worker, kind, item}）裡的每個標籤做即時
    探測，套用 `_run_concurrent()` 的併發＋整體時間預算。"""
    if not to_probe:
        return {}
    fns = {label: (lambda info=info: probe_live(info["worker"], info["kind"], info["item"]))
          for label, info in to_probe.items()}
    raw = _run_concurrent(fns)
    results = {}
    for label, info in to_probe.items():
        live = raw[label]
        live.setdefault("elapsed", None)
        state, note = _map_probe_state(live.get("status", "unknown"))
        out = {"state": state, "worker": info["worker"], "kind": info["kind"], **live}
        if note:
            out["note"] = note
        results[label] = out
    return results


def gather_status() -> dict:
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
    label_status.update(_run_probes(to_probe))

    return {
        "alive": alive, "pid": pid,
        "cloud_workers": cloud_workers, "cloud_items": cloud_items,
        "cloud_done": cloud_done, "label_status": label_status,
    }


def gather_worker_status() -> dict:
    """以雲端服務（worker）為單位，不是以步驟為單位——單純回答「這個
    worker 現在是不是真的在跑」（2026-08-25 使用者要求新增的第二種
    介面）。跟 `gather_status()` 是同一批來源資料的另一種切法，不重複
    定義佇列格式，但因為關心的問題不同，即時探測的對象也不同：這裡
    探測的是「這個 worker 上排定的第一個未完成 label」，`gather_status()`
    探測的是「stage_map.py 裡列出的每個 label」——兩邊在同一個 worker
    同時只有一個槽位在跑的前提下通常會對到同一個工作，但這支函式就算
    stage_map.py 完全沒收錄某個 label，也照樣看得到。"""
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

    probe_results = _run_probes(to_probe)
    ping_fns = {name: (lambda n=name: _ssh_ping(n)) for name in idle_ssh}
    ping_results = _run_concurrent(ping_fns) if ping_fns else {}

    workers_out = []
    for name, kind in sorted(cloud_workers.items()):
        if name in probe_results:
            r = probe_results[name]
            workers_out.append({"name": name, "kind": kind, "assigned": True,
                                "label": assigned[name]["label"], **r})
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
    "pending": "待派工", "unknown": "沒有紀錄",
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
    else:
        cls, text, detail = "unknown", "沒有紀錄", st.get("note", "")
    return (f'<span class="badge {cls}">{html.escape(text)}</span>'
           f'<span class="detail">{html.escape(detail)}</span>')


def render_html(status: dict) -> str:
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
（重新整理頁面 = 重新讀取所有來源檔案 + 對進行中工作即時探測）</p>

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

    for stage in STAGES:
        parts.append(f'<details class="stage"><summary>{html.escape(stage["name"])}</summary>')
        for step in stage["steps"]:
            parts.append(f'<details class="step"><summary>{html.escape(step["name"])}</summary>')
            if step.get("note"):
                parts.append(f'<p class="note">{html.escape(step["note"])}</p>')
            for label in step.get("queue_labels", []):
                st = label_status.get(label)
                if st is None:
                    continue
                parts.append(f'<div class="status-row"><code>{html.escape(label)}</code>'
                             f'{_status_badge(st)}</div>')
            for script in step.get("scripts", []):
                doc = read_docstring(script)
                parts.append(
                    f'<details class="script"><summary><code>{html.escape(script)}</code></summary>'
                    f'<pre class="doc">{html.escape(doc)}</pre></details>')
            parts.append("</details>")
        parts.append("</details>")

    parts.append("</body></html>")
    return "".join(parts)


_NAV = ('<nav class="nav"><a href="/">依步驟看</a>'
       '<a href="/workers">依雲端服務看</a></nav>')


def _worker_badge(w: dict) -> str:
    if w["assigned"]:
        state = w["state"]
        if state == "live":
            cls, text = "live", f"執行中：{w['label']}"
            bits = []
            if w.get("elapsed"):
                bits.append(f"已耗時 {w['elapsed']}")
            if w.get("error"):
                bits.append(w["error"])
            detail = "　".join(bits)
        else:
            cls, text = "unknown", f"排定了 {w['label']}，但探測結果是「{w.get('status', '?')}」"
            detail = w.get("note", w.get("error", ""))
    elif w.get("reachable") is True:
        cls, text, detail = "ok", "閒置中（機器連得上）", ""
    elif w.get("reachable") is False:
        cls, text, detail = "fail", "連不上", w.get("error", "")
    else:
        cls, text, detail = "pending", "閒置中", "Kaggle 沒有常駐機器，沒有工作時無法探測連線"
    return (f'<span class="badge {cls}">{html.escape(text)}</span>'
           f'<span class="detail">{html.escape(detail)}</span>')


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
            f'<div class="worker-row"><strong>{html.escape(w["name"])}</strong>'
            f'<span class="kind">（{html.escape(w["kind"])}）</span>'
            f'{_worker_badge(w)}</div>')

    parts.append("</body></html>")
    return "".join(parts)


_CSS = """
.nav { margin: 0.3em 0 1em; font-size: 0.9em; }
.nav a { margin-right: 1em; }
.worker-row { border: 1px solid #999; border-radius: 4px; padding: 0.6em 0.9em;
             margin-bottom: 0.6em; }
.worker-row .kind { color: #777; font-size: 0.85em; margin-right: 0.6em; }
:root { color-scheme: light dark; }
body { font-family: -apple-system, "Microsoft JhengHei", sans-serif;
      max-width: 900px; margin: 2em auto; padding: 0 1em; line-height: 1.6; }
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
details.stage { border: 1px solid #999; border-radius: 4px; margin-bottom: 0.8em;
               padding: 0.4em 0.8em; }
details.stage > summary { font-size: 1.15em; font-weight: 600; cursor: pointer; }
details.step { border-left: 2px solid #ccc; margin: 0.5em 0 0.5em 0.5em;
              padding: 0.3em 0 0.3em 0.8em; }
details.step > summary { font-weight: 600; cursor: pointer; }
details.script { margin: 0.3em 0 0.3em 1em; }
details.script > summary { cursor: pointer; font-size: 0.9em; }
.note { font-size: 0.85em; color: #777; margin: 0.3em 0; }
.status-row { font-size: 0.85em; margin: 0.2em 0 0.2em 1em; }
.status-row code { margin-right: 0.5em; }
.doc { white-space: pre-wrap; font-size: 0.82em; background: rgba(128,128,128,0.08);
      padding: 0.6em; border-radius: 3px; }
.badge { border-radius: 3px; padding: 0.05em 0.5em; font-size: 0.85em;
        margin-right: 0.5em; }
.badge.ok { background: rgba(34,170,102,0.2); }
.badge.fail { background: rgba(204,51,51,0.2); }
.badge.live { background: rgba(200,140,0,0.2); }
.badge.pending { background: rgba(128,128,128,0.15); }
.badge.unknown { background: rgba(128,128,128,0.1); }
.detail { color: #777; font-size: 0.85em; }
code { font-family: Consolas, monospace; }
"""


# ==================================================================
# 伺服器
# ==================================================================

_ROUTES = {
    "/": lambda: render_html(gather_status()),
    "/workers": lambda: render_workers_html(gather_worker_status()),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 — 覆寫標準函式庫的命名慣例
        route = _ROUTES.get(self.path)
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = route().encode("utf-8")
        except Exception as e:  # noqa: BLE001 — 任何未預期例外都不該讓伺服器整個掛掉
            import traceback
            traceback.print_exc()
            body = (f"<pre>整理狀態時發生錯誤：\n{html.escape(str(e))}\n\n"
                    "看主控台的完整 traceback。</pre>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{datetime.now():%H:%M:%S}] " + fmt % args, flush=True)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"M45 IMF 主控板啟動：{url}（Ctrl+C 結束）", flush=True)
    # 開瀏覽器交給桌面捷徑用的 launch_dashboard.vbs 負責（sh.Run 那行），
    # 這裡不重複開，避免透過捷徑啟動時跳出兩個分頁。直接用
    # `py app.py` 手動跑的話，自己貼網址開就好。
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
