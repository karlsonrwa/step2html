"""What every suite needs, and used to carry a copy of.

Four suites, four copies of check() and of the FAILURES list, two of the
face walk, and fifteen degrees written out as a float in three places. One
copy here, so a suite says what it checks rather than how.

Each suite is still a process of its own - see run_all.py - so what is
shared is code, not state: FAILURES is per suite by construction.

Nothing here imports OCP at module level. The suites that need no OCCT at
all - the budget search, the progress bar - come through here too, and an
import at the top would drag ninety megabytes into a test of arithmetic.
"""
from __future__ import annotations

import sys
from pathlib import Path

# The project root and this folder, so the pipeline and the fixtures import
# from wherever the suite is started.
TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
for _p in (str(ROOT), str(TESTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ANGULAR = 15 * 3.141592653589793 / 180.0      # the CLI default, in radians
FAILURES: list[str] = []


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}"
          + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def area(shape) -> float:
    """Surface area, as OCCT's own opinion of it."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def run(main, title: str) -> int:
    """Print the title, run the suite, and answer 0 only if nothing failed."""
    print(title)
    main()
    return 1 if FAILURES else 0
