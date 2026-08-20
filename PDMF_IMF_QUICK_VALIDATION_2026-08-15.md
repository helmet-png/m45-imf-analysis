# PDMF → IMF quick validation — 2026-08-15

## Purpose

Run a short, reproducible verification of the PDMF → IMF analysis tools after
publishing PR #45.  This is a software and analysis-chain check only; it does
not add a new M45 measurement.

## What was run

All checks used the code at commit `d7503c7` and synthetic inputs supplied by
the scripts themselves.

| Tool | Check | Result |
|---|---|---|
| `petar_m45_grid.py` | Validate the formal ten-run M45 PeTar screening grid | Pass: 10 runs, 3 priority-1 seeds, no configuration errors |
| `petar_pdmf_analysis.py` | Analyse a known synthetic initial/final snapshot with 32 projections | Pass: ID matching, artificial-particle filtering, and unknown-state rejection all work |
| `pdmf_system_definition_bridge.py` | Compare component, primary, total-system, and photometric definitions | Pass: all definitions are finite and remain distinct as intended |
| `petar_system_catalog.py` | Preserve components while grouping hierarchical systems | Pass: recursive component accounting works |
| `petar_pdmf_ensemble.py` | Aggregate one synthetic run into the standard uncertainty format | Pass: all five correction terms are exported with the correct sign convention |
| Analysis scripts | Compile the LIMEPY, N-body, PeTar, and definition-bridge scripts | Pass |

## Interpretation

The pipeline is ready to receive formal PeTar snapshots: it can read the
particles safely, separate survival / stellar-evolution / aperture effects,
match the correction to the observational mass definition, and aggregate
multiple runs.  The synthetic numerical values, including a total correction
of `+0.283` in the test, are **not M45 results** and must not be quoted as
such.

## Still required for a scientific result

Run the ten PeTar initial-condition cases to 125 Myr and give their processed
catalogues or snapshots to `petar_pdmf_analysis.py`.  Only then can the
ensemble output become an M45 PDMF → IMF correction with a real uncertainty.
