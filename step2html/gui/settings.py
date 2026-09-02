"""What the window remembers between runs.

The defaults in one place - they were spread between the window's __init__
and its _load_config, which is two places to keep in step - and a load and
a save that never raise: an absent or unreadable file means the defaults,
quietly, and a folder that cannot be written must not stop the window
closing.

Only where the MODELS are is remembered. The output folder is deliberately
not - see App.set_step for the two attempts that were both wrong in use.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path


@dataclass
class Settings:
    last_step_dir: str = ""
    title: str = ""
    auto_deflection: bool = True
    deflection: str = "0.02"
    angle: str = "15"
    budget_mode: str = "auto"        # auto | none | fixed
    budget_mb: str = ""
    repair: bool = True
    read_only: bool = False
    open_when_done: bool = True
    window_state: str = "normal"     # normal | zoomed
    geometry: str = ""               # the last NON-maximized "WxH+X+Y"

    @classmethod
    def load(cls, path) -> "Settings":
        """The file, or the defaults where there is no file to speak of.

        Each field is coerced to its own kind - a bool stays a bool, a
        number typed into a box stays the text that was typed - and a key
        the file has that this does not know is ignored, so a settings file
        from a later version does not stop an earlier one starting.
        """
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return cls()
        if not isinstance(data, dict):
            return cls()
        kw = {}
        for f in fields(cls):
            if f.name in data:
                value = data[f.name]
                kw[f.name] = (bool(value) if isinstance(f.default, bool)
                              else str(value))
        return cls(**kw)

    def save(self, path) -> bool:
        """Written, or not: False where the folder refuses, and nothing raised."""
        try:
            Path(path).write_text(json.dumps(asdict(self), indent=2),
                                  encoding="utf-8")
            return True
        except OSError:
            return False
