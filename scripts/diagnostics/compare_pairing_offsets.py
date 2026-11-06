# -*- coding: utf-8 -*-
"""比較兩種雙星配對規則下，「主星質量函數」跟「成員星質量函數」的斜率差
（LIMITATIONS.md D26）。

為什麼需要：前向模型擬合出的 alpha 是主星質量分布的冪次（system MF，
D14）；N-body 端 mcluster 的 IMF 斜率是成員星（component）的冪次。
要把觀測 alpha 換成 component IMF，需要一個「靜態」的定義換算量
（兩者在 t=0 的斜率差），而這個量取決於雙星怎麼配對：

* forward：`JointModel.synthesise()` 的規則——主星抽自 IMF，獨立擲
  Bernoulli(f_bin)，伴星 m2 = q*m1，p(q) ∝ q^q_gamma，q ∈ [q_min, 1]。
* random：mcluster 預設 `pairing=3`（main.c pin a147bb5 第 107 行），
  主星質量 < msort=5 M☉ 時就是從 IMF 隨機抽兩顆配成一對，主星＝較重的
  那顆。M45 分析窗 0.30–2.50 M☉ 遠低於 5 M☉，所以這裡只模擬隨機配對。

兩種規則都用同一個兩段 Kroupa IMF（0.08–0.5 M☉ 斜率 1.3、0.5–150 M☉
斜率 2.3，跟 `petar_m45_grid.csv` 一致）、同一個估計器
（`petar_pdmf_analysis.mle_powerlaw`，bridge 也用它）、同一個質量窗。
random 規則的結果可以直接跟 `results/m45_system_definition_bridge_*`
裡 PeTar t=0 的 component／primary 斜率對照，當作這支模擬的驗證。

用法：
    python scripts/diagnostics/compare_pairing_offsets.py
    python scripts/diagnostics/compare_pairing_offsets.py --mass-min 0.5
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "nbody_petar"))
# 跟 pdmf_system_definition_bridge.py 用同一個估計器，才能直接對照 PeTar t=0
from petar_pdmf_analysis import mle_powerlaw  # noqa: E402

BREAKS = (0.08, 0.5, 150.0)
SLOPES = (1.3, 2.3)
BRIDGE_GLOB = "results/m45_system_definition_bridge_20261102_r4/*/*_definition_bridge.json"


def sample_kroupa(rng, n):
    """兩段冪律反 CDF 抽樣，段的權重由段間連續性決定。"""
    (lo, mid, hi), (a1, a2) = BREAKS, SLOPES

    def seg_int(a, x0, x1):
        return (x1 ** (1 - a) - x0 ** (1 - a)) / (1 - a)

    # dN/dm 在 mid 處連續：第二段乘上 mid^(a2-a1)
    w1 = seg_int(a1, lo, mid)
    w2 = mid ** (a2 - a1) * seg_int(a2, mid, hi)
    first = rng.random(n) < w1 / (w1 + w2)
    u = rng.random(n)
    out = np.empty(n)
    for mask, a, x0, x1 in ((first, a1, lo, mid), (~first, a2, mid, hi)):
        e = 1 - a
        out[mask] = (x0 ** e + u[mask] * (x1 ** e - x0 ** e)) ** (1 / e)
    return out


def forward_pairing(rng, n_sys, f_bin, q_gamma, q_min):
    m1 = sample_kroupa(rng, n_sys)
    is_bin = rng.random(n_sys) < f_bin
    u = rng.random(is_bin.sum())
    e = q_gamma + 1.0
    q = (q_min ** e + u * (1.0 - q_min ** e)) ** (1.0 / e)
    m2 = m1[is_bin] * q
    return m1, np.concatenate([m1, m2])


def random_pairing(rng, n_sys, f_sys):
    n_bin = int(round(n_sys * f_sys))
    a = sample_kroupa(rng, n_bin)
    b = sample_kroupa(rng, n_bin)
    single = sample_kroupa(rng, n_sys - n_bin)
    primary = np.concatenate([np.maximum(a, b), single])
    return primary, np.concatenate([a, b, single])


def bridge_t0(mass_min, mass_max):
    rows = []
    for path in sorted(glob.glob(str(ROOT / BRIDGE_GLOB))):
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        rng = d.get("mass_range_msun")
        if rng and (abs(rng[0] - mass_min) > 1e-6 or abs(rng[1] - mass_max) > 1e-6):
            continue
        defs = d["definitions"]
        rows.append((defs["component"]["initial_global"]["alpha"],
                     defs["primary"]["initial_global"]["alpha"]))
    return np.array(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-sys", type=int, default=2_000_000)
    ap.add_argument("--mass-min", type=float, default=0.30)
    ap.add_argument("--mass-max", type=float, default=2.50)
    ap.add_argument("--f-bin", type=float, default=0.568, help="headline p2_final2_v3")
    ap.add_argument("--q-gamma", type=float, default=-0.896, help="headline p2_final2_v3")
    ap.add_argument("--q-min", type=float, default=0.10, help="config.toml binary_q_min")
    ap.add_argument("--f-sys", type=float, default=0.95, help="petar_m45_grid.csv 中央值")
    ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "results" / "pairing_offsets.json")
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    lo, hi = a.mass_min, a.mass_max

    res = {"mass_range_msun": [lo, hi], "imf_breaks": BREAKS, "imf_slopes": SLOPES,
           "n_sys": a.n_sys, "seed": a.seed}
    for name, (prim, comp) in {
        "forward": forward_pairing(rng, a.n_sys, a.f_bin, a.q_gamma, a.q_min),
        "random": random_pairing(rng, a.n_sys, a.f_sys),
    }.items():
        ac = mle_powerlaw(comp, lo, hi)["alpha"]
        ap_ = mle_powerlaw(prim, lo, hi)["alpha"]
        res[name] = {"alpha_component": float(ac), "alpha_primary": float(ap_),
                     "offset_component_minus_primary": float(ac - ap_)}
    res["forward"]["params"] = {"f_bin": a.f_bin, "q_gamma": a.q_gamma, "q_min": a.q_min}
    res["random"]["params"] = {"binary_system_fraction": a.f_sys}

    t0 = bridge_t0(lo, hi)
    if len(t0):
        off = t0[:, 0] - t0[:, 1]
        res["petar_t0_check"] = {
            "n_runs": int(len(t0)),
            "alpha_component_mean": float(t0[:, 0].mean()),
            "alpha_primary_mean": float(t0[:, 1].mean()),
            "offset_mean": float(off.mean()),
            "offset_std": float(off.std(ddof=1)) if len(off) > 1 else None,
            "note": "10 組 grid 的 f_sys 不全是 0.95（bin_low 0.87、bin_high 0.99）",
        }
    for k in ("forward", "random"):
        r = res[k]
        print(f"{k:8s} component {r['alpha_component']:.3f}  primary "
              f"{r['alpha_primary']:.3f}  差 {r['offset_component_minus_primary']:+.3f}")
    if "petar_t0_check" in res:
        c = res["petar_t0_check"]
        print(f"PeTar t=0（{c['n_runs']} 組）component {c['alpha_component_mean']:.3f}  "
              f"primary {c['alpha_primary_mean']:.3f}  差 {c['offset_mean']:+.3f}"
              f" ± {c['offset_std']:.3f}")
    a.out.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫入 {a.out}")


if __name__ == "__main__":
    main()
