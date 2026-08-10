# -*- coding: utf-8 -*-
"""把本專案的計算工作推到 Kaggle，跟本機的佇列平行跑、加快進度。

**架構**：Kaggle notebook 沒有「常駐背景佇列」這種東西——上傳一次、跑到完成
或逾時（GPU/CPU 額度通常單次上限約 9-12 小時）、下載結果、結束。
所以走法是：把要跑的那支腳本連同它需要的資料，打包成一個 Kaggle Dataset，
建一個對應的 Kernel（notebook）去跑它，跑完把 output 抓回本機。

**已知限制**（先講清楚，避免誤用）：
  - **實測腳本會被執行兩次**（2026-08-09 smoke test 觀察到，原因未查）。
    若腳本本身是確定性的（固定亂數種子、輸出用 np.savez 覆寫），重跑一次
    無害只是多花時間；若腳本有非冪等的副作用（附加寫檔、呼叫外部 API 會計費），
    先確認能承受跑兩次再推上去。
  - Kaggle 環境是 x64（無 ARM64 選項），跑起來比本機慢，不是為了單次算得快，
    是為了**跟本機同時跑另一批**，總時程縮短。
  - 每次同步都要重新上傳資料（isochrones/ 網格檔可能到數百 MB），
    網路慢的話上傳本身就要一段時間，不適合拿去跑「秒級」的小工作。
  - 無法像本機一樣中途追加任務（run_queue.py 那種可插隊的機制在 Kaggle
    上不成立，一個 kernel 對應一次固定的執行內容）。

**CPU 數**：Kaggle 的免費 CPU-only notebook 通常只給 4 顆虛擬核心
（比本機的 8 顆少），所以 `--args` 裡的 `--procs` 建議傳 4，不要照抄本機的 8。

**多帳號（2026-08-09 新增）**：`--account <名稱>` 對應 `kaggle_accounts.json`
裡的一個帳號，用它的 token 認證，不必自己管 KAGGLE_USERNAME/KAGGLE_KEY。
不同帳號可以同時各自 push/poll，因為每次呼叫都用獨立的工作目錄
（`--work-dir`，預設用帳號名稱自動分開）與獨立的環境變數，互不干擾。

**用法**：
    python kaggle_sync.py push --script profile_lowmass.py --args "--procs 4 --repeats 5" --account helmetalbert
    python kaggle_sync.py status --kernel <帳號>/m45-imf-run-<腳本名> --account helmetalbert
    python kaggle_sync.py pull --kernel <帳號>/m45-imf-run-<腳本名> --account helmetalbert

**必要條件**：`kaggle_accounts.json`（見 `kaggle_accounts.json.example`），
或單人使用時退回讀 `~/.kaggle/access_token`（`kaggle_accounts.py` 處理）。

**只有 kaggle.json（帳號+key）不夠**（2026-08-09 實測驗證，不是道聽塗說）：
上傳操作（`datasets create`／`kernels push`）一定要 token，CLI 自己的錯誤
訊息也是這樣講。所以每個帳號只登記一個 token，不需要 username+key 那一套。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import kaggle_accounts

HERE = Path(__file__).resolve().parent

# 這些是跑計算腳本需要、但不必每次都重新展開的靜態資料。
# isochrones/ 只挑目前實際用到的那幾個網格檔，不要整個資料夾都上傳
# （PARSEC 原始網格加 MIST 打包檔加起來超過 800 MB，Kaggle Dataset
# 沒必要背這個重量，且大部分格點用不到）。
NEEDED_ISOCHRONE_GLOBS = [
    "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat",
    "mist_v1.2_gaiaDR2_logt7.8-8.5_feh-0.5-0.5.dat",
    # 2026-08-10：P9c 用的新版 MIST 網格（涵蓋 7.30-8.50，取代舊版
    # 7.80-8.50 造成的簡併平坦區問題）。差點忘記加進這張白名單——
    # 加了新網格檔卻沒加進這裡，Kaggle 上會悄悄打包到舊版、重蹈覆轍
    # 卻不會報錯，是同一種「檔案清單沒跟著更新」的坑（config.toml
    # 那次已經踩過一次）。
    "mist_v1.2_gaiaDR2_logt7.3-8.5_feh-0.5-0.5.dat",
]
NEEDED_DATA_FILES = [
    "cmd_members.csv", "errmodel.npz", "selection.npz",
]


def resolve_account(name: str | None) -> tuple[str, dict, dict]:
    """回傳 (實際解析到的帳號名稱, 帳號資訊, 給 subprocess 用的環境變數字典)。

    name 為 None 時取登記檔裡的第一個帳號（單人使用的預設行為）——
    回傳實際名稱是為了讓呼叫端能在訊息裡準確講「用的是哪個帳號」，
    不必自己重複一次「None 時取第一個」的邏輯。
    """
    accounts = kaggle_accounts.load_accounts()
    if name is None:
        name = next(iter(accounts))
    if name not in accounts:
        print(f"找不到帳號 {name!r}，登記檔裡有：{list(accounts)}")
        sys.exit(1)
    acc = accounts[name]
    return name, acc, kaggle_accounts.env_for(acc)


def run(cmd, **kw):
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def build_payload(script: str, extra_files: list[str], work_dir: Path,
                  minimal: bool = False):
    """組出要上傳的檔案集合。只帶跑得動這支腳本需要的最小集合。

    minimal=True 跳過 pipeline/、data/、isochrones/ —— 給不依賴這些的輕量腳本
    （例如連線測試、純 numpy 的小工作）用，避免每次驗證都上傳上百 MB。

    **work_dir 必須是呼叫端專屬的資料夾**（2026-08-09 多帳號並行時新增
    這個參數）：原本固定用同一個 kaggle_work/，多個帳號同時 push 會搶著
    寫同一批檔案，內容互相覆蓋。改成每次呼叫傳入不同路徑
    （kaggle_queue.py 用帳號名稱區分），彼此才不會互相干擾。
    """
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    shutil.copy(HERE / script, work_dir / script)
    for f in extra_files:
        src = HERE / f
        if src.exists():
            shutil.copy(src, work_dir / Path(f).name)
        else:
            print(f"  警告：找不到 {src}，略過（若這支腳本不需要它可忽略）")

    if not minimal:
        # 整個 pipeline/ 套件
        shutil.copytree(HERE / "pipeline", work_dir / "pipeline")
        # config.toml 在專案根目錄、不在 data/ 底下，所以不會被下面那圈
        # NEEDED_DATA_FILES 帶到。漏掉它的症狀是 pipeline/config.py 的
        # load() 拋錯，而且 Kaggle log 的中文亂碼會讓錯誤訊息看不出原因
        # （2026-08-09 實測踩到，浪費一次 push-run-pull 循環）。
        shutil.copy(HERE / "config.toml", work_dir / "config.toml")
        (work_dir / "data").mkdir()
        for f in NEEDED_DATA_FILES:
            src = HERE / "data" / f
            if src.exists():
                shutil.copy(src, work_dir / "data" / f)
        (work_dir / "isochrones").mkdir()
        for pat in NEEDED_ISOCHRONE_GLOBS:
            src = HERE / "isochrones" / pat
            if src.exists():
                shutil.copy(src, work_dir / "isochrones" / pat)
            else:
                print(f"  警告：找不到 isochrone 網格 {pat}")

    size_mb = sum(f.stat().st_size for f in work_dir.rglob("*") if f.is_file())
    size_mb /= 1024 * 1024
    print(f"打包完成：{work_dir}（{size_mb:.1f} MB）")
    return size_mb


def make_dataset_metadata(slug: str, username: str, work_dir: Path):
    meta = {
        "title": f"m45-imf-{slug}",
        "id": f"{username}/m45-imf-{slug}",
        "licenses": [{"name": "CC0-1.0"}],
    }
    (work_dir / "dataset-metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")
    return meta["id"]


def make_kernel(script: str, args: str, dataset_id: str, username: str,
                slug: str, extra_files: list[str], work_dir: Path,
                minimal: bool = False):
    """建一個對應的 notebook：安裝依賴、掛上資料、跑腳本、印出結果。"""
    base = "/kaggle/input/m45-imf-" + slug + "/"
    # **2026-08-10 根本修法：掛載時序問題不該靠外部重推整個 kernel 版本解決，
    # 該讓 kernel 自己在真正開始跑之前先等資料掛好。**
    # 先前的作法是 kaggle_queue.py 偵測到 FileNotFoundError 後，重新
    # push 一個新的 kernel 版本重跑——但實測發現連 push 第 5 次（距離
    # dataset 建立已經過了快 16 分鐘）都還是在 kernel 執行的頭幾秒內就
    # FileNotFoundError，代表這個延遲不是「累積等待時間」能解決的，是
    # 每次 kernel container 重新啟動時，掛載本身要花一小段時間才會就緒，
    # 跟 dataset 建立多久無關。與其每次都重新起一整個 container（貴、慢、
    # 而且賭運氣），不如讓同一個正在跑的 container 自己原地等——真正的
    # 掛載延遲很可能只有幾十秒等級，用短間隔輪詢比整批重推便宜太多。
    # 外部的重推機制（kaggle_queue.py 的 BACKOFFS）保留當最後防線，
    # 但這裡先讓大多數情況根本不必走到那一步。
    # 這裡故意全部印英文（不是隨便，是 2026-08-09 已經查證過的教訓：
    # Kaggle 的 log 擷取管線會把中文轉成亂碼，跟我們子行程的編碼設定
    # 無關，不受控制範圍。這段訊息真的印出來時代表逾時失敗，需要能被
    # 讀懂，所以延續「跑在 Kaggle 上一律印英文」的既有規則）。
    wait_lines = [
        "import time\n",
        "def _wait_input(path, timeout=280, interval=5):\n",
        "    t0 = time.time()\n",
        "    while not os.path.exists(path):\n",
        "        if time.time() - t0 > timeout:\n",
        "            raise FileNotFoundError(\n",
        "                f'waited {timeout}s, Kaggle has not mounted dataset at "
        "{path} yet (platform-side mount delay, not a script bug)')\n",
        "        time.sleep(interval)\n",
        f"_wait_input('{base}{'pipeline' if not minimal else script}')\n",
    ]
    copy_lines = [f"shutil.copy('{base}{script}', '{script}')\n"]
    for f in extra_files:
        name = Path(f).name
        copy_lines.append(f"shutil.copy('{base}{name}', '{name}')\n")
    if not minimal:
        # 這裡的每一項都必須跟 build_payload() 打包的內容一一對應 ——
        # 只打包不複製（或反過來）就會在 Kaggle 上才炸掉，而且中文亂碼
        # 讓錯誤訊息難讀。config.toml 就是這樣漏掉一次的（2026-08-09）。
        copy_lines = [
            f"shutil.copytree('{base}pipeline', 'pipeline', "
            "dirs_exist_ok=True)\n",
            f"shutil.copytree('{base}data', 'data', dirs_exist_ok=True)\n",
            f"shutil.copytree('{base}isochrones', 'isochrones', "
            "dirs_exist_ok=True)\n",
            f"shutil.copy('{base}config.toml', 'config.toml')\n",
        ] + copy_lines
    # **只有真的要跑 MCMC 的腳本才需要 emcee，而且不能讓它裝失敗就整批掛掉。**
    # 實測（2026-08-09）：Kaggle 帳號未完成手機驗證時 notebook 沒有對外網路，
    # `pip install emcee` 會重試五次後失敗，check=True 讓整個 kernel ERROR ——
    # 但 profile_lowmass.py 用的是網格搜尋、根本不需要 emcee，等於為了一個
    # 用不到的套件白白丟掉四分鐘的計算。
    # 改成：只有腳本原始碼真的 import emcee 時才嘗試安裝，且失敗不中斷
    # （若真的需要它，後面會在 import 時給出明確的錯誤，比裝不起來的
    # pip log 好讀得多）。
    need_emcee = "emcee" in (HERE / script).read_text(
        encoding="utf-8", errors="ignore")
    pip_line = ("subprocess.run([sys.executable, '-m', 'pip', 'install', "
                "'-q', 'emcee'], check=False)\n") if need_emcee else ""
    # **中文輸出的編碼修正**：實測 Kaggle 的 Linux 環境預設沒把子行程的
    # stdout 設成 UTF-8，我們所有進度訊息都是中文，不修的話回傳的 log
    # 全部是亂碼（已在 kaggle_smoketest.py 的第一次真實測試中發生）。
    # 用 env 傳 PYTHONIOENCODING，而不是在被跑的腳本裡加
    # sys.stdout.reconfigure —— 這樣任何腳本都不必為了在 Kaggle 上跑
    # 而修改自己，編碼修正留在這支同步工具裡。
    # 實測過兩種修法都沒用（2026-08-09）：PYTHONIOENCODING=utf-8 和
    # LC_ALL/LANG=C.UTF-8，回傳的 log 亂碼模式完全相同（Unicode 替代字元）。
    # 代表問題出在 Kaggle 平台自己的 log 擷取層（notebook -> log JSON 那段
    # 轉檔管線），不是我們子行程的編碼設定能控制的範圍。
    # **唯一確認有效的解法：跑在 Kaggle 上的腳本，進度訊息一律印英文。**
    # ASCII 每字元 1 byte，不會觸發那段有問題的多位元組解碼。
    # 這不是隨便迴避——是先查出問題確實在我們控制範圍外，才選擇繞過它。
    # 真正的計算結果不受影響：np.savez 存的是二進位陣列，跟主控台文字編碼
    # 無關，pull 回來的 .npz 檔案數字永遠是對的，只有「印出來的敘述文字」
    # 在 log 裡會不會亂碼的差別。
    env_line = ("env = dict(os.environ, PYTHONIOENCODING='utf-8')\n")
    nb = {
        "cells": [{
            "cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [],
            "source": (
                ["import subprocess, sys, shutil, os\n"] + wait_lines
                + copy_lines
                + ([pip_line] if pip_line else [])
                + [env_line,
                   f"subprocess.run([sys.executable, '-u', '{script}'] + "
                   f"'{args}'.split(), check=True, env=env)\n"]
            ),
        }],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                          "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4, "nbformat_minor": 5,
    }
    (work_dir / f"{slug}.ipynb").write_text(json.dumps(nb), encoding="utf-8")
    kmeta = {
        "id": f"{username}/m45-imf-run-{slug}",
        "title": f"m45-imf-run-{slug}",
        "code_file": f"{slug}.ipynb",
        "language": "python", "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False, "enable_tpu": False, "enable_internet": True,
        "dataset_sources": [dataset_id],
        "competition_sources": [], "kernel_sources": [],
    }
    (work_dir / "kernel-metadata.json").write_text(
        json.dumps(kmeta, indent=2), encoding="utf-8")
    return kmeta["id"]


def wait_dataset_ready(dataset_id: str, env: dict, timeout_s: int = 180,
                       interval_s: int = 15, confirm_s: int = 30):
    """等 dataset 從「正在處理」變成 ready 才能推 kernel。

    **第一版只等單次 ready 就不夠**（2026-08-09 排隊自動化時實測踩到）：
    `kaggle datasets status` 回報 ready 之後**立刻**推 kernel，kernel 執行時
    仍拿到 `FileNotFoundError`，因為 status 的 ready 是 metadata 層級的信號，
    dataset 實際被掛載到 `/kaggle/input/` 供 kernel 讀取還有額外的最終一致性
    延遲（狀態說「好了」，檔案還沒真的鋪好）。第一次手動 push（profile-lowmass）
    之所以沒踩到，是因為中間人工檢查花掉的時間**意外**蓋過了這段延遲。

    **這只是第一道防線，不是唯一防線**：實測連等 138 秒、事後手動再等數分鐘
    都還是失敗過，代表這段延遲本身不穩定，猜不出一個穩妥的等待時長。
    真正兜底的是 `kaggle_queue.py` 的重試機制——偵測到這個特定的
    FileNotFoundError 就自動重推 kernel，而不是在這裡死等。
    這裡只求擋掉大多數「太快」的情況，減少重試次數。
    """
    t0 = time.time()
    first_ready_at = None
    while time.time() - t0 < timeout_s:
        r = subprocess.run(["kaggle", "datasets", "status", dataset_id],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        status = (r.stdout + r.stderr).strip()
        is_ready = "ready" in status.lower()
        if is_ready:
            if first_ready_at is None:
                first_ready_at = time.time()
            elif time.time() - first_ready_at >= confirm_s:
                print(f"  dataset 就緒且已確認穩定"
                      f"（共等了 {time.time()-t0:.0f}s）", flush=True)
                return True
        else:
            first_ready_at = None      # 中途變回非 ready，重新累計
        time.sleep(interval_s)
    print(f"  警告：等了 {timeout_s}s dataset 仍未穩定就緒，繼續推 kernel "
          "但可能會失敗（可用 status 手動確認後重推）")
    return False


def cmd_push(a):
    account_name, acc, env = resolve_account(a.account)
    username = acc["username"]
    slug = a.slug or Path(a.script).stem.replace("_", "-")
    # work_dir 預設用帳號名稱區分（不是固定的 kaggle_work/）——
    # 這樣不同帳號同時 push 才不會搶著寫同一批檔案。
    work_dir = Path(a.work_dir) if a.work_dir else \
        HERE / "kaggle_work" / account_name
    extra_files = a.extra.split(",") if a.extra else []
    build_payload(a.script, extra_files, work_dir, minimal=a.minimal)

    dataset_id = make_dataset_metadata(slug, username, work_dir)
    # 先建/更新 dataset
    exists = subprocess.run(
        ["kaggle", "datasets", "status", dataset_id],
        capture_output=True, text=True, env=env)
    if exists.returncode == 0:
        run(["kaggle", "datasets", "version", "-p", str(work_dir),
             "-m", "update", "-r", "zip"], env=env)
    else:
        run(["kaggle", "datasets", "create", "-p", str(work_dir),
             "-r", "zip"], env=env)
    wait_dataset_ready(dataset_id, env)

    kernel_id = make_kernel(a.script, a.args, dataset_id, username, slug,
                            extra_files, work_dir, minimal=a.minimal)
    run(["kaggle", "kernels", "push", "-p", str(work_dir)], env=env)
    print(f"\nKERNEL_ID={kernel_id}", flush=True)
    print(f"追蹤：https://www.kaggle.com/code/{kernel_id.split('/')[-1]}")
    print(f"查狀態：python kaggle_sync.py status --kernel {kernel_id} "
          f"--account {account_name}")


def cmd_status(a):
    _, _, env = resolve_account(a.account)
    run(["kaggle", "kernels", "status", a.kernel], env=env)


def cmd_pull(a):
    _, _, env = resolve_account(a.account)
    out = HERE / "kaggle_results" / Path(a.kernel).name
    out.mkdir(parents=True, exist_ok=True)
    run(["kaggle", "kernels", "output", a.kernel, "-p", str(out)], env=env)
    print(f"結果存到 {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("push", help="打包並推送一支腳本到 Kaggle 執行")
    p1.add_argument("--script", required=True)
    p1.add_argument("--args", default="")
    p1.add_argument("--extra", default="",
                    help="逗號分隔，這支腳本 import 的其他同層 .py 檔")
    p1.add_argument("--account", default=None,
                    help="kaggle_accounts.json 裡的帳號名稱，"
                         "省略則用登記檔裡的第一個帳號")
    p1.add_argument("--work-dir", default=None,
                    help="打包用的暫存資料夾，省略則用 "
                         "kaggle_work/<帳號名稱>（多帳號並行靠這個互不干擾）")
    p1.add_argument("--minimal", action="store_true",
                    help="不帶 pipeline/data/isochrones，給輕量腳本用")
    p1.add_argument("--slug", default="",
                    help="dataset/kernel 的識別名，預設用腳本檔名推出。"
                         "同一支腳本要用不同參數跑多份時務必指定不同 slug，"
                         "否則會共用同一個 dataset/kernel、後者蓋掉前者")
    p1.set_defaults(func=cmd_push)

    p2 = sub.add_parser("status")
    p2.add_argument("--kernel", required=True)
    p2.add_argument("--account", default=None)
    p2.set_defaults(func=cmd_status)

    p3 = sub.add_parser("pull")
    p3.add_argument("--kernel", required=True)
    p3.add_argument("--account", default=None)
    p3.set_defaults(func=cmd_pull)

    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
