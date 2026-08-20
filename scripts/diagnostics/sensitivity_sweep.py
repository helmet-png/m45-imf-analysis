# -*- coding: utf-8 -*-
"""D2：對 config.toml 裡未測過的設定做敏感度掃描，量頭條 alpha 怎麼變。

**範圍說明**（WORK_BOARD.md D2）：`config.toml` 裡列了 7 個從沒做過敏感度
測試的設定（`pca_dims`、`stars_per_cluster`、`clustering_method`、
`inner_loop_runs`、`hess_color_range`／`hess_mag_range`、`min_flux_snr_bp`、
`membership_threshold`）。這支腳本先示範影響面最廣的一個：
**`membership_threshold`**（哪些星被算進「成員」，直接決定樣本本身）。

**為什麼先做這個、不是 `stars_per_cluster`**：`membership_threshold` 只是
對 `results/baseline.dat`（pyUPMASK 已經算出的成員機率）重新設門檻，
不需要重跑 pyUPMASK 本身，第 2、3 步（測光篩選＋前向模型擬合）用現有的
`pipeline` 模組直接可做。`stars_per_cluster` 是 pyUPMASK 內部分群參數，
改它必須真的重跑 pyUPMASK 聚類——本機（2026-08 這台 Acer AI 16）還沒有
`pyUPMASK/` 目錄，沒有驗證過能不能跑，貿然宣稱測過會是假結果。
`--target stars_per_cluster` 因此只做**可行性檢查**（偵測 `pyUPMASK/` 是否
存在、要不要透過 `run_variant.py` 重跑），查不到就明講「這台機器做不了」，
不猜一個數字出來。

**方法**：對每個 `membership_threshold` 值，重新套用門檻 -> 重跑第 2 步
（測光品質篩選）-> 用 config C（選擇函數＋差異消光）跑一次前向模型擬合，
量 alpha 怎麼變。精修程度比 headline 低（預設 `--refines 3`），這是敏感度
掃描不是最終數字，跟 `profile_outlierfrac.py`／`profile_lowmass.py` 同一個
精神：只要看得出量級，不需要 headline 等級的精度。

用法：
    python scripts/diagnostics/sensitivity_sweep.py --target membership_threshold
    python scripts/diagnostics/sensitivity_sweep.py --target stars_per_cluster
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod, step2_cmd  # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import COARSE, multi_stage_best       # noqa: E402
from scripts.drivers.run_pipeline import load_members          # noqa: E402

ALPHA_STAT_SIGMA = 0.144   # 注入回收量到的統計誤差（S3F），當比較尺度

# 現行值 0.7。掃描範圍涵蓋「門檻放鬆會混進更多場星污染」跟「門檻收緊會
# 砍掉邊緣真成員、放大統計誤差」兩個方向，取 pyUPMASK 常見的判定帶。
MEMBERSHIP_THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]


def sweep_membership_threshold(args, n_proc, refines):
    cfg = cfgmod.load()
    baseline_path = HERE / "results" / "baseline.dat"
    if not baseline_path.exists():
        sys.exit(f"找不到 {baseline_path}——這是 pyUPMASK 第 1 步的輸出，"
                 f"必須先有這個檔案才能重新套用門檻。")

    thresholds = ([float(x) for x in args.values.split(",")] if args.values
                 else MEMBERSHIP_THRESHOLDS)
    grid = isomod.load_grid(isomod.CACHE / GRID)
    sel_default = selmod.load(HERE / "data" / "selection.npz")

    print(f"對 {baseline_path.name} 重新套用 {len(thresholds)} 個成員機率門檻："
          f"{thresholds}\n")

    results = {}
    for thr in thresholds:
        t0 = time.time()
        cfg._data["step1_membership"]["membership_threshold"] = thr
        members = load_members(cfg)
        clean, errmodel = step2_cmd.run(cfg, members)

        c3 = cfg.step3_age
        plx = np.asarray(clean["parallax"], float)
        dm = 5.0 * np.log10(1000.0 / (np.median(plx)
                                      - c3.parallax_zero_point)) - 5.0
        color = np.asarray(clean["bp_rp"], float)
        mag = np.asarray(clean["phot_g_mean_mag"], float)
        ok = np.isfinite(color) & np.isfinite(mag)
        color, mag = color[ok], mag[ok]
        n_obs = len(color)

        cfg._data["step3_age"]["n_synthetic"] = args.n_syn
        cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
        # selection.npz 是用現行門檻（0.7）的樣本迴歸出來的係數，門檻一變
        # 樣本就變了，理論上該重新迴歸。**這裡刻意沿用同一份**——重新迴歸
        # 選擇函數需要另一輪測光品質篩選統計，超出這次「先看量級」的範圍，
        # 且選擇函數係數對樣本邊界變化預期是二階效應（見 LIMITATIONS.md）。
        # 這是已知的簡化，不是疏忽，量出的 alpha 敏感度可能因此略為低估。
        m = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
        m.selection = sel_default
        m.bounds = m.bounds[:6].copy()
        m.enable_dav_fit(0.0, args.dav_max)

        best, lp, bounds = multi_stage_best(
            m, COARSE, refines, n_proc,
            extra_axis=np.arange(0.0, args.dav_max + 1e-9, args.dav_max / 4),
            allow_wall=(5, 6))
        results[thr] = best
        print(f"  threshold={thr:.2f}  n_obs={n_obs:,}  alpha={best[3]:.3f}  "
              f"logage={best[0]:.3f}  A_V={best[1]:.3f}  lnP={lp:.1f}  "
              f"({time.time()-t0:.0f}s)", flush=True)

    print(f"\n{'='*70}\nalpha 對 membership_threshold 的敏感度\n{'='*70}")
    print(f"{'threshold':>10}{'alpha':>9}")
    alphas = np.array([results[t][3] for t in thresholds])
    for t in thresholds:
        print(f"{t:>10.2f}{results[t][3]:>9.3f}")
    span = float(alphas.max() - alphas.min())
    print(f"\nalpha 跨度（掃過 threshold={min(thresholds)}-{max(thresholds)}）"
          f"= {span:.3f}")
    print(f"對照注入回收統計誤差 {ALPHA_STAT_SIGMA:.3f} "
          f"-> {span/ALPHA_STAT_SIGMA:.1f} 倍")
    print("\n判讀：倍數遠大於 1，代表成員門檻的選擇是重要的誤差來源，該收窄")
    print("      判定帶或做敏感度加權；倍數接近或小於 1，代表現行 0.7 這個")
    print("      選擇在這個範圍內不是主要誤差來源，記入 LIMITATIONS.md D2。")

    out = HERE / "results" / "sensitivity_membership_threshold.npz"
    np.savez(out, thresholds=np.array(thresholds),
             **{f"t{t:g}": results[t] for t in thresholds})
    print(f"\n寫入 {out}")


def check_stars_per_cluster(args):
    """`stars_per_cluster` 需要真的重跑 pyUPMASK 聚類，不是重新套用門檻能
    做到的。這裡只做可行性檢查，查不到 pyUPMASK 就誠實報告，不猜數字。
    """
    pyupmask_dir = HERE / "pyUPMASK"
    prepared = list((HERE / "prepared").glob("*.dat")) if (
        HERE / "prepared").exists() else []
    print("stars_per_cluster 可行性檢查（這個設定改變 pyUPMASK 內部分群，"
          "無法只靠重新套用門檻測出敏感度，需要真的重跑聚類）：")
    print(f"  pyUPMASK/ 目錄存在：{pyupmask_dir.exists()}")
    print(f"  prepared/ 底下的輸入檔：{len(prepared)} 個"
          f"{[p.name for p in prepared[:3]]}")
    if not pyupmask_dir.exists():
        print("\n結論：這台機器沒有 pyUPMASK/，做不了這個掃描。**不要編造"
              "一個敏感度數字**——沒跑過就是沒跑過。")
        print("下一步：確認 pyUPMASK 能在這台機器（Acer AI 16，x64）跑起來"
              "（README.md 的安裝步驟），驗證通過後用")
        print("  python scripts/drivers/run_variant.py --name spc_<N> "
              "--input <prepared檔> ...")
        print("對 2-3 個 stars_per_cluster 值各跑一次（該腳本目前沒有直接"
              "暴露 stars_per_cluster 旗標，需要先比照 --pca-dims 的模式"
              "加一個），再接上面 membership_threshold 那條路徑的第 2、3 步"
              "算 alpha。這步留給認領的下一個 session，見 WORK_BOARD.md D2。")
        return
    print("\npyUPMASK/ 存在，可以嘗試——但這支腳本目前沒有自動化這條路徑"
          "（run_variant.py 尚未暴露 --stars-per-cluster 旗標），請先確認"
          "環境能跑，再回來擴充這支腳本。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True,
                    choices=["membership_threshold", "stars_per_cluster"])
    ap.add_argument("--values", default=None,
                    help="逗號分隔，覆寫預設掃描點（僅 membership_threshold）")
    ap.add_argument("--procs", type=int, default=None)
    ap.add_argument("--n-syn", type=int, default=40000)
    ap.add_argument("--refines", default="3")
    ap.add_argument("--dav-max", type=float, default=0.6)
    args = ap.parse_args()
    n_proc = args.procs or (os.cpu_count() or 1)
    refines = [int(x) for x in args.refines.split(",") if x.strip()]

    if args.target == "membership_threshold":
        sweep_membership_threshold(args, n_proc, refines)
    else:
        check_stars_per_cluster(args)


if __name__ == "__main__":
    main()
