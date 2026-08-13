# -*- coding: utf-8 -*-
"""第 3 步（PDMF → IMF 路線 C 之外的另一條）：LIMEPY 多質量平衡模型。

用觀測到的（質量、投影半徑）分佈去擬合一個多質量、各向同性的平衡星團模型
（Gieles & Zocchi 2015 的 LIMEPY），反推潮汐半徑外還有多少質量——這是
唯一不需要重抓資料就能估計「潮汐半徑外還有多少低質量星」的路線，見
PAPER_OUTLINE.md 與 WORK_BOARD.md「待認領工作：PDMF → IMF」表第 3 步。

方法：把成員星依質量切成 N_MASS_BINS 個區間，各自算投影半徑的環帶數密度
剖面（觀測值），再用 LIMEPY 生成模型剖面，對 (phi0, r0, M) 三個參數做
卡方擬合（mj／Mj 用觀測到的各質量區間平均質量／總質量比例固定，只讓整體
形狀與尺度自由）。King(g=1)／Woolley(g=0)／Wilson(g=2) 三種模型形狀測過，
擬合出的 phi0/r0/M 幾乎一樣，用最常見的 King(g=1)。

**環境需求（重要，先讀）**：astro-limepy 依賴 `scipy.integrate.ode`
這支已棄用的舊 API，在 scipy 1.17.1（ARM64 機器，見 LIMITATIONS.md
「LIMEPY 環境問題」一節）與 1.18.0（這台機器，Python 3.14）上都各自踩到
不同的相容性 bug（前者是 `nsteps` 型別、後者是 dopri5 的 solout 呼叫
慣例已改變，`nsteps` 型別修好後還會再撞到第二個 bug）。Python 3.14
目前沒有任何舊版 scipy 的 cp314 wheel（要編譯器才能裝，這台機器沒裝），
沒辦法直接在主環境釘舊版。**解法：獨立 venv 釘 scipy==1.16.3**
（唯一測過能跑的版本組合，King/Woolley/Wilson 三種模型都驗證過收斂）：

    python -m venv .venv_limepy
    .venv_limepy/Scripts/python -m pip install "scipy==1.16.3" astro-limepy astropy numpy
    .venv_limepy/Scripts/python scripts/diagnostics/limepy_multimass.py

不要在主環境裝 astro-limepy——會把主環境的 scipy 降級，影響其他所有
腳本。這支腳本只需要 numpy/scipy/astropy/limepy 四個套件，不需要專案
其他重依賴（pipeline/ 都不用 import）。

**已知限制（誠實記錄，見 LIMITATIONS.md）**：
1. 這是單一各向同性模型擬合三個質量區間的投影數密度剖面，reduced
   chi^2 約 9（不算好，King/Woolley/Wilson 三種形狀給出幾乎一樣的結果，
   代表限制不在模型形狀選擇，可能是徑向分箱統計量不足或真實剖面有
   模型未捕捉到的結構），數字方向可信、精確值不宜過度解讀。
2. 質量區間之間的相對總質量比例（Mj）直接固定成觀測值，只有整體
   normalization（M）自由——如果 PDMF 本身因為蒸發已經扭曲，這個比例
   會把扭曲也帶進模型，這正是 A5 想解決的問題，屬於已知的方法論簡化。
3. 「潮汐半徑外還有多少質量」是模型外推，不是直接測量；LIMEPY 的
   phi(r)=0 半徑（這裡稱 r_t）是模型內部量，不等於用銀河潮汐力算出的
   Jacobi 半徑（`dynamics_estimate.py` 算出 12.96 pc）——兩者概念不同，
   數字對不上是預期內的事，不要混為一談。
"""
from __future__ import annotations

import numpy as np
from pathlib import Path
from astropy.table import Table
from scipy.optimize import minimize
from scipy.integrate import quad
import limepy

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DIST_PC = 136.0          # M45 距離，跟 dynamics_estimate.py --distance 預設一致
MASS_MIN, MASS_MAX = 0.30, 2.50   # 跟 config.toml [step5_imf] 一致
N_MASS_BINS = 3
N_RADIAL_BINS = 6
MODEL_G = 1               # King model；Woolley(0)/Wilson(2) 驗證過結果一致


def load_masses_and_radii():
    """沿用 run_pipeline.py 第 5 步同一套質量指派與角距離公式，不重新發明。"""
    f5 = dict(np.load(REPO_ROOT / "results" / "step5_imf.npz"))
    masses = f5["masses"]
    clean = Table.read(REPO_ROOT / "data" / "cmd_members.csv", format="csv")
    ra = np.radians(np.asarray(clean["ra"], float))
    dec = np.radians(np.asarray(clean["dec"], float))
    ra0 = np.radians(np.median(np.asarray(clean["ra"], float)))
    dec0 = np.radians(np.median(np.asarray(clean["dec"], float)))
    cosr = (np.sin(dec0) * np.sin(dec)
            + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0))
    r_deg = np.degrees(np.arccos(np.clip(cosr, -1, 1)))
    r_pc = np.radians(r_deg) * DIST_PC
    return masses, r_pc


