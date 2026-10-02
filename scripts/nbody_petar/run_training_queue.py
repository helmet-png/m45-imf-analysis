#!/usr/bin/env python
"""依序把 petar_m45_training_grid.csv 的每一列餵給 run_nbody_case.py，
跑完方法 B 的整批訓練集（預設 430 runs）。

功能：`run_nbody_case.py` 一次只跑一個 `--run-id`；這支程式是外層迴圈，
在**同一台機器**上依序（不平行）把整份訓練網格跑完，供背景長時間
（單機序列估計 ~100+ 小時，見 `docs/planning/NBODY_PREREGISTRATION.md`
第六節時程表）無人值守執行時用（`nohup python run_training_queue.py &`）。
真正要多機平行時，把 `--grid` 切成幾份子檔案（例如依 run_id 的雜湊或
連續區段切）在不同機器上各跑一份，不需要改這支程式。

方法：
1. 讀 grid CSV 的所有 run_id（照 CSV 原本順序，不重排——`run_id` 已經
   按拉丁超立方設計點序號命名，維持原順序方便事後檢查進度）。
2. 每個 run_id：先看 `<runs-dir>/<run_id>/result.json` 是否存在且
   `status` 是 `"complete"`——是就跳過（**可續跑**，機器中途重開、
   SSH 斷線重連都不用從頭來過，這點沿用 `run_nbody_case.py` 自己
   `stage.json` 的續跑機制，這支程式只是在更外層加一層「整批」的
   續跑判斷）。
3. 沒跳過的就 `subprocess.run([sys.executable, "run_nbody_case.py",
   "--run-id", run_id, ...])`——不直接呼叫 `run_case()` 函式，而是開
   子行程：單一 run 若真的當掉（segfault、OOM），子行程崩潰不會拖垮
   這支外層迴圈，下一個 run_id 還能繼續跑，錯誤只記錄不中止整批。
4. 每個 run 結束（不論成功/失敗）都在 `<runs-dir>/queue_progress.json`
   追加一筆記錄（run_id、status、耗時、時間戳），供另開一個 shell用
   `tail -f` 或直接讀 JSON 檢查進度，不用等全部跑完才知道目前在哪。
5. `--limit N`：只跑前 N 個尚未完成的 run，方便先跑一小批確認沒問題
   再放著跑一整晚／一整批。

自我測試：不適用（這支程式本身沒有需要驗證的計算邏輯，全部邏輯都是
子行程呼叫與 JSON 記錄；正確性由 `run_nbody_case.py` 自己的
`--self-test` 保證，這裡不重複驗證一次）。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
全部是 Python 標準庫：
  argparse     讀命令列參數
  json         讀 result.json、寫進度紀錄
  subprocess   subprocess.run 執行 run_nbody_case.py，等它結束再跑下一個
  sys          sys.executable：用目前這個 Python 去執行子程式
  time         計時（time.monotonic）與時間戳（time.strftime）
  pathlib      路徑
本專案其他模組：
  scripts/nbody_petar/petar_m45_grid.py   load_grid()：讀網格 CSV
  scripts/nbody_petar/run_nbody_case.py   被當成子程式執行（不是 import）

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --grid              網格 CSV，預設 petar_m45_training_grid.csv
  --runs-dir          每個 run 的輸出資料夾，預設 runs_training/
                      ⚠ emulator_fit.py 的 --runs-dir 預設是 runs/，
                        訓練時要記得指到 runs_training/
  --n-threads (8)     每個模擬用幾個執行緒（OMP_NUM_THREADS）
  --energy-threshold (1e-3)  能量守恆門檻，原樣傳給 run_nbody_case.py
  --petar-bin (petar)  PeTar 執行檔名，原樣傳給 run_nbody_case.py
  --limit             這次最多跑幾個尚未完成的 run

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 93–109 行｜already_complete()：判斷一個 run 是否已用正式設定跑完
  核心 2｜第 124–142 行｜main() 決定要跑哪些 run、排順序
  核心 3｜第 144–175 行｜main() 逐一執行 run_nbody_case.py 並記錄結果

======================================================================
【(d) 整體流程】
======================================================================
  讀網格 CSV 的所有 run_id
    → 過濾掉已完成的（result.json 的 status 是 complete、且不是 smoke）
    → 排序：從沒開始過的排前面，開始過但失敗的排後面
    → 有 --limit 就只取前 N 個
    → 逐一：執行 python run_nbody_case.py --run-id … --grid … --runs-dir …
      → 回傳碼 0 記為 complete，否則記為 failed（能量檢查沒過也會回傳 1）
      → 在 <runs-dir>/queue_progress.json 追加一行紀錄
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from petar_m45_grid import load_grid  # noqa: E402


# ═══════════════ 核心 1：判斷是否已完成 ═══════════════
def already_complete(run_dir: Path) -> bool:
    """2026-09-18 修正（Codex review）：以前只看 status=='complete'，沒
    排除 smoke 跑完留下的 result.json——smoke 用縮短的積分時間跑，拿它
    的 result.json 當「這個 run_id 已經用正式設定跑完」會整批漏跑。這
    支程式從不傳 --smoke（見上方模組說明），所以任何 smoke=true 的舊
    結果一定是別的用途（手動測試）留下的殘留，不能算數。"""
    # ↓ run_nbody_case.py 跑完會寫 result.json；沒有就是沒跑完
    result_path = run_dir / "result.json"
    if not result_path.exists():
        return False
    try:
        data = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    # ↓ 狀態是 complete、而且不是 smoke（縮短版測試）才算完成
    return data.get("status") == "complete" and not data.get("smoke", False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_training_grid.csv")
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    parser.add_argument("--n-threads", type=int, default=8)
    parser.add_argument("--energy-threshold", type=float, default=1e-3)
    parser.add_argument("--petar-bin", default="petar",
                         help="轉傳給 run_nbody_case.py，見該檔案 --petar-bin 的說明")
    parser.add_argument("--limit", type=int, default=None,
                         help="只跑前 N 個尚未完成的 run（測試用），預設全部")
    args = parser.parse_args()

    # ═══════════════ 核心 2：決定要跑哪些 run ═══════════════
    rows = load_grid(args.grid)
    run_ids = [r["run_id"] for r in rows]
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    progress_path = args.runs_dir / "queue_progress.json"

    # ↓ 還沒完成的 run_id（照 CSV 原順序）
    todo = [rid for rid in run_ids if not already_complete(args.runs_dir / rid)]
    # 2026-09-21：沒跑過的排前面、失敗過的排後面（sorted 是穩定排序，各組
    # 內維持 CSV 原順序）。派工佇列把同一個 `--limit N` 重複排很多次，
    # 若某個 run 每次都失敗又永遠排在最前面，會吃掉每一批的名額、讓後面
    # 沒跑過的 run 永遠輪不到。
    todo = sorted(todo, key=lambda rid: (args.runs_dir / rid / "stage.json").exists())
    n_pending = len(todo)  # 截斷前的未完成數，已完成數要用這個算（CodeRabbit #223）
    if args.limit is not None:
        todo = todo[: args.limit]

    print(f"總共 {len(run_ids)} 筆，已完成 {len(run_ids) - n_pending} 筆，"
          f"本次要跑 {len(todo)} 筆", flush=True)

    # ═══════════════ 核心 3：逐一執行 ═══════════════
    for i, run_id in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] 開始 {run_id}", flush=True)
        t0 = time.monotonic()
        # ↓ 開一個子行程執行 run_nbody_case.py；這個 run 當掉不會拖垮整批
        proc = subprocess.run(
            [
                sys.executable, str(HERE / "run_nbody_case.py"),
                "--run-id", run_id,
                "--grid", str(args.grid),
                "--runs-dir", str(args.runs_dir),
                "--n-threads", str(args.n_threads),
                "--energy-threshold", str(args.energy_threshold),
                "--petar-bin", args.petar_bin,
            ],
            cwd=REPO_ROOT,
        )
        elapsed = time.monotonic() - t0
        status = "complete" if proc.returncode == 0 else f"failed(rc={proc.returncode})"
        print(f"[{i}/{len(todo)}] {run_id}：{status}，耗時 {elapsed:.1f}s", flush=True)

        record = {
            "run_id": run_id,
            "status": status,
            "elapsed_seconds": elapsed,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        # ↓ 用附加模式（"a"）寫一行 JSON 紀錄，不覆蓋之前的
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    print("整批跑完", flush=True)


if __name__ == "__main__":
    main()
