# -*- coding: utf-8 -*-
"""四參數聯合擬合：年齡、消光、雙星比例、IMF 斜率一次解出。

修正循序擬合（第 3→4→5 步）造成的問題：誤差被低估、看不到參數間的相關性。

用法：
    python run_joint.py --time-only     # 只測單次概似耗時，估算總時間
    python run_joint.py                 # 實際跑 MCMC
    python run_joint.py --steps 300 --procs 4    # 短鏈測試
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod  # noqa: E402
from pipeline import joint_fit                               # noqa: E402
from pipeline.table_compat import Table                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--time-only", action="store_true")
    ap.add_argument("--steps", type=int, default=None,
                    help="覆寫 config 的 n_steps")
    ap.add_argument("--procs", type=int, default=None,
                    help="平行行程數，預設為 CPU 核心數 - 1")
    a = ap.parse_args()

    cfg = cfgmod.load(a.config)
    c3, cj = cfg.step3_age, cfg.joint_fit

    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    gname = cj.get("grid_file") or (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat")
    print(f"isochrone 網格：{gname}")
    grid = isomod.load_grid(isomod.CACHE / gname)

    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0

    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    print(f"觀測 {ok.sum():,} 顆，距離模數 {dm:.4f}")

    # MCMC 用較少的合成星以換取速度
    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    model = joint_fit.JointModel(cfg, color[ok], mag[ok], grid, errmodel, dm)
    print(f"合成星數 {model.n_syn:,}")

    # 起始點：前四個用循序擬合的結果，金屬量與 q_gamma 用輪廓測試的最佳點
    f4 = np.load(HERE / "results" / "step4_fit.npz")
    f5 = np.load(HERE / "results" / "step5_imf.npz")
    start = np.array([float(f4["logage"]), float(f4["av"]),
                      float(f4["fbin"]), float(f5["alpha_forward"]),
                      0.05, -0.5])
    start = np.clip(start, model.bounds[:, 0] + 1e-3,
                    model.bounds[:, 1] - 1e-3)
    print("起始點：" + "  ".join(
        f"{n}={v:.3f}" for n, v in zip(joint_fit.PARAM_NAMES, start)))

    n_steps = a.steps or cj.n_steps
    t0 = time.time()
    lp = model.log_posterior(start)
    dt = time.time() - t0
    n_eval = cj.n_walkers * n_steps
    print(f"\n單次概似 {dt*1000:.0f} ms，起始點 lnP = {lp:.1f}")
    print(f"MCMC 需 {cj.n_walkers} walkers x {n_steps} steps "
          f"= {n_eval:,} 次，單執行緒預估 {n_eval*dt/60:.1f} 分鐘")
    if a.time_only:
        return
    # burn-in 不能超過鏈長的一半，否則短鏈測試會把樣本全部丟光
    n_burn = min(cj.n_burn, n_steps // 2)
    n_proc = a.procs if a.procs is not None else max(1, (os.cpu_count() or 2) - 1)
    print(f"\n開始取樣（{cj.n_walkers} walkers x {n_steps} steps，"
          f"{n_proc} 個行程，burn-in {n_burn}）…")

    t0 = time.time()
    if n_proc > 1:
        # 模型只在工人啟動時送一次，不要每步重送（見 joint_fit._init_worker）
        with joint_fit.make_pool(model, n_proc) as pool:
            res = joint_fit.run_mcmc(
                model, cj.n_walkers, n_steps, n_burn, start,
                cfg.step1_membership.random_seed, progress=False, pool=pool)
    else:
        res = joint_fit.run_mcmc(
            model, cj.n_walkers, n_steps, n_burn, start,
            cfg.step1_membership.random_seed, progress=False)
    elapsed = time.time() - t0
    print(f"取樣完成，{elapsed/60:.1f} 分鐘"
          f"（單執行緒需 {n_eval*dt/60:.1f} 分，加速 {n_eval*dt/elapsed:.1f}x）")

    print(f"\n接受率 {res['acceptance']:.3f}"
          f"（0.2–0.5 為佳；過低代表步伐太大，過高代表探索不足）")
    print(f"自相關時間 {np.array2string(res['tau'], precision=1)}")
    if np.isfinite(res["tau"]).any():
        n_eff = len(res["chain"]) / np.nanmax(res["tau"])
        print(f"有效樣本數約 {n_eff:.0f}"
              f"（低於 100 代表鏈太短，結論不可信）")

    s = joint_fit.summarise(res["chain"])
    print(f"\n{'參數':<10}{'中位數':>10}{'-1sigma':>10}{'+1sigma':>10}")
    for k, v in s.items():
        print(f"{k:<10}{v['median']:>10.3f}{v['minus']:>10.3f}{v['plus']:>10.3f}")
    age = 10 ** s["logage"]["median"] / 1e6
    age_lo = 10 ** s["logage"]["lo"] / 1e6
    age_hi = 10 ** s["logage"]["hi"] / 1e6
    print(f"\n年齡 {age:.1f} Myr（{age_lo:.1f} – {age_hi:.1f}）")

    print(f"\n參數相關矩陣（循序擬合看不到的東西）：")
    cm = joint_fit.correlation_matrix(res["chain"])
    print(f"{'':<10}" + "".join(f"{n:>10}" for n in joint_fit.PARAM_NAMES))
    for i, n in enumerate(joint_fit.PARAM_NAMES):
        print(f"{n:<10}" + "".join(f"{cm[i, j]:>10.2f}" for j in range(len(cm))))

    np.savez(HERE / "results" / "joint_fit.npz",
             chain=res["chain"], logp=res["logp"], best=res["best"],
             tau=res["tau"], dm=dm, corr=cm)
    print(f"\n寫入 results/joint_fit.npz")


if __name__ == "__main__":
    main()
