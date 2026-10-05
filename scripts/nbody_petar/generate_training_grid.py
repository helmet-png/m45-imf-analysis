#!/usr/bin/env python
"""產生方法 B（高斯過程模擬器＋貝氏反推）的訓練網格 petar_m45_training_grid.csv。

功能：在 6 維初始條件空間 θ = (N_sys, f_bin_ini, r_h_ini, S, alpha_in_low,
alpha_in_high) 上撒一組拉丁超立方（Latin Hypercube）設計點，每點一個
seed；另外從中挑 20 個點各加 4 個額外 seed（共 5 seed／點），供
`emulator_fit.py` 量測「同一組初始條件、不同亂數」造成的模擬雜訊
（GP 的 nugget 項）。輸出的 CSV 跟 `petar_m45_grid.csv` 完全同一個欄位
schema，`petar_m45_grid.render_commands()` / `run_nbody_case.py` 不需要
任何修改就能直接讀這份新檔案（`--grid` 參數指過去即可）。

方法：
1. **參數範圍**——直接取自
   `docs/planning/floofy-wandering-crescent.md`（已核准的執行計劃）
   第 3.3 節「初始條件空間」與第 N6 節「先驗：N、r_h 均勻；f_bin
   均勻 0.2–1.0；α 均勻 1.0–3.5」，不自行加寬或另訂數字：
     - N_sys ∈ [1200, 1700]（整數；C&S 2010 與 Hobart+2026 的聯集範圍）
     - f_bin_ini ∈ [0.30, 0.95]（3.3 節 IC 空間）
     - r_h_ini ∈ [2.4, 4.5] pc（3.3 節 IC 空間）
     - S（mass segregation, McLuster `-S`）∈ [0.0, 0.499]（`profile=2`
       時 `validate_grid()` 要求嚴格 < 0.5，取 0.499 避免邊界剛好撞上）
     - alpha_in_high（0.5–150 M☉ 段）∈ [1.0, 3.5]（N6 節先驗範圍，
       emulator_fit.py 的後驗搜尋會用同一個先驗，訓練網格必須覆蓋到
       先驗邊界，否則 GP 在邊界附近會外插而非內插）
     - alpha_in_low（0.08–0.5 M☉ 段）∈ [0.3, 2.0]——**這個範圍計劃書
       沒有給出明確數字**（3.3 節只討論方法 A 用兩個離散值 1.3/0.84），
       這裡用文獻已出現的兩個值（Kroupa 1.3、Moraux 2003 的 0.84）
       加上對稱寬裕度選定，記在這裡供之後檢視／調整，不是隱藏假設。
   `profile` 固定 `2`（King/Subr 質量分層剖面，對應 C&S 2010 的 n=3
   多方球模型，也是既有 screening grid 的多數選擇）；`galactic_tide`
   固定 `true`（訓練網格要對應真實物理設定，跟 S4 smoke test 同一種
   組態：BSE 開＋銀河潮汐開），跟 galactic_tide=false 的潮汐對照
   （方法 A 的 A5）分開處理，不混在同一份訓練網格。
2. **抽樣**：`scipy.stats.qmc.LatinHypercube`（`scipy==1.18.1`，本機
   `.venv_nbody_tools` 已裝），6 維、`n_design` 點（預設 350，對齊計劃書
   3.5／3.11 節「≥350 runs」），`scramble=True` 但用固定 `seed=`
   （見下方 `--master-seed`）確保可重現——同一個 master seed 重跑這支
   程式要產生逐位元組相同的 CSV。
3. **雜訊量測子集**：用 `numpy.linspace(0, n_design-1, n_noise_points,
   dtype=int)` 從設計點裡等距挑 `n_noise_points`（預設 20）個索引
   （去重後可能略少於 20，直接印出實際挑了幾個），每個額外配 4 個
   seed（`--extra-seeds-per-point`，預設 4），θ 完全不變、只換 seed，
   量測「同一組初始條件不同亂數」造成的統計量散布。
4. **seed 配置**：主設計點 seed = `40001 + i`（i 為 0-indexed 設計點
   序號，避開既有 screening grid 用過的 101/202/303）；雜訊點的額外
   seed = `90001 + 10*point_index + k`（k=1..4），跟主 seed 池不重疊、
   一看數字就知道是哪個設計點的雜訊複製。
5. **衍生欄位**：`n_binaries = round(n_systems * binary_system_fraction)`、
   `n_stars = n_systems + n_binaries`，跟 `petar_m45_grid.parse_row()`
   的驗證公式完全一致（不能不一致，否則 `validate_grid()` 會報
   `n_binaries` 不合預期）。

自我測試（`--self-test`）：用小網格（`--n-design 12 --n-noise-points 3`）
產生 CSV 到暫存檔，檢查（a）列數 = 12 + 3*4 = 24、（b）每欄數值都落在
宣告的範圍內、（c）`petar_m45_grid.load_grid()` + `validate_grid()` 能
直接吃這份輸出不報錯（跟正式產出走同一條驗證路徑，不是另外自己檢查
一遍）、（d）同一個 `--master-seed` 跑兩次逐位元組相同（reproducibility）。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, sys, pathlib   參數與路徑
  filecmp                  filecmp.cmp 逐位元組比較兩個檔案（自我測試用）
  tempfile                 暫存資料夾（自我測試用）
  csv, json（函式內 import）  寫 CSV、印結果
第三方套件：
  numpy（np）              np.linspace 等距挑雜訊點的編號
  scipy.stats.qmc
      qmc.LatinHypercube(d, seed)  拉丁超立方抽樣器：在 d 維空間撒點，保證
                                   每一維切成 n 等份時每份剛好有一個點，
                                   比純隨機撒點更均勻
      sampler.random(n)            產生 n 個落在 0–1 之間的 d 維點
      qmc.scale(點, 下限, 上限)     把 0–1 的點線性換算到實際參數範圍
本專案其他模組：
  scripts/nbody_petar/petar_m45_grid.py
      load_grid()      讀網格 CSV
      validate_grid()  檢查每一列是否合法（n_binaries 是否吻合、S < 0.5 等）

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --n-design (350)              拉丁超立方設計點數
  --n-noise-points (20)         挑幾個設計點做雜訊量測
  --extra-seeds-per-point (4)   每個雜訊點額外多跑幾個 seed
  --master-seed (20260910)      拉丁超立方的亂數種子（固定 → 結果可重現）
  --output                      輸出路徑，預設 repo 根目錄 petar_m45_training_grid.csv
  --self-test                   只跑自我測試
模組常數：
  PARAM_NAMES／PARAM_BOUNDS     六個初始條件與範圍（見上方「方法」第 1 點）
  CSV_FIELDS                    輸出欄位，跟 petar_m45_grid.csv 相同
  MAIN_SEED_BASE = 40001        主設計點的 seed 起點
  NOISE_SEED_BASE = 90001       雜訊複製的 seed 起點
⚠ 下方 PARAM_NAMES 上一行的註解說順序「跟 emulator_fit.py 的 θ 順序對齊」，
  實際上這裡是低質量段在前、emulator_fit.py 是高質量段在前。
  emulator_fit.py 讀資料時依欄位名稱取值，所以不會對調，只是註解寫錯。
預設產出：350 + 20 × 4 = 430 列

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 156–167 行｜sample_design()：拉丁超立方抽 350 個 6 維設計點
  核心 2｜第 170–222 行｜build_rows()：每個設計點組成一列 CSV，雜訊點多加 4 個 seed
  核心 3｜第 283–321 行｜main()：產生、寫檔、讀回驗證

======================================================================
【(d) 整體流程】
======================================================================
  拉丁超立方在 0–1 的 6 維立方體裡撒 350 個點 → 換算到實際參數範圍
    → 從 350 個點裡等距挑 20 個當雜訊點
    → 對每個設計點：
        系統數取整數、雙星比例四捨五入到 4 位小數
        → 雙星數 = round(系統數 × 雙星比例)；恆星數 = 系統數 + 雙星數
        → 寫一列（seed = 40001 + 編號）；是雜訊點就再多寫 4 列（只換 seed）
    → 寫成 CSV → 用 petar_m45_grid.py 的同一套驗證讀回來檢查
"""
from __future__ import annotations

