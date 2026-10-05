#!/usr/bin/env python
"""把一份 cmd_members.csv 格式的星表（真實或 `observe_snapshot.py` 產的
假資料）壓成一組固定長度的統計量，供方法 A（IC 概似加權）與方法 B
（模擬器訓練資料）共用。

功能：真實觀測與模擬觀測**必須用同一支程式**算這組統計量，否則比較的
兩邊不是同一個量——這正是這支程式存在的理由。`--from-real` 對
`data/cmd_members.csv` 跑一次，凍結成 `results/nbody_observed_targets.json`
（要進版控、hash 寫進預註冊文件，之後不能悄悄換算法）；`--from-mock`
對 `observe_snapshot.py` 的輸出跑同一套邏輯。

方法：統計量分四組，全部用**傳統法**估計器（`pipeline/step5_imf.py`
的 `assign_masses`／`mle_powerlaw`，`pipeline/step4_binaries.py` 的
`flag_cmd_offset`），不是前向模型——原因是前向模型（`fit_real.py`）
一次擬合要 40,000 顆合成星、多階網格精修，一次要跑到數小時，N-body
方法 A 就要跑 ~85 次、方法 B 要跑 ~350+ 次，乘上去完全不可行。傳統法
換算成 O(1) 的內插+一維數值優化，每個半徑切片幾毫秒。**這是刻意的
取捨，不是疏忽**：`results/RESULTS_LOG.md` 的 `radial_final_reruns`
四個帶誤差棒的 α(<r)（2.0644/2.3889/2.4244/2.3844）是前向模型算的，
跟這支程式算出來的傳統法數字**不是同一個估計器**，不能直接拿來對照
當「這支程式對不對」的驗收標準——只能檢查方向與量級合理（見自我測試）。

1. **N(<r)**：投影半徑 <= r 的星數，4 個半徑（依 `--distance-pc` 換算
   1°/2°/3°/全孔徑對應的 pc，跟舊有 `radial_r1/r2/r3/rall` 的角度定義
   一致，只是換成物理半徑當統一單位）。
2. **α(<r)**：`assign_masses()` 把每顆星的 G 星等（+顏色一致性檢查）
   換成質量，`mle_powerlaw()` 在 `--mass-min/--mass-max`（預設
   0.5-2.5，跟 headline 定義一致）內做冪律 MLE。
3. **f_bin(r)**：全域 + 4 個半徑環帶，`flag_cmd_offset()` 判雙星
   （門檻 `--cmd-offset-threshold`，預設 0.375 mag，跟
   `config.toml` 的 `cmd_offset_threshold` 一致）後取平均。
4. **r_h,2D**：投影半質量半徑（依星數，不是質量——傳統法把每顆星當
   單星處理，沒有独立的質量權重意義；用星數中位數半徑近似）。
5. **逐質量段徑向數密度**：3 個質量段（0.3-0.5／0.5-1.0／1.0-2.5）
   × 4 個環帶，數密度 = 環帶內星數 / 環帶面積（pc²）。

`--from-real` 需要 `source_id` 欄位才能排除
`step5_imf.CONFIRMED_NON_MEMBER_IDS`（H8，跟 `fit_real.py` 一致）；
`--from-mock` 的星表沒有真正的 source_id，跳過這一步（合成資料本來
就不含這兩顆已知非成員）。

自我測試（`--self-test`）：對 `data/cmd_members.csv` 跑一次，檢查
(a) 四個半徑的樣本數單調遞增（半徑越大涵蓋越多星，這是幾何上必然
成立的，不是統計巧合）；(b) 算出的 α 都落在 [1, 4] 這個寬鬆但有意義
的量級範圍內；(c) f_bin 落在 [0, 1]；(d) 找不到 `data/cmd_members.csv`
時優雅地回報缺檔，不是模糊的 traceback。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, json, math, sys, pathlib   參數、寫 JSON、數學函數、路徑
第三方套件：
  numpy（np）   np.isin（排除非成員）、np.sort（求半數半徑）、np.mean 等
本專案其他模組：
  pipeline/isochrones.py     load_grid()、isochrone_at()：取等時線
  pipeline/step3_age.py      COL_*（欄位名）、_Ext（消光係數盒子）
  pipeline/step4_binaries.py flag_cmd_offset()：比單星主序亮 0.375 星等以上就判為雙星
  pipeline/step5_imf.py      assign_masses()（星等查質量）、mle_powerlaw()（冪律擬合）、
                             CONFIRMED_NON_MEMBER_IDS（非成員名單）
  pipeline/table_compat.py   Table：簡易表格
  observe_snapshot.py        DEFAULT_*（距離、消光、年齡、金屬量、等時線檔）、
                             EXT_COEFF（消光係數）——兩支程式共用同一組設定

======================================================================
【(b) 用到的參數與意義】
======================================================================
  --from-real <CSV>   真實星表（data/cmd_members.csv）；會排除已知非成員；
                      預設輸出 results/nbody_observed_targets.json
  --from-mock <CSV>   observe_snapshot.py 產的假星表；
                      預設輸出跟輸入同名、副檔名換成 .stats.json
                      ⚠ emulator_fit.py 讀的是 <run 資料夾>/observed.stats.json，
                        所以假星表要命名為該 run 資料夾裡的 observed.csv 才接得上
  （兩者必須二選一）
  --distance-pc (135.48)、--av (0.386)、--logage (8.026)、--mh (−0.022)
                      等時線與距離設定（預設同 observe_snapshot.py）
  --aperture-pc (11.68)  最外圈的半徑
  --mass-min (0.5)、--mass-max (2.5)  冪律擬合的質量範圍
  --cmd-offset-threshold (0.375)       雙星判定門檻
  --isochrone-grid、--output、--self-test
26 個統計量（emulator_fit.py 用的就是這 26 個）：
  n_within × 4      1°、2°、3°、全孔徑內的星數
  alpha_within × 4  同樣四個半徑內的 α
  fbin_within × 4   同樣四個半徑內的雙星比例
  fbin_global × 1   全部星的雙星比例
  half_number_radius_2d_pc × 1   一半的星落在多大半徑內
  radial_mass_density_pc2 × 12   3 個質量段 × 4 個環帶的面數密度
  （另外輸出 global_fit 等資訊，但 emulator_fit.py 沒有用）

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 149–160 行｜radius_bin_edges_pc()、_projected_radius_pc()：半徑定義
  核心 2｜第 180–265 行｜compute_stats()：算出全部統計量
  核心 3｜第 314–365 行｜main()：讀星表、算統計量、寫 JSON

======================================================================
【(d) 整體流程】
======================================================================
  讀星表（真實或假）→（真實才做）排除非成員
    → 每顆星的投影半徑：假星表直接讀 projected_radius_pc 欄；
      真實星表用 RA/Dec 中位數當中心算角距，再換成 pc
    → 取等時線、算距離模數
    → 對 4 個半徑：星數、查質量後擬合 α、CMD 偏移判雙星的比例
    → 全部星：α、雙星比例；半數半徑
    → 3 個質量段 × 4 個環帶：環帶內星數 ÷ 環帶面積
    → 寫成 JSON
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent  # scripts/nbody_petar/
REPO_ROOT = HERE.parent.parent

sys.path.insert(0, str(REPO_ROOT))
from pipeline import isochrones as isomod  # noqa: E402
from pipeline.step3_age import COL_BP, COL_G, COL_RP, _Ext  # noqa: E402
from pipeline.step4_binaries import flag_cmd_offset  # noqa: E402
from pipeline.step5_imf import (  # noqa: E402
    CONFIRMED_NON_MEMBER_IDS,
    assign_masses,
    mle_powerlaw,
)
from pipeline.table_compat import Table  # noqa: E402

sys.path.insert(0, str(HERE))
from observe_snapshot import (  # noqa: E402
    DEFAULT_AV,
    DEFAULT_DISTANCE_PC,
    DEFAULT_ISOCHRONE_GRID,
    DEFAULT_LOGAGE,
    DEFAULT_MH,
    EXT_COEFF,
)

MASS_BINS_MSUN = [(0.3, 0.5), (0.5, 1.0), (1.0, 2.5)]
DEFAULT_MASS_MIN = 0.5
DEFAULT_MASS_MAX = 2.5
DEFAULT_CMD_OFFSET_THRESHOLD = 0.375


# ═══════════════ 核心 1：半徑的定義 ═══════════════
def radius_bin_edges_pc(distance_pc: float, aperture_pc: float) -> list[float]:
    """1 度/2 度/3 度/全孔徑，換算成物理半徑（pc），跟 radial_r1/r2/r3/rall
    的角度定義一致（tan(角度)*距離），全孔徑用修正後的實際孔徑而不是
    再算一次 5 度。"""
    # ↓ 角度換成物理半徑：tan(角度) × 距離。135.48 pc 時 1° ≈ 2.36 pc
    return [
        math.tan(math.radians(1.0)) * distance_pc,
        math.tan(math.radians(2.0)) * distance_pc,
        math.tan(math.radians(3.0)) * distance_pc,
        aperture_pc,
    ]


def _projected_radius_pc(t, distance_pc: float) -> np.ndarray:
    """優先讀既有的 projected_radius_pc 欄位（observe_snapshot.py 的輸出），
    否則從 ra/dec 用大圓角距（樣本中位中心）換算——跟 fit_real.py 的
    --radius-range 算法一致，這樣真實資料算出來的半徑跟模擬端可比。
    """
    if "projected_radius_pc" in t.colnames:
        return np.asarray(t["projected_radius_pc"], float)
    ra = np.radians(np.asarray(t["ra"], float))
    dec = np.radians(np.asarray(t["dec"], float))
    ra0 = np.radians(float(np.median(np.degrees(ra))))
    dec0 = np.radians(float(np.median(np.degrees(dec))))
    cosr = (np.sin(dec0) * np.sin(dec)
            + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0))
    rdeg = np.degrees(np.arccos(np.clip(cosr, -1, 1)))
    return np.tan(np.radians(rdeg)) * distance_pc


# ═══════════════ 核心 2：算統計量 ═══════════════
def compute_stats(
    t,
    distance_pc: float,
    av: float,
    logage: float,
    mh: float,
    aperture_pc: float,
    mass_min: float,
    mass_max: float,
    cmd_offset_threshold: float,
    iso_grid,
    exclude_non_members: bool,
) -> dict:
    # ↓ 真實星表：排除 step5_imf.py 名單裡的已確認非成員
    if exclude_non_members and "source_id" in t.colnames:
        sid = np.asarray(t["source_id"], np.int64)
        excluded = np.isin(sid, np.array(list(CONFIRMED_NON_MEMBER_IDS), np.int64))
        t = t[~excluded]

    color = np.asarray(t["bp_rp"], float)
    mag = np.asarray(t["phot_g_mean_mag"], float)
    radius_pc = _projected_radius_pc(t, distance_pc)

    # ↓ 距離模數、消光係數、等時線（查質量與判雙星都用這條）
    dist_mod = 5.0 * math.log10(distance_pc) - 5.0
    ext = _Ext(EXT_COEFF["G"], EXT_COEFF["BP"], EXT_COEFF["RP"])
    iso = isomod.isochrone_at(iso_grid, logage, mh)

    edges = radius_bin_edges_pc(distance_pc, aperture_pc)
    labels = ["r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture"]

    n_within: dict[str, int] = {}
    alpha_within: dict[str, dict] = {}
    fbin_within: dict[str, float] = {}
    for label, edge in zip(labels, edges):
        # ↓ 這個半徑內的星
        sel = radius_pc <= edge
        n_within[label] = int(sel.sum())
        # ↓ 傳統法：星等查質量（含顏色檢查）→ 0.5–2.5 M☉ 內擬合 α
        masses = assign_masses(mag[sel], iso, dist_mod, av, ext, obs_color=color[sel])
        alpha_within[label] = mle_powerlaw(masses, mass_min, mass_max)
        # ↓ 比單星主序亮超過 0.375 星等的判為雙星，雙星比例 = 被判為雙星的比例
        is_bin = flag_cmd_offset(color[sel], mag[sel], iso, dist_mod, av, ext,
                                 cmd_offset_threshold)
        valid = np.isfinite(color[sel]) & np.isfinite(mag[sel])
        fbin_within[label] = float(np.mean(is_bin[valid])) if valid.any() else float("nan")

    all_masses = assign_masses(mag, iso, dist_mod, av, ext, obs_color=color)
    global_fit = mle_powerlaw(all_masses, mass_min, mass_max)
    is_bin_all = flag_cmd_offset(color, mag, iso, dist_mod, av, ext, cmd_offset_threshold)
    valid_all = np.isfinite(color) & np.isfinite(mag)
    fbin_global = float(np.mean(is_bin_all[valid_all])) if valid_all.any() else float("nan")

    # ↓ 半數半徑：所有半徑排序後取正中間那一個
    sorted_r = np.sort(radius_pc)
    r_half = float(sorted_r[len(sorted_r) // 2]) if len(sorted_r) else float("nan")

    density = {}
    ring_edges = [0.0] + edges
    for m_lo, m_hi in MASS_BINS_MSUN:
        in_mass = (all_masses >= m_lo) & (all_masses < m_hi)
        for i, label in enumerate(labels):
            lo, hi = ring_edges[i], ring_edges[i + 1]
            # ↓ 這個質量段、這個環帶裡的星；環帶面積 = π(外半徑² − 內半徑²)
            in_ring = (radius_pc > lo) & (radius_pc <= hi) & in_mass
            area_pc2 = math.pi * (hi**2 - lo**2)
            density[f"m{m_lo:g}_{m_hi:g}_{label}"] = (
                float(np.sum(in_ring) / area_pc2) if area_pc2 > 0 else float("nan")
            )

    return {
        "n_input": int(len(t)),
        "n_within": n_within,
        "alpha_within": alpha_within,
        "fbin_within": fbin_within,
        "fbin_global": fbin_global,
        "global_fit": global_fit,
        "half_number_radius_2d_pc": r_half,
        "radial_mass_density_pc2": density,
        "radius_bin_edges_pc": dict(zip(labels, edges)),
        "config": {
            "distance_pc": distance_pc, "av": av, "logage": logage, "mh": mh,
            "aperture_pc": aperture_pc, "mass_min": mass_min, "mass_max": mass_max,
        },
    }


def run_self_test() -> dict:
    members_csv = REPO_ROOT / "data" / "cmd_members.csv"
    if not members_csv.exists():
        return {
            "status": "skipped_no_members_csv",
            "reason": f"{members_csv} 不存在，這個環境沒有真實成員星表可測",
        }
    if not DEFAULT_ISOCHRONE_GRID.exists():
        return {
            "status": "skipped_no_isochrone_cache",
            "reason": f"{DEFAULT_ISOCHRONE_GRID} 不存在，無法離線測",
        }
    t = Table.read(members_csv, format="csv")
    iso_grid = isomod.load_grid(DEFAULT_ISOCHRONE_GRID)
    stats = compute_stats(
        t, DEFAULT_DISTANCE_PC, DEFAULT_AV, DEFAULT_LOGAGE, DEFAULT_MH,
        11.68, DEFAULT_MASS_MIN, DEFAULT_MASS_MAX, DEFAULT_CMD_OFFSET_THRESHOLD,
        iso_grid, exclude_non_members=True,
    )

    n_vals = [stats["n_within"][k] for k in
              ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture")]
    alphas = [stats["alpha_within"][k]["alpha"] for k in
              ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture")]

    checks = {
        "sample_count_monotonic_nondecreasing": bool(
            all(n_vals[i] <= n_vals[i + 1] for i in range(len(n_vals) - 1))
        ),
        "alphas_in_plausible_range": bool(all(1.0 <= a <= 4.0 for a in alphas)),
        "global_fbin_in_unit_interval": bool(0.0 <= stats["fbin_global"] <= 1.0),
        "half_number_radius_positive": bool(stats["half_number_radius_2d_pc"] > 0),
    }

    summary = {
        "status": "self_test_on_real_data_not_a_synthetic_fixture",
        "n_within": stats["n_within"],
        "alpha_within": {k: v["alpha"] for k, v in stats["alpha_within"].items()},
        "fbin_global": stats["fbin_global"],
        "checks": checks,
    }
    if not all(checks.values()):
        raise AssertionError(f"nbody_summary_stats self-test failed: {checks}")
    return summary


# ═══════════════ 核心 3：讀星表、算、寫檔 ═══════════════
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-real", type=Path)
    parser.add_argument("--from-mock", type=Path)
    parser.add_argument("--distance-pc", type=float, default=DEFAULT_DISTANCE_PC)
    parser.add_argument("--av", type=float, default=DEFAULT_AV)
    parser.add_argument("--logage", type=float, default=DEFAULT_LOGAGE)
    parser.add_argument("--mh", type=float, default=DEFAULT_MH)
    parser.add_argument("--aperture-pc", type=float, default=11.68)
    parser.add_argument("--mass-min", type=float, default=DEFAULT_MASS_MIN)
    parser.add_argument("--mass-max", type=float, default=DEFAULT_MASS_MAX)
    parser.add_argument("--cmd-offset-threshold", type=float,
                        default=DEFAULT_CMD_OFFSET_THRESHOLD)
    parser.add_argument("--isochrone-grid", type=Path, default=DEFAULT_ISOCHRONE_GRID)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        summary = run_self_test()
        print(json.dumps(summary, indent=2))
        return

    if (args.from_real is None) == (args.from_mock is None):
        parser.error("exactly one of --from-real / --from-mock is required")
    source = args.from_real if args.from_real is not None else args.from_mock
    is_real = args.from_real is not None

    t = Table.read(source, format="csv")
    iso_grid = isomod.load_grid(args.isochrone_grid)
    stats = compute_stats(
        t, args.distance_pc, args.av, args.logage, args.mh, args.aperture_pc,
        args.mass_min, args.mass_max, args.cmd_offset_threshold, iso_grid,
        exclude_non_members=is_real,
    )
    stats["status"] = "observed_targets" if is_real else "mock_observation"
    stats["source"] = str(source)

    # ↓ 輸出路徑：真實 → results/nbody_observed_targets.json；
    #   假 → 跟輸入同位置、副檔名換成 .stats.json
    output = args.output
    if output is None:
        output = (
            REPO_ROOT / "results" / "nbody_observed_targets.json"
            if is_real
            else source.with_suffix(".stats.json")
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
