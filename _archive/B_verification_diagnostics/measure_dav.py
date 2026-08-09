# -*- coding: utf-8 -*-
"""從 Gaia 自己的消光估計，外部量出 M45 的差異消光。

**為什麼要這樣做**

注入回收證實 dav（差異消光的星對星散布）**不被 CMD 資料約束** ——
給多少範圍它就吃多少（上界 0.6 跑到 0.600、放寬到 1.2 跑到 1.200，
加大 n_synthetic 無效）。在假資料上 alpha 不受它影響，但真實資料上會：
dav 上界從 0.6 放到 1.2，alpha 從 2.300 跳到 2.700。

所以「把它當 nuisance 放自由、對 alpha 無害」這條路走不通。

剩下的正當作法只有一條，而且是本專案已經寫進方法論的那條：
**用外部獨立資料打破簡併，而不是用假設迴避它。** 距離就是這樣處理的
（由 Gaia 視差固定，不當自由參數），金屬量的高斯先驗也是這樣來的
（取自 GSP-Spec 與 GSP-Phot）。

Gaia 的 GSP-Phot 對每顆星各自給了 A_0（547.7 nm 的單色消光，約等於 A_V），
機制與我們的 CMD 擬合完全獨立。成員星之間 A_0 的散布就是差異消光，
只要先扣掉每顆星自身的量測誤差。

**這個量法的已知偏差**：GSP-Phot 的單星 A_0 與有效溫度高度簡併，
所以量到的散布是**上限**，不是無偏估計。因此輸出三個數字
（原始散布、扣掉量測誤差後、以及穩健版），把差距當成這一項的不確定度。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load():
    cols = ("azero_gspphot", "ag_gspphot", "ag_gspphot_lower",
            "ag_gspphot_upper", "teff_gspphot")
    acc = {c: [] for c in cols}
    with open(HERE / "data" / "astrophys.csv", newline="",
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for c in cols:
                v = r[c]
                acc[c].append(float(v) if v not in ("", "nan", "null")
                              else np.nan)
    return {c: np.array(v, float) for c, v in acc.items()}


def main():
    d = load()
    a0 = d["azero_gspphot"]
    # 量測誤差用 ag 的 16/84 區間半寬換算（A_G ≈ 0.83 * A_0）
    err = (d["ag_gspphot_upper"] - d["ag_gspphot_lower"]) / 2.0 / 0.83
    ok = np.isfinite(a0) & np.isfinite(err) & (a0 >= 0)
    a0, err, teff = a0[ok], err[ok], d["teff_gspphot"][ok]
    print(f"有 GSP-Phot 消光估計的成員 {ok.sum():,} 顆 / 1,078 顆\n")

    print(f"{'量':<28}{'值':>10}")
    print(f"{'平均 A_0':<28}{a0.mean():>10.3f}")
    print(f"{'中位 A_0':<28}{np.median(a0):>10.3f}")
    raw = a0.std()
    print(f"{'原始散布 sd(A_0)':<28}{raw:>10.3f}")
    med_err = np.median(err)
    print(f"{'單星量測誤差中位':<28}{med_err:>10.3f}")
    # 扣掉量測誤差：sd_intrinsic^2 = sd_observed^2 - <err^2>
    var = raw**2 - np.mean(err**2)
    intr = np.sqrt(var) if var > 0 else 0.0
    print(f"{'扣掉量測誤差後':<28}{intr:>10.3f}")
    # 穩健版：用四分位距換算（對 GSP-Phot 的離群值不敏感）
    q = np.percentile(a0, [25, 75])
    rob = (q[1] - q[0]) / 1.349
    var_r = rob**2 - np.median(err)**2
    intr_r = np.sqrt(var_r) if var_r > 0 else 0.0
    print(f"{'穩健版（IQR/1.349）':<28}{rob:>10.3f}")
    print(f"{'穩健版扣掉量測誤差':<28}{intr_r:>10.3f}")

    # GSP-Phot 的 A_0 與 Teff 簡併，若散布主要來自這個簡併，
    # A_0 就會隨 Teff 系統性變化 —— 那部分不是真的差異消光。
    good = np.isfinite(teff)
    if good.sum() > 100:
        c = np.corrcoef(a0[good], teff[good])[0, 1]
        print(f"\nA_0 與 Teff 的相關係數 {c:+.3f}"
              f"（|r| 大代表散布有一部分是 GSP-Phot 自己的簡併，不是真消光）")
        # 扣掉隨 Teff 的線性趨勢後剩多少散布
        p = np.polyfit(teff[good], a0[good], 1)
        resid = a0[good] - np.polyval(p, teff[good])
        var_d = resid.std()**2 - np.mean(err[good]**2)
        print(f"扣掉 Teff 趨勢後的散布 "
              f"{np.sqrt(var_d) if var_d > 0 else 0.0:>.3f}")

    print(f"\n對照：HR23 給 M45 的差異消光 0.634、平均消光 A_V 0.102")
    print(f"      我們的 CMD 擬合把 A_V 頂到網格上界 0.400（貼牆）")
    print("\n判讀：把上面幾個估計的跨度當成 dav 的不確定度，"
          "用高斯先驗鎖住它，\n      而不是讓它在 CMD 概似裡自由奔跑。")


if __name__ == "__main__":
    main()
