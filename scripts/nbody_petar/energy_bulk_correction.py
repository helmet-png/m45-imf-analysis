#!/usr/bin/env python
"""事後扣除 PeTar 開潮汐時漏記的「流失質量整體運動動能」，重算能量誤差。

功能：開銀河潮汐（`--galpy-set`）時，PeTar 的 `Total` 是銀河系座標下的
總能量（含星團質心以約 224 pc/Myr 繞銀河的整體動能），但恆星演化與
逃逸星移除造成質量減少時，`Modify` 記的動能只用相對質心的速度，漏掉
流失質量帶走的整體運動動能 ½|V_cm|²ΔM（見
`docs/planning/NBODY_PREREGISTRATION.md` 五節 2026-10-02 再訂正）。結果
`Error_cum` 被這一項主宰，不能判斷積分品質。這支程式把漏記的部分從
`Error_cum` 扣掉，得到可以用來篩選 run 的「修正後累積誤差」。

方法：
1. 讀 `petar.log` 每個輸出區間的 `Error`（PeTar `energy.hpp` 欄位順序，
   見 `summarize_training_runs.py`），以及 `data.0`…`data.K` 快照：每張
   快照表頭第 7–9 欄是質心速度 V_k（pc/Myr），每列第 1 欄是質量。
2. 每個區間 k→k+1：ΔM_k = M_k − M_{k+1}，漏記量預測
   P_k = −½ ΔM_k · (|V_k|² + |V_{k+1}|²)/2。修正後累積誤差
   E_corr = Error_cum − Σ_k P_k。
3. 分母用**星團內部能量** |E_int,0|（不是銀河系座標的 |Total|，後者被
   整體運動與銀河位能主宰，會讓任何誤差看起來都很小）：
   E_int,0 = Σ ½ m|v_rel|² + Σ_{i<j} −G m_i m_j / r_ij，由 `data.0` 直接算
   （檔內速度已是相對質心）。G = 0.00449830997959438 pc³/(M☉ Myr²)，
   與 PeTar `-u 1` 相同。
4. 已知的近似（決定這個指標的精度下限，不是 bug）：
   - 用區間兩端的 |V|² 平均，忽略區間內質量損失的時間分布；
   - 忽略交叉項 Σ dm (v_rel · V_cm)。v_rel 約 1 pc/Myr、V 約 224 pc/Myr，
     相對 ½V² 約 1% 量級；逃逸星的 v_rel 有方向性，不一定平均掉。
   所以這是**粗篩**：能抓出明顯壞掉的 run，不能證明積分誤差小於 1e-3。
   精確做法是修 PeTar 的記帳本身（方案 B）。

自我測試（`--self-test`）：
(a) 兩質點系統的內部能量與解析值一致；
(b) 造一組假 run：質心速度固定、每區間掉固定質量、PeTar 誤差恰好等於
    漏記量 → 修正後累積誤差為 0。
真實資料上的驗證：對「關潮汐」對照 run，由快照算出的 E_int,0 必須等於
PeTar 自己印的初始 Total（那個 run 沒有整體運動與銀河位能）——這一步
在執行報告裡印出，不藏在 self-test 裡。
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
G_PETAR = 0.00449830997959438  # pc^3 / (Msun Myr^2)，PeTar -u 1


def read_snapshot(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """回傳 (V_cm, mass, pos_rel, vel_rel)。"""
    with path.open() as f:
        head = f.readline().split()
    v_cm = np.array([float(x) for x in head[6:9]])
    data = np.loadtxt(path, skiprows=1, usecols=range(7), ndmin=2)
    return v_cm, data[:, 0], data[:, 1:4], data[:, 4:7]


def internal_energy(mass: np.ndarray, pos: np.ndarray, vel: np.ndarray, g: float = G_PETAR) -> float:
    ekin = 0.5 * np.sum(mass * np.sum(vel**2, axis=1))
    epot = 0.0
    n = len(mass)
    chunk = 512
    for i0 in range(0, n, chunk):
        i1 = min(n, i0 + chunk)
        d = pos[i0:i1, None, :] - pos[None, :, :]
        r = np.sqrt(np.sum(d**2, axis=2))
        mm = mass[i0:i1, None] * mass[None, :]
        idx_i = np.arange(i0, i1)[:, None]
        upper = np.arange(n)[None, :] > idx_i  # 只算 i<j，避免重複與自身
        epot -= g * np.sum(mm[upper] / r[upper])
    return float(ekin + epot)


def parse_physic_err(log: Path) -> tuple[list[float], float, float]:
    """回傳 (每區間 Error, 最後 Error_cum, 初始 Total)。"""
    rows = [l.split()[1:12] for l in log.read_text(encoding="utf-8", errors="replace").splitlines()
            if l.startswith("Physic:")]
    vals = [[float(x) for x in r] for r in rows]
    return [v[1] for v in vals[1:]], vals[-1][2], vals[0][3]


def correct_run(run_dir: Path) -> dict:
    errs, err_cum, total0 = parse_physic_err(run_dir / "petar.log")
    n_snap = len(errs) + 1
    snaps = [read_snapshot(run_dir / f"data.{k}") for k in range(n_snap)]
    m = np.array([s[1].sum() for s in snaps])
    v2 = np.array([s[0] @ s[0] for s in snaps])
    pred = -0.5 * (m[:-1] - m[1:]) * 0.5 * (v2[:-1] + v2[1:])
    v0, mass0, pos0, vel0 = snaps[0]
    e_int0 = internal_energy(mass0, pos0, vel0)
    e_corr = err_cum - pred.sum()
    return {
        "run_id": run_dir.name,
        "n_intervals": len(errs),
        "mass_initial": float(m[0]),
        "mass_final": float(m[-1]),
        "v_cm_initial": float(np.sqrt(v2[0])),
        "total_initial": total0,
        "e_internal_initial": e_int0,
        "err_cum": err_cum,
        "pred_bulk_missing": float(pred.sum()),
        "ratio_err_cum_over_pred": float(err_cum / pred.sum()) if pred.sum() else float("nan"),
        "err_cum_corrected": float(e_corr),
        "err_cum_corrected_over_e_int0": float(e_corr / abs(e_int0)),
        "err_cum_raw_over_e_int0": float(err_cum / abs(e_int0)),
    }


def run_self_test() -> dict:
    checks = {}
    m = np.array([2.0, 3.0])
    pos = np.array([[0.0, 0, 0], [4.0, 0, 0]])
    vel = np.array([[0.0, 1, 0], [0.0, -1, 0]])
    expect = 0.5 * (2 + 3) * 1.0 - G_PETAR * 6.0 / 4.0
    checks["two_body_internal_energy"] = abs(internal_energy(m, pos, vel) - expect) < 1e-12

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "mb_train_0000_s1"
        d.mkdir()
        V = np.array([100.0, 0.0, 0.0])
        masses = [10.0, 8.0, 7.0]
        lines = ["Physic: -0 0 0 -1000 0 0 0 0 0 0 0"]
        cum = 0.0
        for k in range(2):
            e = -0.5 * (masses[k] - masses[k + 1]) * (V @ V)
            cum += e
            lines.append(f"Physic: 0 {e} {cum} -1000 0 0 0 0 0 0 0")
        (d / "petar.log").write_text("\n".join(lines) + "\n")
        for k, mk in enumerate(masses):
            head = f"{k} 2 {5.0*k} 0 0 0 {V[0]} {V[1]} {V[2]}\n"
            rows = f"{mk/2} 1 0 0 0 0.1 0\n{mk/2} -1 0 0 0 -0.1 0\n"
            (d / f"data.{k}").write_text(head + rows)
        r = correct_run(d)
    checks["corrected_error_zero_when_only_bulk_term"] = abs(r["err_cum_corrected"]) < 1e-9
    checks["ratio_one"] = abs(r["ratio_err_cum_over_pred"] - 1.0) < 1e-12
    if not all(checks.values()):
        raise AssertionError(f"energy_bulk_correction self-test failed: {checks}")
    return {"status": "synthetic_validation_only", "checks": checks}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs-dir", type=Path, default=REPO_ROOT / "runs_training")
    ap.add_argument("--out-csv", type=Path,
                    default=REPO_ROOT / "results" / "nbody_training_energy_correction.csv")
    ap.add_argument("--validate-notide-run", type=Path, default=None,
                    help="關潮汐對照 run 的目錄：比對快照算的 E_int,0 與 PeTar 初始 Total")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(run_self_test(), indent=2))
        return

    if args.validate_notide_run:
        total0_notide = parse_physic_err(args.validate_notide_run / "petar.log")[2]
        _, mass0, pos0, vel0 = read_snapshot(args.validate_notide_run / "data.0")
        e_int = internal_energy(mass0, pos0, vel0)
        print(f"[驗證] 關潮汐對照 run：PeTar 初始 Total = {total0_notide:.6e}，"
              f"快照算 E_int,0 = {e_int:.6e}，相對差 {abs(e_int/total0_notide-1):.2e}", flush=True)

    rows = []
    for d in sorted(args.runs_dir.glob("mb_train_*")):
        if not (d / "petar.log").exists():
            continue
        try:
            rows.append(correct_run(d))
        except (OSError, ValueError, IndexError) as exc:
            rows.append({"run_id": d.name, "error": f"{type(exc).__name__}: {exc}"})
    fields = sorted({k for r in rows for k in r}, key=lambda k: (k != "run_id", k))
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if "error" not in r]
    corr = np.array([r["err_cum_corrected_over_e_int0"] for r in ok])
    raw = np.array([r["err_cum_raw_over_e_int0"] for r in ok])
    ratio = np.array([r["ratio_err_cum_over_pred"] for r in ok])
    print(json.dumps({
        "n_runs": len(ok), "n_errors": len(rows) - len(ok),
        "raw_err_cum_over_e_int0_pct_0_50_90_100": np.percentile(np.abs(raw), [0, 50, 90, 100]).tolist(),
        "corrected_over_e_int0_pct_0_50_90_100": np.percentile(np.abs(corr), [0, 50, 90, 100]).tolist(),
        "ratio_err_cum_over_pred_pct_10_50_90": np.nanpercentile(ratio, [10, 50, 90]).tolist(),
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
