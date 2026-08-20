# -*- coding: utf-8 -*-
"""驗證排程項目：逐星雙星偵測的精確率／召回率（不是下游 alpha 偏差）。

**動機**（2026-08-11，使用者追問後決定實作，見 LIMITATIONS.md）：
先前比較 CMD／RUWE／NSS／前向模型幾種「雙星處理法」只看下游 alpha
偏差，是端到端的黑盒結果指標——知道 CMD 剔除系統性過矯正（+0.120），
但不知道是不是因為它偵測雙星本身就不準。這支腳本回答機制層級的問題：
CMD 偏移法、前向模型的逐星後驗機率（`per_star_binary_prob`），到底
各自抓雙星抓得多準（精確率／召回率），用已知真值的合成資料直接對答案。

**做得到跟做不到的**：`JointModel.synthesise(return_binary_flag=True)`
能給出合成星的雙星真值，所以 CMD 偏移法跟前向模型後驗機率都能測；
RUWE／Gaia NSS 沒有對應的正向模型（真實天測解算與官方目錄流程無法
簡單合成），這裡測不到，維持先前就有的已知限制。

**比較基準**：`per_star_binary_prob()` 的密度估計要用一個獨立生成的
「參考族群」建 Hess 圖上的單星／雙星密度，跟拿去驗證的「觀測」是
分開兩批生成的（不同亂數種子），避免用同一批資料的密度去驗證同一批
資料造成的樂觀偏誤。
"""
from __future__ import annotations

import argparse
import sys
import types
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline.table_compat import Table as _CompatTable  # noqa: E402
_a = types.ModuleType("astropy")
_t = types.ModuleType("astropy.table")
_t.Table = _CompatTable
_a.table = _t
sys.modules.setdefault("astropy", _a)
sys.modules.setdefault("astropy.table", _t)

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit, selection as selmod           # noqa: E402
from pipeline.step3_age import _Ext, draw_randoms             # noqa: E402
from pipeline.step4_binaries import per_star_binary_prob, flag_cmd_offset  # noqa: E402
from measure_overconfidence import GRID                       # noqa: E402
from injection_recovery import THETA_TRUE, make_fake          # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402


