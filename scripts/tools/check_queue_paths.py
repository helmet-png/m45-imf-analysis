# -*- coding: utf-8 -*-
"""檢查佇列檔裡每一行工作的腳本與額外檔案都存在。

2026-11 目錄重整後新增：搬檔之後，任何新排進佇列、還寫舊路徑的工作會
在 worker 上才失敗（浪費一次派工），這裡在 PR 階段就擋下。
`results/` 開頭的額外檔案不檢查：那些是先前工作的產出，排隊當下可能還沒進版控。

用法：python scripts/tools/check_queue_paths.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPE_QUEUES = ("cloud_queue.txt", "ops/kaggle_queue.txt")   # 標籤|腳本|參數|額外檔案|...
CMD_QUEUES = ("ops/queue.txt",)                             # 標籤|腳本 參數


def _active_lines(rel: str):
    for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
        if line.strip() and not line.lstrip().startswith("#") and "|" in line:
            yield n, line.split("|")


def find_problems() -> list[str]:
    problems = []
    for rel in PIPE_QUEUES:
        for n, f in _active_lines(rel):
            if len(f) < 4:
                continue
            for t in [f[1].strip()] + [x.strip() for x in f[3].split(",")]:
                if t and not t.startswith("results/") and not (ROOT / t).exists():
                    problems.append(f"{rel}:{n} 找不到 {t}")
    for rel in CMD_QUEUES:
        for n, f in _active_lines(rel):
            words = f[1].split()
            if words and not (ROOT / words[0]).exists():
                problems.append(f"{rel}:{n} 找不到 {words[0]}")
    return problems


def main() -> int:
    problems = find_problems()
    for p in problems:
        print(p)
    if problems:
        print(f"\n共 {len(problems)} 筆。檔案搬過位置的話，對照 README 第 8 節改成新路徑。")
        return 1
    print("佇列檔裡的腳本與額外檔案路徑全部存在，檢查通過。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
