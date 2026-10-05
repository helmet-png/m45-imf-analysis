#!/usr/bin/env python
"""用真實 N-body 訓練資料做 K 折交叉驗證，量 GP 模擬器的預測準度。

功能：`emulator_fit.py` 的正式推論（讀觀測目標、MCMC、SBC）還沒接上；在接
之前要先知道「拿現有的 run 訓練出來的模擬器，對沒看過的 run 能預測得多準」。
這支只做這件事：K 折交叉驗證，逐一報告 26 個統計量的 R² 與預測誤差，並跟
觀測端的統計量大小對照。不做推論、不產出任何 α 值。

方法：
1. 用 `emulator_fit.load_training_data()` 讀 `<runs-dir>/*/observed.stats.json`
   與網格 CSV，得到設計矩陣 X（6 維 θ）與統計量 Y（26 維）。不重寫讀檔邏輯。
2. 每筆 run 的 `observed.provenance.json` 記著該 run 用的 PeTar 執行檔
   （`build_training_stats.py` 寫的）；`--binary-filter` 可只取修補版或舊版，
   預設全取並在報告中分開計數。
3. K 折（預設 5，固定亂數種子）：每折用 `emulator_fit.fit_emulators()` 訓練、
   `predict()` 預測留出的 run。每個統計量各自只用有限值（解體星團的 α 為 NaN，
   見 `build_training_stats.py` 的說明）。
4. 每個統計量報告：有限值筆數、交叉驗證 R²、預測殘差的 RMS，以及該統計量在
   真實 M45 觀測值（`--targets`）的大小，方便判斷誤差相對量級。

自我測試（`--self-test`）：用解析函數 y = θ₁ + 2θ₂² 造 60 筆假資料，確認交叉
驗證 R² > 0.9；再塞入 NaN 確認會被排除而不是讓整個統計量失敗。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from emulator_fit import fit_emulators, load_training_data, predict  # noqa: E402


def kfold_r2(X: np.ndarray, Y: np.ndarray, names: list[str], k: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    folds = np.array_split(rng.permutation(len(X)), k)
    pred = np.full_like(Y, np.nan, dtype=float)
    for f in folds:
        train = np.setdiff1d(np.arange(len(X)), f)
        model = fit_emulators(X[train], Y[train], names)
        for i in f:
            pred[i] = predict(model, X[i])[0]
    out = {}
    for j, name in enumerate(names):
        ok = np.isfinite(Y[:, j]) & np.isfinite(pred[:, j])
        if ok.sum() < 5:
            out[name] = {"n_finite": int(ok.sum()), "r2": None, "rms": None}
            continue
        y, p = Y[ok, j], pred[ok, j]
        ss_res = float(np.sum((y - p) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        out[name] = {"n_finite": int(ok.sum()),
                     "r2": 1 - ss_res / ss_tot if ss_tot > 0 else None,
                     "rms": float(np.sqrt(ss_res / ok.sum())),
                     "y_std": float(y.std())}
    return out


def flatten_targets(t: dict) -> dict:
    """把 nbody_observed_targets.json 攤平成跟 load_training_data 一樣的名稱。"""
    out = {}
    for key in ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture"):
        out[f"n_{key}"] = t["n_within"][key]
        out[f"alpha_{key}"] = t["alpha_within"][key]["alpha"]
        out[f"fbin_{key}"] = t["fbin_within"][key]
    out["fbin_global"] = t["fbin_global"]
    out["half_number_radius_2d_pc"] = t["half_number_radius_2d_pc"]
    for key, v in t["radial_mass_density_pc2"].items():
        out[f"density_{key}"] = v
    return out


def run_self_test() -> dict:
    rng = np.random.default_rng(1)
    X = rng.uniform(0, 1, size=(60, 2))
    Y = np.c_[X[:, 0] + 2 * X[:, 1] ** 2, X[:, 0]]
    Y[:5, 1] = np.nan
    res = kfold_r2(X, Y, ["a", "b"], k=5, seed=0)
    checks = {"r2_high_on_smooth_function": res["a"]["r2"] > 0.9,
              "nan_rows_excluded": res["b"]["n_finite"] == 55 and res["b"]["r2"] > 0.9}
    if not all(checks.values()):
        raise AssertionError(f"emulator_holdout_check self-test failed: {checks} {res}")
    return {"status": "synthetic_validation_only", "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    ap.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_training_grid.csv")
    ap.add_argument("--targets", type=Path, default=REPO_ROOT / "results" / "nbody_observed_targets.json")
    ap.add_argument("--binary-filter", choices=("all", "patched", "original"), default="all")
    ap.add_argument("--patched-marker", default="install_framefix",
                    help="provenance 裡 petar_binary 路徑含這個字串就算修補版")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20261002)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "nbody_emulator_holdout.json")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

    run_dirs, n_patched, n_orig = [], 0, 0
    for d in sorted(p for p in args.runs_dir.iterdir() if p.is_dir() and ".stale-" not in p.name):
        prov = d / "observed.provenance.json"
        if not (d / "observed.stats.json").exists() or not prov.exists():
            continue
        patched = args.patched_marker in json.loads(prov.read_text(encoding="utf-8")).get("petar_binary", "")
        n_patched += patched
        n_orig += not patched
        if args.binary_filter == "all" or (args.binary_filter == "patched") == patched:
            run_dirs.append(d)
    X, Y, names = load_training_data(run_dirs, args.grid)
    res = kfold_r2(X, Y, names, args.k, args.seed)
    targets = flatten_targets(json.loads(args.targets.read_text(encoding="utf-8")))
    for n in names:
        res[n]["observed_m45"] = targets.get(n)
    summary = {
        "status": "preliminary_holdout_check_not_inference",
        "n_runs_used": int(len(X)), "n_patched_available": n_patched, "n_original_available": n_orig,
        "binary_filter": args.binary_filter, "k": args.k,
        "theta_order": ["n_systems", "binary_system_fraction", "half_mass_radius_pc",
                        "mcluster_S", "imf_alpha_high", "imf_alpha_low"],
        "per_statistic": res,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for n in names:
        r = res[n]
        r2 = "  n/a" if r["r2"] is None else f"{r['r2']:5.2f}"
        print(f"{n:32s} n={r['n_finite']:3d}  R2={r2}  rms={r.get('rms') or float('nan'):.4g}  "
              f"obs={r['observed_m45']}")


if __name__ == "__main__":
    main()
