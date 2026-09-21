"""Where the window goes, with no display in the room.

The cases that have actually gone wrong: a monitor to the left of the
primary, whose coordinates are negative and which Tk writes as "+-1920"; a
second monitor since unplugged, whose remembered position would open the
window somewhere invisible; a window closed maximized.
"""
from __future__ import annotations

import sys

from harness import check, run
from step2html.gui.geometry import centred, parse, reachable, virtual_screen


def main():
    check(parse("620x855+526+87") == (620, 855, 526, 87), "a plain geometry parses")
    check(parse("620x855+-1920+87") == (620, 855, -1920, 87),
          "a monitor left of the primary is negative, and written +-1920")
    check(parse("620x855-100+87") is None,
          "a bare minus is an offset from the right edge, not a position")
    check(parse("garbage") is None and parse("") is None and parse("  ") is None,
          "anything else is nothing")

    one = (0, 0, 1920, 1080)
    check(reachable(620, 855, 526, 87, one), "a window on the primary can be seen")
    check(not reachable(620, 855, 2500, 87, one),
          "one on an unplugged monitor to the right cannot")
    check(not reachable(620, 855, -1920, 87, one),
          "nor one on an unplugged monitor to the left")
    two = (-1920, 0, 3840, 1080)
    check(reachable(620, 855, -1920, 87, two), "with that monitor attached it can")
    check(not reachable(620, 855, 100, -50, one),
          "a title bar above every screen cannot be grabbed")
    check(not reachable(620, 855, 1850, 1060, one),
          "a sliver at the edge is not enough to grab")
    check(reachable(620, 855, 1790, 1000, one),
          "but a corner with room for the title bar is")

    check(centred(700, 720, 1920, 1080) == (610, 120),
          "a first run is centred, a little high")
    check(centred(2000, 2000, 1920, 1080) == (0, 0),
          "and never off the top left of a small screen")

    screen = virtual_screen((0, 0, 800, 600))
    check(len(screen) == 4 and all(isinstance(v, int) for v in screen)
          and screen[2] > 0 and screen[3] > 0,
          "the virtual screen is four integers with a size", str(screen))
    # And it is MEASURED where it can be. A fallback nothing could mistake
    # for a screen must not be what comes back on a machine that can be
    # asked: asked only of a plausible fallback, this check passed with the
    # whole Windows query deleted.
    odd = (-1, -1, 1, 1)
    got = virtual_screen(odd)
    if sys.platform == "win32":
        check(got != odd and got[2] >= 640 and got[3] >= 480,
              "on Windows the virtual desktop is measured, not the fallback",
              str(got))
    else:
        check(got == odd, "elsewhere the fallback is the answer, as given",
              str(got))


if __name__ == "__main__":
    sys.exit(run(main, "window geometry"))
