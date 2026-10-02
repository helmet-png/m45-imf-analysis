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

======================================================================
【目前的狀態（請先看這段）】
======================================================================
⚠ **正式推論還沒實作**。main() 目前只做到「讀訓練資料 → 訓練 GP」；
  只要 --targets 指到的檔案存在就報錯結束。而 --targets 的預設值
  results/nbody_observed_targets.json 已經在 repo 裡，所以照預設執行時，
  訓練完一定會以錯誤結束——這是刻意的拒絕，不是 bug。
  run_mcmc() 與 sbc_test() 目前只在 --self-test（用解析函式當假模擬器）跑過。
⚠ 文件與程式不一致：
  - 上方第 2 點寫「Matern 核」，程式實際用 RBF 核（fit_emulators()）
  - 上方第 5 點提到的 `--test-split` 參數不存在
⚠ --runs-dir 預設 runs/，但訓練網格的 run 由 run_training_queue.py 寫在
  runs_training/；--grid 預設是法 A 的小網格，訓練要指到
  petar_m45_training_grid.csv。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, json, sys, pathlib   參數、讀 stats JSON、路徑
  csv（load_training_data 內 import）   讀網格 CSV
第三方套件：
  numpy（np）   陣列運算、亂數、np.histogram（SBC 排名分箱）
  sklearn.gaussian_process（fit_emulators 內 import）
      GaussianProcessRegressor   高斯過程迴歸：給一堆 (θ, 統計量) 的例子，
                                 學出「任意 θ 的統計量大概是多少、有多不確定」
      kernels.RBF                核函數：θ 越接近，預測的統計量越相似；
                                 length_scale 決定「多接近才算接近」（每一維各自學）
      kernels.WhiteKernel        白雜訊項：吸收同一組 θ 換 seed 的隨機跳動
  emcee（run_mcmc 內 import）    MCMC 系綜取樣器（跟 pipeline/joint_fit.py 同一套）
  scipy.stats.chi2（sbc_test 內 import）   卡方分布，算均勻性檢定的 p 值

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --runs-dir   放所有 run 資料夾的地方（每個 run 要有 observed.stats.json）
  --grid       網格 CSV（用 run_id 對回 6 個初始條件）
  --targets    真實 M45 的 26 個統計量（nbody_summary_stats.py --from-real 產生）
  --output     推論結果輸出路徑（目前沒有寫出任何東西）
  --self-test  用解析函式當假模擬器，測 GP、MCMC、SBC 整條鏈
模組常數：
  THETA_NAMES          六個要反推的初始條件：系統數、初始雙星比例、初始半質量
                       半徑、質量分層程度 S、高質量段斜率、低質量段斜率
  THETA_PRIOR_LOW／HIGH  均勻先驗的上下界：
                       1200–1700、0.30–0.95、2.4–4.5 pc、0–0.5、1.9–2.7、0.84–1.3
run_mcmc() 預設：32 個走者、2000 步、丟掉前 500 步
sbc_test() 預設：30 組真值、每組 16 個走者 × 400 步、丟掉前 100 步

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 135–162 行｜fit_emulators()：26 個統計量各訓練一個 GP
  核心 2｜第 165–181 行｜predict()：用 GP 預測任一組 θ 的統計量與不確定度
  核心 3｜第 184–207 行｜log_likelihood()：預測跟觀測差多少（含三種誤差）
  核心 4｜第 210–238 行｜run_mcmc()：用 emcee 對 θ 取樣，得到後驗
  核心 5｜第 241–290 行｜sbc_test()：檢驗推論鏈的統計校準
  核心 6｜第 362–417 行｜load_training_data()：把每個 run 的 θ 與 26 個統計量組成訓練資料

======================================================================
【(d) 整體流程】
======================================================================
設計上的完整流程（★ = 目前已實作）：
  ★ 讀每個 run 的 observed.stats.json 與網格裡的 θ → X（run 數 × 6）、Y（run 數 × 26）
  ★ 少於 20 組就拒絕（設計上要約 300 組）
  ★ θ 標準化 → 對 Y 的每一欄各訓練一個 GP
    讀真實 M45 的 26 個統計量（--targets）
    → MCMC：每一步用 GP 預測統計量、跟真實值比、算概似 → 得到 θ 的後驗
    → SBC 檢驗校準 → 寫出結果
  （後四步目前只在 --self-test 裡用假資料跑過）
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


