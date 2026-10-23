# Things already tried, and why it is the way it is

*[English](design-notes.md) · [Русский](design-notes.ru.md)*

Part of [step2html](../README.md). Every item here cost at least one round and would be re-broken by an obvious looking simplification; read it before changing anything it names.

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

**A keyboard shortcut bound to a letter is bound to a layout.** Tk binds
`<<Paste>>` to `<Control-Key-v>` - the keysym, the Latin letter - and under a
Russian layout the V key arrives as `??` on Tk 9.0 (`Cyrillic_ve` on others),
so Ctrl+V did nothing in any field of the window on the very machines it is
meant for, while the same key pasted everywhere else on the desktop. The
physical key is `event.keycode` and the letter is `event.keysym`; on a machine
with two layouts they agree only half the time. `gui/editing.py` goes by the
keycode and declines when the keysym is the Latin letter, or under a Latin
layout every paste would happen twice. Measured rather than assumed:
`tests/test_editing.py` switches the layout for its own thread and presses the
key by keycode - the "cannot be tested" that stood in the way was as wrong as
"no display" had been. Since 23 Sep 2026 its window, and the ones `test_gui`
maps, live on a desktop of their own (`tests/harness.keep_windows_off_screen`,
at the user's request): still mapped, so the keys and the focus behave as
before - the same 30 and 60 checks with the same verdicts, and every mutation
row caught by the same check - but nothing comes up on the user's desktop,
and the foreground the suite forces is nobody's.

**A test puts text on the clipboard as real data, never as Tk's promise.**
Tk's `clipboard_append` makes a Tk window the clipboard's owner and only
promises the text: whoever reads it waits for that window's event loop, up to
30 s, and the text dies with the process. `tests/test_editing.py` put the
user's text "back" that way, and on 23 Oct 2026, in session 0 of the 4090
where nobody else uses the clipboard, the text the clipboard held before the
suite was gone after it in 6 runs of 6 (`work/clip96/defect_probe.py`); a
reader that took the suite's turn - the named mutex Simple 3D's suite takes
too - the moment it was given away waited 0.2 s and got nothing. Now
`tests/harness.py` puts real data with Win32, the user's text is read by
another process within 10 s and put back the same way - unless the clipboard
changed since the suite's own last change, when what is there is newer and
stays: kept in 6 runs of 6, read in 0.03 s. The real clipboard brings the rest
of the session in, and the suite allows for each part: a paste gets ten
chances, since a paste inserts nothing while another program holds the
clipboard open (rdpclip.exe does, on every change, in an RDP session); a check
the clipboard changed under - the user's own copy mid-run - says "not judged"
instead of failing; and every put first tells Tk to let go of the clipboard,
because a copy Tk made while another program held it open never reached
Windows and Tk went on pasting it from its memory over the new text (2 of 2,
`work/clip96/desync_probe.py`). Each rule is made to happen once in [2], with
the menu, and has its row in the table (12 new, 256 in all). The two rules
that need a program holding the clipboard open hold it 0.25 s against ten
pastes about 51 ms apart, so the paste lands on the sixth try, about 200 ms
from either end; at 0.4 s it landed on the ninth, 60 ms from the last, and
one late holder would have failed a healthy run (try 9 in 84 runs of 84,
then try 6 in 84 of 84 for each rule, 23 Oct 2026). In the owner's
session on the 4090 all 21 rows naming `test_editing` were caught, the nine
old ones by the same checks as on 23 Sep; 8 parallel copies passed 8 of 8, and
8 beside two windows of `test_gui` 10 of 10; 84 runs on 4-16 copies had no
FAIL and no check left unjudged, and the user's text was there after all 10
rounds - the old suite, 36 runs, lost it after all 6. Two checks turned out
to pass for the wrong reason: the read-only log's paste check passed with no
key delivered at all, and the cut's check on the text the copy before it had
left - a cut that only deleted was caught by the fake events of [1], never by
the real key. The price: the suite holds the turn about 2.4 s instead of 0.2.

**The mesh export is checked face by face, not trusted by order.**
`RWGltf_CafWriter` hands the triangulations back as one primitive per face,
and on every board tried they come in exactly the order `faces()` walks them
- so the obvious code takes the k-th primitive for the k-th face and is done.
It would be right until a document arranged its shapes differently, and then
it would put one face's triangles under another face's colour and placement
with nothing to say so. So `tessellate` asks three cheap questions of each
primitive before using it - the counts, the first node's place, the first
triangle's winding - and walks the face node by node when any answer is no,
with a line in the log. On 6,614 faces the questions cost under a tenth of a
second; the alternative is a silently wrong picture.

**`Uint8Array.from` over a string is a call per character.** The base64 of
the payload was turned into bytes with `Uint8Array.from(atob(b64), c =>
c.charCodeAt(0))` - one line, the idiom every answer on the subject gives -
and on the 24 MB page that line took 3.1 s of a 4.7 s open, with the parser
blocked and nothing on screen, because the string is iterated character by
character and each character becomes a string of its own before the
callback sees it. A `for` loop over `charCodeAt` into a preallocated array
does the same in 0.1 s. It sat there through every profile of the Python
side because nobody had timed the page from the inside; the measurement in
docs/performance.md is the whole of the argument.
