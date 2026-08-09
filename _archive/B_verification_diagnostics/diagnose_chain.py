# -*- coding: utf-8 -*-
"""診斷 MCMC 鏈：是「還沒跑夠」還是「原則上定不出來」？

兩者的處置完全不同 —— 前者加長鏈就好，後者加再多也沒用，必須引入外部資訊。
判斷依據：
  1. 走者有沒有貼在先驗邊界上（貼邊 = 資料沒有約束力，是先驗在決定答案）
  2. 前半鏈與後半鏈的分布有沒有明顯漂移（仍在漂 = 尚未平衡）
  3. 沿著簡併方向的散布有多大（大 = 資料無法沿該方向區分）
"""
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE))
from pipeline import config as cfgmod, joint_fit  # noqa: E402

cfg = cfgmod.load()
b = cfg.joint_fit
bounds = np.array([[b.logage_min, b.logage_max], [b.av_min, b.av_max],
                   [b.fbin_min, b.fbin_max], [b.alpha_min, b.alpha_max],
                   [b.mh_min, b.mh_max], [b.qgamma_min, b.qgamma_max]])

d = np.load(HERE / "results" / "joint_fit.npz")
chain = d["chain"]
names = joint_fit.PARAM_NAMES
print(f"鏈：{chain.shape[0]:,} 個樣本 x {chain.shape[1]} 參數\n")

print("=== 1. 走者有沒有貼在先驗邊界上 ===")
print(f"{'參數':<10}{'先驗下界':>10}{'5百分位':>10}{'中位':>10}"
      f"{'95百分位':>10}{'先驗上界':>10}{'貼邊':>8}")
for i, n in enumerate(names):
    q = np.percentile(chain[:, i], [5, 50, 95])
    lo, hi = bounds[i]
    span = hi - lo
    near_lo = (q[0] - lo) / span < 0.05
    near_hi = (hi - q[2]) / span < 0.05
    tag = "下界" if near_lo else ("上界" if near_hi else "")
    print(f"{n:<10}{lo:>10.3f}{q[0]:>10.3f}{q[1]:>10.3f}{q[2]:>10.3f}"
          f"{hi:>10.3f}{tag:>8}")

print("\n=== 2. 前半鏈 vs 後半鏈（仍在漂移？）===")
half = len(chain) // 2
print(f"{'參數':<10}{'前半中位':>10}{'後半中位':>10}{'差異':>10}{'後半散布':>10}")
for i, n in enumerate(names):
    m1 = np.median(chain[:half, i])
    m2 = np.median(chain[half:, i])
    sd = np.std(chain[half:, i])
    flag = "  <- 漂移大於散布" if abs(m2 - m1) > sd else ""
    print(f"{n:<10}{m1:>10.3f}{m2:>10.3f}{m2-m1:>10.3f}{sd:>10.3f}{flag}")

print("\n=== 3. 簡併方向的散布 ===")
c = np.corrcoef(chain.T)
sub = [0, 1, 4]      # logage, A_V, MH
print("年齡-消光-金屬量 三者的相關係數：")
for i in sub:
    print(f"  {names[i]:<8}" + "".join(f"{c[i, j]:>9.2f}" for j in sub))
# 主成分：看有多少變異集中在單一方向
x = chain[:, sub]
x = (x - x.mean(0)) / x.std(0)
w = np.linalg.eigvalsh(np.cov(x.T))[::-1]
print(f"\n這三個參數的主成分變異佔比："
      f"{' / '.join(f'{v/w.sum()*100:.1f}%' for v in w)}")
print("若第一主成分佔比極高，代表三者幾乎只沿一條線變動 ——")
print("資料能定出的是「這條線的位置」，而不是三個獨立的值。")
