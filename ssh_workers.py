# -*- coding: utf-8 -*-
"""載入 SSH 遠端運算節點的登記檔（GCP／Oracle／任何有 SSH 的 Linux VM），
跟 kaggle_accounts.py 是同一種角色，給 ssh_sync.py / cloud_queue.py 用。

**跟 Kaggle 帳號的關鍵差異，決定了整套架構怎麼設計**：Kaggle 的 kernel
容器是一次性的（跑完就消失），所以每次都要重新打包上傳整個 pipeline／
資料／isochrone 網格。SSH worker 是**持久機器**——git clone／pip install
只要做一次，之後每次都只需要 `git pull` 同步程式碼，靜態資料（isochrones/、
data/ 底下那些不進版控的大檔）也只需要在第一次或有更新時才傳一次，
不必每個工作都重來。這個差異是 ssh_sync.py 的 ensure_repo()／
ensure_static_data() 只做「缺什麼補什麼」而不是整包重傳的原因。

**認證方式**：走一般 SSH 金鑰登入，不經手密碼。VM 上的 git clone
用**唯讀 Deploy Key**（在 GitHub repo 設定加 VM 自己產生的公鑰，
勾選不給 write 權限）——這台 VM 只需要讀取程式碼，不需要、也不應該
拿到能推送的憑證，把可寫入的 GitHub 權杖散布到更多機器上是不必要的
風險面擴大。結果檔一律由這台本機用 scp 拉回來、在本機決定要不要
commit，不讓 VM 自己碰 git push。完整設定步驟見
docs/reference/CLOUD_WORKERS.md。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKERS_FILE = HERE / "ssh_workers.json"
EXAMPLE_FILE = HERE / "ssh_workers.json.example"

# 全新的雲端 VM 第一次連線時，本機的 known_hosts 裡不會有它的主機金鑰。
# "accept-new" 只在完全沒有記錄時自動接受並記住，之後同一台主機再連線
# 若金鑰換了（可能代表遭到中間人攻擊或機器被重建）仍會照常擋下來要求
# 確認——比 StrictHostKeyChecking=no（永遠不驗證，形同關掉這層保護）
# 安全，又不需要使用者手動先跑一次互動式連線去按 yes。
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=15"]


def load_workers() -> dict[str, dict]:
    """回傳 {識別名: {"host":..., "user":..., "key_path":..., "port":...,
    "remote_dir":..., "procs":...}}。找不到登記檔時回傳空字典（不是
    錯誤——這個機制在只用 Kaggle、還沒設定任何 SSH worker 時本來就該
    是空的，讓 cloud_queue.py 自然跳過這個 backend）。"""
    if not WORKERS_FILE.exists():
        return {}
    data = json.loads(WORKERS_FILE.read_text(encoding="utf-8"))
    data.pop("_說明", None)
    out = {}
    for name, info in data.items():
        host = info.get("host", "")
        # 範本裡的佔位字串都是中文說明句，含空白；真正的 IP／網域不會。
        if not host or " " in host or "　" in host:
            print(f"警告：worker {name!r} 的 host 看起來還是範本佔位字串，略過")
            continue
        out[name] = {
            "host": host,
            "user": info.get("user", "ubuntu"),
            "key_path": info.get("key_path") or "",
            "port": int(info.get("port", 22)),
            "remote_dir": info.get("remote_dir", "~/m45_membership"),
            "procs": int(info.get("procs", 4)),
        }
    return out


def ssh_base(w: dict) -> list[str]:
    """組出這個 worker 的 ssh 前綴指令（不含要在遠端跑的指令本身），
    push()／run()／poll()／pull() 都在後面接自己的遠端指令字串。"""
    cmd = ["ssh"] + _SSH_OPTS + ["-p", str(w["port"])]
    if w["key_path"]:
        cmd += ["-i", str(Path(w["key_path"]).expanduser())]
    cmd.append(f"{w['user']}@{w['host']}")
    return cmd


def scp_base(w: dict) -> list[str]:
    cmd = ["scp"] + _SSH_OPTS + ["-P", str(w["port"])]
    if w["key_path"]:
        cmd += ["-i", str(Path(w["key_path"]).expanduser())]
    return cmd


def remote_run(w: dict, remote_cmd: str, timeout: int = 60
               ) -> subprocess.CompletedProcess:
    """在 worker 上跑一段 shell 指令並等它結束（同步、有逾時）。
    用來做狀態查詢、小型檔案操作——長時間運算不走這裡，見 ssh_sync.py
    的 run() 用 nohup + disown 讓遠端行程在 SSH 連線斷開後繼續跑。"""
    return subprocess.run(ssh_base(w) + [remote_cmd], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


if __name__ == "__main__":
    workers = load_workers()
    print(f"找到 {len(workers)} 個 SSH worker：")
    for name, w in workers.items():
        print(f"  {name:<12} {w['user']}@{w['host']}:{w['port']}  "
              f"procs={w['procs']}  remote_dir={w['remote_dir']}")
