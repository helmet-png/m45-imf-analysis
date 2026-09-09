#!/usr/bin/env python
"""方法 B：高斯過程模擬器 + 貝氏反推，從一批 N-body run 的統計量學出
p(θ_初始條件 | 觀測)。只有 smoke test（S0-S4）量出單次 run 時間 <= 1
小時、使用者決定要走方法 B 時才需要這支程式；方法 A（加性修正）不依賴
這裡的任何東西。

功能：`nbody_summary_stats.py` 把每個 N-body run 壓成一個 26 維統計量
向量，這支程式反過來——訓練一個「初始條件 θ -> 統計量」的高斯過程
（GP）模擬器，這樣不用每次改變 θ 都重跑一次真正的 N-body 模擬，就能
評估「這組 θ 有多可能重現觀測到的 M45」，進而用 MCMC 對 θ 做貝氏反推。

方法：
1. **訓練資料**：讀一批 `<run_dir>/observed.stats.json`（`observe_snapshot.py`
   ->`nbody_summary_stats.py --from-mock` 的輸出）+ 對應的
   `petar_m45_grid.csv` 那列的 θ（N_sys、f_bin,ini、r_h,ini、S、
   α_in,high、α_in,low），組成設計矩陣 X（n_runs × 6）與回應矩陣 Y
   （n_runs × 26）。
2. **模擬器**：對 Y 的每一維獨立訓練一個 `sklearn.gaussian_process.
   GaussianProcessRegressor`（Matern 核 + 白雜訊核，白雜訊核吸收
   seed-to-seed 的隨機性，不是量測誤差）。獨立訓練（不是聯合多輸出
   GP）是刻意的簡化：sklearn 沒有現成的異方差多輸出 GP，26 個獨立
   GP 實作簡單、除錯容易，代價是忽略統計量之間的協方差——這是已知
   簡化，寫進自我測試與交接說明，不是被忽略的問題。
3. **概似**：`ln L = -0.5 * (y_obs - μ_GP(θ))ᵀ Σ⁻¹ (y_obs - μ_GP(θ))`，
   `Σ` 對角，每一維 = 觀測誤差² + GP 預測變異數² + seed 雜訊變異數
   （後者要另外從重複 seed 的 run 估）。**GP 的預測不確定度必須進 Σ**
   ——這正是本專案已經吃過虧的教訓（`LIMITATIONS.md` 記錄過前向模型
   的誤差棒曾經只算了統計波動，漏了模型本身的不確定度，導致「誤差棒
   太小」），這裡從一開始就不能重蹈覆轍。
4. **取樣**：`emcee`（repo 已有這個依賴，`pipeline/joint_fit.py` 也
   用）的 ensemble sampler。
5. **SBC（simulation-based calibration）**：從先驗抽 N 組 θ，用訓練好
   的 GP（不是真的 N-body！）產生假觀測，對每組假觀測跑 MCMC 反推，
   記錄真值在後驗樣本裡的排名（rank statistic）。若 GP／MCMC 校準
   正確，排名應接近均勻分布（Talts et al. 2018 的標準做法）。這裡
   驗證的是「GP+MCMC 這條推論鏈本身的統計性質」，不是「GP 有沒有
   正確逼近真正的 N-body」——後者要等真的有多組 N-body run 之後才能
   用留出測試集的 R² 檢查（`--test-split` 那條路徑）。

自我測試（`--self-test`）：不需要真的跑過 N-body，用一個已知的解析
函式（線性 + 高斯雜訊）當「假模擬器」產生訓練資料，訓練 GP、跑 SBC，
檢查：(a) GP 在留出測試集的 R² 夠高（能學出這個簡單函式）；
(b) SBC 的排名分布通過寬鬆的均勻性檢定（卡方檢定，p > 0.01，用寬鬆
門檻是因為自我測試只抽有限組數，不追求嚴格統計檢定力）；(c) 用已知
真值當觀測反推，真值要落在後驗的 95% 可信區間內。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

THETA_NAMES = ["n_sys", "f_bin_ini", "r_h_ini_pc", "mcluster_s", "alpha_in_high", "alpha_in_low"]
THETA_PRIOR_LOW = np.array([1200.0, 0.30, 2.4, 0.0, 1.9, 0.84])
THETA_PRIOR_HIGH = np.array([1700.0, 0.95, 4.5, 0.5, 2.7, 1.3])


def fit_emulators(X: np.ndarray, Y: np.ndarray, stat_names: list[str]) -> dict:
    """對 Y 的每一維獨立訓練一個 GP，回傳 {stat_name: fitted GP}。"""
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, WhiteKernel

    emulators = {}
    x_mean, x_std = X.mean(axis=0), X.std(axis=0)
    x_std[x_std == 0] = 1.0
    x_norm = (X - x_mean) / x_std
    for i, name in enumerate(stat_names):
        y = Y[:, i]
        finite = np.isfinite(y)
        if finite.sum() < 5:
            emulators[name] = None
            continue
        kernel = RBF(length_scale=np.ones(X.shape[1])) + WhiteKernel(noise_level=1.0)
        gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=2)
        gp.fit(x_norm[finite], y[finite])
        emulators[name] = gp
    return {"emulators": emulators, "x_mean": x_mean, "x_std": x_std, "stat_names": stat_names}


def predict(model: dict, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (mean, std) 各長度 = len(stat_names)，對應每個統計量。"""
    theta_norm = ((np.atleast_2d(theta) - model["x_mean"]) / model["x_std"])
    means, stds = [], []
    for name in model["stat_names"]:
        gp = model["emulators"][name]
        if gp is None:
            means.append(np.nan)
            stds.append(np.nan)
            continue
        mu, sd = gp.predict(theta_norm, return_std=True)
        means.append(float(mu[0]))
        stds.append(float(sd[0]))
    return np.asarray(means), np.asarray(stds)


