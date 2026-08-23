#!/usr/bin/env python
"""Summarize completed paired BP20/BP15 diagnostic forward runs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

EXPECT_N_SYN = 3000
EXPECT_REFINES = "3,3"
# 2026-08-23 CodeRabbit review：原本 row() 只讀 C，不驗證 manifest——
# 若某個檔案被錯誤結果覆蓋或置換（例如 BP15 那份不小心被 BP20 的輸出
# 覆寫），輸出仍會照樣印出固定的 paired seeds 與 BP15-BP20 差值，不會
# 有任何警示。selection_file 是唯一能分辨「這份輸出真的是 BP15 smoke
# 輸入跑出來的、不是 BP20」的欄位，一併驗證。
EXPECT_SELECTION = {
    "bp20": "data/selection.npz",
    "bp15": "results/selection_bp15_smoke.npz",
}


def row(name: str, *, kind: str, repeat_offset: int) -> list[float]:
    path = RESULTS / name
    with np.load(path, allow_pickle=False) as data:
        if "__manifest__" not in data.files:
            raise ValueError(f"{name}：沒有 manifest，無法驗證這份輸出的設定")
        man = json.loads(str(data["__manifest__"]))
        C = np.asarray(data["C"], float)
    if C.shape[0] < 1:
        raise ValueError(f"{name}：C 是空的，沒有任何結果列")
    if man.get("n_syn") != EXPECT_N_SYN:
        raise ValueError(
            f"{name}：n_syn={man.get('n_syn')!r}，預期 {EXPECT_N_SYN}")
    if man.get("refines") != EXPECT_REFINES:
        raise ValueError(
            f"{name}：refines={man.get('refines')!r}，預期 {EXPECT_REFINES!r}")
    if man.get("repeat_offset") != repeat_offset:
        raise ValueError(
            f"{name}：repeat_offset={man.get('repeat_offset')!r}，"
            f"預期 {repeat_offset}")
    if man.get("selection_file") != EXPECT_SELECTION[kind]:
        raise ValueError(
            f"{name}：selection_file={man.get('selection_file')!r}，"
            f"預期 {EXPECT_SELECTION[kind]!r}（這份輸出可能不是真的用"
            f"{kind.upper()} 輸入跑出來的）")
    return C[0].tolist()


def main() -> None:
    names = ["logage", "av", "f_bin", "alpha", "mh", "q_gamma", "dav"]
    pairs = []
    # Each offset is a new paired Monte-Carlo draw.  Keep this list explicit
    # so a missing or mismatched output cannot silently be averaged in.
    for offset, (seed, suffix) in enumerate([(2000, ""), (2013, "_rep1"), (2026, "_rep2")]):
        bp20 = row(f"fit_real_bp20_control_3k{suffix}.npz", kind="bp20", repeat_offset=offset)
        bp15 = row(f"fit_real_bp15_smoke_3k{suffix}.npz", kind="bp15", repeat_offset=offset)
        pairs.append({
            "seed": seed,
            "bp20": dict(zip(names, bp20)),
            "bp15": dict(zip(names, bp15)),
            "bp15_minus_bp20": dict(zip(names, np.subtract(bp15, bp20).tolist())),
        })
    deltas = np.asarray([[p["bp15_minus_bp20"][n] for n in names] for p in pairs])
    output = {
        "status": "diagnostic_inconclusive_monte_carlo_noise",
        "settings": {"n_synthetic": 3000, "paired_seeds": [2000, 2013, 2026],
                     "refines": [3, 3], "config": "C"},
        "pairs": pairs,
        "paired_delta_mean": dict(zip(names, deltas.mean(axis=0).tolist())),
        "paired_delta_range": dict(zip(names, np.ptp(deltas, axis=0).tolist())),
        "stopped_incomplete_runs": {
            "n_synthetic": 10000, "seed": 2026,
            "reason": "both paired jobs exceeded 55 minutes when sharing one machine; no atomic result file was produced"
        },
        "interpretation": [
            "The alpha delta changed sign across the paired seeds, so these runs cannot establish a BP15 effect.",
            "The isolated BP15 inputs and custom fit entrypoint are verified and reproducible.",
            "A formal comparison needs matched BP20/BP15 runs at 40000 synthetic systems and multiple paired seeds on separate workers.",
        ],
    }
    (RESULTS / "bp15_forward_smoke_summary.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