def precision_recall(pred: np.ndarray, truth: np.ndarray) -> tuple[float, float, int]:
    """pred/truth 是布林陣列，NaN 已在呼叫端濾掉。回傳 (精確率, 召回率, 樣本數)。"""
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    precision = tp / (tp + fp) if (tp + fp) > 0 else float("nan")
    recall = tp / (tp + fn) if (tp + fn) > 0 else float("nan")
    return precision, recall, len(truth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-obs", type=int, default=1078,
                    help="每次試驗的觀測星數，預設對齊真實 M45 樣本數")
    ap.add_argument("--n-ref", type=int, default=200_000,
                    help="建密度估計用的參考族群大小")
    ap.add_argument("--trials", type=int, default=5)
    ap.add_argument("--fbins", default="0.00,0.30,0.45,0.60")
    args = ap.parse_args()

    cfg = cfgmod.load()
    c2 = cfg.step2_cmd
    c4 = cfg.step4_binaries
    ext = _Ext(c2.ext_coeff_g, c2.ext_coeff_bp, c2.ext_coeff_rp)
    grid = isomod.load_grid(isomod.CACHE / GRID)
    sel = selmod.load(HERE / "data" / "selection.npz")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    color_real = np.asarray(clean["bp_rp"], float)
    mag_real = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color_real) & np.isfinite(mag_real)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - cfg.step3_age.parallax_zero_point)) - 5.0

    cfg._data["step3_age"]["n_synthetic"] = args.n_ref
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0
    base = joint_fit.JointModel(cfg, color_real[ok], mag_real[ok], grid,
                                errmodel, dm)
    base.selection = sel

    iso_true = isomod.isochrone_at(grid, THETA_TRUE[0], THETA_TRUE[4])
    av_true = THETA_TRUE[1]
    fbins = [float(x) for x in args.fbins.split(",")]
    print(f"參考族群 {args.n_ref:,} 顆、觀測 {args.n_obs:,} 顆、"
          f"每個 f_bin 跑 {args.trials} 次\n")

    print(f"{'f_bin':>7}{'判準':>10}{'精確率':>9}{'召回率':>9}{'樣本數':>8}")
    results = {}
    for fbin in fbins:
        th = THETA_TRUE.copy()
        th[2] = fbin
        cmd_p, cmd_r, fwd_p, fwd_r = [], [], [], []
        for t in range(args.trials):
            # 參考族群：獨立亂數種子，只用來建密度估計
            ref = joint_fit.JointModel(cfg, color_real[ok], mag_real[ok],
                                       grid, errmodel, dm)
            ref.selection = sel
            ref.n_syn = args.n_ref
            ref.draws = draw_randoms(args.n_ref,
                                     np.random.default_rng(9000 + 31 * t))
            out = ref.synthesise(th, return_binary_flag=True)
            if out is None:
                print(f"  f_bin={fbin:.2f} 第{t+1}次：參考族群生成失敗，跳過")
                continue
            ref_color, ref_mag, ref_is_bin = out
            pop = {"color": ref_color, "mag": ref_mag, "is_binary": ref_is_bin}

            # 觀測：獨立亂數種子，帶真值
            obs_color, obs_mag, obs_is_bin = make_fake(
                base, th, args.n_obs, seed=6000 + 31 * t,
                selection=sel, return_binary_flag=True)
            obs_is_bin = obs_is_bin.astype(bool)

            # CMD 偏移法
            cmd_flag = flag_cmd_offset(obs_color, obs_mag, iso_true, dm,
                                       av_true, ext, c4.cmd_offset_threshold)
            p, r, n = precision_recall(cmd_flag, obs_is_bin)
            cmd_p.append(p); cmd_r.append(r)

            # 前向模型後驗機率
            p_bin = per_star_binary_prob(obs_color, obs_mag, pop, cfg)
            valid = np.isfinite(p_bin)
            fwd_flag = p_bin[valid] > c4.forward_prob_threshold
            p2, r2, n2 = precision_recall(fwd_flag, obs_is_bin[valid])
            fwd_p.append(p2); fwd_r.append(r2)

        def fmt(vals):
            v = np.array(vals, float)
            v = v[np.isfinite(v)]
            return (float(v.mean()), float(v.std())) if len(v) else (float("nan"), 0.0)

        cp, cp_sd = fmt(cmd_p)
        cr, cr_sd = fmt(cmd_r)
        fp, fp_sd = fmt(fwd_p)
        fr, fr_sd = fmt(fwd_r)
        results[fbin] = dict(cmd_p=cmd_p, cmd_r=cmd_r, fwd_p=fwd_p, fwd_r=fwd_r)
        print(f"{fbin:>7.2f}{'CMD偏移':>10}{cp:>9.3f}{cr:>9.3f}{args.n_obs:>8}")
        print(f"{'':>7}{'前向後驗':>10}{fp:>9.3f}{fr:>9.3f}{args.n_obs:>8}")

    print("\n判讀：精確率＝標記為雙星裡真的是雙星的比例；召回率＝真雙星裡")
    print("被抓到的比例。CMD 偏移法先驗上只抓得到質量比高的組合，召回率")
    print("預期偏低是設計使然，不是失準；前向後驗機率若召回率也不高，")
    print("代表這件事本質上難（單星序附近的低質量比雙星光度差異太小），")
    print("不是哪個判準的實作問題。")

    np.savez(HERE / "results" / "verify_binary_detection.npz",
             fbins=np.array(fbins),
             **{f"f{fb}::{k}": np.array(v) for fb, d in results.items()
                for k, v in d.items()})
    print("\n寫入 results/verify_binary_detection.npz")


if __name__ == "__main__":
    main()