# ═══════════════ 核心 1：訓練 GP 模擬器 ═══════════════
def fit_emulators(X: np.ndarray, Y: np.ndarray, stat_names: list[str]) -> dict:
    """對 Y 的每一維獨立訓練一個 GP，回傳 {stat_name: fitted GP}。"""
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import RBF, WhiteKernel

    emulators = {}
    # ↓ θ 標準化：每一維減平均、除標準差，讓 1200–1700 的系統數跟 0.3–0.95 的
    #   雙星比例在同一個尺度上（標準差為 0 的維度改除 1，避免除以零）
    x_mean, x_std = X.mean(axis=0), X.std(axis=0)
    x_std[x_std == 0] = 1.0
    x_norm = (X - x_mean) / x_std
    for i, name in enumerate(stat_names):
        # ↓ 第 i 個統計量在所有 run 的值；少於 5 個有效值就不訓練這一個
        y = Y[:, i]
        finite = np.isfinite(y)
        if finite.sum() < 5:
            emulators[name] = None
            continue
        # ↓ 核函數 = RBF（每一維各一個長度尺度，初始 1）+ 白雜訊（初始 1）
        kernel = RBF(length_scale=np.ones(X.shape[1])) + WhiteKernel(noise_level=1.0)
        # ↓ normalize_y：統計量先標準化再學；n_restarts_optimizer=2：
        #   超參數最佳化多試 2 個起點，避免卡在局部最佳
        gp = GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=2)
        # ↓ 用有效的 run 訓練：學出這些 θ 與這個統計量之間的關係
        gp.fit(x_norm[finite], y[finite])
        emulators[name] = gp
    return {"emulators": emulators, "x_mean": x_mean, "x_std": x_std, "stat_names": stat_names}