def log_likelihood(
    theta: np.ndarray,
    model: dict,
    y_obs: np.ndarray,
    y_obs_err: np.ndarray,
    seed_noise_std: np.ndarray,
    theta_lo: np.ndarray,
    theta_hi: np.ndarray,
) -> float:
    if np.any(theta < theta_lo) or np.any(theta > theta_hi):
        return -np.inf
    mu, gp_std = predict(model, theta)
    valid = np.isfinite(mu) & np.isfinite(y_obs)
    if not valid.any():
        return -np.inf
    sigma2 = y_obs_err[valid] ** 2 + gp_std[valid] ** 2 + seed_noise_std[valid] ** 2
    sigma2 = np.where(sigma2 <= 0, 1e-6, sigma2)
    resid2 = (y_obs[valid] - mu[valid]) ** 2
    return float(-0.5 * np.sum(resid2 / sigma2 + np.log(2 * np.pi * sigma2)))


def run_mcmc(
    model: dict,
    y_obs: np.ndarray,
    y_obs_err: np.ndarray,
    seed_noise_std: np.ndarray,
    theta_lo: np.ndarray,
    theta_hi: np.ndarray,
    n_walkers: int = 32,
    n_steps: int = 2000,
    n_burn: int = 500,
    seed: int = 0,
) -> np.ndarray:
    import emcee

    rng = np.random.default_rng(seed)
    ndim = len(theta_lo)
    start = theta_lo + rng.random((n_walkers, ndim)) * (theta_hi - theta_lo)

    def log_prob(theta):
        return log_likelihood(theta, model, y_obs, y_obs_err, seed_noise_std, theta_lo, theta_hi)

    sampler = emcee.EnsembleSampler(n_walkers, ndim, log_prob)
    sampler.run_mcmc(start, n_steps, progress=False)
    chain = sampler.get_chain(discard=n_burn, flat=True)
    return chain