def build_profiles(m, r):
    """依質量切 N_MASS_BINS 個區間，各自算投影半徑環帶數密度剖面。"""
    edges_m = np.percentile(m, np.linspace(0, 100, N_MASS_BINS + 1))
    bin_idx = np.clip(np.digitize(m, edges_m[1:-1]), 0, N_MASS_BINS - 1)
    mj = np.array([np.mean(m[bin_idx == j]) for j in range(N_MASS_BINS)])
    Mj_tot = np.array([np.sum(m[bin_idx == j]) for j in range(N_MASS_BINS)])
    Mj_frac = Mj_tot / Mj_tot.sum()

    r_edges = np.logspace(np.log10(0.3), np.log10(r.max()), N_RADIAL_BINS + 1)
    r_mid = np.sqrt(r_edges[:-1] * r_edges[1:])
    area = np.pi * (r_edges[1:] ** 2 - r_edges[:-1] ** 2)

    obs_R, obs_Sigma, obs_err, obs_n = [], [], [], []
    for j in range(N_MASS_BINS):
        counts, _ = np.histogram(r[bin_idx == j], bins=r_edges)
        sigma = counts / area
        err = np.sqrt(np.maximum(counts, 1)) / area
        valid = counts > 0
        obs_R.append(r_mid[valid])
        obs_Sigma.append(sigma[valid])
        obs_err.append(err[valid])
        obs_n.append(counts)
    return mj, Mj_frac, obs_R, obs_Sigma, obs_err, obs_n, edges_m


def fit(mj, Mj_frac, obs_R, obs_Sigma, obs_err, g=MODEL_G):
    """對 (phi0, log10(r0), log10(M)) 做卡方擬合，Mj 形狀固定成觀測比例。"""
    def chi2(params):
        phi0, log_r0, log_M = params
        if phi0 <= 0.5 or phi0 > 14:
            return 1e12
        try:
            model = limepy.limepy(phi0, g, mj=list(mj), Mj=list(Mj_frac),
                                  r0=10 ** log_r0, M=10 ** log_M, project=True)
        except Exception:
            return 1e12
        if not model.converged:
            return 1e12
        total = 0.0
        for j in range(len(mj)):
            pred = np.interp(obs_R[j], model.R, model.Sigmaj[j],
                             left=np.nan, right=0.0)
            good = np.isfinite(pred)
            total += np.sum(((obs_Sigma[j][good] - pred[good])
                             / obs_err[j][good]) ** 2)
        return total

    res = minimize(chi2, [6.0, np.log10(3.0), np.log10(300)],
                   method="Nelder-Mead",
                   options={"xatol": 1e-3, "fatol": 1e-3, "maxiter": 500})
    phi0, log_r0, log_M = res.x
    return phi0, 10 ** log_r0, 10 ** log_M, res.fun


def mass_beyond_radius(model, r_sample, mj):
    """把擬合模型的 3D 密度（各質量區間分開）從 r_sample 積分到 r_t。"""
    rt = float(model.rt)
    if rt <= r_sample:
        return 0.0, rt
    total = 0.0
    for j in range(len(mj)):
        def integrand(rr, j=j):
            return np.interp(rr, model.r, model.rhoj[j]) * 4 * np.pi * rr ** 2
        val, _ = quad(integrand, r_sample, rt, limit=200)
        total += val
    return total, rt


def main():
    masses, r_pc = load_masses_and_radii()
    keep = (masses >= MASS_MIN) & (masses <= MASS_MAX)
    m, r = masses[keep], r_pc[keep]
    print(f"樣本：{keep.sum()} 顆星（質量範圍 {MASS_MIN}-{MASS_MAX} M_sun），"
          f"投影半徑 {r.min():.2f}-{r.max():.2f} pc（距離 {DIST_PC} pc）")

    mj, Mj_frac, obs_R, obs_Sigma, obs_err, obs_n, edges_m = build_profiles(m, r)
    print(f"\n質量分箱邊界（M_sun）：{edges_m}")
    for j in range(N_MASS_BINS):
        print(f"  區間 {j}：平均質量 {mj[j]:.3f} M_sun，"
              f"質量佔比 {Mj_frac[j]*100:.1f}%，環帶星數 {list(obs_n[j])}")

    print(f"\n擬合 King(g={MODEL_G}) 模型（Woolley/Wilson 已驗證給出一致結果）...")
    phi0, r0, M_fit, chi2 = fit(mj, Mj_frac, obs_R, obs_Sigma, obs_err)
    n_data = sum(len(x) for x in obs_R)
    dof = n_data - 3
    print(f"  phi0(W0) = {phi0:.2f}")
    print(f"  r0 (尺度半徑) = {r0:.2f} pc")
    print(f"  M (擬合總質量) = {M_fit:.1f} M_sun")
    print(f"  卡方 = {chi2:.1f}（{n_data} 個資料點，{dof} 自由度，"
          f"reduced chi^2 = {chi2/dof:.2f}）")

    model = limepy.limepy(phi0, MODEL_G, mj=list(mj), Mj=list(Mj_frac),
                          r0=r0, M=M_fit, project=True)
    print(f"\n  r_t (模型潮汐半徑，phi=0 處) = {model.rt:.2f} pc")
    print(f"  r_h (半質量半徑) = {model.rh:.2f} pc")
    print(f"  （注意：這是模型內部量，不等於銀河潮汐力算出的 Jacobi 半徑"
          f"（dynamics_estimate.py 算出 12.96 pc）——兩者概念不同）")

    mass_beyond, rt = mass_beyond_radius(model, r.max(), mj)
    print(f"\n目前 Gaia 樣本邊緣 {r.max():.2f} pc 到模型 r_t={rt:.2f} pc 之間，"
          f"模型預測的質量：{mass_beyond:.1f} M_sun"
          f"（佔模型總質量 {mass_beyond/model.M*100:.1f}%）")

    out = REPO_ROOT / "results" / "limepy_multimass.npz"
    np.savez(out, phi0=phi0, r0=r0, M_fit=M_fit, chi2=chi2, dof=dof,
             mj=mj, Mj_frac=Mj_frac, rt=model.rt, rh=model.rh,
             r_sample_max=r.max(), mass_beyond_sample=mass_beyond,
             model_g=MODEL_G, n_stars=keep.sum())
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
