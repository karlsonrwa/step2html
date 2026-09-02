# step2html — STEP → один интерактивный HTML

*[English](#english) · [Русский](#русский)*

---

<a name="english"></a>
# English

# ⚠️ Disclaimer

Everything in this repository has been created through vibe coding with Claude.
I am not a professional software developer. My background is in hardware engineering, and this project exists solely because I wanted to solve problems I encountered in my own workflow.
I am not proficient in Python. Instead, I focus on clearly defining the behavior I expect from the tool and iteratively refining it until it does what I need.
If you find a bug, an issue, or have an idea for improvement, please feel free to open an Issue or submit a Pull Request. I will do my best to investigate and fix it, but I cannot promise a quick response.
Although this project was developed using an AI-assisted workflow, I make an effort to validate the generated code in real-world use and rely on this tool in my own projects.

## Why this exists

Sending a 3D model to somebody who has no CAD is awkward. The usual answer is a
3D PDF, and it is a poor one: a 3D PDF is a PDF with a `/3D` annotation holding
**U3D** or **PRC**, no other format goes in, and both are viewable only in
desktop Adobe Acrobat — where 3D content is **off by default** — and not at all
in browser PDF viewers, on iOS or on Android. U3D has been unmaintained since
2010; the only free PRC writer is the one Asymptote carries, under LGPL-3.0;
and FreeCAD's own 3D PDF export is still an unmerged draft pull request.

**step2html** writes one self-contained HTML file instead. It opens by
double-click in any current browser, on a phone as well as a desktop, with no
Acrobat, no plugin, no internet, no server and nothing to install for whoever
you send it to. It can also **report its own damage**, which a PDF cannot.

It works on any STEP, not only on boards.

## How it works

```bash
python step_to_html.py board.step
```

That writes `board.html` beside it. Or, with a window around it:

```bash
python gui.py
```

Inside the file:

* Geometry tessellated with OCCT, coloured **per face**, falling back to the
  solid the face belongs to and then to the part — so a layer-coloured board
  arrives layer-coloured.
* Real B-rep edges, drawn the way a CAD viewer draws "shaded with edges".
* A viewer written in plain WebGL2: **no three.js, no CDN, no fonts, nothing
  external at all.**
* The geometry as one raw-deflated, base64 block with its length and CRC32
  beside it. The page checks both **before it draws** and says the file is
  damaged rather than drawing something untrue.

In the viewer: drag to turn, wheel or pinch to zoom, right button or two
fingers to pan, **a single click moves the centre of rotation onto the point
under it**, double click resets. Orthographic or perspective, edges on or off,
and a theme that follows the system until told otherwise.

The small cube in the bottom right corner raises a menu of the eight standard
views — top, bottom, front, back, left, right, and isometric from above or
below. Each one reorients and refits. A click anywhere else closes the menu
and changes nothing.

Front is the view from **−Y**, with **+X** to the right and **+Z** up; back is
its opposite. If a board's own idea of front is the other way round, it is one
line in `VIEWS`.

Tick **Measure** and two clicks give the distance between the points, with
ΔX/ΔY/ΔZ beside it — computed in model space, so the number is millimetres and
owes nothing to the projection it is looked at through, and shown **to a
thousandth**. The file can carry that: the coordinates are float32 about the
middle of the model, so on a 160 mm board one step of the format is some five
millionths of a millimetre. What the third decimal is *worth* is a different
question, answered under Known limitations. A third click starts again. Measuring is a mode rather than a modifier because a plain click
already means "turn about this point", and one gesture cannot honestly mean
two things.

A measurement **snaps to the centre of a circle**. Hovering within about 14
pixels of a circular edge — the rim of a hole, the end of a pin — catches that
circle: its rim is drawn as a ring before the click, and the click takes the
centre rather than the point under the cursor. The rims of the two points that
were taken stay drawn, so a finished measurement, and a picture saved of it,
says plainly that it was taken centre to centre and not by eye.

The catch is made on the **rim** and not on the wall of the hole, because an
arc has an exact centre while a cylinder only gives an axis — the height along
it would be wherever the cursor happened to be. And it is tested against the
**visible** point under the cursor, which is what stops it catching a hole on
the far side of the board. The circles are found once, in Python, from the
edges whose curve is a circle, and one hole is one entry however its rim is
cut into arcs or shared between faces: on a 927-face board that is 545 circles,
15 kB raw and **3.9 kB in the finished file — a quarter of a percent**.

While measuring, the face under the cursor lights up and the line follows the
cursor with the distance updating as it goes. The highlight costs almost
nothing to carry: the triangles of one face are contiguous, so the file needs
a single start index per face — 13 kB raw and 4.6 kB deflated on a 3286-face
board, against 299 kB for an id on every triangle. A ray cast per mouse move
is 7.6 ms on a 300k-triangle board, throttled to one per 16 ms and only while
measuring.

After the second click the measurement also draws the **stepped path** a CAD
viewer draws: from the first point along X, then Y, then Z to the second, each
leg in its own colour and carrying its own number. A leg of no length is not
drawn at all. The same three colours label the **axis triad** in the bottom
left corner — X red, Y green, Z blue, in **two sets**, because one cannot be
right on both backgrounds: light enough to carry on the dark theme, saturated
instead of pale on the light one, and a single middling set reads as muted on
both. The triad shows orientation and nothing
else: no projection, no distance, no pivot. Checked against the named views,
where it is unambiguous: from the top the Z arm collapses to a point, from the
front the Y arm does and Z stands straight up.

The reading itself parks in **the corner of the view furthest from the
measurement**, on a thin lead back to the middle of the line. In the middle of
that line, which is where it sat before, it covered the very thing being
measured. The corner is chosen against points sampled *along* the legs and not
only at their ends — a corner far from both ends can still sit squarely on top
of a long leg. Drag it if the corner chosen is the wrong one; it then holds
that place until the measurement is cleared, and is clamped back into view if
the window is narrowed under it.

**No corner is empty**, and which of them are occupied is asked of the
elements rather than written down as numbers. That distinction was a bug: the
two bottom corners were numbers, so the reading cleared the view cube and the
axis triad, while the help button — fixed to the top right of the *window*,
which in the side layout is over the canvas — had no number of its own and was
quietly slid under. Each corner is now taken as given horizontally and pushed
inwards until nothing is beneath the label.

**Save PNG** writes out **what is on screen**, not just the triangles: the measurement, its stepped path, the numbers, the centre of rotation and the axis triad are all DOM and SVG, so they are drawn again onto a 2D canvas over the WebGL image, read back off the live elements so the file cannot disagree with the screen. The keys `1`–`8` pick
the eight views, `E` edges, `P` projection, `M` measuring, `Esc` clears. And
the address bar always names the view on screen, so sending somebody a link to
one corner of the board is a copy away.

## Installation

Python 3.10 or newer, and one dependency. From the project folder:

```bash
python -m pip install -r requirements.txt
```

```bash
python tests/run_all.py
```

`python -m pip` rather than `pip`, and **from the project folder**, and both
for reasons that have bitten already. A machine with several Pythons on it can
have a `pip` belonging to a different one from the `python` you will run this
with — which is exactly how the window ends up unable to start. And the
requirements file installs `.`, the current directory, so pip run from
somewhere else looks for a project where you are standing and says so.

The file lists no dependencies of its own. There is one, `cadquery-ocp`, and it
is declared in `pyproject.toml`; a second copy would be a second list to keep in
step. `-e .` makes pip read that one. Editable, so the folder you edit stays the
folder that runs — and it puts `step2html` and `step2html-gui` on that Python's
PATH, the second of which is a windowed entry point and so another way past the
vanishing console described below.

`cadquery-ocp` is OCCT. Nothing else is needed, and nothing else is used.
Tested against 7.9.3 on Python 3.12.

## The GUI

**Start it with `step2html.cmd`**, or with `python gui.py` from a console.
Double-clicking `gui.py` is the one way that can quietly fail: Windows hands a
`.py` to whichever Python the file association picks — usually the `py`
launcher — and on a machine with several Pythons installed that need not be the
one OCP is in. The window then cannot start, says exactly why, and says it to a
console that closes in the same instant, so what you see is a black flash. It
has been reported twice, with the same workaround both times: a batch file,
which keeps the console alive.

Two things about that are now fixed. The reason goes into a **dialog** — with
the interpreter that is running named in it, which is the fact that settles the
question — because tkinter is in the standard library and is there whatever
else is missing. And `step2html.cmd` ships beside the script: it runs `python`
from `PATH`, or whatever `STEP2HTML_PYTHON` points at, and pauses on a failure
so the reason can be read.

Every command line flag has a control, a log coloured the way Simple 3D colours
its own, a progress bar and a Cancel button. The conversion runs in a **child
process**: OpenCASCADE can die outright rather than raise, and a thread taking
that hit would take the window with it, leaving nothing written anywhere. The
window remembers its settings in `step2html_config.json` beside the script.

The bar tracks the current build, phases taking their share of it by roughly
what they cost, and moves per FACE inside the long ones — a real board is one
part with 900 faces, and per-part progress would sit still through the whole of
it. The label says which build it is, `build 3 of at most 6`; the bar starts
again for each, which is honest, since with a size budget the number of builds
is not knowable until the sizes come back.

The window opens centred on a first run and afterwards where it was left,
maximized if it was closed maximized. A remembered position that is no longer
reachable — the monitor it was on has been unplugged — is ignored and the
window is centred instead, rather than opening somewhere invisible.

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

**The output name is finished for you.** A name given without an extension
gets `.html`, and it is **appended, never substituted** — `board rev.3` becomes
`board rev.3.html`, because `with_suffix` would have made it `board rev.html`
and thrown the revision away. A name that already ends in `.html` or `.htm` is
left exactly as it was typed, whatever case it is in, and a path that is an
existing folder takes the STEP's own name inside it rather than becoming a file
sitting next to that folder. The rule lives in one function that both front
ends call, so the window's field cannot promise a name the pipeline does not
write.

The default budget refines the mesh as far as it can while the `.html` stays
smaller than the `.step` it came from.

Size against quality is close to a power law, so two measurements give the
exponent for that particular model and the third build goes more or less
straight to the budget — three or four builds, where a fixed ladder took seven.
What is **not** predicted is the answer: every setting that gets kept has been
built and weighed, and the fit only chooses where to look next. How well a
payload deflates depends on the model, and no formula knows it.

Pass `--max-bytes none` for a single build.

## Speed, and where it went

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

## Standalone

For a machine with no Python and no OCP on it:

```bash
python -m pip install pyinstaller
packaging\build.cmd
```

`STEP2HTML_ONEDIR=1` builds a folder instead of one file, `STEP2HTML_CONSOLE=1`
a console build for checking from a shell. Everything lands in `dist\`.

| | one file | a folder |
|---|---|---|
| on disk | **82.4 MB** | 306.5 MB, 1066 files |
| zipped, to send | 82.4 MB | **82.7 MB** |
| start, to first response | 8.1–9.3 s | **3.05 s** |

Measured the same way for both — the folder wins on every launch and costs
nothing to send, because zip compresses the same bytes the one-file bootloader
does. What one file buys is that there is nothing to unpack by hand.

**Where the weight is**, and none of it is ours: `OCP.pyd` 94 MB, the OCCT DLLs
it links against 65 MB, **VTK 135 MB**, Python and Tk about 12. VTK is not used
here by a single line, and it still cannot go — measured, in two steps. Without
`vtk.libs` at all, `OCP/__init__.py` dies on `os.add_dll_directory`, which it
calls for that folder with no `isdir()` guard, unlike the line above it that
does exactly that for `cadquery_ocp.libs`. With an **empty** `vtk.libs`, the
directory is accepted and `OCP.pyd` then fails to load: Windows resolves every
name in an import table at load time, and six VTK DLLs are in that table.

**The standard library is left alone.** Excluding the parts this tool does not
use — `http`, `urllib`, `email`, `asyncio` — looked free and was not: `pathlib`
imports `urllib` for `as_uri()`, so the build came up dead with *No module
named 'urllib'* out of `pathlib`, in a dialog, twice over, before a line of
ours had run. All of `base_library.zip` is 1.2 MB of a 306 MB bundle.

**Check a build with `--selftest`:**

```bash
dist\step2html.exe --selftest some.step
```

It drives the *window's* machinery headless — Tk up, Generate pressed, the
channel pumped until the child answers — and writes `some.selftest.html`. That
path is worth its own check because the command line never starts a child
process, so a binary can convert perfectly from a shell and still fail the
moment somebody presses Generate. The result is a file rather than a message
because a windowed build has nowhere to print.

A frozen build stamps pages with the version and **no commit hash**: there is
no repository beside an executable to ask.

On the eight seconds a one-file build spends unpacking: PyInstaller can show a
**splash image** during it, and that image appears before Python starts, which
is the right moment. But the only thing a program can change on it is one line
of text, through `pyi_splash.update_text()`, and only once Python is running —
by which time the wait is over. The bootloader reports no progress to anyone,
so a real progress bar is not available, and a frozen one reads worse than
none. The folder build removes the wait instead of decorating it.

## Package layout

| | |
|---|---|
| `step_to_html.py` | the whole pipeline, and the page template. `convert(Options, log, progress)` is the one entry point; `main()` is a thin CLI over it |
| `gui.py` | the window. Builds the same `Options` and hands it to the worker |
| `worker.py` | `convert` in a child process. Must never import tkinter: on Windows the child is spawned and re-imports it |
| `step2html.cmd` | starts the window with a Python of your choosing, and holds the console open if it fails |
| `requirements.txt` | `-e .`, so one command installs the one dependency that `pyproject.toml` declares |
| `packaging/` | the standalone build: `build.cmd`, the PyInstaller spec, and the launcher that is the frozen entry point |
| `tests/` | four suites, `python tests/run_all.py`, about twelve seconds |
| `docs/` | the architecture as it stands, the review log by date, and the plan for taking the monoliths apart |

The CLI and the window share one code path on purpose. A second implementation
of the pipeline behind a GUI is how the two drift apart, and
`tests/test_gui.py` fails if a flag ever gains no control.

## Versions

Semantic, bumped by hand, and the number lives in `__version__` in
`step_to_html.py` — `pyproject.toml` reads it from there, so there is one place
to change and nothing to keep in step. A patch is a fix; a minor is a new
capability or a change to what the generated file looks like.

Every generated file states what made it, at the foot of its own help: the
version, the short commit, the source STEP's name, the mesh actually used and
the date. The commit matters more than it looks — between two files carrying
the same version there can be a dozen commits of repairs, and the hash is what
pins the source when one of them comes back with a question. A file built from
an edited working tree says `+edits`, because it cannot be reproduced from the
commit it names.

There is also `<meta name="generator">` in the head, so every file made by a
given version can be found with an ordinary search through a folder.

This is separate from the **payload format version** in the `S3DH` header,
which is at 4 and answers a different question: whether the viewer can read
those bytes at all.

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

**A colour can sit on the SOLID rather than on its faces**, and the lookup has
to go face, then the solid the face belongs to, then the part, then grey. XCAF
hangs one colour on the solid and lets the faces inherit it, overriding only
the ones that differ. A real board arrived with its body colour on the solid
and 11 of its 63 faces carrying nothing of their own: those 11 fell past the
missing step straight to the default grey, and that was **44 % of the
surface** — the whole board face, rendered light grey while the file plainly
contained `#1A5924`.

Worth knowing how the fixture for this went wrong twice, because both are easy
to repeat. Given the same colour as another part, the check passed on that
other part's colour. Given a part with ONE solid in it, the part-level lookup
finds the colour by itself and the check passes whether or not the solid is
ever consulted. It takes two solids, two colours, and no face colours at all —
and the way to know is to break the fix on purpose and watch the test fail.

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
sound cylindrical shafts of the pins, which then mesh as two halves that do not
meet and carry an invented edge down each one. `tests/test_repair.py` exists to
catch exactly that.

**A patch need not be built at the model's deflection.** That is what breaks
the deadlock, because refining the mesh makes some faces fail that were fine
before — two 0.12 mm² planes fail at 0.0076 mm and build at 0.019. A face that
will not build at the chosen setting is simply built coarser; on a plane that
is not even a visible difference.

**Edge lines come from the triangulation, not from the curve.**
`Poly_PolygonOnTriangulation` gives the indices of the mesh's own nodes along an
edge, so a line segment *is* the triangle edge under it: same vertices,
identical depth, and `depthFunc(LEQUAL)` settles the tie.

Sampling the true curve instead — the obvious thing, and what this did first —
puts a smooth line over a faceted surface with up to one deflection of depth
between them. Covering that needs a bias of at least one deflection, while a
line must stay thinner than a copper layer to avoid showing through it. On a
real board those two demands crossed: 0.023 mm of deflection against 0.018 mm
of copper, and **no value satisfies both**.

**Nothing is done to the fills.** `glPolygonOffset` was tried on them twice and
is wrong both ways round. With a slope factor it multiplies the polygon's
maximum depth slope, which runs away for a face standing edge-on to the camera
— a cylinder's silhouette, an oblique end cap — pushing it behind the far wall
of its own solid, so a solid capacitor rendered as an open tube. Without the
slope factor the constant nudge is far too small on exactly those steep faces,
and the edge lines break into dashes along the rim of a board seen nearly
edge-on. What is left is a fixed 1e-5 of clip depth applied to the *lines*,
which answers nothing but the difference between how a line and a triangle are
rasterised.

**Orientation is a matrix, not a yaw and a pitch.** Angles have poles: pitch
has to be stopped just short of straight down, or crossing it flips the horizon
and reverses what a sideways drag does. That stop is something a drag runs
into. A matrix turned about the axes of the screen has nowhere to run into.
Gram-Schmidt once per drag, because a rotation multiplied by another a few
thousand times in float32 stops being one.

**A single click moves the centre of rotation onto the point under it**, the
way a CAD viewer does, which is what makes a large board inspectable: turning
and zooming then work on the detail being looked at. The ray is cast against
the triangles on the CPU, because the depth buffer of the default framebuffer
is not readable in WebGL; at 150k triangles that is a few milliseconds, once
per click.

Moving the pivot must not move the picture, and the arithmetic for that is one
line — put the camera translation exactly where the picked point already sits
in view space — but it holds only in perspective. In an orthographic view the
DISTANCE IS THE ZOOM, so changing it rescales everything. Hence `cam.oh`, the
orthographic half-height, kept as a number of its own: the wheel moves it
together with the distance, a click moves the distance alone. The pick ray has
to be built from `cam.oh` as well, or it is cast at the wrong scale, picks the
wrong triangle, and drags the clipping planes off with it.

The point picked is **marked on screen** — a ring and crosshair that pulses
where the click landed, stays up for the whole of a turn and fades after it. It
is an HTML overlay whose position is projected once per frame rather than a
second draw call, so CSS animates it for nothing. Being the centre of the turn,
it is the one thing on screen that does NOT move while the view rotates, which
is the clearest possible statement of what it is.

**The help button needs a stacking order.** It is fixed to the screen's top
right corner, so in the side layout it reaches out across the canvas — and
`#bar` comes before `#view` in the markup with neither carrying a `z-index`, so
the canvas paints straight over it and the button is simply not there. Worth
knowing how this hides: `getBoundingClientRect()` reports the button in its
right place whether or not anything covers it, so a geometry check passes while
nothing is on screen. `elementFromPoint` is what answers the question actually
being asked.

**Page height comes off the viewport, not off a `height:100%` chain.** The
chain collapses to zero wherever an ancestor has no height, and on a phone
`100vh` counts the space under the collapsing address bar. `100dvh` is the
visible height.

**The bar goes wherever it leaves the squarest view behind.** Across the top it
costs height, down the side it costs width, and which of those hurts depends on
the shape of the window — a phone held sideways makes an already wide view
wider still. Both layouts are measured for real rather than guessed from an
`(orientation: landscape)` media query, because the thickness of the bar is
whatever its contents and wrapping make it. Measured across eight window
shapes, every one picks the better of the two: 780×360 keeps 1.75 at the side
against 2.70 on top, 360×780 keeps 1.76 on top against 3.45 at the side, and
1024×768 comes out at 1.16.

Four things there are load-bearing, and three of them were found by getting
them wrong first.

*The side column must size to its widest CONTROL and must not wrap.* Stretch
it, or let it spill into a second column, and it grows wide enough to lose
every comparison it is put up against — the side layout is then never chosen
and the whole mechanism looks dead while computing perfectly. The title and the
statistics are kept out of that width with `width:0; min-width:100%`, so they
wrap inside the column the controls decided on.

*The observer must be kept in a variable.* Written as
`new ResizeObserver(...).observe(x)` nothing holds a strong reference to it, and
it stops firing whenever the collector takes it. That is how this shipped at
first: the layout was chosen once at load and never again, and every redraw
that made it look alive was coming from somewhere else.

*The decision runs twice — immediately, and again next frame.* Measuring only
inside the event catches layout that has not settled; waiting only for an
animation frame means it never happens at all in a view that is not producing
frames.

*The observer watches the BODY, never the view* — the view is what this
resizes, and an observer on it would answer its own change for ever.

**A menu that closes on an outside click needs the click SWALLOWED**, not
merely noticed. A listener that closes the menu still lets the same press
reach the canvas underneath, which turns the model or moves the centre of
rotation — and the requirement was that choosing nothing changes nothing. A
transparent scrim over everything, shown with the menu, is what makes that
true; measured at 0 % of pixels changed.

The six standard views are built from a BASIS — the direction the camera sits
in and which way is up — rather than from angles. There is no ordering to get
wrong, and each view reads as what it is. Measured on a 160 × 80 board: top
and bottom fill 47.6 % of the frame with a 2:1 outline, left and right 1.8 %
with a 3.76:1 one, the isometrics 22.1 % at 1.69:1.

**The orthographic pick ray must start in front of the model**, not on the
camera plane. On the camera plane anything nearer to the viewer sits behind
the ray's origin and is discarded by the `t > 0` test — while still being
drawn, because the near clipping plane is `span*4` further back. `cam.dist`
shrinks both when the wheel turns and when a click puts the centre of rotation
on a near surface, so that plane can end up inside the model and visible faces
stop being pickable. Parallel rays hit the same thing wherever they start, so
moving the origin costs nothing.

**A canvas has to be downloaded through a blob, not a data: URL.** Chrome
refuses to download a data: URL past about two megabytes, and a full-screen
shot of a board on a dense display runs to several - so Save PNG quietly did
nothing at all, with no error anywhere. `toBlob` plus `createObjectURL` has no
such limit.

**A stray newline inside a JS string breaks the whole page.** Python writes
the viewer as text and cannot tell; the browser then runs nothing at all, so
the symptom is a blank page rather than a broken feature, and every control
looks dead at once. It cost an afternoon of hunting in the renderer for a
fault that was one lost backslash in a patch. `tests/test_page.py` now counts
quotes per line of the generated script, and that check has been shown to fail
on a deliberately broken one.

**Touch needs two pointers.** A phone never sends a `wheel` event, so without
the two-pointer case there is no way to zoom on one at all.

## Reviewed

### 2 Sep 2026, at 0.9.6

A fourth pass, over everything, with a different question this time: not only
what is wrong, but what here is a monolith and what could be carried into
another project as it stands. The full list with reproductions, the structural
and functional diagrams, and the plan for taking the monoliths apart are in
`docs/` — [review-2026-09-02.md](docs/review-2026-09-02.md),
[architecture.md](docs/architecture.md),
[refactoring-plan.md](docs/refactoring-plan.md). Nothing in the code was
changed by this pass; the fixes are the first phase of the plan.

* **When nothing fits the budget, the FIRST build is kept, not the smallest.**
  The comment says smallest and the log says "keeping N bytes" — with N of
  the build at q = 1.0, which `page` and `rep` still hold because the search
  loop never reassigns them. Reproduced on the fixture with a 1000-byte
  budget: 73,873 and 71,842 bytes built, 73,873 kept.
* **An old Chrome is told the file is damaged.** The page tests for
  `DecompressionStream` and promises Chrome/Edge 80+, but `deflate-raw`
  arrived in Chrome 103; on 80–102 the constructor throws inside the same
  `try` as the unpacking, and the message shown is the wrong one. The floor
  is 103+, and `:has()` in the stylesheet is 105+, degrading gracefully.
* **The size weighed is not the size written.** The budget is checked
  against the page as bytes of LF text, but `write_text` without `newline=`
  lets Windows turn every line ending into CR LF: the file on disk is one
  byte per template line larger than what was weighed - 1,382 on the
  fixture, 73,873 in the log against 75,255 on disk - so a budget of exactly
  the STEP can be missed by that much, and `Report.size` counts a different
  thing from what the search chose. Found while writing the test for the
  first item.
* **`gui` and `worker` install as top-level modules** of those names — a
  collision waiting for a machine with one more package on it. Becomes a
  package, which is the first step of the plan.
* **A patch carries its seam as an edge line** — the very artefact
  `test_repair.py` guards the whole solid against, accepted on the one face.
  Not wrong; undocumented.
* Smaller: `_faces` does not dedupe a face shared by two solids;
  `<Configure>` on the root fires for every child widget; `pack` slices and
  unpacks more than it needs; the quote check in `test_page.py` splits on
  `//` blind; `os` and `TopExp` are unused; a docstring still names
  `simple3d_config.json`; `const on` is shadowed in the key handler;
  `worker.py` states an invariant the spawn does not keep (tkinter *is*
  imported in the child, through `__mp_main__` — what must not happen is
  `Tk()` at module level); this file says 3.12 and twelve seconds where 3.14
  and twenty are also true; no git tags.

Checked and found sound: placeholders both ways, `TEXT`, every id the script
reaches for, no unreferenced function, the payload layout against its header,
and every item of the three earlier reviews.

### 31 Jul 2026, at 0.9.4

A third pass, over everything. One fault, two holes in the suite where the
newest work had none, and three tidyings. The mechanical cross-checks from the
last pass — placeholders against substitutions both ways, `TEXT` keys, every id
the script reaches for, functions nothing calls — all came back clean.

* **Text substituted into the page was then read AS page.** `build_page`
  replaced key by key in a loop, so a value could contain what looks like a
  later placeholder and be rewritten by it. A title is user text — a `--title`,
  or the STEP's own stem — and a title of `__L_ON__` came out on the page as
  **On**. One `re.sub` pass now, so nothing substituted is ever scanned again.
* **The repair had no test at all.** The fixture has no face the mesher
  refuses, which the suite even states, so `_patch_face` — the most delicate
  piece here, and the one whose order was just rearranged for speed — was
  running untested. A refusable face could not be built to order either: five
  constructions of the closed periodic case, π to 3π on a cylinder and on a
  cone, were all meshed happily. So the patch is exercised on a healthy closed
  face instead, which pins what a patch must be whatever asked for it — meshed,
  covering **exactly** the surface it stands in for (area equal to a millionth),
  and split, that last one pinning the order.
* **The circles a measurement snaps to had no geometric test.** They come from
  an edge's curve, which already carries the *edge's* location, and the
  *part's* placement is applied on top by hand — the same hiding place as the
  colour bug of two rounds ago. Now pinned: the fixture's pin gives one circle
  per rim and no more, their centres carry the placement, they sit 6 mm apart,
  and every axis is a unit vector. Proven by breaking it: drop the placement
  and the centres land 40 mm away, back at the origin.
* **Three forced layouts a frame** in `paintMeasure`, one expression asking for
  the same rectangle twice. A `getBoundingClientRect` after a style has been
  written makes the browser lay the page out again to answer; it is asked once
  now.
* **A `hasattr` guard that cannot fail** in the window's `_remembered` —
  `_load_config` sets the attribute unconditionally in `__init__`. The same
  species the first review found in the tests.
* **An assumption worth writing down:** the picture paints the axis triad at an
  offset in CSS pixels into coordinates that are SVG user units, which is only
  the same thing because `#axes` is 88 px wide with a `0 0 88 88` viewBox.

### 31 Jul 2026, at 0.8.0

A second full pass. Three of these are real faults, the rest are the kind of
thing that becomes one later. Everything is fixed, and the two that could be
pinned by a test are pinned by a test **that was made to fail first**.

* **`read_step` raised `SystemExit`.** That derives from `BaseException`, so
  neither `except ConvertError` nor `except Exception` in the worker could
  catch it: a STEP that OCCT refuses to read killed the child process with
  nothing said, and the window then reported the only thing it knows about a
  silent death — "usually a crash inside OCCT", which is both alarming and
  wrong. It is a `ConvertError` now, and the CLI is unchanged because `main()`
  already turns one of those into the same exit.
* **`fail()` threw on its last line.** It ended on `getElementById('hud')`, an
  id renamed away long ago, which returns `null`. Checked on a page with one
  payload character flipped: the message does appear — that line comes first —
  and then `TypeError: Cannot read properties of null`. So anything added
  after it would silently never have run, in the one function whose whole job
  is to keep the page's promise about a damaged file.
* **The view in the address mangled some numbers.** `toPrecision(6)` followed
  by stripping trailing zeros turns `120000` into `12`. `1200` survives,
  because its six-digit form is `1200.00` and has a decimal point to stop at;
  anything from a hundred thousand up has none. The symptom would have been a
  link that quietly restores a different view. The restore side had the
  mirror-image fault: its character class had no `+`, so `1.00000e+6` — which
  the same code produces past a million — could never be read back.
* **Two copies of "set up a named view",** one behind the menu and one behind
  the number keys. Identical today, which is the only moment they ever are.
* **`_mesh_and_count` was dead** — left behind when the repair moved to one
  face at a time.
* **The axis triad's corner was written down twice:** once in the stylesheet,
  once as a constant in the PNG painter. The picture now asks the element
  where it is, which is the rule the rest of that painter already follows.
* **`[c1, c2] = querySelectorAll('circle')`** took the two measurement dots by
  position, and a third circle now exists above them.
* **The canvas drawing buffer was reallocated on every frame** — assigning
  `width`/`height` does that even when the number has not changed.
* **A dragged reading could be left outside a narrowed window,** and an unused
  variable in `savePng`.

Checked and found sound: every placeholder in the template has a substitution
and every substitution has a placeholder, nothing in `TEXT` is unused, every id
the script reaches for exists, and the payload's arrays are where its header
says they are.

### 30 Jul 2026, at 0.3.0

A full pass over the code found eight things, none of which a test had caught,
and all of which are now fixed and mostly pinned:

* The progress label said `build 3 of at most 8` while the search would never
  spend more than 6 — two constants doing one job, one of them stale.
* `tests/test_gui.py` carried a check guarded by `hasattr` on a widget that
  does not exist, so it passed without looking at anything. A check that cannot
  fail is worse than no check: it reads as coverage.
* Choosing "No larger than" with the megabytes box left empty reached the
  pipeline as `0`, which it reads as **no limit at all** — the opposite of what
  the radio button says.
* A bad number in a field raised `ValueError` and arrived as a traceback in the
  log. They are `ConvertError` now, and say what was expected.
* `os.startfile` raises `OSError` where nothing is registered for `.html`, and
  that was thrown from inside the poll loop — which would have stopped the loop
  and left the window stuck.
* The window kept a `multiprocessing.Queue`, and its feeder thread, for every
  conversion it had ever run.
* Enabling and disabling was written two ways, `configure(state=...)` and
  `state([...])`. Two ways of saying one thing eventually disagree.
* A flag the code set and nothing ever read.

## Known limitations

* The result is a **mesh**, not B-rep, and not for machining. What that costs a
  measurement is worth stating exactly, because measurements are shown to a
  thousandth of a millimetre and a number that precise invites belief: a point
  taken off a surface is only as true as the mesh under it, which is the
  deflection the file was built at — 0.006 mm on the test board, so the third
  decimal there is decoration. A point **snapped to a circle's centre** is not,
  because that centre comes from the B-rep and never passes through the mesh at
  all. So centre to centre is exact to the thousandth shown; anything off a
  surface carries the deflection with it.
* No model tree and no section planes. A 3D PDF in Acrobat has those; this does
  not.
* The page needs `DecompressionStream` and WebGL2: Chrome/Edge 80+, Firefox
  113+, Safari 16.4+. Anything older says so instead of drawing nothing.
* A size budget costs several builds and up to a minute. `--max-bytes none` is
  one build.

## Licence

MIT. See [LICENSE](LICENSE).

---

<a name="русский"></a>
# Русский

# ⚠️ Дисклеймер

Весь код в этом репозитории создан с использованием вайбкодинга совместно с Claude.
Я не являюсь профессиональным разработчиком программного обеспечения. По профессии я инженер-разработчик аппаратного обеспечения, и этот проект появился исключительно как попытка решить собственные практические задачи.
Я не владею в совершенстве Python. Вместо этого я стараюсь максимально точно формулировать требования к инструменту и постепенно доводить его до нужного результата.
Если вы обнаружите ошибку, неточность или захотите предложить улучшение — пожалуйста, создайте Issue или Pull Request. Я постараюсь разобраться и исправить проблему, однако не могу гарантировать, что это произойдет быстро.
Несмотря на выбранный подход к разработке, я стараюсь проверять результаты работы инструмента на практике и использовать этот проект в реальных задачах.

## Зачем это нужно

Отправить трёхмерную модель тому, у кого нет CAD, неудобно. Обычный ответ —
3D PDF, и ответ этот плохой: 3D PDF — это PDF с аннотацией `/3D`, внутри
которой лежит **U3D** или **PRC**, третьего формата не бывает, и оба
открываются только в настольном Adobe Acrobat, где 3D по умолчанию
**выключено**, — и не открываются вовсе ни в браузерных просмотрщиках, ни на
iOS, ни на Android. U3D заброшен с 2010 года; единственный свободный писатель
PRC — тот, что несёт в себе Asymptote, под лицензией LGPL-3.0; а собственный
экспорт 3D PDF во FreeCAD до сих пор незамёрженный черновой pull request.

**step2html** вместо этого пишет один самодостаточный HTML-файл. Он
открывается двойным щелчком в любом современном браузере, на телефоне не хуже
чем на настольной машине, без Acrobat, без плагинов, без интернета, без сервера
и без чего-либо, что нужно ставить тому, кому вы его отправляете. И он умеет
**сообщать о собственном повреждении**, чего PDF не умеет.

Работает с любым STEP, не только с платами.

## Как это работает

```bash
python step_to_html.py board.step
```

Рядом появится `board.html`. Либо с окном:

```bash
python gui.py
```

Что внутри файла:

* Геометрия, тесселированная через OCCT и покрашенная **по граням**, с
  откатом на солид, которому грань принадлежит, а затем на деталь — поэтому
  плата, покрашенная по слоям, такой и приезжает.
* Настоящие рёбра B-rep, нарисованные так, как их рисует CAD в режиме «с
  рёбрами».
* Просмотрщик на голом WebGL2: **ни three.js, ни CDN, ни шрифтов, ничего
  внешнего вообще.**
* Геометрия одним сжатым deflate блоком в base64, рядом с ним его длина и
  CRC32. Страница проверяет и то и другое **до отрисовки** и сообщает о
  повреждении, вместо того чтобы нарисовать неправду.

Управление: протяжка — поворот, колесо или щипок — масштаб, правая кнопка или
два пальца — сдвиг, **одиночный щелчок переносит центр вращения на точку под
курсором**, двойной щелчок — сброс. Проекция ортогональная или перспективная,
рёбра включаются и выключаются, тема по умолчанию системная.

Кубик в правом нижнем углу поднимает меню из восьми стандартных видов —
сверху, снизу, спереди, сзади, слева, справа и изометрия сверху или снизу.
Каждый разворачивает камеру и вписывает модель в кадр. Щелчок мимо меню
закрывает его и не меняет ничего.

«Спереди» — это взгляд со стороны **−Y**, при котором **+X** вправо, а **+Z**
вверх; «сзади» — противоположный. Если у платы своё представление о том, где
перёд, это правится одной строкой в `VIEWS`.

Галка **Measure** — и два щелчка дают расстояние между точками, рядом
ΔX/ΔY/ΔZ. Считается в системе координат модели, поэтому число это миллиметры и
оно ничем не обязано той проекции, через которую на него смотрят, и
показывается **до тысячных**. Файл это выдерживает: координаты — float32
относительно середины модели, так что на плате в 160 мм один шаг формата это
около пяти миллионных миллиметра. Чего третий знак *стоит* — вопрос другой,
и ответ на него в «Известных ограничениях». Третий щелчок начинает заново. Измерение сделано режимом, а не модификатором, потому
что обычный щелчок уже означает «вращать вокруг этой точки», а один жест не
может честно значить два разных.

Измерение **привязывается к центру окружности**. Если курсор оказался
примерно в 14 пикселях от круглого ребра — кромки отверстия, торца ножки, —
эта окружность ловится: её обод рисуется кольцом ещё до щелчка, а щелчок
ставит точку в центр, а не туда, куда попал курсор. Ободы обеих взятых точек
остаются на экране, так что готовое измерение — и сохранённая картинка с ним —
прямо говорит, что мерили от центра до центра, а не на глаз.

Ловится именно **обод**, а не стенка отверстия: у дуги есть точный центр, а
цилиндр даёт только ось, и высота вдоль неё оказалась бы там, куда случайно
попал курсор. Проверка идёт по **видимой** точке под курсором — это и не даёт
поймать отверстие с обратной стороны платы. Окружности находятся один раз, в
Python, по рёбрам, кривая которых — окружность, и одно отверстие даёт одну
запись, на сколько бы дуг ни был разрезан его обод и сколькими гранями бы он
ни делился: на плате с 927 гранями это 545 окружностей, 15 КБ сырых и
**3.9 КБ в готовом файле — четверть процента**.

Во время измерения грань под курсором подсвечивается, а линия тянется за
курсором, и расстояние обновляется на ходу. Подсветка почти ничего не стоит в
файле: треугольники одной грани лежат подряд, поэтому нужен один начальный
индекс на грань — 13 КБ сырых и 4.6 КБ сжатых на плате с 3286 гранями, против
299 КБ, если хранить идентификатор у каждого треугольника. Бросок луча на
каждое движение мыши — 7.6 мс на 300 тысячах треугольников, не чаще раза в
16 мс и только в режиме измерения.

После второго щелчка измерение рисует ещё и **ступенчатый путь**, как это
делает CAD: от первой точки вдоль X, затем Y, затем Z ко второй, каждый
отрезок своим цветом и со своим числом. Отрезок нулевой длины не рисуется
вовсе. Те же три цвета у **тройки осей** в левом нижнем углу — X красная, Y
зелёная, Z синяя, — и цветов этих **два набора**, потому что один не может
быть верным на обоих фонах: на тёмной теме они должны быть светлыми, чтобы
тянуть, на светлой — насыщенными, а единый средний набор на обеих читается
приглушённым. Тройка показывает ориентацию и больше ничего: ни проекции, ни
расстояния, ни центра вращения. Проверена по именованным видам,
где ответ однозначен: сверху луч Z схлопывается в точку, спереди то же делает
Y, а Z встаёт вертикально.

Сама табличка с результатом уходит **в самый дальний от измерения угол вида**,
а к середине линии от неё тянется тонкий поводок. Посреди этой линии, где она
стояла раньше, она закрывала собой ровно то, что измеряют. Угол выбирается по
точкам, взятым *вдоль* отрезков, а не только по их концам: угол, далёкий от
обоих концов, вполне может оказаться прямо на длинном отрезке. Если выбранный
угол не тот, табличку можно перетащить мышью; она останется на новом месте,
пока измерение не сбросят, и вернётся в поле зрения, если окно под ней сузят.

**Пустых углов нет**, и какие из них заняты — спрашивается у самих элементов,
а не записано числами. Разница эта была ошибкой: два нижних угла были
числами, поэтому табличка обходила кубик видов и тройку осей, а кнопка справки
— прибитая к правому верхнему углу *окна*, который в боковой раскладке
приходится на холст, — своего числа не имела, и под неё табличка спокойно
заезжала. Теперь угол берётся как есть по горизонтали и отодвигается внутрь,
пока под табличкой ничего не останется.

**Save PNG** сохраняет **то, что на экране**, а не только треугольники: измерение, его ступенчатый путь, числа, центр вращения и тройка осей — это DOM и SVG, поэтому они дорисовываются на двумерном холсте поверх картинки WebGL, причём считываются с живых элементов, чтобы файл не мог разойтись с экраном. Клавиши `1`–`8` — восемь видов,
`E` — рёбра, `P` — проекция, `M` — измерение, `Esc` — сброс. А адрес страницы
всегда называет вид, который на экране, так что отправить кому-то ссылку на
конкретный угол платы — это скопировать строку.

## Установка

Python 3.10 или новее и одна зависимость. Из папки проекта:

```bash
python -m pip install -r requirements.txt
```

```bash
python tests/run_all.py
```

`python -m pip`, а не `pip`, и **из папки проекта** — и то и другое по
причинам, которые уже кусались. На машине с несколькими Python команда `pip`
вполне может принадлежать не тому интерпретатору, которым вы будете запускать
инструмент, — именно так окно и оказывается неспособным стартовать. А файл
требований ставит `.`, то есть текущую папку, поэтому pip, запущенный откуда-то
ещё, будет искать проект там, где вы стоите, и прямо об этом скажет.

Сам файл никаких зависимостей не перечисляет. Зависимость одна, `cadquery-ocp`,
и она объявлена в `pyproject.toml`; вторая копия была бы вторым списком, за
которым надо следить. `-e .` заставляет pip прочитать тот, единственный.
Установка редактируемая, поэтому папка, которую вы правите, и есть та, что
работает, — а ещё в PATH этого Python появляются `step2html` и `step2html-gui`,
причём второй это оконная точка входа, то есть ещё один способ обойти
исчезающую консоль, о которой ниже.

`cadquery-ocp` — это OCCT. Больше ничего не требуется и ничего не используется.
Проверено на 7.9.3 и Python 3.12.

## Окно программы

**Запускать через `step2html.cmd`** или командой `python gui.py` из консоли.
Двойной щелчок по `gui.py` — единственный способ, который может тихо не
сработать: Windows отдаёт `.py` тому Python, который прописан в ассоциации
(обычно это лаунчер `py`), а на машине с несколькими Python это не обязательно
тот, в который поставлен OCP. Окно тогда не запускается, честно говорит почему
— и говорит это в консоль, которая закрывается в ту же секунду, так что видно
только чёрную вспышку. Об этом сообщили дважды, и оба раза с одним и тем же
обходным путём: батник, который консоль не даёт закрыть.

Две вещи в этом теперь исправлены. Причина выводится **в диалоговом окне**, и в
нём назван запущенный интерпретатор — тот самый факт, который всё решает, —
потому что tkinter входит в стандартную библиотеку и есть всегда, чего бы ни
не хватало. И рядом со скриптом лежит `step2html.cmd`: он берёт `python` из
`PATH` либо то, на что указывает `STEP2HTML_PYTHON`, и при ошибке делает паузу,
чтобы причину можно было прочитать.

У каждого ключа командной строки есть свой контрол, лог расцвечен так же, как в
Simple 3D, есть индикатор выполнения и кнопка отмены. Преобразование идёт в
**дочернем процессе**: OpenCASCADE умеет умирать сразу, а не бросать исключение,
и поток, принявший такой удар, унёс бы окно с собой, не оставив нигде ни
строчки. Свои настройки окно держит в `step2html_config.json` рядом со скриптом.

Полоса показывает текущую сборку, фазы делят её примерно по своей стоимости, а
внутри длинных фаз она движется **по граням** — у настоящей платы это одна
деталь на 900 граней, и подетальный прогресс простоял бы неподвижно всё это
время. Подпись говорит, какая это сборка: `build 3 of at most 6`. Для каждой
сборки полоса начинается заново, и это честно: при заданном бюджете размера
число сборок неизвестно, пока не вернутся размеры.

При первом запуске окно открывается по центру, дальше — там, где его закрыли, и
развёрнутым, если закрыли развёрнутым. Запомненное положение, которое больше
недостижимо (монитор отключили), игнорируется, и окно центрируется — вместо
того чтобы открыться где-то невидимо.

## Ключи

```
step_to_html.py STEP [-o OUT] [--title TITLE] [--deflection MM]
                     [--angle DEG] [--max-bytes N] [--no-repair] [--read-only]
```

| | |
|---|---|
| `--deflection` | допуск сетки в мм, либо `auto` (по умолчанию) — по размеру модели |
| `--angle` | угловой допуск в градусах, по умолчанию 15 |
| `--max-bytes` | бюджет размера, по умолчанию `auto` = размер самого STEP; `none` снимает |
| `--no-repair` | не пытаться спасать грани, которые мешер оставил пустыми |
| `--read-only` | поставить атрибут «только для чтения», чтобы блокнот отказался сохранять поверх |

**Имя выходного файла дописывается за вас.** Имя, заданное без расширения,
получает `.html`, причём расширение **добавляется, а не подменяется**:
`board rev.3` станет `board rev.3.html`, потому что `with_suffix` сделал бы из
него `board rev.html` и выбросил номер ревизии. Имя, которое уже кончается на
`.html` или `.htm`, остаётся ровно таким, как его написали, в любом регистре, а
путь, который указывает на существующую папку, забирает внутрь неё собственное
имя STEP, вместо того чтобы стать файлом рядом с этой папкой. Правило живёт в
одной функции, которую вызывают оба интерфейса, поэтому поле в окне не может
обещать имя, которого конвейер не запишет.

Бюджет по умолчанию мельчит сетку настолько, насколько это возможно, пока
`.html` остаётся меньше `.step`, из которого он сделан.

Размер против качества — почти степенная зависимость, поэтому двух замеров
хватает, чтобы получить показатель степени для конкретной модели, и третья
сборка идёт почти точно в бюджет: три-четыре сборки там, где фиксированная
лестница тратила семь. Чего **не** предсказывается — так это ответ: всякая
принятая настройка была собрана и взвешена, а подгонка лишь выбирает, куда
смотреть дальше. Насколько хорошо сжимается нагрузка, зависит от модели, и
никакая формула этого не знает.

`--max-bytes none` — одна сборка.

## Скорость, и куда она уходила

Профилировалось на тестовой rigid-flex плате: 927 граней, 2.4 МБ STEP, четыре
сборки. **34.4 с было, 20.7 с стало**, при том же выбранном шаге сетки. Одна
сборка на самой мелкой настройке — с 11.5 с до 6.8 с. Почти ничего из этого не
лежало там, куда показывал профилировщик: cProfile насчитал 2 с питоновского
времени в 11.5-секундной сборке, потому что остальное сидит внутри OCCT. Так
что все числа ниже — это часы на стене вокруг каждой фазы.

Помогли две вещи, и обе — работа, не дававшая ничего:

* **Попытки починки шли не в том порядке.** Грань, от которой мешер
  отказался, переделывается на копии: сперва как есть, потом с разрезом, и так
  на пяти допусках. Но копия «как есть» на собственном допуске модели — это
  единственная попытка, про которую кое-что известно: мешер только что отказал
  ровно этой грани ровно на этих числах. На этой плате каждый из четырёх
  конических кончиков ножек тратил **0.85 с на то, чтобы получить отказ снова,
  и 0.01 с на то, чтобы собраться после разреза**. Десять отказавших граней,
  3.40 с потрачено, полезной работы из них — 0.05 с. Теперь разрез идёт первым,
  и только на первом допуске: дальше, на более грубых, копия «как есть» всё
  ещё стоит того, чтобы пробовать её первой, потому что она оставляет грань
  целой. Починка: 5.1 с → 1.7 с.
* **Форма мешилась дважды.** `tessellate` начинался с собственного
  `BRepMesh_IncrementalMesh` по деталям, которые только что были смешены с теми
  же числами, а этот вызов перемешивает заново, а не замечает, что триангуляция
  уже несёт запрошенный допуск: 1.2 с на сборку. Удаление заодно закрыло вещь
  потише: раньше починка решала, какие грани пустые, по одной триангуляции, а
  геометрия бралась потом из другой, и они не всегда совпадали. Доказательство
  в числах: при одинаковых настройках было 132 005 треугольников, стало
  132 013.

Куда уходят оставшиеся 6.8 с на сборку:

| | |
|---|---|
| мешинг, `BRepMesh` | 1.7 с |
| тесселяция, питоновский цикл по 105 тыс. узлов и 132 тыс. треугольников | 1.9 с |
| `pack` — struct, перевод нормалей в байты, deflate уровня 9 | 0.9 с |
| рёбра из триангуляции | 0.5 с |
| страница, подстановка и экранирование | 0.2 с |
| чтение STEP — **один раз**, а не на каждую сборку | 1.7 с |

Что осталось на столе, тоже по замерам, а не по догадке: преобразование узла
можно делать в Python вместо `gp_Pnt.Transformed` — это 0.09 с; deflate уровня
6 здесь не быстрее и чуть хуже по размеру; а нормали можно брать не усреднением
граней в Python, а у самого OCCT, что было бы и быстрее, и честнее, — но это
меняет затенение и тянет на работу, а не на правку. Самый крупный оставшийся
рычаг вообще не в коде: сборка, вылетевшая за бюджет, выбрасывается, и эта
плата выбрасывает одну каждый раз. `--max-bytes none` — одна сборка и около
семи секунд.

## Standalone

Для машины, где нет ни Python, ни OCP:

```bash
python -m pip install pyinstaller
packaging\build.cmd
```

`STEP2HTML_ONEDIR=1` собирает папку вместо одного файла, `STEP2HTML_CONSOLE=1`
— консольную сборку, чтобы проверять из оболочки. Всё складывается в `dist\`.

| | одним файлом | папкой |
|---|---|---|
| на диске | **82.4 МБ** | 306.5 МБ, 1066 файлов |
| в архиве, чтобы переслать | 82.4 МБ | **82.7 МБ** |
| старт до первого ответа | 8.1–9.3 с | **3.05 с** |

Мерилось обоим одинаково. Папка выигрывает при каждом запуске и ничего не
стоит при пересылке: zip сжимает те же байты, что и загрузчик одного файла.
Единственное преимущество одного файла — руками ничего распаковывать не надо.

**Из чего вес**, и ничего из этого не наше: `OCP.pyd` 94 МБ, библиотеки OCCT,
с которыми он слинкован, — 65 МБ, **VTK — 135 МБ**, Python и Tk — около 12.
VTK здесь не используется ни одной строчкой и всё равно не выкидывается — это
проверено в два шага. Без папки `vtk.libs` падает сам `OCP/__init__.py`: он
зовёт для неё `os.add_dll_directory` **без проверки на существование**, в
отличие от строки выше, которая делает ровно это для `cadquery_ocp.libs`. С
**пустой** папкой `vtk.libs` она принимается, но уже `OCP.pyd` не грузится:
Windows разрешает все имена из таблицы импорта при загрузке, а шесть
vtk-библиотек в этой таблице есть.

**Стандартную библиотеку не трогаем.** Выкинуть из неё то, чем инструмент не
пользуется — `http`, `urllib`, `email`, `asyncio`, — выглядело бесплатным и
таким не оказалось: `pathlib` импортирует `urllib` ради `as_uri()`, и сборка
поднялась мёртвой с «No module named 'urllib'» из `pathlib`, в диалоговом
окне, причём в двух сразу, ещё до единой нашей строки. Весь
`base_library.zip` — это 1.2 МБ из 306.

**Проверять сборку — ключом `--selftest`:**

```bash
dist\step2html.exe --selftest some.step
```

Он прогоняет машинерию *окна* без окна — поднимает Tk, жмёт Generate, качает
канал до ответа — и пишет `some.selftest.html`. Этот путь стоит отдельной
проверки, потому что командная строка дочерний процесс не запускает вовсе:
бинарник может прекрасно преобразовывать из оболочки и падать в ту секунду,
когда кто-то нажмёт Generate. Результат — файл, а не сообщение, потому что
оконной сборке печатать некуда.

Замороженная сборка подписывает страницы версией и **без хеша коммита**: рядом
с исполняемым файлом нет репозитория, чтобы спросить.

Про восемь секунд, которые один файл тратит на распаковку: PyInstaller умеет
показывать **заставку**, и появляется она до старта Python — то есть в нужный
момент. Но единственное, что программа может на ней менять, — одна строка
текста, через `pyi_splash.update_text()`, и только когда Python уже запущен, а
к этому времени ожидание позади. Загрузчик прогресс распаковки никому не
сообщает, так что честного индикатора не получится, а замерший читается хуже,
чем его отсутствие. Сборка папкой убирает ожидание, а не украшает его.

## Структура пакета

| | |
|---|---|
| `step_to_html.py` | весь конвейер и шаблон страницы. `convert(Options, log, progress)` — единственная точка входа, `main()` — тонкая обёртка командной строки |
| `gui.py` | окно. Собирает тот же самый `Options` и отдаёт его воркеру |
| `worker.py` | `convert` в дочернем процессе. Не должен импортировать tkinter: на Windows дочерний процесс порождается заново и импортирует модуль с нуля |
| `step2html.cmd` | запускает окно выбранным Python и держит консоль открытой, если он упал |
| `requirements.txt` | `-e .`, чтобы одной командой ставилась единственная зависимость, объявленная в `pyproject.toml` |
| `packaging/` | сборка standalone: `build.cmd`, spec для PyInstaller и лаунчер — точка входа замороженного файла |
| `tests/` | четыре набора, `python tests/run_all.py`, около двенадцати секунд |
| `docs/` | архитектура как есть, ревью по датам и план дробления монолитов |

Командная строка и окно намеренно идут одним кодом. Отдельная реализация
конвейера под GUI — это ровно то, как две ветки расходятся, и
`tests/test_gui.py` падает, если у какого-то ключа не окажется контрола.

## Версии

Семантические, поднимаются вручную, число живёт в `__version__` в
`step_to_html.py` — `pyproject.toml` читает его оттуда, так что менять надо в
одном месте и нечему рассинхронизироваться. Патч — исправление; minor — новая
возможность или изменение того, как выглядит генерируемый файл.

Каждый сгенерированный файл сообщает, чем он сделан, внизу собственной
справки: версия, короткий хеш коммита, имя исходного STEP, реально
использованная сетка и дата. Хеш важнее, чем кажется: между двумя файлами с
одной и той же версией может лежать десяток коммитов правок, и именно хеш
привязывает файл к исходнику, когда его присылают с вопросом. Файл, собранный
из изменённого рабочего дерева, говорит `+edits`, потому что его нельзя
воспроизвести из названного коммита.

В шапке есть ещё `<meta name="generator">`, так что все файлы определённой
версии находятся обычным поиском по папке.

Это отдельно от **версии формата полезной нагрузки** в заголовке `S3DH`, которая
сейчас равна 4 и отвечает на другой вопрос: сможет ли просмотрщик вообще
прочитать эти байты.

## Что уже пробовали, и почему сделано именно так

Каждый пункт стоил как минимум одного раунда и будет сломан заново любым
очевидным на вид упрощением.

**Цвет находится по тождеству формы.** Не по метке: OCP связывает только
перегрузку `GetColor`, принимающую `TopoDS_Shape`, а `GetColor_s` — это совсем
другой вызов, «эта метка *и есть* цвет». И **никогда не перемещайте форму до
того, как искать её цвет**: на тестовой плате все 69 граней находятся на
хранимой форме и **ни одна** — после `.Moved()`, отчего вся модель красится в
один плоский цвет. Положение едет рядом и применяется к точкам тесселяции.

**Цвет может лежать на СОЛИДЕ, а не на его гранях**, и цепочка поиска обязана
идти: грань, затем солид, которому грань принадлежит, затем деталь, затем
серый. XCAF вешает один цвет на солид и позволяет граням его наследовать,
переопределяя только те, что отличаются. Настоящая плата приехала с цветом тела
на солиде, и 11 из её 63 граней не несли своего цвета вовсе: эти 11
проваливались мимо недостающего шага прямо в серый по умолчанию, а это
**44 % площади** — всё полотно платы, отрисованное светло-серым, при том что в
файле недвусмысленно лежал `#1A5924`.

Стоит знать, как фикстура к этому дважды оказалась негодной, потому что
повторить обе ошибки легко. С тем же цветом, что и у другой детали, проверка
проходила на чужом цвете. С деталью, внутри которой **один** солид, цвет
находится уже на уровне детали, и проверка проходит независимо от того,
спрашивают солид или нет. Нужны два солида, два цвета и ни одного цвета на
гранях — а узнать это можно единственным способом: сломать исправление
намеренно и посмотреть, упадёт ли тест.

**OCCT возвращает линейные компоненты цвета.** Если читать как есть, медь
`#B87333` приезжает как `(122, 44, 8)`. На выходе они кодируются в sRGB, а
шейдер линеаризует их обратно перед освещением.

**Некоторые грани не строятся ни при каких настройках.** На настоящем разъёме
четыре конические фаски на кончиках выводов остались пустыми и при 0.04 мм, и
при 0.01, и при 0.002 — причём более мелкая сетка делала **хуже**, а не лучше.
Ни один параметр мешера (`MinSize`, `AdjustMinSize`, `AllowQualityDecrease`,
`Relative`, `ForceFaceDeflection`) ничего не изменил, а `ShapeFix` нечего
чинить, потому что `BRepCheck` считает эти грани валидными. Это замкнутые
периодические грани, параметризованные от π до 3π вместо 0..2π. Разрез надвое
убирает шов, и они строятся.

**Чинить по одной грани и на копии.** `ShapeUpgrade_ShapeDivideClosed`,
натравленный на солид целиком, режет **каждую** замкнутую грань в нём, включая
исправные цилиндрические стержни выводов, которые после этого мешатся двумя
половинами, не сходящимися друг с другом, и несут выдуманное ребро вдоль
каждого. `tests/test_repair.py` существует ровно для того, чтобы это поймать.

**Заплатку не обязательно строить с допуском модели.** Именно это развязывает
тупик, потому что при измельчении сетки начинают отказывать грани, которые
раньше строились: две плоскости по 0.12 мм² отказывают на 0.0076 мм и строятся
на 0.019. Грань, которая не строится на выбранной настройке, просто строится
грубее; на плоскости это даже не различимо.

**Линии рёбер берутся из триангуляции, а не из кривой.**
`Poly_PolygonOnTriangulation` даёт индексы собственных узлов сетки вдоль ребра,
поэтому отрезок линии *и есть* ребро треугольника под ним: те же вершины, та же
глубина, а `depthFunc(LEQUAL)` решает ничью.

Сэмплирование истинной кривой — очевидное решение, и именно с него всё
начиналось — кладёт гладкую линию поверх гранёной поверхности, и между ними до
одного допуска по глубине. Чтобы это перекрыть, нужен сдвиг не меньше одного
допуска, а линия при этом обязана быть тоньше медного слоя, иначе просвечивает
сквозь него. На настоящей плате эти два требования пересеклись: допуск 0.023 мм
против меди 0.018 мм, и **ни одно значение не удовлетворяет обоим**.

**С заливками не делается ничего.** `glPolygonOffset` пробовали на них дважды, и
он неверен в обе стороны. С множителем наклона он умножает максимальный наклон
глубины полигона, а тот убегает в бесконечность у грани, стоящей ребром к
камере — силуэт цилиндра, наклонный торец, — и отправляет её за дальнюю стенку
собственного тела, отчего сплошной конденсатор отрисовывался открытой трубой.
Без множителя постоянная поправка слишком мала ровно на этих косых гранях, и
линии рёбер рассыпаются в пунктир вдоль торца платы, видимой почти ребром. От
всего этого остался фиксированный сдвиг 1e-5 отсечённой глубины, применяемый к
**линиям**, и отвечает он только за разницу в том, как растеризуются линия и
треугольник.

**Ориентация — матрица, а не пара углов.** У углов есть полюса: тангаж
приходится останавливать чуть-чуть не доходя до отвеса, иначе при переходе
через него переворачивается горизонт и движение вбок начинает работать
наоборот. В этот упор и упирается протяжка. Матрице, которую поворачивают оси
экрана, упираться некуда. Ортонормировка Грама-Шмидта раз за протяжку — потому
что матрица поворота, умноженная сама на себя несколько тысяч раз в float32,
перестаёт быть поворотом.

**Одиночный щелчок переносит центр вращения на точку под курсором**, как это
делает CAD, и именно это делает большую плату осматриваемой: поворот и зум
после этого работают вокруг той детали, на которую смотрят. Луч бросается по
треугольникам на процессоре, потому что буфер глубины основного фреймбуфера в
WebGL читать нельзя; на 150 тысячах треугольников это несколько миллисекунд,
один раз на щелчок.

Перенос точки не должен двигать картинку, и арифметика для этого — одна строка:
поставить перенос камеры ровно туда, где выбранная точка уже находится в
системе координат вида. Но справедливо это только в перспективе. В
ортогональной проекции **расстояние и есть масштаб**, поэтому его изменение
перемасштабирует всё. Отсюда `cam.oh` — полувысота ортогонального окна,
хранимая отдельным числом: колесо двигает её вместе с расстоянием, щелчок
двигает только расстояние. Луч выбора тоже обязан строиться от `cam.oh`, иначе
он бросается в другом масштабе, попадает не в тот треугольник и утаскивает за
собой плоскости отсечения.

Выбранная точка **отмечается на экране** — кольцо с перекрестием вспыхивает
там, куда пришёлся щелчок, держится всю протяжку и гаснет после неё. Это
HTML-накладка, чья позиция пересчитывается проекцией раз в кадр, а не второй
вызов отрисовки, поэтому CSS анимирует её бесплатно. Будучи центром вращения,
она — единственное на экране, что при повороте **не** двигается, и это самое
внятное объяснение того, чем она является.

**Кнопке справки нужен порядок наложения.** Она закреплена за правым верхним
углом экрана, поэтому в боковой раскладке вылезает поверх холста — а `#bar`
идёт в разметке до `#view`, и ни у того ни у другого нет `z-index`, так что
холст рисуется сверху и кнопки просто нет. Стоит знать, как это прячется:
`getBoundingClientRect()` сообщает положение кнопки независимо от того, накрыта
она чем-нибудь или нет, поэтому проверка по геометрии проходит, когда на экране
ничего нет. На заданный вопрос отвечает `elementFromPoint`.

**Высота страницы берётся от области просмотра, а не от цепочки
`height:100%`.** Цепочка схлопывается в ноль везде, где у предка нет высоты, а
на телефоне `100vh` считает и место под сворачивающейся адресной строкой.
`100dvh` — это видимая высота.

**Панель ставится туда, после чего остаток ближе к квадрату.** Сверху она
стоит высоты, сбоку — ширины, и что из этого больнее, зависит от формы окна:
телефон, повёрнутый набок, делает и без того широкий вид ещё шире. Обе
раскладки измеряются по-настоящему, а не угадываются по медиазапросу
`(orientation: landscape)`, потому что толщина панели — это то, во что её
сложило содержимое и переносы строк. Замерено на восьми формах окна, и во всех
выбирается лучшая из двух: 780×360 даёт 1.75 сбоку против 2.70 сверху, 360×780
даёт 1.76 сверху против 3.45 сбоку, а 1024×768 выходит 1.16.

Четыре вещи там несущие, и три из них найдены тем, что сначала были сделаны
неправильно.

*Боковая колонка обязана быть шириной со свой самый широкий КОНТРОЛ и не
переноситься.* Растяните её или дайте перетечь во вторую колонку — и она
станет достаточно широкой, чтобы проигрывать любое сравнение: боковая
раскладка тогда не выбирается никогда, и весь механизм выглядит мёртвым, считая
при этом безупречно. Название и статистика выведены из этой ширины через
`width:0; min-width:100%` и переносятся внутри колонки, которую задали
контролы.

*Наблюдатель обязан храниться в переменной.* Записанный как
`new ResizeObserver(...).observe(x)` он не имеет ни одной сильной ссылки и
перестаёт срабатывать, как только его заберёт сборщик мусора. Именно так это и
работало сначала: раскладка выбиралась один раз при загрузке и больше никогда,
а всякая перерисовка, из-за которой всё выглядело живым, приходила совсем из
других мест.

*Решение принимается дважды — сразу и ещё раз в следующем кадре.* Считать
только внутри события — значит попадать на неустоявшуюся раскладку; ждать
только кадра анимации — значит не дождаться вовсе там, где кадры не
производятся.

*Наблюдатель следит за `body`, а не за областью просмотра* — область и есть то,
что этим меняется, и наблюдатель на ней отвечал бы на собственное изменение
бесконечно.

**Меню, закрывающееся щелчком мимо, обязано этот щелчок ПОГЛОТИТЬ**, а не
просто заметить. Обработчик, который закрывает меню, оставляет то же нажатие
дойти до холста под ним — а тот повернёт модель или перенесёт центр вращения,
тогда как требование было ровно обратное: не выбрав ничего, не изменить
ничего. Прозрачная накладка поверх всего, показываемая вместе с меню, — это то,
что делает требование правдой; замерено 0 % изменившихся пикселей.

Шесть стандартных видов строятся из **базиса** — направления, в котором стоит
камера, и указания, где верх, — а не из углов. Порядок применения перепутать
негде, и каждый вид читается как то, чем он является. Замерено на плате
160 × 80: сверху и снизу занимают 47.6 % кадра при габарите 2:1, слева и
справа — 1.8 % при 3.76:1, изометрии — 22.1 % при 1.69:1.

**Ортогональный луч выбора обязан начинаться перед моделью**, а не на
плоскости камеры. На плоскости камеры всё, что ближе к зрителю, оказывается
позади начала луча и отбрасывается условием `t > 0` — но при этом рисуется,
потому что ближняя плоскость отсечения отнесена на `span*4` назад. `cam.dist`
уменьшается и от колеса, и когда щелчок переносит центр вращения на близкую
поверхность, так что эта плоскость может уйти внутрь модели, и видимые грани
перестают выбираться. Параллельные лучи попадают в одно и то же независимо от
того, откуда начаты, поэтому перенос начала не стоит ничего.

**Холст нужно отдавать на скачивание через blob, а не через `data:`-ссылку.**
Chrome отказывается скачивать `data:` длиннее примерно двух мегабайт, а снимок
платы во весь экран на плотном дисплее весит несколько — поэтому Save PNG
молча не делал ничего, и нигде никакой ошибки. У `toBlob` с `createObjectURL`
такого предела нет.

**Случайный перевод строки внутри строкового литерала JS ломает страницу
целиком.** Python пишет просмотрщик как текст и отличить не может; браузер
после этого не выполняет вообще ничего, поэтому симптом — пустая страница, а
не сломанная функция, и разом мёртвыми выглядят все органы управления. Это
стоило половины дня поисков в отрисовке при том, что причиной был один
потерянный обратный слеш в правке. `tests/test_page.py` теперь считает кавычки
по строкам сгенерированного скрипта, и эта проверка показана падающей на
намеренно сломанном файле.

**Сенсору нужны два указателя.** Телефон не шлёт события колеса вовсе, поэтому
без обработки двух пальцев масштаба на нём нет никакого.

## Ревью

### 2 сентября 2026, на 0.9.6

Четвёртый проход, по всему, и с другим вопросом: не только что не так, но
что здесь монолит и что можно унести в другой проект как есть. Полный список
с воспроизведениями, структурная и функциональная схемы и план дробления —
в `docs/`: [review-2026-09-02.md](docs/review-2026-09-02.md),
[architecture.md](docs/architecture.md),
[refactoring-plan.md](docs/refactoring-plan.md). Код этим проходом не
менялся; исправления — первая фаза плана.

* **Когда ничего не влезает в бюджет, остаётся ПЕРВАЯ сборка, а не самая
  маленькая.** Комментарий говорит «наименьшая», лог говорит «keeping N
  bytes» — где N от сборки при q = 1.0, которую `page` и `rep` всё ещё
  держат, потому что цикл поиска их не переприсваивает. Воспроизведено на
  фикстуре с бюджетом 1000 байт: построено 73 873 и 71 842, оставлено 73 873.
* **Старому Chrome говорят, что файл повреждён.** Страница проверяет
  `DecompressionStream` и обещает Chrome/Edge 80+, но `deflate-raw`
  появился в Chrome 103; на 80–102 конструктор бросает исключение внутри
  того же `try`, что и распаковка, и показывается не то сообщение. Пол —
  103+, а `:has()` в стилях — 105+, с мягкой деградацией.
* **Взвешивается не то, что записывается.** Бюджет сравнивается со
  страницей как с байтами текста с `\n`, но `write_text` без `newline=`
  даёт Windows превратить каждый конец строки в CR LF: файл на диске больше
  взвешенного на байт на каждую строку шаблона — 1382 на фикстуре, 73 873 в
  логе против 75 255 на диске, — так что бюджет ровно в размер STEP может
  быть промахнут на столько, а `Report.size` считает не то, что выбирал
  поиск. Найдено при написании теста к первому пункту.
* **`gui` и `worker` устанавливаются модулями верхнего уровня** с такими
  именами — столкновение ждёт машины, где стоит ещё один пакет. Становится
  пакетом, и это первый шаг плана.
* **Заплатка несёт свой шов как линию ребра** — тот самый артефакт, от
  которого `test_repair.py` бережёт весь солид, принят на одной грани. Не
  ошибка; не записано.
* Мелочи: `_faces` не дедуплицирует грань, общую для двух солидов;
  `<Configure>` на корне срабатывает на каждый дочерний виджет; `pack`
  режет и разворачивает больше, чем нужно; проверка кавычек в
  `test_page.py` слепо режет по `//`; `os` и `TopExp` не используются;
  докстринг всё ещё называет `simple3d_config.json`; `const on` затенён в
  обработчике клавиш; `worker.py` записывает инвариант, который spawn не
  держит (tkinter в дочернем процессе *импортирован*, через `__mp_main__`,
  — нельзя лишь `Tk()` на уровне модуля); этот файл говорит 3.12 и
  двенадцать секунд там, где верны и 3.14 с двадцатью; тегов в git нет.

Проверено и оказалось в порядке: места подстановки в обе стороны, `TEXT`,
каждый элемент, который ищет скрипт, функции без ссылок, раскладка
нагрузки против заголовка и все пункты трёх прошлых ревью.

### 31 июля 2026, на 0.9.4

Третий проход, по всему. Одна ошибка, две дыры в тестах ровно там, где лежала
самая свежая работа, и три наведения порядка. Механические сверки прошлого
прохода — места подстановки против подстановок в обе стороны, ключи `TEXT`, все
элементы, которые ищет скрипт, функции, которых никто не зовёт, — все чистые.

* **Текст, подставленный в страницу, потом читался КАК страница.**
  `build_page` заменял ключ за ключом в цикле, поэтому значение могло содержать
  то, что выглядит как более позднее место подстановки, и быть переписано им.
  Заголовок — это пользовательский текст: `--title` или имя самого STEP. И
  заголовок `__L_ON__` выходил на странице как **On**. Теперь один проход
  `re.sub`, и подставленное больше никогда не перечитывается.
* **У починки не было ни одного теста.** У фикстуры нет грани, от которой
  мешер отказывается, — набор тестов сам об этом и пишет, — так что
  `_patch_face`, самая тонкая здесь вещь и та, чей порядок только что
  переставили ради скорости, работал непроверенным. Построить отказную грань
  на заказ тоже не вышло: пять конструкций замкнутого периодического случая, от
  π до 3π на цилиндре и на конусе, спокойно смешились. Поэтому починка
  проверяется на здоровой замкнутой грани — и это закрепляет то, чем патч
  обязан быть, кто бы его ни попросил: смешенным, покрывающим **ровно** ту
  поверхность, вместо которой он стоит (площадь с точностью до миллионной), и
  разрезанным — последнее закрепляет порядок.
* **У окружностей, к которым привязывается измерение, не было геометрической
  проверки.** Они берутся из кривой ребра, которая уже несёт локацию *ребра*, а
  положение *детали* накладывается сверху вручную — то же самое укрытие, что и
  у ошибки с цветом двумя раундами раньше. Теперь закреплено: ножка фикстуры
  даёт по одной окружности на кромку и не больше, их центры несут положение
  детали, они стоят в 6 мм друг от друга, и у каждой единичная ось. Доказано
  поломкой: без наложения положения центры уезжают на 40 мм, обратно в начало
  координат.
* **Три принудительных пересчёта раскладки на кадр** в `paintMeasure`, причём
  одно выражение спрашивало один и тот же прямоугольник дважды.
  `getBoundingClientRect` после записи стиля заставляет браузер разложить
  страницу заново, чтобы ответить; теперь спрашивается один раз.
* **Проверка `hasattr`, которая не может провалиться,** в `_remembered` окна:
  `_load_config` ставит атрибут безусловно и в `__init__`. Тот же вид, что
  первое ревью нашло в тестах.
* **Допущение, которое стоило записать:** картинка рисует тройку осей со
  смещением в CSS-пикселях в координатах, которые являются пользовательскими
  единицами SVG, и это одно и то же только потому, что `#axes` шириной 88 px
  при viewBox `0 0 88 88`.

### 31 июля 2026, на 0.8.0

Второй полный проход. Три пункта — настоящие ошибки, остальные из тех, что
становятся ошибкой позже. Исправлено всё, а два, которые можно закрепить
тестом, закреплены тестом, **который сперва заставили упасть**.

* **`read_step` бросал `SystemExit`.** Это наследник `BaseException`, поэтому
  в рабочем процессе его не ловил ни `except ConvertError`, ни
  `except Exception`: STEP, который OCCT читать отказался, убивал дочерний
  процесс молча, а окно сообщало единственное, что оно знает про молчаливую
  смерть, — «обычно это падение внутри OCCT», что и пугает, и неправда.
  Теперь это `ConvertError`, а командная строка не изменилась: `main()` и так
  превращал его в тот же самый выход.
* **`fail()` падал на своей последней строке.** Она заканчивалась на
  `getElementById('hud')` — идентификатор давно переименован, и возвращается
  `null`. Проверено на странице с одним испорченным символом нагрузки:
  сообщение появляется, потому что эта строка идёт первой, а следом —
  `TypeError: Cannot read properties of null`. То есть всё, что дописали бы
  после неё, молча не работало бы — в той самой функции, вся работа которой
  состоит в том, чтобы сдержать обещание про испорченный файл.
* **Вид в адресе портил некоторые числа.** `toPrecision(6)` и срезание
  хвостовых нулей превращают `120000` в `12`. `1200` выживает, потому что в
  шестизначной записи это `1200.00` и у нуля есть точка, на которой
  остановиться; у всего от ста тысяч её нет. Симптом был бы такой: ссылка
  тихо восстанавливает другой вид. На стороне восстановления была зеркальная
  ошибка: в классе символов не было `+`, поэтому `1.00000e+6` — который тот же
  код выдаёт после миллиона — прочитать было нельзя.
* **Две копии «настроить именованный вид»,** одна за меню, другая за
  цифровыми клавишами. Сегодня одинаковые — а одинаковые они только сегодня.
* **`_mesh_and_count` был мёртв** — остался с тех пор, как починка перешла на
  одну грань за раз.
* **Угол тройки осей записан дважды:** один раз в стилях, второй — константой
  в рисовальщике PNG. Теперь картинка спрашивает у самого элемента, где он, —
  по тому же правилу, которому весь остальной рисовальщик и так следует.
* **`[c1, c2] = querySelectorAll('circle')`** брал две точки измерения по
  порядку, а над ними теперь есть третий кружок.
* **Буфер рисования холста перевыделялся каждый кадр** — присваивание
  `width`/`height` делает это, даже если число не изменилось.
* **Перетащенную табличку могло оставить за краем суженного окна,** плюс
  неиспользуемая переменная в `savePng`.

Проверено и оказалось в порядке: у каждого места подстановки в шаблоне есть
подстановка и наоборот, в `TEXT` нет неиспользуемых строк, все элементы,
которые ищет скрипт, существуют, а массивы нагрузки лежат ровно там, где
говорит её заголовок.

### 30 июля 2026, на 0.3.0

Полный проход по коду нашёл восемь вещей, ни одна из которых не была поймана
тестом; все исправлены и в основном закреплены:

* Подпись прогресса говорила `build 3 of at most 8`, тогда как поиск никогда не
  тратит больше 6 — две константы делали одну работу, и одна отстала.
* В `tests/test_gui.py` была проверка, обёрнутая в `hasattr` по имени
  несуществующего виджета, — она проходила, ничего не проверяя. Проверка,
  которая не может упасть, хуже отсутствия проверки: она читается как покрытие.
* Выбор «No larger than» с пустым полем мегабайт доходил до конвейера как `0`, а
  это читается как **отсутствие ограничения** — противоположное тому, что
  написано на радиокнопке.
* Кривое число в поле давало `ValueError` и приезжало в лог трассировкой.
  Теперь это `ConvertError` с указанием, чего ожидали.
* `os.startfile` бросает `OSError` там, где на `.html` ничего не
  зарегистрировано, и бросал он его **изнутри цикла опроса** — это остановило
  бы цикл и оставило окно висеть.
* Окно держало `multiprocessing.Queue` вместе с её служебным потоком за каждое
  преобразование, что когда-либо запускало.
* Включение и выключение контролов было написано двумя способами,
  `configure(state=...)` и `state([...])`. Два способа сказать одно и то же
  рано или поздно расходятся.
* Флаг, который код ставил и никто никогда не читал.

## Известные ограничения

* Результат — **сетка**, а не B-rep, и обрабатывать по нему нельзя. Чего это
  стоит измерению, лучше сказать точно — тем более что числа показываются до
  тысячных, а такая точность располагает верить: точка, взятая с поверхности,
  верна ровно настолько, насколько верна сетка под ней, то есть с точностью до
  отклонения, с которым собран файл, — 0.006 мм на тестовой плате, так что
  третий знак там украшение. Точка, **привязанная к центру окружности**, — нет:
  этот центр приходит из B-rep и через сетку не проходит вовсе. Так что от
  центра до центра — точно до показанной тысячной, а всё, что упирается в
  поверхность, несёт на себе отклонение.
* Нет дерева модели и нет секущих плоскостей. У 3D PDF в Acrobat это есть,
  здесь — нет.
* Странице нужны `DecompressionStream` и WebGL2: Chrome/Edge 80+, Firefox 113+,
  Safari 16.4+. Всё, что старше, скажет об этом, а не покажет пустоту.
* Бюджет размера стоит нескольких сборок и до минуты времени.
  `--max-bytes none` — одна сборка.

## Лицензия

MIT, см. [LICENSE](LICENSE).
