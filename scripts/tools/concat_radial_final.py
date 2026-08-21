# -*- coding: utf-8 -*-
"""把 radial_<組>_final 的 5 個 Kaggle 分片串接成一份完整結果。

**分片檔名全部相同**（fit_real_radial_<組>_final.npz），靠所在目錄名
（radial_<組>_final_rep<N>）對應 repeat_offset，不能只看檔名。

串接前逐項核對 manifest：除了 repeat_offset 之外每個欄位都必須一致，
不一致就中止——那代表某一片是用不同設定跑的，混進來會讓整組數字失去
「只差重複次數」這個前提。
"""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
group = sys.argv[1] if len(sys.argv) > 1 else "r3"   # r1 / r2 / r3 / rall
n_expect = 5

rows = []
for off in range(n_expect):
    d = REPO / "kaggle_results" / f"radial_{group}_final_rep{off}"
    f = d / "results" / f"fit_real_radial_{group}_final.npz"
    if not f.is_file():
        print(f"缺少分片 offset={off}: {f}")
        sys.exit(1)
    with np.load(f, allow_pickle=True) as z:
        man = json.loads(str(z["__manifest__"])) if "__manifest__" in z.files else None
        C = z["C"]
    rows.append((off, C, man, f))

# manifest 一致性檢查（repeat_offset 以外全部要相同）
base = dict(rows[0][2] or {})
base.pop("repeat_offset", None)
for off, _, man, f in rows[1:]:
    cur = dict(man or {})
    cur.pop("repeat_offset", None)
    diff = {k: (base.get(k), cur.get(k)) for k in set(base) | set(cur)
            if base.get(k) != cur.get(k)}
    if diff:
        print(f"manifest 不一致（offset={off}）：{diff}")
        print("中止：這幾片不是同一組設定跑出來的，不能串接。")
        sys.exit(1)
# 每片的 repeat_offset 要真的等於它所在目錄的 offset
for off, _, man, f in rows:
    got = (man or {}).get("repeat_offset")
    if got != off:
        print(f"目錄 rep{off} 的 manifest 卻記 repeat_offset={got}，中止")
        sys.exit(1)

C_all = np.concatenate([C for _, C, _, _ in rows], axis=0)
print(f"radial_{group}_final：{len(rows)} 片串接完成，C shape={C_all.shape}")
names = ["logage", "A_V", "f_bin", "alpha", "MH", "q_gamma", "dav"]
print(f"{'off':>4} " + " ".join(f"{n:>9}" for n in names[:C_all.shape[1]]))
for (off, C, _, _) in rows:
    print(f"{off:>4} " + " ".join(f"{v:9.4f}" for v in C[0]))
a = C_all[:, 3]
print()
print(f"alpha 五次：{np.round(a,4).tolist()}")
print(f"alpha 平均 = {a.mean():.4f}")
print(f"樣本標準差(ddof=1) = {a.std(ddof=1):.4f}")
print(f"平均值標準誤 = {a.std(ddof=1)/np.sqrt(len(a)):.4f}")

out = REPO / "results" / f"fit_real_radial_{group}_final.npz"
np.savez(out, C=C_all, __manifest__=json.dumps(base, ensure_ascii=False))
print(f"\n寫入 {out}")