def sbc_test(
    model: dict,
    theta_lo: np.ndarray,
    theta_hi: np.ndarray,
    stat_names: list[str],
    n_trials: int = 30,
    n_walkers: int = 16,
    n_steps: int = 400,
    n_burn: int = 100,
    seed: int = 0,
) -> dict:
    """從先驗抽真值 -> 用 GP 產生假觀測（含 GP 自身不確定度當雜訊）->
    反推 -> 記錄真值在後驗第幾個百分位（rank）。GP 預測誤差當觀測誤差，
    seed 雜訊在這個純 GP 驗證裡設為 0（SBC 驗的是推論鏈本身，不是
    seed 雜訊建模對不對）。
    """
    rng = np.random.default_rng(seed)
    ndim = len(theta_lo)
    ranks = []
    for trial in range(n_trials):
        theta_true = theta_lo + rng.random(ndim) * (theta_hi - theta_lo)
        mu, gp_std = predict(model, theta_true)
        gp_std = np.where(np.isfinite(gp_std) & (gp_std > 0), gp_std, 1.0)
        y_obs = mu + rng.normal(size=len(mu)) * gp_std
        y_obs_err = np.zeros(len(mu))
        seed_noise = np.zeros(len(mu))

        chain = run_mcmc(
            model, y_obs, y_obs_err, seed_noise, theta_lo, theta_hi,
            n_walkers=n_walkers, n_steps=n_steps, n_burn=n_burn, seed=trial,
        )
        # 每個維度分別記 rank（真值在後驗樣本裡排名的百分位）
        for d in range(ndim):
            rank = float(np.mean(chain[:, d] < theta_true[d]))
            ranks.append(rank)

    ranks = np.asarray(ranks)
    # 卡方均勻性檢定（10 個箱）
    hist, _ = np.histogram(ranks, bins=10, range=(0, 1))
    expected = len(ranks) / 10
    chi2 = float(np.sum((hist - expected) ** 2 / expected)) if expected > 0 else np.nan
    from scipy.stats import chi2 as chi2_dist

    p_value = float(1 - chi2_dist.cdf(chi2, df=9)) if np.isfinite(chi2) else np.nan
    return {"ranks": ranks.tolist(), "chi2": chi2, "p_value": p_value, "n_trials": n_trials}


