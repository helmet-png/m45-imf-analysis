#!/usr/bin/env python3
"""Audit Gaia DR3 proper-motion/parallax covariance columns."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from astropy.table import MaskedColumn, Table

ERROR_COLUMNS = ("pmra_error", "pmdec_error", "parallax_error")
CORR_COLUMNS = ("pmra_pmdec_corr", "parallax_pmra_corr", "parallax_pmdec_corr")


def audit(table: Table) -> dict:
    """Return coverage and positive-semidefinite checks for the 3D covariance."""
    missing = [name for name in (*ERROR_COLUMNS, *CORR_COLUMNS)
               if name not in table.colnames]
    report = {"n_rows": len(table), "required_columns": list((*ERROR_COLUMNS, *CORR_COLUMNS)),
              "missing_columns": missing, "usable_rows": 0, "out_of_range_rows": 0,
              "non_psd_rows": 0, "minimum_eigenvalue": None,
              "status": "missing_columns" if missing else "ok"}
    if missing:
        return report
    errors = np.column_stack([
        np.ma.filled(np.asanyarray(table[name], dtype=float), np.nan)
        for name in ERROR_COLUMNS
    ])
    corrs = np.column_stack([
        np.ma.filled(np.asanyarray(table[name], dtype=float), np.nan)
        for name in CORR_COLUMNS
    ])
    finite = np.isfinite(errors).all(axis=1) & np.isfinite(corrs).all(axis=1)
    in_range = (np.abs(corrs) <= 1).all(axis=1)
    usable = finite & (errors > 0).all(axis=1) & in_range
    report["usable_rows"] = int(usable.sum())
    report["out_of_range_rows"] = int((finite & ~in_range).sum())
    if report["out_of_range_rows"]:
        report["status"] = "out_of_range_rows"
    if not usable.any():
        report["status"] = "no_usable_rows"
        return report
    r12, r13, r23 = corrs[usable].T
    matrices = np.empty((usable.sum(), 3, 3), dtype=float)
    matrices[:, 0, 0] = matrices[:, 1, 1] = matrices[:, 2, 2] = 1.0
    matrices[:, 0, 1] = matrices[:, 1, 0] = r12
    matrices[:, 0, 2] = matrices[:, 2, 0] = r13
    matrices[:, 1, 2] = matrices[:, 2, 1] = r23
    minimum = np.linalg.eigvalsh(matrices).min(axis=1)
    report["minimum_eigenvalue"] = float(minimum.min())
    report["non_psd_rows"] = int((minimum < -1e-10).sum())
    if report["non_psd_rows"]:
        report["status"] = "non_psd_rows"
    return report


def self_test() -> None:
    table = Table({"pmra_error": [0.2, 0.2, 0.2], "pmdec_error": [0.3, 0.3, 0.3],
                   "parallax_error": [0.1, 0.1, 0.1],
                   "pmra_pmdec_corr": MaskedColumn([0.1, 1.0, 0.2],
                                                     mask=[False, False, True]),
                   "parallax_pmra_corr": [0.2, 1.0, 0.3],
                   "parallax_pmdec_corr": [0.3, -1.0, 0.4]})
    report = audit(table)
    assert report["usable_rows"] == 1 and report["non_psd_rows"] == 1
    assert report["status"] == "out_of_range_rows"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test: ok")
        return
    if args.input is None:
        parser.error("input is required unless --self-test is used")
    text = json.dumps(audit(Table.read(args.input, format="csv")), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
