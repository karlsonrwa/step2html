# step2html

Turn a STEP assembly into **one self-contained interactive HTML file**.

```bash
python step_to_html.py board.step
```

That writes `board.html` beside it. Double-click it: the model spins in any
current browser, on a phone as well as a desktop. No Acrobat, no plugin, no
internet, no server, and nothing to install for whoever you send it to.

Or with a window around it:

```bash
python gui.py
```

Every flag below has a control there, a log coloured the way Simple 3D colours
its own, a progress bar and a Cancel button. The conversion runs in a **child
process**: OpenCASCADE can die outright rather than raise, and a thread taking
that hit would take the window with it, leaving nothing written anywhere. The
window remembers its settings in `step2html_config.json` beside the script.

The bar tracks the current build, phases taking their share of it by roughly
what they cost, and moves per FACE inside the long ones - a real board is one
part with 900 faces, and per-part progress would sit still through the whole
of it. The label says which build it is, `build 3 of at most 6`; the bar
starts again for each, which is honest, since with a size budget the number of
builds is not knowable until the sizes come back.

The window opens centred on a first run and afterwards where it was left,
maximized if it was closed maximized. A remembered position that is no longer
reachable - the monitor it was on has been unplugged - is ignored and the
window is centred instead, rather than opening somewhere invisible.

It works on any STEP, not only on boards.

---

## Why not a 3D PDF

A 3D PDF is a PDF with a `/3D` annotation holding **U3D** or **PRC** — no
other format goes in. Both are viewable only in desktop Adobe Acrobat, where
3D content is **off by default**, and not at all in browser PDF viewers, on
iOS or on Android. U3D has been unmaintained since 2010; the only free PRC
writer is the one Asymptote carries, under LGPL-3.0, and FreeCAD's own 3D PDF
export is still an unmerged draft PR.

An HTML page opens everywhere and can be made to **report its own damage**,
which a PDF cannot.

## What is in the file

* Board or model geometry, tessellated, coloured **per face** with the part
  colour as the fallback — so a layer-coloured board arrives layer-coloured.
* Real B-rep edges, drawn like a CAD viewer's "shaded with edges".
* A viewer written in plain WebGL2: **no three.js, no CDN, no fonts, nothing
  external at all.**
* The geometry as one raw-deflated, base64 block with its length and CRC32
  beside it. The page checks both **before it draws** and says the file is
  damaged rather than drawing something untrue.

## Options

```
step_to_html.py STEP [-o OUT] [--title TITLE] [--deflection MM]
                     [--angle DEG] [--max-bytes N] [--no-repair] [--read-only]
```

| | |
|---|---|
| `--deflection` | mesh deflection in mm, or `auto` (default) — scaled to the model |
| `--angle` | angular deflection in degrees, default 15 |
| `--max-bytes` | size budget, default `auto` = the size of the STEP itself; `none` lifts it |
| `--no-repair` | do not try to rescue faces the mesher leaves empty |
| `--read-only` | set the read-only attribute, so Notepad refuses to save over it |

The default budget refines the mesh as far as it can while the `.html` stays
smaller than the `.step` it came from.

Size against quality is close to a power law, so two measurements give the
exponent for that particular model and the third build goes more or less
straight to the budget - three or four builds, where a fixed ladder took
seven. What is **not** predicted is the answer: every setting that gets kept
has been built and weighed, and the fit only chooses where to look next. How
well a payload deflates depends on the model, and no formula knows it.

Pass `--max-bytes none` for a single build.

## Requirements

