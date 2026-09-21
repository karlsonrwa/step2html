"""Repairing a face the mesher refuses must be INVISIBLE to every other face.

This is not a hypothetical. The first version of the repair split the closed
faces of the whole solid, which sliced the sound cylindrical shafts of a
connector's pins into halves that meshed separately and did not meet, and
drew an invented edge down each one. The fix was to patch one face at a time,
on a copy, leaving the part itself untouched - and this test is what would
have caught the first version.

The check is deliberately blunt: with the repair on, every face of the part
must have exactly the triangle count it has with the repair off, and the
edges must be identical. Anything the repair touches beyond the broken face
shows up immediately.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

from harness import ANGULAR, area, check, run
from fixtures import PIN, RIM, coloured_assembly
from step2html import ConvertError, meshing
from step2html.convert import Options, convert
from step2html.meshing import (auto_deflection, faces, mesh_parts,
                               patch_face, repair_parts)
from step2html.tessellate import tessellate
from step2html.xcaf import collect_parts, colour_lookup, read_step

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.TopLoc import TopLoc_Location


def build(step, repair):
    doc = read_step(step)
    parts, color_tool = collect_parts(doc)
    colour_of = colour_lookup(color_tool)
    linear = auto_deflection(parts)
    if repair:
        parts, _r, left = repair_parts(parts, colour_of, linear, ANGULAR,
                                       lambda _m: None)
    else:
        parts, _r, left = mesh_parts(parts, linear, ANGULAR)
    signature = []
    for _n, _c, sh, _l, _p in parts:
        for face in faces(sh):
            tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
            signature.append(tri.NbTriangles() if tri is not None else 0)
    pos, nrm, col, idx, epos, eidx, stats = tessellate(
        parts, colour_of, linear=linear, angular=ANGULAR, doc=doc)
    return signature, stats, left, len(eidx) // 2, len(idx) // 3


def main():
    with tempfile.TemporaryDirectory() as tmp:
        step = coloured_assembly(Path(tmp) / "fixture.step")
        plain_sig, _s0, _l0, plain_edges, plain_tris = build(step, repair=False)
        fixed_sig, _s1, left, fixed_edges, fixed_tris = build(step, repair=True)

        check(len(plain_sig) == len(fixed_sig),
              "the repair adds no faces to the part itself",
              f"{len(plain_sig)} vs {len(fixed_sig)}")
        differing = sum(1 for a, b in zip(plain_sig, fixed_sig) if a != b)
        check(differing == 0,
              "every face keeps exactly the triangles it had",
              f"{differing} differ")
        check(plain_edges == fixed_edges,
              "the edges are untouched, segment for segment",
              f"{plain_edges} vs {fixed_edges}")
        check(fixed_tris >= plain_tris,
              "the repair only ever adds geometry",
              f"{plain_tris} -> {fixed_tris}")
        check(not left, "this fixture needs no patching in the first place")

        # ... and because it does, _patch_face itself had no test at all - the
        # most delicate piece of the pipeline, and the one whose order was just
        # rearranged for speed. A face the mesher refuses could not be built
        # synthetically to trigger it: five constructions of the closed
        # periodic case, pi to 3*pi on a cylinder and on a cone, were all
        # meshed happily. So the patch is exercised on a healthy closed face
        # instead, which pins what a patch must be whatever asked for it.
        cyl = BRepPrimAPI_MakeCylinder(1.5, 6.0).Shape()
        lateral = max(faces(cyl), key=area)          # the closed periodic one
        patch = patch_face(lateral, 0.04, ANGULAR)
        check(patch is not None, "a patch comes back at all")
        if patch is not None:
            tris = 0
            for f in faces(patch):
                t = BRep_Tool.Triangulation_s(f, TopLoc_Location())
                tris += t.NbTriangles() if t is not None else 0
            check(tris > 0, "and it is meshed", f"{tris} triangles")
            # A patch stands in for the face it replaces, so it has to cover
            # the same surface. Mangled by the split, it would be a hole or a
            # doubled face, and nothing else here would notice.
            a0, a1 = area(lateral), area(patch)
            check(abs(a1 - a0) <= a0 * 1e-6,
                  "and it covers exactly the face it stands in for",
                  f"{a0:.5f} -> {a1:.5f} mm2")
            # Two faces mean the SPLIT was tried first, which is the whole of
            # the speed fix: a plain copy at the model's own deflection is the
            # attempt the mesher has just refused, and on a real connector it
            # costs 0.85 s to be refused again.
            check(len(faces(patch)) == 2,
                  "and the split is what was tried first at this deflection",
                  f"{len(faces(patch))} face(s)")

        # ---- the rescue arm itself ---------------------------------------- #
        # patch_face above is one half of the repair; the other half is
        # repair_parts deciding to call it, carrying what comes back beside
        # the part and painting it. Nothing in this fixture is refused, so
        # that arm never ran here: severing it - patch_face replaced by None
        # - left every check above green. Tell repair_parts that one healthy
        # face of each part came out empty, and the arm runs end to end.
        doc3 = read_step(step)
        raw3, ct3 = collect_parts(doc3)
        lin3 = auto_deflection(raw3)
        was = meshing.empty_faces
        meshing.empty_faces = lambda shape: [(faces(shape)[0],
                                              area(faces(shape)[0]))]
        try:
            forced, rescued, over = repair_parts(raw3, colour_lookup(ct3),
                                                 lin3, ANGULAR, lambda _m: None)
        finally:
            meshing.empty_faces = was
        check(rescued == len(raw3) and not over,
              "every face the mesher refuses is patched, and none is left over",
              f"{rescued} patched of {len(raw3)}, {len(over)} left")
        check(all(len(patches) == 1 for _n, _c, _s, _l, patches in forced),
              "each patch is carried beside its own part, not merged into it",
              str([len(p[4]) for p in forced]))
        painted = {name: patches[0][1]
                   for name, _c, _s, _l, patches in forced if patches}
        check(painted.get("board") == RIM and painted.get("pin") == PIN,
              "and takes the face's own colour, or the part's where it has none",
              f"board {painted.get('board')}, pin {painted.get('pin')}")
        forced_sig = []
        for _n, _c, sh, _l, _p in forced:
            for face in faces(sh):
                tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
                forced_sig.append(tri.NbTriangles() if tri is not None else 0)
        check(forced_sig == plain_sig,
              "and the part it patched is untouched, triangle for triangle",
              f"{sum(1 for a, b in zip(forced_sig, plain_sig) if a != b)} of "
              f"{len(plain_sig)} faces differ")

        # tessellate reads the triangulation; it does not make one. That is
        # what took the second BRepMesh out of it - 1.2 s a build on a real
        # board - and it is a contract, so it is pinned: unmeshed parts must
        # come back empty rather than quietly meshing themselves again.
        doc0 = read_step(step)
        raw_parts, ct0 = collect_parts(doc0)
        unmeshed = [(n, c, sh, l, []) for n, c, sh, l in raw_parts]
        lin0 = auto_deflection(raw_parts)
        pos0, _n0, _c0, idx0, epos0, _ei0, st0 = tessellate(
            unmeshed, colour_lookup(ct0), linear=lin0,
            angular=ANGULAR, doc=doc0, workdir=tmp)
        check(len(pos0) == 0 and len(idx0) == 0,
              "tessellate reads a mesh, it does not make one",
              f"{len(pos0) // 3} vertices from unmeshed parts")
        # And the other half of the same call: with no triangulation to take
        # an edge's points from, every edge comes from the curve itself.
        # That fallback is the one path nothing else here walks - the
        # placement was dropped out of it and the whole suite stayed green -
        # so it is measured where it is reached: the edges must still outline
        # the model where it really stands, which OCCT is asked for.
        edge = np.asarray(epos0, dtype=np.float64).reshape(-1, 3)
        check(len(edge) > 0 and st0["edges_from_curve"] > 0
              and st0["edges_from_mesh"] == 0,
              "an unmeshed part still gets its edges, from the curve itself",
              f"{st0['edges_from_curve']} from the curve, "
              f"{st0['edges_from_mesh']} from a mesh")
        box0 = Bnd_Box()
        for _n, _c, sh, loc in raw_parts:
            BRepBndLib.Add_s(sh.Moved(loc), box0, True)
        lo, hi = box0.CornerMin(), box0.CornerMax()
        worst = max(
            float(np.abs(edge.min(axis=0)
                         - np.array([lo.X(), lo.Y(), lo.Z()])).max()),
            float(np.abs(edge.max(axis=0)
                         - np.array([hi.X(), hi.Y(), hi.Z()])).max())
        ) if len(edge) else 99.0
        check(worst <= lin0,
              "and they outline the model where it really stands",
              f"worst corner off by {worst:.3g} mm, deflection {lin0:.3g} mm")

        # The auto deflection has to be a number and has to scale with the
        # model, since a fixed millimetre is the wrong unit for both a pin and
        # a panel.
        doc = read_step(step)
        parts, _ct = collect_parts(doc)
        deflection = auto_deflection(parts)
        check(0.004 <= deflection <= 0.25,
              "the automatic deflection is inside its clamp",
              f"{deflection:.4g} mm")
        # "Inside the clamp" is what the last line of auto_deflection DOES,
        # so that check held whatever the rule above it was: halving the
        # divisor left it green. The rule itself is one part in 2000 of the
        # diagonal, and a 3-4-12 box has a diagonal of exactly 13 mm - a
        # number known here, not taken from the code - so 0.0065 mm.
        here = TopLoc_Location()
        known = auto_deflection([("b", PIN, BRepPrimAPI_MakeBox(3.0, 4.0, 12.0)
                                  .Shape(), here)])
        check(abs(known - 13.0 / 2000.0) < 1e-6,
              "the automatic deflection is one part in 2000 of the diagonal",
              f"{known:.6g} mm for a 13 mm diagonal")
        # And the clamp itself, at both ends, where the rule would run off.
        speck = auto_deflection([("s", PIN, BRepPrimAPI_MakeBox(1.0, 1.0, 1.0)
                                  .Shape(), here)])
        panel = auto_deflection([("p", PIN, BRepPrimAPI_MakeBox(1000.0, 1000.0,
                                                                1000.0)
                                  .Shape(), here)])
        check(speck == 0.004 and panel == 0.25,
              "and the clamp holds at both ends",
              f"1 mm cube -> {speck:.4g} mm, 1 m cube -> {panel:.4g} mm")

        # A file that is not a STEP has to come back as a ConvertError and
        # nothing else. SystemExit derives from BaseException, so the worker's
        # "except Exception" would let it straight through: the child process
        # died silently and the window blamed OCCT for a crash it never had.
        junk = Path(tmp) / "not-a-step.step"
        junk.write_text("this is not a STEP file at all\n", encoding="utf-8")
        try:
            convert(Options(step=str(junk)))
            raised = "nothing"
        except ConvertError as exc:
            raised = "ConvertError"
            detail = str(exc)
        except BaseException as exc:            # noqa: BLE001 - that is the point
            raised = type(exc).__name__
            detail = str(exc)
        check(raised == "ConvertError",
              "an unreadable STEP raises ConvertError, catchable by the worker",
              f"{raised}: {detail[:60]}")


if __name__ == "__main__":
    sys.exit(run(main, "repairing a refused face"))
