# -*- coding: utf-8 -*-
"""拆解我跟 HR23 不一致的星到底是什麼。

重點：validate.py 把「HR23 Prob>=0.5」當真成員，所以被判成 FP 的星有三種可能
  (a) HR23 也列在成員表，只是 Prob<0.5   -> 其實兩邊都認為可能是成員
  (b) HR23 完全沒收               -> 真正的分歧
  (c) 我的誤判
分開數才知道 precision 0.78 的意義。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).parent
t = Table.read(HERE / "data" / "comparison.csv", format="csv")

p = np.asarray(t["my_prob"], float)
hr_p = np.asarray(t["hr23_prob"], float)          # 不在 HR23 名單裡 = nan
in_hr = np.isfinite(hr_p)                          # 有出現在 HR23 成員表（任何 Prob）
truth = np.asarray(t["hr23_member"], int).astype(bool)   # HR23 Prob>=0.5
pmra, pmde = np.asarray(t["pmRA"], float), np.asarray(t["pmDE"], float)
plx, g = np.asarray(t["Plx"], float), np.asarray(t["Gmag"], float)

print("=== 我的機率分布 ===")
bins = [("遮罩 P=-1", p < 0),
        ("P = 0 (確定非成員)", p == 0),
        ("0 < P <= 0.5", (p > 0) & (p <= .5)),
        ("0.5 < P <= 0.9", (p > .5) & (p <= .9)),
        ("0.9 < P < 0.99", (p > .9) & (p < .99)),
        ("P >= 0.99", p >= .99)]
for lab, m in bins:
    print(f"  {lab:<20} {m.sum():>6,}   其中 HR23 有收 {in_hr[m].sum():>5,}")

print("\n=== HR23 成員（Prob>=0.5）拿到的我方機率 ===")
q = np.percentile(p[truth], [0, 1, 5, 50, 100])
print(f"  最小 {q[0]:.4f} / 1% {q[1]:.4f} / 5% {q[2]:.4f} / 中位 {q[3]:.4f} / 最大 {q[4]:.4f}")
print(f"  拿到 P>=0.99 的比例: {(p[truth] >= .99).mean()*100:.2f}%")

print("\n=== 我在 P>=0.99 判為成員、但不在 HR23 Prob>=0.5 名單裡的星 ===")
fp = (p >= .99) & ~truth
a = fp & in_hr
b = fp & ~in_hr
print(f"  總數                      {fp.sum():>5}")
print(f"  (a) HR23 有收但 Prob<0.5  {a.sum():>5}"
      f"   -> 其 HR23 Prob 中位數 {np.median(hr_p[a]):.3f}")
print(f"  (b) HR23 完全沒收          {b.sum():>5}")

print("\n=== 這兩群長什麼樣（跟公認成員比）===")
ref = truth
for lab, m in [("HR23 成員 (Prob>=0.5)", ref), ("(a) HR23 低機率", a),
               ("(b) HR23 未收", b)]:
    if m.sum() == 0:
        continue
    print(f"  {lab:<22} n={m.sum():>4}  "
          f"pm=({np.median(pmra[m]):+6.2f},{np.median(pmde[m]):+7.2f})  "
          f"Plx={np.median(plx[m]):5.2f}  "
          f"G 中位={np.median(g[m]):5.2f}  G 範圍 {g[m].min():.1f}-{g[m].max():.1f}")

# 用公認成員的散布，量化 (b) 群離團心多遠（以標準差為單位）
c_pm = np.array([np.median(pmra[ref]), np.median(pmde[ref])])
s_pm = np.array([np.std(pmra[ref]), np.std(pmde[ref])])
c_plx, s_plx = np.median(plx[ref]), np.std(plx[ref])
for lab, m in [("(a) HR23 低機率", a), ("(b) HR23 未收", b)]:
    if m.sum() == 0:
        continue
    d = np.sqrt(((pmra[m] - c_pm[0]) / s_pm[0])**2
                + ((pmde[m] - c_pm[1]) / s_pm[1])**2
                + ((plx[m] - c_plx) / s_plx)**2)
    print(f"  {lab:<22} 距團心 {np.median(d):.2f} sigma（中位）"
          f"，{(d < 3).sum()}/{m.sum()} 顆在 3 sigma 內")
