"""One conversion, end to end: convert(Options, log, progress) -> Report.

The CLI and the window both come through here and nowhere else. What is
here is the ORDER of things: read the STEP, choose a deflection, let the
search in budget.py ask for builds until one fits, write the one it kept.
Every step of the work itself lives in a module of its own, and one_build
below is the whole of a build, with everything it needs handed to it by
name rather than taken from a closure.
"""
from __future__ import annotations

import math
import stat
from dataclasses import dataclass
from pathlib import Path

from . import ConvertError
from .budget import MAX_BUILDS, Sample, search
from .meshing import auto_deflection, mesh_parts, repair_parts
from .meta import today
from .page import build_page
from .payload import pack
from .progress import Phaser
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


def _budget(opts: Options, step: Path):
    """The size budget in bytes, or None for no limit; ConvertError on nonsense."""
    want = str(opts.max_bytes).strip().lower()
    if want == "auto":
        return step.stat().st_size
    if want in ("none", "off", "", "0"):
        return None
    try:
        budget = int(float(opts.max_bytes))
    except ValueError:
        raise ConvertError(f"The size budget must be a number of bytes, "
                           f"'auto' or 'none', not {opts.max_bytes!r}")
    if budget <= 0:
        raise ConvertError(f"A size budget of {budget} bytes cannot be met")
    return budget


def _deflection(opts: Options, parts) -> float:
    """The linear deflection in mm: the automatic one, or the one asked for."""
    try:
        return (auto_deflection(parts)
                if str(opts.deflection).strip().lower() == "auto"
                else float(opts.deflection))
    except ValueError:
        raise ConvertError(f"Deflection must be a number in mm, or 'auto', "
                           f"not {opts.deflection!r}")


def one_build(quality: float, parts, colour_of, base_linear: float,
              base_angle: float, repair: bool, phaser: Phaser, title: str,
              source: str, log, doc=None, workdir=None) -> Sample:
    """The whole page at a quality multiplier. 1.0 is the plain automatic
    mesh; 2.0 halves both deflections, and so on.

    Everything it needs comes in by name. It used to be a closure over a
    dozen variables of convert(), which is the shape of thing that cannot be
    read on its own, let alone tested. *doc* is the XCAF document the parts
    came from, which lets tessellate take the mesh from OCCT in one piece
    (gltf.py); *workdir* is where that export may be written.
    """
    phaser.next_build()
    lin = max(5.0e-4, base_linear / quality)
    deg = max(0.5, base_angle / quality)
    ang = deg * math.pi / 180.0

    phaser.phase(0)
    prepared, _rescued, left = (
        repair_parts(parts, colour_of, lin, ang, log, tick=phaser.tick)
        if repair else mesh_parts(parts, lin, ang, tick=phaser.tick))

    phaser.phase(1)
    pos, nrm, col, idx, epos, eidx, st = tessellate(
        prepared, colour_of, linear=lin, angular=ang, tick=phaser.tick,
        doc=doc, log=log, workdir=workdir)
    if len(pos) == 0:
        raise ConvertError(f"{source} tessellated to nothing - no faces?")

    phaser.phase(3)
    data, crc, raw = pack(pos, nrm, col, idx, epos, eidx,
                          st.get("face_starts", ()), st.get("circles", ()))

    phaser.phase(4)
    # Each build stamps ITS OWN mesh, so whichever one is kept describes
    # itself rather than something the search tried on the way.
    span = lambda a: max(a) - min(a)
    page = build_page(title, st, data, crc, raw, meta={
        "source": source,
        "size": f"{span(pos[0::3]):.4g} × {span(pos[1::3]):.4g} "
                f"× {span(pos[2::3]):.4g} mm",
        "mesh": f"{lin:.4g} mm / {deg:.3g}°, "
                + f"{st['triangles']:,}".replace(",", " ")
                + " triangles",
        "made": today(),
    })
    return Sample(quality=quality, size=len(page.encode("utf-8")),
                  holes=sum(left), label=f"{lin:.4g} mm / {deg:.3g} deg",
                  payload={"page": page, "stats": st, "left": left,
                           "lin": lin, "deg": deg})


def convert(opts: Options, log=None, progress=None) -> Report:
    """Do the whole job. The CLI and the GUI both come through here.

    *log* takes one line of text. A line opening with "warning:" or "error:"
    is coloured as such by the GUI, and reads the same way in a terminal, so
    put the word in the message rather than inventing a second channel.

    *progress* takes (value, total, label), exactly as far as the current
    build has got.
    """
    log = log or (lambda _m: None)

    step = Path(opts.step)
    if not step.is_file():
        raise ConvertError(f"No such file: {step}")
    out = html_target(opts.out, step)
    if opts.out and out != Path(opts.out):
        log(f"Writing {out.name}")
    title = opts.title or step.stem
    budget = _budget(opts, step)
    phaser = Phaser(progress, MAX_BUILDS if budget else 1)

    phaser.start("reading the STEP")
    log(f"Reading {step.name}")
    doc = read_step(step)
    parts, color_tool = collect_parts(doc)
    colour_of = colour_lookup(color_tool)
    if not parts:
        raise ConvertError(f"{step.name} holds no shapes")
    log(f"{len(parts)} part(s)")
    base_linear = _deflection(opts, parts)
    if budget:
        log(f"Size budget {budget:,} bytes; refining while it fits")

    def build(quality: float) -> Sample:
        return one_build(quality, parts, colour_of, base_linear, opts.angle,
                         opts.repair, phaser, title, step.name, log,
                         doc=doc, workdir=out.parent)

    found = search(build, budget, log=log)
    kept = found.best.payload
    page, stats, missing = kept["page"], kept["stats"], kept["left"]

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
    phaser.done()

    log(f"Mesh {kept['lin']:.4g} mm / {kept['deg']:.3g} deg"
        + (f", chosen by {len(found.samples)} build(s)" if budget else ""))
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
                  linear=kept["lin"], angle_deg=kept["deg"],
                  builds=len(found.samples), missing=list(missing))
