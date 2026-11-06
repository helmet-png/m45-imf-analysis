# -*- coding: utf-8 -*-
"""把前向模型的 f_bin（q >= q_min 全部算）換算成「只數 q > q_c」的雙星比例
（LIMITATIONS.md D24）。

為什麼需要：`JointModel.synthesise()` 的 f_bin 數的是 q_min=0.10 以上的
所有伴星，q 分布 p(q) ∝ q^q_gamma。q 小的伴星幾乎不改變系統的測光
（q=0.2 的主序伴星只讓系統亮約 0.01–0.03 mag），所以 f_bin 裡 q 小的
那一塊主要是由 q_gamma 外推出來的，不是 CMD 直接量到的。拿 f_bin 跟文獻
並排之前，要先換到同一個 q 區間。

換算式（p(q) ∝ q^g，q ∈ [q_min, 1]，g != -1）：

    f(q > q_c) = f_bin * (1 - q_c^(g+1)) / (1 - q_min^(g+1))

每次重複各自用自己的 (f_bin, q_gamma) 換算，再取平均與樣本標準差
（ddof=1），所以 f_bin 與 q_gamma 的相關有被保留。只做這個代數換算，
不重跑任何擬合。q_gamma 的注入回收偏差（-0.12～-0.18，見
`results/injection_recovery*.npz`）沒有傳播進來，見 D24。

用法：
    python scripts/diagnostics/fbin_qcut_conversion.py
    python scripts/diagnostics/fbin_qcut_conversion.py --npz results/fit_real_p2final_v3.npz
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
# fit_real.py 的 C 陣列欄位順序：logage, A_V, f_bin, alpha, MH, q_gamma, dav
I_FBIN, I_QG = 2, 5
Q_CUTS = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]


def frac_above(q_c, g, q_min):
    """p(q) ∝ q^g 在 [q_min, 1] 上，q > q_c 所佔比例。"""
    g = np.asarray(g, float)
    if np.any(np.isclose(g, -1.0)):
        raise ValueError("q_gamma = -1 需要對數形式，這裡沒有實作")
    e = g + 1.0
    return (1.0 - q_c ** e) / (1.0 - q_min ** e)


def run(npz: Path, key: str, q_min: float) -> dict:
    C = np.load(npz)[key]
    fbin, qg = C[:, I_FBIN], C[:, I_QG]
    rows = [{"q_cut": q_min, "mean": float(fbin.mean()),
             "std": float(fbin.std(ddof=1))}]
    for q_c in Q_CUTS:
        x = fbin * frac_above(q_c, qg, q_min)
        rows.append({"q_cut": q_c, "mean": float(x.mean()),
                     "std": float(x.std(ddof=1))})
    below03 = 1.0 - frac_above(0.3, qg, q_min)
    return {
        "source": str(npz.relative_to(ROOT)).replace("\\", "/"),
        "key": key, "n_repeats": int(len(C)), "q_min": q_min,
        "q_gamma_mean": float(qg.mean()),
        "share_of_binaries_with_q_below_0p3": float(below03.mean()),
        "rows": rows,
        "note": "std 是重複擬合雜訊（ddof=1），不是注入回收誤差；"
                "q_gamma 的注入回收偏差未傳播",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", type=Path,
                    default=ROOT / "results" / "fit_real_p2final_v3.npz")
    ap.add_argument("--key", default="C")
    ap.add_argument("--q-min", type=float, default=0.10,
                    help="必須等於擬合時的 config.toml binary_q_min")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "fbin_qcut_conversion.json")
    a = ap.parse_args()
    res = run(a.npz.resolve(), a.key, a.q_min)
    print(f"{res['source']}  ({res['n_repeats']} 次重複，"
          f"q_gamma 平均 {res['q_gamma_mean']:+.3f})")
    for r in res["rows"]:
        print(f"  q > {r['q_cut']:.2f}:  {r['mean']:.3f} ± {r['std']:.3f}")
    print(f"  q < 0.3 佔全部雙星的比例: "
          f"{res['share_of_binaries_with_q_below_0p3']:.3f}")
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    print(f"寫入 {a.out}")


if __name__ == "__main__":
    main()
