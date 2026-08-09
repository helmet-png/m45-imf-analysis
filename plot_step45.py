# -*- coding: utf-8 -*-
"""第 4、5 步的診斷圖。圖上用英文標籤（matplotlib 預設字型沒有中文）。"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.table import Table  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pipeline import config as cfgmod  # noqa: E402

cfg = cfgmod.load()
f4 = np.load(HERE / "results" / "step4_fit.npz")
f5 = np.load(HERE / "results" / "step5_imf.npz")
bins = Table.read(HERE / "results" / "step4_binaries.csv", format="csv")
radial = Table.read(HERE / "results" / "step5_mf_radial.csv", format="csv")
obs = Table.read(HERE / "data" / "cmd_members.csv", format="csv")

fig, ax = plt.subplots(2, 3, figsize=(16.5, 9.5))

# 1) 雙星比例的邊際化概似
ll = f4["loglike"]
fbins = f4["fbins"]
marg = ll.reshape(-1, len(fbins)).max(axis=0)
ax[0, 0].plot(fbins, marg - marg.max(), "o-", c="#1f6feb", ms=4)
ax[0, 0].axvline(float(f4["fbin"]), c="#1f6feb", ls="--", lw=1,
                 label=f"best $f_b$={float(f4['fbin']):.2f}")
ax[0, 0].axvspan(0.15, 0.60, color="#8a8f98", alpha=.12,
                 label="Cordoni+2023 range")
ax[0, 0].set(xlabel="binary fraction $f_b$",
             ylabel="$\\Delta \\ln L$ (profiled)",
             title="Population-level binary fraction", ylim=(-400, 30))
ax[0, 0].legend(fontsize=8)

# 2) 四種方法標記數與兩兩重疊
names = ["前向模型", "RUWE", "CMD偏移", "GaiaNSS"]
labels = ["Forward\nmodel", "RUWE", "CMD\noffset", "Gaia\nNSS"]
counts = [int(np.asarray(bins[n], int).sum()) for n in names]
ax[0, 1].bar(labels, counts, color=["#1f6feb", "#bf8700", "#1a7f37", "#cf222e"])
for i, c in enumerate(counts):
    ax[0, 1].text(i, c + 8, str(c), ha="center", fontsize=10)
ax[0, 1].set(ylabel="stars flagged as binary",
             title=f"Four methods on the same {len(bins):,} stars")

# 3) 兩兩交集比例熱圖
mat = np.zeros((4, 4))
for i, a in enumerate(names):
    fa = np.asarray(bins[a], int).astype(bool)
    for j, b in enumerate(names):
        fb = np.asarray(bins[b], int).astype(bool)
        mat[i, j] = np.nan if i == j else (fa & fb).sum() / max((fa | fb).sum(), 1)
im = ax[0, 2].imshow(mat * 100, cmap="viridis", vmin=0, vmax=30)
ax[0, 2].set_xticks(range(4), labels, fontsize=8)
ax[0, 2].set_yticks(range(4), labels, fontsize=8)
for i in range(4):
    for j in range(4):
        if i != j:
            ax[0, 2].text(j, i, f"{mat[i,j]*100:.0f}%", ha="center",
                          va="center", color="w", fontsize=9)
ax[0, 2].set_title("Pairwise agreement (intersection / union)")
fig.colorbar(im, ax=ax[0, 2], label="%")

# 4) CMD 依雙星機率上色
pb = np.asarray(bins["binary_prob"], float)
c = np.asarray(obs["bp_rp"], float)
m = np.asarray(obs["phot_g_mean_mag"], float)
n = min(len(pb), len(c))
s = ax[1, 0].scatter(c[:n], m[:n], c=pb[:n], s=7, lw=0, cmap="magma",
                     vmin=0, vmax=1, rasterized=True)
ax[1, 0].set(xlabel="BP-RP", ylabel="G (mag)", xlim=(-0.2, 3.8), ylim=(4, 18),
             title="Per-star binary probability (forward model)")
ax[1, 0].invert_yaxis()
fig.colorbar(s, ax=ax[1, 0], label="$P_{\\rm binary}$")

# 5) 質量函數與兩種擬合
masses = f5["masses"]
c5 = cfg.step5_imf
mm = masses[np.isfinite(masses) & (masses >= c5.mass_min)
            & (masses <= c5.mass_max)]
edges = np.logspace(np.log10(c5.mass_min), np.log10(c5.mass_max), 18)
h, _ = np.histogram(mm, bins=edges)
ctr = np.sqrt(edges[:-1] * edges[1:])
dm = np.diff(edges)
ax[1, 1].errorbar(ctr, h / dm, yerr=np.sqrt(h) / dm, fmt="o", c="#1a1a1a",
                  ms=4, label=f"observed (n={len(mm):,})")
for a, col, lab in ((float(f5["alpha_naive"]), "#cf222e",
                     f"naive $\\alpha$={float(f5['alpha_naive']):.2f}"),
                    (float(f5["alpha_forward"]), "#1f6feb",
                     f"forward $\\alpha$={float(f5['alpha_forward']):.2f}"),
                    (2.35, "#8a8f98", "Salpeter 2.35")):
    y = ctr ** (-a)
    y = y * (h / dm)[len(ctr) // 2] / y[len(ctr) // 2]
    ax[1, 1].plot(ctr, y, c=col, lw=1.8, ls="-" if a != 2.35 else ":", label=lab)
ax[1, 1].set(xscale="log", yscale="log", xlabel="mass ($M_\\odot$)",
             ylabel="$dN/dm$", title="Mass function and power-law fits")
ax[1, 1].legend(fontsize=8)

# 6) 質量分層：alpha 隨半徑
rc = 0.5 * (np.asarray(radial["r_lo"], float) + np.asarray(radial["r_hi"], float))
ax[1, 2].errorbar(rc, np.asarray(radial["alpha"], float),
                  yerr=np.asarray(radial["alpha_err"], float),
                  fmt="o-", c="#1f6feb", ms=6, capsize=3)
ax[1, 2].axhline(2.35, c="#8a8f98", ls=":", lw=1.2, label="Salpeter 2.35")
ax[1, 2].axhline(float(f5["alpha_forward"]), c="#cf222e", ls="--", lw=1,
                 label="global (forward)")
for x, y, nn in zip(rc, np.asarray(radial["alpha"], float),
                    np.asarray(radial["n"], int)):
    ax[1, 2].annotate(f"n={nn}", (x, y), textcoords="offset points",
                      xytext=(0, 11), ha="center", fontsize=8)
ax[1, 2].set(xlabel="radius (deg)", ylabel="$\\alpha$",
             title="Mass segregation: MF slope vs radius")
ax[1, 2].legend(fontsize=8)

for a in ax.ravel():
    a.grid(alpha=.15, lw=.5)
fig.suptitle("Steps 4 & 5: binary treatment and the mass function", y=.995)
fig.tight_layout()
dest = HERE / "figs" / "step45_binaries_imf.png"
dest.parent.mkdir(exist_ok=True)
fig.savefig(dest, dpi=130)
print(f"寫入 {dest}")
