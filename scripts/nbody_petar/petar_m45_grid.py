#!/usr/bin/env python
"""Validate the M45 PeTar screening grid and render reproducible commands.

功能：讀 petar_m45_grid.csv 一列，驗證欄位一致性（n_binaries/n_stars 算術、
S 範圍、half_mass_radius 為正…），並把該列組裝成 mcluster_sse -> petar.init
-> petar -> petar.data.gether -> petar.data.process 的完整 shell 指令序列。

方法：純字串／字典操作，不執行任何外部程式（執行交給 run_nbody_case.py，
2026-09 之後新增）。指令模板對照 docs/planning/PETAR_M45_EXPERIMENT.md 手動
核對過，這裡是唯一產生指令字串的地方，避免兩處各自組一份、彼此漂移。

已知未完成（2026-09 審視 H3）：`galactic_tide` 欄位目前只被解析成布林，
render_commands() 完全沒有讀它——設 true 也會生成跟 false 完全相同的指令，
銀河潮汐（--galpy-set MWPotential2014、petar.init -c 銀心座標）尚未實作。
在真正接上 m45_orbit_init.py 算出的座標之前，validate_grid() 直接拒絕
galactic_tide=true 的列，避免使用者以為潮汐已經生效。
"""
from __future__ import annotations

import argparse
import csv
import json
import shlex
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent.parent  # 2026-08-26 檔案搬到 scripts/nbody_petar/，往上三層才是 repo 根目錄


