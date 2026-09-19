# -*- coding: utf-8 -*-
"""D19 Stage 2／C8：pyUPMASK 成員判定完整度（召回率）對 G 的注入回收測試。

**要回答的問題**：把成員深度從 G<18 延伸到 G<20，暗端的真成員會不會被
pyUPMASK 漏掉？PR #219 的 control field 只量了偽陽性（極端場星被誤判成成員
的比例），而且因為 control 在分群用的三個維度上偏離 10σ，≈0% 是設計出來
的結果；「真成員被誤丟」完全沒測到。這支腳本補上這一半。

**做法**：
1. 從 `data/m45_g20_full.dat`（G<20 全場星，9,278 顆）移除現有 1,078 顆成員
   （避免把星團算兩次），改注入合成成員，其中 G 在 16–20 每 0.5 等分箱
   注入相同顆數（預設 190，共 1,520 顆，量級與真實星團 P≥0.7 的 1,542 顆
   相當，使星團／場星密度比與真實情況相近）。
2. 合成成員的運動學：以 G<17 的真成員估計星團中心與**本質**離散度
   （觀測變異數減去平均測光誤差平方），再加上各星自己的觀測誤差。
3. **誤差不是憑空給的**：每顆合成星的 (e_pmRA, e_pmDE, e_Plx) 取自 G 與
   BP−RP 最接近的真實場星，所以暗端誤差變大的效應是真實的。
4. 位置從真成員的 (x, y) 重抽並加 0.05° 抖動，保留真實的空間分布。
5. 用產線設定（OL_runs=25、KDE 後驗、PCA 2 維、resample）跑 pyUPMASK，
   量每個 G 分箱中 P≥0.7 的合成成員比例（Wilson 95% 區間）。

**這個測試量得到什麼、量不到什麼**（引用前必讀）：
- 量得到：在「星團運動學服從高斯、離散度等於亮端真成員」的假設下，
  pyUPMASK 隨 G 變暗、誤差變大時的召回率。
- 量不到：真實暗端成員若運動學不同於亮端（例如質量分層造成的離散度差異、
  潮汐尾）——合成星按定義服從我們給的分布，所以這是**樂觀的上限估計**，
  不是完整度的校準。P<0 的哨兵值（pyUPMASK 未分類）算作未召回並另外回報。
- 對成員而言 BP−RP 是 G 的函數（沿主序），所以 completeness(G) 在成員
  母體上近似等於 completeness(G, colour)；雙星造成的偏離不在此測試內。

用法（worker 上，repo 根目錄）：
    python scripts/diagnostics/d19_completeness_injection.py --seed 1
本機只驗證建構與分析邏輯（不跑 pyUPMASK）：
    python scripts/diagnostics/d19_completeness_injection.py --seed 1 --build-only
    python scripts/diagnostics/d19_completeness_injection.py --seed 1 --analyze-only
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
FIELD = HERE / "data" / "m45_g20_full.dat"
MEMBERS = HERE / "data" / "cmd_members.csv"
PYUPMASK_PYTHON = HERE / ".venv_pyupmask" / "bin" / "python3"
HEADER = ("source_id _x _y pmRA pmDE Plx e_pmRA e_pmDE e_Plx "
          "Gmag BP_RP RUWE")
COLS = HEADER.split()
G_EDGES = [16.0 + 0.5 * i for i in range(9)]
N_PER_BIN = 190
FAKE_ID_BASE = 8_000_000_000_000_000_000
THRESHOLDS = (0.5, 0.7, 0.9)
Z95 = 1.959963984540054
BRIGHT_G = 17.0
POS_JITTER_DEG = 0.05
N_DONORS = 20


def read_dat(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines[0].split()[:12] != COLS:
        raise ValueError(f"{path.name} header 不符")
    ids = np.array([int(r.split()[0]) for r in lines[1:]], dtype=np.int64)
    vals = np.array([[float(t) for t in r.split()[1:12]] for r in lines[1:]])
    return ids, vals, lines[0].split()


def wilson(k: int, n: int):
    if n == 0:
        return math.nan, math.nan
    p = k / n
    d = 1 + Z95 ** 2 / n
    c = (p + Z95 ** 2 / (2 * n)) / d
    h = Z95 * math.sqrt(p * (1 - p) / n + Z95 ** 2 / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def build(seed: int, out_path: Path, truth_path: Path):
    rng = np.random.default_rng(20260919 + seed)
    ids, v, _ = read_dat(FIELD)
    ix = {n: i for i, n in enumerate(COLS[1:])}
    member_ids = set(int(x.split(",")[0]) for x in
                     MEMBERS.read_text(encoding="utf-8").splitlines()[1:])
    is_mem = np.array([int(i) in member_ids for i in ids])
    if is_mem.sum() != 1078:
        raise ValueError(f"預期 1,078 顆現有成員，實際 {int(is_mem.sum())}")

    mem = v[is_mem]
    bright = mem[mem[:, ix["Gmag"]] < BRIGHT_G]
    center, sigma_int = {}, {}
    for k, e in (("pmRA", "e_pmRA"), ("pmDE", "e_pmDE"), ("Plx", "e_Plx")):
        col = bright[:, ix[k]]
        center[k] = float(np.median(col))
        var = float(np.var(col) - np.mean(bright[:, ix[e]] ** 2))
        sigma_int[k] = math.sqrt(max(var, 1e-6))

    field_idx = np.where(~is_mem)[0]
    fv = v[field_idx]
    g_field = fv[:, ix["Gmag"]]
    c_field = fv[:, ix["BP_RP"]]
    g_mem = mem[:, ix["Gmag"]]
    c_mem = mem[:, ix["BP_RP"]]
    ok_mem = np.isfinite(c_mem)

    fake_rows, fake_g = [], []
    n = 0
    for lo, hi in zip(G_EDGES[:-1], G_EDGES[1:]):
        for _ in range(N_PER_BIN):
            g = rng.uniform(lo, hi)
            j = np.where(ok_mem)[0][np.argmin(np.abs(g_mem[ok_mem] - g))]
            colour = float(c_mem[j])
            ok_f = np.isfinite(c_field)
            dist = (np.abs(g_field - g) / 0.25) ** 2 + \
                   np.where(ok_f, ((c_field - colour) / 0.3) ** 2, 4.0)
            donor = fv[rng.choice(np.argsort(dist)[:N_DONORS])]
            e_ra, e_de, e_pl = (donor[ix["e_pmRA"]], donor[ix["e_pmDE"]],
                                donor[ix["e_Plx"]])
            src = mem[rng.integers(len(mem))]
            x = src[ix["_x"]] + rng.normal(0, POS_JITTER_DEG)
            y = src[ix["_y"]] + rng.normal(0, POS_JITTER_DEG)
            row = [FAKE_ID_BASE + n, x, y,
                   center["pmRA"] + rng.normal(0, sigma_int["pmRA"]) + rng.normal(0, e_ra),
                   center["pmDE"] + rng.normal(0, sigma_int["pmDE"]) + rng.normal(0, e_de),
                   center["Plx"] + rng.normal(0, sigma_int["Plx"]) + rng.normal(0, e_pl),
                   e_ra, e_de, e_pl, g, colour, donor[ix["RUWE"]]]
            fake_rows.append(row)
            fake_g.append(g)
            n += 1

    def fmt(x):
        return "nan" if (isinstance(x, float) and not np.isfinite(x)) else repr(float(x)) \
            if not isinstance(x, (int, np.integer)) else str(int(x))

    out = [HEADER]
    for i, r in zip(ids[field_idx], fv):
        out.append(" ".join([str(int(i))] + [fmt(float(x)) for x in r]))
    for r in fake_rows:
        out.append(" ".join([str(int(r[0]))] + [fmt(float(x)) for x in r[1:]]))
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    truth = {"seed": seed, "n_field_kept": int(len(field_idx)),
             "n_injected": len(fake_rows), "n_per_bin": N_PER_BIN,
             "center": center, "sigma_intrinsic": sigma_int,
             "fake_ids": [int(r[0]) for r in fake_rows], "fake_g": fake_g}
    truth_path.write_text(json.dumps(truth), encoding="utf-8")
    print(f"注入輸入：{out_path.name}，場星 {len(field_idx)} + 合成 {len(fake_rows)}")
    print(f"  星團中心 {center}\n  本質離散度 {sigma_int}")
    return truth


def analyze(result_path: Path, truth_path: Path, out_json: Path):
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    lines = result_path.read_text(encoding="utf-8").splitlines()
    prob = {int(r.split()[0]): float(r.split()[12]) for r in lines[1:]}
    fake = truth["fake_ids"]
    if any(i not in prob for i in fake):
        raise ValueError("有合成星不在 pyUPMASK 輸出裡")
    g = np.array(truth["fake_g"])
    p = np.array([prob[i] for i in fake])
    report = {"seed": truth["seed"], "n_injected": len(fake),
              "sentinel_total": int((p < 0).sum()), "bins": {}, "scope":
              "樂觀上限：合成成員服從高斯運動學，見檔頭說明；不是完整度校準"}
    print(f"\nG 分箱召回率（合成成員 P>=閾值 的比例；Wilson 95%）")
    print(f"{'G':>10}{'N':>6}" + "".join(f"{'P>='+str(t):>22}" for t in THRESHOLDS)
          + f"{'P<0':>6}")
    for lo, hi in zip(G_EDGES[:-1], G_EDGES[1:]):
        m = (g >= lo) & (g < hi)
        n = int(m.sum())
        row = {"n": n, "sentinel": int((p[m] < 0).sum())}
        cells = []
        for t in THRESHOLDS:
            k = int((p[m] >= t).sum())
            a, b = wilson(k, n)
            row[f"recall_p{t}"] = k / n
            row[f"wilson_p{t}"] = [a, b]
            cells.append(f"{k / n:>7.3f} [{a:.3f},{b:.3f}]")
        report["bins"][f"{lo:.1f}-{hi:.1f}"] = row
        print(f"{lo:>4.1f}-{hi:<4.1f}{n:>6}" + "".join(f"{c:>22}" for c in cells)
              + f"{row['sentinel']:>6}")
    r18 = np.mean(p[g < 18] >= 0.7)
    r20 = np.mean(p[g >= 18] >= 0.7)
    report["recall_p0.7_g16_18"] = float(r18)
    report["recall_p0.7_g18_20"] = float(r20)
    print(f"\nP>=0.7 召回率：G<18 {r18:.3f}，G>=18 {r20:.3f}")
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"寫入 {out_json.relative_to(HERE)}")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--result", default=None,
                    help="--analyze-only 時指定 pyUPMASK 輸出檔")
    a = ap.parse_args()

    name = f"d19_inject_s{a.seed}"
    inp = HERE / "prepared" / f"{name}.dat"
    truth_path = HERE / "results" / f"{name}_truth.json"
    result = Path(a.result) if a.result else HERE / "results" / f"{name}.dat"
    out_json = HERE / "results" / f"{name}_recall.json"
    (HERE / "results").mkdir(exist_ok=True)

    if not a.analyze_only:
        build(a.seed, inp, truth_path)
        if a.build_only:
            return
        r = subprocess.run(["bash", str(HERE / "setup" / "setup_pyupmask.sh"),
                            sys.executable], cwd=HERE, text=True,
                           capture_output=True)
        if r.returncode != 0:
            print(r.stdout[-3000:], r.stderr[-3000:])
            sys.exit(1)
        t0 = time.time()
        r = subprocess.run([str(PYUPMASK_PYTHON),
                            str(HERE / "scripts" / "drivers" / "run_variant.py"),
                            "--name", name, "--input", inp.name,
                            "--ol-runs", "25", "--seed", str(99 + a.seed)],
                           cwd=HERE, text=True, capture_output=True)
        print(f"pyUPMASK 耗時 {time.time() - t0:.1f}s")
        if r.returncode != 0:
            print(r.stdout[-4000:], r.stderr[-4000:])
            sys.exit(1)
    analyze(result, truth_path, out_json)


if __name__ == "__main__":
    main()
