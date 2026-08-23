#!/usr/bin/env python
"""Quantify the size of the BP15 candidate set relative to saved M45 samples."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def main():
    cmd_path = ROOT / "data" / "cmd_members.csv"
    with cmd_path.open(newline="", encoding="utf-8-sig") as handle:
        cmd = list(csv.DictReader(handle))
    masses = np.load(ROOT / "results" / "step5_imf.npz")["masses"]
    candidate_map = json.loads(
        (ROOT / "results" / "hr23_bp15_candidate_mass_mapping.json")
        .read_text(encoding="utf-8")
    )
    if len(masses) != len(cmd):
        raise RuntimeError("Saved masses and cmd_members.csv are not aligned")

    g = np.asarray([float(row["phot_g_mean_mag"]) for row in cmd])
    finite = masses[np.isfinite(masses)]
    n_candidates = int(candidate_map["candidate_count"])
    # Candidates actually located in the >=0.5 Msun segment that controls the
    # forward-model alpha, per the saved G->mass mapping (map_bp15_candidates
    # _to_mass.py).  This must be read from that mapping rather than assumed
    # to be zero: a future rerun with a different candidate set or mapping
    # could put some candidates above 0.5 Msun, and a hardcoded 0.0 here
    # would silently under-report the alpha-segment impact.
    n_candidates_at_least_0p5 = int(candidate_map["mass_at_least_0p5"])
    below_03 = int((finite < 0.3).sum())
    at_least_05 = int((finite >= 0.5).sum())
    faint = int(((g >= 16) & (g < 18)).sum())
    output = {
        "status": "hypothetical_sample_scale_not_membership_or_imf_result",
        "current_cmd_count": len(cmd),
        "current_finite_saved_mass_count": int(len(finite)),
        "current_mass_bins": {
            "below_0p3": below_03,
            "0p3_to_0p5": int(((finite >= 0.3) & (finite < 0.5)).sum()),
            "at_least_0p5": at_least_05,
        },
        "current_G16_to_18_count": faint,
        "bp15_candidate_count": n_candidates,
        "bp15_candidate_count_at_least_0p5": n_candidates_at_least_0p5,
        "hypothetical_increase_if_all_candidates_are_accepted": {
            "relative_to_all_current_cmd_percent": 100 * n_candidates / len(cmd),
            "relative_to_current_below_0p3_percent": 100 * n_candidates / below_03,
            "relative_to_current_G16_to_18_percent": 100 * n_candidates / faint,
            "relative_to_alpha_segment_at_least_0p5_percent": (
                100 * n_candidates_at_least_0p5 / at_least_05
                if at_least_05 else None
            ),
        },
        "limits": [
            "The increases are bookkeeping scenarios, not proof that all 16 candidates should be accepted.",
            "No background contaminants are counted because the full field/control selection has not been rebuilt.",
            "The saved step5 masses are used only for bin location and predate p2final_v3.",
            "No membership model, selection function, forward model or IMF was rerun.",
        ],
    }
    out = ROOT / "results" / "hr23_bp15_sample_scale.json"
    out.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
