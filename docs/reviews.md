# Reviewed

*[English](reviews.md) · [Русский](reviews.ru.md)*

Part of [step2html](../README.md). Every full pass over the code, newest first, with what it found and what was done about it.

### 21 Sep 2026, at 0.15.0

Two questions this time, both answered by measuring rather than reading:
does the suite check anything, and why does the program die on a newer
`cadquery-ocp`.

**The suite, broken on purpose.** Reading a test cannot tell whether it
checks anything — every test looks purposeful — so the code each suite claims
to protect was broken the way a real defect would break it, in a private copy
of the tree, and the suite run there. The rows live in `tests/mutations.json`
(161 of them, one per decision), `tools/mutate.py` applies them to copies
under `work/mutants/` in parallel and reports `caught` or `SURVIVED`, and
`tests/test_mutations.py`, the eleventh suite in `run_all`, applies nothing but
checks every day that each row still matches its file exactly once — a row
whose pattern a refactor broke is a rule with no evidence, and the runner's
`REFUSED` is easy to skim past. The full table: 161 of 161 caught, 164 s of wall for 629 s of suite runs on four copies on four copies.
Before the tests were fixed, 65 of the 150 of the first rows survived. The
suite went from 10 suites and 257 checks to 11 and 338 in the ten old ones plus the sentinel's 681, and the baseline
run from 21 s to 22 s. What the survivors found, by kind:

* **Checks that could not fail.** The automatic deflection was checked to be
  "inside its clamp" — which is the last line of the function restated; a
  3-4-12 box with its 13 mm diagonal pins it now. "The placed part is out at
  its transform" was true with every transform dropped, because the board alone
  reaches that far; the pin's top at z = 8 and the plate's far edge at y = 50 are
  the numbers only the placement can give. "The face table ascends" was true of
  a table of noughts. In the viewer, `fitDist` was compared with a formula built
  from the viewer's own `FOV`, so halving the field of view passed; `rotX(0)`
  is the identity whichever sign the sine has; a transposed or mirrored rotation
  is still orthonormal; "there are eight named views" said nothing about where
  any of them looks; and with one triangle and one circle in the fixture,
  "nearest wins" and "named by its number" were both zero.
* **Paths nothing walked.** Both tessellation paths call the same
  `vertex_normals`, so comparing them compared a bug with itself: every normal
  flipped inward passed. Now the mesh's signed volume is checked against OCCT's
  own, every normal against the facets that meet at it. The per-face check of
  the glTF export lined up 21 of 21 faces on the fixture, so its refusal, the
  node-walk fallback and the winding correction were dead — the same document
  is now handed over with the parts in the other order (12 of 21 line up) and
  the result compared with the pure walk. The rescue of a refused face was never
  entered because the fixture needs no patching; a forced empty face enters it.
  The edge base, the curve fallback of `collect_edges`, the joining of two rims
  into one circle, a title with markup in it, the commit and `+edits` in the
  version stamp: none had a witness. In the viewer, the payload fixture had
  every count but one at zero, so the triangles, edges and face table were never
  read back, and the 4 MiB base64 slicing loop ran once; the camera's aspect
  floor, both distance clamps, the vertical scale, the depth ranges, the
  behind-the-camera guard and the whole perspective projection beyond one
  matrix entry had no check; the pick's origin offset, aspect and canvas
  position, and a triangle exactly at a face start, likewise; `layout.js` was
  not loaded at all.
* **Witnessed only by the golden.** Three mutations of `tessellate` — a flat
  face table, a lost edge base, flipped normals — moved the payload's CRC and
  nothing else, so the only thing the suite could have said was "not byte for
  byte the golden one", which names no cause and reads like an OCCT change.
  Each is now caught by a check that says what broke.
* **Round trips.** The view in the address was decoded only from what
  `encodeView` had produced, with values exact at three digits and an identity
  rotation, which is symmetric; six-digit values and a real rotation now pin it.
* **Equivalent mutants, dropped with a measurement:** the `u > 1` guard in the
  pick's triangle test is implied by the guard after it — 78,408 cursor
  positions over 20 triangles, both projections, four distances, not one answer
  different.

Noticed on the way and left for the next day: a patch for a refused face is painted from
its face or its part, skipping the solid level that `tessellate` consults, so a
solid-coloured part with an unmeshable face would get a grey patch; the DOM
half of the viewer (`boot`, `gl`, `measure`, `png`, `overlays`) has no
behavioural check at all, only `test_page`'s text greps — the inventory of its
unchecked decisions is in the session's report, and whether a browser harness
is worth it is a decision, not a test; `overlays.js` carries a second copy of
`toScreen`'s pixel mapping; `parsePayload` in the page never reads the `S3DH`
magic or the version, the page's gate is the length and the CRC in `boot.js`.

The pure-Python and window suites had the same shapes. An expectation computed
by the code under test (`int(SPAN * WEIGHTS[0])`, now the literal 420);
`check(True, "no progress callback at all is fine")`, which cannot fail; the
quality clamp asserted on a search whose qualities never came near either end;
a check true of an empty list ("nothing is stuck" passed because nothing was
toggleable); a paste test that pasted what it had just copied over the same
selection; handlers asserted and their binding to the field never; a 90 s
timeout doing duty as an oracle; and `virtual_screen` accepted its own
fallback, so a version that never asks Windows passed anywhere. Of 63
mutations of `budget`, `progress`, the window's geometry, the child process,
the editing helpers and the window itself, 24 survived the suites as they
were, and what they severed had no witness at all: the window's whole Cancel
path, opening the result when the box is ticked, a remembered position on a
monitor that is gone, a bad number or an empty budget answered with a
traceback instead of a line in the log, the greying of fields nothing reads,
the frozen flag on a field's own right-click, a child that Cancel let go rather
than killed, a hole every build has taken for a refusal every time, a tick past
its own total, `Traceback` not read as an error, the summary that names the
file and its size, a settings file that turns a bool into a string or raises
when absent or when its folder refuses it. Each has a check now. And none of
it is owed to the developer's own `step2html_config.json`: with that file
deleted all six suites pass, and the runner no longer copies it at all.

