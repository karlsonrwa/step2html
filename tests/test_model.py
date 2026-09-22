"""Colours and geometry: the two things that have been quietly wrong before.

Colour is found by the IDENTITY of a shape, so it survives neither a moved
copy nor a face that has been replaced. Geometry is checked against a second
opinion from OCCT rather than against itself.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from harness import ANGULAR, check, run, scratch
from fixtures import (BODY, PIN, PIN_AT, PLATE_A, PLATE_AT, PLATE_B, RIM,
                      coloured_assembly)
from step2html.meshing import auto_deflection, mesh_parts, repair_parts
from step2html.tessellate import tessellate
from step2html.xcaf import (DEFAULT_RGB, collect_parts, colour_lookup,
                            read_step)

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Trsf, gp_Vec
from OCP.GProp import GProp_GProps
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound


def main():
    with scratch() as tmp:
        step = coloured_assembly(Path(tmp) / "fixture.step")
        doc = read_step(step)
        parts, color_tool = collect_parts(doc)
        colour_of = colour_lookup(color_tool)
        linear = auto_deflection(parts)
        angular = ANGULAR
        parts, _rescued, left = repair_parts(
            parts, colour_of, linear, angular, lambda _m: None)
        warnings = []
        pos, nrm, col, idx, epos, eidx, stats = tessellate(
            parts, colour_of, linear=linear, angular=angular, doc=doc,
            log=warnings.append, workdir=tmp)

        seen = Counter(tuple(col[i:i + 3]) for i in range(0, len(col), 3))

        # ---- the export lines up with the node walk ----------------------- #
        # The mesh comes from OCCT's own glTF export, face by face, and each
        # face is checked before its primitive is used. On this fixture every
        # face must pass, and what comes out must be what walking the nodes
        # gives: the same vertices to a float32, the same triangles, colours
        # and face table exactly, the same edges.
        check(stats["faces_from_export"] == stats["faces"] and not warnings,
              "every face came from the export, none fell back to the nodes",
              f"{stats['faces_from_export']} of {stats['faces']}; {warnings}")
        w_pos, w_nrm, w_col, w_idx, w_epos, w_eidx, w_stats = tessellate(
            parts, colour_of, linear=linear, angular=angular)
        off = float(np.abs(np.asarray(pos) - np.asarray(w_pos)).max()) if len(pos) else 0.0
        check(len(pos) == len(w_pos) and off < 1e-4,
              "the exported vertices are the walked vertices to a float32",
              f"{len(pos) // 3} vs {len(w_pos) // 3} vertices, worst {off:.3g} mm")
        check(list(idx) == list(w_idx) and list(col) == list(w_col)
              and stats["face_starts"] == w_stats["face_starts"],
              "the same triangles, colours and face table exactly")
        e_off = float(np.abs(np.asarray(epos) - np.asarray(w_epos)).max()) if len(epos) else 0.0
        check(list(eidx) == list(w_eidx) and e_off < 1e-4,
              "the same edges, segment for segment", f"worst {e_off:.3g} mm")
        n_off = float(np.abs(np.asarray(nrm) - np.asarray(w_nrm)).max()) if len(nrm) else 0.0
        check(n_off < 1e-3, "and normals that agree to a thousandth",
              f"worst component off by {n_off:.3g}")
        check(not list(Path(tmp).glob("*.glb")), "the export file is gone afterwards")

        # What the per-face check is FOR: a primitive that is not this face.
        # Every face of this fixture lines up - measured, 21 of 21, none
        # refused - so the refusal, the fallback behind it and the winding
        # correction are never reached by the run above, and severing the
        # check outright left every line of it green. Hand tessellate the
        # same document with the parts in the other order: the primitives no
        # longer belong to the parts they are offered to, so the faces that
        # do not line up must be refused, said out loud, and walked - and
        # what comes out must still be the node walk's own answer.
        odd = list(reversed(parts))
        told = []
        o_pos, _on, _oc, o_idx, _oe, _oei, o_stats = tessellate(
            odd, colour_of, linear=linear, angular=angular, doc=doc,
            log=told.append, workdir=tmp)
        n_pos, _nn, _nc, n_idx, _ne, _nei, _nstats = tessellate(
            odd, colour_of, linear=linear, angular=angular)
        check(o_stats["faces_from_export"] < o_stats["faces"] and told,
              "a primitive that is not this face is refused, and said so",
              f"{o_stats['faces_from_export']} of {o_stats['faces']} faces "
              f"from the export, {len(told)} warning(s)")
        mis = (float(np.abs(np.asarray(o_pos) - np.asarray(n_pos)).max())
               if len(o_pos) == len(n_pos) else 99.0)
        check(mis < 1e-4 and list(o_idx) == list(n_idx),
              "and a refused face comes back the node walk's own answer",
              f"{len(o_pos) // 3} vs {len(n_pos) // 3} vertices, worst {mis:.3g} mm")

        # ---- colour ------------------------------------------------------ #
        check(BODY in seen, "the part colour survives",
              f"#{BODY[0]:02X}{BODY[1]:02X}{BODY[2]:02X}")
        check(RIM in seen, "a face painted over the part keeps its own colour",
              f"#{RIM[0]:02X}{RIM[1]:02X}{RIM[2]:02X}")
        check(PIN in seen, "a part placed away from the origin keeps its colour",
              f"#{PIN[0]:02X}{PIN[1]:02X}{PIN[2]:02X}")
        check(PLATE_A in seen and PLATE_B in seen,
              "two solids in one part keep a colour each",
              f"A={PLATE_A in seen} B={PLATE_B in seen}")
        check(DEFAULT_RGB not in seen,
              "nothing fell back to the default grey")

        # ---- placement --------------------------------------------------- #
        # A second opinion: move every part properly and let OCCT measure it.
        builder = BRep_Builder()
        comp = TopoDS_Compound()
        builder.MakeCompound(comp)
        for _n, _c, shape, loc, _p in parts:
            builder.Add(comp, shape.Moved(loc))
        box = Bnd_Box()
        BRepBndLib.Add_s(comp, box, True)
        # The corners, not box.Get(): OCCT 8.0's Get() overload returns an
        # unregistered Bnd_Box::Limits and raises before the six-tuple one is
        # reached (see the note in meshing.auto_deflection).
        lo, hi = box.CornerMin(), box.CornerMax()
        rx0, ry0, rz0 = lo.X(), lo.Y(), lo.Z()
        rx1, ry1, rz1 = hi.X(), hi.Y(), hi.Z()
        tx0, tx1 = min(pos[0::3]), max(pos[0::3])
        ty0, ty1 = min(pos[1::3]), max(pos[1::3])
        tz0, tz1 = min(pos[2::3]), max(pos[2::3])
        worst = max(abs(tx0 - rx0), abs(ty0 - ry0), abs(tz0 - rz0),
                    abs(tx1 - rx1), abs(ty1 - ry1), abs(tz1 - rz1))
        # Not exact, and it must not be: the chords of a curved face lie
        # INSIDE the true surface, so the mesh is smaller than the solid by up
        # to one deflection. A planar model comes out at 0.0000; a cylinder
        # cannot. What has to hold is that the error stays inside the budget
        # asked for, and that the mesh never pokes OUT of the real solid.
        check(worst <= linear, "the tessellation stays within its own deflection",
              f"worst corner off by {worst:.3g} mm, deflection {linear:.3g} mm")
        slack = 1e-9
        check(tx0 >= rx0 - slack and ty0 >= ry0 - slack and tz0 >= rz0 - slack
              and tx1 <= rx1 + slack and ty1 <= ry1 + slack and tz1 <= rz1 + slack,
              "the mesh sits inside the solid, never outside it")
        # Measured on the parts THAT ARE PLACED, not on the model as a whole:
        # the board alone reaches x=60, so "the model reaches past the pin"
        # is true whether or not the pin's transform was ever applied -
        # dropping the component location left that check green. The pin is
        # the only thing that reaches z=8 and the plate the only thing that
        # reaches y=50, so those two numbers cannot be had without them.
        check(abs(tz1 - (PIN_AT[2] + 6.0)) <= linear,
              "the placed pin really is out at its transform",
              f"model reaches z={tz1:.4g}, the pin's top is at "
              f"z={PIN_AT[2] + 6.0:.0f}")
        check(abs(ty1 - (PLATE_AT[1] + 10.0)) <= linear,
              "and so is the placed plate",
              f"model reaches y={ty1:.4g}, the plate's far edge is at "
              f"y={PLATE_AT[1] + 10.0:.0f}")

        # ---- the mesh is a solid, and wound the right way out ------------ #
        # Everything above compares the two paths WITH EACH OTHER, so
        # whatever they share - the winding rule, the normals, which are
        # computed once for both - agrees with itself however wrong it is:
        # turning every normal inside out moved nothing here until this
        # block existed. Two second opinions instead. The signed volume of
        # the triangles (the divergence theorem on a closed mesh) against
        # OCCT's own volume of the same solids - it changes sign the moment
        # the winding turns over. And every vertex normal against the
        # triangles that meet there, by the right-hand rule, which is what
        # the shader lights with.
        P = np.asarray(pos, dtype=np.float64).reshape(-1, 3)
        I = np.asarray(idx, dtype=np.int64).reshape(-1, 3)
        va, vb, vc = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
        facets = np.cross(vb - va, vc - va)
        mesh_volume = float(np.einsum("ij,ij->i", va, facets).sum()) / 6.0
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(comp, props)
        solid_volume = props.Mass()
        check(0.99 <= mesh_volume / solid_volume <= 1.0 + 1e-9,
              "the triangles enclose the solid's own volume, wound outward",
              f"{mesh_volume:.4f} mm3 of mesh against {solid_volume:.4f} mm3 "
              f"of solid")
        N = np.asarray(nrm, dtype=np.float64).reshape(-1, 3)
        off_unit = float(np.abs(np.sqrt((N * N).sum(axis=1)) - 1.0).max())
        check(off_unit < 1e-9, "every normal is a unit vector",
              f"worst length off by {off_unit:.3g}")
        facing = np.einsum("ij,ij->i", N[I.ravel()], np.repeat(facets, 3, axis=0))
        wrong = int((facing <= 0).sum())
        check(wrong == 0,
              "and points the way its own triangles face, not into the solid",
              f"{wrong} of {facing.size} corners point the wrong way")

        # ---- the circles a measurement snaps to -------------------------- #
        # Where a placement bug would hide, and the same hiding place as the
        # colour one: the circle comes out of the edge's own curve, which
        # already carries the EDGE's location, and the PART's placement has to
        # be applied on top by hand. Get that wrong and every hole on every
        # placed component snaps to a centre back at the origin - which looks
        # plausible on a part that happens to sit there.
        circles = stats["circles"]
        pin_rims = [c for c in circles if abs(c[6] - 1.5) < 1e-6]
        check(len(pin_rims) == 2, "the pin gives one circle per rim and no more",
              f"{len(pin_rims)} of {len(circles)} circles at r=1.5")
        off = max((max(abs(c[0] - PIN_AT[0]), abs(c[1] - PIN_AT[1]))
                   for c in pin_rims), default=99.0)
        check(off < 1e-6, "and their centres carry the part's placement",
              f"worst axis off by {off:.3g} mm from ({PIN_AT[0]}, {PIN_AT[1]})")
        zs = sorted(round(c[2], 6) for c in pin_rims)
        check(zs == [PIN_AT[2], PIN_AT[2] + 6.0],
              "one rim at each end of the pin, 6 mm apart", str(zs))
        check(all(abs(c[3] ** 2 + c[4] ** 2 + c[5] ** 2 - 1.0) < 1e-6
                  for c in circles),
              "every circle carries a unit axis")
        # One hole is one circle however its rim is cut up or shared, which
        # is what keeps the snap from scanning the same circle over and
        # over. Every rim of the fixture belongs to one part alone, so the
        # joining never happens there and switching it off changed nothing;
        # two cylinders end to end have four rims and three circles, because
        # the touching pair is one circle arriving twice.
        raised = gp_Trsf()
        raised.SetTranslation(gp_Vec(0.0, 0.0, 3.0))
        stacked, _sr, _sl = mesh_parts(
            [("lower", PIN, BRepPrimAPI_MakeCylinder(2.0, 3.0).Shape(),
              TopLoc_Location()),
             ("upper", PIN, BRepPrimAPI_MakeCylinder(2.0, 3.0).Shape(),
              TopLoc_Location(raised))], linear, angular)
        _sp, _sn, _sc, _si, _se, _sei, st2 = tessellate(
            stacked, lambda _s: None, linear=linear, angular=angular)
        zs2 = sorted(round(c[2], 6) for c in st2["circles"])
        check(len(st2["circles"]) == 3 and zs2 == [0.0, 3.0, 6.0],
              "two rims that are the same circle arrive as one",
              f"{len(st2['circles'])} circles at z={zs2}")

        # ---- what came out ------------------------------------------------ #
        check(stats["triangles"] > 0 and stats["edges"] > 0,
              "there are triangles and edges",
              f"{stats['triangles']} tri, {stats['edges']} edge segments")
        check(stats["edges_from_mesh"] > 0 and stats["edges_from_curve"] == 0,
              "every edge comes from the triangulation, none from the fallback",
              f"{stats['edges_from_mesh']} from the mesh")
        # "From the triangulation" means exactly this: a drawn segment is
        # not near a triangle's edge, it IS one - the same two vertices and
        # the same straight piece between them, which is the whole reason a
        # line needs no depth bias to sit on the surface it bounds. An
        # edge's points are rows of the world array at THAT FACE's own base,
        # and taking them at another face's base leaves them points of the
        # model still: same array, same bounding box, both paths alike, so
        # every check above stayed green and even the outline of the model
        # came out identical. What notices is the pairing - 29 of the 133
        # segments then joined two vertices no triangle joins.
        tri_pairs = set()
        for ta, tb, tc in I:
            for u, v in ((ta, tb), (tb, tc), (tc, ta)):
                tri_pairs.add((min(u, v), max(u, v)))
        at = defaultdict(set)
        for i, row in enumerate(map(tuple, P)):
            at[row].add(i)              # faces share no vertices: one place each
        EP = np.asarray(epos, dtype=np.float64).reshape(-1, 3)
        stray = 0
        for k in range(0, len(eidx), 2):
            p0, p1 = tuple(EP[eidx[k]]), tuple(EP[eidx[k + 1]])
            if not any((min(a, b), max(a, b)) in tri_pairs
                       for a in at.get(p0, ()) for b in at.get(p1, ())):
                stray += 1
        check(len(eidx) > 0 and stray == 0,
              "every edge segment is an edge of a triangle, not merely near one",
              f"{stray} of {len(eidx) // 2} segments join vertices no "
              f"triangle joins")
        # The face table is one number per face, ascending, and it is what
        # says which face a picked triangle is on. "Ascending" alone is true
        # of a table of noughts, which is what a severed one is.
        starts = stats["face_starts"]
        check(len(starts) == stats["faces"] and starts[0] == 0
              and all(a < b for a, b in zip(starts, starts[1:]))
              and starts[-1] < stats["triangles"],
              "the face table names every face once, strictly in order",
              f"{len(starts)} entries for {stats['faces']} faces, last at "
              f"{starts[-1]} of {stats['triangles']} triangles")
        check(not left, "every face meshed")


if __name__ == "__main__":
    sys.exit(run(main, "colours and geometry"))
