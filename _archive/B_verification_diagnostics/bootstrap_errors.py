# -*- coding: utf-8 -*-
"""用自助法（bootstrap）直接量參數的不確定度，繞過概似函數的病態。

為什麼需要這支：
    聯合擬合的 MCMC 中心值穩定，但誤差棒不可信 —— A_V 給 ±0.001、alpha 給 ±0.003，
    而網格搜尋在不同設定下給的 A_V 是 0.14 到 0.32。診斷顯示鏈拉長 2.5 倍後
    alpha 的自相關時間反而從 261 漲到 1025，這是後驗形狀病態的特徵而非取樣不足。

    根源是 Poisson-Hess 概似把 2,000 個格子視為互相獨立，在 1,078 顆星上
    產生過度自信的窄峰。加長鏈無法解決。

自助法的邏輯完全不同：
    把觀測到的星做可置換重抽（同樣顆數，但有些星被抽中多次、有些沒抽中），
    每一份重抽樣本各自重新擬合，看擬合結果的散布有多大。
    這直接回答「換一組統計上等價的觀測資料，答案會差多少」，
    不依賴概似函數的曲率，也不受格子獨立性假設的影響。

    合成星團的亂數維持固定（共用亂數），這樣散布只反映觀測樣本的抽樣不確定度。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from astropy.table import Table
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import joint_fit                               # noqa: E402


# 各參數的初始步長。必須明確指定，不能讓 scipy 用預設的「加 5%」：
# logage 加 5% 是 +0.4，會直接衝出先驗上界導致單純形塌陷；
# 而且 logage 被 isochrone 網格量化成 0.05 一階，步長小於 0.05 根本不改變概似。
STEP = np.array([0.05, 0.03, 0.06, 0.12])


def fit_once(model, start, maxiter=600):
    """從 start 出發做局部最佳化，回傳最佳參數。

    用 Nelder-Mead 而非梯度法：概似函數帶有確定性的偽雜訊（來自合成星團的
    有限取樣），梯度沒有意義，但單純形法只比較函數值大小，不受影響。
    """
    lo, hi = model.bounds[:, 0], model.bounds[:, 1]
    start = np.clip(start, lo + STEP, hi - STEP)

    def neg(theta):
        v = model.log_posterior(theta)
        return 1e12 if not np.isfinite(v) else -v

    # 明確建構初始單純形：以 start 為一頂點，其餘各沿一個維度移動一個步長
    simplex = np.vstack([start] + [start + STEP * np.eye(len(start))[i]
                                   for i in range(len(start))])
    simplex = np.clip(simplex, lo, hi)

    r = minimize(neg, start, method="Nelder-Mead",
                 options={"maxiter": maxiter, "xatol": 5e-3, "fatol": 1.0,
                          "initial_simplex": simplex})
    return np.clip(r.x, lo, hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=60)
    ap.add_argument("--config", default=None)
    a = ap.parse_args()

    cfg = cfgmod.load(a.config)
    c3, cj = cfg.step3_age, cfg.joint_fit

    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))

    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0

    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]
    n_obs = len(color)
    print(f"觀測 {n_obs:,} 顆，距離模數 {dm:.4f}")

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic

    # 先用完整樣本擬合一次，當作中心值與各次自助的起點
    base_model = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    jf = np.load(HERE / "results" / "joint_fit.npz")
    start = np.asarray(jf["best"], float)
    print(f"起點（MCMC 最佳點）：{np.array2string(start, precision=3)}")

    t0 = time.time()
    best_full = fit_once(base_model, start)
    print(f"完整樣本的最佳解：{np.array2string(best_full, precision=4)}"
          f"（{time.time()-t0:.0f} 秒）\n")

    rng = np.random.default_rng(cfg.step1_membership.random_seed)
    boots = []
    t0 = time.time()
    for i in range(a.n_boot):
        idx = rng.integers(0, n_obs, n_obs)          # 可置換重抽
        m = joint_fit.JointModel(cfg, color[idx], mag[idx], grid, errmodel, dm)
        boots.append(fit_once(m, best_full))
        if (i + 1) % 10 == 0:
            el = time.time() - t0
            print(f"  已完成 {i+1}/{a.n_boot}，{el/60:.1f} 分鐘"
                  f"（預估總共 {el/(i+1)*a.n_boot/60:.1f} 分鐘）", flush=True)
    boots = np.array(boots)

    print(f"\n{'參數':<10}{'完整樣本':>10}{'自助中位':>10}"
          f"{'自助 -1σ':>11}{'自助 +1σ':>11}{'MCMC 誤差':>12}")
    mcmc_err = {"logage": 0.017, "A_V": 0.001, "f_bin": 0.017, "alpha": 0.003}
    for i, name in enumerate(joint_fit.PARAM_NAMES):
        q = np.percentile(boots[:, i], [16, 50, 84])
        print(f"{name:<10}{best_full[i]:>10.4f}{q[1]:>10.4f}"
              f"{q[1]-q[0]:>11.4f}{q[2]-q[1]:>11.4f}"
              f"{mcmc_err[name]:>12.4f}")

    print(f"\n年齡 {10**best_full[0]/1e6:.1f} Myr"
          f"（自助 68% 區間 "
          f"{10**np.percentile(boots[:,0],16)/1e6:.1f} – "
          f"{10**np.percentile(boots[:,0],84)/1e6:.1f}）")

    print(f"\n自助樣本的參數相關矩陣：")
    cm = np.corrcoef(boots.T)
    print(f"{'':<10}" + "".join(f"{n:>10}" for n in joint_fit.PARAM_NAMES))
    for i, n in enumerate(joint_fit.PARAM_NAMES):
        print(f"{n:<10}" + "".join(f"{cm[i, j]:>10.2f}" for j in range(len(cm))))

    np.savez(HERE / "results" / "bootstrap.npz",
             boots=boots, best_full=best_full, corr=cm, dm=dm)
    print(f"\n寫入 results/bootstrap.npz")


if __name__ == "__main__":
    main()
