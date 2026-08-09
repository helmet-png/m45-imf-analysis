# -*- coding: utf-8 -*-
"""比較 G<18 與 G<20 兩種星等深度：涵蓋率提升多少？分群品質有沒有劣化？

加深星等在算力上幾乎免費（9.9 分鐘 vs 9.8 分鐘），但 Gaia 天測精度在 G>18 之後
明顯下降，所以真正要驗的是「多撈到的星是真成員還是雜訊」。
"""
from pathlib import Path

import numpy as np
from astropy.table import Table

HERE = Path(__file__).resolve().parent
THR = 0.7

hr = Table.read(HERE / "data" / "hr23_Melotte_22.csv", format="csv")
hr_id = np.asarray(hr["GaiaDR3"], np.int64)
hr_p = np.asarray(hr["Prob"], float)
hr_g = np.asarray(hr["Gmag"], float)
ref = set(hr_id[hr_p >= 0.5].tolist())
print(f"HR23 全天成員 {len(hr_id):,} 顆，其中 Prob>=0.5 者 {len(ref):,} 顆\n")


def load(name):
    t = Table.read(HERE / "results" / f"{name}.dat", format="ascii")
    return (np.asarray(t["source_id"], np.int64),
            np.asarray(t["probs_final"], float),
            t)


print(f"=== 成員判定結果（門檻 P >= {THR}）===")
print(f"{'樣本':<12}{'總星數':>9}{'選出':>8}{'命中':>8}{'漏':>6}"
      f"{'我方獨有':>10}{'precision':>11}{'recall':>9}")
res = {}
for lab, name in (("G<18", "baseline"), ("G<20", "g20")):
    ids, p, t = load(name)
    sel = p >= THR
    truth = np.isin(ids, list(ref))
    # recall 的分母只算「在我樣本裡的」HR23 成員
    in_sample = np.isin(np.array(list(ref)), ids)
    tp = int((sel & truth).sum())
    fp = int((sel & ~truth).sum())
    fn = int((~sel & truth).sum())
    print(f"{lab:<12}{len(ids):>9,}{tp+fp:>8,}{tp:>8,}{fn:>6,}{fp:>10,}"
          f"{tp/max(tp+fp,1):>11.4f}{tp/max(tp+fn,1):>9.4f}")
    res[lab] = {"ids": ids, "p": p, "sel": sel, "truth": truth,
                "covered": int(in_sample.sum())}

print(f"\n涵蓋率（HR23 Prob>=0.5 的成員有多少出現在樣本裡）：")
for lab in ("G<18", "G<20"):
    c = res[lab]["covered"]
    print(f"  {lab}: {c:,} / {len(ref):,} = {c/len(ref)*100:.1f}%")

print(f"\n=== 多撈到的星是什麼 ===")
new = set(res["G<20"]["ids"][res["G<20"]["sel"]].tolist()) - \
      set(res["G<18"]["ids"][res["G<18"]["sel"]].tolist())
print(f"G<20 比 G<18 多選出 {len(new):,} 顆")
in_hr = len(new & set(hr_id.tolist()))
in_ref = len(new & ref)
print(f"  其中 HR23 也收在成員表：{in_hr:,} 顆 ({in_hr/max(len(new),1)*100:.1f}%)")
print(f"  其中 HR23 Prob>=0.5  ：{in_ref:,} 顆 ({in_ref/max(len(new),1)*100:.1f}%)")

ids20, p20, t20 = load("g20")
m_new = np.isin(ids20, list(new))
g20 = np.asarray(t20["Gmag"], float)
print(f"  這批星的 G 中位數 {np.median(g20[m_new]):.2f}，"
      f"範圍 {g20[m_new].min():.2f} – {g20[m_new].max():.2f}")
faint = m_new & (g20 > 18)
print(f"  其中 G>18（原本抓不到的暗端）：{int(faint.sum()):,} 顆")
if faint.any():
    fid = set(ids20[faint].tolist())
    print(f"    這批暗星裡 HR23 也收的：{len(fid & set(hr_id.tolist())):,} 顆")

print(f"\n=== 分群品質有沒有劣化 ===")
print("看機率分布在穩定谷地（0.5-0.9）與飽和區的比例：")
for lab, name in (("G<18", "baseline"), ("G<20", "g20")):
    _, p, _ = load(name)
    v = p[p >= 0]
    mid = int(((v > 0.3) & (v < 0.9)).sum())
    top = int((v >= 0.99).sum())
    zero = int((v == 0).sum())
    print(f"  {lab}: P=0 者 {zero:>5,}，中間帶(0.3-0.9) {mid:>4,}，"
          f"P>=0.99 者 {top:>5,}")

print("\n各門檻下的成員數（看門檻穩定性有沒有變差）：")
print(f"{'門檻':>6}{'G<18':>9}{'G<20':>9}")
for thr in (0.5, 0.7, 0.9, 0.95, 0.99):
    a = int((res['G<18']['p'] >= thr).sum())
    b = int((res['G<20']['p'] >= thr).sum())
    print(f"{thr:>6.2f}{a:>9,}{b:>9,}")
