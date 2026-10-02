# -*- coding: utf-8 -*-
"""四參數聯合擬合：年齡、消光、雙星比例、IMF 斜率一次解出。

修正循序擬合（第 3→4→5 步）造成的問題：誤差被低估、看不到參數間的相關性。

用法：
    python run_joint.py --time-only     # 只測單次概似耗時，估算總時間
    python run_joint.py                 # 實際跑 MCMC
    python run_joint.py --steps 300 --procs 4    # 短鏈測試

======================================================================
【這支程式在做什麼】
======================================================================
用 MCMC（emcee）對 joint_fit.py 的前向模型取樣，目標是得到每個參數的完整
後驗分布與參數之間的相關係數（網格搜尋只給一個最佳點）。
輸出：results/joint_fit.npz（MCMC 樣本鏈、對數後驗、最佳點、自相關時間、
距離模數、相關係數矩陣）
⚠ 這條鏈**從未收斂**：自相關時間 τ = 822–1454 步，鏈長遠不足 50τ，
  誤差棒與相關矩陣都不可引用，只有中心值可參考（LIMITATIONS.md C11、
  results/RESULTS_LOG.md）。目前頭條數字來自 fit_real.py 的網格搜尋。
⚠ 跟頭條 fit_real.py 的設定不同，結果不能直接比：
  - 沒有掛選擇函數（model.selection 維持 None）、沒有差異消光 dav
  - 沒有排除 step5_imf.py 名單裡的兩顆已確認非成員
  - 網格檔用 config.toml [joint_fit] 的 grid_file
    （parsec_v2.0_gaiaEDR3_logt7.6-8.4s0.05_mh-0.5-0.3s0.05.dat）
  - 起始點取自舊版循序流程的 results/step4_fit.npz 與 step5_imf.npz
    （兩個檔都要先存在）
標題寫「四參數」，實際取樣的是 joint_fit.PARAM_NAMES 的六個參數。

======================================================================
【(a) 引用的外部函式庫】
======================================================================
Python 標準庫：
  argparse, os, sys, time, pathlib   參數、CPU 數、路徑、計時
第三方套件：
  numpy（np）   np.load／np.savez 讀寫 .npz；np.clip 把起始點夾在先驗範圍內；
                np.array2string 把陣列印成文字
本專案其他模組：
  pipeline/config.py        cfgmod.load()：讀 config.toml
  pipeline/isochrones.py    isomod.load_grid()：讀等時線網格
  pipeline/joint_fit.py     JointModel（前向模型）、run_mcmc()（emcee 取樣）、
                            make_pool()（多行程）、summarise()（中位數與 16/84
                            百分位）、correlation_matrix()（相關係數矩陣）、
                            PARAM_NAMES（六個參數名稱）
  pipeline/table_compat.py  Table：簡易表格

======================================================================
【(b) 用到的參數與意義】
======================================================================
命令列參數：
  --config      設定檔路徑，預設 config.toml
  --time-only   只算一次概似、估計總耗時就結束
  --steps       覆寫每個走者要走的步數（config 預設 6000）
  --procs       平行行程數，預設 CPU 核心數 − 1
config.toml [joint_fit]：
  n_walkers = 48       同時取樣的走者數
  n_steps = 6000       每個走者走幾步
  n_burn = 2000        丟掉前幾步暖身（不超過步數的一半）
  n_synthetic = 40000  MCMC 用的合成星數（比網格搜尋少，換速度）
  grid_file            等時線網格檔
  先驗範圍見 joint_fit.py 檔頭
寫死的起始值：金屬量 0.05、q_gamma −0.5

======================================================================
【(c) 真正在執行操作的核心】（行號以這個版本為準，改程式後要更新）
======================================================================
  核心 1｜第 114–155 行｜讀資料、建立前向模型、決定起始點
  核心 2｜第 157–189 行｜估計耗時，然後跑 MCMC（可多行程）
  核心 3｜第 191–223 行｜檢查接受率與自相關時間、印出後驗摘要與相關矩陣、存檔

======================================================================
【(d) 整體流程】
======================================================================
  讀 config → 讀 cmd_members.csv、errmodel.npz、等時線網格
    → 視差中位數算距離模數 → 取顏色與 G 星等
    → 合成星數改成 40000 → 建 JointModel
    → 起始點：年齡、消光、雙星比例取自 step4_fit.npz，α 取自 step5_imf.npz，
      金屬量 0.05、q_gamma −0.5，夾進先驗範圍內
    → 算一次對數後驗，估計總耗時（--time-only 到此結束）
    → 48 個走者在起始點附近撒開 → 各走 6000 步 → 丟掉前 2000 步
    → 印出接受率、自相關時間、有效樣本數
    → 印出每個參數的中位數 ± 1σ、年齡（Myr）、6×6 相關矩陣
    → 存 results/joint_fit.npz
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

# ↓ repo 根目錄（本檔在 scripts/drivers/，往上三層），加進 import 路徑
HERE = Path(__file__).resolve().parent.parent.parent
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

    # ═══════════════ 核心 1：讀資料、建模型、決定起始點 ═══════════════
    cfg = cfgmod.load(a.config)
    # ↓ c3：config 的 [step3_age]；cj：[joint_fit]
    c3, cj = cfg.step3_age, cfg.joint_fit

    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    # ↓ 網格檔：優先用 [joint_fit] grid_file，沒有才依 [step3_age] 範圍組檔名
    gname = cj.get("grid_file") or (
        f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
        f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat")
    print(f"isochrone 網格：{gname}")
    grid = isomod.load_grid(isomod.CACHE / gname)

    # ↓ 距離模數：視差中位數扣零點 → 距離 → m − M
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0

    # ↓ 觀測顏色與 G 星等；ok：兩者都有值的星
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    print(f"觀測 {ok.sum():,} 顆，距離模數 {dm:.4f}")

    # MCMC 用較少的合成星以換取速度
    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    # ↓ 建立前向模型（沒有掛選擇函數，見檔頭說明）
    model = joint_fit.JointModel(cfg, color[ok], mag[ok], grid, errmodel, dm)
    print(f"合成星數 {model.n_syn:,}")

    # 起始點：前四個用循序擬合的結果，金屬量與 q_gamma 用輪廓測試的最佳點
    f4 = np.load(HERE / "results" / "step4_fit.npz")
    f5 = np.load(HERE / "results" / "step5_imf.npz")
    # ↓ 順序對應 PARAM_NAMES：logage、A_V、f_bin、alpha、MH、q_gamma
    start = np.array([float(f4["logage"]), float(f4["av"]),
                      float(f4["fbin"]), float(f5["alpha_forward"]),
                      0.05, -0.5])
    # ↓ 起始點夾在先驗範圍內側一點點，避免一開始就落在禁區
    start = np.clip(start, model.bounds[:, 0] + 1e-3,
                    model.bounds[:, 1] - 1e-3)
    print("起始點：" + "  ".join(
        f"{n}={v:.3f}" for n, v in zip(joint_fit.PARAM_NAMES, start)))

    # ═══════════════ 核心 2：估計耗時並跑 MCMC ═══════════════
    n_steps = a.steps or cj.n_steps
    # ↓ 量一次對數後驗要多久，乘上總評估次數 = 單執行緒預估時間
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
        # ↓ run_mcmc(模型, 走者數, 步數, 暖身步數, 起始點, 亂數種子, …)
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

    # ═══════════════ 核心 3：診斷、摘要、存檔 ═══════════════
    # ↓ 接受率：提議的下一步被接受的比例
    print(f"\n接受率 {res['acceptance']:.3f}"
          f"（0.2–0.5 為佳；過低代表步伐太大，過高代表探索不足）")
    print(f"自相關時間 {np.array2string(res['tau'], precision=1)}")
    if np.isfinite(res["tau"]).any():
        # ↓ 有效樣本數 ≈ 總樣本數 ÷ 最大的自相關時間
        n_eff = len(res["chain"]) / np.nanmax(res["tau"])
        print(f"有效樣本數約 {n_eff:.0f}"
              f"（低於 100 代表鏈太短，結論不可信）")

    # ↓ 每個參數的中位數與 16/84 百分位（= 中心值 ± 1σ）
    s = joint_fit.summarise(res["chain"])
    print(f"\n{'參數':<10}{'中位數':>10}{'-1sigma':>10}{'+1sigma':>10}")
    for k, v in s.items():
        print(f"{k:<10}{v['median']:>10.3f}{v['minus']:>10.3f}{v['plus']:>10.3f}")
    # ↓ 年齡從 log10(年) 換回百萬年
    age = 10 ** s["logage"]["median"] / 1e6
    age_lo = 10 ** s["logage"]["lo"] / 1e6
    age_hi = 10 ** s["logage"]["hi"] / 1e6
    print(f"\n年齡 {age:.1f} Myr（{age_lo:.1f} – {age_hi:.1f}）")

    # ↓ 6×6 相關係數矩陣（Pearson 相關係數只量得到線性關係，非線性的參數牽連看不出來）
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
