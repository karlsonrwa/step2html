"""Triangles, normals and colours from meshed parts; edges from the same
triangulation; circles for a measurement to snap to.

The parts must already be meshed - repair_parts or mesh_parts does that -
and the colour of a shape is asked of colour_of(shape), which answers an
sRGB triple or None (see xcaf.colour_lookup). Nothing here imports XCAF.

Two ways to the same arrays. Given the document, the mesh comes from OCCT
in one piece - gltf.py writes it and numpy reads it - and every face is
checked against the export before its primitive is used: the node count,
the first node's place, the first triangle's winding. A face the check
refuses, a patched face (which is a copy outside the document), or the
whole board when there is no document or the writer declines, is walked
node by node with the same arithmetic. Either way the world coordinates are
one (N, 3) array, and normals, edges and the payload are computed from it.
"""
from __future__ import annotations

import numpy as np

from ._occt import (BRep_Tool, BRepAdaptor_Curve, GCPnts_TangentialDeflection,
                    GeomAbs_CurveType, TopAbs_EDGE, TopAbs_Orientation,
                    TopExp_Explorer, TopLoc_Location, TopoDS,
                    TopTools_IndexedMapOfShape)
from .gltf import export_mesh
from .meshing import faces, solid_colours


def tessellate(parts, colour_of, linear=0.04, angular=0.35, tick=None,
               doc=None, log=None, workdir=None):
    """-> (positions, normals, colours, indices, edge positions, edge
    indices, stats).

    Positions are a flat float64 array, three per vertex, in world
    coordinates; normals likewise, from vertex_normals; colours a flat list of
    sRGB bytes; indices a flat int64 array, three per triangle.

    Normals are averaged per FACE, so a bend comes out smooth and the edge
    between two faces stays sharp.

    *doc* is the XCAF document the parts came from. With it the mesh is
    taken from OCCT's own glTF export (gltf.py) face by face, each face
    checked before its primitive is used - see _lined_up - and walked node
    by node when the check fails; without it every face is walked node by
    node. *log* takes a line when the export and the faces disagree, so a
    slow build says why it was slow. *workdir* is where the export may be
    written.

    **The parts must already be meshed.** This reads the triangulation that is
    there and does not make it, and *linear* and *angular* are here for the
    edges, which are discretised from the curve when a face has no polygon on
    it. Every caller meshes first - repair_parts does it, and the --no-repair
    branch does it by hand - so a second BRepMesh_IncrementalMesh here was
    doing the work twice: measured at 1.2 s of an 11.5 s build on a 927-face
    board, because that call re-meshes rather than noticing the triangulation
    already carries the deflection asked for.
    """
    chunks_pos: list[np.ndarray] = []      # (n, 3) world coordinates per face
    chunks_idx: list[np.ndarray] = []      # (m, 3) vertex indices per face
    nverts = ntris = 0
    col: list[int] = []
    faces_seen = 0
    from_export = 0
    # Where each face's triangles start, in triangles. They are emitted one
    # face after another and never interleave, so a start index per face is
    # the whole of what "which face is this triangle on" needs - 13 kB on a
    # 3286-face board, against 299 kB for an id on every triangle.
    face_starts: list[int] = []
    # Where each face's VERTICES begin, one entry per face in walk order and
    # None for a face with no triangulation - so collect_edges, which walks
    # the same faces in the same order, can take its edge points from the
    # world coordinates computed here instead of transforming every node a
    # second time.
    bases: list[int | None] = []
    tick = tick or (lambda _d, _t, _w: None)
    log = log or (lambda _m: None)
    # Counted up front so the bar means something: a real board is one part
    # with 900 faces, and per-part progress would sit still for the whole of
    # it. Per face it moves.
    total_faces = sum(len(faces(sh)) + sum(len(faces(pc)) for pc, _c in pt)
                      for _n, _r, sh, _l, pt in parts) or 1

    exported = export_mesh(doc, workdir) if doc is not None else None
    if doc is not None and exported is None:
        log("warning: OCCT declined to export the mesh; tessellating node by node")
    instances = iter(exported) if exported is not None else None

    for name, part_rgb, shape, part_loc, patches in parts:
        place = part_loc.Transformation()
        place12 = _twelve(place)
        # A mirrored placement reverses the winding of every triangle in it.
        mirrored = place.IsNegative()
        # The colour of the SOLID each face belongs to - the level of the
        # lookup between the face and the part, which was missing once and
        # is now one helper shared with the repair (meshing.solid_colours).
        by_solid, solid_rgb = solid_colours(shape, colour_of)

        # This part's primitives from the export, consumed in face order.
        # The patches are copies the document has never seen, so they are
        # walked node by node whatever the export holds.
        prims = next(instances, None) if instances is not None else None
        prim_at = 0
        own_faces = own_from_export = 0

        # The part's own faces, then any patched face carried beside it.
        jobs = [(f, None, True) for f in faces(shape)]
        for piece, patch_rgb in patches:
            jobs += [(f, patch_rgb, False) for f in faces(piece)]
        for face, forced, own in jobs:
            if faces_seen % 25 == 0:
                tick(faces_seen, total_faces, "tessellating")
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                bases.append(None)
                continue
            faces_seen += 1
            own_faces += own
            # Where this face's triangles begin. Recorded here, before any of
            # them are emitted, because the whole point is that they are
            # contiguous - one number per face instead of one per triangle.
            face_starts.append(ntris)
            flipped = (face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED)
            if mirrored:
                flipped = not flipped
            # Face, then the solid it belongs to, then the part, then grey.
            # Every step of that chain is one a real file has needed.
            rgb = (forced
                   or colour_of(face)
                   or solid_rgb.get(by_solid.FindIndex(face))
                   or part_rgb)

            base = nverts
            bases.append(base)
            arrays = None
            if own and prims is not None and prim_at < len(prims):
                positions, triangles = prims[prim_at]
                wound = _lined_up(tri, _twelve(loc.Transformation()),
                                  positions, triangles, flipped)
                if wound is not None:
                    prim_at += 1
                    own_from_export += 1
                    # The primitive is in the part's frame, float32; the
                    # placement goes on in double, in the order gp_Trsf
                    # evaluates it, the same as the node walk below.
                    arrays = (_placed(place12, positions.astype(np.float64)), wound)
            if arrays is None:
                # node -> face frame -> part frame -> world, composed once
                arrays = face_arrays(tri, _twelve(place.Multiplied(loc.Transformation())),
                                     flipped)
            points, triangles = arrays
            chunks_pos.append(points)
            chunks_idx.append(triangles + base)
            nverts += len(points)
            ntris += len(triangles)
            col.extend(tuple(rgb) * len(points))

        from_export += own_from_export
        if prims is not None and own_from_export < own_faces:
            log(f"warning: the mesh export did not line up with {name}: "
                f"{own_faces - own_from_export} of {own_faces} face(s) taken node by node")

    world = (np.concatenate(chunks_pos) if chunks_pos
             else np.zeros((0, 3), dtype=np.float64))
    idx = (np.concatenate(chunks_idx).ravel() if chunks_idx
           else np.zeros(0, dtype=np.int64))
    nrm = vertex_normals(world, idx)

    epos, eidx, from_mesh, from_curve, circles = collect_edges(
        parts, linear, angular, world, bases, tick=tick, total=total_faces)

    stats = {
        "parts": len(parts),
        "faces": faces_seen,
        "faces_from_export": from_export,
        "vertices": len(world),
        "triangles": len(idx) // 3,
        "edges": len(eidx) // 2,
        "edges_from_mesh": from_mesh,
        "edges_from_curve": from_curve,
        "face_starts": face_starts,
        "circles": circles,
    }
    return world.ravel(), nrm, col, idx, epos, eidx, stats


