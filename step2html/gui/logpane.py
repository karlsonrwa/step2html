"""The log, coloured the way Simple 3D colours its own, and by the same rule:
severity is read off the FIRST WORD of the line, so a message only has to
say "warning: ..." once, in the pipeline, to be marked in the terminal and
in the window alike.
"""
from __future__ import annotations

import tkinter as tk

# Colours, and the rule that picks them. Matched to Simple 3D so the two tools
# read the same way side by side.
COLOURS = {"warning": "#d9791e", "error": "#8b0000", "success": "#1a7f2e"}
MUTED = "#555"
ERROR_PREFIXES = ("error", "traceback")
WARNING_PREFIXES = ("warning", "ignored", "ignoring")


def severity_of(message: str) -> str | None:
    low = message.lstrip().lower()
    if low.startswith(ERROR_PREFIXES):
        return "error"
    if low.startswith(WARNING_PREFIXES):
        return "warning"
    return None


class LogPane(tk.Text):
    """A read-only Text that takes one line at a time, coloured by its first
    word unless told otherwise."""

    def __init__(self, master, **kw):
        kw.setdefault("height", 14)
        kw.setdefault("wrap", "word")
        super().__init__(master, state="disabled", **kw)
        for name, colour in COLOURS.items():
            self.tag_configure(name, foreground=colour)

    def log(self, message: str, severity: str | None = None) -> None:
        severity = severity or severity_of(message)
        self.configure(state="normal")
        self.insert("end", message.rstrip() + "\n", severity or ())
        self.see("end")
        self.configure(state="disabled")

    def clear(self) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.configure(state="disabled")
