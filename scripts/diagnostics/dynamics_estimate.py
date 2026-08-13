# -*- coding: utf-8 -*-
"""M45 的動力學時標估計：半質量弛豫時間、動力學年齡、Jacobi（潮汐）半徑。

**這不是擬合**——這裡沒有用到任何觀測到的質量函數資料，只用星團的
總質量、成員數、半質量半徑（都是文獻值/估計值）代公式，回答「M45 大約
演化了幾個弛豫時間、潮汐半徑大約是多少」。目的是替 `PDMF_TO_IMF_PLAN.md`
的路線規劃提供量級依據，不是產生要拿去跟其他結果比較的「答案」。

參考《教學_PDMF轉IMF.md》第三、四節有完整推導，這支程式是那兩節公式的
直接對照。

輸入的星團參數（M_cl、N、r_h）目前是文獻估計值的合理範圍（Adams et al.
2001, AJ 121, 2053；Converse & Stahler 2010, MNRAS 405, 666），不是我們
自己從 Gaia 資料量出來的——這是本腳本最大的誤差來源，見下面的敏感度掃描。
"""
from __future__ import annotations

import argparse
import numpy as np

G_PC_KMS2 = 4.30091e-3   # 重力常數，單位 pc*(km/s)^2/Msun
PC_KMS_TO_MYR = 0.9778   # 1 pc/(km/s) 換成 Myr 的係數
V_LSR_KMS = 230.0        # 太陽鄰域的銀河系公轉速度
R0_PC = 8178.0           # 太陽到銀河中心距離


def half_mass_relaxation_time(M_cl: float, N: float, r_h: float) -> float:
    """半質量弛豫時間 t_rh，單位 Myr。

    公式（Spitzer 1987 標準式，見教學文件 3.3 節推導）：
        t_rh = 0.138 * sqrt(N * r_h^3 / (G * <m>)) / ln(0.4 N)
    """
    mbar = M_cl / N
    lnL = np.log(0.4 * N)
    t_rh_pc_kms = 0.138 * np.sqrt(N * r_h**3 / (G_PC_KMS2 * mbar)) / lnL
    return t_rh_pc_kms * PC_KMS_TO_MYR


def jacobi_radius(M_cl: float, v_lsr: float = V_LSR_KMS,
                   r0: float = R0_PC) -> float:
    """Jacobi（潮汐）半徑，單位 pc（假設銀河系平坦轉動曲線，見教學文件 4.2 節）。

        r_J = (G*M_cl / (2*Omega^2))^(1/3)，Omega = v_lsr / r0
    """
    omega = v_lsr / r0
    return (G_PC_KMS2 * M_cl / (2 * omega**2)) ** (1 / 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mass", type=float, default=800.0,
                     help="星團總質量估計值 (Msun)，文獻範圍 600-1000")
    ap.add_argument("--n", type=float, default=1200.0,
                     help="成員系統數估計值（含雙星系統）")
    ap.add_argument("--rh", type=float, default=4.0,
                     help="半質量半徑估計值 (pc)，文獻範圍 3-5")
    ap.add_argument("--age", type=float, default=125.0,
                     help="星團年齡 (Myr)，來自 config C 的最佳擬合")
    ap.add_argument("--distance", type=float, default=136.0,
                     help="星團距離 (pc)，用來把 pc 換算成度")
    ap.add_argument("--sample-radius-deg", type=float, default=5.0,
                     help="目前 Gaia 樣本的搜尋半徑 (度)")
    ap.add_argument("--sweep", action="store_true",
                     help="額外印出對 mass/rh 假設的敏感度掃描")
    args = ap.parse_args()

    t_rh = half_mass_relaxation_time(args.mass, args.n, args.rh)
    tau = args.age / t_rh
    r_J = jacobi_radius(args.mass)
    r_J_deg = np.degrees(r_J / args.distance)
    sample_pc = np.radians(args.sample_radius_deg) * args.distance

    print(f"輸入：M_cl={args.mass:.0f} Msun, N={args.n:.0f}, "
          f"r_h={args.rh:.1f} pc, age={args.age:.0f} Myr\n")
    print(f"半質量弛豫時間 t_rh     = {t_rh:6.1f} Myr")
    print(f"動力學年齡 tau=age/t_rh = {tau:6.2f}"
          f"  {'（已走過至少一個弛豫時間，分層預期已發生）' if tau >= 1 else '（還不到一個弛豫時間）'}")
    print(f"Jacobi（潮汐）半徑      = {r_J:6.2f} pc = {r_J_deg:.2f} 度"
          f"（距離 {args.distance:.0f} pc）")
    print(f"目前樣本半徑            = {args.sample_radius_deg:.2f} 度 "
          f"= {sample_pc:.2f} pc = {sample_pc/r_J:.2f} x Jacobi 半徑")

    if args.sweep:
        print("\n對 M_cl / r_h 假設的敏感度掃描（t_rh 隨假設變化多少）：")
        print(f"{'M_cl':>6}{'r_h':>6}{'t_rh(Myr)':>12}{'tau':>8}")
        for M in (600.0, 800.0, 1000.0):
            for rh in (3.0, 4.0, 5.0):
                t = half_mass_relaxation_time(M, args.n, rh)
                print(f"{M:6.0f}{rh:6.1f}{t:12.0f}{args.age/t:8.2f}")


if __name__ == "__main__":
    main()