# ═══════════════ 核心 2：用 GP 預測 ═══════════════
def predict(model: dict, theta: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """回傳 (mean, std) 各長度 = len(stat_names)，對應每個統計量。"""
    # ↓ 用訓練時同樣的平均與標準差把 θ 標準化
    theta_norm = ((np.atleast_2d(theta) - model["x_mean"]) / model["x_std"])
    means, stds = [], []
    for name in model["stat_names"]:
        gp = model["emulators"][name]
        if gp is None:
            means.append(np.nan)
            stds.append(np.nan)
            continue
        # ↓ 預測值 mu 與預測不確定度 sd（離訓練點越遠，sd 越大）
        mu, sd = gp.predict(theta_norm, return_std=True)
        means.append(float(mu[0]))
        stds.append(float(sd[0]))
    return np.asarray(means), np.asarray(stds)


# ═══════════════ 核心 3：概似 ═══════════════
def log_likelihood(
    theta: np.ndarray,
    model: dict,
    y_obs: np.ndarray,
    y_obs_err: np.ndarray,
    seed_noise_std: np.ndarray,
    theta_lo: np.ndarray,
    theta_hi: np.ndarray,
) -> float:
    # ↓ 超出先驗盒子 → 不可能
    if np.any(theta < theta_lo) or np.any(theta > theta_hi):
        return -np.inf
    # ↓ GP 預測這組 θ 的 26 個統計量（不用真的跑 N-body）
    mu, gp_std = predict(model, theta)
    valid = np.isfinite(mu) & np.isfinite(y_obs)
    if not valid.any():
        return -np.inf
    # ↓ 每個統計量的總變異 = 觀測誤差² + GP 預測不確定度² + seed 雜訊²
    sigma2 = y_obs_err[valid] ** 2 + gp_std[valid] ** 2 + seed_noise_std[valid] ** 2
    sigma2 = np.where(sigma2 <= 0, 1e-6, sigma2)
    # ↓ 高斯概似的對數：−½ Σ [ (觀測 − 預測)² / 變異 + ln(2π 變異) ]
    resid2 = (y_obs[valid] - mu[valid]) ** 2
    return float(-0.5 * np.sum(resid2 / sigma2 + np.log(2 * np.pi * sigma2)))


# ═══════════════ 核心 4：MCMC 取樣 ═══════════════
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
    # ↓ 每個走者在先驗盒子內隨機選起點
    start = theta_lo + rng.random((n_walkers, ndim)) * (theta_hi - theta_lo)

    def log_prob(theta):
        return log_likelihood(theta, model, y_obs, y_obs_err, seed_noise_std, theta_lo, theta_hi)

    # ↓ 均勻先驗在盒子內是常數，所以對數後驗 = 對數概似（+ 常數）
    sampler = emcee.EnsembleSampler(n_walkers, ndim, log_prob)
    sampler.run_mcmc(start, n_steps, progress=False)
    # ↓ 丟掉暖身步數，剩下所有走者的樣本攤平 = θ 的後驗樣本
    chain = sampler.get_chain(discard=n_burn, flat=True)
    return chain


# ═══════════════ 核心 5：SBC 校準檢驗 ═══════════════
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
        # ↓ 從先驗隨機抽一組「真值」，用 GP 產生它的假觀測（加上 GP 自己的不確定度當雜訊）
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
            # ↓ 排名 = 後驗樣本中小於真值的比例；校準正確時，這個比例在
            #   多次試驗間應該均勻分布在 0–1
            rank = float(np.mean(chain[:, d] < theta_true[d]))
            ranks.append(rank)

    ranks = np.asarray(ranks)
    # 卡方均勻性檢定（10 個箱）
    # ↓ 把排名分成 10 箱，跟「每箱一樣多」比較，算卡方值與 p 值
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


# ═══════════════ 核心 6：組訓練資料 ═══════════════
def load_training_data(run_dirs: list[Path], grid_csv: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """從一批 run 目錄的 observed.stats.json 組出設計矩陣。真正有 N-body
    run 資料之後才會被呼叫；目前 repo 裡沒有任何符合條件的 run，
    這個函式沒有被 --self-test 用到。
    """
    import csv

    # ↓ 網格讀成 {run_id: 那一列}
    grid_rows = {}
    with grid_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grid_rows[row["run_id"]] = row

    xs, ys, stat_names = [], [], None
    for run_dir in run_dirs:
        # ↓ 每個 run 資料夾裡要有 observed.stats.json（26 個統計量）；沒有就略過
        stats_path = run_dir / "observed.stats.json"
        if not stats_path.exists():
            continue
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        row = grid_rows.get(run_dir.name)
        if row is None:
            continue
        # ↓ 依欄位名稱取出 6 個初始條件，順序同 THETA_NAMES（高質量段在前）
        #   ⚠ 欄位缺少時會默默用 2.3／1.3 代替
        theta = [
            float(row["n_systems"]), float(row["binary_system_fraction"]),
            float(row["half_mass_radius_pc"]), float(row["mcluster_S"]),
            float(row.get("imf_alpha_high", 2.3)), float(row.get("imf_alpha_low", 1.3)),
        ]
        # ↓ 把 26 個統計量依固定順序攤平成一列（順序見 nbody_summary_stats.py 檔頭）
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

    # 2026-09-18 修正（Codex review）：以前 --targets/--output 兩個旗標
    # 完全沒被讀寫——訓練資料足夠時呼叫者會拿到 exit 0，看起來像是
    # 完整跑完了「訓練→推論→輸出」，實際上只做了訓練，取樣／SBC／
    # 寫 --output 全部沒有實作。完整推論 CLI（讀 targets、真的執行
    # 推論、保存結果）留給有真實 N-body 網格資料時再接上；在那之前，
    # 只要偵測到呼叫者真的想做推論（--targets 指到的檔案存在），就
    # 明確用非零碼拒絕，不能悄悄只做訓練檢查卻裝作推論完成。
    if args.targets.exists():
        parser.error(
            f"{args.targets} 存在，但這個版本的 emulator_fit.py 還沒有"
            "實作正式推論（讀 targets、取樣、SBC、寫 --output 都還沒接"
            "上，見上面的訓練/取樣/SBC/輸出流程註解）。目前只能做訓練"
            "資料是否足夠、fit_emulators() 介面是否正確這兩件事——如果"
            "你要的是正式推論結果，這個版本還不能提供，不要把上面的"
            "exit 0 當成推論已完成"
        )
    print(
        "訓練檢查完成（--self-test 之外的正式訓練也一樣）；沒有寫任何"
        f"檔案到 {args.output}——正式推論尚未實作，見上面訊息。"
    )


if __name__ == "__main__":
    main()
