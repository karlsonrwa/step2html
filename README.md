# step2html — STEP → один интерактивный HTML

*[English](#english) · [Русский](README.ru.md)*

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
python -m step2html board.step
```

That writes `board.html` beside it. Or, with a window around it:

```bash
python -m step2html.gui
```

Installed, the same two are `step2html` and `step2html-gui`.

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
Tested against 7.9.3 on Python 3.12 and 3.14.

## The GUI

**Start it with `step2html.cmd`**, with `python -m step2html.gui` from a
console, or as `step2html-gui` once installed. Starting it with the wrong
Python is the one way that can quietly fail: on a machine with several Pythons
installed, the one that answers to `python` — or to a double-clicked `.py`,
through the file association — need not be the one OCP is in. The window then cannot start, says exactly why, and says it to a
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
step2html STEP [-o OUT] [--title TITLE] [--deflection MM]
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

## Package layout

| | |
|---|---|
| `step2html/` | the pipeline, one module per concern. `convert.py` is the one entry point, `convert(Options, log, progress)`; `xcaf.py` reads the STEP and its colours, `meshing.py` meshes and repairs, `tessellate.py` makes triangles, edges and circles, `payload.py` packs them, `page.py` writes the page around them from the template in `viewer/` - the markup, the stylesheet, and the script as one file per concern, concatenated in the order `page.py` names, with everything stateful in `boot.js` and the pure parts checked by node; `cli.py` is a thin command line over the lot, and `python -m step2html` reaches it from a checkout |
| `step2html/gui/` | the window, `python -m step2html.gui`. `app.py` is the widgets and the wiring, and builds the same `Options` the CLI does; `job.py` is the child process and its channel, `logpane.py` the coloured log, `geometry.py` where the window goes, `settings.py` what it remembers - none of those four needs a window, and three are tested without one |
| `step2html/worker.py` | `convert` in a child process. Nothing on the way in may build a `Tk()`: on Windows the child is spawned and re-imports the main module |
| `step2html.cmd` | starts the window with a Python of your choosing, and holds the console open if it fails |
| `requirements.txt` | `-e .`, so one command installs the one dependency that `pyproject.toml` declares |
| `packaging/` | the standalone build: `build.cmd`, the PyInstaller spec, and the launcher that is the frozen entry point |
| `tests/` | nine suites, `python tests/run_all.py`, twenty to thirty seconds; five of them - the budget search, the progress bar, window geometry, the child process and the viewer's pure modules under node - need no OCCT |
| `docs/viewer-checklist.md` | what the tests cannot see: the gestures, run by hand on a real board after any change under `viewer/` |
| `docs/` | the design record (`design-notes.md`), the review log (`reviews.md`), the profile (`performance.md`), the frozen build (`standalone.md`), the architecture and the plan that took the monoliths apart, and the checklist for the viewer; each of the first four also in Russian, as `.ru.md` |

The CLI and the window share one code path on purpose. A second implementation
of the pipeline behind a GUI is how the two drift apart, and
`tests/test_gui.py` fails if a flag ever gains no control.

## Versions

Semantic, bumped by hand, and the number lives in `__version__` in
`step2html/__init__.py` — `pyproject.toml` reads it from there, so there is one place
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
* The page needs `DecompressionStream` with `deflate-raw`, and WebGL2:
  Chrome/Edge 103+, Firefox 113+, Safari 16.4+. Anything older says so instead of drawing nothing.
* A size budget costs several builds and up to a minute. `--max-bytes none` is
  one build.

## Read on

* [Things already tried, and why it is the way it is](docs/design-notes.md) —
  the design record. Every item there cost at least one round and would be
  re-broken by an obvious looking simplification.
* [Reviewed](docs/reviews.md) — the review log, newest first.
* [Speed, and where it went](docs/performance.md) — the profile, and what is
  left on the table.
* [Standalone](docs/standalone.md) — the frozen build, and what it weighs.
* [Architecture](docs/architecture.md), [the plan that took the monoliths
  apart](docs/refactoring-plan.md), and [the checklist for the
  viewer](docs/viewer-checklist.md).

## Licence

MIT. See [LICENSE](LICENSE).
