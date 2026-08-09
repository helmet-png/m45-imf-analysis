# -*- coding: utf-8 -*-
"""第 3 步的診斷圖與文獻對照。

三格：觀測 CMD 疊上最佳解的合成星團、概似曲面、以及與 HR23 的參數比較。
圖上用英文標籤（matplotlib 預設字型沒有中文）。
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.table import Table  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pipeline import config as cfgmod, isochrones as isomod, step3_age  # noqa: E402

VIZIER = "https://tapvizier.cds.unistra.fr/TAPVizieR/tap/sync"


def hr23_params(name):
    adql = ('SELECT "logAge16","logAge50","logAge84","AV16","AV50","AV84",'
            '"diffAV50","MOD50","dist50" FROM "J/A+A/673/A114/clusters" '
            f"WHERE \"Name\"='{name}'")
    body = urllib.parse.urlencode({
        "REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json",
        "QUERY": adql}).encode()
    req = urllib.request.Request(VIZIER, data=body,
                                 headers={"User-Agent": "m45-pipeline/1.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=180).read().decode())
    return dict(zip([m["name"] for m in d["metadata"]], d["data"][0]))


cfg = cfgmod.load()
c3 = cfg.step3_age
fit = np.load(HERE / "results" / "step3_fit.npz")
obs = Table.read(HERE / "data" / "cmd_members.csv", format="csv")
errmodel = dict(np.load(HERE / "data" / "errmodel.npz"))

logage, av, dm = float(fit["logage"]), float(fit["av"]), float(fit["dm"])
print(f"我們的結果: logAge={logage:.3f} ({10**logage/1e6:.1f} Myr), "
      f"A_V={av:.3f}, DM={dm:.3f}")

hr = hr23_params(cfg.target.hr23_name)
print(f"HR23      : logAge={hr['logAge50']:.3f} "
      f"({10**hr['logAge50']/1e6:.1f} Myr) "
      f"[{hr['logAge16']:.2f}, {hr['logAge84']:.2f}], "
      f"A_V={hr['AV50']:.3f} [{hr['AV16']:.2f}, {hr['AV84']:.2f}], "
      f"diffA_V={hr['diffAV50']:.3f}, DM={hr['MOD50']:.3f}")

# 用最佳解生成合成星團
grid = isomod.load_grid(HERE / "isochrones" / (
    f"parsec_v2.0_gaiaEDR3_logt{c3.logage_min:g}-{c3.logage_max:g}"
    f"s{c3.logage_step:g}_mh{c3.mh_min:g}-{c3.mh_max:g}s{c3.mh_step:g}.dat"))
one = isomod.isochrone_at(grid, logage, c3.metallicity_mh)
draws = step3_age.draw_randoms(
    c3.n_synthetic, np.random.default_rng(cfg.step1_membership.random_seed))
ext = step3_age._Ext(cfg.step2_cmd.ext_coeff_g, cfg.step2_cmd.ext_coeff_bp,
                     cfg.step2_cmd.ext_coeff_rp)
sc, sm = step3_age.synth_cluster(
    one, c3.n_synthetic, dm, av, c3.binary_fraction, c3.binary_q_gamma,
    c3.binary_q_min, c3.imf, errmodel, ext, draws,
    g_faint=cfg.step1_membership.g_mag_max,
    g_bright=cfg.step2_cmd.g_bright_limit)

fig, ax = plt.subplots(1, 3, figsize=(16, 5.4))

oc = np.asarray(obs["bp_rp"], float)
om = np.asarray(obs["phot_g_mean_mag"], float)
ax[0].scatter(sc, sm, s=2, lw=0, c="#c8d2e8", label=f"synthetic (n={len(sc):,})",
              rasterized=True)
ax[0].scatter(oc, om, s=6, lw=0, c="#1a1a1a", label=f"observed (n={len(oc):,})",
              rasterized=True)
ax[0].set(xlim=c3.hess_color_range, ylim=c3.hess_mag_range,
          xlabel="BP-RP", ylabel="G (mag)",
          title=f"Best fit: {10**logage/1e6:.0f} Myr, $A_V$={av:.2f}")
ax[0].invert_yaxis()
ax[0].legend(markerscale=3, fontsize=9, loc="lower left")

ll = fit["loglike"]
ages, avs = fit["ages"], fit["avs"]
peak = ll.max()
im = ax[1].pcolormesh(avs, ages, np.clip(ll - peak, -200, 0),
                      cmap="viridis", shading="auto")
ax[1].plot(av, logage, "x", c="#d6555b", ms=12, mew=2.5)
ax[1].axhline(hr["logAge50"], c="#d6555b", ls=":", lw=1.2)
ax[1].text(avs[-1], hr["logAge50"], " HR23", color="#d6555b", va="center",
           fontsize=9)
ax[1].set(xlabel="$A_V$", ylabel="log(age/yr)",
          title="Log-likelihood surface (relative to peak)")
fig.colorbar(im, ax=ax[1], label="$\\Delta \\ln L$")

# 年齡的邊際化概似
marg = ll.max(axis=1)
ax[2].plot(ages, marg - peak, c="#1f6feb", lw=1.8)
ax[2].axvline(logage, c="#1f6feb", ls="--", lw=1,
              label=f"ours {10**logage/1e6:.0f} Myr")
ax[2].axvline(hr["logAge50"], c="#d6555b", ls=":", lw=1.5,
              label=f"HR23 {10**hr['logAge50']/1e6:.0f} Myr")
ax[2].axvspan(hr["logAge16"], hr["logAge84"], color="#d6555b", alpha=.12)
ax[2].set(xlabel="log(age/yr)", ylabel="$\\Delta \\ln L$ (profiled over $A_V$)",
          ylim=(-300, 20), title="Age likelihood")
ax[2].legend(fontsize=9)

for a in ax:
    a.grid(alpha=.15, lw=.5)
fig.suptitle("Step 3: forward-model age and extinction fit", y=.99)
fig.tight_layout()
dest = HERE / "figs" / "step3_agefit.png"
dest.parent.mkdir(exist_ok=True)
fig.savefig(dest, dpi=130)
print(f"\n寫入 {dest}")
