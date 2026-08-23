# -*- coding: utf-8 -*-
"""CI 用：驗證附加型清單檔（見 .gitattributes 的 merge=union 那兩個）
沒有既有行被改掉或刪掉，只允許新增。

**為什麼需要這個**（2026-08-21 CodeRabbit review）：`.gitattributes` 的
`merge=union` 解決的是「兩邊都在檔尾附加一行」不會產生衝突，但它**不驗證**
契約本身——兩個分支若剛好改到同一筆既有紀錄（不是附加，是修改），union
會把兩個版本都留下、不報衝突，讀者看到兩筆內容矛盾的紀錄卻不知道哪個才對。
這支腳本在 CI 補上這層驗證：PR 分支相對於 base 分支，這兩個檔案的既有行
必須全部還在（可以增加新行，不能刪除或修改舊行）。

**判定方式，故意選最寬鬆的**：只比對「非空白行的多重集合」（忽略順序），
不逐行比對位置。理由：`merge=union` 本身就可能改變行的相對順序（兩邊各自
新增的行怎麼交錯，取決於 git 的合併演算法，不保證跟原檔案順序一致），若
用「逐行完全一致的前綴」這種嚴格判定，會把 union 合併本身造成的正常重排
也判成違規，變成擋自己人。

**用 `Counter`（多重集合）而不是純 `set`**（2026-08-21 CodeRabbit
review）：純集合比對有個真的會漏抓的洞——base 若有兩行內容完全相同，
PR 刪掉其中一行，`set(base) - set(cur)` 算出來還是空的（因為那個內容
在 `cur` 裡仍出現一次），append-only 契約明明被違反卻放行。`Counter`
會記住每個內容出現的次數，`base_counts - cur_counts` 對「次數變少」的
內容才會顯示正數，逐行內容不同的極端案例仍然抓不到（那不是這支腳本
要解決的），但「行的出現次數變少」這個更貼近契約本身的情況會被抓到。
"""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]

# 跟 .gitattributes 的 merge=union 清單保持同步——這兩份名單分開維護是
# 刻意的：.gitattributes 管「怎麼合併」，這裡管「合併後怎麼驗證」，兩者
# 職責不同，但涵蓋的檔案必須是同一組，否則會有檔案「用 union 合併卻沒被
# 驗證」或「被驗證但沒有用 union」的落差。
#
# **每個 group 是「必須合起來看的一組檔案」**（2026-08-23 CodeRabbit
# review）：`WORK_BOARD.md` 依 `CONTRIBUTING.md` 零之四規則，任務完成後
# 允許把那一行**搬**到 `WORK_BOARD_DONE.md`——單獨看 `WORK_BOARD.md`
# 這是「刪除既有行」，會被逐檔案比對的舊版邏輯誤判成違規；但那一行的
# 完整內容其實原封不動出現在 `WORK_BOARD_DONE.md` 裡，沒有真的遺失或
# 被改掉，只是換了檔案。改成把同一組的檔案內容合起來看 append-only：
# 「合併後的多重集合」不能少任何一行，行可以在組內的檔案之間搬動，
# 但內容不能真的消失或被改掉。`results/RESULTS_LOG.md` 沒有這種「搬去
# 別的檔案」的機制，維持單檔案一組。
APPEND_ONLY_GROUPS: list[list[str]] = [
    ["results/RESULTS_LOG.md"],
    ["WORK_BOARD.md", "WORK_BOARD_DONE.md"],
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
    for group in APPEND_ONLY_GROUPS:
        label = " + ".join(group)
        # Counter（多重集合）不是 set：base 裡兩行內容相同、PR 刪掉一行時，
        # 純 set 比對會算成沒有變化（那個內容在 cur 裡仍出現一次），
        # Counter 才抓得到「出現次數變少」（見上方 docstring 說明）。
        base_counts: Counter[str] = Counter()
        cur_counts: Counter[str] = Counter()
        any_base_file = False
        for rel in group:
            base_text = _file_at_ref(base_ref, rel)
            if base_text is not None:
                any_base_file = True
                base_counts.update(l for l in base_text.splitlines() if l.strip())
            cur_path = HERE / rel
            if cur_path.is_file():
                cur_text = cur_path.read_text(encoding="utf-8", errors="replace")
                cur_counts.update(l for l in cur_text.splitlines() if l.strip())
        if not any_base_file:
            print(f"  {label}：{base_ref} 上都沒有這些檔案，跳過（視為這個 PR 新增）")
            continue
        missing = base_counts - cur_counts   # 只留「base 次數 > cur 次數」的差額
        n_missing = sum(missing.values())
        if missing:
            fails.append(
                f"{label}：{n_missing} 行在 {base_ref} 存在的次數比這個分支（這組檔案合併後）多"
                f"——這組 append-only 檔案只能新增或在組內搬移，不能真的修改或刪除既有行")
            for m in sorted(missing.elements())[:5]:
                print(f"    消失/被改掉的行：{m[:150]}")
            if n_missing > 5:
                print(f"    ...還有 {n_missing - 5} 行")
        else:
            print(f"  {label}：OK（{sum(base_counts.values())} 行全部還在）")
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
