# Speed, and where it went

*[English](performance.md) · [Русский](performance.ru.md)*

Part of [step2html](../README.md).

Profiled on the 927-face rigid-flex test board, 2.4 MB of STEP, four builds:
**34.4 s before, 20.7 s after**, same mesh chosen. One build at the finest
setting went from 11.5 s to 6.8 s. Almost none of it was where a profiler
pointed — cProfile accounted for 2 s of Python in an 11.5 s build, because the
rest is inside OCCT, so the numbers below are wall clock around each phase.

Two things paid, and both were work that produced nothing:

* **The patch attempts were in the wrong order.** A face the mesher refuses is
  retried on a copy, plainly first and split second, at five deflections. But
  a plain copy at the model's own deflection is the one attempt something is
  known about: the mesher has just refused that very face at exactly those
  numbers. On this board each of the four conical pin tips took **0.85 s to be
  refused again and 0.01 s to build once split** — ten refused faces, 3.40 s
  spent, of which 0.05 s did anything. The split now goes first, and only at
  that first deflection; coarser, a plain patch is still worth trying first,
  because it keeps the face whole. Repair: 5.1 s → 1.7 s.
* **The shape was meshed twice.** `tessellate` opened with its own
  `BRepMesh_IncrementalMesh`, on parts that had just been meshed with the same
  numbers, and that call re-meshes rather than noticing the triangulation
  already carries the deflection asked for: 1.2 s a build. Removing it also
  settled something quieter — before, the repair decided which faces were
  empty on one triangulation and the geometry was then taken from another, and
  the two did not always agree. The proof is in the counts: identical settings
  gave 132,005 triangles then and 132,013 now.

Where the remaining 6.8 s goes, per build:

| | |
|---|---|
| meshing, `BRepMesh` | 1.7 s |
| tessellation, the Python loop over 105k nodes and 132k triangles | 1.9 s |
| `pack` — struct, the normals byte pass, deflate at level 9 | 0.9 s |
| edges from the triangulation | 0.5 s |
| the page, substitution and escaping | 0.2 s |
| reading the STEP — **once**, not per build | 1.7 s |

What is left on the table, measured rather than guessed: the per-node transform
can be done in Python instead of through `gp_Pnt.Transformed`, worth 0.09 s;
deflate at level 6 is no faster here and marginally worse; and the normals
could come from OCCT's own surface normals instead of being averaged from
facets in Python, which would be both quicker and truer, but changes the
shading and is a piece of work rather than a tweak. The largest remaining
lever is not in the code at all: a build that overshoots the budget is thrown
away, and this board throws one away every time — `--max-bytes none` is one
build and about seven seconds.
