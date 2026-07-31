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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import step_to_html as S
from fixtures import coloured_assembly

from OCP.BRep import BRep_Tool
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.TopLoc import TopLoc_Location

FAILURES = []
ANGULAR = 15 * 3.141592653589793 / 180.0


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def _area(shape) -> float:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def build(step, repair):
    doc = S.read_step(step)
    parts, color_tool = S.collect_parts(doc)
    linear = S.auto_deflection(parts)
    if repair:
        parts, _r, left = S.repair_parts(parts, color_tool, linear, ANGULAR,
                                         lambda _m: None)
    else:
        parts = [(n, c, sh, l, []) for n, c, sh, l in parts]
        for _n, _c, sh, _l, _p in parts:
            BRepTools.Clean_s(sh)
            BRepMesh_IncrementalMesh(sh, linear, False, ANGULAR, True)
        left = []
    signature = []
    for _n, _c, sh, _l, _p in parts:
        for face in S._faces(sh):
            tri = BRep_Tool.Triangulation_s(face, TopLoc_Location())
            signature.append(tri.NbTriangles() if tri is not None else 0)
    pos, nrm, col, idx, epos, eidx, stats = S.tessellate(
        parts, color_tool, linear=linear, angular=ANGULAR)
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
        lateral = max(S._faces(cyl), key=_area)      # the closed periodic one
        patch = S._patch_face(lateral, 0.04, ANGULAR)
        check(patch is not None, "a patch comes back at all")
        if patch is not None:
            tris = 0
            for f in S._faces(patch):
                t = BRep_Tool.Triangulation_s(f, TopLoc_Location())
                tris += t.NbTriangles() if t is not None else 0
            check(tris > 0, "and it is meshed", f"{tris} triangles")
            # A patch stands in for the face it replaces, so it has to cover
            # the same surface. Mangled by the split, it would be a hole or a
            # doubled face, and nothing else here would notice.
            a0, a1 = _area(lateral), _area(patch)
            check(abs(a1 - a0) <= a0 * 1e-6,
                  "and it covers exactly the face it stands in for",
                  f"{a0:.5f} -> {a1:.5f} mm2")
            # Two faces mean the SPLIT was tried first, which is the whole of
            # the speed fix: a plain copy at the model's own deflection is the
            # attempt the mesher has just refused, and on a real connector it
            # costs 0.85 s to be refused again.
            check(len(S._faces(patch)) == 2,
                  "and the split is what was tried first at this deflection",
                  f"{len(S._faces(patch))} face(s)")

        # tessellate reads the triangulation; it does not make one. That is
        # what took the second BRepMesh out of it - 1.2 s a build on a real
        # board - and it is a contract, so it is pinned: unmeshed parts must
        # come back empty rather than quietly meshing themselves again.
        doc0 = S.read_step(step)
        raw_parts, ct0 = S.collect_parts(doc0)
        unmeshed = [(n, c, sh, l, []) for n, c, sh, l in raw_parts]
        pos0, _n0, _c0, idx0, _e0, _ei0, _st0 = S.tessellate(
            unmeshed, ct0, linear=S.auto_deflection(raw_parts), angular=ANGULAR)
        check(not pos0 and not idx0,
              "tessellate reads a mesh, it does not make one",
              f"{len(pos0) // 3} vertices from unmeshed parts")

        # The auto deflection has to be a number and has to scale with the
        # model, since a fixed millimetre is the wrong unit for both a pin and
        # a panel.
        doc = S.read_step(step)
        parts, _ct = S.collect_parts(doc)
        deflection = S.auto_deflection(parts)
        check(0.004 <= deflection <= 0.25,
              "the automatic deflection is inside its clamp",
              f"{deflection:.4g} mm")

        # A file that is not a STEP has to come back as a ConvertError and
        # nothing else. SystemExit derives from BaseException, so the worker's
        # "except Exception" would let it straight through: the child process
        # died silently and the window blamed OCCT for a crash it never had.
        junk = Path(tmp) / "not-a-step.step"
        junk.write_text("this is not a STEP file at all\n", encoding="utf-8")
        try:
            S.convert(S.Options(step=str(junk)))
            raised = "nothing"
        except S.ConvertError as exc:
            raised = "ConvertError"
            detail = str(exc)
        except BaseException as exc:            # noqa: BLE001 - that is the point
            raised = type(exc).__name__
            detail = str(exc)
        check(raised == "ConvertError",
              "an unreadable STEP raises ConvertError, catchable by the worker",
              f"{raised}: {detail[:60]}")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    print("repairing a refused face")
    sys.exit(main())
