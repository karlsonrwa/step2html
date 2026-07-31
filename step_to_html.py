"""STEP assembly -> one self-contained interactive HTML file.

    python step_to_html.py board.step
    python step_to_html.py board.step -o board.html --title "Board A0"

Run by hand on a STEP that already exists, so it works on any STEP, not only
on boards. See README.md for what has already been tried and why the code
looks the way it does - several of the obvious simplifications are wrong, and
the reasons are not guessable from the source alone.

No third-party anything: OCP tessellates, the viewer below is plain WebGL2
written out inline. The result opens by double-click in any current browser,
on a phone as well as a desktop, with no Acrobat and no internet.

The geometry travels as one raw-deflated, base64'd block with its length and
CRC32 written beside it. The page checks both BEFORE it draws and reports
damage instead of drawing something untrue - which is the one thing a 3D PDF
cannot do, since a damaged PDF simply fails to open. Measured: a single
changed character anywhere in the payload is always caught, as are a deleted
character and a truncated file. Inserted whitespace is accepted, correctly -
atob() ignores it, so the data has not changed.

Colours are read per FACE, falling back to the part, so boardMode 'layers'
comes out coloured by layer kind the way it does in the STEP.
"""
from __future__ import annotations

import argparse
import base64
import html
import math
import os
import stat
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.GCPnts import GCPnts_TangentialDeflection
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepTools import BRepTools
    from OCP.Quantity import Quantity_Color
    from OCP.ShapeUpgrade import ShapeUpgrade_ShapeDivideClosed
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_Orientation,
                            TopAbs_SOLID)
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedMapOfShape
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_ColorType, XCAFDoc_DocumentTool
except ImportError as exc:  # pragma: no cover - environment problem, not logic
    raise SystemExit(
        f"{exc}\n\nThis needs the same Python that runs stepbuilder - the one "
        f"with OCP installed.\nCheck with:  python -c \"import OCP; print(OCP.__file__)\""
    )

__version__ = "0.2.1"
"""The one place the number lives; pyproject reads it from here.

Semantic, bumped by hand: a patch is a fix, a minor is a new capability or a
change to what the generated file looks like. The commit is stamped beside it
at generation time, because between two files carrying the same number there
can be a dozen commits of repairs, and the hash is what pins the source when
somebody sends a file back with a question.
"""

DEFAULT_RGB = (170, 170, 170)

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_commit = None


def tool_version() -> str:
    """"0.2.0 - f323ec6", or just the number where git cannot answer.

    Asked once per process and remembered: a subprocess per conversion is
    wasteful, and the answer cannot change while we run. A copy of this file
    taken somewhere without a repository still reports its number, which is
    the point of keeping the number in the source rather than deriving it.
    """
    global _commit
    if _commit is None:
        _commit = ""
        try:
            import subprocess
            here = Path(__file__).resolve().parent
            out = subprocess.run(["git", "-C", str(here), "rev-parse",
                                  "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                _commit = out.stdout.strip()
                dirty = subprocess.run(["git", "-C", str(here), "status",
                                        "--porcelain"],
                                       capture_output=True, text=True, timeout=5)
                if dirty.returncode == 0 and dirty.stdout.strip():
                    # Said out loud: a file built from an edited tree cannot be
                    # reproduced from the commit it names.
                    _commit += "+edits"
        except Exception:
            _commit = ""
    return f"{__version__} · {_commit}" if _commit else __version__


def today() -> str:
    """A date the page can show in any locale. strftime("%b") would print a
    Russian month on a Russian Windows, in the middle of an English page."""
    from datetime import date
    d = date.today()
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"

# Everything the page says, in one place. Change the language here.
TEXT = {
    "stats": "{parts} parts · {faces} faces · {triangles} triangles",
    "old_browser": "This browser is too old: no DecompressionStream. "
                   "Needs Chrome/Edge 80+, Firefox 113+ or Safari 16.4+.",
    "no_webgl": "WebGL2 is not available in this browser.",
    "unpack_failed": "Damaged file: the model data could not be decompressed. "
                     "Get an undamaged copy.",
    "crc_failed": "Damaged file: the model checksum does not match. Nothing is "
                  "drawn, rather than drawing something untrue. Get an "
                  "undamaged copy.",
    "projection": "Projection",
    "perspective": "Perspective",
    "orthographic": "Orthographic",
    "edges": "Edges",
    "on": "On",
    "off": "Off",
    "theme": "Theme",
    "system": "System",
    "light": "Light",
    "dark": "Dark",
    "help": "Help",
    "help_title": "Controls",
    "k_rotate": "Left button, or one finger",
    "v_rotate": "Rotate",
    "k_zoom": "Wheel, or pinch",
    "v_zoom": "Zoom",
    "k_pan": "Right button, Shift-drag, or two fingers",
    "v_pan": "Pan",
    "k_click": "Single click on the model",
    "v_click": "Turn about that point from now on",
    "k_reset": "Double click",
    "v_reset": "Reset the view and the centre of rotation",
    "close": "Close",
    "about_source": "Source",
    "about_mesh": "Mesh",
    "about_made": "Made",
}


# --------------------------------------------------------------------------- #
# reading the STEP
# --------------------------------------------------------------------------- #

def read_step(path: Path):
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    app.NewDocument(TCollection_ExtendedString("MDTV-XCAF"), doc)

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise SystemExit(f"could not read {path}")
    if not reader.Transfer(doc):
        raise SystemExit(f"could not transfer {path}")
    return doc


def label_name(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _srgb_byte(v: float) -> int:
    """OCCT hands back LINEAR components. Encode to sRGB so the byte matches
    the #RRGGBB the user typed into simple3d_config.json - read raw, #B87333
    copper arrives as (122, 44, 8). The shader linearises again before
    lighting."""
    s = 12.92 * v if v <= 0.0031308 else 1.055 * (v ** (1 / 2.4)) - 0.055
    return max(0, min(255, round(s * 255)))


def get_color(color_tool, shape, fallback):
    """Colour of a SHAPE, Surf then Gen, else the fallback.

    By shape, not by label: OCP binds only the TopoDS_Shape overload of
    GetColor, and GetColor_s is the unrelated "this label IS a colour entry"
    call. Passing a label raises TypeError - and an except that swallows it
    paints the whole board grey, which is exactly how this was first written.
    """
    if shape is None or shape.IsNull():
        return fallback
    col = Quantity_Color()
    for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                 XCAFDoc_ColorType.XCAFDoc_ColorGen):
        if color_tool.GetColor(shape, kind, col):
            return tuple(_srgb_byte(v) for v in (col.Red(), col.Green(), col.Blue()))
    return fallback


def collect_parts(doc):
    """[(name, rgb, shape IN ITS OWN FRAME, location to the world)].

    The shape is deliberately NOT moved into place here. XCAF finds a colour
    by the identity of the shape, and a moved copy is a different object: on
    the m_custom test board all 69 faces resolve on the stored shape and NONE
    of them resolve after .Moved(), which paints the whole board one colour -
    board rim and every component alike. So the location travels alongside
    and gets applied to the tessellated points instead.
    """
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    out = []

    def walk(label, loc, inherited, name_hint):
        shape = shape_tool.GetShape_s(label)
        colour = get_color(color_tool, shape, inherited)
        name = label_name(label) or name_hint
        if shape_tool.IsAssembly_s(label):
            comps = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, comps)
            for i in range(1, comps.Length() + 1):
                comp = comps.Value(i)
                sub_loc = loc.Multiplied(shape_tool.GetLocation_s(comp))
                sub_col = instance_color(color_tool, shape_tool, comp, colour)
                ref = TDF_Label()
                if shape_tool.GetReferredShape_s(comp, ref):
                    walk(ref, sub_loc, sub_col, label_name(comp) or name)
                else:
                    walk(comp, sub_loc, sub_col, name)
            return
        if shape is None or shape.IsNull():
            return
        out.append((name, colour, shape, loc))

    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), TopLoc_Location(), DEFAULT_RGB, f"part{i}")
    return out, color_tool


def instance_color(color_tool, shape_tool, comp_label, fallback):
    """Colour set on one PLACEMENT of a shared part, if there is one.

    Same part used twice with two colours is legal in XCAF, and that override
    lives on the component label, not on the part - GetInstanceColor is the
    only way to it.
    """
    shape = shape_tool.GetShape_s(comp_label)
    if shape is None or shape.IsNull():
        return fallback
    col = Quantity_Color()
    for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                 XCAFDoc_ColorType.XCAFDoc_ColorGen):
        try:
            if color_tool.GetInstanceColor(shape, kind, col):
                return tuple(_srgb_byte(v)
                             for v in (col.Red(), col.Green(), col.Blue()))
        except Exception:
            break
    return fallback


