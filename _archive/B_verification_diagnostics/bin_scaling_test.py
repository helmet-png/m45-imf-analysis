# -*- coding: utf-8 -*-
"""檢驗「2,000 個格子被當成 2,000 份獨立證據」這個診斷到底成不成立。

**為什麼要先檢驗這件事**

上一輪的結論是：Poisson-Hess 概似把 CMD 切成 2,000 格、當成 2,000 份獨立證據，
但實際只有 1,078 顆星，所以概似過度自信；根治方法是改用無分箱概似。

這個推論有一個問題。分箱**不會**憑空製造資訊：把資料丟進直方圖是一種有損壓縮，
格子越粗損失越多。當格距趨近於零時，分箱 Poisson 概似會收斂到無分箱概似 ——

    sum_i [ n_i * ln(N rho_i dA) - N rho_i dA ]  --(dA->0)-->  sum_j ln rho(x_j) + const

也就是說「無分箱」正是「格子無限多」的極限，是資訊量最大的那一端，不是最小的那一端。
若真的是格子數在灌水信心，那換成無分箱只會更糟。

**這支程式怎麼判**

固定同一批觀測星、同一組參數、同一批共用亂數，只改 Hess 圖的格子數，
量概似峰有多窄（用 alpha 與 MH 兩個方向）。峰寬換算成 sigma：

  * 若「格子數灌水」成立 -> 資訊量正比於格子數 -> sigma 正比於 1/sqrt(n_bins)，
    從 120 格到 32,000 格應該窄掉約 16 倍。
  * 若分箱只是有損壓縮 -> sigma 隨格子變細而下降，但會**收斂**到無分箱的值，
    不會無止境變窄。

無分箱那一列用合成星團的核密度估計直接算 sum_j ln rho(x_j)，
是同一批合成星、同一個離群成分，唯一的差別就是概似形式。

輸出的 sigma 是「概似自己宣稱的統計誤差」，不是真實誤差。
這裡比的是它隨格子數怎麼變，不是它對不對。
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

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit                                # noqa: E402
from pipeline.step3_age import hess, poisson_loglike          # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402

GRID = "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"

# 參考點取自高斯先驗版六參數 MCMC 的後驗中位數（logs/joint_gauss.log）。
# 掃描時只動一個參數，其餘固定在這裡。
THETA0 = np.array([8.184, 0.049, 0.545, 2.331, 0.181, -0.722])

# 要比較的分箱方式（顏色格數, 星等格數）。目前正式使用的是 40x50 = 2,000。
BINNINGS = [(10, 12), (20, 25), (40, 50), (80, 100), (160, 200)]

OUTLIER_FRAC = 0.01     # 與 poisson_loglike 的預設一致

# 實測的統計誤差，用來把「換格子數造成的中心值移動」換算成幾倍統計誤差。
# 來源是注入回收測試（S3F，最乾淨的一種，不受切半實驗的貼牆問題影響）。
STAT_SIGMA = {"alpha": 0.144, "MH": 0.050}


def unbinned_loglike(obs_c, obs_m, syn_c, syn_m, crange, mrange,
                     bw=None, n_kde=20000, rng=None):
    """無分箱概似：對每顆觀測星取模型密度的對數再相加。

    模型密度用合成星團的高斯核密度估計。這是「格子無限細」的極限，
    項數恰好等於觀測星數（1,078），不會有任何一份證據被重複採計。

    代價是引入帶寬 bw 這個新的任意參數（bw=None 用 Scott 法則自動選）。
    離群成分與分箱版一樣是**加法**混入，不是摺積，才不會把雙星序抹掉。
    """
    from scipy.stats import gaussian_kde

    if len(syn_c) > n_kde:
        r = rng if rng is not None else np.random.default_rng(0)
        pick = r.choice(len(syn_c), n_kde, replace=False)
        syn_c, syn_m = syn_c[pick], syn_m[pick]
    kde = gaussian_kde(np.vstack([syn_c, syn_m]), bw_method=bw)
    rho = kde(np.vstack([obs_c, obs_m]))
    area = (crange[1] - crange[0]) * (mrange[1] - mrange[0])
    mix = (1.0 - OUTLIER_FRAC) * rho + OUTLIER_FRAC / area
    return float(np.sum(np.log(mix)))


def sigma_from_curve(x, y, half_width):
    """由概似曲線求「概似自己宣稱的 sigma」。

    在峰值附近 half_width 範圍內配拋物線 y = ymax - (x-x0)^2 / (2 sigma^2)。
    用配線而不是單點差值，是因為曲面有 +-10 lnL 的取樣抖動，
    單點差值會被抖動主導。
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    k = int(np.argmax(y))
    sel = np.abs(x - x[k]) <= half_width
    if sel.sum() < 5:
        return np.nan, x[k]
    c = np.polyfit(x[sel] - x[k], y[sel], 2)
    if c[0] >= 0:                       # 峰是凹的才有意義
        return np.nan, x[k]
    return float(np.sqrt(-0.5 / c[0])), float(x[k] - 0.5 * c[1] / c[0])


