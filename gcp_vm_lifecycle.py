# -*- coding: utf-8 -*-
"""管理 GCP VM 的自動開關機。

**為什麼要自動開關，不是常駐開著就好**：多帳號資源池用的是各自的
GCP 免費試用額度（$300／90 天），e2-highcpu-8 約 $0.221/hr（美國區
基準價，asia-east1 通常再貴 5-10%），90 天常駐開著單台就接近
$480——超過額度。所以派工前才開機、閒置一段時間沒工作就關機，不是
效能優化，是免費額度撐不撐得住的問題。

只在 worker 有填 `gcp_project`／`gcp_zone`／`gcp_instance` 這三個
欄位時生效（見 ssh_workers.py／ssh_workers.json.example）——沒填就
這支模組完全不動作，backward compatible，不影響非 GCP 的 SSH worker
（例如 Oracle）。

需要本機已裝 gcloud CLI 並完成 `gcloud auth login`（用中控機操作者
自己的 Google 帳號），且該帳號在 VM 所在的專案被授予
`compute.instanceAdmin.v1`（建議用 IAM 條件限縮到單一 VM，不要整個
專案——中控機操作者要能開關隊友的 VM，但不需要、也不應該拿到隊友
專案裡其他資源的控制權）。完整設定步驟見
docs/reference/CLOUD_WORKERS_IAP_SETUP.md。
"""
from __future__ import annotations

import shutil
import subprocess

# gcloud 在 Windows 上是 gcloud.cmd（批次檔殼），不是純 .exe——
# subprocess 不開 shell=True 時直接给 "gcloud" 會因為 Win32
# CreateProcess 不做 PATHEXT 副檔名搜尋而找不到檔案。shutil.which()
# 會照 PATHEXT 規則正確解析出完整路徑（含副檔名），一次解析、全模組
# 共用，不必每次呼叫都重新搜尋 PATH。
_GCLOUD = shutil.which("gcloud")

# subprocess.CREATE_NO_WINDOW 只存在於 Windows 版的 subprocess 模組
# （2026-08-26 CodeRabbit review 訂正：原本直接寫 subprocess.CREATE_NO_WINDOW，
# 這個專案目前只在 Windows 上跑沒問題，但屬性本身在非 Windows 平台
# 不存在，直接參照會在 subprocess.run() 執行前就先拋出 AttributeError，
# 比「忘記防閃視窗」更嚴重——用 getattr 給預設值 0（等於不加任何旗標，
# 跟沒傳這個參數效果相同），非 Windows 平台安全地變成無操作）。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# 這裡的逾時只包一次 gcloud 呼叫本身（等 GCP API 操作完成回應），不是
# 等到整台機器完全能連線——開機後 VM 內部開機＋IAP tunnel 重新連線
# 還要另外一段時間，那段等待交給呼叫端（ssh_sync.push()）用既有的
# 「這一輪失敗、下一輪重試」機制處理，不在這裡原地阻塞（見
# ensure_running() 的說明）。
_GCLOUD_TIMEOUT = 60


