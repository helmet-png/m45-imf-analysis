# -*- coding: utf-8 -*-
"""PDMF -> IMF 第 3 步驗收：LIMEPY 多質量模型預測的 alpha(<r) 跟觀測比較。

見 WORK_BOARD.md「待認領工作：第 2 步四項到齊後新解鎖的工作」表
`limepy_radial_crosscheck` 條目。讀 `limepy_multimass.py` 已經擬合好的
King(g=1) 模型（results/limepy_multimass.npz），從模型的投影質量面密度
剖面 Sigmaj(R) 算出模型預測在 r1/r2/r3/rall 對應半徑處的「模型 alpha」，
跟 radial_r1/r2/r3/rall 的觀測值（目前是 _prelim 版，單次無誤差棒）並排
比較。

**方法論限制（誠實記錄，不要省略）**：
1. 模型只切了 3 個質量區間（`N_MASS_BINS=3`），逐半徑對這 3 個點做
   log(N) vs log(m) 線性回歸取斜率當「模型 alpha」——這是用 3 個點的
   冪律擬合，跟觀測端的完整 MLE（用全部 694 顆星的個別質量）不是同一種
   估計量，只能當粗略的方向性比較，不是嚴格同方法論的對照。
2. 觀測端目前只有 _prelim（單次無誤差棒）版本，`radial_final_reruns`
   （有誤差棒版）還沒跑完，這裡的比較只能看方向/量級，不能下「模型
   統計上顯著偏離觀測」這種結論。
3. LIMEPY 模型的 mj/Mj 比例是直接固定成觀測值（見 limepy_multimass.py
   docstring 限制 2），不是獨立預測——這個交叉比對本質上是「模型的
   徑向輪廓形狀 vs 觀測的徑向輪廓形狀」，不是「模型從頭預測質量函數」。

需要 astro-limepy 環境，跟 limepy_multimass.py 一樣：
    .venv_limepy/Scripts/python scripts/diagnostics/limepy_radial_crosscheck.py
"""
from __future__ import annotations

import sys
import numpy as np
from pathlib import Path
import limepy

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from limepy_multimass import load_masses_and_radii, build_profiles  # noqa: E402

DIST_PC = 136.0  # 跟 limepy_multimass.py / dynamics_estimate.py 一致

# radial_r1/r2/r3/rall 的半徑定義（度）與觀測到的 _prelim alpha（見
# LIMITATIONS.md A5、WORK_BOARD.md 第 2 步）。rall 用樣本實際最大半徑
# （不是固定角度），跟 limepy_multimass.py 存的 r_sample_max 一致。
RADII_DEG = {"r1": 1.0, "r2": 2.0, "r3": 3.0}
OBS_ALPHA_PRELIM = {"r1": 2.10, "r2": 2.43, "r3": 2.50, "rall": 2.43}


def model_alpha_at_radius(model, mj, delta_m, R_max_pc: float) -> float:
    """對 3 個質量區間，分別把 Sigmaj(R)/mj 從 0 積分到 R_max，得到
    每個區間的模型預測星數 N_j(<R)，除以該區間的質量寬度 delta_m 換成
    密度 dN/dm，再對 (log mj, log(dN/dm)) 做線性回歸——斜率的負值就是
    這個半徑內的模型 alpha（dN/dm ~ m^-alpha 的定義）。**除以 delta_m
    這一步是必要的**：3 個區間是用星數百分位切的，質量寬度不等，直接
    對星數 N_j 取斜率會把「哪個區間比較寬」跟「哪個區間比較多星」混在
    一起，算出來的斜率沒有物理意義（第一版腳本漏掉這步，算出負值）。
    """
    n_j = np.zeros(len(mj))
    for j in range(len(mj)):
        R = model.R
        sigma_n = model.Sigmaj[j] / mj[j]  # M_sun/pc^2 -> 顆/pc^2
        inside = R <= R_max_pc
        R_in = np.concatenate([R[inside], [R_max_pc]])
        sigma_in = np.concatenate([
            sigma_n[inside],
            [np.interp(R_max_pc, R, sigma_n)]])
        integrand = 2 * np.pi * R_in * sigma_in
        trapz = getattr(np, "trapezoid", None) or np.trapz
        n_j[j] = trapz(integrand, R_in)
    dn_dm = n_j / delta_m
    log_m = np.log10(mj)
    log_dndm = np.log10(np.clip(dn_dm, 1e-12, None))
    slope, _ = np.polyfit(log_m, log_dndm, 1)
    return -slope, n_j


