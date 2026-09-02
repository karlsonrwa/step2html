"""One conversion, end to end: convert(Options, log, progress) -> Report.

The CLI and the window both come through here and nowhere else. What is
here is the ORDER of things and the search for a mesh that fits the size
budget; every step of the work itself lives in a module of its own.
"""
from __future__ import annotations

import math
import stat
from dataclasses import dataclass
from pathlib import Path

from . import ConvertError
from .meshing import auto_deflection, mesh_parts, repair_parts
from .meta import today
from .page import build_page
from .payload import pack
from .tessellate import tessellate
from .xcaf import collect_parts, colour_lookup, read_step


@dataclass(frozen=True)
class Options:
    """One conversion, as plain values.

    Frozen and primitive on purpose: the GUI hands this across a process
    boundary, and a widget edited afterwards must not change a build already
    in flight.
    """

    step: str
    out: str = ""                 # "" -> beside the STEP, same stem
    title: str = ""               # "" -> the file's stem
    deflection: str = "auto"      # "auto", or millimetres as text
    angle: float = 15.0
    max_bytes: str = "auto"       # "auto" (the STEP's own size), "none", or a count
    repair: bool = True
    read_only: bool = False


HTML_SUFFIXES = (".html", ".htm")


def html_target(out: str, step: Path) -> Path:
    """Where the page really goes, from what was asked for and the STEP.

    One rule, in one place, because the CLI and the window both come through
    it - a second copy in the window would eventually promise a name the
    pipeline does not write.

    A name typed without an extension gets one. Appended, never substituted:
    with_suffix would turn "board rev.3" into "board rev.html" and throw the
    revision away, so a dot that is not an extension is left where it is and
    "board rev.3.html" comes out. An .htm is already an HTML file and is kept
    as typed. And a path that is an existing FOLDER takes the STEP's own name
    inside it, rather than becoming a file sitting next to that folder.
    """
    typed = str(out).strip()
    if not typed:
        return step.with_suffix(".html")
    p = Path(typed)
    if not p.name or p.is_dir():
        return p / f"{step.stem}.html"
    if p.suffix.lower() in HTML_SUFFIXES:
        return p
    return p.with_name(p.name + ".html")


@dataclass
class Report:
    out: Path
    size: int
    stats: dict
    linear: float
    angle_deg: float
    builds: int
    missing: list          # areas in mm2 of the faces nothing could build


# Phases inside ONE build. The search may run several, and the bar starts
# again for each - which is honest: how many builds there will be is not
# knowable until the sizes come back.
PHASES = ("meshing", "tessellating", "edges", "compressing", "writing the page")


# Roughly what each phase costs, so the bar moves at something like a steady
# rate instead of sitting at 25% through the longest part of the job.
WEIGHTS = (0.42, 0.30, 0.16, 0.08, 0.04)


SPAN = 1000                      # the bar's resolution, in steps


MAX_BUILDS = 6                   # most builds the search may spend