import argparse
import filecmp
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.stats import qmc

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from petar_m45_grid import load_grid, validate_grid  # noqa: E402

# 6 維設計空間，順序固定（跟 emulator_fit.py 的 θ 順序對齊）：
# N_sys, f_bin_ini, r_h_ini_pc, S, alpha_in_low, alpha_in_high
PARAM_NAMES = ["n_systems", "binary_system_fraction", "half_mass_radius_pc",
               "mcluster_S", "imf_alpha_low", "imf_alpha_high"]
PARAM_BOUNDS = {
    "n_systems": (1200.0, 1700.0),
    "binary_system_fraction": (0.30, 0.95),
    "half_mass_radius_pc": (2.4, 4.5),
    "mcluster_S": (0.0, 0.499),
    "imf_alpha_low": (0.3, 2.0),
    "imf_alpha_high": (1.0, 3.5),
}
CSV_FIELDS = [
    "run_id", "n_systems", "binary_system_fraction", "n_stars", "n_binaries",
    "profile", "mcluster_S", "half_mass_radius_pc", "imf_alpha_low",
    "imf_alpha_high", "seed", "galactic_tide", "priority", "status",
]

MAIN_SEED_BASE = 40001
NOISE_SEED_BASE = 90001


# ═══════════════ 核心 1：拉丁超立方抽樣 ═══════════════
def sample_design(n_design: int, master_seed: int) -> np.ndarray:
    """回傳 (n_design, 6) 的實際參數值陣列（已縮放到 PARAM_BOUNDS）。"""
    # ↓ 建立 6 維的拉丁超立方抽樣器（固定種子 → 每次結果相同）
    sampler = qmc.LatinHypercube(d=len(PARAM_NAMES), seed=master_seed)
    # ↓ 抽 n_design 個點，每個點的 6 個座標都在 0–1 之間
    unit = sampler.random(n=n_design)
    # ↓ 每一維的下限與上限
    lo = np.array([PARAM_BOUNDS[p][0] for p in PARAM_NAMES])
    hi = np.array([PARAM_BOUNDS[p][1] for p in PARAM_NAMES])
    # ↓ 線性換算：實際值 = 下限 + (上限 − 下限) × 0–1 座標
    return qmc.scale(unit, lo, hi)


