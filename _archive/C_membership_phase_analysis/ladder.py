# -*- coding: utf-8 -*-
"""視差切階梯：每一階留下多少星、留下多少 HR23 成員、估計 pyUPMASK 要跑多久。

用來判斷「不切視差的對照跑」實際跑得動哪幾階。
不切視差是 198,672 顆（先前已量過），這裡只補中間各階。
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from astropy.table import Table

sys.path.insert(0, r"C:\Users\Alber\Claude\gaia-export")
import server  # noqa: E402

HERE = Path(__file__).parent
RA, DEC = 56.60083, 24.11389
# plx>4 的基準：6,956 顆、25 輪跑了 9.8 分鐘
N_REF, MIN_REF = 6956, 9.8

ap = argparse.ArgumentParser()
ap.add_argument("--steps", type=float, nargs="+", default=[4, 3, 2, 1.5, 1])
a = ap.parse_args()

hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
hr_plx = np.asarray(hr["Plx"], float)
hr_g = np.asarray(hr["Gmag"], float)
hr_prob = np.asarray(hr["Prob"], float)

print(f"{'切法':<10}{'樣本N':>10}{'HR23成員':>10}{'成員佔比':>9}"
      f"{'估計耗時':>12}", flush=True)
for plx in a.steps:
    p = {"mode": "cone", "ra": RA, "dec": DEC, "radius": 5.0, "mag_max": 18,
         "parallax_min": plx}
    n = server.count_sources(p)
    # HR23 成員在同樣條件下有幾顆（錐內已由成員表位置隱含，這裡只加星等與視差）
    m = int(((hr_g <= 18) & (hr_plx >= plx) & (hr_prob >= 0.5)).sum())
    # pyUPMASK 內圈成本大致隨 N^2 成長
    est = MIN_REF * (n / N_REF) ** 2
    est_s = f"{est:.0f} 分" if est < 600 else f"{est/60:.1f} 小時"
    print(f"plx>{plx:<6g}{n:>10,}{m:>10,}{m/n*100:>8.1f}%{est_s:>12}", flush=True)
    time.sleep(2)
