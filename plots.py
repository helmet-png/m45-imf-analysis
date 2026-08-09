# -*- coding: utf-8 -*-
"""畫 validate.py 產出的逐星比對表。

用 Agg 後端，不開視窗（這台機器上跳出來的視窗會干擾使用者）。
圖上標籤一律英文，matplotlib 預設字型沒有中文字。
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.table import Table  # noqa: E402

HERE = Path(__file__).parent
DOT = dict(s=3, lw=0, rasterized=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/comparison.csv")
    ap.add_argument("--thr", type=float, default=0.5, help="我的成員判定門檻")
    ap.add_argument("--out", default="figs/m45_validation.png")
    a = ap.parse_args()

    t = Table.read(HERE / a.csv, format="csv")
    p = np.asarray(t["my_prob"], float)
    truth = np.asarray(t["hr23_member"], int).astype(bool)
    mine = p >= a.thr
    pmra, pmde = np.asarray(t["pmRA"], float), np.asarray(t["pmDE"], float)
    plx = np.asarray(t["Plx"], float)
    x, y = np.asarray(t["_x"], float), np.asarray(t["_y"], float)
    g, bprp = np.asarray(t["Gmag"], float), np.asarray(t["BP_RP"], float)

    fig, ax = plt.subplots(2, 3, figsize=(16, 9.5))

    # 1) 自行運動平面，用我的機率上色
    s = ax[0, 0].scatter(pmra, pmde, c=np.clip(p, 0, 1), cmap="viridis", **DOT)
    ax[0, 0].set(xlim=(-20, 50), ylim=(-80, 20), xlabel="pmRA* (mas/yr)",
                 ylabel="pmDE (mas/yr)", title="Proper motion, coloured by pyUPMASK P")
    fig.colorbar(s, ax=ax[0, 0], label="P")

    # 2) 我與 HR23 的一致與不一致
    cat = [("Both (TP)", mine & truth, "#1a7f37"),
           ("Mine only (FP)", mine & ~truth, "#cf222e"),
           ("HR23 only (FN)", ~mine & truth, "#bf8700"),
           ("Neither", ~mine & ~truth, "#d0d7de")]
    for lab, m, c in reversed(cat):
        ax[0, 1].scatter(pmra[m], pmde[m], c=c, label=f"{lab}  n={m.sum()}", **DOT)
    ax[0, 1].set(xlim=(0, 40), ylim=(-65, -25), xlabel="pmRA* (mas/yr)",
                 ylabel="pmDE (mas/yr)", title=f"Agreement with HR23 (P>={a.thr})")
    ax[0, 1].legend(markerscale=4, fontsize=8, loc="upper left")

    # 3) 視差 vs 自行運動大小
    pmtot = np.hypot(pmra, pmde)
    ax[0, 2].scatter(pmtot[~mine], plx[~mine], c="#d0d7de", **DOT)
    ax[0, 2].scatter(pmtot[mine], plx[mine], c="#1f6feb", **DOT)
    ax[0, 2].set(xlim=(0, 80), ylim=(3.5, 12), xlabel="total proper motion (mas/yr)",
                 ylabel="parallax (mas)", title="Parallax vs proper motion")

    # 4) 天球分布（切平面投影）
    ax[1, 0].scatter(x[~mine], y[~mine], c="#d0d7de", **DOT)
    ax[1, 0].scatter(x[mine], y[mine], c="#1f6feb", **DOT)
    ax[1, 0].set(xlabel="xi (deg)", ylabel="eta (deg)", title="Sky (tangent plane)",
                 aspect="equal")

    # 5) 色光圖
    ax[1, 1].scatter(bprp[~mine], g[~mine], c="#d0d7de", **DOT)
    ax[1, 1].scatter(bprp[mine], g[mine], c="#1f6feb", **DOT)
    ax[1, 1].set(xlabel="BP-RP", ylabel="G (mag)",
                 title="CMD (members should trace one sequence)")
    ax[1, 1].invert_yaxis()

    # 6) 門檻掃描
    thrs = np.linspace(0.02, 0.99, 60)
    prec, rec, f1 = [], [], []
    for th in thrs:
        pr = p >= th
        tp, fp, fn = (pr & truth).sum(), (pr & ~truth).sum(), (~pr & truth).sum()
        pp = tp / (tp + fp) if tp + fp else np.nan
        rr = tp / (tp + fn) if tp + fn else np.nan
        prec.append(pp)
        rec.append(rr)
        f1.append(2 * pp * rr / (pp + rr) if pp and rr else np.nan)
    ax[1, 2].plot(thrs, prec, label="precision")
    ax[1, 2].plot(thrs, rec, label="recall")
    ax[1, 2].plot(thrs, f1, label="F1", lw=2)
    ax[1, 2].axvline(a.thr, color="#57606a", ls=":", lw=1)
    ax[1, 2].set(xlabel="probability threshold", ylabel="score", ylim=(0, 1.02),
                 title="Threshold sweep vs HR23")
    ax[1, 2].legend(fontsize=8)

    for axis in ax.ravel():
        axis.grid(alpha=.15, lw=.5)
    fig.suptitle("M45 membership: pyUPMASK vs Hunt & Reffert 2023", y=.995)
    fig.tight_layout()

    dest = HERE / a.out
    dest.parent.mkdir(exist_ok=True)
    fig.savefig(dest, dpi=130)
    print(f"寫入 {dest}")


if __name__ == "__main__":
    main()