# --------------------------------------------------------------------------- #
# mesh settings, and repairing what the mesher refuses
# --------------------------------------------------------------------------- #

def auto_deflection(parts):
    """A linear deflection taken from the size of the model itself.

    A fixed number in mm is the wrong unit for this job: 0.04 is coarse on a
    connector pin and needlessly fine on a 300 mm panel. One part in 2000 of
    the diagonal keeps the error below what a screen can show at any sensible
    zoom, and the clamp keeps a tiny or an enormous model out of the ditch.
    """
    box = Bnd_Box()
    for _n, _c, shape, loc in parts:
        BRepBndLib.Add_s(shape.Moved(loc), box, True)
    if box.IsVoid():
        return 0.04
    x0, y0, z0, x1, y1, z1 = box.Get()
    diag = ((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
    return max(0.004, min(0.25, diag / 2000.0))


def _faces(shape):
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def _mesh_and_count(shape, linear, angular):
    """Mesh from scratch; -> areas of the faces left with no triangles.

    Areas, not a count: four missing slivers of a millionth of a square
    millimetre and four missing pin tips both read as '4' and only one of
    them is worth telling anyone about.
    """
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
    bad = []
    for face in _faces(shape):
        tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        if tri is not None and tri.NbTriangles():
            continue
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        bad.append(props.Mass())
    return bad


def _empty_faces(shape):
    """Faces the mesher left with no triangles at all, with their areas."""
    out = []
    for face in _faces(shape):
        tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        if tri is not None and tri.NbTriangles():
            continue
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        out.append((face, props.Mass()))
    return out


def _meshed_ok(shape, linear, angular):
    """Mesh a candidate patch; -> the shape if every face of it came out."""
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
    faces = _faces(shape)
    if not faces:
        return None
    for f in faces:
        tri = BRep_Tool.Triangulation_s(f, TopLoc_Location())
        if tri is None or tri.NbTriangles() == 0:
            return None
    return shape


def _patch_face(face, linear, angular):
    """Build ONE face the mesher refused, on its own; -> the piece, or None.

    Two levers, and the second is the useful one.

    Splitting removes a bad seam - a closed periodic face parametrised from
    pi to 3*pi rather than 0 to 2*pi, which is what the conical pin tips of a
    real connector turned out to be. It is applied to a COPY of the single
    face: turned loose on the whole solid it slices every closed face there
    is, including the sound cylindrical shafts, which then mesh as two halves
    that do not meet and carry an invented edge down each one.

    And the patch does not have to be built at the model's own deflection.
    That is what breaks the deadlock: refining the mesh makes some faces fail
    that were fine before - two 0.12 mm2 planes on this connector fail at
    0.0076 mm and build at 0.019 - so a face that will not build at the
    chosen setting is simply built coarser. On a plane that is not even a
    visible difference, and a slightly coarse patch beats a hole every time.
    The cost is that the patch is meshed in isolation, so its border need not
    agree edge for edge with its neighbours; at these sizes the seam is far
    below a pixel.
    """
    for mult in (1.0, 2.0, 4.0, 8.0, 16.0):
        lin = linear * mult
        ang = min(angular * mult, 1.0)
        plain = BRepBuilderAPI_Copy(face).Shape()
        got = _meshed_ok(plain, lin, ang)
        if got is not None:
            return got
        divide = ShapeUpgrade_ShapeDivideClosed(BRepBuilderAPI_Copy(face).Shape())
        divide.SetNbSplitPoints(1)
        divide.Perform()
        got = _meshed_ok(divide.Result(), lin, ang)
        if got is not None:
            return got
    return None


def repair_parts(parts, color_tool, linear, angular, log, tick=None):
    """Mesh every part and patch, ONE FACE AT A TIME, whatever came out empty.

    Some faces come out of a real STEP with no triangles at all, and no
    setting reaches them - measured on a connector: four conical pin tips
    stayed empty at 0.04 mm, at 0.01 and at 0.002, a finer mesh made matters
    worse rather than better, and every mesher parameter (MinSize,
    AdjustMinSize, AllowQualityDecrease, Relative, ForceFaceDeflection) left
    all four exactly as they were. BRepCheck calls the faces valid, so
    ShapeFix has nothing to repair either. They are closed periodic faces
    whose seam runs from pi to 3*pi instead of 0 to 2*pi.

    The part itself is never modified: the patch is extra geometry carried
    alongside, so every other face keeps its identity, its colour and its
    edges.

    -> parts as (name, rgb, shape, loc, patches), patches = [(shape, rgb)]
    """
    out = []
    rescued = 0
    still_bad: list[float] = []
    tick = tick or (lambda _d, _t, _w: None)
    for index, (name, rgb, shape, loc) in enumerate(parts):
        tick(index, len(parts), f"meshing {name}")
        BRepTools.Clean_s(shape)
        BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
        empty = _empty_faces(shape)
        patches = []
        left = []
        for face, area in empty:
            piece = _patch_face(face, linear, angular)
            if piece is None:
                left.append(area)
                continue
            patches.append((piece, get_color(color_tool, face, rgb)))
            rescued += 1
        if empty:
            log(f"  {name}: {len(empty)} face(s) the mesher refused, "
                f"{len(empty) - len(left)} patched, {len(left)} left")
        still_bad += left
        out.append((name, rgb, shape, loc, patches))
    tick(len(parts), len(parts), "meshed")
    return out, rescued, still_bad


# --------------------------------------------------------------------------- #
# tessellation
# --------------------------------------------------------------------------- #

def tessellate(parts, color_tool, linear=0.04, angular=0.35, tick=None):
    """-> (positions, normals, colours, indices, stats).

    Normals are averaged per FACE, so a bend comes out smooth and the edge
    between two faces stays sharp.
    """
    pos: list[float] = []
    nrm: list[float] = []
    col: list[int] = []
    idx: list[int] = []
    faces_seen = 0
    tick = tick or (lambda _d, _t, _w: None)
    # Counted up front so the bar means something: a real board is one part
    # with 900 faces, and per-part progress would sit still for the whole of
    # it. Per face it moves.
    total_faces = sum(len(_faces(sh)) + sum(len(_faces(pc)) for pc, _c in pt)
                      for _n, _r, sh, _l, pt in parts) or 1

    for _name, part_rgb, shape, part_loc, patches in parts:
        BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
        place = part_loc.Transformation()
        # A mirrored placement reverses the winding of every triangle in it.
        mirrored = place.IsNegative()
        # The colour of the SOLID each face belongs to, which is a level of
        # the lookup that was missing. XCAF hangs one colour on the solid and
        # lets its faces inherit it, overriding only the ones that differ - a
        # real board arrived with its body colour on the solid and 11 of its
        # 63 faces carrying nothing of their own, so those 11 fell straight
        # past to the default grey. On that board it was 44% of the surface.
        by_solid = TopTools_IndexedMapOfShape()
        solid_rgb = {}
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solid = exp.Current()
            exp.Next()
            rgb = get_color(color_tool, solid, None)
            if rgb is None:
                continue
            for f in _faces(solid):
                solid_rgb[by_solid.Add(f)] = rgb

        # The part's own faces, then any patched face carried beside it.
        jobs = [(f, None) for f in _faces(shape)]
        for piece, patch_rgb in patches:
            jobs += [(f, patch_rgb) for f in _faces(piece)]
        for face, forced in jobs:
            if faces_seen % 25 == 0:
                tick(faces_seen, total_faces, "tessellating")
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                continue
            faces_seen += 1
            # node -> face frame -> part frame -> world, composed once
            trsf = place.Multiplied(loc.Transformation())
            flipped = (face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED)
            if mirrored:
                flipped = not flipped
            # Face, then the solid it belongs to, then the part, then grey.
            # Every step of that chain is one a real file has needed.
            rgb = (forced
                   or get_color(color_tool, face, None)
                   or solid_rgb.get(by_solid.FindIndex(face))
                   or part_rgb)

            base = len(pos) // 3
            px = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                px.append((p.X(), p.Y(), p.Z()))
                pos.extend((p.X(), p.Y(), p.Z()))
                nrm.extend((0.0, 0.0, 0.0))
                col.extend(rgb)

            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if flipped:
                    b, c = c, b
                ax, ay, az = px[a - 1]
                bx, by, bz = px[b - 1]
                cx, cy, cz = px[c - 1]
                ux, uy, uz = bx - ax, by - ay, bz - az
                vx, vy, vz = cx - ax, cy - ay, cz - az
                fx = uy * vz - uz * vy
                fy = uz * vx - ux * vz
                fz = ux * vy - uy * vx
                for k in (a, b, c):
                    o = (base + k - 1) * 3
                    nrm[o] += fx
                    nrm[o + 1] += fy
                    nrm[o + 2] += fz
                idx.extend((base + a - 1, base + b - 1, base + c - 1))

    for i in range(0, len(nrm), 3):
        x, y, z = nrm[i], nrm[i + 1], nrm[i + 2]
        m = (x * x + y * y + z * z) ** 0.5
        if m > 0:
            nrm[i], nrm[i + 1], nrm[i + 2] = x / m, y / m, z / m
        else:
            nrm[i + 2] = 1.0

    epos, eidx, from_mesh, from_curve = collect_edges(
        parts, linear, angular, tick=tick, total=total_faces)

    stats = {
        "parts": len(parts),
        "faces": faces_seen,
        "vertices": len(pos) // 3,
        "triangles": len(idx) // 3,
        "edges": len(eidx) // 2,
        "edges_from_mesh": from_mesh,
        "edges_from_curve": from_curve,
    }
    return pos, nrm, col, idx, epos, eidx, stats


def collect_edges(parts, linear, angular, tick=None, total=1):
    """Real B-rep edges as line segments, taken FROM THE TRIANGULATION.

    Not from the true curve, and that is the whole point. OCCT discretises an
    edge once and hands the same discretisation to both faces that share it -
    that is what keeps the mesh watertight - and stores it per face as a
    Poly_PolygonOnTriangulation: the indices of the triangulation's own nodes
    along that edge. Built from those, a line segment is not merely close to
    the triangle edge it bounds, it IS that edge: same vertices, same straight
    piece between them, identical depth along the whole of it. depthFunc
    LEQUAL then settles the tie in favour of the line.

    Sampling the true curve instead - which is what this did before - puts a
    smooth line over a faceted surface, and the gap between the two is up to
    one deflection of depth. Covering that needs a bias of at least one
    deflection, while a line must stay thinner than a copper layer to avoid
    showing through it. On a real board those two demands crossed: 0.023 mm
    of deflection against 0.018 mm of copper, no value satisfies both. Here
    the question does not arise, because there is no gap to cover.

    The cost is that a curved edge now follows the chords, so on a coarse
    mesh a circle is visibly a polygon. The surface is exactly as coarse, so
    the line finally agrees with the silhouette it is drawn on.
    """
    pos: list[float] = []
    idx: list[int] = []
    from_mesh = from_curve = 0
    tick = tick or (lambda _d, _t, _w: None)
    done = 0

    def emit(points):
        first = len(pos) // 3
        for x, y, z in points:
            pos.extend((x, y, z))
        for k in range(len(points) - 1):
            idx.extend((first + k, first + k + 1))

    for _name, _rgb, shape, part_loc, patches in parts:
        place = part_loc.Transformation()
        for source in [shape] + [piece for piece, _c in patches]:
            seen = TopTools_IndexedMapOfShape()
            for face in _faces(source):
                if done % 25 == 0:
                    tick(done, total, "edges")
                done += 1
                floc = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(face, floc)
                trsf = place.Multiplied(floc.Transformation())
                exp = TopExp_Explorer(face, TopAbs_EDGE)
                while exp.More():
                    edge = TopoDS.Edge_s(exp.Current())
                    exp.Next()
                    if BRep_Tool.Degenerated_s(edge):
                        continue
                    # An edge belongs to two faces; draw it once.
                    if seen.FindIndex(edge):
                        continue

                    poly = (BRep_Tool.PolygonOnTriangulation_s(edge, tri, floc)
                            if tri is not None else None)
                    if poly is not None:
                        nodes = poly.Nodes()
                        if nodes.Length() >= 2:
                            emit([(lambda q: (q.X(), q.Y(), q.Z()))(
                                      tri.Node(nodes.Value(i)).Transformed(trsf))
                                  for i in range(nodes.Lower(), nodes.Upper() + 1)])
                            seen.Add(edge)
                            from_mesh += 1
                            continue

                    # No polygon on this triangulation - a face that would not
                    # mesh, or a free edge. Fall back to the curve itself.
                    try:
                        curve = BRepAdaptor_Curve(edge)
                        disc = GCPnts_TangentialDeflection(curve, angular, linear, 2)
                    except Exception:
                        continue
                    if disc.NbPoints() < 2:
                        continue
                    emit([(lambda q: (q.X(), q.Y(), q.Z()))(
                              curve.Value(disc.Parameter(k)).Transformed(place))
                          for k in range(1, disc.NbPoints() + 1)])
                    seen.Add(edge)
                    from_curve += 1

    return pos, idx, from_mesh, from_curve


# --------------------------------------------------------------------------- #
# payload
# --------------------------------------------------------------------------- #

def pack(pos, nrm, col, idx, epos=(), eidx=()):
    """-> (base64 payload, crc32, uncompressed length)."""
    nv = len(pos) // 3
    ni = len(idx)
    nev = len(epos) // 3
    nei = len(eidx)
    cx = (min(pos[0::3]) + max(pos[0::3])) / 2
    cy = (min(pos[1::3]) + max(pos[1::3])) / 2
    cz = (min(pos[2::3]) + max(pos[2::3])) / 2

    centred = []
    r2 = 0.0
    for i in range(nv):
        x, y, z = pos[3 * i] - cx, pos[3 * i + 1] - cy, pos[3 * i + 2] - cz
        centred.extend((x, y, z))
        r2 = max(r2, x * x + y * y + z * z)
    span = (r2 ** 0.5) or 1.0

    # Edge points ride in the same frame as the surface points.
    ecentred = []
    for i in range(nev):
        ecentred.extend((epos[3 * i] - cx, epos[3 * i + 1] - cy, epos[3 * i + 2] - cz))

    hx = (max(pos[0::3]) - min(pos[0::3])) / 2
    hy = (max(pos[1::3]) - min(pos[1::3])) / 2
    hz = (max(pos[2::3]) - min(pos[2::3])) / 2

    body = bytearray()
    body += struct.pack("<4sIIIIIffff", b"S3DH", 2, nv, ni, nev, nei,
                        span, hx, hy, hz)
    body += struct.pack(f"<{nv * 3}f", *centred)
    body += bytes(max(0, min(255, int(round(v * 127)) + 128)) for v in nrm)
    body += bytes(col)
    body += struct.pack(f"<{ni}I", *idx)
    body += struct.pack(f"<{nev * 3}f", *ecentred)
    body += struct.pack(f"<{nei}I", *eidx)

    crc = zlib.crc32(bytes(body)) & 0xFFFFFFFF
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)   # raw deflate = deflate-raw
    blob = comp.compress(bytes(body)) + comp.flush()
    return base64.b64encode(blob).decode("ascii"), crc, len(body)


# --------------------------------------------------------------------------- #
# the page
# --------------------------------------------------------------------------- #

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="__M_GENERATOR__">
<title>__TITLE__</title>
<style>
  /* color-scheme drives the native radio buttons and the scrollbars, so they
     follow the theme without being restyled. */
  :root{color-scheme:dark;
        --bg:#14171c;--fg:#c8ccd4;--strong:#f0f2f5;--panel:#1a1e25;
        --line:#2c313a;--hover:rgba(255,255,255,.08);
        --press:rgba(255,255,255,.16);--accent:#4d9fff}
  :root.light{color-scheme:light;
        --bg:#eef1f5;--fg:#3a4350;--strong:#11161d;--panel:#fff;
        --line:#d7dde5;--hover:rgba(0,0,0,.06);
        --press:rgba(0,0,0,.12);--accent:#1a73e8}
  html,body{margin:0;background:var(--bg);color:var(--fg);
    font:13px/1.5 "Segoe UI",system-ui,sans-serif;overflow:hidden}
  /* Height off the VIEWPORT, not off a height:100% chain through <html>:
     the chain collapses to zero wherever an ancestor has no height of its
     own, and on a phone 100vh is taller than what you can actually see,
     because it counts the space under the collapsing address bar. dvh is
     the visible height, and 100vh above it is the fallback for old
     browsers that do not know dvh. */
  body{height:100vh;height:100dvh;display:flex;flex-direction:column}
  /* The bar is IN the flow, not over the model: a narrow window makes it
     wrap onto more lines and the canvas gives up the height, instead of the
     controls sitting on top of the board. The right padding is the space the
     help button is absolutely positioned into, so that it stays in the top
     right corner however many lines the rest wraps onto. */
  #bar{position:relative;flex:0 0 auto;display:flex;flex-wrap:wrap;
    align-items:center;gap:6px 22px;padding:8px 48px 8px 14px;
    background:var(--panel);border-bottom:1px solid var(--line)}
  #bar .grp{display:flex;flex-wrap:wrap;align-items:center;gap:2px 8px}
  #bar b{color:var(--strong);font-weight:600}
  #bar .sub{opacity:.6;font-size:12px}
  #bar .cap{opacity:.5;font-size:11px;letter-spacing:.07em;
    text-transform:uppercase}
  #bar label{display:inline-flex;align-items:center;gap:5px;cursor:pointer;
    padding:3px 8px;border-radius:4px;white-space:nowrap;font-size:12px}
  #bar label:hover{background:var(--hover)}
  #bar input[type=radio]{accent-color:var(--accent);margin:0;cursor:pointer}
  #bar label:has(input:disabled){opacity:.4;cursor:default}
  #bar label:has(input:disabled):hover{background:none}
  /* Flat, in the material sense: no fill, no border, the surface only
     answers to hover and press. */
  /* Fixed to the VIEWPORT, so it is in the top right corner of the screen
     whichever side the bar is on. In the side layout that puts it over the
     model, hence the panel-coloured chip - a bare glyph is unreadable
     against arbitrary geometry. */
  /* z-index, or it is invisible in the side layout. #bar comes before #view
     in the markup and neither carries a z-index, so the canvas paints over
     anything of the bar's that reaches across it - and a fixed button in the
     screen's corner does exactly that. getBoundingClientRect() reports the
     button in its place either way, so the geometry looks right while
     nothing is on screen: elementFromPoint is what tells the truth here. */
  #help{position:fixed;top:6px;right:8px;z-index:5;width:32px;height:32px;
    background:var(--panel);
    display:grid;place-items:center;font:inherit;font-size:15px;font-weight:700;
    color:var(--fg);border:0;border-radius:4px;cursor:pointer}
  #help:hover{background:var(--hover)}
  #help:active{background:var(--press)}
  #help:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
  /* The same bar, stood on its end. Which of the two is used is decided by
     measurement, not by a media query - see chooseLayout(). */
  body.side{flex-direction:row}
  /* The column must be only as wide as its widest label. Stretching it, or
     letting it wrap into a second column, makes the side layout wide enough
     to lose every measurement it is put up against. */
  body.side #bar{flex-direction:column;flex-wrap:nowrap;align-items:flex-start;
    gap:12px;padding:10px 14px 12px;overflow-y:auto;overflow-x:hidden;
    max-width:40%;border-bottom:0;border-right:1px solid var(--line)}
  body.side #bar .grp{flex-direction:column;flex-wrap:nowrap;
    align-items:flex-start;gap:1px}
  /* The column is as wide as the widest CONTROL and no wider. width:0 keeps
     the title and the statistics out of the intrinsic width the column is
     sized from, min-width:100% then gives them the whole of it to wrap
     inside. Without this the one-line statistics set the width and the
     column comes out half as wide again. */
  body.side #bar > .grp:first-child{width:0;min-width:100%;
    overflow-wrap:anywhere}
  #view{flex:1 1 auto;min-height:0;min-width:0;position:relative}
  /* The centre of rotation, drawn as an overlay rather than as geometry: it
     is projected to a screen position once per frame, which is a great deal
     less than a second draw call, and CSS animates it for free. */
  #pivot{position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;
    pointer-events:none;opacity:0;transition:opacity .45s ease}
  #pivot.on{opacity:.85;animation:pivotpop .3s ease-out}
  #pivot::before,#pivot::after{content:"";position:absolute;
    background:var(--accent)}
  #pivot::before{left:50%;top:0;width:1px;height:100%;margin-left:-.5px}
  #pivot::after{top:50%;left:0;height:1px;width:100%;margin-top:-.5px}
  #pivot i{position:absolute;inset:6px;border:1.5px solid var(--accent);
    border-radius:50%}
  @keyframes pivotpop{from{transform:scale(2.1);opacity:0}
                      to{transform:scale(1);opacity:.85}}
  canvas{display:block;width:100%;height:100%;touch-action:none}
  dialog{color:var(--fg);background:var(--panel);border:0;border-radius:8px;
    padding:20px 24px;max-width:32em;box-shadow:0 10px 40px rgba(0,0,0,.45)}
  dialog::backdrop{background:rgba(0,0,0,.5)}
  dialog h2{margin:0 0 14px;font-size:14px;color:var(--strong);
    letter-spacing:.04em;text-transform:uppercase}
  dialog dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:7px 18px}
  dialog dt{color:var(--strong)}
  dialog dd{margin:0;opacity:.7}
  dialog hr{border:0;border-top:1px solid var(--line);margin:16px 0 12px}
  dialog .about{font-size:12px;opacity:.75}
  dialog .about dt{color:var(--fg);font-weight:400}
  dialog .made{margin:12px 0 0;font-size:11px;opacity:.5;letter-spacing:.04em}
  dialog .close{display:block;margin:18px 0 0 auto;font:inherit;font-size:12px;
    font-weight:600;letter-spacing:.05em;text-transform:uppercase;
    color:var(--accent);background:none;border:0;border-radius:4px;
    padding:7px 14px;cursor:pointer}
  dialog .close:hover{background:var(--hover)}
  /* Above the button: when this is up, nothing else should be reachable. */
  #err{position:fixed;inset:0;z-index:10;display:none;place-items:center;
    text-align:center;background:var(--bg);padding:40px}
  #err p{max-width:32em;color:#c0392b;font-size:15px}
  :root:not(.light) #err p{color:#ffb4b4}
