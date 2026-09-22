"""The command line: every decision it makes before convert() is reached.

argparse is thin, and thin is where things go missing quietly. A flag that
is parsed and then not carried into Options does nothing at all, and the
only sign of it is a file that comes out exactly as it would have anyway -
which is not something anyone notices. Until this suite existed, cli.py,
__init__.py and __main__.py were exercised only in passing, by one call in
test_page.py that wanted a page rather than a command line.

Most of what follows replaces convert() with a recorder and reads the
decisions off the Options the command line built: no mesh, no OCCT, a
millisecond each. Three checks need a real process - one conversion of the
fixture, `python -m step2html --version`, and an interpreter that imports
the package and reports whether OCP came with it.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

from harness import ROOT, check, run, scratch
from step2html import ConvertError, cli
from step2html.meta import tool_version

# "0.15.0", or "0.15.0 · a1f5b2c" where git can answer. Either way three
# numbers: the version is read by pyproject and stamped into every page, and
# a version that is not a version is not a thing anyone can report a bug
# against.
VERSION = re.compile(r"^step2html (\d+)\.(\d+)\.(\d+)(\s|$)")


class Recorded:
    """convert(), replaced: what the command line decided, and no build.

    Answers with a Report-shaped object, because main() reads .out and .size
    off it to print the summary line - which is itself one of the decisions.
    """

    def __init__(self, out: Path, size: int = 250):
        self.calls = []
        self.out, self.size = out, size

    def __call__(self, opts, log=None, progress=None):
        self.calls.append(opts)
        if log is not None:
            log("a line from the pipeline")
        return self


def decide(argv, convert=None):
    """cli.main(argv) with the pipeline replaced.

    -> (Options or None, exit code or the SystemExit's own, stdout, stderr)
    """
    out, err = io.StringIO(), io.StringIO()
    real, cli.convert = cli.convert, convert
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    except Exception as exc:              # noqa: BLE001 - reported, not raised
        # A command line that throws is an answer too, and a readable one:
        # letting it out would end the suite here with a traceback instead of
        # naming the check that asked.
        code = f"{type(exc).__name__}: {exc}"
    finally:
        cli.convert = real
    seen = getattr(convert, "calls", [])
    return (seen[0] if seen else None), code, out.getvalue(), err.getvalue()


def from_args(argv, step: Path, out: Path | None = None, size: int = 250):
    """The Options the command line built for `step2html <step> *argv`."""
    rec = Recorded(out or step.with_suffix(".html"), size)
    opts, code, said, _err = decide([str(step)] + list(argv), rec)
    return opts, code, said


def in_a_process(args, expect_text=True):
    """Run a real interpreter. The console encoding is pinned: the version
    line carries a middle dot, and a cp1251 console would mangle it."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8",
               PYTHONUTF8="1")
    return subprocess.run([sys.executable, *args], cwd=str(ROOT), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


def main():
    with scratch("cli-") as tmp:
        here = Path(tmp).resolve()
        check(here.is_relative_to((ROOT / "work" / "tmp").resolve()),
              "the suite writes under work/tmp, not the system TEMP on C:",
              str(here))

        # Not a STEP file: convert() is replaced for everything but the last
        # block, and all main() asks of the path is its size, for the "% of
        # the STEP" in the summary.
        step = Path(tmp) / "board.step"
        step.write_bytes(b"x" * 1000)

        # ---- what the flags are, when nobody sets them ----------------- #
        plain, code, said = from_args([], step)
        check(plain is not None and plain.step == str(step),
              "the STEP named on the command line is the one converted",
              getattr(plain, "step", "convert() was never called"))
        check(plain.out == "",
              "with no -o the output is left to the pipeline, which puts it "
              "beside the STEP", repr(plain.out))
        check(plain.title == "", "with no --title the page is headed by the "
                                 "file's own name", repr(plain.title))
        check(plain.deflection == "auto",
              "the mesh deflection defaults to 'auto'", repr(plain.deflection))
        check(plain.angle == 15.0, "the angular deflection defaults to 15 "
                                   "degrees", repr(plain.angle))
        check(plain.max_bytes == "auto",
              "the size budget defaults to 'auto', the size of the STEP",
              repr(plain.max_bytes))
        check(plain.repair is True, "faces the mesher refuses are repaired "
                                    "unless told otherwise", repr(plain.repair))
        check(plain.read_only is False,
              "and the result is left writable", repr(plain.read_only))
        check(code == 0, "a conversion that worked exits 0", repr(code))

        # ---- and what they are when somebody does ---------------------- #
        elsewhere = Path(tmp) / "some folder" / "board A0.html"
        opts, _code, _said = from_args(
            ["-o", str(elsewhere), "--title", "Board A0, rev 3",
             "--deflection", "0.05", "--angle", "3", "--max-bytes", "none",
             "--no-repair", "--read-only"], step)
        check(opts.out == str(elsewhere), "-o reaches the pipeline", opts.out)
        check(opts.title == "Board A0, rev 3", "--title reaches it", opts.title)
        # As TEXT: "auto" and a number travel down the same field, and
        # float() here would have to invent something for "auto".
        check(opts.deflection == "0.05",
              "--deflection travels as the text that was typed",
              repr(opts.deflection))
        check(opts.angle == 3.0 and isinstance(opts.angle, float),
              "--angle is a number of degrees", repr(opts.angle))
        check(opts.max_bytes == "none", "--max-bytes none lifts the budget",
              repr(opts.max_bytes))
        check(opts.repair is False, "--no-repair turns the repair off",
              repr(opts.repair))
        check(opts.read_only is True, "--read-only reaches it too",
              repr(opts.read_only))

        for typed, want in (("auto", "auto"), ("none", "none"),
                            ("1048576", "1048576"), ("1.5e6", "1.5e6")):
            got, _c, _s = from_args(["--max-bytes", typed], step)
            check(got.max_bytes == want,
                  f"--max-bytes {typed} is passed on as {want!r}, for "
                  f"convert() to read", repr(got.max_bytes))

        # ---- what it says when it worked ------------------------------- #
        # 250 bytes out of a 1,000-byte STEP: the share is computed from the
        # file on disk, not from anything the report carries.
        made = Path(tmp) / "board.html"
        _opts, code, said = from_args([], step, out=made, size=250)
        check(said.splitlines()[-1] == f"{made}: 250 bytes HTML (25% of the STEP)",
              "the summary names the file, its size and its share of the STEP",
              said.splitlines()[-1] if said else "nothing printed")
        _opts, _code, said = from_args(["--read-only"], step, out=made)
        check(said.splitlines()[-1].endswith(" (read-only)"),
              "and says so when the file was made read-only",
              said.splitlines()[-1] if said else "nothing printed")
        check("a line from the pipeline" in said,
              "the pipeline's own log reaches the terminal", said.strip()[:60])

        # ---- and when it did not ---------------------------------------- #
        def refuse(_opts, log=None, progress=None):
            raise ConvertError("No such file: nothing.step")

        _opts, code, said, err = decide([str(step)], refuse)
        check(code == "No such file: nothing.step",
              "a ConvertError becomes the exit, with its own sentence as the "
              "message - not a traceback and not a bare code", repr(code))

        _opts, code, _said, err = decide([str(step), "--angle", "abc"], Recorded(made))
        check(code == 2 and "--angle" in err,
              "a number that is not one is refused by name, exit 2",
              f"{code!r}, {err.strip().splitlines()[-1] if err else 'nothing said'}")
        _opts, code, _said, err = decide([], Recorded(made))
        check(code == 2 and "step" in err,
              "and so is no STEP at all", f"{code!r}, "
              f"{err.strip().splitlines()[-1] if err else 'nothing said'}")

        # ---- --version, which is what a bug report quotes ---------------- #
        _opts, code, said, _err = decide(["--version"], Recorded(made))
        check(code == 0 and VERSION.match(said.strip()),
              "--version prints the tool's name and three-part version, "
              "and stops", f"{code!r}, {said.strip()!r}")
        check(said.strip() == f"step2html {tool_version()}",
              "which is the version the pages are stamped with",
              f"{said.strip()!r} vs {tool_version()!r}")

        # ---- the two entry points, in interpreters of their own ---------- #
        done = in_a_process(["-m", "step2html", "--version"])
        check(done.returncode == 0 and VERSION.match(done.stdout.strip()),
              "python -m step2html --version answers and exits 0",
              f"exit {done.returncode}, {done.stdout.strip()!r} "
              f"{done.stderr.strip()[:60]}")

        # The window has to be able to catch a missing OCP and say so in a
        # dialog (gui/app.py), and it cannot catch what is raised before its
        # first line runs. That promise is kept by __init__.py importing
        # nothing, and nothing else guards it.
        done = in_a_process(["-c", "import sys, step2html; "
                                   "print('OCP' in sys.modules)"])
        check(done.returncode == 0 and done.stdout.strip() == "False",
              "importing the package does not drag OCP in with it",
              f"exit {done.returncode}, {done.stdout.strip()!r} "
              f"{done.stderr.strip()[-80:]}")

        # ---- and one real trip, fixture to file ------------------------- #
        # The only thing here that meshes anything: one build at a coarse
        # mesh with the budget lifted, to pin the default output path on
        # disk rather than in an Options.
        from fixtures import coloured_assembly
        real_step = coloured_assembly(Path(tmp) / "fixture.step")
        beside = real_step.with_suffix(".html")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main([str(real_step), "--max-bytes", "none",
                             "--deflection", "0.1"])
        said = out.getvalue()
        check(code == 0 and beside.is_file(),
              "step2html board.step writes board.html beside it, and exits 0",
              f"exit {code!r}, {beside.name} "
              f"{'is there' if beside.is_file() else 'is missing'}")
        check(said.strip().splitlines()[-1].startswith(f"{beside}: "),
              "and the last line it prints is the file it wrote",
              said.strip().splitlines()[-1] if said.strip() else "nothing printed")


if __name__ == "__main__":
    sys.exit(run(main, "the command line"))