def _twelve(trsf):
    """A gp_Trsf as its twelve numbers: three rows of a rotation-and-scale
    and a translation, row by row - what _placed and face_arrays apply."""
    return tuple(trsf.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4))


def _placed(m, points):
    """*points* (n, 3) float64 through the transform *m* (see _twelve), each
    coordinate as a11*x + a12*y + a13*z + t1 in that order - the expression
    gp_Trsf evaluates, and the one face_arrays writes out per node, so the
    two paths agree to the last bit on the same input."""
    a11, a12, a13, t1, a21, a22, a23, t2, a31, a32, a33, t3 = m
    x, y, z = points[:, 0], points[:, 1], points[:, 2]
    return np.stack((a11 * x + a12 * y + a13 * z + t1,
                     a21 * x + a22 * y + a23 * z + t2,
                     a31 * x + a32 * y + a33 * z + t3), axis=1)


def face_arrays(tri, m, flipped):
    """One face node by node: -> (points (n, 3) float64 in world
    coordinates, triangles (m, 3) int64 of local vertex numbers).

    The transform done here, from the twelve numbers of the gp_Trsf, and X,
    Y, Z read once per node. What a node costs is the call into OCP, not the
    arithmetic: on a 525k-node board this loop went from 8.7 s through
    gp_Pnt.Transformed with the coordinates read twice to 5.3 s like this,
    with every one of the 1.57 million doubles bit-identical to OCCT's own -
    the expression below is the one gp_Trsf evaluates, in its order
    (docs/performance.md). Since 0.13.0 this is the road for the patches and
    for any face the export does not line up with; the rest come from
    gltf.py, ten times cheaper.
    """
    a11, a12, a13, t1, a21, a22, a23, t2, a31, a32, a33, t3 = m
    node = tri.Node
    pts = []
    for i in range(1, tri.NbNodes() + 1):
        p = node(i)
        x, y, z = p.X(), p.Y(), p.Z()
        pts.append((a11 * x + a12 * y + a13 * z + t1,
                    a21 * x + a22 * y + a23 * z + t2,
                    a31 * x + a32 * y + a33 * z + t3))
    points = np.array(pts, dtype=np.float64).reshape(-1, 3)
    # A reversed face, or a mirrored placement, turns every triangle over;
    # both together turn it back. Decided once per face, not per triangle.
    triangle = tri.Triangle
    corners = (triangle(i).Get() for i in range(1, tri.NbTriangles() + 1))
    if flipped:
        tris = [(a - 1, c - 1, b - 1) for a, b, c in corners]
    else:
        tris = [(a - 1, b - 1, c - 1) for a, b, c in corners]
    return points, np.array(tris, dtype=np.int64).reshape(-1, 3)


