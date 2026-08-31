# -*- coding: utf-8 -*-
"""載入多帳號憑證登記檔，讓 kaggle_sync.py / kaggle_queue.py 可以用不同帳號
分別認證，藉此在 Kaggle 上同時跑多份工作（每個帳號各自的 CPU 額度互不相干）。

**認證方式的選擇（2026-08-09 實測驗證，不是照抄文件）**：只有 kaggle.json
（帳號 + legacy key）**不足以做上傳**（`datasets create`／`kernels push`）。
實測把現有的 access_token 移開、只留 kaggle.json，上傳直接被拒絕，
CLI 自己印出的訊息就是「請用 KAGGLE_API_TOKEN 環境變數或
~/.kaggle/access_token」。所以每個帳號只需要登記**一個 token**：
在 kaggle.com/settings/api 按 Generate New Token 直接複製，
不需要下載 kaggle.json、也不需要跑 `kaggle auth login` 的瀏覽器流程 ——
token 本身就能驗證身分（伺服器端 introspection 會反查出 username），
我們額外要求填 username 純粹是為了組出 dataset/kernel 的 ID
（`helmetalbert/m45-imf-run-xxx` 這種格式），不是 Kaggle 認證需要它。

**環境變數注入**：只需要設 `KAGGLE_API_TOKEN`。這是 kaggle 套件官方支援的
環境變數（`kagglesdk.kaggle_env.get_access_token_from_env` 第一優先檢查
的來源），不需要碰任何檔案，每次 subprocess 呼叫各自帶一份環境變數字典，
就能讓同一台機器同時以不同帳號跟 Kaggle API 對話。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCOUNTS_FILE = HERE / "kaggle_accounts.json"
EXAMPLE_FILE = HERE / "kaggle_accounts.json.example"

# kaggle CLI 只裝在 ARM64 版 Python 底下（這台機器是 Snapdragon X，`py`
# 預設常解析到 x64 模擬版）。**這裡必須直接改當前行程的 os.environ**，
# 不能只在傳給 subprocess 的 env 字典裡加 PATH——2026-08-10 實測發現
# Windows 的 subprocess.run(["kaggle", ...], env=...) 找執行檔用的是
# 呼叫端行程（也就是這支腳本自己）當下的 PATH，不是要傳給子行程的 env
# 參數；env 字典裡的 PATH 只決定子行程「自己」看到的環境，不影響
# CreateProcess 怎麼找 kaggle.exe 本身。改這裡一次，kaggle_sync.py／
# kaggle_queue.py 裡所有 subprocess.run(["kaggle", ...]) 都會受益。
_ARM64_SCRIPTS = (Path.home() / "AppData" / "Local" / "Python" /
                  "pythoncore-3.14-arm64" / "Scripts")
if _ARM64_SCRIPTS.exists() and str(_ARM64_SCRIPTS) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_ARM64_SCRIPTS}{os.pathsep}{os.environ.get('PATH', '')}"


# 呼叫 Kaggle CLI 的指令前綴。**不要寫死成 ["kaggle", ...]**
# （2026-08-26，這個坑實際擋掉了整批派工）：
#
# Windows 的 Smart App Control（智慧型應用程式控制）開啟時，會擋掉
# 「沒有數位簽章、或簽章知名度不足」的執行檔。`kaggle.exe` 是 pip 安裝時
# 自動產生的 wrapper，正好屬於這一類，於是 `subprocess.run(["kaggle", ...])`
# 直接噴 `OSError: [WinError 4551] 應用程式控制原則已封鎖此檔案`。
#
# **症狀很容易誤判成別的問題**：派工器推得出去工作，但每次查狀態就拋
# 例外、保留槽位、下一輪重試，於是所有 Kaggle 帳號看起來都「卡在檢查
# 中」、永遠不會完成，log 裡只有一長串看起來跟 Kaggle 無關的
# CreateProcess traceback。2026-08-26 PR #136／#139 合併後，9 個 Kaggle
# 工作全部卡在這裡。
#
# 解法是改用 `python -m kaggle`：跑的是 python.exe（本來就在允許清單裡，
# 否則這支程式自己也起不來），Kaggle 套件本身是純 Python 模組、不受執行檔
# 簽章政策管轄。功能與參數跟 kaggle.exe 完全相同——kaggle.exe 本來就只是
# 這個模組的一層薄殼。
#
# **刻意不要求使用者關掉 Smart App Control**：它一旦關閉，就無法在不重灌
# Windows 的情況下重新開啟。為了一支工具犧牲整台機器的執行檔防護不划算，
# 而且換一台機器（例如隊友的）一樣會再踩到，改程式才是一勞永逸的修法。
#
# 用 `sys.executable` 而不是字面的 "python"：確保用的是「現在正在跑這支
# 程式的那個 Python」。這跟上面 ARM64 PATH 那段處理的是同一類問題——
# 這台機器上同時存在好幾個 Python 版本，裝了 kaggle 套件的不一定是 PATH
# 上排最前面的那一個。
KAGGLE_CMD = [sys.executable, "-m", "kaggle"]


def load_accounts() -> dict[str, dict[str, str]]:
    """回傳 {識別名: {"username":..., "token":...}}。

    找不到 kaggle_accounts.json 時，退回單一預設帳號 ——
    向後相容單人使用時的舊流程（讀 ~/.kaggle/access_token）。
    """
    if not ACCOUNTS_FILE.exists():
        token_path = Path.home() / ".kaggle" / "access_token"
        if not token_path.exists():
            raise FileNotFoundError(
                f"找不到 {ACCOUNTS_FILE}，也找不到 {token_path}。\n"
                f"單人使用：先跑過一次 kaggle 登入設定既有的 access_token。\n"
                f"多人使用：複製 {EXAMPLE_FILE.name} 改名成 "
                f"{ACCOUNTS_FILE.name}，每個帳號去 kaggle.com/settings/api "
                f"按 Generate New Token 貼進去。")
        # 舊流程沒有登記 username，用 kaggle.json 裡的（若存在）或留空 ——
        # 留空只會影響組 ID 時的顯示，實際認證只看 token。
        username = ""
        kj = Path.home() / ".kaggle" / "kaggle.json"
        if kj.exists():
            try:
                username = json.loads(kj.read_text(encoding="utf-8")).get(
                    "username", "")
            except (json.JSONDecodeError, OSError):
                pass
        return {"default": {"username": username,
                            "token": token_path.read_text(encoding="utf-8").strip()}}

    data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    data.pop("_說明", None)
    accounts = {}
    for name, info in data.items():
        token = info.get("token", "")
        # 真 token（KGAT_ 開頭的十六進位字串）不含空白；範本裡的佔位字串
        # 都是中文說明句，一定含空白，用這個分辨比找特定關鍵字穩健。
        if not token or " " in token or "　" in token:
            print(f"警告：帳號 {name!r} 的 token 看起來還是範本佔位字串，略過")
            continue
        accounts[name] = {"username": info.get("username", name),
                          "token": token}
    if not accounts:
        raise ValueError(
            f"{ACCOUNTS_FILE} 裡沒有任何看起來像真 token 的帳號，"
            f"檢查是否忘記把範例文字換成真的 token")
    return accounts


def env_for(account: dict[str, str]) -> dict[str, str]:
    """回傳帶有該帳號 token 的環境變數字典，供 subprocess 呼叫使用。"""
    env = dict(os.environ)
    env["KAGGLE_API_TOKEN"] = account["token"]
    # 避免其他帳號殘留的環境變數／檔案型憑證干擾 ——
    # KAGGLE_API_TOKEN 的優先權最高，但清乾淨比較保險。
    env.pop("KAGGLE_USERNAME", None)
    env.pop("KAGGLE_KEY", None)
    # kaggle CLI 只裝在 ARM64 版 Python 底下（這台機器是 Snapdragon X，
    # `py` 預設可能解析到 x64 模擬版），呼叫端的 PATH 不一定含這個
    # Scripts 目錄——尤其是用 Start-Process 這種脫離互動 shell 的方式
    # 啟動時（2026-08-10 實測：detached 背景執行時 subprocess.run(["kaggle",
    # ...]) 直接 FileNotFoundError，兩個帳號的 push 都還沒上傳就失敗）。
    # 這裡把它的 Scripts 目錄補進 PATH，不依賴呼叫端當下的 shell 環境。
    arm64_scripts = (Path.home() / "AppData" / "Local" / "Python" /
                     "pythoncore-3.14-arm64" / "Scripts")
    if arm64_scripts.exists():
        env["PATH"] = f"{arm64_scripts}{os.pathsep}{env.get('PATH', '')}"
    return env


if __name__ == "__main__":
    accounts = load_accounts()
    print(f"找到 {len(accounts)} 個帳號：")
    for name, info in accounts.items():
        masked = info["token"][:8] + "..." if len(info["token"]) > 8 else "***"
        print(f"  {name:<12} username={info['username']:<20} token={masked}")