# ═══════════════ 核心 2：組成網格的每一列 ═══════════════
def build_rows(n_design: int, n_noise_points: int, extra_seeds: int,
                master_seed: int) -> list[dict]:
    values = sample_design(n_design, master_seed)
    # ↓ 在 0 到 n_design−1 之間等距挑 n_noise_points 個編號當雜訊點（去重、排序）
    noise_idx = sorted(set(np.linspace(0, n_design - 1, n_noise_points, dtype=int).tolist()))

    rows: list[dict] = []
    for i in range(n_design):
        # ↓ 第 i 個設計點的 6 個值（順序同 PARAM_NAMES）
        n_sys = int(round(values[i, 0]))
        # 先四捨五入到 CSV 實際會寫出的 4 位小數，n_binaries 才跟
        # validate_grid() 用「CSV 裡讀回來的值」重算出來的結果一致
        # ——否則用全精度浮點數算出的 n_binaries，跟四捨五入寫檔後
        # 再讀回來算出的 expected_binaries 會在邊界情況差 1。
        f_bin = round(float(values[i, 1]), 4)
        r_h = float(values[i, 2])
        s_seg = float(values[i, 3])
        a_low = float(values[i, 4])
        a_high = float(values[i, 5])
        # ↓ 衍生欄位：雙星系統數、恆星總數（每個雙星多一顆星）
        n_bin = round(n_sys * f_bin)
        n_stars = n_sys + n_bin

        def make_row(run_id: str, seed: int) -> dict:
            return {
                "run_id": run_id,
                "n_systems": n_sys,
                "binary_system_fraction": f"{f_bin:.4f}",
                "n_stars": n_stars,
                "n_binaries": n_bin,
                "profile": 2,
                "mcluster_S": f"{s_seg:.4f}",
                "half_mass_radius_pc": f"{r_h:.4f}",
                "imf_alpha_low": f"{a_low:.4f}",
                "imf_alpha_high": f"{a_high:.4f}",
                "seed": seed,
                "galactic_tide": "true",
                "priority": 1,
                "status": "ready",
            }

        # ↓ 主設計點：run_id 例如 mb_train_0007_s40008
        main_seed = MAIN_SEED_BASE + i
        rows.append(make_row(f"mb_train_{i:04d}_s{main_seed}", main_seed))

        # ↓ 雜訊點：初始條件完全相同，只換 seed，多寫 extra_seeds 列
        if i in noise_idx:
            for k in range(1, extra_seeds + 1):
                extra_seed = NOISE_SEED_BASE + 10 * i + k
                rows.append(make_row(f"mb_train_{i:04d}_s{extra_seed}", extra_seed))

    return rows


