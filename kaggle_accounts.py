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
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACCOUNTS_FILE = HERE / "kaggle_accounts.json"
EXAMPLE_FILE = HERE / "kaggle_accounts.json.example"


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
    return env


if __name__ == "__main__":
    accounts = load_accounts()
    print(f"找到 {len(accounts)} 個帳號：")
    for name, info in accounts.items():
        masked = info["token"][:8] + "..." if len(info["token"]) > 8 else "***"
        print(f"  {name:<12} username={info['username']:<20} token={masked}")
