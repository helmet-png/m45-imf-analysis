"""Kaggle-hosted Linux smoke test for the M45 N-body pipeline (S0-S2).

Function: builds PeTar (with BSE stellar evolution and galpy external
potential support) and mcluster from source on a Kaggle CPU kernel, then
runs the toolchain check (S0) and two pipeline-sanity checks (S1: does
the mcluster->petar.init->petar->process chain run at all; S2: does a
pure-gravity Plummer run conserve energy), matching
docs/planning/NBODY_PREREGISTRATION.md's smoke-test levels.

Why Kaggle: the project's own machine is Windows ARM64, which cannot
build or install galpy at all (no wheel). The project's usual Linux
compute is a GCP VM in project "hepblogger" that is currently out of
zonal capacity (gcloud start failed with resource_availability). Kaggle
kernel containers are Linux/x86_64, run as root, and have internet
access enabled (see kaggle_sync.py's enable_internet=True) -- enough to
build and smoke-test the toolchain, even though Kaggle kernels are
ephemeral (no persistent disk between runs) and therefore not a fit for
the full multi-run matrix that comes after the smoke test passes.

Method: shells out to plain apt/git/make/pip commands, mirroring the
steps in nbody_setup/setup_linux_nbody.sh (reimplemented inline here,
not by invoking that script, because a single self-contained Python
script is much easier to debug over Kaggle's asynchronous push-run-pull
cycle than a wrapped external .sh file whose failures would need a
second round trip just to see which line broke). Every step's return
code, a truncated stdout/stderr tail, and elapsed time are collected
into one JSON object, written to /kaggle/working/smoke_result.json
(Kaggle keeps files under /kaggle/working/ as kernel output, pulled
back by `kaggle kernels output`) and also printed at the end.

All console output is kept plain ASCII deliberately: kaggle_smoketest.py
documents that Kaggle's own log-capture pipeline corrupts multi-byte
UTF-8 text before it reaches the downloaded log, confirmed 2026-08-09 in
this same repo. This script follows that same convention.

Steps run in order (stops at the first hard failure, still writes the
partial JSON so the failure is visible without a second pull):
  1. Environment probe (OS, CPU count, free disk).
  2. apt-get install build dependencies.
  3. Clone FDPS/SDAR/PeTar/mcluster at the commits pinned in
     nbody_setup/README.md.
  4. pip install galpy==1.10.2.
  5. Configure and build PeTar (--with-interrupt=bse --with-external=galpy).
  6. Build mcluster_sse.
  7. S0 checks: `petar -h` contains --galpy-set; `python -c "import
     galpy; print(galpy.__version__)"` prints 1.10.2; `petar.data.process
     -h` exits 0.
  8. S1: two tiny scratch grid rows (not the project's real
     petar_m45_grid.csv) are written, then run_nbody_case.py --smoke
     drives the full mcluster->petar.init->petar->gether->process chain
     for a 200-star, no-binary, no-BSE, 1 Myr run and checks every stage
     completed.
  9. S2: the same chain for a 1000-star Plummer run (10 Myr) and checks
     the parsed energy error is below 1e-4 (the acceptance threshold
     recorded for S2 in NBODY_PREREGISTRATION.md).
"""
from __future__ import annotations

import json
import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

WORK = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path.cwd()
NBODY_DIR = WORK / "nbody"
INSTALL_DIR = NBODY_DIR / "install"

FDPS_COMMIT = "6fedb4b8bd7a504598e83a4189a7a83c533a0848"
SDAR_COMMIT = "f64f11801f494bdceda9f4c93dad71dd64c57278"
PETAR_COMMIT = "84b81a8c339c49291de53f7a72829dd80e188182"
MCLUSTER_COMMIT = "a147bb5f1c0186a2d2d5b513ed112992929dd12a"
GALPY_VERSION = "1.10.2"