</style></head><body>
<div id="bar">
<div class="grp"><b>__TITLE__</b><span class="sub">__STATS__</span></div>
<div class="grp"><span class="cap">__L_PROJECTION__</span>
<label><input type="radio" name="proj" value="ortho" checked>__L_ORTHOGRAPHIC__</label>
<label><input type="radio" name="proj" value="persp">__L_PERSPECTIVE__</label></div>
<div class="grp"><span class="cap">__L_EDGES__</span>
<label><input type="radio" name="edge" value="on" checked>__L_ON__</label>
<label><input type="radio" name="edge" value="off">__L_OFF__</label></div>
<div class="grp"><span class="cap">__L_THEME__</span>
<label><input type="radio" name="theme" value="system" checked>__L_SYSTEM__</label>
<label><input type="radio" name="theme" value="light">__L_LIGHT__</label>
<label><input type="radio" name="theme" value="dark">__L_DARK__</label></div>
<button id="help" type="button" title="__L_HELP__" aria-label="__L_HELP__">?</button>
</div>
<div id="view"><canvas id="cv"></canvas>
<div id="pivot"><i></i></div></div>
<dialog id="helpbox">
<h2>__L_HELP_TITLE__</h2>
<dl><dt>__L_K_ROTATE__</dt><dd>__L_V_ROTATE__</dd>
<dt>__L_K_ZOOM__</dt><dd>__L_V_ZOOM__</dd>
<dt>__L_K_PAN__</dt><dd>__L_V_PAN__</dd>
<dt>__L_K_CLICK__</dt><dd>__L_V_CLICK__</dd>
<dt>__L_K_RESET__</dt><dd>__L_V_RESET__</dd></dl>
<hr>
<dl class="about">
<dt>__L_ABOUT_SOURCE__</dt><dd>__M_SOURCE__</dd>
<dt>__L_ABOUT_MESH__</dt><dd>__M_MESH__</dd>
<dt>__L_ABOUT_MADE__</dt><dd>__M_MADE__</dd></dl>
<p class="made">__M_VERSION__</p>
<button class="close" type="button">__L_CLOSE__</button>
</dialog>
<div id="err"><p id="errtext"></p></div>
<script type="text/plain" id="geo">__DATA__</script>
<script>
const CRC=__CRC__, RAW=__RAW__;
const MSG={old:"__OLD_BROWSER__",gl:"__NO_WEBGL__",
           unpack:"__UNPACK_FAILED__",crc:"__CRC_FAILED__"};
