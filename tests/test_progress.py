"""The bar: one number per tick, never backwards inside a phase, and a label
that says which build this is when there is more than one to say.

Runs without OCCT, in a millisecond.
"""
from __future__ import annotations

import sys

from harness import check, run
from step2html.progress import PHASES, SPAN, WEIGHTS, Phaser


def main():
    check(len(PHASES) == len(WEIGHTS) and abs(sum(WEIGHTS) - 1.0) < 1e-9,
          "every phase has a weight and the weights sum to one",
          f"{len(PHASES)} phases, weights sum {sum(WEIGHTS):.3f}")

    seen = []
    ph = Phaser(lambda v, t, l: seen.append((v, t, l)), planned=3)
    ph.start("reading the STEP")
    check(seen == [(0, SPAN, "reading the STEP")], "the bar starts at zero")

    ph.next_build()
    ph.phase(0)
    ph.tick(1, 4, "meshing")
    ph.tick(4, 4, "meshing")
    ph.phase(1)
    ph.tick(50, 100, "tessellating")
    ph.tick(100, 100, "tessellating")
    ph.tick(3, 10, "edges")
    ph.phase(3)
    ph.phase(4)
    ph.done()
    values = [v for v, _t, _l in seen]
    check(values == sorted(values), "inside one build the bar never goes back",
          str(values))
    check(all(t == SPAN for _v, t, _l in seen), "and it is always SPAN long")
    check(seen[-1] == (SPAN, SPAN, "done"), "and it ends full")
    labels = [l for _v, _t, l in seen[1:-1]]
    check(all(l.startswith("build 1 of at most 3 - ") for l in labels),
          "with several builds planned every label says which this is",
          labels[0] if labels else "")
    check(any(l.endswith("meshing 25%") for l in labels)
          and any(l.endswith("tessellating 50%") for l in labels)
          and any(l.endswith("edges 30%") for l in labels),
          "the long phases say how far they are, in percent")
    check(any(l.endswith("compressing") for l in labels)
          and any(l.endswith("writing the page") for l in labels),
          "the short phases are named")
    check({p for p in PHASES if any(p in l for l in labels)} == set(PHASES),
          "every phase is announced in a build")

    ph.next_build()
    ph.phase(0)
    check(seen[-1][0] == 0 and seen[-1][2].startswith("build 2 of at most 3"),
          "a new build starts the bar again and says so", seen[-1][2])

    # A detail inside the first phase - "meshing pin", "meshed" - is a label
    # of its own, with no percentage bolted on.
    ph.tick(0, 2, "meshing pin")
    check(seen[-1][2].endswith("meshing pin"), "a named part is a label as given")
    ph.tick(2, 2, "meshed")
    # 420, not int(SPAN * WEIGHTS[0]): an expectation computed from the very
    # constant under test agrees with whatever that constant is changed to.
    # Meshing is 42% of a build, and the end of it is 42% of the bar.
    check(seen[-1][0] == 420 and seen[-1][2].endswith("meshed"),
          "and meshed is the whole of the first phase, 42% of the bar",
          str(seen[-1]))

    # A stage that reports more done than it planned - the face count grows
    # while it works - must not push the bar past the end of its own phase.
    over = []
    past = Phaser(lambda v, _t, _l: over.append(v))
    past.next_build()
    past.tick(9, 4, "meshing")
    check(over == [420], "a tick past its own total stops at the end of the phase",
          str(over))

    alone = []
    single = Phaser(lambda v, t, l: alone.append(l), planned=1)
    single.next_build()
    single.phase(0)
    single.tick(1, 2, "edges")
    check(all("build" not in l for l in alone),
          "with one build planned the labels do not count builds", str(alone))

    # check(True, ...) was here, which cannot fail. What is claimed is that
    # the calls go nowhere quietly, so that is what is asked.
    silent = Phaser(None)
    try:
        silent.start("x"); silent.next_build(); silent.phase(2); silent.done()
        quiet = silent.progress(1, SPAN, "x") is None
    except Exception as exc:                      # noqa: BLE001 - the point
        quiet = f"raised {exc!r}"
    check(quiet is True,
          "no progress callback at all is fine: the calls go nowhere quietly",
          str(quiet))


if __name__ == "__main__":
    sys.exit(run(main, "the progress bar"))