**A newer `cadquery-ocp`.** A user reported that 0.14.0 runs with 7.9.3.1.1
and not with "newer cadquery and numpy". Measured in a venv: `pip install -e .`
today resolves `cadquery-ocp>=7.7` to **8.0.1.0.0**, OCCT 8.0, a 617 MB
install, and the package dies at import — before the STEP is opened. Three
binding changes, none of them numpy's (2.3.5 and 2.5.3 give byte-identical
payloads under one OCCT):

* every `NCollection` instantiation moved to one module, `OCP.collections`,
  named after its template arguments — `TDF_LabelSequence` is
  `Sequence_TDF_Label` there and `OCP.TDF` no longer has the old name;
* `TopoDS.Face_s` and `Edge_s` lost their suffix; the bare names exist in both;
* `Bnd_Box.Get()` gained an overload returning a struct that the bindings never
  register, and pybind11 tries it first, so every call raises `Unregistered
  type`; `CornerMin`/`CornerMax` return the same six doubles in both.

The trap inside the fix: 8.0 binds two indexed shape maps, one keyed on
`IsEqual` (orientation counts) and one on `IsSame`; 7.9's map was the second,
and the first draws every shared edge twice — 24 edges on a cube instead of 12,
266 on the fixture instead of 133. Fixed in `_occt.py`, `meshing.py` and
`tessellate.py`; on 7.9 not one output byte changed (the golden's CRC and a
real board's page compared before and after). 8.0 itself meshes one disc face
of the fixture from the next node round and, on a real board, flips 1.3 % of
the diagonals at the same area, so its pages differ from 7.9's in bytes and not
in geometry: `tests/golden.json` now keeps one golden per OCCT version, and a
golden is written only on purpose (`--golden`), never because a file or a key
was missing. `pyproject.toml` pins `cadquery-ocp>=7.7,<9`. And the start-up
message, which called an installed OCP with one missing name "the Python
running this does not have OCP", now prints the OCP version and the range the
code knows — that wording is why the report arrived without the name of the
symbol.

**22 Sep 2026, at 0.16.0 - everything the pass found is fixed, and the DOM
half of the viewer has a real check.** A patch for a refused face now takes
its colour by the same three levels as every other face - its own, its
solid's, its part's - through one helper, `meshing.solid_colours`, that the
repair and `tessellate` share; proved on the plate, whose colours sit on its
two solids and on nothing else. `tests/test_browser.py` opens the real page
in headless Chrome (Edge where there is no Chrome; SwiftShader, `--dump-dom`,
virtual time) and reads back the address, the DOM and the framebuffer: 71
checks over `boot`, `gl`, `measure`, `png` and `overlays` - the counter's
split and its gate, the payload gate, the address written 400 ms after the
movement and by `replaceState`, the wheel law, a drag that turns about the
screen's axes, a three-pixel click against a ten-pixel drag, the keys and the
guard on them, the named views refitted with `oh` in step, the theme and the
edges' colour under it, the pixel where a triangle is, the hovered face and
only it, the marker on the pivot's projection after a pan, a measurement with
its signed legs and the zero that is not drawn, a PNG the size of the canvas
drawn again before it is copied, a hand-written address restored, and the
four refusals each naming its cause. 11-17 s on an idle machine; seven pages,
two browsers at a time, each with a profile of its own under `work/tmp`.
`placeMarker` goes through `toScreen` instead of carrying a second copy of
the divide; `parsePayload` refuses a payload without the `S3DH` magic or with
another format version, and the page says so in words that name the cause,
in `TEXT` with the other messages; `decodeView` is pinned to a hand-written
address, which the round trip never was; the word greps in `test_page` are
scoped to the function that does the job or replaced by the browser check -
one of them, `span*4`, had been passing on a comment. The pivot ring, held
up on pointerdown, now lets go after a measuring click instead of staying
until the next release and landing in a saved PNG. The window's child
process: the queue is proved closed on every ending, and a child that ends
with exit code 0 without a word is reported as a death now, not taken for a
run the window waits on for ever. `test_editing` survives eight copies at
once - one clipboard and one foreground per session were the cause, a named
mutex and `focus_force` the cure. `tests/test_cli.py` gives the command line
33 checks of its own. Every suite writes its temp files under `work/tmp`,
off C:, and reads no settings file of the developer's. The table holds 244
rows, all caught; the runner was re-derived from the shared harness, which
gained a timeout for a suite that never finishes. And the standalone exe is
built again, for every version from now on - `docs/standalone.md`.

### 2 Sep 2026, at 0.9.6

A fourth pass, over everything, with a different question this time: not only
what is wrong, but what here is a monolith and what could be carried into
another project as it stands. The full list with reproductions, the structural
and functional diagrams, and the plan for taking the monoliths apart are in
`docs/` — [review-2026-09-02.md](review-2026-09-02.md),
[architecture.md](architecture.md),
[refactoring-plan.md](refactoring-plan.md). Nothing in the code was
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
