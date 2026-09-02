"""Finding the finest mesh that still fits a size budget.

How the search works, and why it is not a ladder.

Size against quality is close to a power law - halve both deflections and
the payload grows by a fixed factor - so two measurements are enough to know
the exponent for THIS model, and the third build can go more or less
straight to the budget. A fixed ladder of 1.6 with a bisection after it took
seven builds on a real connector where this takes four, and the builds are
the whole of the cost.

What is NOT predicted is the answer. Every setting that gets kept has been
built and weighed; the fit only chooses where to look next, never what to
accept. That distinction is the reason this converges at all: how well the
payload deflates depends on the model, and no formula knows it.

Holes do not follow the curve, or anything else. On a real connector the
mesher builds every face at 0.0194 mm, fails on two planes of 0.12 mm2 at
0.0076, and succeeds again finer still. A sample that opens one still tells
us about size, so it is kept for the fit and refused as an answer.

Nothing here knows what a build IS. It is handed build(quality) -> Sample
and a budget in bytes, and that is the whole of its world - which is what
lets tests/test_budget.py drive it with a power law and no STEP.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

MAX_BUILDS = 6                   # most builds the search may spend
TARGET = 0.97                    # aim just under the budget, not exactly at it
CLOSE_ENOUGH = 0.94              # within this share of it, stop spending builds
FLOOR_SLACK = 1.0e-4             # a hole this much larger than the first build's, in mm2, counts


@dataclass(frozen=True)
class Sample:
    """One build, weighed."""

    quality: float          # the multiplier it was built at; 1.0 is the plain automatic mesh
    size: int               # bytes of page
    holes: float            # total area in mm2 of the faces nothing could build
    label: str              # how the log names it, "0.0393 mm / 15 deg"
    payload: Any = None     # whatever the caller wants back for the one that is kept


@dataclass
class Outcome:
    best: Sample
    samples: list            # every build made, in the order it was made
    fitted: bool             # False when nothing fitted and best is merely the smallest


def search(build: Callable[[float], Sample], budget: int | None, *,
           first: float = 1.0, max_builds: int = MAX_BUILDS,
           target: float = TARGET, close_enough: float = CLOSE_ENOUGH,
           log=None) -> Outcome:
    """Build at *first*, then look for the largest page under *budget*.

    No budget means one build, kept as it is. Otherwise every build after
    the first is logged with its verdict, and when nothing fits at all the
    smallest thing built goes back - with fitted False and a warning in the
    log - rather than nothing.
    """
    log = log or (lambda _m: None)

    def note(s: Sample, verdict: str) -> None:
        log(f"  {s.label} -> {s.size:,} bytes, {verdict}")

    s = build(first)
    samples = [s]
    if not budget:
        return Outcome(s, samples, True)

    floor = s.holes + FLOOR_SLACK
    best = s if s.size <= budget else None
    smallest = s
    note(s, "kept" if best is not None else "over budget")

    def predict() -> float:
        """Where to look next, from the samples in hand."""
        goal = budget * target
        q0, s0 = samples[-1].quality, samples[-1].size
        if len(samples) >= 2:
            # Exponent from the two most spread-out samples, for the longest
            # baseline and so the least noise.
            a = min(samples, key=lambda x: x.quality)
            b = max(samples, key=lambda x: x.quality)
            if b.quality > a.quality and b.size > a.size > 0:
                alpha = math.log(b.size / a.size) / math.log(b.quality / a.quality)
            else:
                alpha = 1.3
        else:
            alpha = 1.3         # a plausible first guess; corrected at once
        alpha = max(0.3, min(4.0, alpha))
        return q0 * (goal / max(s0, 1)) ** (1.0 / alpha)

    while len(samples) < max_builds:
        if best is not None and best.size >= budget * close_enough:
            break
        q = max(0.15, min(24.0, predict()))
        if any(abs(math.log(q / seen.quality)) < 0.03 for seen in samples):
            break               # nowhere new left to look
        t = build(q)
        samples.append(t)
        if t.size < smallest.size:
            smallest = t
        if t.size > budget:
            note(t, "over budget")
        elif t.holes > floor:
            note(t, "fits, but opens a hole - refused")
        elif best is None or t.size > best.size:
            note(t, "kept")
            best = t
        else:
            note(t, "no better")

    if best is None:
        # Nothing fitted, not even the coarsest tried. Give back the smallest
        # that was built rather than nothing at all, and say so.
        log(f"warning: nothing fitted the {budget:,} byte budget; keeping "
            f"the smallest built, {smallest.size:,} bytes")
        return Outcome(smallest, samples, False)
    return Outcome(best, samples, True)
