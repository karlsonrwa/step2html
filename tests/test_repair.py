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

from harness import ANGULAR, area, check, run
from fixtures import coloured_assembly
from step2html import ConvertError
from step2html.convert import Options, convert
from step2html.meshing import (auto_deflection, faces, mesh_parts,
                               patch_face, repair_parts)
from step2html.tessellate import tessellate
from step2html.xcaf import collect_parts, colour_lookup, read_step

from OCP.BRep import BRep_Tool
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
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

        # tessellate reads the triangulation; it does not make one. That is
        # what took the second BRepMesh out of it - 1.2 s a build on a real
        # board - and it is a contract, so it is pinned: unmeshed parts must
        # come back empty rather than quietly meshing themselves again.
        doc0 = read_step(step)
        raw_parts, ct0 = collect_parts(doc0)
        unmeshed = [(n, c, sh, l, []) for n, c, sh, l in raw_parts]
        pos0, _n0, _c0, idx0, _e0, _ei0, _st0 = tessellate(
            unmeshed, colour_lookup(ct0), linear=auto_deflection(raw_parts),
            angular=ANGULAR, doc=doc0)
        check(len(pos0) == 0 and len(idx0) == 0,
              "tessellate reads a mesh, it does not make one",
              f"{len(pos0) // 3} vertices from unmeshed parts")

        # The auto deflection has to be a number and has to scale with the
        # model, since a fixed millimetre is the wrong unit for both a pin and
        # a panel.
        doc = read_step(step)
        parts, _ct = collect_parts(doc)
        deflection = auto_deflection(parts)
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