# ---- 平行：工人各算一個掃描點的合成星團，回傳所有概似變體 ----
_W = {}


def _init(model, obs_c, obs_m, crange, mrange, bws):
    _W.update(model=model, obs_c=obs_c, obs_m=obs_m,
              crange=crange, mrange=mrange, bws=bws)


def _eval(job):
    """job = (掃描維度 index, 該維度的值)。回傳各概似變體的 lnL。"""
    dim, val = job
    th = THETA0.copy()
    th[dim] = val
    syn = _W["model"].synthesise(th)
    if syn is None:
        return val, {}
    sc, sm = syn
    out = {}
    for nc, nm in BINNINGS:
        oh = hess(_W["obs_c"], _W["obs_m"], nc, nm, _W["crange"], _W["mrange"])
        mh_ = hess(sc, sm, nc, nm, _W["crange"], _W["mrange"])
        out[f"bin{nc*nm}"] = poisson_loglike(oh, mh_, len(_W["obs_c"]))
    for bw in _W["bws"]:
        tag = "kde-scott" if bw is None else f"kde-{bw}"
        out[tag] = unbinned_loglike(_W["obs_c"], _W["obs_m"], sc, sm,
                                    _W["crange"], _W["mrange"], bw=bw)
    return val, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--procs", type=int, default=None)
    # 下面三個是「模型修好之後用同一把尺重測」用的。
    # 中心值對格子數的敏感度原本是統計誤差的 24 倍（MH）、30 倍（alpha）；
    # 補上選擇函數與差異消光之後應該掉下來，掉多少就是修得多好。
    ap.add_argument("--selection", action="store_true",
                    help="啟用測光品質選擇函數")
    ap.add_argument("--dav", type=float, default=0.0,
                    help="差異消光的星對星散布（0 = 關閉）")
    ap.add_argument("--n-syn", type=int, default=None,
                    help="覆寫合成星數。格子開細時每格星數不能太少")
    ap.add_argument("--theta", default=None,
                    help="逗號分隔的六個參數，覆寫掃描中心。"
                         "模型改了之後最佳解會移動，中心要跟著移")
    ap.add_argument("--tag", default="",
                    help="輸出檔名的後綴，避免覆蓋掉對照組的結果")
    args = ap.parse_args()
    n_proc = args.procs or (os.cpu_count() or 1)
    if args.theta:
        THETA0[:] = [float(x) for x in args.theta.split(",")]

    cfg = cfgmod.load()
    c3, cj = cfg.step3_age, cfg.joint_fit
    clean = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
    errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))
    grid = isomod.load_grid(isomod.CACHE / GRID)
    plx = np.asarray(clean["parallax"], float)
    dm = 5.0 * np.log10(1000.0 / (np.median(plx) - c3.parallax_zero_point)) - 5.0
    color = np.asarray(clean["bp_rp"], float)
    mag = np.asarray(clean["phot_g_mean_mag"], float)
    ok = np.isfinite(color) & np.isfinite(mag)
    color, mag = color[ok], mag[ok]

    n_syn = args.n_syn or cj.n_synthetic
    cfg._data["step3_age"]["n_synthetic"] = n_syn
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0     # 只測概似，關掉先驗

    crange, mrange = tuple(c3.hess_color_range), tuple(c3.hess_mag_range)
    inside = ((color >= crange[0]) & (color < crange[1])
              & (mag >= mrange[0]) & (mag < mrange[1]))
    color, mag = color[inside], mag[inside]
    print(f"觀測 {len(color):,} 顆（落在 Hess 範圍內），距離模數 {dm:.4f}")

    model = joint_fit.JointModel(cfg, color, mag, grid, errmodel, dm)
    model.dav = args.dav
    if args.selection:
        from pipeline import selection as selmod
        model.selection = selmod.load(HERE / "data" / "selection.npz")
    print(f"模型設定：選擇函數 {'開' if args.selection else '關'}、"
          f"dav = {args.dav}、n_synthetic = {n_syn:,}")
    print("掃描中心：" + "  ".join(
        f"{n}={v:.3f}" for n, v in zip(joint_fit.PARAM_NAMES, THETA0)))
    # 格子太細時，模型端每格的合成星數會掉到個位數，Poisson 概似就被
    # 模型自己的蒙地卡羅雜訊主導，量到的窄不是資料給的。先把這個數字列出來。
    print("\n每格平均星數（模型端 / 觀測端）：")
    for nc, nm in BINNINGS:
        print(f"  {nc:>3}x{nm:<4} = {nc*nm:>6,} 格   "
              f"模型 {n_syn/(nc*nm):>7.1f}   觀測 {len(color)/(nc*nm):>6.2f}")
    bws = [None, 0.15, 0.30]
    variants = [f"bin{nc*nm}" for nc, nm in BINNINGS] + \
               ["kde-scott"] + [f"kde-{b}" for b in bws if b is not None]

    # alpha 是解析套用的冪次，可以連續掃；
    # MH 受限於 isochrone 網格步長 0.05（_isochrone 取最近格點），
    # 掃更細只會得到階梯狀曲線，所以按網格步長掃。
    scans = [
        # (參數 index, 名稱, 掃描座標, 配拋物線的半寬)
        (3, "alpha", np.arange(1.50, 2.901, 0.02), 0.15),
        (4, "MH",    np.arange(-0.15, 0.451, 0.05), 0.16),
    ]

    from multiprocessing import Pool
    results = {}
    with Pool(n_proc, initializer=_init,
              initargs=(model, color, mag, crange, mrange, bws)) as pool:
        for dim, name, xs, hw in scans:
            t0 = time.time()
            jobs = [(dim, float(v)) for v in xs]
            got = pool.map(_eval, jobs, chunksize=1)
            curves = {v: np.array([g[1].get(v, np.nan) for g in got])
                      for v in variants}
            results[name] = (xs, curves, hw)
            print(f"{name} 掃描 {len(xs)} 點完成（{time.time()-t0:.0f}s）")

    print(f"\n{'='*78}")
    print("概似自己宣稱的 sigma（不是真實誤差，這裡只看它隨格子數怎麼變）")
    print(f"{'='*78}")
    for name, (xs, curves, hw) in results.items():
        print(f"\n--- 掃描 {name} ---")
        print(f"{'概似形式':<14}{'格數/帶寬':>12}{'峰位':>10}"
              f"{'sigma':>10}{'相對 2000 格':>14}")
        ref = None
        rows = []
        for v in variants:
            s, pk = sigma_from_curve(xs, curves[v], hw)
            rows.append((v, pk, s))
            if v == "bin2000":
                ref = s
        for v, pk, s in rows:
            nb = v.replace("bin", "").replace("kde-", "KDE ")
            rel = (s / ref) if (ref and np.isfinite(s) and np.isfinite(ref)) \
                else np.nan
            print(f"{v:<14}{nb:>12}{pk:>10.3f}{s:>10.4f}{rel:>13.2f}x")

        # 若「格子數灌水」成立，sigma 應正比於 1/sqrt(n_bins)
        nb = np.array([nc * nm for nc, nm in BINNINGS], float)
        sg = np.array([sigma_from_curve(xs, curves[f'bin{int(b)}'], hw)[0]
                       for b in nb])
        good = np.isfinite(sg)
        if good.sum() >= 3:
            slope = np.polyfit(np.log(nb[good]), np.log(sg[good]), 1)[0]
            print(f"\n  sigma 對格子數的冪次 = {slope:+.3f}"
                  f"（「格子灌水」預測 -0.50，「分箱只是有損壓縮」預測趨近 0）")

        # **這一段才是判準。** 換格子數是一個不帶物理內容的分析選擇，
        # 中心值不該跟著跑。跑多少，就是系統誤差有多大。
        # 只算「可辯護區間」內的格數 —— 模型每格星數低於 20 顆時，
        # 概似被模型自己的取樣雜訊主導，那時中心值跑掉是已知的人工產物。
        ok_bins = [(nc, nm) for nc, nm in BINNINGS if n_syn / (nc * nm) >= 20]
        peaks = [sigma_from_curve(xs, curves[f"bin{nc*nm}"], hw)[1]
                 for nc, nm in ok_bins]
        peaks = np.array([p for p in peaks if np.isfinite(p)])
        stat = STAT_SIGMA.get(name)
        if len(peaks) >= 2:
            spread = float(peaks.max() - peaks.min())
            print(f"\n  可辯護區間（每格 >=20 顆）："
                  f"{', '.join(f'{a*b:,}' for a, b in ok_bins)} 格")
            print(f"  中心值跨度 = {spread:.3f}"
                  f"（{'  '.join(f'{p:.3f}' for p in peaks)}）")
            if stat:
                print(f"  對照實測統計誤差 {stat:.3f} -> "
                      f"**{spread/stat:.1f} 倍**"
                      f"（修好前 alpha 是 30 倍、MH 是 24 倍；"
                      f"目標是降到 1 倍附近，剩下的算系統誤差）")

    np.savez(HERE / "results" / f"bin_scaling{args.tag}.npz",
             **{f"{n}_x": r[0] for n, r in results.items()},
             **{f"{n}_{v}": r[1][v] for n, r in results.items()
                for v in variants})
    print(f"\n寫入 results/bin_scaling{args.tag}.npz")


if __name__ == "__main__":
    main()