Python 3.10+ and [`cadquery-ocp`](https://pypi.org/project/cadquery-ocp/)
(OCCT). Nothing else.

```bash
pip install cadquery-ocp
python tests/run_all.py
```

---

## Things already tried, and why it is the way it is

Every item here cost at least one round and would be re-broken by an obvious
looking simplification.

**Colour is found by the identity of a shape.** Not by its label — OCP binds
only the `TopoDS_Shape` overload of `GetColor`, and `GetColor_s` is the
unrelated "this label *is* a colour entry" call. And **never move a shape
before looking its colour up**: on a test board all 69 faces resolve on the
stored shape and *none* of them resolve after `.Moved()`, which paints the
whole model one flat colour. The location travels alongside and is applied to
the tessellated points instead.

**OCCT returns linear colour components.** Read raw, `#B87333` copper arrives
as `(122, 44, 8)`. They are encoded to sRGB on the way out and the shader
linearises again before lighting.

**Some faces cannot be meshed at any setting.** On a real connector, four
conical pin tips stayed empty at 0.04 mm, at 0.01 and at 0.002 — and a finer
mesh made it *worse*, not better. Every mesher parameter (`MinSize`,
`AdjustMinSize`, `AllowQualityDecrease`, `Relative`, `ForceFaceDeflection`)
changed nothing, and `ShapeFix` had nothing to fix because `BRepCheck` calls
those faces valid. They are closed periodic faces parametrised from π to 3π
instead of 0 to 2π. Splitting them in two removes the seam and they mesh.

**Patch one face at a time, on a copy.** `ShapeUpgrade_ShapeDivideClosed`
turned loose on a whole solid cuts *every* closed face in it, including the
sound cylindrical shafts of the pins, which then mesh as two halves that do
not meet and carry an invented edge down each one. `tests/test_repair.py`
exists to catch exactly that.

**A patch need not be built at the model's deflection.** That is what breaks
the deadlock, because refining the mesh makes some faces fail that were fine
before — two 0.12 mm² planes fail at 0.0076 mm and build at 0.019. A face
that will not build at the chosen setting is simply built coarser; on a plane
that is not even a visible difference.

**Edge lines come from the triangulation, not from the curve.**
`Poly_PolygonOnTriangulation` gives the indices of the mesh's own nodes along
an edge, so a line segment *is* the triangle edge under it: same vertices,
identical depth, and `depthFunc(LEQUAL)` settles the tie.

Sampling the true curve instead — the obvious thing, and what this did first —
puts a smooth line over a faceted surface with up to one deflection of depth
between them. Covering that needs a bias of at least one deflection, while a
line must stay thinner than a copper layer to avoid showing through it. On a
real board those two demands crossed: 0.023 mm of deflection against 0.018 mm
of copper, and **no value satisfies both**.

**Nothing is done to the fills.** `glPolygonOffset` was tried on them twice
and is wrong both ways round. With a slope factor it multiplies the polygon's
maximum depth slope, which runs away for a face standing edge-on to the
camera — a cylinder's silhouette, an oblique end cap — pushing it behind the
far wall of its own solid, so a solid capacitor rendered as an open tube.
Without the slope factor the constant nudge is far too small on exactly those
steep faces, and the edge lines break into dashes along the rim of a board
seen nearly edge-on. What is left is a fixed 1e-5 of clip depth applied to
the *lines*, which answers nothing but the difference between how a line and
a triangle are rasterised.

**Page height comes off the viewport, not off a `height:100%` chain.** The
chain collapses to zero wherever an ancestor has no height, and on a phone
`100vh` counts the space under the collapsing address bar. `100dvh` is the
visible height.

**The bar goes wherever it leaves the squarest view behind.** Across the top
it costs height, down the side it costs width, and which of those hurts
depends on the shape of the window - a phone held sideways makes an already
wide view wider still. Both layouts are measured for real rather than guessed
from an `(orientation: landscape)` media query, because the thickness of the
bar is whatever its contents and wrapping make it. Measured across eight
window shapes, every one picks the better of the two: 780x360 keeps 1.75 at
the side against 2.70 on top, 360x780 keeps 1.76 on top against 3.45 at the
side, and 1024x768 comes out at 1.16.

Four things here are load-bearing, and three of them were found by getting
them wrong first.

*The side column must size to its widest CONTROL and must not wrap.* Stretch
it, or let it spill into a second column, and it grows wide enough to lose
every comparison it is put up against - the side layout is then never chosen
and the whole mechanism looks dead while computing perfectly. The title and
the statistics are kept out of that width with `width:0; min-width:100%`, so
they wrap inside the column the controls decided on.

*The observer must be kept in a variable.* Written as
`new ResizeObserver(...).observe(x)` nothing holds a strong reference to it,
and it stops firing whenever the collector takes it. That is how this shipped
at first: the layout was chosen once at load and never again, and every
redraw that made it look alive was coming from somewhere else.

*The decision runs twice - immediately, and again next frame.* Measuring only
inside the event catches layout that has not settled; waiting only for an
animation frame means it never happens at all in a view that is not producing
frames.

*The observer watches the BODY, never the view* - the view is what this
resizes, and an observer on it would answer its own change for ever.

**The help button needs a stacking order.** It is fixed to the screen's top
right corner, so in the side layout it reaches out across the canvas - and
`#bar` comes before `#view` in the markup with neither carrying a `z-index`,
so the canvas paints straight over it and the button is simply not there.
Worth knowing how this hides: `getBoundingClientRect()` reports the button in
its right place whether or not anything covers it, so a geometry check passes
while nothing is on screen. `elementFromPoint` is what answers the question
actually being asked.

**Touch needs two pointers.** A phone never sends a `wheel` event, so without
the two-pointer case there is no way to zoom on one at all.

## Licence

MIT. See [LICENSE](LICENSE).
