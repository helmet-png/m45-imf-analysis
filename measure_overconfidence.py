# -*- coding: utf-8 -*-
"""實測概似函數高估了多少信心。

**問題**：我們把 1,078 顆星切成 2,000 個格子，Poisson 概似把每一格當成
一份獨立證據。但格子數比星數還多，而且相鄰格子是連動的（模型主序位置一動，
一整排格子一起動）。等於把同一份證詞重複採計，導致概似「過度自信」——
實測後果是高斯先驗（中心 -0.03、sigma 0.10）完全推不動後驗（跑到 +0.181），
因為先驗懲罰只有 -2.2 而概似差異數百。

**測法**：把觀測星隨機切成兩半，各自獨立擬合。
兩半的答案差多少，反映的是真實的統計不確定度。

  每半的樣本量是全體的一半 -> sigma_half = sigma_full * sqrt(2)
  兩個獨立估計的差 -> |a1 - a2| 的期望值約 sigma_half * sqrt(2) = 2 * sigma_full
  所以 sigma_full 約等於 |a1 - a2| / 2

重複多次隨機切分取統計，再跟 MCMC 報的誤差棒相除，就是高估倍數。

用網格搜尋而非優化器：概似曲面有尖刺，優化器會卡住（先前自助法就是這樣失敗的），
網格只是「某幾格值偏高」，仍能找到整體最佳。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import config as cfgmod, isochrones as isomod   # noqa: E402
from pipeline import joint_fit                                # noqa: E402
from pipeline.table_compat import Table                       # noqa: E402

GRID = "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat"
# MCMC（高斯先驗版）報出的 1 sigma 誤差棒，拿來當比較基準
MCMC_ERR = {"logAge": 0.084, "A_V": 0.060, "f_bin": 0.043,
            "alpha": 0.072, "MH": 0.081, "q_gamma": 0.061}


def _decode(k, axes, strides):
    """把攤平後的線性索引還原成各維座標。"""
    th = np.empty(len(axes))
    rem = k
    for d in range(len(axes)):
        i, rem = divmod(rem, strides[d])
        th[d] = axes[d][i]
    return th


def _strides(axes):
    sizes = [len(a) for a in axes]
    return np.cumprod([1] + sizes[:0:-1])[::-1]


def grid_best(model, axes):
    """在給定的各維座標軸上做完全掃描。維度數由 axes 的長度決定。

    用攤平的線性索引而不是巢狀迴圈，維度數才不會寫死在程式碼裡 ——
    差異消光升格成第七個參數時，這裡不需要再改一次。
    """
    strides = _strides(axes)
    total = int(np.prod([len(a) for a in axes]))
    best, best_lp = None, -np.inf
    for k in range(total):
        th = _decode(k, axes, strides)
        lp = model.log_posterior(th)
        if lp > best_lp:
            best_lp, best = lp, th.copy()
    return best, best_lp


# ---- 平行版網格搜尋 ----
#
# 網格搜尋是教科書等級的「令人尷尬的平行」問題：格點之間完全獨立、沒有順序關係。
# 把最外層的 logAge 迴圈拆給各行程，每個行程掃完自己那份回報最佳解，主行程取最好。
# 只在最後彙總一次，通訊量極小。
#
# 模型必須用 Pool 的 initializer 只送一次。若每次呼叫都重送，4 MB 的模型
# 會讓序列化開銷吃掉全部平行效益（先前實測那樣做只有 1.2 倍加速）。
_G_MODEL = None
_G_AXES = None


def _keep_worker_awake():
    """2026-08-16：radial_r3 卡死好幾次的根因追查——run_queue.py 的
    keep_system_awake() 只在**它自己這個 process** 呼叫 SetThreadExecutionState，
    這個宣告不會傳給它用 subprocess 開出來的 fit_real.py，更不會傳給
    fit_real.py 底下這些用 multiprocessing.Pool 另外開的工人行程（Windows
    的這個 API 是 per-thread/per-process 的，不會沿行程樹往下繼承）。
    也就是說：真正在燒 CPU 的 8 個工人，一個都沒有跟系統宣告過「別把我
    當閒置」，run_queue.py 的宣告只保護了它自己這個幾乎不耗 CPU 的協調行程。
    而且 multi_stage_best() 的架構是**每一個精修階段都重開一次 Pool**
    （粗網格一次、每個 refine 各一次），代表這個「剛開新行程、還沒宣告
    保護」的空窗期不是只在 watchdog 重試時出現一次，是整支程式跑的過程中
    反覆發生好幾次——這比原本只懷疑「防毒掃描卡住重啟後的新行程」的假設
    涵蓋的觸發窗口更廣，且是可以直接從程式碼結構確認的落差，不只是猜測。
    在 Pool 的 initializer 裡讓每個工人一啟動就自己宣告，補上這個缺口。
    失敗只印警告不中斷——這是可用性優化，不是正確性前提。"""
    try:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_AWAYMODE_REQUIRED = 0x00000040
        prev = ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
        if not prev:
            # 跟 run_queue.py 的 keep_system_awake() 用同一種處理方式：
            # 回傳 0 代表宣告失敗，印警告但不中斷這個工人——保持滿速是
            # 最佳化，不是能不能跑的前提。
            print("警告：worker 呼叫 SetThreadExecutionState 失敗"
                  "（回傳 0），可能還是會被系統當閒置節流。", flush=True)
    except (AttributeError, OSError, ImportError):
        pass                      # 非 Windows／OEM 電源管理不接受這個旗標


def _init_grid_worker(model, axes):
    global _G_MODEL, _G_AXES
    _keep_worker_awake()
    _G_MODEL, _G_AXES = model, axes


def _scan_chunk(bounds):
    """掃描攤平後的 [起, 迄) 這一段格點，回傳該段的最佳解。

    工人自己用線性索引還原出六個座標，所以主行程只需傳兩個整數，
    通訊量極小。
    """
    lo, hi = bounds
    best, best_lp = None, -np.inf
    strides = _strides(_G_AXES)          # 各維的進位權重
    for k in range(lo, hi):
        th = _decode(k, _G_AXES, strides)
        lp = _G_MODEL.log_posterior(th)
        if lp > best_lp:
            best_lp, best = lp, th.copy()
    return best, best_lp


def grid_best_parallel(model, axes, n_proc, chunks_per_proc=40):
    """平行版網格搜尋。

    **不要按某一個維度切工作**。最外層維度的格點數往往只有個位數
    （例如 logAge 精修時只有 9 個），發給 8 個工人會嚴重不均：
    第一輪 8 個工人各拿 1 份，剩下的 1 份得等第二輪，
    那一輪就只有一個工人在跑、其餘七個全閒置 ——
    實測整機 CPU 掉到 34%，且大半時間都耗在這種尾巴上。

    正確作法是把六維所有組合攤平成一條線性索引，切成遠多於行程數的小塊，
    工人做完一塊立刻領下一塊，自然達成負載平衡。
    """
    total = int(np.prod([len(a) for a in axes]))
    if n_proc <= 1 or total < 1000:
        return grid_best(model, axes)

    from multiprocessing import Pool
    n_chunk = max(n_proc, n_proc * chunks_per_proc)
    edges = np.linspace(0, total, n_chunk + 1).astype(int)
    jobs = [(int(edges[i]), int(edges[i + 1])) for i in range(n_chunk)
            if edges[i + 1] > edges[i]]

    with Pool(n_proc, initializer=_init_grid_worker,
              initargs=(model, axes)) as pool:
        results = pool.map(_scan_chunk, jobs, chunksize=1)
    best, best_lp = None, -np.inf
    for b, lp in results:
        if b is not None and lp > best_lp:
            best_lp, best = lp, b
    return best, best_lp


def two_stage_best(model, coarse_axes, bounds, refine=4, n_proc=1):
    """兩階段搜尋：先粗掃定位，再在最佳點附近用細格距精修。

    直接用細格距全掃會爆炸（六維各縮四倍 = 4^6 = 4096 倍格點，估計 19 小時）。
    兩階段的代價是可能落入局部最佳，但粗掃已經涵蓋整個範圍，
    只要粗格距小於特徵尺度就不會漏掉主峰。
    """
    best, lp = grid_best_parallel(model, coarse_axes, n_proc)
    fine_axes = []
    for i, ax in enumerate(coarse_axes):
        if len(ax) < 2:
            fine_axes.append(ax)
            continue
        step = float(ax[1] - ax[0])
        # 在最佳點 +-1 個粗格距內，用 1/refine 的格距重掃
        lo = max(best[i] - step, bounds[i][0])
        hi = min(best[i] + step, bounds[i][1])
        fine_axes.append(np.arange(lo, hi + 1e-9, step / refine))
    return grid_best_parallel(model, fine_axes, n_proc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-split", type=int, default=6,
                    help="做幾次隨機切分")
    ap.add_argument("--refine", type=int, default=4,
                    help="精修階段的格距是粗掃的幾分之一")
    a = ap.parse_args()

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
    n = len(color)
    print(f"觀測 {n:,} 顆，距離模數 {dm:.4f}")

    cfg._data["step3_age"]["n_synthetic"] = cj.n_synthetic
    cfg._data["joint_fit"]["mh_prior_sigma"] = 0.0   # 測概似本身，先關掉先驗

    # 網格必須涵蓋 MCMC 找到的區域（logAge 約 8.18、MH 約 0.18）
    # 網格粗細的取捨：這裡量的是「兩半的答案差多少」，不需要精確定位峰值，
    # 只要格距明顯小於預期的差異即可。q_gamma 經輪廓測試確認影響很小，固定住。
    ages = np.arange(8.00, 8.31, 0.05)
    avs = np.arange(0.00, 0.29, 0.06)
    fbins = np.arange(0.35, 0.71, 0.05)
    alphas = np.arange(2.0, 2.81, 0.10)
    mhs = np.arange(0.00, 0.31, 0.10)
    qgs = [-0.7]
    coarse = [ages, avs, fbins, alphas, mhs, np.array(qgs)]
    npt = int(np.prod([len(x) for x in coarse]))
    fine_step = [float(x[1] - x[0]) / a.refine if len(x) > 1 else 0
                 for x in coarse]
    print(f"粗掃 {npt:,} 個格點，再以 1/{a.refine} 格距精修")
    print(f"精修後的有效解析度："
          f"logAge {fine_step[0]:.4f}、A_V {fine_step[1]:.4f}、"
          f"f_bin {fine_step[2]:.4f}、alpha {fine_step[3]:.4f}、"
          f"MH {fine_step[4]:.4f}\n")

    rng = np.random.default_rng(cfg.step1_membership.random_seed)
    names = ["logAge", "A_V", "f_bin", "alpha", "MH", "q_gamma"]
    bounds_list = [(x.min(), x.max()) for x in coarse]
    diffs = []

    for k in range(a.n_split):
        t0 = time.time()
        perm = rng.permutation(n)
        h = n // 2
        outs = []
        for idx in (perm[:h], perm[h:]):
            m = joint_fit.JointModel(cfg, color[idx], mag[idx], grid,
                                     errmodel, dm)
            best, _ = two_stage_best(m, coarse, bounds_list, a.refine)
            outs.append(best)
        d = np.abs(outs[0] - outs[1])
        diffs.append(d)
        print(f"切分 {k+1}: " + "  ".join(
            f"{nm}={outs[0][i]:.2f}/{outs[1][i]:.2f}"
            for i, nm in enumerate(names)) + f"  ({time.time()-t0:.0f}s)",
            flush=True)

    diffs = np.array(diffs)
    print(f"\n{'='*74}\n概似高估倍數\n{'='*74}")
    print(f"{'參數':<10}{'|差|中位':>10}{'推得 sigma':>12}"
          f"{'MCMC 誤差棒':>12}{'高估倍數':>10}")
    for i, nm in enumerate(names):
        med = float(np.median(diffs[:, i]))
        sigma_full = med / 2.0        # 見檔頭推導
        ratio = sigma_full / MCMC_ERR[nm] if MCMC_ERR[nm] > 0 else np.nan
        print(f"{nm:<10}{med:>10.3f}{sigma_full:>12.3f}"
              f"{MCMC_ERR[nm]:>12.3f}{ratio:>9.1f}x")

    np.savez(HERE / "results" / "overconfidence.npz",
             diffs=diffs, mcmc_err=np.array([MCMC_ERR[n] for n in names]))
    print(f"\n寫入 results/overconfidence.npz")
    print("\n判讀：高估倍數就是概似該被打的折扣。若倍數約為 k，")
    print("      表示有效的獨立資訊量只有名目的 1/k^2，")
    print("      正確作法是把 log 概似除以 k^2（等同於降低它的權重）。")


if __name__ == "__main__":
    main()
