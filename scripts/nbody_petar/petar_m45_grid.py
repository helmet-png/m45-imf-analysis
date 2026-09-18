#!/usr/bin/env python
"""Validate the M45 PeTar screening grid and render reproducible commands.

功能：讀 petar_m45_grid.csv 一列，驗證欄位一致性（n_binaries/n_stars 算術、
S 範圍、half_mass_radius 為正…），並把該列組裝成 mcluster_sse -> petar.init
-> petar -> petar.data.gether -> petar.data.process 的完整 shell 指令序列。

方法：純字串／字典操作，不執行任何外部程式（執行交給 run_nbody_case.py，
2026-09 之後新增）。指令模板對照 docs/planning/PETAR_M45_EXPERIMENT.md 手動
核對過，這裡是唯一產生指令字串的地方，避免兩處各自組一份、彼此漂移。

2026-09（H3 修復）：`galactic_tide=true` 的列會讀
`results/m45_orbit_init.json`（`m45_orbit_init.py` 算出、往返自洽誤差
1.34e-6 的 125 Myr 前銀心座標），把 `petar.init -c` 換成真實六維座標、
並在 `petar` 那行加 `--galpy-set MWPotential2014`；`galactic_tide=false`
維持 `-c 0,0,0,0,0,0`、不加 `--galpy-set`（供 Method A 的 A5 潮汐對照組
使用）。

2026-09（H5 修復）：mcluster 不再固定 `-f 1`（Kroupa 2001 內建常數），
改用 `-f 2` 兩段自訂冪律，斷點固定在 0.5 M☉（跟前向模型/傳統法同一個
斷點，才能跨方法比較），`imf_alpha_low`／`imf_alpha_high` 兩欄位決定
兩段斜率。**斜率符號**：直接讀 mcluster `main.c`（pin 版 a147bb5）
`case 'a'` 與 `mfunc==5`（Marks & Kroupa 2012）區塊確認——`-a` 疊代填入
的 `alpha[]` 是程式內部慣例（`generate_m2()` 用 `subint(..., alpha[i]+1.)`
積分 dN/dm ∝ m^alpha[i]），Kroupa 標準值以**負數**傳入（`alpha[0]=-1.3`
對應物理慣例 dN/dm ∝ m^-1.3）；這裡 `imf_alpha_low`／`imf_alpha_high`
欄位維持本專案一貫的**正數**慣例（跟 `step5_imf.py` 的 α 同號），
`render_commands()` 內部轉負號才傳給 `-a`。

H12（2026-09-05，參數標準化，查證 mcluster 官方 README 確認）：

- `mcluster_S` is mcluster's ``-S`` flag: "degree of mass segregation
  (0.0-1.0, 0.0=no segregation)", not a fractal dimension. mcluster's
  fractal dimension is a *different* flag, ``-D`` (1.6-3.0, 3.0=no
  fractalization), which this grid does not expose as a column and
  never passes -- do not confuse the two when reading mcluster's own
  docs, the flag letters are easy to mix up.
  2026-09-18 correction (Codex review): ``-S`` and Converse & Stahler
  (2010) Table 1's segregation parameter beta (0.5 +/- 0.3) both
  *control* mass segregation, but they are not the same physical
  quantity -- C&S Sec 2.1 Eq. (24) defines beta through a Gaussian
  mass/energy-rank-ordering width parameter (sigma_E = -N_tot*ln(beta)/2),
  while mcluster's ``-S``/``-P 2`` implements the Subr/PLUMIX
  segregation model (see mcluster's own README). No numeric mapping
  between the two has been verified; treat ``mcluster_S`` as its own
  independent parameter, not a stand-in for beta, until someone
  actually compares the two models' output mass-segregation profiles.
- ``profile`` (mcluster's ``-P``): 0=Plummer, 2=Subr et al. (2007)
  mass-segregated profile (this grid never uses 1=King or 3=EFF/Nuker).
  This is a *different* modeling choice from the King/Woolley/Wilson
  dynamical-equilibrium models compared in
  ``scripts/diagnostics/limepy_multimass.py`` (route D, LIMITATIONS.md
  B5) -- the two are unrelated axes answering different questions
  (initial density-profile shape for an N-body IC vs. present-day
  equilibrium-model fit to observed density), not something that needs
  to agree with each other.
- Virial ratio (mcluster's ``-Q``) was never set, so every run silently
  used whatever mcluster's compiled-in default is -- mcluster's own
  README documents no default value for ``-Q``. C&S's initial state is
  explicitly virial equilibrium (Q=0.5), so ``render_commands()`` now
  passes ``-Q 0.50`` explicitly instead of relying on an unverified
  default.
"""
from __future__ import annotations

import argparse
import csv
import json
import shlex
from pathlib import Path


