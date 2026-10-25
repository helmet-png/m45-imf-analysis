#!/usr/bin/env python
"""方法 B 訓練資料的批次後處理：N-body 快照 → observed.stats.json。

功能：`emulator_fit.load_training_data()` 要讀每筆 run 目錄裡的
`observed.stats.json`（26 維統計量，定義見
`docs/planning/NBODY_PREREGISTRATION.md` 第四節），但沒有任何程式會產生
它。這支程式把既有的三支單筆工具串起來，對整個 `runs_training/` 逐筆
跑完：

    data.K（PeTar 原始快照）
      → petar.data.process -M     （只處理這一張，輸出到 <run>/multiples/，
                                   不覆蓋原始的 data.K.single/.binary）
      → petar_system_catalog.py   （組成「系統」層級的 NPZ）
      → observe_snapshot.py       （投影＋等時線測光＋雙星合併＋雜訊＋選樣＋孔徑，
                                   輸出跟 data/cmd_members.csv 同欄位的假觀測）
      → nbody_summary_stats.py --from-mock
                                  （與真實資料共用同一支估計器）
      → <run>/observed.stats.json

三支工具都用子行程呼叫原本的 CLI，不重新實作任何一步；這支只負責選
快照、選投影、組參數、記錄來源、可續跑與平行。

方法（每個選擇都寫進每筆的 `observed.provenance.json`，之後要改可追溯）：
0. **多重系統重新偵測**：訓練網格跑的 `petar.data.process` 沒有 `-M`，只找
   單星與雙星；階層式三合星會被拆成兩筆共用同一顆星的雙星（2026-10-02 在
   `mb_train_0005_s40006` 實測：ID 786 同時是 45 AU 內雙星與 6,000 AU 外雙星
   的成員），`petar_system_catalog.py` 因 ID 重複而拒絕。這裡把選定的快照
   複製到 `<run>/multiples/`，用同樣的 `-i bse -t galpy` 加 `-M` 重新偵測
   單／雙／三／四合星，再交給後面兩步。
1. **快照時間**：預設 105 Myr（`data.21`，`--snapshot-index`）。理由：
   `observe_snapshot.py` 把質量換成星等用的等時線年齡是 logage 8.026
   ≈ 106 Myr（前向模型擬合真實資料的年齡）；快照時間要跟等時線年齡
   一致，否則模擬端的質量—光度關係跟觀測端不是同一個年齡。年齡不確定度
   （預註冊的 100–135 Myr 窗）之後要另外處理（例如把時間當作 θ 的一維），
   不在這支程式偷偷平均掉。
2. **投影方向**：每筆 run 只取一個方向，索引由 run_id 決定
   （`sha256(run_id) mod --n-projections`），讓不同 run 的方向均勻分散、
   且重跑結果可重現。單一方向造成的統計量雜訊由 GP 的 nugget 吸收
   （跟「每點一個 seed」同一個設計）。
3. **選樣退化**：`observe_snapshot.py` 不允許測光品質選擇函數與 HR23
   召回曲線同時開（兩者量的是同一批流失，疊乘會算兩次，見該檔說明）。
   預設開選擇函數、關召回曲線（`--no-recall`）：選擇函數是機制模型
   （SNR 對星等／顏色），召回曲線的流失已被證實完全可由品質切割解釋。
   這是**初步判讀**，可用 `--degradation recall` 換成另一種。
4. **哪些 run 要處理**：預設只處理 `result.json` 的 status 為
   `complete` 且非 smoke 的 run（`--include-status` 可改）。舊版 PeTar
   跑的 run，其 `complete` 標記不代表積分驗收通過（見預註冊五節
   2026-10-02 再訂正），所以每筆 provenance 都記下該 run 用的 PeTar
   執行檔，訓練時可以據此篩選。
5. **可續跑**：`observed.stats.json` 已存在且 provenance 的設定跟這次
   相同就跳過；設定不同就重做（舊檔覆蓋前先改名保留）。
6. **平行**：`--jobs` 個 run 同時處理（預設 2，避免搶正在跑 N-body 的 CPU）。

自我測試（`--self-test`）：不需要真的快照。檢查 (a) 投影索引的決定性與
範圍、(b) 依 status 篩 run 的邏輯、(c) 組出來的三段指令參數正確（含
triple 檔存在才帶 `--triple`）、(d) provenance 相同時會跳過。真正的端到端
驗證是對 VM 上已跑完的 run 實跑，結果寫在執行報告裡。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
SNAPSHOT_DT_MYR = 5.0  # petar_m45_grid.render_commands() 的 -o 5.0


def projection_index(run_id: str, n_projections: int) -> int:
    return int(hashlib.sha256(run_id.encode()).hexdigest(), 16) % n_projections


def select_runs(runs_dir: Path, include_status: set[str]) -> list[Path]:
    out = []
    for d in sorted(runs_dir.glob("mb_train_*")):
        if not d.is_dir() or ".stale-" in d.name:
            continue
        res = d / "result.json"
        if not res.exists():
            continue
        try:
            r = json.loads(res.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if r.get("status") in include_status and not r.get("smoke", False):
            out.append(d)
    return out


def petar_binary_of(run_dir: Path) -> str:
    """從 manifest.json 讀出這筆 run 實際用的 petar 執行檔（第 3 步指令的第一個字）。"""
    m = run_dir / "manifest.json"
    if not m.exists():
        return "unknown"
    try:
        cmds = json.loads(m.read_text(encoding="utf-8")).get("commands", [])
        return cmds[2].split()[0] if len(cmds) > 2 else "unknown"
    except (json.JSONDecodeError, IndexError):
        return "unknown"


def build_commands(run_dir: Path, args, py: str) -> tuple[list[list[str]], dict]:
    k = args.snapshot_index
    mdir = run_dir / "multiples"
    base = mdir / f"data.{k}"
    t_myr = k * SNAPSHOT_DT_MYR
    pidx = projection_index(run_dir.name, args.n_projections)
    catalog = run_dir / f"catalog_t{t_myr:g}.npz"
    observed = run_dir / "observed.csv"

    multi_cmd = ["petar.data.process", "-i", "bse", "-t", "galpy", "-M", "-n", "1",
                 "-p", str(mdir / "data"), str(mdir / "snap.lst")]

    cat_cmd = [py, str(HERE / "petar_system_catalog.py"),
               "--single", f"{base}.single", "--time-myr", f"{t_myr:g}",
               "--interrupt-mode", "bse", "--external-mode", "galpy",
               "--output", str(catalog), "--confirm-complete"]
    # binary/triple/quadruple 檔要等 multi_cmd 跑完才存在，所以這裡固定帶
    # 「可能存在」的路徑，由 process_run() 在 multi_cmd 之後再依實際檔案篩掉。
    for kind in ("binary", "triple", "quadruple"):
        cat_cmd += [f"--{kind}", f"{base}.{kind}"]
    if args.petar_package_path:
        cat_cmd += ["--petar-package-path", str(args.petar_package_path)]

    obs_cmd = [py, str(HERE / "observe_snapshot.py"), "--catalog", str(catalog),
               "--projection-index", str(pidx), "--n-projections", str(args.n_projections),
               "--seed", str(pidx), "--output", str(observed)]
    obs_cmd.append("--no-recall" if args.degradation == "selection" else "--no-selection")

    stats_cmd = [py, str(HERE / "nbody_summary_stats.py"), "--from-mock", str(observed),
                 "--output", str(run_dir / "observed.stats.json")]

    provenance = {
        "snapshot_index": k, "time_myr": t_myr,
        "projection_index": pidx, "n_projections": args.n_projections,
        "degradation": args.degradation,
        "multiples_redetected": True,
        "petar_binary": petar_binary_of(run_dir),
    }
    return [multi_cmd, cat_cmd, obs_cmd, stats_cmd], provenance


def _drop_missing_optional(cmd: list[str]) -> list[str]:
    """拿掉指向不存在或空檔的 --binary/--triple/--quadruple。"""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] in ("--binary", "--triple", "--quadruple"):
            f = Path(cmd[i + 1])
            if f.exists() and f.stat().st_size > 0:
                out += cmd[i:i + 2]
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def process_run(run_dir: Path, args, py: str) -> dict:
    cmds, prov = build_commands(run_dir, args, py)
    stats_p = run_dir / "observed.stats.json"
    prov_p = run_dir / "observed.provenance.json"
    if stats_p.exists() and prov_p.exists():
        try:
            old = json.loads(prov_p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
        if {k: old.get(k) for k in prov} == prov:
            return {"run_id": run_dir.name, "status": "skipped_up_to_date"}
        stamp = int(time.time())
        stats_p.rename(stats_p.with_name(f"observed.stats.json.old-{stamp}"))
    snap = run_dir / f"data.{args.snapshot_index}"
    if not snap.exists():
        return {"run_id": run_dir.name, "status": "missing_snapshot"}

    mdir = run_dir / "multiples"
    mdir.mkdir(exist_ok=True)
    shutil.copy2(snap, mdir / snap.name)
    (mdir / "snap.lst").write_text(f"{mdir / snap.name}\n", encoding="utf-8")

    log_p = run_dir / "build_training_stats.log"
    t0 = time.monotonic()
    with log_p.open("w", encoding="utf-8") as log:
        for step, cmd in zip(("multiples", "catalog", "observe", "stats"), cmds):
            if step == "catalog":
                cmd = _drop_missing_optional(cmd)
            log.write("$ " + " ".join(cmd) + "\n")
            log.flush()
            r = subprocess.run(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT)
            if r.returncode != 0:
                return {"run_id": run_dir.name, "status": f"failed_{step}", "log": str(log_p)}
    prov["seconds"] = round(time.monotonic() - t0, 1)
    prov_p.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    return {"run_id": run_dir.name, "status": "ok", "seconds": prov["seconds"]}


def run_self_test() -> dict:
    checks = {}
    idx = [projection_index(f"mb_train_{i:04d}_s{i}", 32) for i in range(200)]
    checks["projection_deterministic"] = projection_index("a", 32) == projection_index("a", 32)
    checks["projection_in_range_and_spread"] = min(idx) >= 0 and max(idx) < 32 and len(set(idx)) > 20

    with tempfile.TemporaryDirectory() as tmp:
        rd = Path(tmp)
        for name, res in [("mb_train_0001_s1", {"status": "complete", "smoke": False}),
                          ("mb_train_0002_s2", {"status": "energy_check_failed"}),
                          ("mb_train_0003_s3", {"status": "complete", "smoke": True}),
                          ("mb_train_0004_s4.stale-1", {"status": "complete"})]:
            (rd / name).mkdir()
            (rd / name / "result.json").write_text(json.dumps(res))
        sel = [p.name for p in select_runs(rd, {"complete"})]
        checks["select_only_formal_complete"] = sel == ["mb_train_0001_s1"]

        d = rd / "mb_train_0001_s1"
        (d / "data.21.single").write_text("x")
        (d / "multiples").mkdir()
        (d / "multiples" / "data.21.binary").write_text("x")
        (d / "multiples" / "data.21.triple").write_text("")  # 空檔不該帶
        (d / "manifest.json").write_text(json.dumps({"commands": ["a", "b", "/x/petar.omp.y -u 1", "c"]}))
        ns = argparse.Namespace(snapshot_index=21, n_projections=32, degradation="selection",
                                petar_package_path=None)
        cmds, prov = build_commands(d, ns, "py")
        multi, cat, obs, st = cmds
        checks["multiples_step_uses_M_and_galpy"] = "-M" in multi and multi[multi.index("-t") + 1] == "galpy"
        cat = _drop_missing_optional(cat)
        checks["catalog_has_binary_not_empty_triple"] = (
            "--binary" in cat and "--triple" not in cat and "--quadruple" not in cat)
        checks["catalog_reads_multiples_dir"] = "/multiples/" in cat[cat.index("--single") + 1].replace("\\", "/")
        checks["catalog_time_105"] = cat[cat.index("--time-myr") + 1] == "105"
        checks["observe_no_recall"] = "--no-recall" in obs and "--no-selection" not in obs
        checks["stats_output_name"] = st[-1].endswith("observed.stats.json")
        checks["petar_binary_recorded"] = prov["petar_binary"] == "/x/petar.omp.y"

        (d / "observed.stats.json").write_text("{}")
        (d / "observed.provenance.json").write_text(json.dumps(prov))
        checks["skip_when_provenance_matches"] = process_run(d, ns, "py")["status"] == "skipped_up_to_date"
    if not all(checks.values()):
        raise AssertionError(f"build_training_stats self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    ap.add_argument("--snapshot-index", type=int, default=21, help="快照編號；時間 = 編號 × 5 Myr")
    ap.add_argument("--n-projections", type=int, default=32)
    ap.add_argument("--degradation", choices=("selection", "recall"), default="selection")
    ap.add_argument("--include-status", default="complete",
                    help="逗號分隔，處理 result.json 的哪些 status")
    ap.add_argument("--petar-package-path", type=Path,
                    default=Path(os.environ.get("PETAR_PYTHON_PATH", "")) or None)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--run-ids", default=None, help="逗號分隔，只處理這些 run（仍套用 --include-status）")
    ap.add_argument("--summary-out", type=Path,
                    default=REPO_ROOT / "results" / "nbody_training_stats_build.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return
    if args.petar_package_path is not None and str(args.petar_package_path) in ("", "."):
        args.petar_package_path = None

    runs = select_runs(args.runs_dir, set(args.include_status.split(",")))
    if args.run_ids:
        wanted = set(args.run_ids.split(","))
        runs = [d for d in runs if d.name in wanted]
    if args.limit:
        runs = runs[: args.limit]
    print(f"要處理 {len(runs)} 筆 run（status ∈ {args.include_status}）", flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futs = {pool.submit(process_run, d, args, sys.executable): d for d in runs}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = {"n_runs": len(results), "status_count": counts,
               "snapshot_index": args.snapshot_index, "degradation": args.degradation,
               "failed": [r for r in results if r["status"].startswith(("failed", "missing"))]}
    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    args.summary_out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
