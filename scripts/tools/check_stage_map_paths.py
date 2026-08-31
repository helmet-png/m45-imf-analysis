# -*- coding: utf-8 -*-
"""驗證 `status_dashboard/stage_map.py` 裡列的每支 script 路徑，在 repo
裡真的存在——2026-08-31 發現的問題：`scripts/tools/reorganize.py` 之類
的搬檔案／改名 commit 完全不會動到 `stage_map.py`（兩者沒有程式層級的
關聯，只是同一批人手動維護），檔案搬走後主控板會一直顯示「本機找不到」
卻沒有人會主動發現，直到有人剛好點開那個步驟才踩到。

這支腳本補上自動化的那一道檢查：CI 每次 PR 都跑一次，路徑對不上就讓
建置失敗，逼搬檔案的人順手更新 `stage_map.py`（跟 `git mv` 忘記更新
import 路徑是同一類坑，只是這裡沒有 import 錯誤可以提示，得自己檢查）。

`external`（第三方套件，見 stage_map.py 檔頭說明）裡列的路徑本來就允許
本機沒有，跳過不驗證。

用法：
    python3 scripts/tools/check_stage_map_paths.py
在 repo 根目錄執行，找到任何找不到的路徑就印出來並以非 0 結束。
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

sys.path.insert(0, str(REPO_ROOT / "status_dashboard"))
from stage_map import STAGES  # noqa: E402


def main() -> int:
    missing: list[tuple[str, str, str]] = []
    for stage in STAGES:
        for step in stage["steps"]:
            external = step.get("external", {})
            for script in step.get("scripts", []):
                if script in external:
                    continue
                if not (REPO_ROOT / script).is_file():
                    missing.append((stage["name"], step["name"], script))

    if not missing:
        print("stage_map.py 裡的腳本路徑全部存在，檢查通過。")
        return 0

    print("stage_map.py 裡有腳本路徑在本機找不到，可能是搬檔案／改名"
          "後忘記同步更新（也可能是 external 漏標）：\n")
    for stage_name, step_name, script in missing:
        print(f"  [{stage_name} / {step_name}] {script}")
    print(f"\n共 {len(missing)} 筆。請更新 status_dashboard/stage_map.py "
          "對應的 scripts 路徑，或若是第三方套件就補上 external 標記。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
