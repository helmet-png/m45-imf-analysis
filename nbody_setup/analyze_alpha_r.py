"""Compute alpha(r) from a PeTar snapshot of an N-body cluster pilot run,
reusing the M45 project's own mle_powerlaw() (pipeline/step5_imf.py) for a
like-for-like comparison against the observational alpha(r).

Run from the directory containing the PeTar output (data.core, and
data.<N>.single/.binary produced by `petar.data.process`). Needs two paths
that vary by machine:
  NBODY_INSTALL_PATH   PeTar install prefix (contains include/petar/), see
                       nbody_setup/README.md. Default: ../install relative
                       to this repo's parent directory.
  (this repo's own path is found automatically via this file's location)

Usage:
  NBODY_INSTALL_PATH=/path/to/nbody/install python analyze_alpha_r.py data.25
"""
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NBODY_INSTALL = os.environ.get(
    "NBODY_INSTALL_PATH", str(REPO_ROOT.parent / "nbody" / "install"))
sys.path.insert(0, str(Path(NBODY_INSTALL) / "include"))
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from petar import Particle, Binary
from pipeline.step5_imf import mle_powerlaw

prefix = sys.argv[1] if len(sys.argv) > 1 else "data.25"

single = Particle(interrupt_mode="bse")
single.loadtxt(prefix + ".single")
binary = Binary(member_particle_type=Particle, interrupt_mode="bse")
binary.loadtxt(prefix + ".binary")

mass = np.concatenate([single.mass, binary.mass])
pos = np.concatenate([single.pos, binary.pos], axis=0)

core = np.loadtxt("data.core")
center = core[1:4] if core.ndim == 1 else core[-1, 1:4]
r = np.sqrt(np.sum((pos - center) ** 2, axis=1))

print(f"N bodies (singles + binary COMs): {len(mass)}")
print(f"Total mass: {mass.sum():.2f} Msun")
print(f"Mass range: {mass.min():.3f} - {mass.max():.3f} Msun")
print(f"Radius percentiles (pc): "
      f"10%={np.percentile(r, 10):.2f} 50%={np.percentile(r, 50):.2f} "
      f"90%={np.percentile(r, 90):.2f} max={r.max():.1f}")
n_far = np.sum(r > 20)
print(f"Bodies beyond 20 pc (likely dynamically ejected, not bound cluster "
      f"members): {n_far}")

# bound members only: exclude far-flung ejecta (same spirit as the
# pipeline's own r-escape criterion) so radius bins reflect the actual
# cluster body, not stars in free flight after an ejection
bound = r < 20
mass_b, r_b = mass[bound], r[bound]
print(f"Bound bodies used for alpha(r): {len(mass_b)}")

mass_min, mass_max = 0.1, 2.0
edges = np.percentile(r_b, [0, 33, 66, 100])
print(f"\nRadius bin edges (tertiles of bound sample, pc): {edges}")

print("\nalpha(r):")
print("r_lo   r_hi     n   alpha  alpha_err  median_mass")
for lo, hi in zip(edges[:-1], edges[1:]):
    sel = (r_b >= lo) & (r_b <= hi)
    fit = mle_powerlaw(mass_b[sel], mass_min, mass_max)
    in_range = mass_b[sel][(mass_b[sel] >= mass_min) & (mass_b[sel] <= mass_max)]
    med_m = np.median(in_range) if len(in_range) else float("nan")
    print(f"{lo:5.2f} {hi:6.2f}  {fit['n']:4d}  {fit['alpha']:.3f}  "
          f"{fit['alpha_err']:.3f}      {med_m:.3f}")
