#!/usr/bin/env python
"""方法 B 正式推論（第一版）：GP 模擬器 + MCMC，從 M45 觀測統計量反推 6 維初始條件 θ。

功能：`emulator_fit.py` 有 GP 訓練（`fit_emulators`）與預測（`predict`），但沒有
把真實觀測接進來取樣。這支程式補上：讀訓練資料與 `nbody_observed_targets.json`，
訓練 GP、估計統計量之間的相關、跑 emcee、做 SBC 校準檢查，寫出後驗。

方法：
1. 訓練資料：`emulator_fit.load_training_data()`（每筆 run 的 26 個統計量 + 網格 θ）。
   `--drop-prefix fbin` 預設拿掉 5 個雙星比例統計量（交叉驗證 R² ≤ 0.3，且 M45
   觀測值落在模擬分布第 93–94 百分位，留著會把後驗推向雙星比例上界）。
   `--max-energy-error` 可依 `summarize_training_runs.py` 的彙整表排除 t=105 Myr
   累積能量誤差 |ΔE/E₀| 超過門檻的修補版 run（舊版 run 的這個值無意義，不篩）。
2. 概似：多變量常態，Σ(θ) = D(θ) R D(θ)。
   - D(θ) = GP 預測標準差（sklearn 的 `return_std` 含 WhiteKernel，也就是含 seed
     之間的隨機散布：投影方向、有限星數、測光雜訊都已在 observe_snapshot.py 模擬，
     所以不再另加觀測誤差，避免重複計算）。
   - R = 統計量之間的相關矩陣，由 K 折交叉驗證的標準化殘差估計（成對完整的
     樣本、特徵值下限 1e-3 保持正定）。星數、密度彼此高度相關，若當成獨立會
     重複計算資訊、後驗過窄；這是 `emulator_fit.log_likelihood()` 對角版本的已知缺點。
3. 先驗：每一維在訓練網格的 [min, max] 內均勻（拉丁超立方設計的範圍）。
4. 取樣：emcee（向量化，每步一次批次預測所有走者）。
5. SBC：從先驗抽 θ_true，用 GP 均值 + Σ(θ_true) 抽假觀測，反推後記錄真值在後驗中的
   排名；校準正確時排名均勻（Talts et al. 2018）。這只驗證「GP + MCMC」推論鏈本身，
   不驗證 GP 是否逼近真正的 N-body（那是 emulator_holdout_check.py 的工作）。

已知簡化（第一版，結果標「試跑」）：
- WhiteKernel 每個統計量一個固定雜訊，實際上星數的散布隨星數變（近似 Poisson），
  離觀測遠的區域雜訊會被高估、近處可能低估。
- 解體星團的 α 是 NaN，GP 只用有限值訓練；在解體區域 α 的預測是外推（觀測的星數
  本身會把後驗推離那一區）。

自我測試（`--self-test`）：兩個高度相關的解析輸出（相關 0.9），確認相關矩陣估得
出來、後驗 68% 區間涵蓋真值，且 SBC 排名不偏。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
from emulator_fit import fit_emulators, load_training_data  # noqa: E402
from emulator_holdout_check import flatten_targets  # noqa: E402

THETA_NAMES = ["n_systems", "binary_system_fraction", "half_mass_radius_pc",
               "mcluster_S", "imf_alpha_high", "imf_alpha_low"]


def predict_batch(model: dict, thetas: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """一次預測多組 θ；回傳 (mean, std)，形狀 (n_theta, n_stat)。"""
    t = (np.atleast_2d(thetas) - model["x_mean"]) / model["x_std"]
    mu = np.empty((len(t), len(model["stat_names"])))
    sd = np.empty_like(mu)
    for j, name in enumerate(model["stat_names"]):
        m, s = model["emulators"][name].predict(t, return_std=True)
        mu[:, j], sd[:, j] = m, s
    return mu, sd


def cv_correlation(X, Y, names, k, seed):
    """K 折交叉驗證的標準化殘差 → 相關矩陣（成對完整樣本），並回傳每維 R²。"""
    rng = np.random.default_rng(seed)
    folds = np.array_split(rng.permutation(len(X)), k)
    z = np.full_like(Y, np.nan, dtype=float)
    pred = np.full_like(Y, np.nan, dtype=float)
    for f in folds:
        train = np.setdiff1d(np.arange(len(X)), f)
        model = fit_emulators(X[train], Y[train], names)
        mu, sd = predict_batch(model, X[f])
        pred[f] = mu
        z[f] = (Y[f] - mu) / sd
    n = len(names)
    R = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            ok = np.isfinite(z[:, i]) & np.isfinite(z[:, j])
            R[i, j] = R[j, i] = np.corrcoef(z[ok, i], z[ok, j])[0, 1] if ok.sum() > 10 else 0.0
    w, v = np.linalg.eigh(R)
    R = (v * np.maximum(w, 1e-3)) @ v.T
    d = np.sqrt(np.diag(R))
    R = R / np.outer(d, d)
    r2, zstd = {}, {}
    for j, name in enumerate(names):
        ok = np.isfinite(Y[:, j]) & np.isfinite(pred[:, j])
        y, p = Y[ok, j], pred[ok, j]
        r2[name] = float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2))
        zstd[name] = float(np.nanstd(z[:, j]))
    return R, r2, zstd


def make_log_prob(model, y_obs, R, lo, hi):
    Rinv = np.linalg.inv(R)
    logdetR = np.linalg.slogdet(R)[1]

    def log_prob(thetas):
        thetas = np.atleast_2d(thetas)
        out = np.full(len(thetas), -np.inf)
        inside = np.all((thetas >= lo) & (thetas <= hi), axis=1)
        if inside.any():
            mu, sd = predict_batch(model, thetas[inside])
            u = (y_obs - mu) / sd
            out[inside] = -0.5 * (np.einsum("ij,jk,ik->i", u, Rinv, u)
                                  + 2 * np.log(sd).sum(1) + logdetR)
        return out
    return log_prob


def sample(log_prob, lo, hi, n_walkers, n_steps, n_burn, seed):
    import emcee
    rng = np.random.default_rng(seed)
    start = lo + rng.random((n_walkers, len(lo))) * (hi - lo)
    s = emcee.EnsembleSampler(n_walkers, len(lo), log_prob, vectorize=True)
    s.run_mcmc(start, n_steps, progress=False)
    try:
        tau = s.get_autocorr_time(discard=n_burn, quiet=True).tolist()
    except Exception as exc:  # noqa: BLE001 - 只記錄，不影響樣本
        tau = f"unavailable: {exc}"
    return (s.get_chain(discard=n_burn, flat=True), s.get_log_prob(discard=n_burn, flat=True),
            float(np.mean(s.acceptance_fraction)), tau)


def run_sbc(model, R, lo, hi, n_trials, n_walkers, n_steps, n_burn, seed):
    rng = np.random.default_rng(seed)
    L = np.linalg.cholesky(R)
    ranks = []
    for t in range(n_trials):
        th = lo + rng.random(len(lo)) * (hi - lo)
        mu, sd = predict_batch(model, th)
        y = mu[0] + sd[0] * (L @ rng.standard_normal(len(mu[0])))
        chain, _, _, _ = sample(make_log_prob(model, y, R, lo, hi), lo, hi,
                                n_walkers, n_steps, n_burn, seed + 1000 + t)
        ranks.append(np.mean(chain < th, axis=0))
    ranks = np.array(ranks)
    from scipy.stats import chi2
    out = {}
    for d, name in enumerate(THETA_NAMES[:len(lo)]):
        h, _ = np.histogram(ranks[:, d], bins=5, range=(0, 1))
        e = n_trials / 5
        c = float(np.sum((h - e) ** 2 / e))
        out[name] = {"rank_hist_5bins": h.tolist(), "chi2": c, "p_value": float(1 - chi2.cdf(c, 4))}
    return {"n_trials": n_trials, "per_parameter": out, "ranks": ranks.tolist()}


def summarize(chain, lp, lo, hi, names):
    q = np.percentile(chain, [2.5, 16, 50, 84, 97.5], axis=0)
    prior_sd = (hi - lo) / np.sqrt(12)
    best = chain[np.argmax(lp)]
    return {name: {"q2.5": q[0, i], "q16": q[1, i], "median": q[2, i], "q84": q[3, i], "q97.5": q[4, i],
                   "posterior_sd": float(chain[:, i].std()), "prior_sd": float(prior_sd[i]),
                   "sd_ratio": float(chain[:, i].std() / prior_sd[i]), "max_lp_sample": float(best[i]),
                   "prior_lo": float(lo[i]), "prior_hi": float(hi[i])}
            for i, name in enumerate(names)}


def run_self_test() -> dict:
    rng = np.random.default_rng(7)
    X = rng.uniform(0, 1, size=(200, 2))
    noise = rng.multivariate_normal([0, 0], [[1, 0.9], [0.9, 1]], size=200) * 0.05
    Y = np.c_[X[:, 0] + X[:, 1], X[:, 0] - 0.5 * X[:, 1]] + noise
    names = ["a", "b"]
    R, r2, _ = cv_correlation(X, Y, names, 5, 0)
    model = fit_emulators(X, Y, names)
    lo, hi = np.zeros(2), np.ones(2)
    truth = np.array([0.4, 0.6])
    y_obs = np.array([truth[0] + truth[1], truth[0] - 0.5 * truth[1]])
    chain, lp, acc, _ = sample(make_log_prob(model, y_obs, R, lo, hi), lo, hi, 16, 1500, 500, 1)
    q16, q84 = np.percentile(chain, [16, 84], axis=0)
    checks = {"correlation_recovered": bool(0.75 < R[0, 1] < 0.98),
              "emulator_accurate": bool(min(r2.values()) > 0.95),
              "posterior_covers_truth": bool(np.all((q16 - 0.05 < truth) & (truth < q84 + 0.05))),
              "acceptance_reasonable": bool(0.1 < acc < 0.9)}
    if not all(checks.values()):
        raise AssertionError(f"emulator_infer self-test failed: {checks} R01={R[0, 1]:.3f} r2={r2}")
    return {"status": "synthetic_validation_only", "checks": checks, "R01": float(R[0, 1])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "results" / "nbody_training_runs")
    ap.add_argument("--grid", type=Path, default=REPO_ROOT / "petar_m45_training_grid.csv")
    ap.add_argument("--targets", type=Path, default=REPO_ROOT / "results" / "nbody_observed_targets.json")
    ap.add_argument("--drop-prefix", default="fbin", help="逗號分隔；空字串 = 全部 26 個統計量都用")
    ap.add_argument("--max-energy-error", type=float, default=None)
    ap.add_argument("--run-summary", type=Path, default=REPO_ROOT / "results" / "nbody_training_runs_summary.csv")
    ap.add_argument("--cv-k", type=int, default=5)
    ap.add_argument("--n-walkers", type=int, default=48)
    ap.add_argument("--n-steps", type=int, default=6000)
    ap.add_argument("--n-burn", type=int, default=2000)
    ap.add_argument("--sbc-trials", type=int, default=40)
    ap.add_argument("--sbc-steps", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=20261025)
    ap.add_argument("--tag", default="")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

    run_dirs = sorted(p for p in args.runs_dir.iterdir() if p.is_dir() and ".stale-" not in p.name)
    n_excluded = 0
    if args.max_energy_error is not None:
        # 只篩修補版 PeTar 的 run：舊版 95 筆的 Error_cum 被移動座標系記帳錯誤蓋過，
        # 不是積分品質指標；它們的動力學已驗證與修補版逐位元相同（預註冊五節 2026-10-25）。
        with args.run_summary.open(newline="", encoding="utf-8") as f:
            rows = {r["run_id"]: r for r in csv.DictReader(f)}
        missing = [d.name for d in run_dirs if rows.get(d.name, {}).get("err_cum_over_e0_t105", "") == ""]
        if missing:
            raise ValueError(f"{len(missing)} runs lack err_cum_over_e0_t105: {missing[:5]}")
        kept = [d for d in run_dirs if rows[d.name]["petar_patched"] != "True"
                or abs(float(rows[d.name]["err_cum_over_e0_t105"])) <= args.max_energy_error]
        n_excluded, run_dirs = len(run_dirs) - len(kept), kept
    X, Y, names = load_training_data(run_dirs, args.grid)
    drops = [p for p in args.drop_prefix.split(",") if p]
    keep = [i for i, n in enumerate(names) if not any(n.startswith(p) for p in drops)]
    names = [names[i] for i in keep]
    Y = Y[:, keep]
    targets = flatten_targets(json.loads(args.targets.read_text(encoding="utf-8")))
    y_obs = np.array([targets[n] for n in names], float)
    if not np.all(np.isfinite(y_obs)):
        raise ValueError("observed targets contain non-finite values")
    lo, hi = X.min(axis=0), X.max(axis=0)
    print(f"{len(X)} runs (energy-excluded {n_excluded}), {len(names)} statistics", flush=True)

    R, r2, zstd = cv_correlation(X, Y, names, args.cv_k, args.seed)
    print("CV R2:", {k: round(v, 3) for k, v in r2.items()}, flush=True)
    model = fit_emulators(X, Y, names)
    log_prob = make_log_prob(model, y_obs, R, lo, hi)
    chain, lp, acc, tau = sample(log_prob, lo, hi, args.n_walkers, args.n_steps, args.n_burn, args.seed)
    post = summarize(chain, lp, lo, hi, THETA_NAMES)
    mu, sd = predict_batch(model, np.median(chain, axis=0))
    ppc = {n: {"observed": float(y_obs[j]), "emulator_mean": float(mu[0, j]), "emulator_sd": float(sd[0, j]),
               "z": float((y_obs[j] - mu[0, j]) / sd[0, j])} for j, n in enumerate(names)}
    u = (y_obs - mu[0]) / sd[0]
    chi2_med = float(u @ np.linalg.inv(R) @ u)
    print("posterior:", json.dumps({k: [round(v["q16"], 3), round(v["median"], 3), round(v["q84"], 3)]
                                    for k, v in post.items()}), flush=True)
    sbc = (run_sbc(model, R, lo, hi, args.sbc_trials, 32, args.sbc_steps, args.sbc_steps // 3, args.seed)
           if args.sbc_trials > 0 else None)

    out = REPO_ROOT / "results" / f"nbody_emulator_infer{args.tag}"
    summary = {
        "status": "trial_run_not_citable",
        "n_runs": int(len(X)), "n_energy_excluded": n_excluded, "max_energy_error": args.max_energy_error,
        "statistics": names, "dropped_prefixes": drops,
        "cv_r2": r2, "cv_standardized_residual_sd": zstd, "correlation_matrix": R.tolist(),
        "mcmc": {"n_walkers": args.n_walkers, "n_steps": args.n_steps, "n_burn": args.n_burn,
                 "acceptance_fraction": acc, "autocorr_time": tau, "seed": args.seed},
        "posterior": post, "posterior_predictive_at_median": ppc,
        "chi2_at_median": chi2_med, "n_statistics": len(names), "sbc": sbc,
    }
    out.with_suffix(".json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=float) + "\n",
                                        encoding="utf-8")
    thin = max(1, len(chain) // 20000)
    np.savez_compressed(out.with_suffix(".npz"), chain=chain[::thin], log_prob=lp[::thin],
                        theta_names=np.array(THETA_NAMES))
    print(f"wrote {out.with_suffix('.json')} and .npz", flush=True)
    if sbc:
        print("SBC p-values:", {k: round(v["p_value"], 3) for k, v in sbc["per_parameter"].items()})


if __name__ == "__main__":
    main()
