"""Compute alpha(r) from a PeTar snapshot of an N-body cluster pilot run,
reusing the M45 project's own mle_powerlaw() (pipeline/step5_imf.py) for a
like-for-like comparison against the observational alpha(r).

Run from the directory containing the PeTar output (data.<N>.single/.binary
produced by `petar.data.process`, using `tools/data_process.py` -- the
`Particle`/`Binary` loader already returns positions in the density-center
frame via `correctCenter()`, so do NOT subtract data.core's center again;
that was a real bug in an earlier version of this script, caught by
CodeRabbit review on PR #29 and confirmed by checking that the median
position in a .single file is ~(0,0,0), not the core position). Needs one
path that varies by machine:
  NBODY_INSTALL_PATH   PeTar install prefix (contains include/petar/), see
                       nbody_setup/README.md. Default: sibling nbody/install
                       next to this repo (i.e. ../../nbody/install from
                       this file).
  (this repo's own path is found automatically via this file's location)

Usage:
  NBODY_INSTALL_PATH=/path/to/nbody/install python analyze_alpha_r.py data.25
  python analyze_alpha_r.py --self-test      # binning logic only, no PeTar

===========================================================================
2026-08-20：分箱／口徑對齊（WORK_BOARD `nbody_prior_from_radial` 起手式）
===========================================================================
WORK_BOARD 要求「開始前先解決一個真的定義不一致的問題」，並提供兩個修法
擇一。**這裡採用修法 (1)**：把模擬粒子改用**累積**半徑切法，校準目標就是
現成的 `radial_r1/r2/r3/rall`，不用另外算一組觀測值。

實際動手時發現不一致**不只 WORK_BOARD 講的分箱那一項，總共有三項**，
三項都要對齊才談得上比較，只改分箱是不夠的：

1. **分箱定義**（WORK_BOARD 已指出）：舊版用 `np.percentile(r, [0,33,66,100])`
   切**互斥環帶**；觀測的 `fit_real.py --radius-range 0,N` 是**累積** alpha(<r)。
   -> 已改成累積切法，邊界用觀測的角度換算成 pc（見 `CUM_EDGES_DEG`）。

2. **半徑的維度**（WORK_BOARD 未提及，但同樣是真的不一致）：舊版用
   `r = sqrt(x^2+y^2+z^2)`，是**三維**團心距；觀測只量得到天球上的
   **投影**距離（二維）。同一顆星的 3D 半徑永遠 >= 投影半徑，拿兩者並排
   會系統性地把模擬的「外圍」算得比實際觀測到的外圍更遠。
   -> 已改成投影半徑 `sqrt(x^2+y^2)`（沿 z 軸投影），並支援 `--n-projections`
   對多個隨機視線方向平均，降低單一視線的投影雜訊。

3. **質量範圍與估計量**（WORK_BOARD 未提及，**這項最嚴重**）：舊版算
   `mle_powerlaw(mass, 0.1, 2.0)`，是對 0.1-2.0 Msun 直接做截斷冪律 MLE；
   但觀測端 `radial_r*` 來自 `fit_real.py` 的**前向模型**，它的 `alpha`
   自由參數**只控制 Kroupa 分段冪律 m>0.5 Msun 那一段**（見
   `pipeline/joint_fit.py` 的註解：「`alpha` 這個自由參數只改 m>0.5 段」），
   m<0.5 那段是固定的 1.3。0.1-2.0 這個範圍跨過了 0.5 這個分段點，等於
   把「固定的低質量段」跟「要比較的高質量段」混在一起擬合出一個平均斜率
   —— 這跟前向模型的 alpha **根本不是同一個量**，就算分箱與維度都對齊了
   也不能並排比較。
   -> 已把預設質量範圍改成 `0.5 - 2.50`（下界對齊前向模型的 alpha 分段點，
   上界對齊 `config.toml [step5_imf] mass_max`）。

**對齊之後仍然存在、無法用改這支腳本解決的差異（誠實記錄，不要當成已對齊）**：
- 觀測端是**前向模型**（會把未解析聯星、選擇函數、測光誤差一起建模掉）
  擬合出的 alpha；這裡是對模擬粒子的真實質量做**直接 MLE**，沒有這些
  觀測效應。兩者即使數值接近也不代表方法一致，比較時只能當「趨勢方向」
  的對照，不能宣稱是同一個估計量的兩次測量。
- 這裡的 binary 用的是 `binary.mass`（聯星系統的總質量，即 COM 粒子），
  對應觀測端的 **system MF** 而非 stellar MF（見 `LIMITATIONS.md` D14）。
  這一項剛好是對齊的，但要明確知道是哪一種，不是碰巧。
- 觀測的 `radial_r1/r2/r3/rall` 目前仍是 `_prelim`（單次重複、單階精修、
  **沒有誤差棒**）。在 `radial_final_reruns` 跑完之前，任何「模擬跟觀測
  差多少」的比較都無法判斷顯著性。
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NBODY_INSTALL = os.environ.get(
    "NBODY_INSTALL_PATH", str(REPO_ROOT.parent / "nbody" / "install"))
sys.path.insert(0, str(Path(NBODY_INSTALL) / "include"))
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

# 觀測端 radial_r1/r2/r3/rall 的累積半徑邊界（度），與 M45 距離。
# rall 不設角度上限（用全部束縛成員），對應觀測端不帶 --radius-range 的那一項。
CUM_EDGES_DEG = {"r1": 1.0, "r2": 2.0, "r3": 3.0}
DIST_PC = 136.0          # 跟 limepy_multimass.py／dynamics_estimate.py 一致
# 質量範圍：下界對齊前向模型 alpha 的 Kroupa 分段點（m>0.5），
# 上界對齊 config.toml [step5_imf] mass_max。見檔頭第 3 點。
MASS_MIN, MASS_MAX = 0.5, 2.50
R_BOUND_PC = 20.0        # 超過這個距離視為動力學拋射，不算束縛成員


def projected_radii(pos, n_projections=1, seed=20260820):
    """把 3D 位置投影到天球平面，回傳投影半徑。

    觀測只看得到投影距離，所以要跟觀測比就必須投影，不能用 3D 團心距
    （見檔頭第 2 點）。n_projections>1 時對多個隨機視線方向各投影一次，
    回傳 shape (n_projections, n_stars)，讓呼叫端可以平均掉單一視線的
    投影雜訊（小 N 的 pilot 模擬這個雜訊不可忽略）。
    """
    pos = np.asarray(pos, float)
    if n_projections == 1:
        # 預設沿 z 軸投影，結果可重現、不依賴亂數
        return np.sqrt(pos[:, 0] ** 2 + pos[:, 1] ** 2)[None, :]
    rng = np.random.default_rng(seed)
    out = np.empty((n_projections, len(pos)))
    for k in range(n_projections):
        # 在球面上均勻取一個視線方向，投影半徑 = 位置向量垂直於視線的分量
        v = rng.normal(size=3)
        v /= np.linalg.norm(v)
        along = pos @ v
        out[k] = np.sqrt(np.maximum(np.sum(pos ** 2, axis=1) - along ** 2, 0.0))
    return out


def cumulative_alpha(mass, r_proj, edges_pc, mass_min=MASS_MIN,
                     mass_max=MASS_MAX):
    """對每個累積半徑上界算一次 alpha(<r)，對齊觀測的 --radius-range 0,N。

    edges_pc 是 (tag, 上界) 的序列，下界一律為 0——這就是「累積」的意思：
    一層包一層，不是互斥環帶。上界為 None 代表不設上限（對應 rall）。
    """
    from pipeline.step5_imf import mle_powerlaw
    rows = []
    for tag, hi in edges_pc:
        sel = np.ones(len(mass), bool) if hi is None else (r_proj <= hi)
        fit = mle_powerlaw(mass[sel], mass_min, mass_max)
        in_range = mass[sel][(mass[sel] >= mass_min) & (mass[sel] <= mass_max)]
        rows.append({
            "tag": tag,
            "r_hi_pc": np.inf if hi is None else hi,
            "n_total": int(sel.sum()),
            "n_in_massrange": int(len(in_range)),
            "alpha": fit["alpha"],
            "alpha_err": fit["alpha_err"],
            "median_mass": float(np.median(in_range)) if len(in_range) else np.nan,
        })
    return rows


def build_edges():
    """把觀測的角度邊界換算成 pc，末項 None 代表 rall（不設上限）。"""
    edges = [(tag, np.radians(deg) * DIST_PC)
             for tag, deg in CUM_EDGES_DEG.items()]
    edges.append(("rall", None))
    return edges


def self_test():
    """不需要 PeTar 資料，只驗證分箱與累積邏輯本身是否正確。

    造一組已知答案的合成資料：質量抽自 alpha=2.3 的截斷冪律，位置給定
    已知的徑向分層（重的星集中在核心），檢查 (a) 累積切片確實是一層包
    一層、星數單調遞增，(b) 投影半徑恆 <= 3D 半徑，(c) 回收到的 alpha
    接近輸入真值，(d) 分層方向正確。
    """
    from pipeline.step5_imf import mle_powerlaw
    rng = np.random.default_rng(42)
    n = 4000
    alpha_true = 2.3
    # 截斷冪律逆變換抽樣
    u = rng.random(n)
    a = 1 - alpha_true
    mass = (MASS_MIN ** a + u * (MASS_MAX ** a - MASS_MIN ** a)) ** (1 / a)
    # 質量分層：重的星傾向半徑較小，但**刻意做成溫和的統計傾向而非嚴格
    # 排序**。第一版用 argsort 排名直接對應半徑，等於「核心裡只有最重的
    # 那幾百顆」，MLE 會直接撞到 mle_powerlaw 的 alpha 下界 0.1
    # （pipeline/step5_imf.py:149 `bounds=(0.1, 5.0)`），那樣下面的分層
    # 方向斷言會因為貼牆而「假通過」——測不到分箱邏輯本身對不對。
    # 這裡改成用一個帶大量雜訊的質量相依半徑，核心仍偏重但不是純排序。
    seg_strength = 0.35
    u_r = rng.random(n)
    bias = (mass - MASS_MIN) / (MASS_MAX - MASS_MIN)      # 0(輕)~1(重)
    r_frac = np.clip(u_r - seg_strength * bias * rng.random(n), 0.0, 1.0)
    r3d = 0.5 + 12.0 * r_frac ** 0.7
    theta = np.arccos(rng.uniform(-1, 1, n))
    phi = rng.uniform(0, 2 * np.pi, n)
    pos = np.column_stack([r3d * np.sin(theta) * np.cos(phi),
                           r3d * np.sin(theta) * np.sin(phi),
                           r3d * np.cos(theta)])

    r_proj = projected_radii(pos, n_projections=1)[0]
    assert np.all(r_proj <= np.sqrt(np.sum(pos ** 2, axis=1)) + 1e-9), \
        "投影半徑不該大於 3D 半徑"

    edges = build_edges()
    rows = cumulative_alpha(mass, r_proj, edges)
    counts = [r["n_total"] for r in rows]
    assert counts == sorted(counts), f"累積切片星數必須單調遞增，得到 {counts}"
    assert counts[-1] == n, f"rall 應包含全部 {n} 顆，得到 {counts[-1]}"

    fit_all = mle_powerlaw(mass, MASS_MIN, MASS_MAX)
    assert abs(fit_all["alpha"] - alpha_true) < 0.15, \
        f"全樣本 alpha 回收失準：{fit_all['alpha']:.3f} vs 真值 {alpha_true}"
    # 貼牆檢查：mle_powerlaw 的搜尋界是 (0.1, 5.0)，任何一片的 alpha 撞到
    # 界上就代表這一片的資料撐不出有意義的擬合（本專案一貫的貼牆判準），
    # 這時下面的方向斷言會因為貼牆而假通過，必須先攔下來。
    for row in rows:
        assert 0.1 + 1e-6 < row["alpha"] < 5.0 - 1e-6, \
            (f"{row['tag']} 的 alpha={row['alpha']:.3f} 貼到 mle_powerlaw 的"
             f"搜尋界，這一片撐不出有意義的擬合，方向斷言會假通過")

    assert rows[0]["alpha"] < rows[-1]["alpha"], \
        "輸入的是「重星集中核心」的分層，核心 alpha 應該比全樣本平緩"

    multi = projected_radii(pos, n_projections=8)
    assert multi.shape == (8, n)
    assert np.all(multi >= 0)

    print("self-test 通過：")
    print(f"  全樣本 alpha 回收 {fit_all['alpha']:.3f}（真值 {alpha_true}）")
    print(f"  累積星數 {counts}（單調遞增）")
    print(f"  核心 alpha {rows[0]['alpha']:.3f} < 全樣本 {rows[-1]['alpha']:.3f}"
          f"（分層方向正確）")
    print("  投影半徑恆 <= 3D 半徑")
    print("\n**注意**：self-test 只驗證分箱／投影／累積邏輯，不驗證跟真實 "
          "PeTar 快照接得起來，也不代表跟觀測的比較在方法論上成立"
          "（見檔頭「對齊之後仍然存在的差異」）。")


def main():
    args = list(sys.argv[1:])
    if "--self-test" in args:
        self_test()
        return

    n_proj = 1
    if "--n-projections" in args:
        i = args.index("--n-projections")
        n_proj = int(args[i + 1])
        del args[i:i + 2]
    prefix = args[0] if args else "data.25"

    from petar import Particle, Binary

    single = Particle(interrupt_mode="bse")
    single.loadtxt(prefix + ".single")
    binary = Binary(member_particle_type=Particle, interrupt_mode="bse")
    binary.loadtxt(prefix + ".binary")

    mass = np.concatenate([single.mass, binary.mass])
    pos = np.concatenate([single.pos, binary.pos], axis=0)

    # pos is already in the density-center frame (petar.data.process calls
    # correctCenter() internally before saving .single/.binary) -- do not
    # subtract data.core's center again, that would double-subtract it.
    r3d = np.sqrt(np.sum(pos ** 2, axis=1))

    print(f"N bodies (singles + binary COMs): {len(mass)}")
    print(f"Total mass: {mass.sum():.2f} Msun")
    print(f"Mass range: {mass.min():.3f} - {mass.max():.3f} Msun")
    print(f"3D radius percentiles (pc): "
          f"10%={np.percentile(r3d, 10):.2f} 50%={np.percentile(r3d, 50):.2f} "
          f"90%={np.percentile(r3d, 90):.2f} max={r3d.max():.1f}")
    n_far = int(np.sum(r3d > R_BOUND_PC))
    print(f"Bodies beyond {R_BOUND_PC:.0f} pc (likely dynamically ejected, not "
          f"bound cluster members): {n_far}")

    # bound members only: exclude far-flung ejecta (same spirit as the
    # pipeline's own r-escape criterion) so radius bins reflect the actual
    # cluster body, not stars in free flight after an ejection.
    # 束縛判定用 3D 半徑（那是物理上的束縛與否），分箱才用投影半徑
    # （那是為了跟觀測對齊）——兩者用途不同，不要混用。
    bound = r3d < R_BOUND_PC
    mass_b, pos_b = mass[bound], pos[bound]
    print(f"Bound bodies used for alpha(<r): {len(mass_b)}")

    edges = build_edges()
    proj = projected_radii(pos_b, n_projections=n_proj)
    print(f"\n累積投影半徑切片（對齊觀測 --radius-range 0,N，距離 {DIST_PC} pc）")
    print(f"質量範圍 {MASS_MIN}-{MASS_MAX} Msun（對齊前向模型 alpha 的 m>0.5 段）")
    if n_proj > 1:
        print(f"對 {n_proj} 個隨機視線方向各算一次後取平均與散布")

    per_proj = [cumulative_alpha(mass_b, proj[k], edges) for k in range(n_proj)]

    print("\nalpha(<r):")
    print("tag    r_hi(pc)   n_in_range   alpha" +
          ("  proj_std" if n_proj > 1 else "  alpha_err") + "  median_mass")
    for j in range(len(edges)):
        alphas = np.array([p[j]["alpha"] for p in per_proj])
        ref = per_proj[0][j]
        spread = alphas.std(ddof=1) if n_proj > 1 else ref["alpha_err"]
        hi = ref["r_hi_pc"]
        hi_s = "  full" if not np.isfinite(hi) else f"{hi:6.2f}"
        print(f"{ref['tag']:5s} {hi_s}     {ref['n_in_massrange']:6d}  "
              f"{alphas.mean():.3f}     {spread:.3f}      {ref['median_mass']:.3f}")

    print("\n**比較時必讀**：這裡的 alpha 是對模擬粒子真實質量做直接 MLE，"
          "觀測的 radial_r* 是前向模型擬合值，兩者不是同一個估計量；"
          "且觀測值目前仍是 _prelim（無誤差棒）。詳見本檔開頭說明。")


if __name__ == "__main__":
    main()