def _lined_up(tri, floc12, positions, triangles, flipped):
    """Is this primitive this face? -> its triangles wound our way, or None.

    Three checks, each cheap and each one a real file could fail: the node
    and triangle counts; the first node, transformed by the face's own
    location into the part's frame, within a float32 of the primitive's first
    position; and the first non-degenerate triangle, which says whether the
    writer already turned the face over (it does for a REVERSED face, and
    not for a mirrored placement, which lives in the glTF node instead) -
    so the primitive's winding is corrected to the rule face_arrays follows,
    reversed XOR mirrored, and never flipped twice.
    """
    n, m = tri.NbNodes(), tri.NbTriangles()
    if len(positions) != n or len(triangles) != m:
        return None
    a11, a12, a13, t1, a21, a22, a23, t2, a31, a32, a33, t3 = floc12
    p = tri.Node(1)
    x, y, z = p.X(), p.Y(), p.Z()
    want = (a11 * x + a12 * y + a13 * z + t1,
            a21 * x + a22 * y + a23 * z + t2,
            a31 * x + a32 * y + a33 * z + t3)
    for w, g in zip(want, positions[0]):
        if abs(w - float(g)) > 1e-3 + 1e-6 * abs(w):
            return None
    writer_flipped = False
    for i in range(1, min(m, 8) + 1):
        a, b, c = tri.Triangle(i).Get()
        if a == b or b == c or a == c:
            continue
        got = (int(triangles[i - 1, 0]), int(triangles[i - 1, 1]), int(triangles[i - 1, 2]))
        if got == (a - 1, b - 1, c - 1):
            writer_flipped = False
        elif got == (a - 1, c - 1, b - 1):
            writer_flipped = True
        else:
            return None
        break
    return triangles if writer_flipped == flipped else triangles[:, [0, 2, 1]]


def vertex_normals(pos, idx):
    """A unit normal per vertex: the facet normals of every triangle that
    meets there, summed and normalised. -> a flat float64 array, three per
    vertex.

    Faces never share vertices, so the sum only ever runs over one face and
    the edge between two faces stays sharp while a bend comes out smooth. A
    vertex no triangle touches points along +Z rather than nowhere.

    numpy, in place of a Python loop over every triangle, and in the SAME
    ORDER of additions as that loop: np.add.at applies its additions in the
    order of the index array, and the index array here is the triangles as
    emitted, corner by corner, which is exactly how the loop walked them. So
    the sums are bit-identical, not merely close - measured on the 513k
    triangles of a real board, and held by the golden payload
    (docs/performance.md). 2.5 s -> 0.6 s there.
    """
    P = np.asarray(pos, dtype=np.float64).reshape(-1, 3)
    I = np.asarray(idx, dtype=np.int64).reshape(-1, 3)
    N = np.zeros_like(P)
    if len(I):
        A, B, C = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
        # b - a crossed with c - a: the same three products-and-differences
        # the loop wrote out, so the same doubles.
        F = np.cross(B - A, C - A)
        np.add.at(N, I.ravel(), np.repeat(F, 3, axis=0))
    x, y, z = N[:, 0], N[:, 1], N[:, 2]
    m = np.sqrt(x * x + y * y + z * z)
    flat = m == 0
    m[flat] = 1.0
    N /= m[:, None]
    N[flat] = (0.0, 0.0, 1.0)
    return N.ravel()


