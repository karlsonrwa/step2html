"""Mesh settings, and repairing what the mesher refuses.

Knows nothing about XCAF: a colour for a patch is asked of a colour_of(face)
callable handed in by the caller (see xcaf.colour_lookup).
"""
from __future__ import annotations

from ._occt import (Bnd_Box, BRep_Tool, BRepBndLib, BRepBuilderAPI_Copy,
                    BRepGProp, BRepMesh_IncrementalMesh, BRepTools,
                    GProp_GProps, ShapeUpgrade_ShapeDivideClosed, TopAbs_FACE,
                    TopExp_Explorer, TopLoc_Location, TopoDS)


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


def faces(shape):
    out = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        out.append(TopoDS.Face_s(exp.Current()))
        exp.Next()
    return out


def empty_faces(shape):
    """Faces the mesher left with no triangles at all, with their areas.

    Areas, not a count: four missing slivers of a millionth of a square
    millimetre and four missing pin tips both read as "4", and only one of
    them is worth telling anyone about.
    """
    out = []
    for face in faces(shape):
        tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
        if tri is not None and tri.NbTriangles():
            continue
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        out.append((face, props.Mass()))
    return out


def meshed_ok(shape, linear, angular):
    """Mesh a candidate patch; -> the shape if every face of it came out."""
    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
    got = faces(shape)
    if not got:
        return None
    for f in got:
        tri = BRep_Tool.Triangulation_s(f, TopLoc_Location())
        if tri is None or tri.NbTriangles() == 0:
            return None
    return shape


def patch_face(face, linear, angular):
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
    ORDER = {1.0: ("divide", "plain")}      # everywhere else: plain, divide

    def attempt(how, lin, ang):
        copy = BRepBuilderAPI_Copy(face).Shape()
        if how == "plain":
            return meshed_ok(copy, lin, ang)
        divide = ShapeUpgrade_ShapeDivideClosed(copy)
        divide.SetNbSplitPoints(1)
        divide.Perform()
        return meshed_ok(divide.Result(), lin, ang)

    for mult in (1.0, 2.0, 4.0, 8.0, 16.0):
        lin = linear * mult
        ang = min(angular * mult, 1.0)
        # The split goes FIRST at the model's own deflection, and only there.
        # A plain copy at those numbers is the one attempt something is known
        # about: the mesher has just refused this very face at exactly them.
        # It is not a proof - a face meshed alone is a different problem from
        # the same face meshed in an assembly, where shared edges constrain it
        # - which is why the attempt is kept rather than dropped. But it is a
        # poor thing to try first, and on a real connector an expensive one:
        # each of the four conical pin tips takes 0.85 s to be refused again
        # and 0.01 s to build once split. Ten refused faces, 3.40 s spent, of
        # which 0.05 s did anything - measured, and the reason repair went
        # from 5.1 s to 1.7 s.
        #
        # Coarser is a different matter: there a plain patch is worth having
        # first, because it keeps the face whole and needs no seam. Two 0.12
        # mm2 planes on the same connector fail at 0.0076 mm and build plain
        # at twice that.
        for how in ORDER.get(mult, ("plain", "divide")):
            got = attempt(how, lin, ang)
            if got is not None:
                return got
    return None


def repair_parts(parts, colour_of, linear, angular, log, tick=None):
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
        empty = empty_faces(shape)
        patches = []
        left = []
        for face, area in empty:
            piece = patch_face(face, linear, angular)
            if piece is None:
                left.append(area)
                continue
            patches.append((piece, colour_of(face) or rgb))
            rescued += 1
        if empty:
            log(f"  {name}: {len(empty)} face(s) the mesher refused, "
                f"{len(empty) - len(left)} patched, {len(left)} left")
        still_bad += left
        out.append((name, rgb, shape, loc, patches))
    tick(len(parts), len(parts), "meshed")
    return out, rescued, still_bad


def mesh_parts(parts, linear, angular, tick=None):
    """Mesh every part as it is and patch nothing: the --no-repair path.

    The same shape of answer as repair_parts, so the caller need not know
    which of the two it got: parts as (name, rgb, shape, loc, patches) with
    every patches list empty, nothing rescued and nothing left over.
    """
    tick = tick or (lambda _d, _t, _w: None)
    out = []
    for index, (name, rgb, shape, loc) in enumerate(parts):
        tick(index, len(parts), "meshing")
        BRepTools.Clean_s(shape)
        BRepMesh_IncrementalMesh(shape, linear, False, angular, True)
        out.append((name, rgb, shape, loc, []))
    tick(len(parts), len(parts), "meshed")
    return out, 0, []
