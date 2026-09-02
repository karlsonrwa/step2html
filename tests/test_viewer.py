"""The pure modules of the viewer, run by node where node exists.

Matrices, the camera, the pick ray, the snap and the view in the address
have no DOM in them, so they can be checked with numbers - see
viewer.test.js. Where there is no node this says so and passes: the checks
are a bonus over test_page, not a gate the suite cannot open.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from harness import check, run

TESTS = Path(__file__).resolve().parent


def main():
    node = shutil.which("node")
    if not node:
        print("  note  node is not on PATH; the viewer's pure modules were "
              "not run")
        return
    done = subprocess.run([node, str(TESTS / "viewer.test.js")],
                          capture_output=True, text=True, encoding="utf-8")
    print(done.stdout, end="")
    tail = (done.stderr.strip().splitlines() or [""])[-1]
    check(done.returncode == 0, "node ran the viewer checks and every one passed",
          tail)


if __name__ == "__main__":
    sys.exit(run(main, "the viewer, in node"))
