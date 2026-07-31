"""The page itself: the payload must survive the trip, and nothing that is
meant to be substituted may reach the browser unsubstituted.

The damage checks matter because the page PROMISES to report damage rather
than draw something untrue. If the checksum is not actually wired up, that
promise is a lie and nobody would notice.
"""
from __future__ import annotations

import base64
import re
import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import step_to_html as S
from fixtures import coloured_assembly

FAILURES = []


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        step = coloured_assembly(Path(tmp) / "fixture.step")
        out = Path(tmp) / "fixture.html"
        S.main([str(step), "-o", str(out), "--max-bytes", "none"])
        page = out.read_text(encoding="utf-8")

        left = re.findall(r"__[A-Z_]+__", page)
        check(not left, "no placeholder reaches the browser", str(left[:4]))
        check("<html lang=\"en\">" in page, "the page declares English")
        check(not re.search(r"[Ѐ-ӿ]", page),
              "no stray non-English text in the page")

        for want in ('name="proj"', 'name="edge"', 'name="theme"',
                     'id="help"', "<dialog"):
            check(want in page, f"the page carries {want}")
        check('value="ortho" checked' in page, "orthographic is the default")
        check('value="on" checked' in page, "edges are on by default")
        check('value="system" checked' in page, "the theme follows the system")
        check("chooseLayout" in page and "body.side" in page,
              "the bar can stand on its end, and something chooses which")
        # The button is fixed to the screen corner, so in the side layout it
        # reaches across the canvas - and the canvas paints over it without
        # this, because #bar comes first in the markup and neither carries a
        # stacking order of its own.
        check("z-index:5" in page, "the help button is lifted above the canvas")
        check("cam.pivot" in page and "setPivot" in page,
              "a click can move the centre of rotation")
        check('id="pivot"' in page and "showMarker" in page,
              "and the centre of rotation is shown where it landed")
        check("cam.rot" in page and "cam.pitch" not in page,
              "orientation is a matrix, so rotation has no stop in it")
        check(page.count('data-view=') == 8 and 'id="cube"' in page,
              "the view cube offers eight standard views")
        # The order of the menu IS the order of the VIEWS array, and a
        # mismatch would silently show the wrong view under the right name.
        order = re.findall(r'data-view="(\d)" role="menuitem">([^<]+)<', page)
        want = [S.TEXT[k] for k in ("view_top", "view_bottom", "view_front",
                                    "view_back", "view_left", "view_right",
                                    "view_iso_top", "view_iso_bottom")]
        check([n for _i, n in order] == want and
              [i for i, _n in order] == list("01234567"),
              "the menu is in the order the views are defined in",
              ", ".join(n for _i, n in order))
        # The scrim is the whole of "a click outside closes the menu and the
        # view does not change": without it the click reaches the canvas and
        # turns the model or moves the centre of rotation.
        check('id="scrim"' in page and "closeMenu" in page,
              "and a click outside is swallowed rather than passed through")
        check('id="axes"' in page and "paintAxes" in page,
              "an axis triad is drawn in the corner")
        check(page.count("line.ax") >= 1 and "corners" in page,
              "and a measurement steps along the axes")
        check("span*4" in page,
              "the pick ray starts in front of the model, not on the "
              "camera plane")

        # ---- the file says what made it ------------------------------- #
        check(f'name="generator" content="step2html {S.__version__}'
              in page, "the head carries a generator tag with the version")
        check(f"step2html {S.__version__}" in page.split("<body")[1],
              "and the version is visible at the foot of the help")
        for row in (S.TEXT["about_source"], S.TEXT["about_mesh"],
                    S.TEXT["about_made"]):
            check(f"<dt>{row}</dt>" in page, f"the help states the {row.lower()}")
        check("fixture.step" in page, "the source STEP is named")
        check(f"<dt>{S.TEXT['about_size']}</dt>" in page and " mm</dd>" in page,
              "and how big it is, in mm")

        # ---- the tools ------------------------------------------------ #
        for want, what in (('id="measure"', "a measure mode"),
                           ('id="png"', "a way to save the view as a picture"),
                           ("location.hash", "the view in the address"),
                           ("keydown", "keyboard shortcuts")):
            check(want in page, f"the page carries {what}")

        # ---- the payload round-trips -------------------------------------- #
        b64 = re.search(r'id="geo">([^<]+)<', page).group(1).strip()
        crc = int(re.search(r"const CRC=(\d+)", page).group(1))
        raw = int(re.search(r"RAW=(\d+)", page).group(1))
        body = zlib.decompress(base64.b64decode(b64), -15)
        magic, ver, nv, ni, nev, nei, nfa = struct.unpack("<4sIIIIII", body[:28])
        check(magic == b"S3DH", "the payload carries its magic", str(magic))
        # The version and the layout are one thing, and this pins them
        # together: a header edited without the reader following it wrote a
        # version 2 file that the page then read as version 3, and the only
        # symptom was a feature that quietly did nothing.
        check(ver == 3, "the payload is the version the page expects", str(ver))
        head = 4 + 6 * 4 + 4 * 4
        check(len(body) == head + nv * 12 + nv * 3 + nv * 3 + ni * 4
              + nev * 12 + nei * 4 + nfa * 4,
              "and every array in it is exactly where the header says")
        starts = struct.unpack(f"<{nfa}I", body[len(body) - nfa * 4:])
        check(nfa > 0 and all(a <= b for a, b in zip(starts, starts[1:]))
              and starts[-1] < ni // 3,
              "the face table ascends and stays inside the triangles",
              f"{nfa} faces, last starts at {starts[-1]} of {ni // 3}")
        check(len(body) == raw, "the recorded length is the real one",
              f"{len(body)} vs {raw}")
        check((zlib.crc32(body) & 0xFFFFFFFF) == crc, "the recorded CRC matches")
        check(nv > 0 and ni > 0 and nei > 0,
              "vertices, triangles and edges are all present",
              f"{nv} verts, {ni // 3} tri, {nei // 2} lines")

        # ---- damage is detectable ----------------------------------------- #
        # Exactly what the page checks before it draws, done here in Python.
        def survives(mangled: str) -> bool:
            try:
                data = zlib.decompress(base64.b64decode(mangled), -15)
            except Exception:
                return False
            return len(data) == raw and (zlib.crc32(data) & 0xFFFFFFFF) == crc

        check(survives(b64), "an untouched payload is accepted")
        mid = len(b64) // 2
        flipped = b64[:mid] + ("A" if b64[mid] != "A" else "B") + b64[mid + 1:]
        check(not survives(flipped), "one changed character is caught")
        check(not survives(b64[:mid] + b64[mid + 1:]),
              "one deleted character is caught")
        check(not survives(b64[:int(len(b64) * 0.9)]),
              "a truncated payload is caught")
        # atob ignores whitespace, so the data is genuinely unchanged: accepting
        # it is right, and this pins that down as intended rather than missed.
        check(survives(b64[:mid] + " " + b64[mid:]),
              "inserted whitespace is accepted, because it changes nothing")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    print("the generated page")
    sys.exit(main())
