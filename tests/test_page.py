"""The page itself: the payload must survive the trip, and nothing that is
meant to be substituted may reach the browser unsubstituted.

The damage checks matter because the page PROMISES to report damage rather
than draw something untrue. If the checksum is not actually wired up, that
promise is a lie and nobody would notice.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

from harness import check, run
from fixtures import coloured_assembly
from step2html import __version__, cli, payload
from step2html import page as page_module
from step2html.convert import Options, convert
from step2html.page import JS_ORDER, TEXT, build_page


def main():
    with tempfile.TemporaryDirectory() as tmp:
        step = coloured_assembly(Path(tmp) / "fixture.step")
        out = Path(tmp) / "fixture.html"
        # At a FIXED deflection, so the payload below can be compared with the
        # golden one; the automatic figure is checked in test_repair.
        cli.main([str(step), "-o", str(out), "--max-bytes", "none",
                  "--deflection", "0.04", "--angle", "15"])
        page = out.read_text(encoding="utf-8")

        left = re.findall(r"__[A-Z_]+__", page)
        check(not left, "no placeholder reaches the browser", str(left[:4]))
        # A title is user text - a --title, or the STEP's own stem - and text
        # substituted into the template must not then be read AS template.
        # Key by key in a loop it was: a title of "__L_ON__" came out as "On".
        odd = build_page("__L_ON__ rev __L_DARK__",
                         {"parts": 1, "faces": 1, "triangles": 1},
                         "AAAA", 1, 1, meta={"source": "x.step"})
        shown = odd.split("<b>")[1].split("</b>")[0]
        check(shown == "__L_ON__ rev __L_DARK__",
              "substituted text is not scanned again", shown)
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
        want = [TEXT[k] for k in ("view_top", "view_bottom", "view_front",
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
        # A stray newline inside a JS string breaks the WHOLE script, so the
        # page draws nothing at all - and Python happily writes it, because
        # to Python it is just text. One escape lost in transit cost an
        # afternoon; this is the cheap guard against the next one.
        script = page.split("<script>")[-1].split("</script>")[0]
        ragged = []
        for n, line in enumerate(script.splitlines(), 1):
            code = line.split("//")[0]
            code = code.replace("\\'", "").replace('\\"', "")
            if code.count("'") % 2 or code.count('"') % 2:
                ragged.append((n, line.strip()[:60]))
        check(not ragged, "no unbalanced quote in the page's script",
              "; ".join(f"line {n}: {t}" for n, t in ragged[:3]))
        # And, where node is on the machine, a real parser over the SAME
        # script - the one with the values substituted in, not the template.
        # The quote count above catches the one fault that cost an afternoon;
        # this catches every other way a script can fail to parse, with a
        # line number. Skipped, and said so, where there is no node.
        node = shutil.which("node")
        if node:
            script_file = Path(tmp) / "viewer.js"
            script_file.write_text(script, encoding="utf-8")
            done = subprocess.run([node, "--check", str(script_file)],
                                  capture_output=True, text=True)
            said = done.stderr.strip().splitlines()
            check(done.returncode == 0, "node --check accepts the page's script",
                  said[-1] if said else "")
        else:
            print("  note  node is not on PATH; the script was not parsed by "
                  "a real parser")
        # The script is one file per concern under viewer/, concatenated in
        # the order page.py names. Every file there must be named, once, and
        # must land in the page in that order - a file added to the folder
        # and forgotten off the list would simply be missing from every page.
        on_disk = sorted(p.name for p in
                         (Path(page_module.__file__).parent / "viewer").glob("*.js"))
        check(sorted(JS_ORDER) == on_disk and len(set(JS_ORDER)) == len(JS_ORDER),
              "every script file under viewer/ is in the page, once",
              f"on disk {on_disk}, listed {sorted(JS_ORDER)}")
        banners = [page.find("// ==== " + name[:-3] + ":") for name in JS_ORDER]
        check(all(b >= 0 for b in banners) and banners == sorted(banners)
              and page.rstrip().endswith("boot();\n</script></body></html>"),
              "and they arrive in that order, with boot() last",
              str(banners))
        # Every element the script reaches for must exist in the markup.
        # getElementById returns null for one that does not, and the line
        # after it dies - which is how fail(), of all functions, ended up
        # throwing on its last line while still showing its message.
        ids = set(re.findall(r'id="([A-Za-z_0-9]+)"', page))
        wanted = set(re.findall(r"getElementById\('([A-Za-z_0-9]+)'\)", page))
        wanted |= set(re.findall(r"querySelector(?:All)?\('#([A-Za-z_0-9]+)",
                                 page))
        check(not (wanted - ids), "every element the script asks for exists",
              ", ".join(sorted(wanted - ids)))

        for want, what in (("toBlob", "the picture goes out through a blob"),
                           ("createObjectURL", "and a blob URL, not a data one"),
                           ("paintSvgOnto", "overlays are drawn into it")):
            check(want in page, what)

        check("span*4" in page,
              "the pick ray starts in front of the model, not on the "
              "camera plane")
        # An old browser is told so whichever way it is old: no API at all, or
        # an API from before deflate-raw - Chrome 80 to 102 - whose
        # constructor throws. Caught inside the unpacking's own try, that
        # throw read as "damaged file" about a file that was whole.
        check(page.count("{kind:'old'}") == 2 and "MSG.old" in page
              and "103+" in page,
              "an old browser is named as old, not as a damaged file")

        # ---- the measurement snaps, and says so ----------------------- #
        check("snapAt" in page and "rimPath" in page,
              "a measurement can snap to the centre of a circle")
        check("polyline" in page and 'class="rim"' in page,
              "and the rim it caught is shown before the click")
        check("labelAt" in page and "line.lead" in page,
              "the reading parks out of the way, on a lead")

        # The number the pages carry, asked of the tool itself.
        try:
            cli.main(["--version"])
            said = "nothing"
        except SystemExit as exc:
            said = str(exc.code)
        check(said == "0", "--version answers and exits cleanly", said)

        # ---- the file says what made it ------------------------------- #
        check(f'name="generator" content="step2html {__version__}'
              in page, "the head carries a generator tag with the version")
        check(f"step2html {__version__}" in page.split("<body")[1],
              "and the version is visible at the foot of the help")
        for row in (TEXT["about_source"], TEXT["about_mesh"],
                    TEXT["about_made"]):
            check(f"<dt>{row}</dt>" in page, f"the help states the {row.lower()}")
        check("fixture.step" in page, "the source STEP is named")
        check(f"<dt>{TEXT['about_size']}</dt>" in page and " mm</dd>" in page,
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
        body = payload.decode(b64)
        magic, ver, nv, ni, nev, nei, nfa, ncr = struct.unpack(
            "<4sIIIIIII", body[:32])
        # Counted by hand above, on purpose: the Python reader below must
        # agree with a reading that does not go through it.
        mesh = payload.unpack(body)
        check(mesh["counts"] == (nv, ni, nev, nei, nfa, ncr)
              and len(mesh["pos"]) == nv * 3 and len(mesh["idx"]) == ni
              and len(mesh["face_starts"]) == nfa
              and len(mesh["circles"]) == ncr,
              "payload.unpack reads back every array the header names")
        check(magic == b"S3DH", "the payload carries its magic", str(magic))
        # The version and the layout are one thing, and this pins them
        # together: a header edited without the reader following it wrote a
        # version 2 file that the page then read as version 3, and the only
        # symptom was a feature that quietly did nothing.
        check(ver == 4, "the payload is the version the page expects", str(ver))
        head = 4 + 7 * 4 + 4 * 4
        check(len(body) == head + nv * 12 + nv * 3 + nv * 3 + ni * 4
              + nev * 12 + nei * 4 + nfa * 4 + ncr * 28,
              "and every array in it is exactly where the header says")
        # The fixture has a cylinder in it, so it has rims - and each rim must
        # arrive ONCE however many faces and arcs it is cut into, or the snap
        # scans the same circle over and over.
        circles = struct.unpack(f"<{ncr * 7}f", body[len(body) - ncr * 28:])
        centres = {tuple(round(v, 4) for v in circles[i * 7:i * 7 + 7])
                   for i in range(ncr)}
        check(ncr >= 2 and len(centres) == ncr,
              "the circles are there and none of them is a duplicate",
              f"{ncr} circles")
        check(all(circles[i * 7 + 6] > 0 for i in range(ncr)),
              "and every one of them has a radius")
        starts = struct.unpack(f"<{nfa}I",
                              body[len(body) - ncr * 28 - nfa * 4:
                                   len(body) - ncr * 28])
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

        # ---- the golden payload ------------------------------------------- #
        # The same fixture at the same deflection must pack to the same bytes,
        # and this is what proves a MOVE changed nothing: the plan in
        # docs/refactoring-plan.md carries most of the pipeline into other
        # files, and a test that only checks the shapes of things would pass a
        # transposed matrix. Tied to the OCCT that meshed it - a new OCCT may
        # mesh differently, and then the file is regenerated on purpose:
        #     python tests/test_page.py --golden
        golden_path = Path(__file__).resolve().parent / "golden.json"
        got = {"crc": crc, "raw": raw, "counts": [nv, ni, nev, nei, nfa, ncr]}
        if "--golden" in sys.argv or not golden_path.is_file():
            golden_path.write_text(json.dumps(got, indent=2) + "\n",
                                   encoding="utf-8")
            print(f"  note  golden payload written to {golden_path.name}")
        else:
            want = json.loads(golden_path.read_text(encoding="utf-8"))
            check(got == want, "the payload is byte for byte the golden one",
                  "" if got == want else f"got {got}, golden {want}")

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

        # ---- nothing fits: the smallest build goes out -------------------- #
        # With a budget below anything the search can reach, what leaves is
        # the smallest build there was - it used to be the FIRST, while the
        # log claimed otherwise - and its size on disk is the size the log
        # names: written with "\n", not with whatever the platform likes,
        # which on Windows added a byte per template line after the weighing.
        lines = []
        tiny = convert(Options(step=str(step),
                               out=str(Path(tmp) / "tiny.html"),
                               max_bytes="1000"), log=lines.append)
        built = [int(m.group(1).replace(",", ""))
                 for m in (re.search(r"-> ([\d,]+) bytes", l) for l in lines)
                 if m]
        kept = [int(m.group(1).replace(",", ""))
                for m in (re.search(r"keeping the smallest built, ([\d,]+)", l)
                          for l in lines) if m]
        check(len(built) >= 2 and tiny.size == min(built),
              "when nothing fits, the smallest build is the one written",
              f"built {built}, on disk {tiny.size:,}")
        check(kept == [tiny.size], "and the log names the size that is on disk",
              f"log says {kept}, disk says {tiny.size:,}")


if __name__ == "__main__":
    sys.exit(run(main, "the generated page"))
