"""What made the file: the version with its commit, and the date.

Kept apart from everything that needs OCP, so the version can be asked for
by a window that is about to explain that OCP is missing.
"""
from __future__ import annotations

from pathlib import Path

from . import __version__


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


_commit = None


def tool_version() -> str:
    """"0.2.0 - f323ec6", or just the number where git cannot answer.

    Asked once per process and remembered: a subprocess per conversion is
    wasteful, and the answer cannot change while we run. A copy of this file
    taken somewhere without a repository still reports its number, which is
    the point of keeping the number in the source rather than deriving it.
    """
    global _commit
    if _commit is None:
        _commit = ""
        try:
            import subprocess
            here = Path(__file__).resolve().parent
            out = subprocess.run(["git", "-C", str(here), "rev-parse",
                                  "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                _commit = out.stdout.strip()
                dirty = subprocess.run(["git", "-C", str(here), "status",
                                        "--porcelain"],
                                       capture_output=True, text=True, timeout=5)
                if dirty.returncode == 0 and dirty.stdout.strip():
                    # Said out loud: a file built from an edited tree cannot be
                    # reproduced from the commit it names.
                    _commit += "+edits"
        except Exception:
            _commit = ""
    return f"{__version__} · {_commit}" if _commit else __version__


def today() -> str:
    """A date the page can show in any locale. strftime("%b") would print a
    Russian month on a Russian Windows, in the middle of an English page."""
    from datetime import date
    d = date.today()
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