def collect_edges(parts, linear, angular, world, bases, tick=None, total=1):
    """Real B-rep edges as line segments, taken FROM THE TRIANGULATION.

    *world* is every vertex tessellate emitted, in world coordinates, as an
    (N, 3) array, and *bases* says where each face's vertices begin in it,
    one entry per face in the order faces() walks them (None for a face with
    no triangulation). An edge's polygon names nodes of the face's own
    triangulation, so its points are rows of *world* - the very doubles the
    face loop computed - and nothing is transformed twice. On a 366k-node
    board that was the Node, Transformed and X/Y/Z call on every edge point,
    a third of this function's time (docs/performance.md).

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
    chunks: list[np.ndarray] = []           # (k, 3) points per edge, in order
    nverts = 0
    idx: list[int] = []
    from_mesh = from_curve = 0
    tick = tick or (lambda _d, _t, _w: None)
    done = 0
    # Circles, for snapping a measurement to a centre. Kept here rather than
    # in a pass of their own because this is already the one walk over every
    # edge of every part, with the placement to hand.
    circles: list[tuple[float, ...]] = []
    circle_keys: set[tuple] = set()

    def note_circle(edge, place):
        """A circular edge -> centre, axis and radius in world coordinates.

        Measured, not assumed: BRepAdaptor_Curve.Circle() comes back with the
        EDGE's own location already applied - a cylinder built at the origin
        and then moved reports its centres at the moved place - so only the
        part's placement is left to apply.

        One hole is one centre however its rim is cut up. A rim split into
        arcs, or shared by two faces, would otherwise be several identical
        entries, each of them another circle for the snap to scan.
        """
        try:
            ad = BRepAdaptor_Curve(edge)
            if ad.GetType() != GeomAbs_CurveType.GeomAbs_Circle:
                return
            circ = ad.Circle().Transformed(place)
        except Exception:
            return
        c, d = circ.Location(), circ.Axis().Direction()
        r = circ.Radius()
        nx, ny, nz = d.X(), d.Y(), d.Z()
        # A circle and the same circle seen from the other side are one thing,
        # so the axis is given a fixed sense before it is compared.
        if (nx, ny, nz) < (0.0, 0.0, 0.0):
            nx, ny, nz = -nx, -ny, -nz
        rec = (c.X(), c.Y(), c.Z(), nx, ny, nz, r)
        key = tuple(round(v, 4) for v in rec)
        if key in circle_keys:
            return
        circle_keys.add(key)
        circles.append(rec)

    def emit(points):
        """*points* is a (k, 3) array: one polyline, k - 1 segments."""
        nonlocal nverts
        first = nverts
        chunks.append(points)
        nverts += len(points)
        for k in range(len(points) - 1):
            idx.extend((first + k, first + k + 1))

    for _name, _rgb, shape, part_loc, patches in parts:
        place = part_loc.Transformation()
        for source in [shape] + [piece for piece, _c in patches]:
            seen = TopTools_IndexedMapOfShape()
            for face in faces(source):
                if done % 25 == 0:
                    tick(done, total, "edges")
                base = bases[done]
                done += 1
                floc = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(face, floc)
                exp = TopExp_Explorer(face, TopAbs_EDGE)
                while exp.More():
                    # Edge, not Edge_s: the bare name is the one both OCCT
                    # 7.9 and 8.0 bind (see _occt.py).
                    edge = TopoDS.Edge(exp.Current())
                    exp.Next()
                    if BRep_Tool.Degenerated_s(edge):
                        continue
                    # An edge belongs to two faces; draw it once.
                    if seen.FindIndex(edge):
                        continue
                    note_circle(edge, place)

                    poly = (BRep_Tool.PolygonOnTriangulation_s(edge, tri, floc)
                            if tri is not None and base is not None else None)
                    if poly is not None:
                        nodes = poly.Nodes()
                        n = nodes.Length()
                        if n >= 2:
                            # The polygon's node numbers are 1-based indices
                            # into this face's triangulation, whose vertices
                            # sit at world[base:]; the rows are copied, so the
                            # points are the face loop's own doubles.
                            lo = nodes.Lower()
                            ids = np.fromiter((nodes.Value(i) for i in range(lo, lo + n)),
                                              dtype=np.int64, count=n)
                            emit(world[base + ids - 1])
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
                    emit(np.array([(lambda q: (q.X(), q.Y(), q.Z()))(
                                       curve.Value(disc.Parameter(k)).Transformed(place))
                                   for k in range(1, disc.NbPoints() + 1)],
                                  dtype=np.float64).reshape(-1, 3))
                    seen.Add(edge)
                    from_curve += 1

    epos = np.concatenate(chunks).ravel() if chunks else np.zeros(0, dtype=np.float64)
    return epos, idx, from_mesh, from_curve, circles