def run_self_test() -> dict:
    """用已知的解析假模擬器（線性 + 高斯雜訊）驗證整條鏈的統計性質。"""
    rng = np.random.default_rng(20260909)
    ndim = 3
    theta_lo = np.array([0.0, 0.0, 0.0])
    theta_hi = np.array([1.0, 1.0, 1.0])
    true_coeff = np.array([
        [2.0, -1.0, 0.5],
        [0.5, 1.5, -0.5],
        [1.0, 1.0, 1.0],
    ])

    def fake_simulator(theta, noise_rng):
        clean = true_coeff @ theta
        return clean + noise_rng.normal(size=3) * 0.02

    n_train = 200
    X = theta_lo + rng.random((n_train, ndim)) * (theta_hi - theta_lo)
    Y = np.array([fake_simulator(x, rng) for x in X])
    stat_names = ["y0", "y1", "y2"]

    n_test = 40
    X_test = theta_lo + rng.random((n_test, ndim)) * (theta_hi - theta_lo)
    Y_test = np.array([fake_simulator(x, rng) for x in X_test])

    model = fit_emulators(X, Y, stat_names)
    preds = np.array([predict(model, x)[0] for x in X_test])
    ss_res = np.sum((Y_test - preds) ** 2, axis=0)
    ss_tot = np.sum((Y_test - Y_test.mean(axis=0)) ** 2, axis=0)
    r2 = 1 - ss_res / np.where(ss_tot == 0, 1e-12, ss_tot)

    theta_true = np.array([0.6, 0.3, 0.7])
    y_obs = true_coeff @ theta_true
    chain = run_mcmc(
        model, y_obs, np.zeros(3), np.zeros(3), theta_lo, theta_hi,
        n_walkers=24, n_steps=1500, n_burn=400, seed=1,
    )
    lo95 = np.percentile(chain, 2.5, axis=0)
    hi95 = np.percentile(chain, 97.5, axis=0)
    truth_covered = bool(np.all((theta_true >= lo95) & (theta_true <= hi95)))

    sbc = sbc_test(model, theta_lo, theta_hi, stat_names, n_trials=20,
                   n_walkers=16, n_steps=300, n_burn=80, seed=2)

    checks = {
        "gp_r2_above_0.8_all_dims": bool(np.all(r2 > 0.8)),
        "sbc_ranks_roughly_uniform": bool(sbc["p_value"] > 0.01),
        "truth_recovered_within_95pct_interval": truth_covered,
    }

    summary = {
        "status": "synthetic_validation_only",
        "gp_r2": r2.tolist(),
        "recovered_theta_median": np.median(chain, axis=0).tolist(),
        "recovered_theta_95pct_interval": [lo95.tolist(), hi95.tolist()],
        "theta_true": theta_true.tolist(),
        "sbc": {"chi2": sbc["chi2"], "p_value": sbc["p_value"], "n_trials": sbc["n_trials"]},
        "checks": checks,
        "known_simplification": (
            "26 個統計量獨立訓練 GP，忽略統計量之間的協方差；"
            "SBC 只驗證 GP+MCMC 推論鏈本身的統計性質，不驗證 GP 有沒有"
            "正確逼近真正的 N-body 模擬（那要等真實 run 資料的留出測試集）"
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"emulator_fit self-test failed: {checks}")
    return summary


def load_training_data(run_dirs: list[Path], grid_csv: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """從一批 run 目錄的 observed.stats.json 組出設計矩陣。真正有 N-body
    run 資料之後才會被呼叫；目前 repo 裡沒有任何符合條件的 run，
    這個函式沒有被 --self-test 用到。
    """
    import csv

    grid_rows = {}
    with grid_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grid_rows[row["run_id"]] = row

    xs, ys, stat_names = [], [], None
    for run_dir in run_dirs:
        stats_path = run_dir / "observed.stats.json"
        if not stats_path.exists():
            continue
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        row = grid_rows.get(run_dir.name)
        if row is None:
            continue
        theta = [
            float(row["n_systems"]), float(row["binary_system_fraction"]),
            float(row["half_mass_radius_pc"]), float(row["mcluster_S"]),
            float(row.get("imf_alpha_high", 2.3)), float(row.get("imf_alpha_low", 1.3)),
        ]
        flat = []
        names = []
        for key in ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture"):
            flat.append(stats["n_within"][key])
            names.append(f"n_{key}")
        for key in ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture"):
            flat.append(stats["alpha_within"][key]["alpha"])
            names.append(f"alpha_{key}")
        for key in ("r1_1deg", "r2_2deg", "r3_3deg", "rall_aperture"):
            flat.append(stats["fbin_within"][key])
            names.append(f"fbin_{key}")
        flat.append(stats["fbin_global"])
        names.append("fbin_global")
        flat.append(stats["half_number_radius_2d_pc"])
        names.append("half_number_radius_2d_pc")
        for key, value in stats["radial_mass_density_pc2"].items():
            flat.append(value)
            names.append(f"density_{key}")

        xs.append(theta)
        ys.append(flat)
        stat_names = names

    return np.asarray(xs), np.asarray(ys), stat_names or []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_grid.csv")
    parser.add_argument("--targets", type=Path,
                        default=REPO_ROOT / "results" / "nbody_observed_targets.json")
    parser.add_argument("--output", type=Path,
                        default=REPO_ROOT / "results" / "emulator_fit.json")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        summary = run_self_test()
        print(json.dumps(summary, indent=2))
        return

    if not args.runs_dir.exists():
        parser.error(
            f"{args.runs_dir} 不存在——這支程式要等有真正的 N-body run 輸出"
            "（run_nbody_case.py 產生，經 observe_snapshot.py + "
            "nbody_summary_stats.py --from-mock 處理過）才能訓練模擬器，"
            "目前沒有任何 run，先跑 smoke test 與正式網格"
        )
    run_dirs = sorted(p for p in args.runs_dir.iterdir() if p.is_dir())
    X, Y, stat_names = load_training_data(run_dirs, args.grid)
    if len(X) < 20:
        parser.error(
            f"只找到 {len(X)} 組可用的訓練資料，方法 B 至少要 ~300 組"
            "（見 docs/planning/NBODY_PREREGISTRATION.md 第六節），"
            "資料不夠不要硬訓練"
        )
    model = fit_emulators(X, Y, stat_names)
    print(f"Trained emulators on {len(X)} runs, {len(stat_names)} statistics")
    # 完整的訓練/取樣/SBC/輸出流程留給有真實資料時再接上——這裡先確保
    # load_training_data 與 fit_emulators 的介面正確。


if __name__ == "__main__":
    main()