def main():
    d = dict(np.load(REPO_ROOT / "results" / "limepy_multimass.npz",
                     allow_pickle=True))
    mj = d["mj"]

    # 重新跑一次跟 limepy_multimass.py 完全相同的質量分箱，只為了拿
    # edges_m（原始擬合沒有把這個存進 npz）；不影響已擬合好的模型參數。
    masses, r_pc = load_masses_and_radii()
    keep = (masses >= 0.30) & (masses <= 2.50)
    mj_check, _, _, _, _, _, edges_m = build_profiles(masses[keep], r_pc[keep])
    delta_m = np.diff(edges_m)
    if not np.allclose(mj_check, mj, atol=1e-6):
        print("警告：重算的質量分箱跟 npz 存的 mj 對不上，delta_m 正規化"
             "可能不準，結果僅供參考")
    else:
        print(f"重算的分箱 mj 跟 npz 存的完全一致（{keep.sum()} 顆星），"
             f"edges_m={edges_m}，delta_m 正規化可信")

    model = limepy.limepy(float(d["phi0"]), int(d["model_g"]),
                          mj=list(mj), Mj=list(d["Mj_frac"]),
                          r0=float(d["r0"]), M=float(d["M_fit"]),
                          project=True)
    if not model.converged:
        raise RuntimeError("模型沒有收斂，讀出的擬合結果可能有問題")

    r_sample_max = float(d["r_sample_max"])
    print(f"模型：phi0={float(d['phi0']):.2f}, r0={float(d['r0']):.2f} pc, "
         f"M={float(d['M_fit']):.1f} Msun, 樣本邊緣={r_sample_max:.2f} pc")
    print()
    print(f"{'半徑':>6} {'R(pc)':>8} {'模型alpha':>10} {'觀測alpha(prelim)':>18} {'差':>8}")

    rows = []
    for tag, deg in RADII_DEG.items():
        R_pc = np.radians(deg) * DIST_PC
        a_model, n_j = model_alpha_at_radius(model, mj, delta_m, R_pc)
        a_obs = OBS_ALPHA_PRELIM[tag]
        diff = a_model - a_obs
        rows.append((tag, R_pc, a_model, a_obs, diff, n_j.tolist()))
        print(f"{tag:>6} {R_pc:8.2f} {a_model:10.3f} {a_obs:18.2f} {diff:8.3f}")

    a_model_all, n_j_all = model_alpha_at_radius(model, mj, delta_m, r_sample_max)
    a_obs_all = OBS_ALPHA_PRELIM["rall"]
    rows.append(("rall", r_sample_max, a_model_all, a_obs_all,
                a_model_all - a_obs_all, n_j_all.tolist()))
    print(f"{'rall':>6} {r_sample_max:8.2f} {a_model_all:10.3f} "
         f"{a_obs_all:18.2f} {a_model_all - a_obs_all:8.3f}")

    diffs = [r[4] for r in rows]
    print()
    print(f"模型-觀測 alpha 差的範圍：{min(diffs):.3f} ~ {max(diffs):.3f}")
    print("**沒有誤差棒可比較（模型是確定性計算，觀測是 _prelim 單次無誤差棒），"
         "只能看差距量級，不能下統計顯著性結論。**")

    out = REPO_ROOT / "results" / "limepy_radial_crosscheck.npz"
    np.savez(out,
             tags=np.array([r[0] for r in rows]),
             radius_pc=np.array([r[1] for r in rows]),
             model_alpha=np.array([r[2] for r in rows]),
             obs_alpha_prelim=np.array([r[3] for r in rows]),
             diff=np.array([r[4] for r in rows]),
             mj=mj)
    print(f"\n寫入 {out}")


if __name__ == "__main__":
    main()
