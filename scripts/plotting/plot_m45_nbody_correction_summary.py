#!/usr/bin/env python3
"""Create a presentation-ready summary of the M45 PeTar screening grid.

The figure deliberately reports a component-star dynamical correction, rather
than a final observed IMF.  Its values are read from the committed ensemble
run tables so that a later rerun can reproduce the graphic without manual
transcription.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[2] / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALL = ROOT / "results" / "m45_full_10run_ensemble_20260913_runs.csv"
DEFAULT_CENTRAL = ROOT / "results" / "m45_central_3seed_ensemble_20260912_runs.csv"
DEFAULT_OUTPUT = ROOT / "results" / "figures" / "m45_nbody_correction_summary_20260914.png"


def read_runs(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No runs found in {path}")
    required = {"run_id", "delta_correction_to_add_to_pdmf_for_imf", "priority"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {', '.join(sorted(missing))}")
    return rows


def correction(row: dict[str, str]) -> float:
    return float(row["delta_correction_to_add_to_pdmf_for_imf"])


def short_label(run_id: str) -> str:
    return run_id.removeprefix("m45_").removesuffix("_s101").replace("_", " ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-runs", type=Path, default=DEFAULT_ALL)
    parser.add_argument("--central-runs", type=Path, default=DEFAULT_CENTRAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    all_runs = read_runs(args.all_runs)
    central_runs = read_runs(args.central_runs)
    all_values = np.array([correction(row) for row in all_runs])
    central_values = np.array([correction(row) for row in central_runs])
    q16, median, q84 = np.quantile(all_values, [0.16, 0.50, 0.84])

    fig, (seed_ax, grid_ax) = plt.subplots(1, 2, figsize=(12.2, 6.4))
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.25, top=0.84, wspace=0.08)

    seed_x = np.arange(len(central_runs))
    seed_ax.scatter(seed_x, central_values, color="#1f6feb", s=72, zorder=3)
    seed_ax.axhline(np.median(central_values), color="#1f6feb", lw=1.8, ls="--",
                    label=f"median = {np.median(central_values):+.4f}")
    seed_ax.set_xticks(seed_x, [row["seed"] for row in central_runs])
    seed_ax.set_xlabel("random seed (central reference model)")
    seed_ax.set_ylabel(r"correction to add, $\Delta\alpha_{\rm IMF-PDMF}$")
    seed_ax.set_title("Central model: seed repeatability")
    seed_ax.set_ylim(-0.01, 0.50)
    seed_ax.legend(frameon=False, loc="lower right")
    seed_ax.text(0.03, 0.96, f"SD = {np.std(central_values, ddof=1):.4f}\n3 runs",
                 transform=seed_ax.transAxes, va="top", ha="left", fontsize=10)

    ordered = sorted(all_runs, key=lambda row: (int(row["priority"]), row["run_id"]))
    grid_x = np.arange(len(ordered))
    colors = ["#1f6feb" if int(row["priority"]) == 1 else "#8250df" for row in ordered]
    grid_ax.axhspan(q16, q84, color="#8250df", alpha=0.14,
                    label=f"16–84% = {q16:+.4f} to {q84:+.4f}")
    grid_ax.axhline(median, color="#8250df", lw=1.8, ls="--",
                    label=f"all-grid median = {median:+.4f}")
    grid_ax.scatter(grid_x, [correction(row) for row in ordered], color=colors, s=62, zorder=3)
    grid_ax.set_xticks(grid_x, [short_label(row["run_id"]) for row in ordered], rotation=38,
                       ha="right", fontsize=8)
    grid_ax.set_xlabel("screening-grid initial condition")
    grid_ax.set_title("10-run initial-condition sensitivity")
    grid_ax.set_ylim(-0.01, 0.50)
    grid_ax.legend(frameon=False, loc="upper left", fontsize=9)
    grid_ax.text(0.98, 0.04, "blue: central seeds\npurple: sensitivity runs",
                 transform=grid_ax.transAxes, va="bottom", ha="right", fontsize=8.5)

    for axis in (seed_ax, grid_ax):
        axis.grid(axis="y", alpha=0.22, lw=0.7)
        axis.spines[["top", "right"]].set_visible(False)

    fig.suptitle("M45 PeTar N-body screening grid (0–125 Myr; component stars)", y=0.96,
                 fontsize=14)
    fig.text(0.5, 0.055,
             "Use as a dynamical correction scale only: unresolved-system inference, Gaia selection, and Galactic tide are not yet integrated.",
             ha="center", fontsize=9)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
