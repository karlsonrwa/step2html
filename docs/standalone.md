# Standalone

*[English](standalone.md) · [Русский](standalone.ru.md)*

Part of [step2html](../README.md).

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

Those numbers are from 0.9.6. Since 0.12.0 the pipeline uses numpy (33 MB
on disk unpacked), which the spec used to exclude and now carries; the build
has not been redone since, so expect the bundle to be larger by some part of
that.

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
