# -*- mode: python ; coding: utf-8 -*-
"""A standalone build: no Python, no OCP, nothing to install.

    python -m PyInstaller --noconfirm packaging/step2html.spec

  STEP2HTML_ONEDIR=1    a folder instead of one file - five seconds faster to
                        start, the same size once zipped
  STEP2HTML_CONSOLE=1   a console build, for checking the pipeline from a
                        shell, where a failure can be read instead of waiting
                        in a dialog

The floor is not negotiable and it is large: OCP.pyd is 94 MB, the OCCT DLLs it
links against are another 65 MB, and VTK - which this tool does not use a line
of - is 135 MB more and cannot be left out. See below.
"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC))
REPO = os.path.dirname(HERE)

EXCLUDE = [
    # The science stack, in case anything reaches for it. numpy comes with
    # cadquery-ocp and nothing here touches it.
    "numpy", "scipy", "matplotlib", "pandas", "PIL", "IPython",
    # Build and test machinery.
    "pytest", "setuptools", "pip", "wheel", "pkg_resources",
]
# THE STANDARD LIBRARY IS LEFT ALONE. Excluding the parts this tool does not
# use - http, urllib, email, asyncio and the rest - looked free and was not:
# pathlib imports urllib for as_uri(), so the build came up dead with
# "No module named 'urllib'" out of pathlib, in a dialog, twice over, before a
# line of ours had run. All of base_library.zip is 1.2 MB of a 306 MB bundle,
# which is not where the weight is.

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[REPO],
    binaries=[],
    # The page template is three files under step2html/viewer, read at import
    # through importlib.resources; a frozen build has to carry them in the
    # same place, or page.py dies on its first line.
    datas=[(os.path.join(REPO, "step2html", "viewer"),
            os.path.join("step2html", "viewer"))],
    # The window and the worker are reached through imports the analysis can
    # see, but named anyway: a child process starts from THIS executable and
    # imports step2html.worker by name, with nothing static pointing at it.
    hiddenimports=["step2html", "step2html.cli", "step2html.convert",
                   "step2html.worker", "step2html.gui", "step2html.gui.app"],
    excludes=EXCLUDE,
    noarchive=False,
    optimize=2,                 # docstrings out of the bundled bytecode
)

# The stubs are for editors, not for running: 650 .pyi files in the OCP
# package that would otherwise be carried along.
a.datas = [d for d in a.datas if not d[0].lower().endswith((".pyi", ".txt", ".md"))]

# VTK STAYS, and that was measured rather than assumed. It arrives as DLLs
# followed out of OCP.pyd's dependency graph - 135 MB of the bundle - and
# excludes= cannot touch it, because excludes= only reaches Python imports.
# Taken out by hand, in two steps:
#
#   without vtk.libs at all -> OCP/__init__.py dies on os.add_dll_directory,
#       which it calls for that folder with no isdir() guard, unlike the one
#       it calls for cadquery_ocp.libs
#   with an EMPTY vtk.libs -> the directory is accepted and OCP.pyd then fails
#       to load, because Windows resolves every name in an import table at
#       load time and six vtk DLLs are in OCP.pyd's
#
# So the floor is what it is. Left here as the record of an experiment, so the
# next person does not spend an afternoon repeating it.
DROP = ()
if DROP:
    before = len(a.binaries)
    a.binaries = [b for b in a.binaries
                  if not os.path.basename(b[0]).lower().startswith(DROP)]
    print(f"[spec] dropped {before - len(a.binaries)} binaries")

pyz = PYZ(a.pure)

ONEDIR = os.environ.get("STEP2HTML_ONEDIR") == "1"

exe = EXE(
    pyz, a.scripts, [] if ONEDIR else a.binaries, [] if ONEDIR else a.datas, [],
    exclude_binaries=ONEDIR,
    name="step2html",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # A window, not a console: no arguments means the GUI, and a console
    # hanging behind it would be furniture. The console build is for checking.
    console=os.environ.get("STEP2HTML_CONSOLE") == "1",
    disable_windowed_traceback=False,
    icon=None,
)

if ONEDIR:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False,
                   name="step2html")
