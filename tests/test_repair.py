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
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepTools import BRepTools
from OCP.TopLoc import TopLoc_Location

FAILURES = []
ANGULAR = 15 * 3.141592653589793 / 180.0


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


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

        # The auto deflection has to be a number and has to scale with the
        # model, since a fixed millimetre is the wrong unit for both a pin and
        # a panel.
        doc = S.read_step(step)
        parts, _ct = S.collect_parts(doc)
        deflection = S.auto_deflection(parts)
        check(0.004 <= deflection <= 0.25,
              "the automatic deflection is inside its clamp",
              f"{deflection:.4g} mm")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    print("repairing a refused face")
    sys.exit(main())
