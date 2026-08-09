# -*- coding: utf-8 -*-
"""檢驗投影修正有沒有效：已知成員的自行運動散布應該變小。

拿 HR23 Prob>=0.5 的成員當對照組（它們的成員身分不是我判的），比較修正前後
的 pmRA/pmDE 標準差。如果修正是對的，散布會往真實內部彌散靠近；
如果散布沒變或變大，代表這個修正做錯了。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
K = 4.740470446

raw = Table.read(HERE / "prepared" / "m45_raw.dat", format="ascii")
dep = Table.read(HERE / "prepared" / "m45_deproj.dat", format="ascii")
hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")

ids = np.asarray(raw["source_id"], np.int64)
memb = np.isin(ids, np.asarray(hr["GaiaDR3"], np.int64)[
    np.asarray(hr["Prob"], float) >= 0.5])
print(f"對照組：HR23 Prob>=0.5 且在樣本內的成員 {memb.sum():,} 顆\n")

print(f"{'':<12}{'pmRA std':>11}{'pmDE std':>11}{'合成':>9}{'相當於 km/s':>13}")
for lab, t in (("修正前", raw), ("修正後", dep)):
    a = np.asarray(t["pmRA"], float)[memb]
    b = np.asarray(t["pmDE"], float)[memb]
    sa, sb = a.std(), b.std()
    tot = np.hypot(sa, sb)
    print(f"{lab:<12}{sa:>11.3f}{sb:>11.3f}{tot:>9.3f}"
          f"{tot * K / 7.378:>13.3f}")

# 空間相依性：把天區切成環帶，看各環帶的平均自行運動有沒有系統性漂移
x = np.asarray(raw["_x"], float)[memb]
y = np.asarray(raw["_y"], float)[memb]
r = np.hypot(x, y)
print(f"\n各環帶成員的平均自行運動（看有沒有隨半徑系統性漂移）")
print(f"{'半徑':<10}{'n':>6}{'修正前 pmRA':>14}{'pmDE':>10}"
      f"{'修正後 pmRA':>14}{'pmDE':>10}")
for lo, hi in [(0, 1), (1, 2), (2, 3), (3, 5.1)]:
    m = (r >= lo) & (r < hi)
    if m.sum() < 5:
        continue
    ra_r = np.asarray(raw["pmRA"], float)[memb][m].mean()
    de_r = np.asarray(raw["pmDE"], float)[memb][m].mean()
    ra_d = np.asarray(dep["pmRA"], float)[memb][m].mean()
    de_d = np.asarray(dep["pmDE"], float)[memb][m].mean()
    print(f"{lo}-{hi:g} 度{'':<4}{m.sum():>6}{ra_r:>14.3f}{de_r:>10.3f}"
          f"{ra_d:>14.3f}{de_d:>10.3f}")
