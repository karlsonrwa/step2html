"""Colours and geometry: the two things that have been quietly wrong before.

Colour is found by the IDENTITY of a shape, so it survives neither a moved
copy nor a face that has been replaced. Geometry is checked against a second
opinion from OCCT rather than against itself.
"""
from __future__ import annotations

import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import step_to_html as S
from fixtures import (BODY, PIN, PIN_AT, PLATE_A, PLATE_B, RIM,
                      coloured_assembly)

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepBndLib import BRepBndLib
from OCP.TopoDS import TopoDS_Compound

FAILURES = []


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        step = coloured_assembly(Path(tmp) / "fixture.step")
        doc = S.read_step(step)
        parts, color_tool = S.collect_parts(doc)
        linear = S.auto_deflection(parts)
        angular = 15 * 3.141592653589793 / 180.0
        parts, _rescued, left = S.repair_parts(
            parts, color_tool, linear, angular, lambda _m: None)
        pos, nrm, col, idx, epos, eidx, stats = S.tessellate(
            parts, color_tool, linear=linear, angular=angular)

        seen = Counter(tuple(col[i:i + 3]) for i in range(0, len(col), 3))

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
        check(S.DEFAULT_RGB not in seen,
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
        rx0, ry0, rz0, rx1, ry1, rz1 = box.Get()
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
        check(tx1 > PIN_AT[0], "the placed part really is out at its transform",
              f"model reaches x={tx1:.1f}, the pin sits at x={PIN_AT[0]:.0f}")

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

        # ---- what came out ------------------------------------------------ #
        check(stats["triangles"] > 0 and stats["edges"] > 0,
              "there are triangles and edges",
              f"{stats['triangles']} tri, {stats['edges']} edge segments")
        check(stats["edges_from_mesh"] > 0 and stats["edges_from_curve"] == 0,
              "every edge comes from the triangulation, none from the fallback",
              f"{stats['edges_from_mesh']} from the mesh")
        check(not left, "every face meshed")

    return 1 if FAILURES else 0


if __name__ == "__main__":
    print("colours and geometry")
    sys.exit(main())
