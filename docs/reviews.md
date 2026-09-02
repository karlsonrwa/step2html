# Reviewed

*[English](reviews.md) · [Русский](reviews.ru.md)*

Part of [step2html](../README.md). Every full pass over the code, newest first, with what it found and what was done about it.

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
