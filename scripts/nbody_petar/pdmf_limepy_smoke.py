#!/usr/bin/env python
"""Multi-mass LIMEPY smoking test for the M45 PDMF-to-IMF correction.

This is deliberately a diagnostic, not a final IMF inference.  It uses the
per-star system masses already written by step 5, fits the *radial shapes* of
four mass groups, and estimates the mass-dependent fraction projected inside
the existing 5.1 degree footprint.  Unresolved-binary and stellar-evolution
corrections remain outside this script.
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import math
import sys
import time
from pathlib import Path

try:                                # Python < 3.11 沒有 tomllib，
    import tomllib                  # 理由見 pipeline/config.py 同一段
except ModuleNotFoundError:
    import tomli as tomllib

import numpy as np


HERE = Path(__file__).resolve().parent.parent.parent  # 2026-08-26 檔案搬到 scripts/nbody_petar/，往上三層才是 repo 根目錄
DEFAULT_MASS_EDGES = np.array([0.30, 0.50, 0.80, 1.20, 2.50])
DEFAULT_RADIAL_EDGES_DEG = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.1])


def _install_scipy_limepy_compatibility() -> list[str]:
    """Patch two legacy DOPRI assumptions without editing site-packages."""
    from scipy.integrate._ode import dopri5

    applied: list[str] = []
    if not getattr(dopri5.__init__, "_m45_limepy_compat", False):
        original_init = dopri5.__init__

        def compatible_init(self, *args, **kwargs):
            if "nsteps" in kwargs:
                kwargs["nsteps"] = int(kwargs["nsteps"])
            return original_init(self, *args, **kwargs)

        compatible_init._m45_limepy_compat = True
        dopri5.__init__ = compatible_init
        applied.append("cast_dopri5_nsteps_to_int")

    # SciPy 1.18's compiled DOPRI runner supplies an extra callback argument.
    # The wrapper is harmless on versions that still supply only (x, y).
    if not getattr(dopri5._solout, "_m45_limepy_compat", False):
        original_solout = dopri5._solout

        def compatible_solout(self, x, y, *unused):
            return original_solout(self, x, y)

        compatible_solout._m45_limepy_compat = True
        dopri5._solout = compatible_solout
        applied.append("accept_extra_dopri5_solout_argument")
    return applied


def load_limepy(package_path: Path | None):
    if package_path is not None:
        sys.path.insert(0, str(package_path.resolve()))
    patches = _install_scipy_limepy_compatibility()
    from limepy import limepy
    import limepy as limepy_package
    import scipy

    return limepy, {
        "limepy_version": getattr(limepy_package, "__version__", "unknown"),
        "scipy_version": scipy.__version__,
        "compatibility_patches": patches,
    }


def angular_separation_deg(ra, dec, ra0: float, dec0: float):
    ra = np.radians(np.asarray(ra, float))
    dec = np.radians(np.asarray(dec, float))
    ra0 = math.radians(ra0)
    dec0 = math.radians(dec0)
    cosr = (
        np.sin(dec0) * np.sin(dec)
        + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    )
    return np.degrees(np.arccos(np.clip(cosr, -1.0, 1.0)))


def load_observations(members_path: Path, mass_path: Path, config_path: Path):
    members = np.genfromtxt(
        members_path, delimiter=",", names=True, dtype=None, encoding="utf-8"
    )
    masses = np.asarray(np.load(mass_path)["masses"], float)
    valid_cmd = np.isfinite(members["bp_rp"]) & np.isfinite(
        members["phot_g_mean_mag"]
    )
    if int(valid_cmd.sum()) != len(masses):
        raise ValueError(
            "Mass-to-member alignment failed: "
            f"{valid_cmd.sum()} valid CMD rows but {len(masses)} masses"
        )
    members = members[valid_cmd]
    if len(members) != len(masses):
        raise AssertionError("Internal alignment error after applying CMD mask")

    with config_path.open("rb") as handle:
        config = tomllib.load(handle)
    zero_point = float(config["step3_age"]["parallax_zero_point"])
    parallax_corrected = float(np.median(members["parallax"]) - zero_point)
    distance_pc = 1000.0 / parallax_corrected

    # Reproduce the centre convention used by run_pipeline.py step 5.
    center_ra = float(np.median(members["ra"]))
    center_dec = float(np.median(members["dec"]))
    radii_deg = angular_separation_deg(
        members["ra"], members["dec"], center_ra, center_dec
    )
    weights = np.asarray(members["probs_final"], float)
    return masses, radii_deg, weights, {
        "n_members": int(len(members)),
        "center_ra_deg": center_ra,
        "center_dec_deg": center_dec,
        "median_parallax_mas": float(np.median(members["parallax"])),
        "parallax_zero_point_mas": zero_point,
        "distance_pc": distance_pc,
    }


def make_radial_profile(
    masses,
    radii_deg,
    weights,
    mass_edges,
    radial_edges_deg,
    distance_pc,
):
    radial_edges_pc = distance_pc * np.tan(np.radians(radial_edges_deg))
    area_pc2 = math.pi * np.diff(radial_edges_pc**2)
    n_mass = len(mass_edges) - 1
    n_radial = len(radial_edges_deg) - 1
    raw = np.zeros((n_mass, n_radial), int)
    weighted = np.zeros((n_mass, n_radial), float)
    weighted_var = np.zeros((n_mass, n_radial), float)
    rows = []

    for j, (m_lo, m_hi) in enumerate(zip(mass_edges[:-1], mass_edges[1:])):
        upper = masses <= m_hi if j == n_mass - 1 else masses < m_hi
        in_mass = (masses >= m_lo) & upper
        for k, (r_lo, r_hi) in enumerate(
            zip(radial_edges_deg[:-1], radial_edges_deg[1:])
        ):
            in_radius = (radii_deg >= r_lo) & (radii_deg < r_hi)
            selected = in_mass & in_radius
            raw[j, k] = int(selected.sum())
            weighted[j, k] = float(weights[selected].sum())
            weighted_var[j, k] = float(np.square(weights[selected]).sum())
            rows.append(
                {
                    "mass_lo_msun": m_lo,
                    "mass_hi_msun": m_hi,
                    "radius_lo_deg": r_lo,
                    "radius_hi_deg": r_hi,
                    "radius_lo_pc": radial_edges_pc[k],
                    "radius_hi_pc": radial_edges_pc[k + 1],
                    "area_pc2": area_pc2[k],
                    "n_raw": raw[j, k],
                    "n_weighted": weighted[j, k],
                    "surface_density_pc2": weighted[j, k] / area_pc2[k],
                    "surface_density_err_pc2": math.sqrt(weighted_var[j, k])
                    / area_pc2[k],
                }
            )
    return raw, weighted, rows, radial_edges_pc


def representative_masses(masses, mass_edges):
    result = []
    for j, (lo, hi) in enumerate(zip(mass_edges[:-1], mass_edges[1:])):
        upper = masses <= hi if j == len(mass_edges) - 2 else masses < hi
        selected = masses[(masses >= lo) & upper]
        if not len(selected):
            raise ValueError(f"No stars in mass interval {lo}-{hi} Msun")
        result.append(float(np.median(selected)))
    return np.asarray(result)


def projected_cumulative(model, component: int, radii_pc):
    values = np.interp(
        radii_pc,
        np.asarray(model.R, float),
        np.asarray(model.mcpj[component], float),
        left=0.0,
        right=float(model.mcpj[component, -1]),
    )
    return np.maximum.accumulate(values)


def conditional_radial_nll(model, weighted_counts, radial_edges_pc):
    total_nll = 0.0
    all_probabilities = []
    for j in range(weighted_counts.shape[0]):
        cumulative = projected_cumulative(model, j, radial_edges_pc)
        denominator = cumulative[-1]
        if not np.isfinite(denominator) or denominator <= 0:
            return math.inf, None
        probabilities = np.diff(cumulative) / denominator
        probabilities = np.clip(probabilities, 1e-12, None)
        probabilities /= probabilities.sum()
        total_nll -= float(np.sum(weighted_counts[j] * np.log(probabilities)))
        all_probabilities.append(probabilities)
    return total_nll, np.asarray(all_probabilities)


def radial_goodness_of_fit(weighted_counts, probabilities):
    expected = weighted_counts.sum(axis=1)[:, None] * probabilities
    valid = expected > 0
    pearson = float(
        np.sum(np.square(weighted_counts[valid] - expected[valid]) / expected[valid])
    )
    positive = (weighted_counts > 0) & valid
    deviance = float(
        2.0
        * np.sum(
            weighted_counts[positive]
            * np.log(weighted_counts[positive] / expected[positive])
        )
    )
    # Four mass-component normalisations and four fitted structural parameters.
    degrees_of_freedom = int(weighted_counts.size - weighted_counts.shape[0] - 4)
    standardized = np.divide(
        weighted_counts - expected,
        np.sqrt(expected),
        out=np.zeros_like(expected),
        where=expected > 0,
    )
    return {
        "pearson_chi2": pearson,
        "deviance": deviance,
        "degrees_of_freedom_approx": degrees_of_freedom,
        "max_absolute_standardized_residual": float(np.max(np.abs(standardized))),
        "expected_weighted_counts": expected,
        "standardized_residuals": standardized,
    }


def fit_structure(
    limepy_class,
    representative_mass,
    component_mass,
    weighted_counts,
    radial_edges_pc,
    phi0_values,
    g_values,
    delta_values,
    rh_values,
):
    records = []
    best = None
    total_mass = max(float(component_mass.sum()), 1.0)
    for phi0 in phi0_values:
        for g in g_values:
            for delta in delta_values:
                for rh in rh_values:
                    started = time.perf_counter()
                    try:
                        model = limepy_class(
                            float(phi0),
                            float(g),
                            mj=representative_mass,
                            Mj=component_mass,
                            M=total_mass,
                            rh=float(rh),
                            delta=float(delta),
                            project=True,
                            meanmassdef="global",
                            verbose=False,
                        )
                        nll, radial_probabilities = conditional_radial_nll(
                            model, weighted_counts, radial_edges_pc
                        )
                        converged = bool(model.converged) and np.isfinite(nll)
                    except Exception as exc:
                        records.append(
                            {
                                "phi0": phi0,
                                "g": g,
                                "delta": delta,
                                "rh_pc": rh,
                                "converged": False,
                                "nll": math.inf,
                                "error": f"{type(exc).__name__}: {exc}",
                                "seconds": time.perf_counter() - started,
                            }
                        )
                        continue
                    record = {
                        "phi0": float(phi0),
                        "g": float(g),
                        "delta": float(delta),
                        "rh_pc": float(rh),
                        "rt_pc": float(model.rt),
                        "converged": converged,
                        "nll": float(nll),
                        "error": "",
                        "seconds": time.perf_counter() - started,
                    }
                    records.append(record)
                    if converged and (best is None or nll < best["nll"]):
                        best = {
                            **record,
                            "model": model,
                            "radial_probabilities": radial_probabilities,
                        }
    if best is None:
        raise RuntimeError("No LIMEPY model converged on the structural grid")
    return best, records


def binned_powerlaw_slope(counts, mass_edges):
    alpha_grid = np.linspace(0.5, 4.0, 3501)
    loglike = np.empty_like(alpha_grid)
    for i, alpha in enumerate(alpha_grid):
        if abs(alpha - 1.0) < 1e-12:
            integrals = np.log(mass_edges[1:] / mass_edges[:-1])
        else:
            exponent = 1.0 - alpha
            integrals = (
                mass_edges[1:] ** exponent - mass_edges[:-1] ** exponent
            ) / exponent
        probabilities = integrals / integrals.sum()
        loglike[i] = np.sum(counts * np.log(probabilities))
    peak = int(np.argmax(loglike))
    threshold = loglike[peak] - 0.5
    accepted = alpha_grid[loglike >= threshold]
    return {
        "alpha": float(alpha_grid[peak]),
        "alpha_err_minus": float(alpha_grid[peak] - accepted[0]),
        "alpha_err_plus": float(accepted[-1] - alpha_grid[peak]),
        "loglike": float(loglike[peak]),
    }


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_float_list(text):
    return [float(value) for value in text.split(",")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--members", type=Path, default=HERE / "data/cmd_members.csv")
    parser.add_argument("--masses", type=Path, default=HERE / "results/step5_imf.npz")
    parser.add_argument("--config", type=Path, default=HERE / "config.toml")
    parser.add_argument("--package-path", type=Path)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--phi0", default="3,4,5,6,7,8,9")
    parser.add_argument("--g", default="0,1,2")
    parser.add_argument("--delta", default="0,0.15,0.3,0.45,0.6")
    parser.add_argument("--rh-pc", default="2,3,4,5,6,8,10")
    parser.add_argument(
        "--output-prefix", type=Path, default=HERE / "results/pdmf_limepy_smoke"
    )
    args = parser.parse_args()

    limepy_class, environment = load_limepy(args.package_path)
    masses, radii_deg, weights, metadata = load_observations(
        args.members, args.masses, args.config
    )
    raw, weighted, profile_rows, radial_edges_pc = make_radial_profile(
        masses,
        radii_deg,
        weights,
        DEFAULT_MASS_EDGES,
        DEFAULT_RADIAL_EDGES_DEG,
        metadata["distance_pc"],
    )
    mass_mid = representative_masses(masses, DEFAULT_MASS_EDGES)
    observed_number = weighted.sum(axis=1)
    component_mass = observed_number * mass_mid

    all_grid_rows = []
    iteration_summaries = []
    best = None
    for iteration in range(args.iterations):
        best, grid_rows = fit_structure(
            limepy_class,
            mass_mid,
            component_mass,
            weighted,
            radial_edges_pc,
            parse_float_list(args.phi0),
            parse_float_list(args.g),
            parse_float_list(args.delta),
            parse_float_list(args.rh_pc),
        )
        for row in grid_rows:
            row["iteration"] = iteration + 1
        all_grid_rows.extend(grid_rows)

        model = best["model"]
        footprint_pc = radial_edges_pc[-1]
        inside_fraction = []
        for j in range(len(mass_mid)):
            at_footprint = projected_cumulative(model, j, [footprint_pc])[0]
            projected_total = float(model.mcpj[j, -1])
            inside_fraction.append(
                float(np.clip(at_footprint / projected_total, 1e-6, 1.0))
            )
        inside_fraction = np.asarray(inside_fraction)
        global_number = observed_number / inside_fraction
        component_mass = global_number * mass_mid
        iteration_summaries.append(
            {
                "iteration": iteration + 1,
                "phi0": best["phi0"],
                "g": best["g"],
                "delta": best["delta"],
                "rh_pc": best["rh_pc"],
                "rt_pc": best["rt_pc"],
                "nll": best["nll"],
                "inside_fraction": inside_fraction.tolist(),
                "global_number": global_number.tolist(),
            }
        )

    observed_fit = binned_powerlaw_slope(observed_number, DEFAULT_MASS_EDGES)
    corrected_fit = binned_powerlaw_slope(global_number, DEFAULT_MASS_EDGES)
    goodness = radial_goodness_of_fit(
        weighted, best["radial_probabilities"]
    )
    result = {
        "status": "smoking_test_not_final_imf",
        "environment": environment,
        "metadata": metadata,
        "mass_edges_msun": DEFAULT_MASS_EDGES.tolist(),
        "representative_mass_msun": mass_mid.tolist(),
        "radial_edges_deg": DEFAULT_RADIAL_EDGES_DEG.tolist(),
        "radial_edges_pc": radial_edges_pc.tolist(),
        "observed_weighted_number": observed_number.tolist(),
        "corrected_global_number": global_number.tolist(),
        "inside_fraction_at_5p1deg": inside_fraction.tolist(),
        "observed_binned_pdmf": observed_fit,
        "spatially_corrected_binned_pdmf": corrected_fit,
        "delta_alpha_spatial": corrected_fit["alpha"] - observed_fit["alpha"],
        "best_model": {
            key: best[key]
            for key in ("phi0", "g", "delta", "rh_pc", "rt_pc", "nll")
        },
        "radial_goodness_of_fit": {
            key: goodness[key]
            for key in (
                "pearson_chi2",
                "deviance",
                "degrees_of_freedom_approx",
                "max_absolute_standardized_residual",
            )
        },
        "iterations": iteration_summaries,
        "caveats": [
            "Uses unresolved-system masses from the traditional step-5 mapping.",
            "Corrects only mass-dependent spatial coverage under equilibrium.",
            "Does not correct binaries, stellar evolution, tidal tails, or membership selection.",
            "LIMEPY is an equilibrium model; potential escapers can bias the extrapolation.",
        ],
    }

    for row, expected, residual in zip(
        profile_rows,
        goodness["expected_weighted_counts"].ravel(),
        goodness["standardized_residuals"].ravel(),
    ):
        row["model_expected_weighted"] = float(expected)
        row["model_standardized_residual"] = float(residual)

    prefix = args.output_prefix
    write_csv(prefix.with_name(prefix.name + "_radial_profile.csv"), profile_rows)
    write_csv(prefix.with_name(prefix.name + "_grid.csv"), all_grid_rows)
    json_path = prefix.with_suffix(".json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
