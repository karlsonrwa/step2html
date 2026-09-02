"""Run every suite. Exit 0 only if all of them pass.

    python tests/run_all.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

TESTS = Path(__file__).resolve().parent
JOBS = [
    # The two that need no OCCT first: a millisecond each, and a fault in the
    # arithmetic is reported before seven seconds of meshing.
    ("the budget search",        TESTS / "test_budget.py"),
    ("the progress bar",         TESTS / "test_progress.py"),
    ("window geometry",          TESTS / "test_geometry.py"),
    ("colours and geometry",     TESTS / "test_model.py"),
    ("the generated page",       TESTS / "test_page.py"),
    ("repairing a refused face", TESTS / "test_repair.py"),
    ("the window",               TESTS / "test_gui.py"),
    # No OCCT either, but each child is a fresh interpreter, so it is not fast.
    ("the child process",        TESTS / "test_job.py"),
]


def main() -> int:
    started = time.time()
    results = []
    for label, script in JOBS:
        t0 = time.time()
        done = subprocess.run([sys.executable, str(script)],
                              capture_output=True, text=True)
        results.append((label, done.returncode == 0, time.time() - t0))
        print(done.stdout, end="")
        if done.stderr:
            print(done.stderr, end="", file=sys.stderr)

    print()
    for label, ok, took in results:
        print(f"{label:32} {'pass' if ok else 'FAIL':4} {took:5.1f}s")
    passed = sum(1 for _l, ok, _t in results if ok)
    print(f"\n{passed}/{len(results)} passed in {time.time() - started:.0f}s")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