def _run(args: list[str], timeout: int = _GCLOUD_TIMEOUT
        ) -> subprocess.CompletedProcess:
    if _GCLOUD is None:
        raise FileNotFoundError("gcloud 指令找不到")
    return subprocess.run(
        [_GCLOUD, *args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
        creationflags=_CREATE_NO_WINDOW)


def is_gcp_managed(w: dict) -> bool:
    """判斷這個 worker 有沒有填生命週期管理需要的三個欄位。"""
    return bool(w.get("gcp_project") and w.get("gcp_zone")
               and w.get("gcp_instance"))


def describe_status(w: dict) -> str:
    """查 VM 目前狀態：RUNNING／TERMINATED／STOPPING／PROVISIONING／
    STAGING 等（GCP 官方狀態值）。查詢本身失敗（逾時、gcloud 沒裝、
    認證過期）一律回傳 "UNKNOWN"——呼叫端保守處理，不貿然當成任何一種
    確定狀態。"""
    if _GCLOUD is None:
        print("  找不到 gcloud 指令，VM 生命週期管理跳過這一輪——先安裝 "
             "Google Cloud CLI，見 docs/reference/CLOUD_WORKERS_IAP_SETUP.md")
        return "UNKNOWN"
    try:
        r = _run(["compute", "instances", "describe", w["gcp_instance"],
                 f"--project={w['gcp_project']}", f"--zone={w['gcp_zone']}",
                 "--format=value(status)"])
    except subprocess.TimeoutExpired:
        print(f"  查詢 VM {w['gcp_instance']} 狀態逾時，當作 UNKNOWN")
        return "UNKNOWN"
    if r.returncode != 0:
        print(f"  查詢 VM {w['gcp_instance']} 狀態失敗："
             f"{r.stderr.strip()[:300]}")
        return "UNKNOWN"
    return r.stdout.strip() or "UNKNOWN"


def start_vm(w: dict) -> bool:
    print(f"  VM {w['gcp_instance']} 目前沒開機，發出開機指令...")
    try:
        r = _run(["compute", "instances", "start", w["gcp_instance"],
                 f"--project={w['gcp_project']}", f"--zone={w['gcp_zone']}"],
                timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  開機指令失敗（{type(e).__name__}），下一輪重試")
        return False
    if r.returncode != 0:
        print(f"  開機指令失敗：{r.stderr.strip()[:300]}")
        return False
    print("  開機指令已送出，VM 內部開機＋IAP tunnel 重新連線還要一段"
         "時間，這一輪先當作沒準備好，下一輪（約 60 秒後）再檢查")
    return True


def stop_vm(w: dict) -> bool:
    print(f"  VM {w['gcp_instance']} 閒置超過門檻，關機省額度...")
    try:
        r = _run(["compute", "instances", "stop", w["gcp_instance"],
                 f"--project={w['gcp_project']}", f"--zone={w['gcp_zone']}"],
                timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  關機指令失敗（{type(e).__name__}），下一輪重試")
        return False
    if r.returncode != 0:
        print(f"  關機指令失敗：{r.stderr.strip()[:300]}")
        return False
    return True


def ensure_running(w: dict) -> bool:
    """`ssh_sync.push()` 派工前呼叫。回傳這個 worker 現在能不能連線。

    沒填 GCP 三個欄位的 worker 一律回傳 True（不歸這支模組管，交給
    既有的 SSH 連線邏輯直接判斷）。有填的話：VM 已經是 RUNNING 就直接
    放行；還在轉換中（STOPPING／PROVISIONING／STAGING）就回傳 False
    讓下一輪再檢查；其餘狀態（TERMINATED／SUSPENDED／UNKNOWN）一律
    嘗試開機後回傳 False——UNKNOWN 也嘗試開機是因為「查詢失敗」不代表
    「其實已經在跑」，寧可多送一次開機指令（GCP 對已經是 RUNNING 的
    VM 送 start 是無害的 no-op），也不要因為查詢本身不穩定就永遠不
    開機。

    這裡刻意不原地等待開機完成（不 sleep 迴圈輪詢）——開機＋IAP tunnel
    重新連線通常要 30-60 秒以上，堵住 cloud_queue.py 主迴圈去等會拖累
    同一輪其他 worker 的派工，交給呼叫端既有的「這一輪失敗、下一輪
    （60 秒後）重試」機制自然收斂，比原地阻塞便宜。
    """
    if not is_gcp_managed(w):
        return True
    status = describe_status(w)
    if status == "RUNNING":
        return True
    if status in ("STOPPING", "PROVISIONING", "STAGING"):
        print(f"  VM {w['gcp_instance']} 狀態為 {status}（轉換中），"
             f"下一輪再檢查")
        return False
    start_vm(w)
    return False