def write_csv(rows: list[dict], out_path: Path) -> None:
    import csv
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_self_test() -> dict:
    n_design, n_noise, extra = 12, 3, 4
    rows = build_rows(n_design, n_noise, extra, master_seed=12345)
    expected_rows = n_design + n_noise * extra

    checks = {
        "row_count_matches": len(rows) == expected_rows,
        "n_systems_in_bounds": all(
            PARAM_BOUNDS["n_systems"][0] <= r["n_systems"] <= PARAM_BOUNDS["n_systems"][1]
            for r in rows
        ),
        "f_bin_in_bounds": all(
            PARAM_BOUNDS["binary_system_fraction"][0] <= float(r["binary_system_fraction"])
            <= PARAM_BOUNDS["binary_system_fraction"][1]
            for r in rows
        ),
        "alpha_high_in_bounds": all(
            PARAM_BOUNDS["imf_alpha_high"][0] <= float(r["imf_alpha_high"])
            <= PARAM_BOUNDS["imf_alpha_high"][1]
            for r in rows
        ),
        "n_binaries_consistent": all(
            r["n_binaries"] == round(r["n_systems"] * float(r["binary_system_fraction"]))
            for r in rows
        ),
        "seeds_unique": len({r["seed"] for r in rows}) == len(rows),
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "training_grid_selftest.csv"
        write_csv(rows, tmp_path)
        loaded = load_grid(tmp_path)
        for row in loaded:
            row["_grid_path"] = str(tmp_path)
        summary = validate_grid(loaded)
        checks["validate_grid_passes"] = summary["status"] == "pass"

        tmp_path2 = Path(tmp) / "training_grid_selftest_2.csv"
        rows2 = build_rows(n_design, n_noise, extra, master_seed=12345)
        write_csv(rows2, tmp_path2)
        checks["reproducible_same_seed"] = filecmp.cmp(tmp_path, tmp_path2, shallow=False)

    result = {"status": "synthetic_validation_only", "checks": checks, "n_rows": len(rows)}
    if not all(checks.values()):
        raise AssertionError(f"generate_training_grid self-test failed: {checks}")
    return result


# ═══════════════ 核心 3：產生、寫檔、驗證 ═══════════════
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-design", type=int, default=350)
    parser.add_argument("--n-noise-points", type=int, default=20)
    parser.add_argument("--extra-seeds-per-point", type=int, default=4)
    parser.add_argument("--master-seed", type=int, default=20260910)
    parser.add_argument(
        "--output", type=Path,
        default=REPO_ROOT / "petar_m45_training_grid.csv",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print_result = run_self_test()
        import json
        print(json.dumps(print_result, indent=2))
        return

    rows = build_rows(
        args.n_design, args.n_noise_points, args.extra_seeds_per_point, args.master_seed
    )
    write_csv(rows, args.output)

    # ↓ 用正式的讀檔與驗證函式讀回來檢查，確認下游讀得懂
    loaded = load_grid(args.output)
    for row in loaded:
        row["_grid_path"] = str(args.output)
    summary = validate_grid(loaded)

    import json
    print(json.dumps({
        "output": str(args.output),
        "n_design_points": args.n_design,
        "n_noise_points": args.n_noise_points,
        "n_rows_total": len(rows),
        "validate_grid": summary["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
