#!/usr/bin/env python3
"""Summarize the recovered r1--r9 free-lowmass forward-model fits.

The nine recovered archives are independent model-randomness repeats with
repeat offsets 1--9.  This script validates their manifests before calculating
any aggregate.  The older preserved candidate for offset 0 has no manifest, so
it is reported for provenance only and is never mixed into the formal summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
COLUMN_ORDER = (
    "logage",
    "av_mean",
    "f_bin",
    "alpha",
    "MH",
    "q_gamma",
    "dav",
    "p_lowmass",
)
EXPECTED_OFFSETS = tuple(range(1, 10))
EXPECTED_MANIFEST = {
    "free_lowmass": True,
    "n_syn": 40_000,
    "refines": "3,3",
    "seed_scheme": "fit-real-offset-v1:2000+13*(rep+repeat_offset)",
    "grid": "parsec_v2.0_gaiaEDR3_logt7.7-8.3s0.05_mh-0.6-0.6s0.05.dat",
    "members_file": "data/cmd_members.csv",
    "errmodel_file": "data/errmodel.npz",
    "selection_file": "data/selection.npz",
    "fix_mh": None,
    "native_bprp_err": False,
    "radius_range": None,
    "g_bright": None,
}


def read_manifest(raw: np.lib.npyio.NpzFile) -> dict:
    """Decode the manifest field, rejecting archives without one."""
    if "__manifest__" not in raw.files:
        raise ValueError("missing __manifest__")
    value = raw["__manifest__"]
    return json.loads(str(value.item() if value.shape == () else value))


def load_recovered(path: Path, offset: int) -> tuple[np.ndarray, dict]:
    """Load and fail closed on one recovered rN archive."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with np.load(path, allow_pickle=False) as raw:
        required = {"C", "__attempted_C", "__manifest__"}
        missing = sorted(required.difference(raw.files))
        if missing:
            raise ValueError(f"{path.name}: missing arrays {missing}")
        values = np.asarray(raw["C"], dtype=float)
        attempted = np.asarray(raw["__attempted_C"], dtype=int)
        manifest = read_manifest(raw)
    if values.shape != (1, len(COLUMN_ORDER)):
        raise ValueError(f"{path.name}: expected C shape (1, 8), got {values.shape}")
    if attempted.shape != (1,) or int(attempted[0]) != 1:
        raise ValueError(
            f"{path.name}: expected one attempted config-C repeat, got {attempted.tolist()}"
        )
    if not np.isfinite(values).all():
        raise ValueError(f"{path.name}: C contains a non-finite value")
    if manifest.get("tag") != f"_free_lowmass_r{offset}":
        raise ValueError(f"{path.name}: tag does not match offset {offset}")
    if manifest.get("repeat_offset") != offset:
        raise ValueError(f"{path.name}: repeat_offset does not match filename")
    for key, expected in EXPECTED_MANIFEST.items():
        if manifest.get(key) != expected:
            raise ValueError(
                f"{path.name}: manifest {key}={manifest.get(key)!r}, expected {expected!r}"
            )
    return values[0], manifest


def summarize(values: np.ndarray) -> dict[str, dict[str, float]]:
    """Return descriptive repeat-to-repeat statistics for every fit parameter."""
    return {
        name: {
            "mean": float(values[:, index].mean()),
            "sample_sd": float(values[:, index].std(ddof=1)),
            "sem": float(values[:, index].std(ddof=1) / np.sqrt(values.shape[0])),
            "minimum": float(values[:, index].min()),
            "maximum": float(values[:, index].max()),
        }
        for index, name in enumerate(COLUMN_ORDER)
    }


def inspect_legacy(path: Path) -> dict:
    """Describe, but do not validate or aggregate, the manifest-free offset-0 candidate."""
    if not path.exists():
        return {
            "present": False,
            "eligible_for_formal_aggregate": False,
            "reason": "legacy offset-0 candidate is absent",
        }
    with np.load(path, allow_pickle=False) as raw:
        values = np.asarray(raw["C"], dtype=float) if "C" in raw.files else None
        ln_p = np.asarray(raw["lnP"], dtype=float) if "lnP" in raw.files else None
        has_manifest = "__manifest__" in raw.files
    row_is_compatible_shape = values is not None and values.shape == (1, len(COLUMN_ORDER))
    return {
        "present": True,
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "has_manifest": has_manifest,
        "C_shape": list(values.shape) if values is not None else None,
        "lnP": float(ln_p[0]) if ln_p is not None and ln_p.shape == (1,) else None,
        "parameter_row": values[0].tolist() if row_is_compatible_shape else None,
        "eligible_for_formal_aggregate": False,
        "reason": (
            "The archive has no manifest, so its input files, refinement recipe, "
            "seed scheme, and repeat offset cannot be machine-verified."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=ROOT / "results")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "fit_real_free_lowmass_r1_r9_summary.json",
    )
    parser.add_argument(
        "--legacy-offset0",
        type=Path,
        default=ROOT / "results" / "p2_free_lowmass_rep1_preserved.npz",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    rows = []
    manifests = []
    for offset in EXPECTED_OFFSETS:
        path = args.results_dir / f"fit_real_free_lowmass_r{offset}.npz"
        row, manifest = load_recovered(path, offset)
        rows.append(row)
        manifests.append(manifest)
    values = np.vstack(rows)

    output = {
        "status": "complete_recovered_subset_offsets_1_to_9",
        "column_order": list(COLUMN_ORDER),
        "formal_repeat_offsets": list(EXPECTED_OFFSETS),
        "n_formal_recovered_repeats": len(EXPECTED_OFFSETS),
        "manifest_validation": {
            "all_expected_files_present": True,
            "all_manifests_match_expected_recipe": True,
            "validated_recipe": EXPECTED_MANIFEST,
            "tags": [manifest["tag"] for manifest in manifests],
        },
        "parameter_statistics": summarize(values),
        "alpha_p_lowmass_correlation": float(
            np.corrcoef(values[:, 3], values[:, 7])[0, 1]
        ),
        "legacy_offset0_candidate": inspect_legacy(args.legacy_offset0),
        "formal_aggregate_status": "not_a_complete_10_repeat_aggregate",
        "interpretation_limits": [
            "The nine runs differ only through model-randomness repeat offsets; they do not measure observational sampling uncertainty.",
            "The manifest-free offset-0 candidate is excluded from every formal statistic in this file.",
            "The free-lowmass fit does not replace the p6_lowmass_v3 profile needed to measure d(alpha)/d(p).",
            "These descriptive statistics are not a final M45 IMF measurement.",
        ],
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.write:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
