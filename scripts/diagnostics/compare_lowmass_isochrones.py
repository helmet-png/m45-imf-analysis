# -*- coding: utf-8 -*-
"""D19／D1：PARSEC 與 BHAC15 在低質量段差多少、能不能在低質量段單獨換模型。

**這支程式不做擬合**，只在同一個年齡（logAge = 8.00，兩套網格都有這個
格點，不必做年齡內插）、同一個金屬量（MH = 0，BHAC15 只有這一組）比較
兩套等時線，回答三個問題：

1. 在固定視星等下，兩套模型指派的質量差多少？（這才是質量函數看得到的量）
2. 哪個顏色對模型選擇比較不敏感？（BP−RP 還是 G−RP）
3. 如果要在低質量段單獨換成 BHAC15（拼接），有沒有一段質量區間兩者夠
   接近、可以當接縫？

同時跟 PARSEC 的 EDR3 與 DR2 濾光片版本各比一次：BHAC15 原始檔沒有註明
用哪一版 Gaia 濾光片，兩版結果接近就代表差異來自恆星模型本身、不是
濾光片定義。

**BHAC15 原始檔的取得**：`scripts/data_prep/build_bhac_grid.py` 的下載
需要 `certs/ens_lyon_chain.pem`（該伺服器不送中繼憑證，見 `pipeline/net.py`）。
沒有那份憑證鏈的機器可以改用 Windows 內建 curl（schannel 會自己補中繼
憑證，驗證維持開啟）先把原始檔放到 `isochrones/BHAC15_iso.GAIA`，
再跑 build_bhac_grid.py，它看到檔案已存在就不會重新下載：
    curl.exe --ssl-no-revoke -f -o isochrones/BHAC15_iso.GAIA \
        https://perso.ens-lyon.fr/isabelle.baraffe/BHAC15dir/BHAC15_iso.GAIA

用法：
    python scripts/diagnostics/compare_lowmass_isochrones.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(HERE))

from pipeline import isochrones as isomod      # noqa: E402

LOGAGE = 8.00
BHAC_GRID = "bhac15_gaia_logt7.6-8.4.dat"
PARSEC_GRIDS = {
    "EDR3": ("parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat",
             "G_BP_fSBmag"),
    # DR2 版 BP 分亮／暗兩條通帶，低質量星都很暗，用 faint 版
    "DR2": ("parsec_v2.0_gaiaDR2_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat",
            "G_BPft_fSBmag"),
}
MASSES = [0.10, 0.11, 0.13, 0.15, 0.17, 0.20, 0.30, 0.40, 0.50,
          0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.40]
SEAM_TOL = 0.10      # 星等；Hess 圖一格 0.32 星等，接縫落差要明顯小於一格


def sorted_cols(t, bp_col):
    m = np.asarray(t["Mini"], float)
    o = np.argsort(m)
    return (m[o], np.asarray(t["G_fSBmag"], float)[o],
            np.asarray(t[bp_col], float)[o],
            np.asarray(t["G_RP_fSBmag"], float)[o])


def compare(parsec_file, bp_col, bhac):
    mB, gB, bpB, rpB = bhac
    P = isomod.isochrone_at(isomod.load_grid(isomod.CACHE / parsec_file),
                            LOGAGE, 0.0)
    mP, gP, bpP, rpP = sorted_cols(P, bp_col)
    k = mP <= 1.5            # 只取主序段，G 對質量單調
    mP, gP, bpP, rpP = mP[k], gP[k], bpP[k], rpP[k]
    rows = []
    for M in MASSES:
        i = int(np.argmin(np.abs(mB - M)))
        if abs(mB[i] - M) > 1e-3 or M < mP.min():
            continue
        g = np.interp(M, mP, gP)
        bp = np.interp(M, mP, bpP)
        rp = np.interp(M, mP, rpP)
        # 固定 BHAC15 的絕對星等，問 PARSEC 會指派多少質量
        m_parsec_at_g = np.interp(gB[i], gP[::-1], mP[::-1])
        rows.append((M, gB[i] - g, (bpB[i] - rpB[i]) - (bp - rp),
                     (gB[i] - rpB[i]) - (g - rp), (m_parsec_at_g - M) / M))
    return np.array(rows)


def slope_shift(rows, p=1.3, lo=0.10, hi=0.50):
    """質量換算差異單獨造成的低質量段冪次位移（解析粗估，不是擬合）。

    若兩模型在固定星等下的質量比 M_P/M_B 近似 M_B^k（在 lo–hi 間取對數
    線性），則 dN/dM_B 正比 M_B^(-p) 會變成 dN/dM_P 正比 M_P^(-p')，
    p' = (p - 1)/(1 + k) + 1。只含質量換算這一項，不含顏色差異在前向模型
    裡的效應，所以只能當量級參考。
    """
    m, r = rows[:, 0], rows[:, 4]
    a = int(np.argmin(np.abs(m - lo)))
    b = int(np.argmin(np.abs(m - hi)))
    k = (np.log1p(r[b]) - np.log1p(r[a])) / (np.log(m[b]) - np.log(m[a]))
    return (p - 1.0) / (1.0 + k) + 1.0


def main():
    B = isomod.isochrone_at(isomod.load_grid(isomod.CACHE / BHAC_GRID),
                            LOGAGE, 0.0)
    bhac = sorted_cols(B, "G_BP_fSBmag")
    out = {}
    for tag, (fn, bp_col) in PARSEC_GRIDS.items():
        rows = compare(fn, bp_col, bhac)
        out[tag] = rows
        print(f"\n=== BHAC15 − PARSEC {tag}，logAge={LOGAGE}，MH=0 ===")
        print(f"{'M':>6}{'dG':>8}{'d(BP-RP)':>10}{'d(G-RP)':>9}"
              f"{'dM/M(固定G)':>13}")
        for M, dg, dbr, dgr, dm in rows:
            print(f"{M:6.2f}{dg:+8.3f}{dbr:+10.3f}{dgr:+9.3f}{dm:+13.1%}")

    rows = out["EDR3"]
    m = rows[:, 0]
    print("\n=== 判讀（以 EDR3 為準） ===")
    hi_mass = np.abs(rows[m >= 0.5, 4]).max()
    print(f"  M >= 0.5 M☉ 質量差最大 {hi_mass:.1%}"
          f"（高質量段 alpha 對模型選擇不敏感）")
    for M in (0.1, 0.2, 0.3):
        i = int(np.argmin(np.abs(m - M)))
        print(f"  M = {M:.1f} M☉ 質量差 {rows[i, 4]:+.1%}")
    low = m < 0.5
    print(f"  M < 0.5 M☉ 顏色差最大：BP-RP {np.abs(rows[low, 2]).max():.3f}"
          f" 星等，G-RP {np.abs(rows[low, 3]).max():.3f} 星等")
    seam = (np.abs(rows[:, 1]) <= SEAM_TOL + 0.05) & \
        (np.abs(rows[:, 3]) <= 0.03) & (m >= 0.5)
    print(f"  接縫候選（|dG| <= {SEAM_TOL + 0.05:.2f}、|d(G-RP)| <= 0.03）："
          f"{', '.join(f'{x:.1f}' for x in m[seam]) or '無'} M☉")
    both = (np.abs(rows[:, 1]) <= SEAM_TOL) & (np.abs(rows[:, 2]) <= SEAM_TOL)
    print(f"  G 與 BP-RP 同時一致到 {SEAM_TOL:.2f} 星等以內的質量："
          f"{', '.join(f'{x:.1f}' for x in m[both]) or '無'} M☉")
    p_new = slope_shift(rows)
    print(f"  質量換算單獨造成的低質量段冪次位移（粗估）：1.30 -> {p_new:.2f}"
          f"（位移 {p_new - 1.3:+.2f}；對照 Kroupa 外部不確定度 ±0.5）")

    np.savez(HERE / "results" / "d19_isochrone_compare.npz",
             logage=LOGAGE, cols=np.array(["M", "dG", "dBPRP", "dGRP",
                                           "dM_over_M"]),
             edr3=out["EDR3"], dr2=out["DR2"], slope_shift=p_new)
    print("\n寫入 results/d19_isochrone_compare.npz")


if __name__ == "__main__":
    main()
