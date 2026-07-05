"""Lightweight operation-level timing for performance investigation.

Emits `[PERF] <label> <ms>` lines on stderr, independent of LOG_LEVEL, so
timings are always visible in the server log. Pure measurement — no behavior
change. Safe to leave in; remove the calls once profiling is done.
"""

import sys
import time
import logging

logger = logging.getLogger("perf")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class Timer:
    """`with Timer("label"):` — logs wall-clock ms for the block (spans awaits)."""

    def __init__(self, label: str):
        self.label = label

    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        ms = (time.perf_counter() - self.t) * 1000
        logger.info("[PERF] %-30s %10.1f ms", self.label, ms)
        return False
