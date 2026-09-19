# -*- coding: utf-8 -*-
"""D19 Stage 2：用極端運動學 control field 檢查 pyUPMASK 偽陽性率對 G 的變化。

`data/m45_control_field.csv` 的星在 pmRA、pmDE 或視差至少一維偏離 M45
成員中心 10σ，因此可視為已知非成員。把它們與 G<20 的 pyUPMASK 輸出依
source_id 合併後，本腳本量每個 0.5 等分箱中 P(member) >= 0.7 的比例，
並以 Wilson 區間表達有限樣本的不確定度。

這是「極端場星會不會在暗端被誤判成高機率成員」的檢查，不是機率校準：
control field 不含真成員，無法量召回率或完整度。因此即使未見偽陽性接縫，
也不能單靠本檢查報告 D19 的 alpha；Stage 2 仍需要 (G, colour) 完整度模型。
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent.parent
CONTROL = HERE / "data" / "m45_control_field.csv"
FULL_RESULT = HERE / "results" / "d19_g20_full.dat"
OUT = HERE / "results" / "d19_membership_reliability.json"
P_THRESHOLD = 0.7
G_EDGES = [16.0 + 0.5 * i for i in range(9)]
Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """95% Wilson binomial interval without a normal approximation at zero."""
    if total == 0:
        return math.nan, math.nan
    p = successes / total
    denom = 1.0 + Z_95 ** 2 / total
    centre = (p + Z_95 ** 2 / (2.0 * total)) / denom
    half = Z_95 * math.sqrt(p * (1.0 - p) / total + Z_95 ** 2 / (4.0 * total ** 2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def read_probabilities() -> dict[int, float]:
    lines = FULL_RESULT.read_text(encoding="utf-8").splitlines()
    expected = ("source_id _x _y pmRA pmDE Plx e_pmRA e_pmDE e_Plx "
                "Gmag BP_RP RUWE probs_final")
    if not lines or lines[0] != expected:
        raise ValueError("d19_g20_full.dat header 不符預期格式")
    probabilities: dict[int, float] = {}
    for number, row in enumerate(lines[1:], start=2):
        fields = row.split()
        if len(fields) != 13:
            raise ValueError(f"d19_g20_full.dat 第 {number} 列不是 13 欄")
        source_id = int(fields[0])
        if source_id in probabilities:
            raise ValueError(f"d19_g20_full.dat source_id 重複：{source_id}")
        probability = float(fields[12])
        if not math.isfinite(probability):
            raise ValueError(f"d19_g20_full.dat 第 {number} 列機率非有限值")
        probabilities[source_id] = probability
    return probabilities


def read_control() -> list[tuple[int, float]]:
    with CONTROL.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"source_id", "phot_g_mean_mag"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("m45_control_field.csv 缺少 source_id 或 phot_g_mean_mag")
    return [(int(row["source_id"]), float(row["phot_g_mean_mag"])) for row in rows]


def summarize(samples: list[tuple[float, float]], lo: float, hi: float) -> dict[str, float | int]:
    probabilities = [p for g, p in samples if lo <= g < hi]
    high = sum(p >= P_THRESHOLD for p in probabilities)
    lower, upper = wilson_interval(high, len(probabilities))
    # probs_final = -1 是 pyUPMASK 的未分類哨兵值，不是機率；分母含它們會把
    # 「沒被分類」誤當成「被分類為非成員」，另外回報僅已分類星的比率。
    classified = [p for p in probabilities if p >= 0.0]
    high_c = sum(p >= P_THRESHOLD for p in classified)
    lower_c, upper_c = wilson_interval(high_c, len(classified))
    return {
        "n_unclassified": len(probabilities) - len(classified),
        "fpr_classified_only": high_c / len(classified) if classified else math.nan,
        "wilson_95_classified_only": [lower_c, upper_c],
        "g_lo": lo,
        "g_hi": hi,
        "n_control": len(probabilities),
        "n_p_ge_0p7": high,
        "false_positive_rate": high / len(probabilities) if probabilities else math.nan,
        "wilson_95_lo": lower,
        "wilson_95_hi": upper,
    }


def main() -> None:
    probabilities = read_probabilities()
    control = read_control()
    missing = [source_id for source_id, _ in control if source_id not in probabilities]
    if missing:
        raise ValueError(f"{len(missing)} 顆 control field 星不在 d19 輸出中")
    samples = [(gmag, probabilities[source_id]) for source_id, gmag in control]
    bins = [summarize(samples, lo, hi) for lo, hi in zip(G_EDGES[:-1], G_EDGES[1:])]
    if any(row["n_control"] == 0 for row in bins):
        raise ValueError("G=16–20 的 control field 有空分箱")

    bright = summarize(samples, 16.0, 18.0)
    dark = summarize(samples, 18.0, 20.0)
    no_observed_rise = dark["false_positive_rate"] <= bright["false_positive_rate"]
    report = {
        "purpose": "extreme-kinematic-control false-positive rate versus G",
        "inputs": {
            "full_result": str(FULL_RESULT.relative_to(HERE)),
            "control_field": str(CONTROL.relative_to(HERE)),
            "n_result_rows": len(probabilities),
            "n_control_rows": len(control),
            "n_control_matched": len(control),
        },
        "probability_threshold": P_THRESHOLD,
        "bins": bins,
        "bright_g16_18": bright,
        "dark_g18_20": dark,
        "stage2_decision": {
            "probability_seam": (
                "not observed in this extreme control at P>=0.7"
                if no_observed_rise else "observed: dark false-positive rate exceeds bright rate"
            ),
            "alpha_reportable": False,
            "alpha_reason": (
                "This control constrains false positives only. It does not establish "
                "membership completeness as a function of (G, colour), which is the "
                "predeclared D19 gate before reporting alpha."
            ),
        },
        "scope_limit": (
            "The 10-sigma control is deliberately far from M45 kinematics. These rates "
            "must not be interpreted as a calibration of P(member) near the cluster boundary."
        ),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"control match: {len(control)}/{len(control)}")
    print("G bin       N    P>=0.7   FPR      Wilson 95%      P<0(未分類)")
    for row in bins:
        print(f"{row['g_lo']:>4.1f}-{row['g_hi']:<4.1f} "
              f"{row['n_control']:>5} {row['n_p_ge_0p7']:>8} "
              f"{row['false_positive_rate']:>7.4f} "
              f"[{row['wilson_95_lo']:.4f}, {row['wilson_95_hi']:.4f}]"
              f"  {row['n_unclassified']:>5}")
    print(f"\nStage 2 probability seam: {report['stage2_decision']['probability_seam']}")
    print("Stage 2 alpha: do not report; completeness(G, colour) is still unmeasured.")
    print(f"wrote {OUT.relative_to(HERE)}")


if __name__ == "__main__":
    main()
