#!/usr/bin/env python
"""把方法 B 訓練網格已跑完的 run 彙整成一張小表，供進版控與後續判讀。

功能：`runs_training/<run_id>/` 底下的原始資料（每筆約 157MB）不能進
git；這支程式只抽出每筆 run 的設計參數、執行狀態、計時與能量記帳數字，
寫成一份幾十 KB 的 CSV（`results/nbody_training_runs_summary.csv`）和
一份總覽 JSON（`results/nbody_training_runs_summary.json`），讓不在
運算機上的人也能看到「跑了哪些、各自狀況如何」。

方法：
1. 讀網格 CSV（`--grid`，預設 `petar_m45_training_grid.csv`）拿到每個
   run_id 的六維設計參數。
2. 對 `--runs-dir` 底下每個 `mb_train_*` 目錄：
   - `stage.json`：五個步驟各自是否完成（判斷有沒有中途中斷）。
   - `result.json`：`run_nbody_case.py` 的驗收狀態、計時。
   - `petar.log`：解析**所有** `Physic:` 行，不只最後一行。欄位順序依
     PeTar `energy.hpp` 的輸出：Error/Total, Error, Error_cum, Total,
     Kinetic, Potential, Modify, Modify_group, Modify_single, Error_PP,
     Error_PP_cum。另外記錄：
       * `err_last_rel`：最後一個輸出區間的 Error/Total——這是
         `run_nbody_case.py` 現行驗收用的數字（2026-10-02 判定：開潮汐時
         不能當積分品質指標，見 NBODY_PREREGISTRATION.md）。
       * `err_cum_over_e0`：Error_cum ÷ |初始 Total|，累積相對誤差。
       * `err_cum_first_interval_frac`：第一個區間的 Error 佔 Error_cum
         的比例，用來看誤差是否集中在早期大量質量損失的階段。
       * `modify_cum`：最後一行的 Modify（恆星演化等造成的能量改變累計）。
3. 不判斷好壞、不重新分類：這支程式只負責「如實抽出數字」，驗收邏輯要等
   能量指標修正方案定案後另外處理，避免把一個未定案的判準寫死在彙整表裡。

自我測試（`--self-test`）：造一個暫存 run 目錄（兩行 Physic、假的
stage/result），確認欄位解析與比值計算正確、缺 result.json 的 run 會被
如實記成 missing 而不是被略過。
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

PHYSIC_FIELDS = ["err_rel", "err", "err_cum", "total", "kinetic", "potential",
                 "modify", "modify_group", "modify_single", "err_pp", "err_pp_cum"]
DESIGN_FIELDS = ["n_systems", "binary_system_fraction", "half_mass_radius_pc",
                 "mcluster_S", "imf_alpha_low", "imf_alpha_high", "seed"]
OUT_FIELDS = (["run_id"] + DESIGN_FIELDS +
              ["stages_done", "status", "n_threads", "petar_seconds", "n_physic_lines",
               "err_last_rel", "err_cum", "total_initial", "err_cum_over_e0",
               "err_cum_first_interval_frac", "modify_cum", "err_pp_cum",
               "angular_momentum_error_relative"])


def parse_physic(log: Path) -> list[dict]:
    rows = []
    if not log.exists():
        return rows
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("Physic:"):
            continue
        parts = line.split()[1:]
        if len(parts) < len(PHYSIC_FIELDS):  # 被截斷的行（如磁碟寫滿中斷）整行略過
            continue
        try:
            rows.append(dict(zip(PHYSIC_FIELDS, map(float, parts[:len(PHYSIC_FIELDS)]), strict=True)))
        except ValueError:
            continue
    return rows


def summarize_run(run_dir: Path, design: dict | None) -> dict:
    out = {"run_id": run_dir.name}
    for k in DESIGN_FIELDS:
        out[k] = (design or {}).get(k, "")
    stage_p = run_dir / "stage.json"
    try:
        stage = json.loads(stage_p.read_text(encoding="utf-8")) if stage_p.exists() else {}
    except json.JSONDecodeError:
        stage = {}  # 損毀時 stages_done=0 代表「完成資訊不可用」，不代表確定沒跑完
    out["stages_done"] = sum(v == "done" for v in stage.values())

    res_p = run_dir / "result.json"
    if res_p.exists():
        try:
            res = json.loads(res_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            res = {"status": "invalid_result"}
    else:
        res = {"status": "missing_result"}
    out["status"] = res.get("status")
    timing = res.get("timing", {})
    out["n_threads"] = timing.get("n_threads", "")
    out["petar_seconds"] = timing.get("steps", {}).get("petar", "")
    out["angular_momentum_error_relative"] = res.get("energy", {}).get(
        "angular_momentum_error_relative", "")

    ph = parse_physic(run_dir / "petar.log")
    out["n_physic_lines"] = len(ph)
    if len(ph) >= 2:
        first, second, last = ph[0], ph[1], ph[-1]
        out["err_last_rel"] = last["err_rel"]
        out["err_cum"] = last["err_cum"]
        out["total_initial"] = first["total"]
        out["err_cum_over_e0"] = last["err_cum"] / abs(first["total"]) if first["total"] else ""
        out["err_cum_first_interval_frac"] = second["err"] / last["err_cum"] if last["err_cum"] else ""
        out["modify_cum"] = last["modify"]
        out["err_pp_cum"] = last["err_pp_cum"]
    else:
        for k in ("err_last_rel", "err_cum", "total_initial", "err_cum_over_e0",
                  "err_cum_first_interval_frac", "modify_cum", "err_pp_cum"):
            out[k] = ""
    return out


def summarize(runs_dir: Path, grid: Path) -> list[dict]:
    with grid.open(newline="", encoding="utf-8") as f:
        design = {r["run_id"]: r for r in csv.DictReader(f)}
    return [summarize_run(d, design.get(d.name))
            for d in sorted(runs_dir.glob("mb_train_*")) if d.is_dir()]


def run_self_test() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "mb_train_0000_s1"
        d.mkdir()
        (d / "stage.json").write_text(json.dumps({k: "done" for k in
                                                  ["mcluster", "petar_init", "petar", "gether", "process"]}))
        (d / "result.json").write_text(json.dumps({"status": "complete",
                                                   "timing": {"n_threads": 8, "steps": {"petar": 600.0}}}))
        (d / "petar.log").write_text(
            "Physic: -0 0 0 -100 50 -150 0 0 0 0 0\n"
            "Physic: 0.5 -20 -20 -40 10 -50 60 0 0 1 1\n"
            "Physic: 0.01 -5 -25 -45 10 -55 70 0 0 0 1\n")
        m = Path(tmp) / "mb_train_0001_s2"
        m.mkdir()
        (m / "stage.json").write_text('{"mcluster": "do')  # 損毀
        (m / "petar.log").write_text("Physic: -0 0 0 -100 50\n")  # 截斷
        rows = [summarize_run(d, {"seed": "1"}), summarize_run(m, None)]
    r = rows[0]
    checks = {
        "err_last_rel": r["err_last_rel"] == 0.01,
        "err_cum_over_e0": abs(r["err_cum_over_e0"] - (-0.25)) < 1e-12,
        "first_interval_frac": abs(r["err_cum_first_interval_frac"] - 0.8) < 1e-12,
        "modify_cum": r["modify_cum"] == 70,
        "stages_done": r["stages_done"] == 5,
        "missing_result_recorded": rows[1]["status"] == "missing_result",
        "truncated_physic_line_skipped": rows[1]["n_physic_lines"] == 0,
        "corrupt_stage_json_tolerated": rows[1]["stages_done"] == 0,
    }
    if not all(checks.values()):
        raise AssertionError(f"summarize_training_runs self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    ap.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_training_grid.csv")
    ap.add_argument("--out-csv", type=Path, default=REPO_ROOT / "results" / "nbody_training_runs_summary.csv")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

    rows = summarize(args.runs_dir, args.grid)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        w.writeheader()
        w.writerows(rows)

    status_count: dict[str, int] = {}
    for r in rows:
        status_count[r["status"]] = status_count.get(r["status"], 0) + 1
    fully_integrated = [r for r in rows if r["stages_done"] == 5]
    overview = {
        "n_run_dirs": len(rows),
        "n_all_five_stages_done": len(fully_integrated),
        "status_count": status_count,
        "note": ("status 來自 run_nbody_case.py 的現行驗收（最後區間 |Error/Total| < 1e-3），"
                 "2026-10-02 判定該指標在開潮汐時無效，status 不代表資料好壞。"),
    }
    out_json = args.out_csv.with_suffix(".json")
    out_json.write_text(json.dumps(overview, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(overview, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