def convert(opts: Options, log=None, progress=None) -> Report:
    """Do the whole job. The CLI and the GUI both come through here.

    *log* takes one line of text. A line opening with "warning:" or "error:"
    is coloured as such by the GUI, and reads the same way in a terminal, so
    put the word in the message rather than inventing a second channel.

    *progress* takes (value, total, label), exactly as far as the current
    build has got.
    """
    log = log or (lambda _m: None)
    progress = progress or (lambda _v, _t, _l: None)

    step = Path(opts.step)
    if not step.is_file():
        raise ConvertError(f"No such file: {step}")
    out = html_target(opts.out, step)
    if opts.out and out != Path(opts.out):
        log(f"Writing {out.name}")
    title = opts.title or step.stem

    def phase(index, build_no, planned, done=0, total=1, detail=""):
        """One bar for the whole of a build, phases taking their share of it.

        Reporting the phase number alone left the bar still for the tens of
        seconds a real board spends inside one of them, which reads as a
        program that has stopped.
        """
        base = sum(WEIGHTS[:index])
        value = SPAN * (base + WEIGHTS[index] * min(done / max(total, 1), 1.0))
        label = detail or PHASES[index]
        if planned > 1:
            label = f"build {build_no} of at most {planned} - {label}"
        progress(int(value), SPAN, label)

    progress(0, SPAN, "reading the STEP")
    log(f"Reading {step.name}")
    doc = read_step(step)
    parts, color_tool = collect_parts(doc)
    colour_of = colour_lookup(color_tool)
    if not parts:
        raise ConvertError(f"{step.name} holds no shapes")
    log(f"{len(parts)} part(s)")

    base_angle = opts.angle
    try:
        base_linear = (auto_deflection(parts)
                       if str(opts.deflection).strip().lower() == "auto"
                       else float(opts.deflection))
    except ValueError:
        raise ConvertError(f"Deflection must be a number in mm, or 'auto', "
                           f"not {opts.deflection!r}")

    budget = None
    want = str(opts.max_bytes).strip().lower()
    if want == "auto":
        budget = step.stat().st_size
    elif want not in ("none", "off", "", "0"):
        try:
            budget = int(float(opts.max_bytes))
        except ValueError:
            raise ConvertError(f"The size budget must be a number of bytes, "
                               f"'auto' or 'none', not {opts.max_bytes!r}")
        if budget <= 0:
            raise ConvertError(f"A size budget of {budget} bytes cannot be met")
    planned = MAX_BUILDS if budget else 1
    if budget:
        log(f"Size budget {budget:,} bytes; refining while it fits")

    counter = {"n": 0}

    def one_build(quality):
        """The whole page at a quality multiplier. 1.0 is the plain automatic
        mesh; 2.0 halves both deflections, and so on."""
        counter["n"] += 1
        n = counter["n"]
        lin = max(5.0e-4, base_linear / quality)
        deg = max(0.5, base_angle / quality)
        ang = deg * 3.141592653589793 / 180.0

        def tick(done, total, what):
            # "meshing", "tessellating" and "edges" are phases 0, 1 and 2, and
            # each reports its own name, so the phase index follows the work.
            index = PHASES.index(what) if what in PHASES else 0
            phase(index, n, planned, done, total,
                  f"{what} {done * 100 // max(total, 1)}%"
                  if what in PHASES else what)

        phase(0, n, planned)
        prepared, _rescued, left = (
            repair_parts(parts, colour_of, lin, ang, log, tick=tick)
            if opts.repair else mesh_parts(parts, lin, ang, tick=tick))

        phase(1, n, planned)
        pos, nrm, col, idx, epos, eidx, st = tessellate(
            prepared, colour_of, linear=lin, angular=ang, tick=tick)
        if not pos:
            raise ConvertError(f"{step.name} tessellated to nothing - no faces?")

        phase(3, n, planned)
        data, crc, raw = pack(pos, nrm, col, idx, epos, eidx,
                              st.get("face_starts", ()), st.get("circles", ()))

        phase(4, n, planned)
        # Each build stamps ITS OWN mesh, so whichever one is kept describes
        # itself rather than something the search tried on the way.
        span = lambda a: max(a) - min(a)
        page = build_page(title, st, data, crc, raw, meta={
            "source": step.name,
            "size": f"{span(pos[0::3]):.4g} × {span(pos[1::3]):.4g} "
                    f"× {span(pos[2::3]):.4g} mm",
            "mesh": f"{lin:.4g} mm / {deg:.3g}°, "
                    + f"{st['triangles']:,}".replace(",", " ")
                    + " triangles",
            "made": today(),
        })
        return page, {"bytes": len(page.encode("utf-8")), "stats": st,
                      "left": left, "lin": lin, "deg": deg}

    # How the search works, and why it is not a ladder.
    #
    # Size against quality is close to a power law - halve both deflections
    # and the payload grows by a fixed factor - so two measurements are
    # enough to know the exponent for THIS model, and the third build can go
    # more or less straight to the budget. A fixed ladder of 1.6 with a
    # bisection after it took seven builds on a real connector where this
    # takes four, and the builds are the whole of the cost.
    #
    # What is NOT predicted is the answer. Every setting that gets kept has
    # been built and weighed; the fit only chooses where to look next, never
    # what to accept. That distinction is the reason this converges at all:
    # how well the payload deflates depends on the model, and no formula
    # knows it.
    #
    # Holes do not follow the curve, or anything else. On a real connector
    # the mesher builds every face at 0.0194 mm, fails on two planes of
    # 0.12 mm2 at 0.0076, and succeeds again finer still. A sample that opens
    # one still tells us about size, so it is kept for the fit and refused as
    # an answer.
    TARGET = 0.97               # aim just under the budget, not exactly at it
    CLOSE_ENOUGH = 0.94         # within this share of it, stop spending builds

    page, rep = one_build(1.0)
    samples = [(1.0, rep["bytes"])]
    floor = sum(rep["left"]) + 1.0e-4
    best = (page, rep, 1.0) if not budget or rep["bytes"] <= budget else None
    # The smallest thing built so far, for the case where nothing fits. It
    # was the FIRST build that went out in that case - page and rep are never
    # reassigned by the loop - while the log claimed the smallest.
    smallest = (page, rep, 1.0)

    def note(r, verdict):
        log(f"  {r['lin']:.4g} mm / {r['deg']:.3g} deg -> "
            f"{r['bytes']:,} bytes, {verdict}")

    def predict():
        """Where to look next, from the samples in hand."""
        target = budget * TARGET
        (q0, s0) = samples[-1]
        if len(samples) >= 2:
            # Exponent from the two most spread-out samples, for the longest
            # baseline and so the least noise.
            (qa, sa), (qb, sb) = min(samples), max(samples)
            if qb > qa and sb > sa > 0:
                alpha = math.log(sb / sa) / math.log(qb / qa)
            else:
                alpha = 1.3
        else:
            alpha = 1.3         # a plausible first guess; corrected at once
        alpha = max(0.3, min(4.0, alpha))
        return q0 * (target / max(s0, 1)) ** (1.0 / alpha)

    if budget:
        note(rep, "kept" if rep["bytes"] <= budget else "over budget")
        while counter["n"] < MAX_BUILDS:
            if best is not None and best[1]["bytes"] >= budget * CLOSE_ENOUGH:
                break
            q = predict()
            q = max(0.15, min(24.0, q))
            if any(abs(math.log(q / seen)) < 0.03 for seen, _ in samples):
                break           # nowhere new left to look
            trial, trep = one_build(q)
            samples.append((q, trep["bytes"]))
            if trep["bytes"] < smallest[1]["bytes"]:
                smallest = (trial, trep, q)
            if trep["bytes"] > budget:
                note(trep, "over budget")
            elif sum(trep["left"]) > floor:
                note(trep, "fits, but opens a hole - refused")
            elif best is None or trep["bytes"] > best[1]["bytes"]:
                note(trep, "kept")
                best = (trial, trep, q)
            else:
                note(trep, "no better")

    if best is None:
        # Nothing fitted, not even the coarsest tried. Give back the smallest
        # that was built rather than nothing at all, and say so.
        best = smallest
        log(f"warning: nothing fitted the {budget:,} byte budget; keeping "
            f"the smallest built, {smallest[1]['bytes']:,} bytes")

    page, rep, _q = best
    stats, missing = rep["stats"], rep["left"]

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.chmod(out.stat().st_mode | stat.S_IWRITE)   # a previous read-only
    # newline="\n", or Windows writes every line ending as CR LF and the file
    # on disk is one byte per template line - 1,382 of them - larger than the
    # page the budget just weighed. Written the same way everywhere, the size
    # reported is the size chosen.
    out.write_text(page, encoding="utf-8", newline="\n")
    if opts.read_only:
        out.chmod(out.stat().st_mode & ~stat.S_IWRITE)
    progress(SPAN, SPAN, "done")

    log(f"Mesh {rep['lin']:.4g} mm / {rep['deg']:.3g} deg"
        + (f", chosen by {counter['n']} build(s)" if budget else ""))
    log(f"{stats['parts']} part(s), {stats['faces']} face(s), "
        f"{stats['vertices']:,} vertices, {stats['triangles']:,} triangles, "
        f"{stats['edges']:,} edge segment(s)")
    if missing:
        big = max(missing)
        if big < 1.0e-3:
            log(f"{len(missing)} face(s) could not be meshed at all; largest "
                f"is {big:.3g} mm2 - too small to see")
        else:
            log(f"warning: {len(missing)} face(s) could not be meshed at all; "
                f"largest is {big:.3g} mm2 - look for a hole there")
    else:
        log("Every face meshed")

    return Report(out=out, size=out.stat().st_size, stats=stats,
                  linear=rep["lin"], angle_deg=rep["deg"],
                  builds=counter["n"], missing=list(missing))
