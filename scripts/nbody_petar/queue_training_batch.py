#!/usr/bin/env python
"""派工佇列（cloud_queue.txt）用的 N-body 訓練批次包裝腳本。

功能：讓 `cloud_queue.py` 能把方法 B 的訓練網格派到 senior24 這類
「已經自己編好 PeTar／mcluster／galpy」的遠端機器上跑。佇列只會做
`cd <remote_dir> && <python_bin> -u <腳本> <參數>`（見 `ssh_sync.run()`），
不會設定 PeTar 需要的 PATH／PYTHONPATH／OMP 變數，也不知道 PeTar 裝在
哪；這支腳本補上這一層，然後呼叫 `run_training_queue.py` 跑「下一批
尚未完成的 N 筆」。

為什麼要切批次（不是一次丟 430 筆）：`cloud_queue.py` 的
`MAX_WAIT_HOURS = 20`，單一工作超過 20 小時會被判逾時並砍掉。430 筆
估計 100+ 小時，所以在 `cloud_queue.txt` 排多行、每行 `--limit N`
（N 筆約 ≤ 10 小時）。每行都是同一條指令、不同標籤：`run_training_queue.py`
本來就會跳過已完成的 run（可續跑），所以第 k 批自然接著第 k−1 批做，
不需要在參數裡指定切片範圍。

方法：
1. 找 PeTar 安裝目錄 `<nbody-dir>/install/bin`（`--nbody-dir`，預設環境變數
   `NBODY_DIR`，再退回 `~/nbody`）。`petar.omp.*.bse.galpy` 用 glob 找、
   要求恰好一個——共用機器上 `petar` 符號連結會被別人的建置動作改指
   向（見 `run_nbody_case.apply_petar_binary_override()`），所以一律傳
   完整檔名，不依賴裸的 `petar`。找不到或找到多個都直接報錯結束。
2. 組環境：`PATH` 最前面放 `--env-bin`（PeTar 的分析腳本 `petar.data.process`
   是 `#!/usr/bin/env python3`，要能 import numpy／astropy 的那個 python
   必須排在 PATH 最前面；預設用目前這支腳本自己的 python 所在目錄）、
   `<nbody-dir>/install/bin`、`<nbody-dir>/mcluster`；`PYTHONPATH` 加
   `<nbody-dir>/install/include`（`import petar` 用）；`OMP_STACKSIZE=128M`。
3. 開跑前的健檢（任何一項失敗就以非零狀態結束，不開始長跑）：
   (a) `<petar-bin> -h` 輸出含 `--galpy-set`；(b) `mcluster_sse` 找得到；
   (c) 組好環境後的 `python3` 能 import numpy 與 astropy。
   每一項的結果都印出來，失敗時派工主機的 `logs/<label>.out` 就是診斷。
4. 用同一個 python 開子行程跑 `run_training_queue.py --limit N ...`，
   串流輸出；結束後把進度統計（完成幾筆、失敗幾筆、每筆能量誤差）寫成
   小檔 `results/nbody_training_status.json`——派工主機只會把
   `results/` 底下新檔拉回，這份小檔是它看得到進度的唯一管道（run 的
   原始資料量大，留在 senior24 的 `runs_training/`，不拉回）。

自我測試（`--self-test`）：用暫存目錄造出假的安裝樹（假的
`petar.omp.avx512.bse.galpy` 是會印出 `--galpy-set` 的小 shell 腳本）、
確認：glob 恰好一個才通過、找到多個會報錯、缺 `--galpy-set` 會報錯、
PATH 組合順序正確。不需要真的 PeTar。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent


def find_petar_bin(nbody_dir: Path) -> str:
    """回傳 install/bin 底下唯一一個 petar.omp.*.bse.galpy 的**絕對路徑**。

    不能只回傳檔名（CodeRabbit #223）：檔名會被 PATH 解析，`--env-bin`
    目錄若剛好有同名的舊 PeTar 就會先被找到，健檢與訓練會跑錯版本。"""
    bin_dir = nbody_dir / "install" / "bin"
    hits = sorted(glob.glob(str(bin_dir / "petar.omp.*.bse.galpy")))
    if len(hits) != 1:
        raise RuntimeError(
            f"{bin_dir} 底下找到 {len(hits)} 個 petar.omp.*.bse.galpy（要恰好 1 個）："
            f"{[os.path.basename(h) for h in hits]}"
        )
    return str(Path(hits[0]).resolve())


def build_env(nbody_dir: Path, env_bin: str, n_threads: int) -> dict:
    env = os.environ.copy()
    path_parts = [env_bin, str(nbody_dir / "install" / "bin"), str(nbody_dir / "mcluster")]
    env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])
    py_parts = [str(nbody_dir / "install" / "include")]
    if env.get("PYTHONPATH"):
        py_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(py_parts)
    env["OMP_STACKSIZE"] = "128M"
    env["OMP_NUM_THREADS"] = str(n_threads)
    return env


def preflight(petar_bin: str, env: dict) -> list[str]:
    """回傳失敗訊息清單（空清單＝全部通過），每項結果都印出來。"""
    failures: list[str] = []

    r = subprocess.run([petar_bin, "-h"], env=env, capture_output=True, text=True)
    ok = "--galpy-set" in (r.stdout + r.stderr)
    print(f"[健檢] {petar_bin} -h 含 --galpy-set：{ok}", flush=True)
    if not ok:
        failures.append(f"{petar_bin} 沒有 --galpy-set")

    which_mc = shutil.which("mcluster_sse", path=env["PATH"])
    print(f"[健檢] mcluster_sse：{which_mc}", flush=True)
    if not which_mc:
        failures.append("找不到 mcluster_sse")

    py3 = shutil.which("python3", path=env["PATH"])
    r = subprocess.run(
        [py3 or "python3", "-c", "import numpy, astropy; print(numpy.__version__, astropy.__version__)"],
        env=env, capture_output=True, text=True,
    )
    print(f"[健檢] PATH 上的 python3={py3}，import numpy/astropy："
          f"{r.stdout.strip() or r.stderr.strip()[-200:]}", flush=True)
    if r.returncode != 0:
        failures.append("PATH 上的 python3 不能 import numpy/astropy")
    return failures


def write_status(runs_dir: Path, out_path: Path) -> dict:
    complete, failed, energy = [], [], {}
    for d in sorted(runs_dir.glob("mb_train_*")):
        rp = d / "result.json"
        # 沒有 result.json＝這個 run 中途失敗或被中斷（run_nbody_case 步驟失敗
        # 只寫 stage.json、不寫 result.json），要算進 failed，不能悄悄略過
        # （CodeRabbit #223）。本函式只在 run_training_queue 子行程結束後呼叫，
        # 所以不會誤把「正在跑」的 run 當失敗。
        if not rp.exists():
            failed.append({"run_id": d.name, "status": "missing_result"})
            continue
        try:
            data = json.loads(rp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            failed.append({"run_id": d.name, "status": "invalid_result"})
            continue
        if data.get("status") == "complete" and not data.get("smoke", False):
            complete.append(d.name)
            energy[d.name] = data.get("energy", {}).get("energy_error_relative")
        else:
            failed.append({"run_id": d.name, "status": data.get("status")})
    summary = {"n_complete": len(complete), "failed": failed, "energy_error_relative": energy}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def run_self_test() -> dict:
    checks = {}
    with tempfile.TemporaryDirectory() as tmp:
        nb = Path(tmp) / "nbody"
        bin_dir = nb / "install" / "bin"
        bin_dir.mkdir(parents=True)
        (nb / "mcluster").mkdir()
        fake = bin_dir / "petar.omp.avx512.bse.galpy"
        fake.write_text("#!/bin/sh\necho '--galpy-set'\n")
        fake.chmod(0o755)
        checks["glob_single_ok"] = find_petar_bin(nb) == str(fake.resolve())

        (bin_dir / "petar.omp.avx2.bse.galpy").write_text("x")
        try:
            find_petar_bin(nb)
            checks["glob_multiple_rejected"] = False
        except RuntimeError:
            checks["glob_multiple_rejected"] = True
        (bin_dir / "petar.omp.avx2.bse.galpy").unlink()

        env = build_env(nb, "/env/bin", 24)
        parts = env["PATH"].split(os.pathsep)
        checks["path_order"] = parts[:3] == ["/env/bin", str(bin_dir), str(nb / "mcluster")]
        checks["pythonpath_has_include"] = str(nb / "install" / "include") in env["PYTHONPATH"]
        checks["omp_threads"] = env["OMP_NUM_THREADS"] == "24"

        if os.name != "nt":
            checks["preflight_flags_missing_mcluster"] = any(
                "mcluster_sse" in m for m in preflight("petar.omp.avx512.bse.galpy", env)
            )
            fake.write_text("#!/bin/sh\necho nothing\n")
            checks["preflight_flags_missing_galpy_set"] = any(
                "--galpy-set" in m for m in preflight("petar.omp.avx512.bse.galpy", env)
            )

        rd = Path(tmp) / "runs"
        (rd / "mb_train_0001_s1").mkdir(parents=True)
        (rd / "mb_train_0001_s1" / "result.json").write_text(
            json.dumps({"status": "complete", "smoke": False, "energy": {"energy_error_relative": 1e-6}}))
        (rd / "mb_train_0002_s2").mkdir()
        (rd / "mb_train_0002_s2" / "result.json").write_text(
            json.dumps({"status": "complete", "smoke": True}))
        s = write_status(rd, Path(tmp) / "st.json")
        (rd / "mb_train_0003_s3").mkdir()  # 只有目錄、沒有 result.json
        (rd / "mb_train_0004_s4").mkdir()
        (rd / "mb_train_0004_s4" / "result.json").write_text("{not json")
        s = write_status(rd, Path(tmp) / "st.json")
        st = {f["run_id"]: f["status"] for f in s["failed"]}
        checks["status_counts_smoke_excluded"] = s["n_complete"] == 1 and st.get("mb_train_0002_s2") == "complete"
        checks["status_missing_and_invalid_result_are_failed"] = (
            st.get("mb_train_0003_s3") == "missing_result" and st.get("mb_train_0004_s4") == "invalid_result")

    if not all(checks.values()):
        raise AssertionError(f"queue_training_batch self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nbody-dir", type=Path,
                    default=Path(os.environ.get("NBODY_DIR", "~/nbody")).expanduser())
    ap.add_argument("--env-bin", default=str(Path(sys.executable).parent),
                    help="要排在 PATH 最前面的目錄（需有能 import numpy/astropy 的 python3）")
    ap.add_argument("--limit", type=int, default=30, help="本批最多跑幾筆尚未完成的 run")
    ap.add_argument("--n-threads", type=int, default=24)
    ap.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_training_grid.csv")
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

    print(f"nbody-dir={args.nbody_dir}  env-bin={args.env_bin}  limit={args.limit}", flush=True)
    petar_bin = find_petar_bin(args.nbody_dir)
    env = build_env(args.nbody_dir, args.env_bin, args.n_threads)
    failures = preflight(petar_bin, env)
    if failures:
        print("健檢失敗，不開始長跑：" + "；".join(failures), flush=True)
        sys.exit(2)

    rc = subprocess.run(
        [sys.executable, "-u", str(HERE / "run_training_queue.py"),
         "--grid", str(args.grid), "--runs-dir", str(args.runs_dir),
         "--n-threads", str(args.n_threads), "--petar-bin", petar_bin,
         "--limit", str(args.limit)],
        env=env, cwd=REPO_ROOT,
    ).returncode
    summary = write_status(args.runs_dir, REPO_ROOT / "results" / "nbody_training_status.json")
    print(f"本批結束：累計完成 {summary['n_complete']} 筆，失敗／殘留 {len(summary['failed'])} 筆", flush=True)
    sys.exit(rc)


if __name__ == "__main__":
    main()
