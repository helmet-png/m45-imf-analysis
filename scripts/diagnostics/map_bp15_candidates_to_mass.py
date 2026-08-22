#!/usr/bin/env python
"""Map BP15-recovered candidates to approximate headline-isochrone masses."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def number(row, name):
    value = row.get(name, "")
    return float(value) if value not in ("", "null") else np.nan


def main():
    quality = json.loads(
        (ROOT / "results" / "hr23_bp15_colour_error_comparison.json")
        .read_text(encoding="utf-8")
    )
    wanted = set(quality["recovered_source_ids"])
    rows = [
        row for row in load_csv(ROOT / "data" / "hr23_passprob_notcmd_gaia_photometry.csv")
        if row["source_id"] in wanted
    ]
    cmd = load_csv(ROOT / "data" / "cmd_members.csv")
    saved_masses = np.load(ROOT / "results" / "step5_imf.npz")["masses"]
    if len(saved_masses) != len(cmd):
        raise RuntimeError("Saved step5 masses are not aligned with cmd_members.csv")
    cmd_g = np.asarray([number(row, "phot_g_mean_mag") for row in cmd])
    valid = np.isfinite(cmd_g) & np.isfinite(saved_masses)
    order = np.argsort(cmd_g[valid])
    reference_g = cmd_g[valid][order]
    reference_mass = saved_masses[valid][order]
    g = np.asarray([number(row, "phot_g_mean_mag") for row in rows])
    mass_from_g = np.interp(g, reference_g, reference_mass, left=np.nan, right=np.nan)

    stars = []
    for row, mass_g in zip(rows, mass_from_g):
        stars.append({
            "source_id": row["source_id"],
            "g": number(row, "phot_g_mean_mag"),
            "bp_rp": number(row, "bp_rp"),
            "mass_from_g_msun": float(mass_g) if np.isfinite(mass_g) else None,
        })

    finite = mass_from_g[np.isfinite(mass_from_g)]
    output = {
        "status": "empirical_mapping_from_saved_step5_not_imf_refit",
        "reference": "results/step5_imf.npz masses aligned to data/cmd_members.csv",
        "candidate_count": len(rows),
        "finite_mass_count": int(len(finite)),
        "mass_min_msun": float(np.min(finite)) if len(finite) else None,
        "mass_median_msun": float(np.median(finite)) if len(finite) else None,
        "mass_max_msun": float(np.max(finite)) if len(finite) else None,
        "mass_below_0p3": int((finite < 0.3).sum()),
        "mass_0p3_to_0p5": int(((finite >= 0.3) & (finite < 0.5)).sum()),
        "mass_at_least_0p5": int((finite >= 0.5).sum()),
        "stars": sorted(stars, key=lambda star: star["g"]),
        "limits": [
            "Masses are empirical G-band interpolation from the already-saved step5 mass array.",
            "The saved step5 mapping predates the p2final_v3 headline and is used only to locate the candidates relative to the 0.5 Msun break.",
            "Unresolved binaries and differential extinction can change individual inferred masses.",
            "The forward alpha parameter changes only the mass segment above 0.5 Msun, but lower-mass CMD cells can still constrain nuisance parameters.",
            "No membership model, selection function, forward model or IMF was rerun.",
        ],
    }
    out = ROOT / "results" / "hr23_bp15_candidate_mass_mapping.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items() if key != "stars"}, indent=2))


if __name__ == "__main__":
    main()
