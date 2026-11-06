# -*- coding: utf-8 -*-
"""比較專案用的常數消光係數跟 Gaia EDR3 官方隨顏色變的係數（LIMITATIONS.md B6）。

專案全程用常數 A_G/A_V=0.83、A_BP/A_V=1.08、A_RP/A_V=0.63
（`config.toml` [step2_cmd]）。Gaia 官方係數（Fitzpatrick+2019 消光曲線、
主序 log g=4.5，Danielski et al. 2018 的方法）是內稟顏色 X=(BP-RP)_0 與
A0 的多項式：

    k = a1 + a2 X + a3 X^2 + a4 X^3 + a5 A0 + a6 A0^2 + a7 A0^3
        + a8 X A0 + a9 A0 X^2 + a10 X A0^2

只在 -0.06 < X < 2.5、0.01 < A0 < 20 有效，官方明說不可外插。這支腳本
只在有效範圍內算，範圍外的星只計數、不給係數。

資料：`data/gaia_edr3_extinction/Fitz19_EDR3_MainSequence.csv`，原封不動取自
https://www.cosmos.esa.int/web/gaia/edr3-extinction-law 的
`Fitz19_EDR3_extinctionlawcoefficients.zip`（2026-11-06 下載）。
致謝要求："This research or product makes use of public auxiliary data
provided by ESA/Gaia/DPAC/CU5 and prepared by Carine Babusiaux."

A0 是 550 nm 的單色消光，這裡直接當 A_V 用（兩者差約 1%，遠小於要看的差）。
內稟顏色用觀測 BP-RP 減「常數係數下的色超」估計，迭代一次改用官方色超；
這是估計值，不是去紅化後的真值。

用法：
    python scripts/diagnostics/compare_extinction_coefficients.py
    python scripts/diagnostics/compare_extinction_coefficients.py --av 0.102
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
COEF_FILE = ROOT / "data" / "gaia_edr3_extinction" / "Fitz19_EDR3_MainSequence.csv"
TERMS = ["Intercept", "X", "X2", "X3", "A", "A2", "A3", "XA", "AX2", "XA2"]
X_VALID = (-0.06, 2.5)
CONST = {"kG": 0.83, "kBP": 1.08, "kRP": 0.63}  # config.toml [step2_cmd]
BINS = [-0.06, 0.5, 1.0, 1.5, 2.0, 2.5]


def load_coeffs(path: Path = COEF_FILE) -> dict:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["Xname"] == "BPRP"]
    out = {r["Kname"]: np.array([float(r[t]) for t in TERMS]) for r in rows}
    missing = {"kG", "kBP", "kRP"} - set(out)
    if missing:
        raise ValueError(f"{path} 缺少 {sorted(missing)}")
    return out


def k_gaia(c: np.ndarray, x, a0):
    """官方多項式；x 超出有效範圍的位置回傳 NaN（不外插）。"""
    x = np.asarray(x, float)
    a = float(a0)
    k = (c[0] + c[1] * x + c[2] * x**2 + c[3] * x**3 + c[4] * a + c[5] * a**2
         + c[6] * a**3 + c[7] * x * a + c[8] * a * x**2 + c[9] * x * a**2)
    return np.where((x > X_VALID[0]) & (x < X_VALID[1]), k, np.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=Path, default=ROOT / "data" / "cmd_members.csv")
    ap.add_argument("--av", type=float, default=0.386, help="headline p2_final2_v3")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "extinction_coefficient_comparison.json")
    a = ap.parse_args()
    if not 0.01 < a.av < 20:
        ap.error("A0 必須在官方有效範圍 0.01–20")
    C = load_coeffs()
    with a.members.open(newline="", encoding="utf-8") as fh:
        bprp = np.array([float(r["bp_rp"]) for r in csv.DictReader(fh)
                         if r["bp_rp"].strip()])

    e_const = (CONST["kBP"] - CONST["kRP"]) * a.av
    x0 = bprp - e_const
    # 迭代一次：用官方色超重估內稟顏色（有效範圍外維持常數版估計）
    e_gaia = (k_gaia(C["kBP"], x0, a.av) - k_gaia(C["kRP"], x0, a.av)) * a.av
    x = np.where(np.isfinite(e_gaia), bprp - e_gaia, x0)

    kg, kbp, krp = (k_gaia(C[n], x, a.av) for n in ("kG", "kBP", "kRP"))
    valid = np.isfinite(kg)
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = valid & (x >= lo) & (x < hi)
        if not m.any():
            continue
        ebr = (kbp[m] - krp[m]).mean()
        rows.append({
            "x_bin": [lo, hi], "n": int(m.sum()),
            "kG": float(kg[m].mean()), "kBP": float(kbp[m].mean()),
            "kRP": float(krp[m].mean()), "E_BPRP_over_A0": float(ebr),
            "dG_mag_vs_const": float((kg[m].mean() - CONST["kG"]) * a.av),
            "dColour_mag_vs_const": float((ebr - (CONST["kBP"] - CONST["kRP"])) * a.av),
            # 同樣的觀測色超，用官方係數要多大的 A_V 才湊得出來
            "av_scale_for_same_reddening": float((CONST["kBP"] - CONST["kRP"]) / ebr),
        })
    res = {
        "av": a.av, "n_members": int(len(bprp)),
        "n_valid": int(valid.sum()),
        "n_outside_validity_red": int((x >= X_VALID[1]).sum()),
        "n_outside_validity_blue": int((x <= X_VALID[0]).sum()),
        "const_coeffs": CONST, "x_valid": X_VALID, "bins": rows,
        "source": "ESA/Gaia/DPAC/CU5 Fitz19_EDR3_MainSequence.csv (BPRP rows)",
    }
    print(f"A0={a.av}：{res['n_members']} 顆成員，有效範圍內 {res['n_valid']}，"
          f"太紅（X>=2.5）{res['n_outside_validity_red']}，"
          f"太藍 {res['n_outside_validity_blue']}")
    print("  X 區間       N    kG    E(BP-RP)/A0  ΔG(mag)  Δ色(mag)  同色超需 A_V 倍數")
    for r in rows:
        print(f"  {r['x_bin'][0]:+.2f}–{r['x_bin'][1]:.2f} {r['n']:5d}  {r['kG']:.3f}"
              f"   {r['E_BPRP_over_A0']:.3f}     {r['dG_mag_vs_const']:+.3f}   "
              f"{r['dColour_mag_vs_const']:+.3f}    {r['av_scale_for_same_reddening']:.2f}")
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫入 {a.out}")


if __name__ == "__main__":
    main()
