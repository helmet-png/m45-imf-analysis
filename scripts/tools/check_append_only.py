# -*- coding: utf-8 -*-
"""CI 用：驗證附加型清單檔（見 .gitattributes 的 merge=union 那兩個）
沒有既有行被改掉或刪掉，只允許新增。

**為什麼需要這個**（2026-08-21 CodeRabbit review）：`.gitattributes` 的
`merge=union` 解決的是「兩邊都在檔尾附加一行」不會產生衝突，但它**不驗證**
契約本身——兩個分支若剛好改到同一筆既有紀錄（不是附加，是修改），union
會把兩個版本都留下、不報衝突，讀者看到兩筆內容矛盾的紀錄卻不知道哪個才對。
這支腳本在 CI 補上這層驗證：PR 分支相對於 base 分支，這兩個檔案的既有行
必須全部還在（可以增加新行，不能刪除或修改舊行）。

**判定方式，故意選最寬鬆的**：只比對「非空白行的集合」（忽略順序），不比
逐行比對位置。理由：`merge=union` 本身就可能改變行的相對順序（兩邊各自
新增的行怎麼交錯，取決於 git 的合併演算法，不保證跟原檔案順序一致），若
用「逐行完全一致的前綴」這種嚴格判定，會把 union 合併本身造成的正常重排
也判成違規，變成擋自己人。用集合比對雖然抓不到「刪一行、加一行內容剛好
不同」這種邊緣案例，但這是 append-only 契約要防的主要情境（整段改寫、
整段刪除）已經足夠，且不會產生假警報。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]

# 跟 .gitattributes 的 merge=union 清單保持同步——這兩份名單分開維護是
# 刻意的：.gitattributes 管「怎麼合併」，這裡管「合併後怎麼驗證」，兩者
# 職責不同，但涵蓋的檔案必須是同一組，否則會有檔案「用 union 合併卻沒被
# 驗證」或「被驗證但沒有用 union」的落差。
APPEND_ONLY_FILES = [
    "results/RESULTS_LOG.md",
    "WORK_BOARD.md",
]


def _file_at_ref(ref: str, rel_path: str) -> str | None:
    """讀某個 git ref 底下的檔案內容；該 ref 沒有這個檔案就回傳 None
    （例如檔案是這個 PR 才新增的，沒有「既有行」可比對，直接放行）。"""
    r = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=HERE, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        return None
    return r.stdout


def check(base_ref: str) -> int:
    fails: list[str] = []
    for rel in APPEND_ONLY_FILES:
        base_text = _file_at_ref(base_ref, rel)
        if base_text is None:
            print(f"  {rel}：{base_ref} 上沒有這個檔案，跳過（視為這個 PR 新增）")
            continue
        cur_path = HERE / rel
        if not cur_path.is_file():
            fails.append(f"{rel}：{base_ref} 上有這個檔案，但這個分支把它刪掉了")
            continue
        cur_text = cur_path.read_text(encoding="utf-8", errors="replace")
        base_lines = {l for l in base_text.splitlines() if l.strip()}
        cur_lines = {l for l in cur_text.splitlines() if l.strip()}
        missing = base_lines - cur_lines
        if missing:
            fails.append(
                f"{rel}：{len(missing)} 行在 {base_ref} 存在，這個分支卻沒有"
                f"——append-only 檔案只能新增，不能修改或刪除既有行")
            for m in sorted(missing)[:5]:
                print(f"    消失/被改掉的行：{m[:150]}")
            if len(missing) > 5:
                print(f"    ...還有 {len(missing) - 5} 行")
        else:
            print(f"  {rel}：OK（{len(base_lines)} 行全部還在）")
    if fails:
        print("\n結論：不通過")
        for f in fails:
            print(f"  阻擋：{f}")
        return 1
    print("\n結論：通過")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：python check_append_only.py <base_ref>\n"
              "  例如：python check_append_only.py origin/main", file=sys.stderr)
        return 2
    return check(sys.argv[1])


if __name__ == "__main__":
    sys.exit(main())
