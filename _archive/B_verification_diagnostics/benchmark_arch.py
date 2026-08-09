# -*- coding: utf-8 -*-
"""量這台機器上 pipeline 熱點的實際速度，用來比較 x64 模擬與 ARM64 原生。

同一支腳本用兩個 Python 各跑一次就能得到公平的比較數字。
"""
import platform
import sys
import sysconfig
import time

import numpy as np

print(f"Python   : {sys.version.split()[0]}")
print(f"建置平台 : {sysconfig.get_platform()}")
print(f"機器架構 : {platform.machine()}")
print(f"numpy    : {np.__version__}")
try:
    import sklearn
    print(f"sklearn  : {sklearn.__version__}")
except ImportError:
    print("sklearn  : 未安裝")
print()

rng = np.random.default_rng(42)
N = 40_000
results = {}


def bench(name, fn, repeat=5):
    fn()                              # 暖身，排除首次呼叫的載入成本
    t = time.perf_counter()
    for _ in range(repeat):
        fn()
    dt = (time.perf_counter() - t) / repeat
    results[name] = dt
    print(f"{name:<34}{dt*1000:>9.2f} ms")


# 前向模型的四個熱點
mi = np.sort(rng.uniform(0.1, 5.0, 300))
gi = np.sort(rng.uniform(2.0, 18.0, 300))
m1 = rng.uniform(0.1, 5.0, N)
bench("np.interp（質量→星等查表）", lambda: np.interp(m1, mi, gi))

vals = rng.uniform(1.0, 20.0, N)
bench("10**(-0.4*x) 與 log10（流量相加）",
      lambda: -2.5 * np.log10(10 ** (-0.4 * vals) + 10 ** (-0.4 * vals * 1.1)))

c = rng.normal(1.5, 0.8, N)
g = rng.normal(12.0, 3.0, N)
bench("histogram2d（Hess 圖）",
      lambda: np.histogram2d(c, g, bins=[40, 50],
                             range=[(-0.5, 4.0), (2.0, 18.0)]))

bench("normal 抽樣 3xN", lambda: (rng.normal(0, 1, N), rng.normal(0, 1, N),
                                 rng.normal(0, 1, N)))

# pyUPMASK 的熱點
try:
    from sklearn.cluster import MiniBatchKMeans
    X = rng.normal(0, 1, (7000, 2))
    bench("MiniBatchKMeans（pyUPMASK 內圈）",
          lambda: MiniBatchKMeans(n_clusters=50, n_init=3,
                                  random_state=0).fit(X), repeat=3)
except ImportError:
    pass

try:
    from scipy.stats import gaussian_kde
    Y = rng.normal(0, 1, (5, 3000))
    kde = gaussian_kde(Y)
    bench("gaussian_kde 評估（成員機率）",
          lambda: kde.evaluate(Y[:, :1500]), repeat=3)
except ImportError:
    pass

print(f"\n合計 {sum(results.values())*1000:.1f} ms")
print("\n把這份輸出用兩個 Python 各跑一次，直接對比同一列的數字。")
