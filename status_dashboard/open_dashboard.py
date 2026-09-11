# -*- coding: utf-8 -*-
"""桌面捷徑用的本機啟動器（2026-09-02 起，取代直接跑 `app.py`）。

**主控板本身已經搬到協調 VM 上常駐執行**（見
`docs/reference/CLOUD_WORKERS_IAP_SETUP.md`），本機不再自己起一份
`app.py`——本機跟協調 VM 各跑一份會變成兩個互相不知道對方存在的
「主控板」，資料各自為政（各自的 git 同步進度不同、各自看到不同的
未分類程式清單），違背「所有人連同一份、同時看到同一份派工狀態」的
整合目的。

這支腳本改成單純負責：確認本機 `localhost:8866`有沒有一條活著的
IAP tunnel 接到協調 VM，沒有就開一條，然後開瀏覽器。跟原本 `app.py`
的角色分工乾淨切開——這支不碰任何主控板邏輯，只管「怎麼連上去」。

**要更新主控板本身的程式碼**：協調 VM 上的 `app.py` 每次有人整理
頁面都會自動 `git pull`（見 `sync_repo_from_github()`），拉到新 commit
就自動重啟生效——PR 合併進 `main` 之後，下一次任何人重新整理頁面就會
套用新版，不需要手動登入協調 VM 操作。`cloud_queue.py`／
`iap_tunnel_manager.py` 沒有這套自動重啟（那兩支是常駐派工核心，
自己重啟自己風險比較高，故意沒做），改了要手動 SSH 進去
`git pull && sudo systemctl restart cloud-queue.service`。

**不需要單一實例鎖**（跟 `app.py` 的 `acquire_lock()` 不一樣）：
`gcloud compute start-iap-tunnel` 本身會真的綁定本機連接埠，兩個行程
搶同一個埠時，第二個會直接因為 socket bind 失敗而結束，不會像
`ThreadingHTTPServer`（預設 `allow_reuse_address=True`）那樣悄悄疊出
多個都活著的行程——雙擊兩次頂多是第二次的 tunnel 嘗試白做工、可能
多開一個瀏覽器分頁，不會真的疊出殘留行程。
"""
from __future__ import annotations

import http.client
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

# 桌面捷徑用 pyw（pythonw.exe）完全隱藏啟動，跟 app.py 同一個理由：
# pyw 底下 sys.stdout/stderr 是 None，print() 會直接炸掉整支腳本
# （這裡唯一會 print 的情況是 gcloud 找不到的錯誤訊息，但保險起見
# 統一導向 log 檔，不要讓這種邊界情況變成一個沒人看得到的靜默崩潰）。
if sys.stdout is None:
    _log_f = open(Path(__file__).resolve().parent / "open_dashboard.log", "a",
                 encoding="utf-8", buffering=1)
    sys.stdout = _log_f
    sys.stderr = _log_f

# 協調 VM 的連線資訊——跟 `ssh_workers.json` 裡某個 worker 的三項辨識
# （project/zone/instance）形式一樣，但這裡指的是「主控板本身所在的
# 那台機器」，跟任何一個 worker 是不同概念，故意不共用同一份設定檔。
PROJECT = "project-f6e2d0e1-cd17-4cfb-a9b"
ZONE = "us-central1-a"
INSTANCE = "instance-20260827-035250"
PORT = 8866


def _port_alive() -> bool:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=1.5)
        conn.request("HEAD", "/")
        conn.getresponse()
        return True
    except OSError:
        return False
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001, S110 — 連線物件都還沒建好時 close() 可能炸，忽略
            pass


def main() -> None:
    if _port_alive():
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return

    # Windows 上 gcloud 是 gcloud.cmd（批次檔），不是 gcloud.exe——
    # subprocess.Popen(["gcloud", ...]) 不加 shell=True 也不用
    # shutil.which() 解析的話，Windows 的 CreateProcess 不會自動試
    # PATHEXT 副檔名，會直接 FileNotFoundError（本機測試才踩到）。
    # shutil.which() 找到的是完整路徑，含正確副檔名，兩個平台都適用，
    # 不需要另外加 shell=True。
    gcloud = shutil.which("gcloud")
    if gcloud is None:
        print("找不到 gcloud，請先安裝 Google Cloud SDK：https://cloud.google.com/sdk/docs/install",
             flush=True)
        return
    subprocess.Popen(
        [gcloud, "compute", "start-iap-tunnel", INSTANCE, str(PORT),
         f"--local-host-port=localhost:{PORT}", f"--zone={ZONE}",
         f"--project={PROJECT}"],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    # 等 tunnel 真的連上再開瀏覽器，不要開一個連不到的空頁面——IAP
    # tunnel 首次建立通常幾秒內完成，20 秒是留給網路較慢或協調 VM
    # 剛好在忙的寬裕上限。
    for _ in range(20):
        time.sleep(1)
        if _port_alive():
            break

    webbrowser.open(f"http://127.0.0.1:{PORT}/")


if __name__ == "__main__":
    main()
