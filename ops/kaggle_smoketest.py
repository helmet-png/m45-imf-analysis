# -*- coding: utf-8 -*-
"""Smoke test for kaggle_sync.py's push -> run -> pull round trip.

Kept in English deliberately: Kaggle's own log-capture pipeline corrupts
multi-byte UTF-8 (Chinese) text before it reaches the downloaded log file
(confirmed 2026-08-09 -- neither PYTHONIOENCODING nor LC_ALL/LANG fixed it,
so the bug is on Kaggle's side, not ours). ASCII text is immune since it's
always 1 byte per character. This only affects console narration printed
inside a Kaggle-run script -- files written with e.g. np.savez are binary
and unaffected; pull those back for real results, don't parse the log.
"""
import multiprocessing
import platform
import sys

import numpy as np

print("=== Kaggle environment probe ===")
print(f"Python: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"CPU count: {multiprocessing.cpu_count()}")
print(f"numpy: {np.__version__}")

x = np.random.default_rng(0).normal(0, 1, 1_000_000)
print(f"Random check: mean={x.mean():.4f}, std={x.std():.4f} (expect ~0, 1)")
print("=== Done: push/run/pull mechanism verified ===")
