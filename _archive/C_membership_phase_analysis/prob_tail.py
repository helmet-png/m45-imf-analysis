# -*- coding: utf-8 -*-
"""看機率分布在 1.0 附近的細部結構。

門檻穩不穩，取決於「門檻切在星密度高還是低的地方」：
切在稀疏處，機率抖動一點也移動不了幾顆星；切在一堆星的正中間，就會大量搬動。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
EDGES = [0.5, 0.7, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999, 1.0001]

print(f"{'區間':<16}" + "".join(f"{n:>10}" for n in
                                ("seed42", "seed43", "seed44", "seed99")))
runs = {}
for name in ("baseline", "seed43", "seed44", "seed99"):
    t = Table.read(HERE / "results" / f"{name}.dat", format="ascii")
    runs[name] = np.asarray(t["probs_final"], float)

for lo, hi in zip(EDGES[:-1], EDGES[1:]):
    row = f"{lo:g} - {hi:g}".ljust(16)
    for name in runs:
        p = runs[name]
        row += f"{int(((p >= lo) & (p < hi)).sum()):>10,}"
    print(row)

print()
for name, p in runs.items():
    print(f"{name:<10} P=1.0 剛好 {int((p >= 0.99999).sum()):>6,} 顆"
          f"   0.99 以上 {int((p >= 0.99).sum()):>6,} 顆")
