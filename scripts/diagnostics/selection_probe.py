# -*- coding: utf-8 -*-
"""找出測光品質篩選真正的自變數，決定選擇函數要用幾維。

**問題**：completeness.py 量到存活率同時隨星等與顏色變 —— G 17–18 的紅半邊
存活率 0.410、藍半邊 0.799，差 0.388，比整條星等趨勢（0.152）還大 2.6 倍。
所以「只看 G 星等」的一維完整度曲線不夠。

但直接改成 (G, 顏色) 的二維地圖不是最好的作法：格子一多每格星數就不夠，
量出來的地圖會被雜訊主導，而且它只是在描述現象、沒有描述機制。

**這支程式檢查的假設**：那些切本來就不是定義在 G 上的。
`min_flux_snr_bp = 20` 切的是 BP 的訊噪比，而 BP 訊噪比主要由 **BP 星等**決定。
同一個 G 之下紅星的 BP 比較暗，所以紅星先被砍 —— 顏色相依只是這件事的投影。

若把存活率改畫成 BP 星等的函數，顏色相依應該會塌掉。
塌掉 -> 用「各波段星等的一維曲線」即可，物理清楚、雜訊低。
沒塌掉 -> 才需要二維地圖。
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent.parent
G_BRIGHT = 4.0


def load():
    """把原始星表、成員機率、篩選後名單三者接起來。"""
    prob = {}
    with open(HERE / "data" / "comparison.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prob[r["source_id"]] = float(r["my_prob"])
    post = set()
    with open(HERE / "data" / "cmd_members.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            post.add(r["source_id"])

    rows = {k: [] for k in ("g", "bp", "rp", "snr_g", "snr_bp", "snr_rp",
                            "excess", "kept")}
    with open(HERE / "data" / "m45_r5_g18_plx4.csv", newline="",
              encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sid = r["source_id"]
            if prob.get(sid, 0.0) < 0.7:
                continue

            def num(key):
                v = r[key]
                return float(v) if v not in ("", "null", "NaN") else np.nan

            if num("phot_g_mean_mag") < G_BRIGHT:
                continue
            rows["g"].append(num("phot_g_mean_mag"))
            rows["bp"].append(num("phot_bp_mean_mag"))
            rows["rp"].append(num("phot_rp_mean_mag"))
            rows["snr_g"].append(num("phot_g_mean_flux_over_error"))
            rows["snr_bp"].append(num("phot_bp_mean_flux_over_error"))
            rows["snr_rp"].append(num("phot_rp_mean_flux_over_error"))
            rows["excess"].append(num("phot_bp_rp_excess_factor"))
            rows["kept"].append(sid in post)
    out = {k: np.array(v, float) for k, v in rows.items() if k != "kept"}
    out["kept"] = np.array(rows["kept"], bool)
    return out


def which_cut(d):
    """逐一算出每把刀各自砍掉多少，確認我們知道 219 顆是怎麼消失的。"""
    print("各項篩選各自砍掉幾顆（單獨施加，會互相重疊）：")
    tests = [
        ("G 訊噪比 < 50", d["snr_g"] < 50),
        ("BP 訊噪比 < 20", d["snr_bp"] < 20),
        ("RP 訊噪比 < 20", d["snr_rp"] < 20),
        ("BP/RP 或顏色缺值", ~np.isfinite(d["bp"]) | ~np.isfinite(d["rp"])),
    ]
    for name, m in tests:
        print(f"  {name:<20}{np.nansum(m):>6} 顆")
    any_snr = tests[0][1] | tests[1][1] | tests[2][1] | tests[3][1]
    print(f"  {'以上聯集':<20}{any_snr.sum():>6} 顆")
    print(f"  實際被砍          {(~d['kept']).sum():>6} 顆"
          f"（差額由 BP/RP 流量超額那一刀補上）\n")


def survival_vs(d, x, name, edges):
    """存活率對某個變數的曲線，並檢查同一格內是否還殘留顏色相依。"""
    colour = d["bp"] - d["rp"]
    ok = np.isfinite(x)
    print(f"--- 存活率 vs {name} ---")
    print(f"{'區間':>14}{'星數':>7}{'存活率':>9}"
          f"{'紅半邊':>9}{'藍半邊':>9}{'殘留顏色差':>11}")
    worst = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = ok & (x >= lo) & (x < hi)
        if m.sum() < 20:
            continue
        f_all = d["kept"][m].mean()
        cm = m & np.isfinite(colour)
        if cm.sum() >= 20:
            med = np.median(colour[cm])
            red, blue = cm & (colour > med), cm & (colour <= med)
            fr, fb = d["kept"][red].mean(), d["kept"][blue].mean()
            diff = fr - fb
            worst = max(worst, abs(diff))
        else:
            fr = fb = diff = np.nan
        print(f"{lo:6.1f}–{hi:<7.1f}{m.sum():>7}{f_all:>9.3f}"
              f"{fr:>9.3f}{fb:>9.3f}{diff:>+11.3f}")
    print(f"  最大殘留顏色相依 = {worst:.3f}\n")
    return worst


def decompose(d):
    """把被砍掉的星按成因拆開，各自檢查顏色相依。

    存活率的顏色相依在 G、BP、RP 三種自變數下都沒有塌掉（0.35–0.39），
    表示它不是「某一把刀切錯變數」造成的投影。那就得問：
    到底是哪一把刀在砍紅星？
    """
    colour = d["bp"] - d["rp"]
    snr = (d["snr_bp"] < 20) | (d["snr_rp"] < 20) | (d["snr_g"] < 50)
    missing = ~np.isfinite(d["bp"]) | ~np.isfinite(d["rp"])
    removed = ~d["kept"]
    # 沒被訊噪比也沒被缺值解釋的，就是 BP/RP 流量超額那一刀砍的
    excess = removed & ~snr & ~missing

    print("被砍掉的 星 按成因拆解：")
    for name, m in (("訊噪比不足", removed & snr),
                    ("測光缺值", removed & missing & ~snr),
                    ("BP/RP 流量超額", excess)):
        n = m.sum()
        if n == 0:
            continue
        c = colour[m & np.isfinite(colour)]
        g = d["g"][m]
        print(f"  {name:<16}{n:>5} 顆   "
              f"顏色中位 {np.median(c) if len(c) else np.nan:>5.2f}   "
              f"G 中位 {np.median(g):>5.2f}   "
              f"G>17 佔 {np.mean(g > 17):>5.1%}")
    alive = d["kept"] & np.isfinite(colour)
    print(f"  {'（存活者對照）':<16}{alive.sum():>5} 顆   "
          f"顏色中位 {np.median(colour[alive]):>5.2f}   "
          f"G 中位 {np.median(d['g'][alive]):>5.2f}   "
          f"G>17 佔 {np.mean(d['g'][alive] > 17):>5.1%}")

    # 只看最暗那一批（顏色相依最強的地方），逐一成因看紅藍差
    faint = np.isfinite(colour) & (d["g"] >= 17.0)
    med = np.median(colour[faint])
    red, blue = faint & (colour > med), faint & (colour <= med)
    print(f"\nG>=17 的 {faint.sum()} 顆，以顏色中位 {med:.2f} 分紅藍兩半：")
    print(f"{'成因':<18}{'紅半邊被砍':>12}{'藍半邊被砍':>12}{'差':>9}")
    for name, m in (("訊噪比不足", snr), ("測光缺值", missing),
                    ("BP/RP 流量超額", excess)):
        fr, fb = (m & red).sum() / red.sum(), (m & blue).sum() / blue.sum()
        print(f"{name:<18}{fr:>12.3f}{fb:>12.3f}{fr-fb:>+9.3f}")
    print()


def main():
    d = load()
    print(f"P>=0.7 且 G>={G_BRIGHT} 的成員 {len(d['g']):,} 顆，"
          f"通過篩選 {d['kept'].sum():,} 顆（{d['kept'].mean():.1%}）\n")
    which_cut(d)
    decompose(d)

    w_g = survival_vs(d, d["g"], "G 星等", np.arange(5, 18.1, 1.0))
    w_bp = survival_vs(d, d["bp"], "BP 星等", np.arange(5, 21.1, 1.0))
    w_rp = survival_vs(d, d["rp"], "RP 星等", np.arange(5, 18.1, 1.0))

    # 顏色相依幾乎全部來自 BP 訊噪比那一刀，但用 BP 星等當自變數也沒塌掉。
    # 那就直接問：BP 訊噪比本身，是不是 BP 星等的函數？
    print("--- BP 訊噪比 vs BP 星等（同一星等內紅藍是否不同）---")
    colour = d["bp"] - d["rp"]
    ok = np.isfinite(d["bp"]) & np.isfinite(d["snr_bp"]) & np.isfinite(colour)
    print(f"{'BP 區間':>14}{'星數':>7}{'SNR 中位':>10}"
          f"{'紅半邊':>10}{'藍半邊':>10}{'比值':>8}")
    for lo in np.arange(16, 21, 1.0):
        m = ok & (d["bp"] >= lo) & (d["bp"] < lo + 1)
        if m.sum() < 20:
            continue
        med = np.median(colour[m])
        red, blue = m & (colour > med), m & (colour <= med)
        sr, sb = np.median(d["snr_bp"][red]), np.median(d["snr_bp"][blue])
        print(f"{lo:6.1f}–{lo+1:<7.1f}{m.sum():>7}"
              f"{np.median(d['snr_bp'][m]):>10.1f}{sr:>10.1f}{sb:>10.1f}"
              f"{sr/sb:>8.2f}")
    print()

    print("=" * 70)
    print(f"最大殘留顏色相依：G {w_g:.3f}   BP {w_bp:.3f}   RP {w_rp:.3f}")
    print("判讀：若用 BP 星等當自變數後殘留顏色相依明顯小於用 G，")
    print("      代表那把刀本來就切在 BP 上，選擇函數用 BP 的一維曲線即可，")
    print("      不需要（也不該）改用雜訊大的二維地圖。")


if __name__ == "__main__":
    main()
