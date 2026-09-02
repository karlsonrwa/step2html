"""The search for a mesh that fits, with no STEP in the room.

The search is the cleverest thing in the pipeline and, until it was carried
out of convert(), the one thing in it with no test at all: it could only be
run through OCCT, on a real file, at seven seconds a build. Here a build is
a power law - which is what a real one nearly is - and the whole suite runs
in a millisecond.
"""
from __future__ import annotations

import sys

from harness import check, run
from step2html.budget import MAX_BUILDS, Outcome, Sample, search


def synthetic(k=100_000, alpha=1.3, hole=None):
    """A build whose size follows k * q**alpha, opening a hole inside *hole*."""
    calls = []

    def build(q):
        calls.append(q)
        holes = 1.0 if hole and hole[0] <= q <= hole[1] else 0.0
        return Sample(quality=q, size=int(k * q ** alpha), holes=holes,
                      label=f"q={q:.3g}", payload=q)
    return build, calls


def main():
    # ---- no budget, or one that the first build already meets ----------- #
    build, calls = synthetic()
    out = search(build, None)
    check(isinstance(out, Outcome) and len(calls) == 1 and out.fitted
          and out.best.quality == 1.0, "no budget is one build, kept as it is")
    # A roomy budget is not "one build": the whole point is to refine while
    # it fits, so the search goes finer, hits the clamp on quality, and stops
    # when the next place to look is one it has seen.
    build, calls = synthetic()
    out = search(build, 10 ** 9)
    check(out.fitted and out.best.quality > 1.0 and out.best.size <= 10 ** 9
          and len(calls) == 2,
          "a roomy budget is spent on a finer mesh, and the clamp ends it",
          f"{len(calls)} build(s), kept q={out.best.quality:.3g}")

    # ---- a budget in reach: it converges, and it stops when close ------- #
    build, calls = synthetic()
    lines = []
    budget = 1_000_000
    out = search(build, budget, log=lines.append)
    check(out.fitted and budget * 0.94 <= out.best.size <= budget,
          "the kept build lands just under the budget",
          f"{out.best.size:,} of {budget:,}")
    check(len(calls) <= 4, "and it takes a handful of builds, not a ladder",
          f"{len(calls)} build(s): {[round(q, 2) for q in calls]}")
    check(all(s.size <= budget for s in out.samples if s is out.best),
          "nothing over the budget is ever kept")
    check(sum("-> " in line and "bytes" in line for line in lines) == len(calls),
          "every build is logged with its size and a verdict", str(lines))

    # ---- a misjudged exponent is corrected by the second sample --------- #
    build, calls = synthetic(alpha=2.0)
    out = search(build, budget)
    check(out.fitted and budget * 0.94 <= out.best.size <= budget
          and len(calls) <= 4,
          "a model steeper than the first guess still converges",
          f"{len(calls)} build(s), kept {out.best.size:,}")

    # ---- a hole is refused as an answer but used for the fit ------------ #
    build, calls = synthetic(hole=(5.0, 6.5))
    lines = []
    out = search(build, budget, log=lines.append)
    holed = [s for s in out.samples if s.holes > 0]
    check(holed and out.best.holes == 0 and out.fitted,
          "a build that opens a hole is never the answer",
          f"refused {[round(s.quality, 2) for s in holed]}, kept q={out.best.quality:.3g}")
    check(any("refused" in line for line in lines),
          "and the log says it was refused for that")

    # ---- nothing fits: the smallest built goes back, and says so -------- #
    build, calls = synthetic()
    lines = []
    out = search(build, 10, log=lines.append)
    check(not out.fitted and out.best.size == min(s.size for s in out.samples),
          "when nothing fits the smallest build is what comes back",
          f"sizes {[s.size for s in out.samples]}, kept {out.best.size}")
    check(any("nothing fitted" in line and "smallest" in line for line in lines),
          "and the warning names it")

    # ---- the limits hold ------------------------------------------------ #
    build, calls = synthetic(alpha=2.0)
    out = search(build, budget, max_builds=2)
    check(len(calls) == 2 and out.fitted and out.best.quality == 1.0,
          "max_builds stops the search with the best so far",
          f"{len(calls)} build(s)")
    for alpha in (0.4, 1.3, 3.5):
        build, calls = synthetic(alpha=alpha)
        search(build, budget)
        check(len(calls) <= MAX_BUILDS, f"never more than {MAX_BUILDS} builds at alpha {alpha}",
              f"{len(calls)}")
    build, calls = synthetic()
    out = search(build, budget)
    check(all(0.15 <= q <= 24.0 for q in calls),
          "every quality asked for is inside the clamp",
          str([round(q, 2) for q in calls]))


if __name__ == "__main__":
    sys.exit(run(main, "the budget search"))