const BG={dark:[.078,.090,.110],light:[.933,.945,.961]};
function fail(m){document.getElementById('errtext').textContent=m;
  document.getElementById('err').style.display='grid';
  document.getElementById('cv').style.display='none';
  document.getElementById('hud').style.display='none';}
const T=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;
  for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
function crc32(b){let c=0xFFFFFFFF;for(let i=0;i<b.length;i++)
  c=T[(c^b[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0}

async function boot(){
  let b64=document.getElementById('geo').textContent.trim(), bin;
  try{
    const packed=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
    if(!('DecompressionStream' in window)) return fail(MSG.old);
    const ds=new DecompressionStream('deflate-raw');
    const buf=await new Response(new Blob([packed]).stream().pipeThrough(ds)).arrayBuffer();
    bin=new Uint8Array(buf);
  }catch(e){return fail(MSG.unpack);}
  if(bin.length!==RAW||crc32(bin)!==CRC)
    return fail(MSG.crc+' ('+RAW+' / '+CRC.toString(16)+')');

  const dv=new DataView(bin.buffer);
  const nv=dv.getUint32(8,true), ni=dv.getUint32(12,true),
        nev=dv.getUint32(16,true), nei=dv.getUint32(20,true),
        span=dv.getFloat32(24,true);
  const HX=dv.getFloat32(28,true), HY=dv.getFloat32(32,true), HZ=dv.getFloat32(36,true);
  let o=40;
  const pos=new Float32Array(bin.buffer.slice(o,o+nv*12)); o+=nv*12;
  const nrmB=new Uint8Array(bin.buffer.slice(o,o+nv*3)); o+=nv*3;
  const colB=new Uint8Array(bin.buffer.slice(o,o+nv*3)); o+=nv*3;
  const idx=new Uint32Array(bin.buffer.slice(o,o+ni*4)); o+=ni*4;
  const epos=new Float32Array(bin.buffer.slice(o,o+nev*12)); o+=nev*12;
  const eidx=new Uint32Array(bin.buffer.slice(o,o+nei*4));

  const cv=document.getElementById('cv');
  const gl=cv.getContext('webgl2',{antialias:true});
  if(!gl) return fail(MSG.gl);

  const vs=`#version 300 es
  in vec3 aP; in vec3 aN; in vec3 aC;
  uniform mat4 uMVP, uMV; uniform mat3 uNM;
  out vec3 vN, vC, vP;
  void main(){ vN=uNM*aN; vC=aC; vec4 p=uMV*vec4(aP,1.); vP=p.xyz;
    gl_Position=uMVP*vec4(aP,1.); }`;
  const fs=`#version 300 es
  precision highp float; in vec3 vN,vC,vP; out vec4 o;
  void main(){
    vec3 n=normalize(vN); if(!gl_FrontFacing) n=-n;
    vec3 v=normalize(-vP);
    vec3 base=pow(vC,vec3(2.2));            // the bytes are sRGB; light in linear
    float key=max(dot(n,normalize(vec3(.4,.5,1.))),0.);
    float fill=max(dot(n,normalize(vec3(-.6,-.3,.4))),0.)*.35;
    float head=max(dot(n,v),0.)*.35;
    float rim=pow(1.-max(dot(n,v),0.),3.)*.10;
    vec3 c=base*(.22+key*.85+fill+head)+rim;
    o=vec4(pow(clamp(c,0.,1.),vec3(1./2.2)),1.);}`;
  function sh(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);
    if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(x);return x}
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl.VERTEX_SHADER,vs));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,fs));
  gl.linkProgram(pr);gl.useProgram(pr);

  function buf(target,data,loc,size,type,norm){
    const b=gl.createBuffer();gl.bindBuffer(target,b);gl.bufferData(target,data,gl.STATIC_DRAW);
    if(loc>=0){gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,type,norm,0,0)}}
  const vaSurf=gl.createVertexArray(); gl.bindVertexArray(vaSurf);
  buf(gl.ARRAY_BUFFER,pos,gl.getAttribLocation(pr,'aP'),3,gl.FLOAT,false);
  const nf=new Float32Array(nv*3); for(let i=0;i<nv*3;i++) nf[i]=(nrmB[i]-128)/127;
  buf(gl.ARRAY_BUFFER,nf,gl.getAttribLocation(pr,'aN'),3,gl.FLOAT,false);
  buf(gl.ARRAY_BUFFER,colB,gl.getAttribLocation(pr,'aC'),3,gl.UNSIGNED_BYTE,true);
  buf(gl.ELEMENT_ARRAY_BUFFER,idx,-1,0,0,false);

  // Edges: their own tiny program and their own buffers.
  const epr=gl.createProgram();
  gl.attachShader(epr,sh(gl.VERTEX_SHADER,`#version 300 es
    in vec3 aP; uniform mat4 uMV, uP; uniform float uBias;
    void main(){ vec4 p=uP*uMV*vec4(aP,1.);
      // A line and the triangle edge under it now share their vertices, so
      // there is no geometric gap left to cover and this bias is NOT sized
      // to the model or to the mesh. All it answers is that a line and a
      // triangle are rasterised by different machinery and can disagree by
      // a quantum or two of the depth buffer. Hence a fixed slice of clip
      // depth: 1e-5 of the range is some eighty steps of a 24-bit buffer,
      // far too little to lift a line off the surface it lies on.
      p.z-=uBias*p.w; gl_Position=p; }`));
  gl.attachShader(epr,sh(gl.FRAGMENT_SHADER,`#version 300 es
    precision highp float; uniform vec3 uCol; out vec4 o;
    void main(){ o=vec4(uCol,1.); }`));
  gl.linkProgram(epr);
  const uEMV=gl.getUniformLocation(epr,'uMV'), uEP=gl.getUniformLocation(epr,'uP'),
        uECol=gl.getUniformLocation(epr,'uCol'), uEBias=gl.getUniformLocation(epr,'uBias');
  const vaEdge=gl.createVertexArray(); gl.bindVertexArray(vaEdge);
  gl.useProgram(epr);
  buf(gl.ARRAY_BUFFER,epos,gl.getAttribLocation(epr,'aP'),3,gl.FLOAT,false);
  buf(gl.ELEMENT_ARRAY_BUFFER,eidx,-1,0,0,false);
  gl.bindVertexArray(null);

  gl.enable(gl.DEPTH_TEST);          // clear colour comes from applyTheme()
  // NOTHING is done to the fills. Polygon offset was tried on them twice and
  // is wrong both ways round. With a slope factor it multiplies the maximum
  // depth slope of the polygon, which runs away for a face standing edge-on
  // to the camera - a cylinder's silhouette, an oblique end cap - pushing it
  // behind the far wall of its own solid, so a capacitor rendered as an open
  // tube. Without the slope factor a constant nudge is far too small on
  // exactly those steep faces, and the edge lines break into dashes along
  // the rim of a board seen nearly edge-on. The bias belongs on the lines.
  const EDGE_BIAS=__EDGE_BIAS__;

  const uMVP=gl.getUniformLocation(pr,'uMVP'),uMV=gl.getUniformLocation(pr,'uMV'),
        uNM=gl.getUniformLocation(pr,'uNM');
  const FOV=Math.PI/6;                       // 30 degrees vertical
  // Orientation is a MATRIX, turned by the axes of the screen, not a pair of
  // yaw and pitch angles. Angles have poles: pitch has to be stopped just
  // short of straight down, or crossing it flips the horizon and reverses
  // what a sideways drag does. That stop is what a drag runs into. A matrix
  // turned about the screen's own axes has nowhere to run into - the model
  // rolls on for ever in whichever direction the mouse goes.
  const rotX=a=>{const c=Math.cos(a),s=Math.sin(a);
    return new Float32Array([1,0,0,0, 0,c,s,0, 0,-s,c,0, 0,0,0,1]);};
  const rotY=a=>{const c=Math.cos(a),s=Math.sin(a);
    return new Float32Array([c,0,-s,0, 0,1,0,0, s,0,c,0, 0,0,0,1]);};
  function orthonormalise(m){
    // A rotation multiplied by another a few thousand times in float32 stops
    // being quite a rotation, and the model starts to shear. Gram-Schmidt on
    // the three columns, once per drag, costs nothing and prevents it.
    const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    const norm=v=>{const l=Math.hypot(v[0],v[1],v[2])||1;
                   return [v[0]/l,v[1]/l,v[2]/l];};
    let u=norm([m[0],m[1],m[2]]);
    let v=[m[4],m[5],m[6]];
    const k=dot(v,u);
    v=norm([v[0]-k*u[0], v[1]-k*u[1], v[2]-k*u[2]]);
    const w=[u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
    m[0]=u[0];m[1]=u[1];m[2]=u[2];
    m[4]=v[0];m[5]=v[1];m[6]=v[2];
    m[8]=w[0];m[9]=w[1];m[10]=w[2];
    return m;
  }
  // Distance that just fits the eight bbox corners at this orientation. A
  // bounding-sphere fit leaves a long thin board swimming in empty frame -
  // measured 1.38x too far away on the folded rigid-flex test board.
  function fitDist(rot,aspect){
    const t=Math.tan(FOV/2);
    let d=0;
    for(const sx of[-1,1])for(const sy of[-1,1])for(const sz of[-1,1]){
      const X=sx*HX,Y=sy*HY,Z=sz*HZ;
      const x=rot[0]*X+rot[4]*Y+rot[8]*Z;
      const y=rot[1]*X+rot[5]*Y+rot[9]*Z;
      const z=rot[2]*X+rot[6]*Y+rot[10]*Z;
      d=Math.max(d, Math.abs(x)/(t*aspect)+z, Math.abs(y)/t+z);
    }
    return d*1.04;
  }
  const HOME_ROT=mul(rotX(.95),rotY(-.6));   // the view it opens at
  const HOME={dist:0,px:0,py:0};
  // ||1 on both sides: a canvas that has not been laid out yet reports 0,
  // and 0/0 is NaN, which would put the camera nowhere and draw a blank
  // first frame until the observer fires.
  const home=()=>{
    const d=fitDist(HOME_ROT,
                    Math.max(.2,(cv.clientWidth||1)/(cv.clientHeight||1)));
    // oh is the half-height the ORTHOGRAPHIC view shows, and it is a separate
    // number from the distance on purpose. Moving the centre of the turn onto
    // a picked point changes the distance to it - which leaves a perspective
    // image untouched, but would rescale an orthographic one, since there the
    // distance IS the zoom. Kept apart, a click changes nothing on screen in
    // either projection, and the wheel moves both together so the two stay in
    // step.
    return {...HOME, pivot:[0,0,0], rot:new Float32Array(HOME_ROT),
            dist:d, oh:d*Math.tan(FOV/2)};
  };
  let cam=home(), light=false, lastMV=null;
  const marker=document.getElementById('pivot');
  let markerTimer=null;
  function showMarker(fadeAfter){
    // Restarting a CSS animation needs the class off, a reflow, then on.
    marker.classList.remove('on');
    void marker.offsetWidth;
    marker.classList.add('on');
    clearTimeout(markerTimer);
    if(fadeAfter) markerTimer=setTimeout(()=>marker.classList.remove('on'),
                                         fadeAfter);
  }
  // Orthographic and edges-on are the defaults; the theme follows the
  // system until a radio says otherwise, and goes on following it live.
  let ortho=true, edges=true, themeMode='system';
  const sysDark=matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(){
    light = themeMode==='system' ? !sysDark.matches : themeMode==='light';
    document.documentElement.classList.toggle('light',light);
    const c=light?BG.light:BG.dark;
    gl.clearColor(c[0],c[1],c[2],1);
    draw();
  }
  const on=(name,fn)=>document.querySelectorAll('input[name='+name+']')
      .forEach(r=>r.addEventListener('change',e=>fn(e.target.value)));
  on('proj',  v=>{ortho=(v==='ortho'); draw();});
  on('edge',  v=>{edges=(v==='on');    draw();});
  on('theme', v=>{themeMode=v;         applyTheme();});
  if(sysDark.addEventListener)
    sysDark.addEventListener('change',()=>{if(themeMode==='system')applyTheme();});
  if(!nei) document.querySelectorAll('input[name=edge]')
      .forEach(r=>{r.disabled=true;});
  const helpbox=document.getElementById('helpbox');
  document.getElementById('help').addEventListener('click',()=>helpbox.showModal());
  helpbox.querySelector('.close').addEventListener('click',()=>helpbox.close());
  function mul(a,b){const r=new Float32Array(16);
    for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;
      for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];r[i*4+j]=s}return r}
  function draw(){
    const w=cv.clientWidth,h=cv.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
    cv.width=w*dpr;cv.height=h*dpr;gl.viewport(0,0,cv.width,cv.height);
    gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const a=w/h;
    // Both projections are driven by the SAME cam.dist, and the orthographic
    // half-height is dist*tan(FOV/2) - the size the perspective view has at
    // the centre of rotation. So flipping between them does not jump, and the
    // wheel keeps zooming in either one.
    let P;
    if(ortho){
      const t=cam.oh, r=t*a,
            // Generous, and deliberately so: the pivot may sit on the near
            // face of the model, and the far side must still be inside.
            zn=cam.dist-span*4, zf=cam.dist+span*4;   // zn may go negative: fine
      P=new Float32Array([1/r,0,0,0, 0,1/t,0,0, 0,0,-2/(zf-zn),0,
                          0,0,-(zf+zn)/(zf-zn),1]);
    }else{
      const f=1/Math.tan(.5*FOV),
            zn=Math.max(span*.005,cam.dist-span*1.5), zf=cam.dist+span*1.5;
      P=new Float32Array([f/a,0,0,0, 0,f,0,0, 0,0,(zf+zn)/(zn-zf),-1,
                          0,0,2*zf*zn/(zn-zf),0]);
    }
    const Tv=new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, cam.px,cam.py,-cam.dist,1]);
    // ... and the model shifted so that cam.pivot sits at the centre of the
    // turn. A click puts the pivot on the point under the cursor, which is
    // what makes a big board inspectable: rotation and zoom then work on the
    // detail being looked at rather than on the middle of the whole thing.
    const Tp=new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0,
                               -cam.pivot[0],-cam.pivot[1],-cam.pivot[2],1]);
    const MV=mul(Tv,mul(cam.rot,Tp));
    lastMV=MV;
    const MVP=mul(P,MV);
    const lines=edges&&nei;
    gl.useProgram(pr); gl.bindVertexArray(vaSurf);
    gl.uniformMatrix4fv(uMV,false,MV);
    gl.uniformMatrix4fv(uMVP,false,MVP);
    gl.uniformMatrix3fv(uNM,false,new Float32Array([MV[0],MV[1],MV[2],MV[4],MV[5],MV[6],MV[8],MV[9],MV[10]]));
    gl.drawElements(gl.TRIANGLES,ni,gl.UNSIGNED_INT,0);
    // Where the centre of rotation lands on screen this frame.
    const pv=cam.pivot;
    const pw=MVP[3]*pv[0]+MVP[7]*pv[1]+MVP[11]*pv[2]+MVP[15];
    if(pw>1e-6){
      const px_=(MVP[0]*pv[0]+MVP[4]*pv[1]+MVP[8]*pv[2]+MVP[12])/pw;
      const py_=(MVP[1]*pv[0]+MVP[5]*pv[1]+MVP[9]*pv[2]+MVP[13])/pw;
      marker.style.left=((px_*.5+.5)*w)+'px';
      marker.style.top=((.5-py_*.5)*h)+'px';
    }
    if(lines){
      // LEQUAL as well: a line sampled on the true curve and the chords of
      // the mesh that bounds it are not at identical depth, and ties should
      // go to the line.
      gl.depthFunc(gl.LEQUAL);
      gl.useProgram(epr); gl.bindVertexArray(vaEdge);
      gl.uniformMatrix4fv(uEMV,false,MV);
      gl.uniformMatrix4fv(uEP,false,P);
      gl.uniform3fv(uECol,light?[.10,.13,.17]:[.03,.04,.05]);
      gl.uniform1f(uEBias,EDGE_BIAS);
      gl.drawElements(gl.LINES,nei,gl.UNSIGNED_INT,0);
      gl.depthFunc(gl.LESS);
    }
  }
  // One pointer orbits (or pans with the right button / Shift), TWO pointers
  // pinch to zoom and drag to pan. A phone never sends a wheel event, so
  // without the two-pointer case there is no way to zoom on one at all.
  let touched=false;
  const ptrs=new Map();
  let pinch=null;
  const setDist=v=>{
    const next=Math.max(span*.05,Math.min(span*20,v));
    cam.oh*=next/Math.max(cam.dist,1e-9);      // zoom moves both
    cam.dist=next;
  };
  function twoFinger(){
    const [a,b]=[...ptrs.values()];
    const dx=b.x-a.x, dy=b.y-a.y;
    return {d:Math.hypot(dx,dy)||1, mx:(a.x+b.x)/2, my:(a.y+b.y)/2};
  }
  cv.addEventListener('pointerdown',e=>{
    cv.setPointerCapture(e.pointerId); touched=true;
    ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY,
                          downX:e.clientX,downY:e.clientY,
                          pan:e.button===2||e.shiftKey});
    pinch = ptrs.size===2 ? twoFinger() : null;
    // Held up for the whole of a turn, so it is clear what is being turned
    // about, and not only for the instant of the click that set it.
    if(ptrs.size===1 && !(e.button===2||e.shiftKey)) showMarker(0);
  });
  function release(e){
    ptrs.delete(e.pointerId);
    // Back to one finger: forget the pinch, and the finger that stayed keeps
    // its last position, so the next move is a small delta, not a jump.
    pinch = ptrs.size===2 ? twoFinger() : null;
  }
  // ---- picking the point to turn about ------------------------------- #
  // The depth buffer is not readable from the default framebuffer in WebGL,
  // so the ray is cast against the triangles on the CPU. At a hundred and
  // fifty thousand of them that is a few milliseconds, once per click, and it
  // needs no second render target.
  function toModel(v, isDirection){
    const x=v[0]-(isDirection?0:cam.px),
          y=v[1]-(isDirection?0:cam.py),
          z=v[2]+(isDirection?0:cam.dist);
    // MV is rigid, so its inverse rotation is the transpose: dot with each
    // column of the upper-left 3x3.
    const a=lastMV[0]*x+lastMV[1]*y+lastMV[2]*z,
          b=lastMV[4]*x+lastMV[5]*y+lastMV[6]*z,
          c=lastMV[8]*x+lastMV[9]*y+lastMV[10]*z;
    return isDirection ? [a,b,c]
                       : [a+cam.pivot[0], b+cam.pivot[1], c+cam.pivot[2]];
  }
  function pick(clientX, clientY){
    if(!lastMV) return null;
    const r=cv.getBoundingClientRect();
    const nx=2*(clientX-r.left)/r.width-1, ny=1-2*(clientY-r.top)/r.height;
    const t=Math.tan(FOV/2), a=Math.max(.2,r.width/r.height);
    // The orthographic ray starts on the view plane, and its half-height is
    // cam.oh - the same number the projection uses. Reading it off cam.dist
    // instead was a ray cast at the wrong scale, which picked the wrong
    // triangle and took the clipping planes with it.
    const ov = ortho ? [nx*cam.oh*a, ny*cam.oh, 0] : [0,0,0];
    const dv = ortho ? [0,0,-1] : [nx*t*a, ny*t, -1];
    const o=toModel(ov,false), d=toModel(dv,true);
    let best=Infinity, hit=null;
    for(let i=0;i<ni;i+=3){
      const ia=idx[i]*3, ib=idx[i+1]*3, ic=idx[i+2]*3;
      const e1x=pos[ib]-pos[ia], e1y=pos[ib+1]-pos[ia+1], e1z=pos[ib+2]-pos[ia+2];
      const e2x=pos[ic]-pos[ia], e2y=pos[ic+1]-pos[ia+1], e2z=pos[ic+2]-pos[ia+2];
      const px_=d[1]*e2z-d[2]*e2y, py_=d[2]*e2x-d[0]*e2z, pz_=d[0]*e2y-d[1]*e2x;
      const det=e1x*px_+e1y*py_+e1z*pz_;
      if(det>-1e-12 && det<1e-12) continue;
      const inv=1/det;
      const tx=o[0]-pos[ia], ty=o[1]-pos[ia+1], tz=o[2]-pos[ia+2];
      const u=(tx*px_+ty*py_+tz*pz_)*inv;
      if(u<0||u>1) continue;
      const qx=ty*e1z-tz*e1y, qy=tz*e1x-tx*e1z, qz=tx*e1y-ty*e1x;
      const v=(d[0]*qx+d[1]*qy+d[2]*qz)*inv;
      if(v<0||u+v>1) continue;
      const dist=(e2x*qx+e2y*qy+e2z*qz)*inv;
      if(dist>1e-6 && dist<best){best=dist; hit=[o[0]+d[0]*dist,
                                                o[1]+d[1]*dist,
                                                o[2]+d[2]*dist];}
    }
    return hit;
  }
  function setPivot(p){
    // Move the centre of the turn WITHOUT moving the picture. The picked
    // point keeps the place on screen it already had, because the camera
    // translation is set to exactly where that point sits in view space -
    // and cam.dist becomes the true distance to it, so zoom closes on it too.
    const vx=lastMV[0]*p[0]+lastMV[4]*p[1]+lastMV[8]*p[2]+lastMV[12];
    const vy=lastMV[1]*p[0]+lastMV[5]*p[1]+lastMV[9]*p[2]+lastMV[13];
    const vz=lastMV[2]*p[0]+lastMV[6]*p[1]+lastMV[10]*p[2]+lastMV[14];
    cam.pivot=p; cam.px=vx; cam.py=vy; cam.dist=-vz;
  }
  cv.addEventListener('pointerup',e=>{
    const p=ptrs.get(e.pointerId);
    // A click, not the end of a drag: a turn of four pixels is still a turn,
    // and moving the pivot underneath it would be a surprise.
    if(p && !p.pan && ptrs.size===1 && Math.hypot(e.clientX-p.downX,
                                                  e.clientY-p.downY) < 4){
      const target=pick(e.clientX,e.clientY);
      if(target){ setPivot(target); draw(); showMarker(1200); }
      else showMarker(400);
    } else {
      showMarker(500);
    }
    release(e);
  });
  cv.addEventListener('pointercancel',release);
  cv.addEventListener('pointermove',e=>{
    const p=ptrs.get(e.pointerId); if(!p) return;
    const ox=p.x, oy=p.y; p.x=e.clientX; p.y=e.clientY;
    if(ptrs.size>=2){
      const g=twoFinger();
      if(pinch){
        setDist(cam.dist*pinch.d/g.d);
        cam.px+=(g.mx-pinch.mx)*cam.dist/900;
        cam.py-=(g.my-pinch.my)*cam.dist/900;
      }
      pinch=g; draw(); return;
    }
    const dx=e.clientX-ox, dy=e.clientY-oy;
    if(p.pan){cam.px+=dx*cam.dist/900;cam.py-=dy*cam.dist/900}
    else{
      // Pre-multiplied, so the turn is about the axes of the SCREEN and not
      // about axes carried around by the model. No limit in either direction.
      cam.rot=orthonormalise(mul(mul(rotX(dy*.008),rotY(dx*.008)),cam.rot));
    }
    draw();
  });
  cv.addEventListener('wheel',e=>{e.preventDefault();touched=true;
    setDist(cam.dist*Math.exp(e.deltaY*.0012)); draw()},{passive:false});
  cv.addEventListener('contextmenu',e=>e.preventDefault());
  // Refit on resize, but only until the user has moved the camera themselves.
  cv.addEventListener('dblclick',()=>{touched=false;cam=home();draw()});
  // Put the bar wherever it leaves the SQUAREST view behind.
  //
  // A strip across the top costs height, a strip down the side costs width,
  // and which of those hurts depends on the shape of the window: on a phone
  // held sideways a top bar makes an already wide view wider still. Both are
  // measured for real rather than guessed from an orientation media query,
  // because the thickness of the bar is whatever its contents and wrapping
  // make it, and that is not knowable in advance.
  const bar=document.getElementById('bar'), body=document.body;
  const oblong=(w,h)=>{w=Math.max(w,1);h=Math.max(h,1);return Math.max(w/h,h/w);};
  function chooseLayout(){
    const W=innerWidth, H=innerHeight;
    body.classList.remove('side');
    const top=bar.offsetHeight;
    body.classList.add('side');
    const side=bar.offsetWidth;
    body.classList.toggle('side', oblong(W-side,H) < oblong(W,H-top));
  }
  // Decided twice on purpose: once straight away, and once more in the next
  // animation frame. The immediate pass keeps the page correct even where
  // frames are not being produced at all - an embedded or offscreen view
  // never runs a requestAnimationFrame callback, and a layout that waited
  // for one would simply never happen. The second pass re-measures after the
  // browser has settled, which is what catches a measurement taken mid-flight
  // during a resize.
  const settle=()=>{chooseLayout();if(!touched)cam=home();draw();};
  let pending=false;
  const relayout=()=>{
    settle();
    if(pending) return;
    pending=true;
    requestAnimationFrame(()=>{pending=false;settle();});
  };
  // Two ways in, on purpose. A window resize is what a rotation or a dragged
  // window actually is; the observer catches the rest, such as the visible
  // height changing under a phone's address bar without a resize event.
  //
  // The observer is KEPT IN A VARIABLE and referenced again below. Written as
  // new ResizeObserver(...).observe(x) it has no strong reference left, and
  // it stops firing whenever the collector decides to take it - which is what
  // this did at first, silently: the layout was chosen once at load and never
  // again, and every redraw that made it look alive was coming from somewhere
  // else.
  //
  // The BODY is what is watched, never the view: the view is what this
  // resizes, and an observer on it would answer its own change for ever.
  addEventListener('resize',relayout);
  const ro=new ResizeObserver(relayout);
  ro.observe(body);
  addEventListener('pagehide',()=>ro.disconnect());
  chooseLayout();
  applyTheme();                      // sets the clear colour and draws
}
boot();
</script></body></html>
"""


def build_page(title: str, stats: dict, data: str, crc: int, raw: int,
               edge_bias: float = 1.0e-5, meta: dict | None = None) -> str:
    meta = meta or {}
    stat_line = TEXT["stats"].format(
        parts=stats["parts"], faces=stats["faces"],
        triangles=f"{stats['triangles']:,}".replace(",", "\u00a0"),
    )
    # Every substitution is escaped: a title with & or < in it would otherwise
    # break the page, and the message strings sit inside JS string literals.
    subs = {
        "__TITLE__": html.escape(title),
        "__STATS__": html.escape(stat_line),
        "__OLD_BROWSER__": _js(TEXT["old_browser"]),
        "__NO_WEBGL__": _js(TEXT["no_webgl"]),
        "__UNPACK_FAILED__": _js(TEXT["unpack_failed"]),
        "__CRC_FAILED__": _js(TEXT["crc_failed"]),
        "__CRC__": str(crc),
        "__RAW__": str(raw),
        "__EDGE_BIAS__": repr(round(edge_bias, 8)),
        "__M_GENERATOR__": html.escape(f"step2html {tool_version()}"),
        "__M_VERSION__": html.escape(f"step2html {tool_version()}"),
        "__M_SOURCE__": html.escape(meta.get("source", "")),
        "__M_MESH__": html.escape(meta.get("mesh", "")),
        "__M_MADE__": html.escape(meta.get("made", "")),
        "__L_PROJECTION__": html.escape(TEXT["projection"]),
        "__L_PERSPECTIVE__": html.escape(TEXT["perspective"]),
        "__L_ORTHOGRAPHIC__": html.escape(TEXT["orthographic"]),
        "__L_EDGES__": html.escape(TEXT["edges"]),
        "__L_ON__": html.escape(TEXT["on"]),
        "__L_OFF__": html.escape(TEXT["off"]),
        "__L_THEME__": html.escape(TEXT["theme"]),
        "__L_SYSTEM__": html.escape(TEXT["system"]),
        "__L_LIGHT__": html.escape(TEXT["light"]),
        "__L_DARK__": html.escape(TEXT["dark"]),
        "__L_HELP__": html.escape(TEXT["help"]),
        "__L_HELP_TITLE__": html.escape(TEXT["help_title"]),
        "__L_K_ROTATE__": html.escape(TEXT["k_rotate"]),
        "__L_V_ROTATE__": html.escape(TEXT["v_rotate"]),
        "__L_K_ZOOM__": html.escape(TEXT["k_zoom"]),
        "__L_V_ZOOM__": html.escape(TEXT["v_zoom"]),
        "__L_K_PAN__": html.escape(TEXT["k_pan"]),
        "__L_V_PAN__": html.escape(TEXT["v_pan"]),
        "__L_K_CLICK__": html.escape(TEXT["k_click"]),
        "__L_V_CLICK__": html.escape(TEXT["v_click"]),
        "__L_K_RESET__": html.escape(TEXT["k_reset"]),
        "__L_V_RESET__": html.escape(TEXT["v_reset"]),
        "__L_CLOSE__": html.escape(TEXT["close"]),
        "__L_ABOUT_SOURCE__": html.escape(TEXT["about_source"]),
        "__L_ABOUT_MESH__": html.escape(TEXT["about_mesh"]),
        "__L_ABOUT_MADE__": html.escape(TEXT["about_made"]),
        "__DATA__": data,          # base64 cannot contain < or &
    }
    page = PAGE
    for key, value in subs.items():
        page = page.replace(key, value)
    return page


def _js(s: str) -> str:
    """Escape for a double-quoted JS string literal inside <script>."""
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("<", "\\x3c").replace("\n", "\\n"))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

class ConvertError(Exception):
    """Anything that makes a conversion impossible, said in one sentence."""


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
    out = Path(opts.out) if opts.out else step.with_suffix(".html")
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
        if not opts.repair:
            prepared = [(nm, c, sh, l, []) for nm, c, sh, l in parts]
            for i, (_nm, _c, sh, _l, _p) in enumerate(prepared):
                phase(0, n, planned, i, len(prepared), "meshing")
                BRepTools.Clean_s(sh)
                BRepMesh_IncrementalMesh(sh, lin, False, ang, True)
            left = []
        else:
            prepared, _rescued, left = repair_parts(
                parts, color_tool, lin, ang, log, tick=tick)

        phase(1, n, planned)
        pos, nrm, col, idx, epos, eidx, st = tessellate(
            prepared, color_tool, linear=lin, angular=ang, tick=tick)
        if not pos:
            raise ConvertError(f"{step.name} tessellated to nothing - no faces?")

        phase(3, n, planned)
        data, crc, raw = pack(pos, nrm, col, idx, epos, eidx)

        phase(4, n, planned)
        # Each build stamps ITS OWN mesh, so whichever one is kept describes
        # itself rather than something the search tried on the way.
        page = build_page(title, st, data, crc, raw, meta={
            "source": step.name,
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
        best = (page, rep, 1.0)
        log(f"warning: nothing fitted the {budget:,} byte budget; keeping "
            f"{rep['bytes']:,} bytes")

    page, rep, _q = best
    stats, missing = rep["stats"], rep["left"]

    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.chmod(out.stat().st_mode | stat.S_IWRITE)   # a previous read-only
    out.write_text(page, encoding="utf-8")
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


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Turn a STEP assembly into one self-contained interactive "
                    "HTML file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python step_to_html.py "d:/my board/cad/board.step"
      -> writes d:/my board/cad/board.html beside it

  python step_to_html.py board.step -o "//server/share/board A0.html" \\
         --title "Board A0, rev 3" --read-only

  python step_to_html.py board.step --max-bytes none
      -> one build at the automatic mesh, instead of searching for the finest
         mesh that still fits inside the size of the STEP

  python gui.py
      -> the same thing with a window around it
""")
    ap.add_argument("step", type=Path, help="the STEP file to convert")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="output .html (default: beside the STEP, same name)")
    ap.add_argument("--title", default=None,
                    help="heading shown on the page (default: the file name)")
    ap.add_argument("--deflection", default="auto", metavar="MM",
                    help="linear mesh deflection in mm, or 'auto' (the default) "
                         "to scale it to the size of the model")
    ap.add_argument("--angle", type=float, default=15.0, metavar="DEG",
                    help="angular mesh deflection in degrees (default 15)")
    ap.add_argument("--max-bytes", default="auto", metavar="N",
                    help="size budget for the .html: 'auto' (the default) means "
                         "the size of the STEP itself, 'none' lifts it. The mesh "
                         "is refined as far as the budget allows.")
    ap.add_argument("--no-repair", action="store_true",
                    help="do not try to rescue faces the mesher leaves empty")
    ap.add_argument("--read-only", action="store_true",
                    help="set the read-only attribute on the result, so Notepad "
                         "and friends refuse to save over it")
    args = ap.parse_args(argv)

    opts = Options(
        step=str(args.step),
        out=str(args.out) if args.out else "",
        title=args.title or "",
        deflection=str(args.deflection),
        angle=args.angle,
        max_bytes=str(args.max_bytes),
        repair=not args.no_repair,
        read_only=args.read_only,
    )
    try:
        report = convert(opts, log=print)
    except ConvertError as exc:
        raise SystemExit(str(exc))

    source = Path(opts.step).stat().st_size
    share = f" ({100.0 * report.size / source:.0f}% of the STEP)" if source else ""
    print(f"{report.out}: {report.size:,} bytes HTML{share}"
          f"{' (read-only)' if opts.read_only else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