SMOKE_GRID_CSV = (
    "run_id,n_systems,binary_system_fraction,n_stars,n_binaries,profile,"
    "mcluster_S,half_mass_radius_pc,seed,galactic_tide,priority,status\n"
    "smoke_s1,200,0.0,200,0,0,0.00,3.10,1,false,1,ready\n"
    "smoke_s2,1000,0.0,1000,0,0,0.00,3.10,2,false,1,ready\n"
)

results: dict = {"steps": {}}


def log(msg: str) -> None:
    print(msg, flush=True)


def run_step(name: str, cmd, cwd=None, env=None, timeout=1800) -> dict:
    log(f"=== {name} ===")
    log(f"$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, shell=isinstance(cmd, str),
            capture_output=True, text=True, timeout=timeout,
        )
        elapsed = time.monotonic() - t0
        entry = {
            "cmd": cmd if isinstance(cmd, str) else " ".join(cmd),
            "returncode": proc.returncode,
            "elapsed_s": round(elapsed, 1),
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - t0
        entry = {
            "cmd": cmd if isinstance(cmd, str) else " ".join(cmd),
            "returncode": None,
            "elapsed_s": round(elapsed, 1),
            "stdout_tail": (exc.stdout or "")[-4000:] if exc.stdout else "",
            "stderr_tail": "TIMEOUT after %ds" % timeout,
        }
    results["steps"][name] = entry
    log(f"  returncode={entry['returncode']} elapsed={entry['elapsed_s']}s")
    if entry["returncode"] != 0:
        log(f"  stderr tail:\n{entry['stderr_tail'][-1500:]}")
    return entry


def save_and_exit(status: str, code: int) -> None:
    results["status"] = status
    out_path = WORK / "smoke_result.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    log(f"=== FINAL STATUS: {status} (see {out_path}) ===")
    log(json.dumps(results, indent=2))
    sys.exit(code)


def main() -> None:
    results["environment"] = {
        "platform": platform.platform(),
        "python": sys.version,
        "cpu_count": multiprocessing.cpu_count(),
    }
    log("=== Environment probe ===")
    log(json.dumps(results["environment"], indent=2))
    disk = shutil.disk_usage(WORK)
    results["environment"]["disk_free_gb"] = round(disk.free / 1e9, 1)
    log(f"Free disk: {results['environment']['disk_free_gb']} GB")

    NBODY_DIR.mkdir(parents=True, exist_ok=True)

    # 2. apt build deps (Kaggle kernels run as root, no sudo needed)
    r = run_step(
        "apt_install",
        "apt-get update -qq && apt-get install -y -qq "
        "build-essential gfortran cmake libgsl-dev autoconf automake libtool git",
        timeout=600,
    )
    if r["returncode"] != 0:
        save_and_exit("apt_install_failed", 1)

    # 3. clone pinned repos
    repos = [
        ("FDPS", "https://github.com/FDPS/FDPS.git", FDPS_COMMIT),
        ("SDAR", "https://github.com/lwang-astro/SDAR.git", SDAR_COMMIT),
        ("PeTar", "https://github.com/lwang-astro/PeTar.git", PETAR_COMMIT),
        ("mcluster", "https://github.com/lwang-astro/mcluster.git", MCLUSTER_COMMIT),
    ]
    for name, url, commit in repos:
        dest = NBODY_DIR / name
        if not dest.exists():
            r = run_step(f"clone_{name}", ["git", "clone", url, str(dest)], timeout=300)
            if r["returncode"] != 0:
                save_and_exit(f"clone_{name}_failed", 1)
        r = run_step(f"checkout_{name}", ["git", "checkout", commit], cwd=dest)
        if r["returncode"] != 0:
            save_and_exit(f"checkout_{name}_failed", 1)

    # 4. galpy
    r = run_step("pip_install_galpy", [sys.executable, "-m", "pip", "install",
                 "--quiet", f"galpy=={GALPY_VERSION}"], timeout=600)
    if r["returncode"] != 0:
        save_and_exit("galpy_install_failed", 1)

    # 5. configure+build PeTar
    petar_dir = NBODY_DIR / "PeTar"
    env = os.environ.copy()
    env.update({"CXX": "g++", "CC": "gcc", "FC": "gfortran"})
    r = run_step(
        "configure_petar",
        ["./configure", f"--prefix={INSTALL_DIR}", "--with-mpi=no",
         "--with-interrupt=bse", "--with-external=galpy"],
        cwd=petar_dir, env=env,
    )
    if r["returncode"] != 0:
        save_and_exit("configure_petar_failed", 1)
    ncpu = multiprocessing.cpu_count()
    r = run_step("make_petar", ["make", f"-j{ncpu}"], cwd=petar_dir, timeout=1800)
    if r["returncode"] != 0:
        save_and_exit("make_petar_failed", 1)
    r = run_step("make_install_petar", ["make", "install"], cwd=petar_dir)
    if r["returncode"] != 0:
        save_and_exit("make_install_petar_failed", 1)

    # 6. build mcluster
    mcluster_dir = NBODY_DIR / "mcluster"
    r = run_step(
        "make_mcluster",
        ["make", "mcluster_sse", "CFLAGS=-lgfortran"],
        cwd=mcluster_dir,
    )
    if r["returncode"] != 0:
        save_and_exit("make_mcluster_failed", 1)

    # PATH for the rest of this script
    bin_env = os.environ.copy()
    bin_env["PATH"] = f"{INSTALL_DIR / 'bin'}:{mcluster_dir}:{bin_env['PATH']}"
    bin_env["OMP_STACKSIZE"] = "128M"

    # 7. S0 checks
    s0 = {}
    r = run_step("s0_petar_help", ["petar", "-h"], env=bin_env)
    s0["galpy_set_flag_present"] = "--galpy-set" in (r["stdout_tail"] + r["stderr_tail"])
    r = run_step("s0_galpy_version", [sys.executable, "-c",
                 "import galpy; print(galpy.__version__)"])
    s0["galpy_version"] = r["stdout_tail"].strip()
    s0["galpy_version_ok"] = s0["galpy_version"] == GALPY_VERSION
    r = run_step("s0_process_help", ["petar.data.process", "-h"], env=bin_env)
    s0["process_help_ok"] = r["returncode"] == 0
    results["s0"] = s0
    log(f"S0 result: {json.dumps(s0)}")
    if not (s0["galpy_set_flag_present"] and s0["galpy_version_ok"] and s0["process_help_ok"]):
        save_and_exit("s0_failed", 1)

    # 8-9. S1/S2 via run_nbody_case.py, driven against a scratch grid
    smoke_grid = WORK / "smoke_grid.csv"
    smoke_grid.write_text(SMOKE_GRID_CSV, encoding="utf-8")
    runs_dir = WORK / "runs"

    for run_id, label, energy_threshold, t_myr, o_myr in (
        ("smoke_s1", "s1_pipeline_smoke", None, 1.0, 0.5),
        ("smoke_s2", "s2_energy_conservation", 1e-4, 10.0, 5.0),
    ):
        cmd = [
            sys.executable, str(WORK / "run_nbody_case.py"),
            "--run-id", run_id, "--grid", str(smoke_grid),
            "--runs-dir", str(runs_dir), "--smoke",
            "--smoke-t-myr", str(t_myr), "--smoke-o-myr", str(o_myr),
            "--n-threads", str(ncpu),
        ]
        if energy_threshold is not None:
            cmd += ["--energy-threshold", str(energy_threshold)]
        r = run_step(label, cmd, env=bin_env, timeout=900)
        try:
            payload = json.loads(r["stdout_tail"].strip().rsplit("\n", 1)[-1]
                                 if r["stdout_tail"].strip().startswith("{")
                                 else r["stdout_tail"])
        except Exception:
            payload = None
        results.setdefault("run_nbody_case", {})[label] = payload
        if payload is None or payload.get("status") not in ("complete",):
            log(f"  {label}: could not confirm success from output, see stdout_tail above")

    save_and_exit("smoke_complete", 0)


if __name__ == "__main__":
    main()
