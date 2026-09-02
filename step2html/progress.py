"""One bar for the whole of a build, phases taking their share of it.

The search may run several builds, and the bar starts again for each - which
is honest: how many builds there will be is not knowable until the sizes
come back. Reporting the phase number alone left the bar still for the tens
of seconds a real board spends inside one of them, which reads as a program
that has stopped; so the long phases tick per face inside themselves, and
the ticks come through here.

Nothing here knows about OCCT, so the arithmetic can be tested in a
millisecond - see tests/test_progress.py.
"""
from __future__ import annotations

# Phases inside ONE build.
PHASES = ("meshing", "tessellating", "edges", "compressing", "writing the page")
# Roughly what each phase costs, so the bar moves at something like a steady
# rate instead of sitting at 25% through the longest part of the job.
WEIGHTS = (0.42, 0.30, 0.16, 0.08, 0.04)
SPAN = 1000                      # the bar's resolution, in steps


class Phaser:
    """Turns (phase, done, total) into one number on a bar SPAN steps long.

    *progress* takes (value, total, label), exactly as far as the current
    build has got. *planned* is the most builds the search may spend; with
    more than one, every label says which build this is, because with a
    size budget the bar honestly starts again for each.
    """

    def __init__(self, progress, planned: int = 1):
        self.progress = progress or (lambda _v, _t, _l: None)
        self.planned = planned
        self.build_no = 0

    def start(self, label: str) -> None:
        """Before any build: the bar at zero, saying what is happening."""
        self.progress(0, SPAN, label)

    def next_build(self) -> int:
        """Another build begins and the bar starts again. -> its number."""
        self.build_no += 1
        return self.build_no

    def phase(self, index: int, done=0, total=1, detail: str = "") -> None:
        base = sum(WEIGHTS[:index])
        value = SPAN * (base + WEIGHTS[index] * min(done / max(total, 1), 1.0))
        label = detail or PHASES[index]
        if self.planned > 1:
            label = f"build {self.build_no} of at most {self.planned} - {label}"
        self.progress(int(value), SPAN, label)

    def tick(self, done, total, what: str) -> None:
        """What the stages call as they go: (done, total, what).

        "meshing", "tessellating" and "edges" are phases 0, 1 and 2, and each
        reports its own name, so the phase index follows the work. Anything
        else - "meshing pin", "meshed" - is a detail inside the first phase.
        """
        index = PHASES.index(what) if what in PHASES else 0
        self.phase(index, done, total,
                   f"{what} {done * 100 // max(total, 1)}%"
                   if what in PHASES else what)

    def done(self) -> None:
        self.progress(SPAN, SPAN, "done")