HERE = Path(__file__).resolve().parent.parent.parent  # 2026-08-26 檔案搬到 scripts/nbody_petar/，往上三層才是 repo 根目錄
ORBIT_JSON = HERE / "results" / "m45_orbit_init.json"  # m45_orbit_init.py 的輸出，galactic_tide=true 時讀這裡的 -c 座標


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
    for key in (
        "binary_system_fraction",
        "mcluster_S",
        "half_mass_radius_pc",
        "imf_alpha_low",
        "imf_alpha_high",
    ):
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
        # H5：兩段冪律斜率的合理範圍（正數慣例，見檔頭說明）——寬鬆檢查，
        # 只擋明顯打錯（例如把 -2.3 直接填進去、或忘記換號）。
        if not 0.0 < row["imf_alpha_low"] < 4.0:
            errors.append(f"{row['run_id']}: imf_alpha_low 超出合理範圍 (0, 4)")
        if not 0.0 < row["imf_alpha_high"] < 5.0:
            errors.append(f"{row['run_id']}: imf_alpha_high 超出合理範圍 (0, 5)")
        if row["galactic_tide"] and not ORBIT_JSON.exists():
            # H3（2026-09 修復）：真跑之前 results/m45_orbit_init.json 必須
            # 已經存在（`python m45_orbit_init.py` 產生），render_commands()
            # 才讀得到真實座標——不存在就直接擋，不要安靜地退回原點。
            errors.append(
                f"{row['run_id']}: galactic_tide=true 但找不到 "
                f"{ORBIT_JSON}，請先跑 m45_orbit_init.py"
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
    # H5：mcluster 官方 main.c（pin 版 a147bb5）`case 'f'` 只是設定
    # mfunc；真正吃斜率/斷點的是 `mfunc==2` 分支，用重複的 `-a`／`-m`
    # 疊代填 alpha[]/mlim[] 陣列，且強制 mn = an+1（讀原始碼
    # `if (an >= mn) an = mn - 1; mn = an + 1;` 這段確認），所以兩段
    # 冪律要給恰好 3 個 `-m`（兩段的三個邊界）、2 個 `-a`（兩段斜率）。
    # 斷點固定 0.5 M☉、上限固定 150 M☉（沿用 mcluster 預設 upper_IMF_limit，
    # M45 實際最亮的星遠低於這個質量，不會被截斷）。
    mcluster_alpha_low = -row["imf_alpha_low"]
    mcluster_alpha_high = -row["imf_alpha_high"]
    command = [
        "mcluster_sse",
        "-N", str(row["n_stars"]),
        "-B", str(row["n_binaries"]),
        "-P", str(row["profile"]),
        # 2026-09-18：跟 -S 同一個 review 一起修——訓練網格存 4 位小數
        # （如 4.1641），`.2f` 會截掉一半精度，改跟 alpha/S 統一用 `.4f`。
        "-R", f"{row['half_mass_radius_pc']:.4f}",
        # H12: mcluster's README documents no default for -Q, so leaving
        # it unset means every run silently used whatever the compiled
        # binary's own internal default happens to be. C&S's initial
        # state is explicitly virial equilibrium (Q=0.5), so pass it
        # explicitly instead of relying on an unverified default.
        "-Q", "0.50",
        "-f", "2",
        "-m", "0.08", "-m", "0.5", "-m", "150",
        "-a", f"{mcluster_alpha_low:.4f}", "-a", f"{mcluster_alpha_high:.4f}",
        "-C", "5",
        "-u", "1",
        "-s", str(row["seed"]),
        "-Z", "0.02",
        "-o", row["run_id"],
    ]
    if row["profile"] == 2:
        # -S is mass segregation degree (not a fractal dimension --
        # see module docstring), only meaningful for the Subr et al.
        # (2007) mass-segregated profile (-P 2).
        #
        # 2026-09-18 修正（Codex review）：`.2f` 會把 0.4984 這類貼近
        # profile 2 上界（validate_grid() 要求 S<0.5）的值四捨五入成
        # "0.50"，實際傳給 mcluster_sse 的就是不合法的 S=0.50，悄悄
        # 蓋掉網格記錄的真實值。跟 alpha（142-152 行）用同樣的 `.4f`
        # 精度，網格本身存的就是 4 位小數，不會再有這個邊界問題。用
        # 相對結尾的索引（而不是寫死的絕對位置）插入，前面加了 -Q 之後
        # 陣列長度會變，固定索引會插到錯的位置。
        command[-2:-2] = ["-S", f"{row['mcluster_S']:.4f}"]
    mcluster = " ".join(shlex.quote(part) for part in command)

    # -t / -c 在 petar.init 這裡是必要旗標，不是只有 galactic_tide=true
    # 的列才要加（2026-09 在 GCP VM 上實測踩到）：petar 二進位檔一旦用
    # `--with-external=galpy` 編譯，不管執行時有沒有真的傳
    # `--galpy-set`，都預期輸入檔的表頭多帶 6 個質心位置/速度偏移值、
    # 每行粒子資料多帶一欄 pot_ext——這是編譯期選項決定的檔案格式，
    # 不是執行期選項。沒加 `-t` 會在讀檔第一步就崩潰
    # （"FPSoft Data reading fails! requiring data number is 6, only
    # obtain 1"）。
    #
    # H3（2026-09 修復）：galactic_tide=true 的列讀
    # results/m45_orbit_init.json（m45_orbit_init.py 算出、往返自洽誤差
    # 1.34e-6 的 125 Myr 前銀心座標）當真正的 -c 偏移，並在 petar 那行
    # 加 --galpy-set MWPotential2014；false 的列維持 0 偏移、不開
    # --galpy-set（A5 潮汐對照組要用）。validate_grid() 已確保
    # galactic_tide=true 時這個檔案存在，這裡不再重複檢查。
    if row["galactic_tide"]:
        orbit = json.loads(ORBIT_JSON.read_text(encoding="utf-8"))
        c_flag = orbit["petar_init_c_flag"]  # "-c x,y,z,vx,vy,vz"（已含 -c）
        galpy_set = " --galpy-set MWPotential2014"
    else:
        c_flag = "-c 0,0,0,0,0,0"
        galpy_set = ""

    return "\n".join(
        [
            f"mkdir -p runs/{run_id}",
            f"cd runs/{run_id}",
            f"{mcluster} > mcluster.log",
            f"petar.init -s bse -v kms2pcmyr -t {c_flag} -f input <MCLUSTER_OUTPUT>",
            "export OMP_STACKSIZE=128M",
            "export OMP_NUM_THREADS=8",
            (
                f"petar -u 1 -b {row['n_binaries']} --bse-metallicity 0.02 "
                "--stellar-evolution 1 --detect-interrupt 1"
                f"{galpy_set} "
                "-t 125.0 -o 5.0 input > petar.log 2>&1"
            ),
            "petar.data.gether data",
            "petar.data.process -i bse -t galpy data.snap.lst",
        ]
    )


def run_self_test() -> dict:
    """迴歸測試（2026-09-18 Codex review）：`-S` 格式化精度不夠會把
    貼近 profile 2 上界（S<0.5）的值四捨五入成不合法的 "0.50"，悄悄
    蓋掉網格記錄的真實值。對兩份網格檔（校準用小網格 + 430 列正式
    訓練網格，後者存在才測）逐列做 render→parse round trip：從渲染出
    的指令字串正則抓回 `-S` 後面的數字，跟 CSV 的原始值比對，且確認
    真的小於 0.5（不是被夾到剛好等於邊界）。
    """
    import re

    grid_paths = [HERE / "petar_m45_grid.csv", HERE / "petar_m45_training_grid.csv"]
    checked = 0
    mismatches = []
    for grid_path in grid_paths:
        if not grid_path.exists():
            continue
        for raw in load_grid(grid_path):
            row = parse_row(raw)
            mcluster_line = render_commands(raw).split("\n")[2]

            r_match = re.search(r"-R\s+([0-9.]+)", mcluster_line)
            if r_match is None or abs(float(r_match.group(1)) - row["half_mass_radius_pc"]) > 1e-9:
                mismatches.append({
                    "run_id": row["run_id"], "field": "half_mass_radius_pc",
                    "grid_value": row["half_mass_radius_pc"],
                    "rendered_value": r_match.group(1) if r_match else None,
                })

            if row["profile"] != 2:
                continue
            m = re.search(r"-S\s+([0-9.]+)", mcluster_line)
            if m is None:
                mismatches.append({"run_id": row["run_id"], "reason": "no -S flag rendered"})
                continue
            parsed_s = float(m.group(1))
            checked += 1
            if abs(parsed_s - row["mcluster_S"]) > 1e-9 or not (parsed_s < 0.5):
                mismatches.append({
                    "run_id": row["run_id"], "field": "mcluster_S",
                    "grid_value": row["mcluster_S"],
                    "rendered_value": parsed_s,
                })

    summary = {
        "status": "synthetic_validation_only",
        "n_profile2_rows_checked": checked,
        "mismatches": mismatches,
    }
    if checked == 0:
        summary["status"] = "skipped_no_grid_files"
    elif mismatches:
        raise AssertionError(f"petar_m45_grid -S round-trip failed: {mismatches}")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=Path, default=HERE / "petar_m45_grid.csv")
    parser.add_argument("--run-id")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

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
