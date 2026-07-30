"""The conversion, run in a process of its own.

**Why a process and not a thread.** OpenCASCADE can die outright - an access
violation rather than an exception - and a thread cannot survive that: it
takes the whole interpreter with it, and with a window on top that means the
window simply vanishes with nothing written anywhere. A child process dies on
its own and the parent still has its exit code, which is the difference
between a bug report and a mystery. It also makes Cancel trivial: terminate
the child.

Everything here must be picklable and **must not import tkinter**. On Windows
the child is spawned rather than forked, so it re-imports this module from
scratch; dragging the toolkit in would build a second, invisible Tk.

Message shapes on the channel, which the window understands:
    ("log", text)
    ("progress", (value, total, label))
    ("done", (summary, output path))
    ("error", text)
"""
from __future__ import annotations

import traceback

import step_to_html as core


def run(opts: "core.Options", channel) -> None:
    """Convert, reporting everything through *channel*. Never raises."""
    try:
        report = core.convert(
            opts,
            log=lambda m: channel.put(("log", m)),
            progress=lambda v, t, label: channel.put(("progress", (v, t, label))),
        )
    except core.ConvertError as exc:
        # Something the user can act on: a missing file, a STEP with no shapes.
        channel.put(("error", str(exc)))
        return
    except Exception:
        # Anything else is a bug. Keep the traceback so it can be reported.
        channel.put(("error", traceback.format_exc()))
        return

    summary = f"Done: {report.out.name}, {report.size:,} bytes"
    if report.missing:
        summary += f", {len(report.missing)} face(s) missing"
    channel.put(("done", (summary, str(report.out))))
