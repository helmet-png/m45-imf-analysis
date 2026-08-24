"""Compare the saved LIMEPY radial prediction with final five-seed fits.

This is a lightweight post-processing step.  It does not refit LIMEPY or rerun
the forward model.  The final radial files share repeat offsets 0--4, so radial
increments are compared seed by seed.  The saved LIMEPY prediction has no
uncertainty estimate; consequently the reported standardized residuals are
diagnostics, not formal model-rejection significances.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
TAGS = ("r1", "r2", "r3", "rall")
ALPHA_COLUMN = 3
EXPECTED_RADIUS = {"r1": "0,1", "r2": "0,2", "r3": "0,3", "rall": None}
FIXED_SETTINGS = (
    "fix_mh", "free_lowmass", "g_bright", "grid", "n_syn",
    "native_bprp_err", "refines",
)


def load_final(tag: str) -> tuple[np.ndarray, dict]:
    path = ROOT / "results" / f"fit_real_radial_{tag}_final.npz"
    with np.load(path, allow_pickle=False) as data:
        values = np.asarray(data["C"], dtype=float)
        manifest = json.loads(str(data["__manifest__"].item()))
    if values.shape != (5, 7):
        raise ValueError(f"{path.name}: expected C shape (5, 7), got {values.shape}")
    if manifest.get("n_syn") != 40000 or manifest.get("refines") != "3,3":
        raise ValueError(f"{path.name}: unexpected formal-run manifest: {manifest}")
    if manifest.get("radius_range") != EXPECTED_RADIUS[tag]:
        raise ValueError(
            f"{path.name}: radius_range={manifest.get('radius_range')!r}, "
            f"expected {EXPECTED_RADIUS[tag]!r}")
    offsets = manifest.get("aggregated_repeat_offsets")
    if offsets is not None and offsets != [0, 1, 2, 3, 4]:
        raise ValueError(f"{path.name}: unexpected repeat offsets: {offsets}")
    return values[:, ALPHA_COLUMN], manifest


def sample_summary(values: np.ndarray) -> dict[str, float | list[float]]:
    sd = float(np.std(values, ddof=1))
    return {
        "values": values.tolist(),
        "mean": float(np.mean(values)),
        "sample_sd": sd,
        "sem": sd / float(np.sqrt(values.size)),
    }


def main() -> None:
    old_path = ROOT / "results" / "limepy_radial_crosscheck.npz"
    with np.load(old_path, allow_pickle=False) as old:
        saved_tags = tuple(str(x) for x in old["tags"])
        model_alpha = np.asarray(old["model_alpha"], dtype=float)
        radius_pc = np.asarray(old["radius_pc"], dtype=float)
    if saved_tags != TAGS or model_alpha.shape != (4,):
        raise ValueError("saved LIMEPY cross-check does not contain r1/r2/r3/rall")

    observed: dict[str, np.ndarray] = {}
    manifests: dict[str, dict] = {}
    rows = []
    for index, tag in enumerate(TAGS):
        alpha, manifest = load_final(tag)
        observed[tag] = alpha
        manifests[tag] = manifest
        summary = sample_summary(alpha)
        difference = float(model_alpha[index] - summary["mean"])
        rows.append({
            "tag": tag,
            "radius_pc": float(radius_pc[index]),
            "model_alpha": float(model_alpha[index]),
            "observed": summary,
            "model_minus_observed_mean": difference,
            "difference_over_observed_sample_sd": difference / summary["sample_sd"],
            "difference_over_observed_sem": difference / summary["sem"],
        })

    reference = manifests["r1"]
    for tag in TAGS[1:]:
        for key in FIXED_SETTINGS:
            if manifests[tag].get(key) != reference.get(key):
                raise ValueError(
                    f"{tag}: fixed setting {key!r} differs from r1: "
                    f"{manifests[tag].get(key)!r} != {reference.get(key)!r}")

    increments = []
    for index in range(1, len(TAGS)):
        inner, outer = TAGS[index - 1], TAGS[index]
        paired = observed[outer] - observed[inner]
        model_increment = float(model_alpha[index] - model_alpha[index - 1])
        summary = sample_summary(paired)
        residual = model_increment - summary["mean"]
        increments.append({
            "comparison": f"{outer}-{inner}",
            "model_increment": model_increment,
            "observed_paired_increment": summary,
            "model_minus_observed_increment": residual,
            "residual_over_paired_sample_sd": residual / summary["sample_sd"],
        })

    output = {
        "status": "diagnostic_complete_model_uncertainty_missing",
        "inputs": {
            "model_prediction": "results/limepy_radial_crosscheck.npz",
            "observations": [
                f"results/fit_real_radial_{tag}_final.npz" for tag in TAGS
            ],
            "formal_run_manifests": manifests,
            "manifest_validation": {
                "checked_fixed_settings": list(FIXED_SETTINGS),
                "checked_radius_range": EXPECTED_RADIUS,
                "metadata_absent_from_all_manifests": [
                    "tag", "seed_scheme", "input_file_metadata"
                ],
                "offset_metadata_absent": [
                    tag for tag in TAGS
                    if "aggregated_repeat_offsets" not in manifests[tag]
                ],
            },
        },
        "absolute_comparison": rows,
        "paired_radial_increments": increments,
        "interpretation_limits": [
            "LIMEPY model uncertainty was not estimated.",
            "The LIMEPY model and radial fits use overlapping stars and are not independent.",
            "Three LIMEPY mass bins and individual-star forward-model estimates are different estimators.",
            "r3 and rall manifests predate aggregate-offset metadata; their 0--4 offset provenance is documented in RESULTS_LOG rather than machine-verifiable here.",
            "Standardized residuals therefore describe scale only and are not formal rejection significances.",
        ],
    }
    out_path = ROOT / "results" / "limepy_radial_crosscheck.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