def load_grid(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("PeTar grid is empty")
    return rows


def parse_row(raw: dict) -> dict:
    row = dict(raw)
    for key in ("n_systems", "n_stars", "n_binaries", "profile", "seed", "priority"):
        row[key] = int(row[key])
    for key in ("binary_system_fraction", "mcluster_S", "half_mass_radius_pc"):
        row[key] = float(row[key])
    row["galactic_tide"] = row["galactic_tide"].strip().lower() == "true"
    return row


def validate_grid(rows: list[dict]) -> dict:
    parsed = [parse_row(row) for row in rows]
    errors = []
    run_ids = [row["run_id"] for row in parsed]
    if len(set(run_ids)) != len(run_ids):
        errors.append("run_id values are not unique")

    for row in parsed:
        expected_binaries = round(
            row["n_systems"] * row["binary_system_fraction"]
        )
        expected_stars = row["n_systems"] + row["n_binaries"]
        if row["n_binaries"] != expected_binaries:
            errors.append(
                f"{row['run_id']}: n_binaries={row['n_binaries']}, "
                f"expected {expected_binaries}"
            )
        if row["n_stars"] != expected_stars:
            errors.append(
                f"{row['run_id']}: n_stars={row['n_stars']}, "
                f"expected {expected_stars}"
            )
        if not 0.0 <= row["binary_system_fraction"] <= 1.0:
            errors.append(f"{row['run_id']}: binary fraction is outside [0, 1]")
        if row["profile"] not in (0, 2):
            errors.append(f"{row['run_id']}: unsupported screening profile")
        if row["profile"] == 2 and not 0.0 <= row["mcluster_S"] < 0.5:
            errors.append(f"{row['run_id']}: profile 2 requires 0 <= S < 0.5")
        if row["half_mass_radius_pc"] <= 0:
            errors.append(f"{row['run_id']}: half-mass radius must be positive")
        if row["galactic_tide"]:
            # H3（2026-09 審視）：render_commands() 還沒實作潮汐（見檔頭
            # 說明），設 true 目前只會安靜地生成無潮汐指令。在銀河軌道
            # 初始化（m45_orbit_init.py）與 --galpy-set 佈線完成前，寧可
            # 拒絕也不要讓人誤以為潮汐已經生效。
            errors.append(
                f"{row['run_id']}: galactic_tide=true 尚未實作，"
                "render_commands() 不會加入 --galpy-set；"
                "改回 false，或先完成 m45_orbit_init.py 的整合"
            )

    summary = {
        "status": "pass" if not errors else "fail",
        "grid_path": str(Path(rows[0].get("_grid_path", "petar_m45_grid.csv"))),
        "n_runs": len(parsed),
        "n_priority_1": sum(row["priority"] == 1 for row in parsed),
        "n_priority_2": sum(row["priority"] == 2 for row in parsed),
        "seeds": sorted({row["seed"] for row in parsed}),
        "half_mass_radius_pc": sorted({row["half_mass_radius_pc"] for row in parsed}),
        "binary_system_fraction": sorted(
            {row["binary_system_fraction"] for row in parsed}
        ),
        "mcluster_S": sorted({row["mcluster_S"] for row in parsed}),
        "profiles": sorted({row["profile"] for row in parsed}),
        "errors": errors,
    }
    if errors:
        raise ValueError("; ".join(errors))
    return summary


def render_commands(row: dict) -> str:
    row = parse_row(row)
    run_id = shlex.quote(row["run_id"])
    command = [
        "mcluster_sse",
        "-N", str(row["n_stars"]),
        "-B", str(row["n_binaries"]),
        "-P", str(row["profile"]),
        "-R", f"{row['half_mass_radius_pc']:.2f}",
        "-f", "1",
        "-C", "5",
        "-u", "1",
        "-s", str(row["seed"]),
        "-Z", "0.02",
        "-o", row["run_id"],
    ]
    if row["profile"] == 2:
        command[9:9] = ["-S", f"{row['mcluster_S']:.2f}"]
    mcluster = " ".join(shlex.quote(part) for part in command)
    # -t / -c 在 petar.init 這裡是必要旗標，不是只有 galactic_tide=true
    # 的列才要加（2026-09 在 GCP VM 上實測踩到）：petar 二進位檔一旦用
    # `--with-external=galpy` 編譯，不管執行時有沒有真的傳
    # `--galpy-set`，都預期輸入檔的表頭多帶 6 個質心位置/速度偏移值、
    # 每行粒子資料多帶一欄 pot_ext——這是編譯期選項決定的檔案格式，
    # 不是執行期選項。沒加 `-t` 會在讀檔第一步就崩潰
    # （"FPSoft Data reading fails! requiring data number is 6, only
    # obtain 1"）。這裡先固定給 0 偏移（不影響動力學，`--galpy-set`
    # 沒開就沒有外部力作用在任何人身上）；`galactic_tide=true` 真正需要
    # 銀河潮汐時，`-c` 要換成 `m45_orbit_init.py` 算出的座標、且
    # `petar` 那行要加 `--galpy-set MWPotential2014`——這兩處目前
    # 都還沒做（`validate_grid()` 也還在擋 `galactic_tide=true` 的列，
    # 見 H3），先讓不含潮汐的列在檔案格式上正確可跑。
    return "\n".join(
        [
            f"mkdir -p runs/{run_id}",
            f"cd runs/{run_id}",
            f"{mcluster} > mcluster.log",
            "petar.init -s bse -v kms2pcmyr -t -c 0,0,0,0,0,0 -f input <MCLUSTER_OUTPUT>",
            "export OMP_STACKSIZE=128M",
            "export OMP_NUM_THREADS=8",
            (
                f"petar -u 1 -b {row['n_binaries']} --bse-metallicity 0.02 "
                "--stellar-evolution 1 --detect-interrupt 1 "
                "-t 125.0 -o 5.0 input > petar.log 2>&1"
            ),
            "petar.data.gether data",
            "petar.data.process -i bse -t galpy data.snap.lst",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=HERE / "petar_m45_grid.csv")
    parser.add_argument("--run-id")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    rows = load_grid(args.grid)
    for row in rows:
        row["_grid_path"] = str(args.grid)
    summary = validate_grid(rows)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(summary, indent=2))

    if args.run_id:
        selected = [row for row in rows if row["run_id"] == args.run_id]
        if not selected:
            parser.error(f"unknown --run-id {args.run_id!r}")
        print("\n# Review <MCLUSTER_OUTPUT> before continuing\n")
        print(render_commands(selected[0]))


if __name__ == "__main__":
    main()
