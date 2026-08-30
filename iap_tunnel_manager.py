# -*- coding: utf-8 -*-
"""維護 IAP SSH tunnel 常駐連線。

`ssh_workers.json` 裡 `host` 填 `"localhost"`、且填了 `gcp_project`／
`gcp_zone`／`gcp_instance` 的 worker，這支程式負責幫它開一條
`gcloud compute start-iap-tunnel`，讓 ssh_sync.py 照平常方式對
`localhost:<port>` 連線——不用改任何既有的 SSH 邏輯（ssh_workers.py
的 ssh_base()／scp_base() 本來就是照 host/port/key_path 組指令，
指到 localhost 一樣能用）。

**為什麼要 IAP，不直接開 22 埠給某個來源 IP**：來源 IP 白名單會在
本機換網路（換家、換學校網路、電腦睡眠喚醒換到新 IP）時整個失效，
2026-08-25 就真的斷線卡了好幾個小時，且來源 IP 屬於台東高中的 GSN
政府網段，之後也不會固定。IAP tunnel 靠 Google 帳號驗證，不管在哪個
網路都連得上，且 22 埠完全不對外開放，只放行 IAP 的固定網段
（35.235.240.0/20）。完整設定步驟見
docs/reference/CLOUD_WORKERS_IAP_SETUP.md。

**這支程式要常駐、斷線要自動重連**：tunnel 行程本身可能因為本機
網路波動、或 VM 被自動關機（見 gcp_vm_lifecycle.py）而斷線，每隔
CHECK_SECS 秒檢查一次還活不活著，死了就重開。跟 cloud_queue.py 一樣
靠 restart_queue_on_boot.ps1 的既有 Windows 排程機制監看、掛掉自動
重啟這支程式本身（見該檔案裡的 Restart-QueueIfNotRunning 呼叫）。

用法：
    python iap_tunnel_manager.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import ssh_workers
from run_queue import _pid_alive

HERE = Path(__file__).resolve().parent
LOCK = HERE / "logs" / "iap_tunnel_manager.lock"
CHECK_SECS = 30
# 斷線後不要馬上重連，給網路／VM 一點恢復時間，避免瘋狂重試灌爆
# gcloud API 呼叫額度。
#
# **2026-08-30 從 15 秒固定間隔改成漸進式退避（見下面 RESTART_BACKOFF_*
# 三個常數），這是一次真實事故的教訓**：協調 VM 遷移後，`gcp1` 的通道
# 連續斷線好幾天，每次都是固定 15 秒後重試，累積下來對 Google IAP 端點
# （`wss://tunnel.cloudproxy.app/...`）連續打了超過一萬七千次連線請求
# （3 天 × 86400 秒 / 15 秒 ≈ 17,280 次）。查證時發現**同一個連線失敗
# 訊息本身會忽好忽壞**：IAM／防火牆／服務帳戶／OAuth scope 全部確認
# 正確，手動單次測試會成功，但這支程式的高頻重試迴圈卻穩定失敗
# （`ConnectionCreationError: Error while connecting [4033: 'not
# authorized']`）——最合理的解釋是打太頻繁觸發了 IAP 這一層的某種
# 頻率限制／防濫用機制，不是真的權限設定錯誤。改成失敗次數越多、
# 等越久的漸進式退避，才不會在偶發的網路抖動或短暫額度限制時，
# 反而用高頻重試把自己鎖死在被拒絕的狀態出不來。
RESTART_BACKOFF_S = 15           # 第一次失敗後的等待秒數（維持原本反應速度）
RESTART_BACKOFF_MAX_S = 300      # 退避上限（5 分鐘），不要無限拉長
RESTART_BACKOFF_MULT = 2         # 每次失敗，等待時間乘這個倍數

# 見 gcp_vm_lifecycle.py 同一行的說明：gcloud 在 Windows 上是
# gcloud.cmd，用 shutil.which() 才能正確解析出完整路徑。
_GCLOUD = shutil.which("gcloud")

# 見 gcp_vm_lifecycle.py 同一行的說明：CREATE_NO_WINDOW 只存在於
# Windows，getattr 給預設值 0 讓非 Windows 平台安全地變成無操作，
# 不會在 subprocess.Popen() 執行前就先拋出 AttributeError
# （2026-08-26 CodeRabbit review 訂正）。
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ---------------------------------------------------------------- 鎖
# 跟 cloud_queue.py 的 acquire_lock()/release_lock() 是同一套
# TOCTOU-safe 檔案鎖，直接照抄，不重新設計一套——理由跟 cloud_queue.py
# 開頭「沿用 kaggle_queue.py 已經驗證過的東西」一樣。

def acquire_lock() -> None:
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
                print("無法確認鎖檔案是否還存活，保守起見當作還活著，退出。",
                     flush=True)
                sys.exit(1)
            if alive:
                print(f"偵測到另一個 iap_tunnel_manager.py 正在跑"
                     f"（PID {old_pid}），退出。", flush=True)
                sys.exit(1)
            print("鎖檔案殘留，清掉重新搶鎖。", flush=True)
            try:
                current = LOCK.read_text().strip()
            except (FileNotFoundError, OSError):
                current = None
            if current != str(old_pid):
                continue
            try:
                LOCK.unlink()
            except FileNotFoundError:
                pass
            continue
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return


def release_lock() -> None:
    try:
        if int(LOCK.read_text().strip()) == os.getpid():
            LOCK.unlink()
    except (FileNotFoundError, ValueError, OSError):
        pass


# ---------------------------------------------------------------- tunnel

def _tunnel_workers() -> dict[str, dict]:
    """找出需要維護 IAP tunnel 的 worker：host 填 "localhost" 且三個
    GCP 欄位都填了——這個組合本身就是「這個連線要靠本機的 IAP tunnel」
    的宣告，不另外加第四個布林欄位（見 ssh_workers.json.example）。"""
    out = {}
    for name, w in ssh_workers.load_workers().items():
        if w["host"] != "localhost":
            continue
        if not (w["gcp_project"] and w["gcp_zone"] and w["gcp_instance"]):
            continue
        out[name] = w
    return out


def _spawn(name: str, w: dict) -> subprocess.Popen:
    print(f"[{datetime.now():%H:%M:%S}] 開啟 {name} 的 IAP tunnel"
         f"（localhost:{w['port']} → {w['gcp_instance']}:22）...", flush=True)
    log_path = HERE / "logs" / f"iap_tunnel_{name}.log"
    log_path.parent.mkdir(exist_ok=True)
    # 這個檔案控制代碼要活得跟 tunnel 子行程一樣久（Popen 的 stdout
    # 目標），不能用 `with` 立刻關掉——子行程結束或被下一輪偵測到掛掉
    # 重開時，作業系統會在行程結束時自動收回這個 fd，不需要這裡手動
    # close()。
    log_f = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
    return subprocess.Popen(
        [_GCLOUD, "compute", "start-iap-tunnel", w["gcp_instance"], "22",
         f"--local-host-port=localhost:{w['port']}",
         f"--zone={w['gcp_zone']}", f"--project={w['gcp_project']}"],
        stdout=log_f, stderr=subprocess.STDOUT,
        creationflags=_CREATE_NO_WINDOW)


def main() -> None:
    if _GCLOUD is None:
        print("找不到 gcloud 指令——先安裝 Google Cloud CLI，見 "
             "docs/reference/CLOUD_WORKERS_IAP_SETUP.md", flush=True)
        return

    acquire_lock()
    import atexit
    atexit.register(release_lock)

    procs: dict[str, subprocess.Popen] = {}
    # 每個 worker 各自累計「連續失敗次數」，算漸進式退避秒數用
    # （見上面 RESTART_BACKOFF_* 常數的說明）。成功一次
    # （tunnel 撐過一輪 CHECK_SECS 都還活著）就把對應計數歸零，
    # 不然只要斷過一次線，之後即使恢復正常也會一直用最長等待時間。
    fail_counts: dict[str, int] = {}
    print(f"IAP tunnel 管理器啟動 {datetime.now():%Y-%m-%d %H:%M:%S}",
         flush=True)
    # 2026-08-26 CodeRabbit review 訂正：原本只註冊 release_lock()，
    # 這支程式收到 Ctrl+C 或遇到未預期例外結束時，procs 裡還活著的
    # gcloud tunnel 子行程完全沒人管，會變成孤兒行程繼續佔用本機埠，
    # 下次啟動這支程式時那個埠已經被占用、新 tunnel 開不起來，得手動
    # 用工作管理員找出殘留的 gcloud.exe 才能清乾淨。用 try/finally 確保
    # 這兩種結束路徑都會嘗試優雅關閉（terminate + 等 10 秒）再強制 kill
    # 仍不退的——atexit 註冊的 release_lock() 保持不變，這裡另外處理
    # procs，兩者互不影響。**這裡沒有解決的殘留風險**：Windows 的
    # `taskkill /F`／工作管理員「結束工作」等於直接砍掉行程，Python
    # 不會執行 finally（等同 SIGKILL），這種情況下子行程一樣會變孤兒
    # ——要完全杜絕需要 Windows Job Object（把子行程綁進一個「母行程死
    # 了就跟著死」的作業系統群組），這裡先解決常見的兩種結束路徑，
    # Job Object 是後續要做才做的加強，不是這次的範圍。
    try:
        while True:
            targets = _tunnel_workers()
            if not targets:
                print("沒有任何 worker 設定 IAP tunnel（host=localhost 且填了 "
                     "GCP 三個欄位），閒置等待——見 ssh_workers.json.example",
                     flush=True)
            for name, w in targets.items():
                proc = procs.get(name)
                if proc is not None and proc.poll() is None:
                    # 還活著。撐過一輪檢查間隔（CHECK_SECS）才算真的穩定，
                    # 把失敗計數歸零，下次萬一又斷線，重新從最短等待時間
                    # 開始退避，不會因為很久以前斷過一次就一直等很久。
                    fail_counts[name] = 0
                    continue
                if proc is not None:
                    n = fail_counts.get(name, 0)
                    wait_s = min(RESTART_BACKOFF_S * (RESTART_BACKOFF_MULT ** n),
                                RESTART_BACKOFF_MAX_S)
                    fail_counts[name] = n + 1
                    print(f"[{datetime.now():%H:%M:%S}] {name} 的 tunnel 斷了"
                         f"（exit code {proc.returncode}，連續第 {n + 1} 次），"
                         f"{wait_s:.0f} 秒後重開", flush=True)
                    time.sleep(wait_s)
                procs[name] = _spawn(name, w)
            # 設定檔裡拿掉的 worker，順便關掉對應的 tunnel 行程，不留孤兒。
            for name in list(procs):
                if name not in targets:
                    p = procs.pop(name)
                    if p.poll() is None:
                        p.terminate()
            time.sleep(CHECK_SECS)
    finally:
        for name, p in procs.items():
            if p.poll() is not None:
                continue    # 已經自己結束了
            print(f"結束前關閉 {name} 的 tunnel（PID {p.pid}）...", flush=True)
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(f"  {name} 的 tunnel 10 秒內沒回應 terminate，強制"
                     f"kill", flush=True)
                p.kill()


if __name__ == "__main__":
    main()
