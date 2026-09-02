"""Where the window goes: the virtual screen, a remembered place, and
whether that place can still be seen.

Pure functions over numbers, with the screen handed in, so the cases that
matter - a monitor to the left of the primary, a second monitor that has
been unplugged, a title bar above every screen - can be tested without a
display at all (tests/test_geometry.py).
"""
from __future__ import annotations

import re

FIRST_RUN_SIZE = (700, 720)

# Tk writes a negative coordinate as "+-1920", so the sign sits after the
# plus. A bare "-1920" means something else entirely - an offset from the
# right edge - hence the "+" form only.
_GEOMETRY = re.compile(r"^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$")


def virtual_screen(fallback):
    """(x, y, w, h) covering EVERY monitor, not just the primary one.

    Tk's winfo_screenwidth/height describe the primary display only, so a
    window legitimately sitting on a second monitor looks off-screen by
    those numbers - which is exactly the case this exists for. Windows
    reports the whole virtual desktop through GetSystemMetrics, and a
    monitor left of the primary gives a negative origin. *fallback* is the
    answer everywhere Windows cannot be asked: the primary display, as the
    caller sees it.
    """
    try:
        import ctypes
        metrics = ctypes.windll.user32.GetSystemMetrics
        x, y, w, h = (metrics(i) for i in (76, 77, 78, 79))
        if w > 0 and h > 0:
            return x, y, w, h
    except Exception:
        pass
    return fallback


def parse(geometry: str):
    """"620x855+526+87" -> (w, h, x, y); anything else -> None."""
    match = _GEOMETRY.match((geometry or "").strip())
    return tuple(int(g) for g in match.groups()) if match else None


def reachable(w: int, h: int, x: int, y: int, screen) -> bool:
    """Can the window actually be seen and grabbed here?

    The case that matters: it was last closed on a second monitor that is
    no longer attached. Restoring those coordinates puts it somewhere
    invisible with no way to drag it back, which reads as the program
    failing to start.
    """
    vx, vy, vw, vh = screen
    if y < vy:
        return False                       # title bar above every screen
    seen_w = max(0, min(x + w, vx + vw) - max(x, vx))
    seen_h = max(0, min(y + h, vy + vh) - max(y, vy))
    return seen_w >= 120 and seen_h >= 40


def centred(w: int, h: int, screen_w: int, screen_h: int):
    """Where a window of w by h goes on a first run: centred, a little high."""
    return max(0, (screen_w - w) // 2), max(0, (screen_h - h) // 3)
