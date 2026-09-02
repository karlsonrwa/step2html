"""STEP assembly -> one self-contained interactive HTML file.

    step2html board.step
    python -m step2html board.step -o board.html --title "Board A0"
    python -m step2html.gui

Run by hand on a STEP that already exists, so it works on any STEP, not only
on boards. See README.md and docs/ for what has already been tried and why
the code looks the way it does - several of the obvious simplifications are
wrong, and the reasons are not guessable from the source alone.

No third-party anything: OCP tessellates, the viewer is plain WebGL2 written
out inline. The result opens by double-click in any current browser, on a
phone as well as a desktop, with no Acrobat and no internet.

The geometry travels as one raw-deflated, base64'd block with its length and
CRC32 written beside it. The page checks both BEFORE it draws and reports
damage instead of drawing something untrue - which is the one thing a 3D PDF
cannot do, since a damaged PDF simply fails to open.

One module per concern, and this file holds only what every one of them
shares. Importing the package must not import OCP: the window has to be
able to catch a missing OCP and say so in a dialog, and it cannot catch an
exception thrown before its first line runs (see gui/app.py). The pipeline
proper starts at convert.py; the OCP names come in through _occt.py.
"""
from __future__ import annotations

__version__ = "0.11.1"
"""The one place the number lives; pyproject reads it from here.

Semantic, bumped by hand: a patch is a fix, a minor is a new capability or a
change to what the generated file looks like - or, as here, to how the tool
is installed. The commit is stamped beside it at generation time, because
between two files carrying the same number there can be a dozen commits of
repairs, and the hash is what pins the source when somebody sends a file
back with a question.
"""


class ConvertError(Exception):
    """Anything that makes a conversion impossible, said in one sentence.

    Raised from the first stage onwards; the CLI turns it into a SystemExit
    with the sentence, the window into a red line in the log.
    """
