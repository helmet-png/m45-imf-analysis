#!/usr/bin/env python
"""執行 petar_m45_grid.csv 一列的完整外部程式鏈，並記錄計時與能量守恆。

功能：把 `petar_m45_grid.render_commands()` 產生的指令字串**真正跑起來**
（`mcluster_sse` -> `petar.init` -> `petar` -> `petar.data.gether` ->
`petar.data.process`），這是 smoke test（S1-S4，見
`docs/planning/NBODY_PREREGISTRATION.md`）與之後所有正式網格 run 的
共同執行體。這支程式**不重新組裝指令**——組裝邏輯只在
`petar_m45_grid.render_commands()` 一處，這裡只負責「照著跑、跑的過程
記什麼」。

方法：
1. 讀 `petar_m45_grid.csv` 指定的 `--run-id` 一列，呼叫
   `render_commands()` 取得指令序列。該序列裡的 `<MCLUSTER_OUTPUT>`
   佔位字串（`petar_m45_grid.py` 留給人工確認用）由這支程式**程式化
   解析**成 `{run_id}.dat.10`——本次直接讀 mcluster 原始碼
   （`main.c` 的 `output5()`，對應 `-C 5` 輸出格式）確認：`-C 5` 寫出
   的 `.dat.10` 固定是 7 欄（mass, x, y, z, vx, vy, vz），跟
   `petar.init`（`tools/initdata.sh`）預期的輸入格式逐欄相符，不需要
   人工介入。同一次確認也發現 `.fort.12`（mcluster_sse 算出的 SSE
   預先演化狀態）**完全沒有被這條鏈使用**——`petar.init -s bse` 一律
   把每顆星初始化成 type=1（ZAMS）、epoch=0，實際的恆星演化狀態由
   `petar --stellar-evolution 1` 在模擬過程中重新算，不是讀
   `.fort.12`。這不是這條指令鏈的 bug，是 PeTar 官方範例腳本
   （`sample/star_cluster_bse_galpy.sh`）本來就這樣用，這裡記下來
   避免以後有人以為要另外接上 `.fort.12`。
2. 依序 `subprocess.run` 每一步，工作目錄固定在 `runs/<run_id>/`。每步
   完成才進行下一步；任何一步 returncode 非零就停止並保留目前為止的
   log，不清理現場（方便事後診斷）。
3. **階段檔** `runs/<run_id>/stage.json` 記錄哪些步驟已完成，重跑時
   跳過已完成的步驟——長 run 中途被中斷（機器重開、手動中止）時不用
   從頭來過。
4. **計時**：每步驟的 wall time、`OMP_NUM_THREADS`、CPU 資訊寫進
   `runs/<run_id>/timing.json`，這是 smoke test S3/S4 要量的核心產出。
5. **能量／角動量守恆檢查**：解析 `petar.log` 最後一行 `Physic:` 狀態
   輸出的 `Error/Total` 欄位（PeTar README 逐字核對過的欄位順序：
   `Error/Total, Error, Error_cum, Total, Kinetic, Potential, Modify,
   Modify_group, Modify_single, Error_PP, Error_PP_cum`）當累積相對
   能量誤差，以及最後一行 `Angular Momentum:` 的 `|L|err_cum` 除以
   `|L|` 當累積相對角動量誤差。超過門檻（`--energy-threshold`，預設
   1e-3，S2 驗收用 1e-4 需另外傳）就把 `status` 標成
   `energy_check_failed`，但不刪除已產生的資料——是否可用留給人判斷。
6. `--smoke`：覆寫網格列的 `-t`（模擬終止時間）與 `-o`（快照間隔），
   並關閉恆星演化與銀河潮汐（供 S1/S2 使用，那兩關本來就不需要這兩項
   物理）。
7. `--dry-run`：只印出將要執行的指令（含 `<MCLUSTER_OUTPUT>` 已解析），
   不建目錄、不執行，供人工審閱或接進 `cloud_queue.py` 之類的派工系統
   前先確認指令正確。

自我測試（`--self-test`）：用 `--dry-run` 對照
`docs/planning/PETAR_M45_EXPERIMENT.md` 手動核對過的指令模板逐字比對
（`petar_m45_grid.py` 的 `render_commands()` 本身已有這個對照，這裡
額外驗證 `<MCLUSTER_OUTPUT>` 確實被換成 `m45_ref_s101.dat.10`，以及
stage/timing JSON 的結構在乾跑模式下也完整產生，不需要真的裝 PeTar
就能驗證程式邏輯本身沒有錯）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # scripts/nbody_petar/
REPO_ROOT = HERE.parent.parent

sys.path.insert(0, str(HERE))
from petar_m45_grid import load_grid, parse_row, render_commands  # noqa: E402


# render_commands() 產出的每一行 shell 指令，用這個順序拆成獨立步驟，
# 每步驟一個 subprocess.run。跳過 mkdir/cd（這裡改用 Python 的
# cwd/mkdir 處理，不靠 shell 狀態）與 export（改用 subprocess 的 env
# 參數傳遞）。
STEP_NAMES = ["mcluster", "petar_init", "petar", "gether", "process"]


def _resolve_mcluster_output(run_id: str) -> str:
    """`<MCLUSTER_OUTPUT>` 佔位字串要換成的實際檔名。

    見檔頭說明：`-C 5`（NBODY6++GPU 格式）下 mcluster_sse 用 `-o` 指定
    的名字加 `.dat.10` 後綴寫出 7 欄（mass,x,y,z,vx,vy,vz）資料檔，
    直接對照 mcluster `main.c` 的 `output5()` 函式確認過。
    """
    return f"{run_id}.dat.10"


def parse_rendered_commands(rendered: str, run_id: str) -> list[str]:
    """把 render_commands() 的多行輸出拆成可個別執行的指令字串列表。

    跳過 mkdir/cd/export 那幾行（由這支程式的 Python 邏輯處理，不假設
    有一個持續存在的 shell session），保留 5 個真正要執行外部程式的行，
    並把 `<MCLUSTER_OUTPUT>` 換成解析後的實際檔名。
    """
    lines = [ln for ln in rendered.splitlines() if ln.strip()]
    commands = []
    mcluster_output = _resolve_mcluster_output(run_id)
    for ln in lines:
        if ln.startswith("mkdir ") or ln.startswith("cd ") or ln.startswith("export "):
            continue
        ln = ln.replace("<MCLUSTER_OUTPUT>", mcluster_output)
        # 去掉檔案重導向（> xxx.log 2>&1），這支程式自己接管 stdout/stderr
        # 的收集方式（subprocess.run capture_output=True），不靠 shell
        # 重導向，這樣才能在不支援 `2>&1` 語法的環境（例如某些 Windows
        # subprocess 呼叫方式）也正常運作。
        ln = re.sub(r"\s*>\s*\S+(\s+2>&1)?\s*$", "", ln)
        commands.append(ln)
    if len(commands) != len(STEP_NAMES):
        raise ValueError(
            f"預期 {len(STEP_NAMES)} 個指令步驟，實際解析出 {len(commands)} 個；"
            "render_commands() 的輸出格式可能變了，這支程式要跟著更新"
        )
    return commands


def apply_petar_binary_override(command: str, petar_bin: str) -> str:
    """把 petar 那一步的執行檔換成 `petar_bin`（預設 "petar"，不做任何事）。

    2026-09-11 跟協作者對過：PeTar `make install` 會把通用符號連結
    `petar` 指向**最後一次編譯**的變體——同一台機器先裝一般版、後來
    又跑 `add_galpy_support_linux.sh` 加裝 galpy 支援後，`petar` 這個
    裸名字現在指向 galpy 版本；但這個符號連結會隨著任何人下次重跑
    `setup_linux_nbody.sh`（不含 galpy）而悄悄改回沒有 galpy 的版本。
    本專案訓練網格 100% 需要 galpy（`galactic_tide=true`），長時間
    無人值守批次跑到一半符號連結被換掉會造成難以追查的失敗，所以
    派工到共用機器（例如 senior24）時**一律用完整檔名**
    （如 `petar.omp.avx512.bse.galpy`），不依賴裸的 `petar`；本機／
    專用 VM（符號連結不會被別人動）維持預設空字串、沿用裸 `petar`
    不需要額外指定。
    """
    if not petar_bin or petar_bin == "petar":
        return command
    if command.split()[0] != "petar":
        return command
    return petar_bin + command[len("petar"):]


def apply_smoke_overrides(command: str, t_myr: float, o_myr: float) -> str:
    """--smoke 模式：覆寫 -t/-o，並關掉恆星演化與銀河潮汐相關旗標。

    只對 `petar ` 開頭的那一行動手——mcluster_sse 跟 petar.init 的旗標
    不含終止時間，不用改。
    """
    if not command.startswith("petar ") and " petar " not in command:
        return command
    if command.split()[0] != "petar":
        return command
    parts = shlex.split(command)
    out = []
    skip_next = False
    for i, tok in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if tok == "-t":
            out.extend(["-t", f"{t_myr:.4f}"])
            skip_next = True
            continue
        if tok == "-o":
            out.extend(["-o", f"{o_myr:.4f}"])
            skip_next = True
            continue
        if tok == "--stellar-evolution":
            out.extend(["--stellar-evolution", "0"])
            skip_next = True
            continue
        if tok == "--galpy-set":
            skip_next = True
            continue
        out.append(tok)
    return " ".join(shlex.quote(p) if " " in p else p for p in out)


def parse_energy_log(petar_log: Path) -> dict:
    """解析 petar.log 最後一筆 Physic:／Angular Momentum: 狀態輸出。

    欄位順序對照 PeTar README「Output columns」一節逐字核對：
    `Energy: Error/Total Error Error_cum Total Kinetic Potential Modify
    Modify_group Modify_single Error_PP Error_PP_cum`；
    `Angular Momentum: |L|err: .. |L|err_cum: .. L: x y z |L|: ..`。
    """
    if not petar_log.exists():
        return {"status": "log_not_found"}
    text = petar_log.read_text(encoding="utf-8", errors="replace")

    physic_lines = [ln for ln in text.splitlines() if ln.strip().startswith("Physic:")]
    am_lines = [ln for ln in text.splitlines() if ln.strip().startswith("Angular Momentum:")]

    result: dict = {"status": "no_energy_lines_found"}
    if physic_lines:
        fields = physic_lines[-1].split()
        # fields[0] == "Physic:"，fields[1] 是 Error/Total
        try:
            result["energy_error_relative"] = float(fields[1])
            result["status"] = "parsed"
        except (IndexError, ValueError):
            result["status"] = "physic_line_parse_failed"

    if am_lines:
        m = re.search(
            r"\|L\|err_cum:\s*([\-0-9.eE+]+).*\|L\|:\s*([\-0-9.eE+]+)",
            am_lines[-1],
        )
        if m:
            l_err_cum, l_total = float(m.group(1)), float(m.group(2))
            result["angular_momentum_error_relative"] = (
                abs(l_err_cum / l_total) if l_total != 0 else float("inf")
            )
    return result


def run_case(
    run_id: str,
    grid_path: Path,
    runs_dir: Path,
    energy_threshold: float,
    smoke: bool,
    smoke_t_myr: float,
    smoke_o_myr: float,
    dry_run: bool,
    n_threads: int,
    petar_bin: str = "petar",
) -> dict:
    rows = load_grid(grid_path)
    matches = [r for r in rows if r["run_id"] == run_id]
    if not matches:
        raise ValueError(f"grid 裡找不到 run_id={run_id!r}")
    row = matches[0]

    rendered = render_commands(row)
    commands = parse_rendered_commands(rendered, run_id)
    # 順序重要：smoke override 用 `command.split()[0] != "petar"` 判斷
    # 哪一步是 petar，一定要在 petar_bin override 把裸 "petar" 換成完整
    # 檔名（如 petar.omp.avx512.bse.galpy）**之前**做，否則 smoke 模式
    # 會找不到要改的那一步、悄悄不生效（2026-09-11 加 petar_bin 支援時
    # 差點漏掉這個順序依賴）。
    if smoke:
        commands = [apply_smoke_overrides(c, smoke_t_myr, smoke_o_myr) for c in commands]
    commands = [apply_petar_binary_override(c, petar_bin) for c in commands]

    if dry_run:
        return {
            "status": "dry_run",
            "run_id": run_id,
            "commands": commands,
        }

    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    stage_path = run_dir / "stage.json"
    timing_path = run_dir / "timing.json"

    stage = json.loads(stage_path.read_text(encoding="utf-8")) if stage_path.exists() else {}
    timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {
        "cpu": platform.processor() or platform.machine(),
        "platform": platform.platform(),
        "n_threads": n_threads,
        "steps": {},
    }

    env = os.environ.copy()
    env["OMP_STACKSIZE"] = "128M"
    env["OMP_NUM_THREADS"] = str(n_threads)

    log_files = {
        "mcluster": "mcluster.log",
        "petar_init": "petar_init.log",
        "petar": "petar.log",
        "gether": "gether.log",
        "process": "process.log",
    }

    for name, command in zip(STEP_NAMES, commands):
        if stage.get(name) == "done":
            print(f"[{run_id}] {name}：已完成，跳過", flush=True)
            continue
        print(f"[{run_id}] {name}：{command}", flush=True)
        log_path = run_dir / log_files[name]
        t0 = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log_handle:
            proc = subprocess.run(
                shlex.split(command),
                cwd=run_dir,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        elapsed = time.monotonic() - t0
        timing["steps"][name] = elapsed
        timing_path.write_text(json.dumps(timing, indent=2) + "\n", encoding="utf-8")

        if proc.returncode != 0:
            stage[name] = f"failed(rc={proc.returncode})"
            stage_path.write_text(json.dumps(stage, indent=2) + "\n", encoding="utf-8")
            return {
                "status": "step_failed",
                "run_id": run_id,
                "failed_step": name,
                "returncode": proc.returncode,
                "log": str(log_path),
                "timing": timing,
            }
        stage[name] = "done"
        stage_path.write_text(json.dumps(stage, indent=2) + "\n", encoding="utf-8")

    energy = parse_energy_log(run_dir / "petar.log")
    energy_ok = (
        energy.get("status") == "parsed"
        and abs(energy.get("energy_error_relative", float("inf"))) < energy_threshold
    )

    summary = {
        "status": "complete" if energy_ok else "energy_check_failed",
        "run_id": run_id,
        "smoke": smoke,
        "energy_threshold": energy_threshold,
        "energy": energy,
        "timing": timing,
        "run_dir": str(run_dir),
    }
    (run_dir / "result.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def run_self_test() -> dict:
    """乾跑模式核對 `<MCLUSTER_OUTPUT>` 解析與指令拆解，不需要真的裝 PeTar。"""
    grid_path = REPO_ROOT / "petar_m45_grid.csv"
    rows = load_grid(grid_path)
    row = next(r for r in rows if r["run_id"] == "m45_ref_s101")
    rendered = render_commands(row)
    commands = parse_rendered_commands(rendered, "m45_ref_s101")

    checks = {
        "five_steps_parsed": len(commands) == 5,
        "mcluster_output_resolved": "m45_ref_s101.dat.10" in commands[1],
        "no_placeholder_left": all("<MCLUSTER_OUTPUT>" not in c for c in commands),
        "mcluster_first": commands[0].startswith("mcluster_sse"),
        "petar_init_second": commands[1].startswith("petar.init"),
        "petar_third": commands[2].startswith("petar "),
        "gether_fourth": commands[3].startswith("petar.data.gether"),
        "process_fifth": commands[4].startswith("petar.data.process"),
    }

    smoke_petar = apply_smoke_overrides(commands[2], 1.0, 0.5)
    checks["smoke_override_changes_t"] = "-t 1.0000" in smoke_petar
    checks["smoke_override_disables_stellar_evolution"] = "--stellar-evolution 0" in smoke_petar

    # 能量 log 解析：用官方 README 逐字引用的範例行測試。
    sample_log = (
        "Energy:       Error/Total           Error       Error_cum           Total"
        "         Kinetic       Potential          Modify    Modify_group   Modify_single"
        "        Error_PP    Error_PP_cum\n"
        "Physic:      1.883442e-05       -644.6969       -644.6969   -3.422972e+07"
        "    1.846359e+07   -5.269331e+07        1841.216               0     0.008989855"
        "    -8.67599e-06    -8.67599e-06\n"
        "Angular Momentum:  |L|err: 187484.2  |L|err_cum: 187484.2  L: -1.17383e+07"
        "   -1.20975e+07    -1.267862e+09  |L|: 1.267974e+09\n"
    )
    tmp_log = Path("_run_nbody_case_selftest_petar.log")
    tmp_log.write_text(sample_log, encoding="utf-8")
    try:
        energy = parse_energy_log(tmp_log)
    finally:
        tmp_log.unlink(missing_ok=True)
    checks["energy_error_parsed_correctly"] = abs(
        energy.get("energy_error_relative", -1) - 1.883442e-05
    ) < 1e-12
    checks["angular_momentum_ratio_correct"] = abs(
        energy.get("angular_momentum_error_relative", -1) - (187484.2 / 1.267974e9)
    ) < 1e-9

    summary = {
        "status": "synthetic_validation_only",
        "commands": commands,
        "smoke_petar_command": smoke_petar,
        "energy_parse_result": energy,
        "checks": checks,
    }
    if not all(checks.values()):
        raise AssertionError(f"run_nbody_case self-test failed: {checks}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_grid.csv")
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--energy-threshold", type=float, default=1e-3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--smoke-t-myr", type=float, default=1.0)
    parser.add_argument("--smoke-o-myr", type=float, default=0.5)
    parser.add_argument("--n-threads", type=int, default=os.cpu_count() or 1)
    parser.add_argument(
        "--petar-bin", default="petar",
        help="petar 執行檔名稱；共用機器上 `petar` 符號連結可能被別人的"
             "後續建置動作改指向不同變體，長跑批次建議傳完整檔名"
             "（例如 petar.omp.avx512.bse.galpy），見 "
             "apply_petar_binary_override() 的說明",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        summary = run_self_test()
        print(json.dumps(summary, indent=2))
        return

    if not args.run_id:
        parser.error("--run-id is required unless --self-test is used")

    summary = run_case(
        args.run_id,
        args.grid,
        args.runs_dir,
        args.energy_threshold,
        args.smoke,
        args.smoke_t_myr,
        args.smoke_o_myr,
        args.dry_run,
        args.n_threads,
        args.petar_bin,
    )
    print(json.dumps(summary, indent=2))
    if summary["status"] not in ("complete", "dry_run"):
        sys.exit(1)


if __name__ == "__main__":
    main()
