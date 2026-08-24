"""Measure Praesepe offsets from the fixed-age single-star PARSEC locus."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def read_members(path: Path) -> tuple[np.ndarray, np.ndarray]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    colour = np.asarray([float(row["bp_rp"]) for row in rows])
    g = np.asarray([float(row["phot_g_mean_mag"]) for row in rows])
    finite = np.isfinite(colour) & np.isfinite(g)
    return colour[finite], g[finite]


def read_isochrone(path: Path, logage: float) -> tuple[np.ndarray, np.ndarray]:
    header = None
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("# Zini"):
                header = line[2:].split()
            elif line.strip() and not line.startswith("#"):
                rows.append(line.split())
    if header is None:
        raise ValueError("PARSEC column header not found")
    index = {name: i for i, name in enumerate(header)}
    if "MH" not in index:
        raise ValueError("PARSEC grid must contain an MH column")
    data = np.asarray(rows, dtype=float)
    solar = np.isclose(data[:, index["MH"]], 0.0)
    available_ages = np.unique(data[solar, index["logAge"]])
    if not np.any(np.isclose(available_ages, logage)):
        raise ValueError(
            f"requested solar-metallicity logAge={logage:.3f} is absent; "
            f"available range is {available_ages.min():.3f}-{available_ages.max():.3f}")
    use = solar & np.isclose(data[:, index["logAge"]], logage)
    # label 0/1 is the unevolved/main-sequence locus; exclude later phases.
    use &= data[:, index["label"]] <= 1
    bp = data[use, index["G_BP_fSBmag"]]
    rp = data[use, index["G_RP_fSBmag"]]
    g = data[use, index["G_fSBmag"]]
    colour = bp - rp
    order = np.argsort(colour)
    colour, g = colour[order], g[order]
    unique, positions = np.unique(colour, return_index=True)
    return unique, g[positions]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--members", type=Path,
                        default=ROOT / "data/cluster_NGC_2632_cmd_members.csv")
    parser.add_argument("--params", type=Path,
                        default=ROOT / "data/hr23_NGC_2632_params.json")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "results/praesepe_cmd_residual_d17.json")
    args = parser.parse_args()
    params = json.loads(args.params.read_text(encoding="utf-8"))
    age = 8.55  # nearest grid point used by the saved post-merge fixed-age fit
    av = float(params["AV50"])
    dm = float(params["MOD50"])
    iso_c, iso_g = read_isochrone(args.grid, age)
    # Production config extinction coefficients.
    iso_c = iso_c + (1.08 - 0.63) * av
    iso_g = iso_g + dm + 0.83 * av
    colour, g = read_members(args.members)
    inside = (colour >= iso_c.min()) & (colour <= iso_c.max())
    colour, g = colour[inside], g[inside]
    model_g = np.interp(colour, iso_c, iso_g)
    delta = g - model_g  # negative means brighter than the single-star locus
    anchor = (g >= 10.0) & (g < 14.0)
    anchor_shift = float(np.median(delta[anchor]))
    relative_delta = delta - anchor_shift
    bins = []
    for lo in np.arange(6.0, 18.0, 2.0):
        use = (g >= lo) & (g < lo + 2.0)
        if not use.any():
            continue
        bins.append({
            "g_lo": float(lo), "g_hi": float(lo + 2.0), "n": int(use.sum()),
            "median_delta_g": float(np.median(delta[use])),
            "fraction_brighter_0p25": float(np.mean(delta[use] <= -0.25)),
            "fraction_brighter_0p50": float(np.mean(delta[use] <= -0.50)),
            "p16_delta_g": float(np.percentile(delta[use], 16)),
            "p84_delta_g": float(np.percentile(delta[use], 84)),
        })
    members_path = args.members.resolve()
    try:
        members_display = str(members_path.relative_to(ROOT.resolve()))
    except ValueError:
        members_display = str(members_path)
    low_mass = (g >= 14.0) & (g < 18.0)
    output = {
        "members": members_display,
        "grid_name": args.grid.name,
        "logage_grid": age, "av": av, "distance_modulus": dm,
        "n_finite_members": int(len(read_members(args.members)[0])),
        "n_within_isochrone_colour": int(len(delta)),
        "median_delta_g": float(np.median(delta)),
        "fraction_brighter_0p25": float(np.mean(delta <= -0.25)),
        "fraction_brighter_0p50": float(np.mean(delta <= -0.50)),
        "fraction_fainter_0p25": float(np.mean(delta >= 0.25)),
        "anchor_g_10_14_median_delta_g": anchor_shift,
        "low_mass_proxy_g_14_18": {
            "n": int(low_mass.sum()),
            "median_relative_delta_g": float(np.median(relative_delta[low_mass])),
            "fraction_relative_brighter_0p25": float(np.mean(relative_delta[low_mass] <= -0.25)),
            "fraction_relative_brighter_0p50": float(np.mean(relative_delta[low_mass] <= -0.50)),
        },
        "magnitude_bins": bins,
        "interpretation_guardrail": (
            "Observational residual diagnostic only; saved forward B fits hit f_bin=1 "
            "and remain invalid for IMF inference."),
    }
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
