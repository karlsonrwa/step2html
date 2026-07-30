"""A window around step_to_html.

    python gui.py

Every command line flag has a control here and nothing else does: the window
builds an Options and hands it to worker.run in a CHILD PROCESS, which is the
same Options the CLI builds. One code path, two front ends - a second
implementation of the pipeline behind a GUI is how the two drift apart.

The log is coloured the way Simple 3D colours its own, and by the same rule:
severity is read off the FIRST WORD of the line, so a message only has to say
"warning: ..." once, in the pipeline, to be marked in the terminal and in the
window alike.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import queue
import sys
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

import step_to_html as core
import worker

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "step2html_config.json"

# Colours, and the rule that picks them. Matched to Simple 3D so the two tools
# read the same way side by side.
COLOURS = {"warning": "#d9791e", "error": "#8b0000", "success": "#1a7f2e"}
MUTED = "#555"
ERROR_PREFIXES = ("error", "traceback")
WARNING_PREFIXES = ("warning", "ignored", "ignoring")

STEP_TYPES = [("STEP files", "*.step *.stp *.STEP *.STP"), ("All files", "*.*")]


def severity_of(message: str) -> str | None:
    low = message.lstrip().lower()
    if low.startswith(ERROR_PREFIXES):
        return "error"
    if low.startswith(WARNING_PREFIXES):
        return "warning"
    return None


class App:
    """The window. Constructible without mainloop, so it can be driven by a
    test - see tests/test_gui.py."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.proc = None
        self.channel = None
        self._polling = False

        root.title("step2html")
        root.minsize(620, 520)

        self.step_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.title_text = tk.StringVar()
        self.auto_deflection = tk.BooleanVar(value=True)
        self.deflection = tk.StringVar(value="0.02")
        self.angle = tk.StringVar(value="15")
        self.budget_mode = tk.StringVar(value="auto")     # auto | none | fixed
        self.budget_mb = tk.StringVar(value="")
        self.repair = tk.BooleanVar(value=True)
        self.read_only = tk.BooleanVar(value=False)
        self.open_when_done = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready")

        self._build_widgets()
        self._load_config()
        self._sync_enabled()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------------- layout

    def _build_widgets(self) -> None:
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="STEP file").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.step_path).grid(
            row=0, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Browse...", command=self._browse_step).grid(
            row=0, column=2, sticky="ew", **pad)

        ttk.Label(frame, text="Output HTML").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.out_path).grid(
            row=1, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Save as...", command=self._browse_out).grid(
            row=1, column=2, sticky="ew", **pad)

        ttk.Label(frame, text="Title").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.title_text).grid(
            row=2, column=1, columnspan=2, sticky="ew", **pad)
        ttk.Label(frame, text="Left empty, each follows the STEP's own name.",
                  foreground=MUTED).grid(row=3, column=1, columnspan=2,
                                         sticky="w", padx=6)

        mesh = ttk.LabelFrame(frame, text="Mesh", padding=8)
        mesh.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 4))
        ttk.Checkbutton(mesh, text="Deflection from the size of the model",
                        variable=self.auto_deflection,
                        command=self._sync_enabled).grid(row=0, column=0,
                                                         columnspan=2, sticky="w")
        ttk.Label(mesh, text="Deflection, mm").grid(row=1, column=0, sticky="w",
                                                    pady=(4, 0))
        self.deflection_entry = ttk.Entry(mesh, textvariable=self.deflection,
                                          width=10)
        self.deflection_entry.grid(row=1, column=1, sticky="w", padx=6, pady=(4, 0))
        ttk.Label(mesh, text="Angle, degrees").grid(row=2, column=0, sticky="w")
        ttk.Spinbox(mesh, from_=0.5, to=60.0, increment=0.5, width=10,
                    textvariable=self.angle).grid(row=2, column=1, sticky="w",
                                                  padx=6)

        size = ttk.LabelFrame(frame, text="Size budget", padding=8)
        size.grid(row=5, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Radiobutton(size, text="No larger than the STEP itself",
                        value="auto", variable=self.budget_mode,
                        command=self._sync_enabled).grid(row=0, column=0,
                                                         columnspan=2, sticky="w")
        ttk.Radiobutton(size, text="No limit", value="none",
                        variable=self.budget_mode,
                        command=self._sync_enabled).grid(row=1, column=0,
                                                         columnspan=2, sticky="w")
        ttk.Radiobutton(size, text="No larger than", value="fixed",
                        variable=self.budget_mode,
                        command=self._sync_enabled).grid(row=2, column=0,
                                                         sticky="w")
        self.budget_entry = ttk.Entry(size, textvariable=self.budget_mb, width=10)
        self.budget_entry.grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(size, text="MB").grid(row=2, column=2, sticky="w")
        ttk.Label(size, text="The mesh is refined as far as the budget allows, "
                            "which costs several builds.",
                  foreground=MUTED).grid(row=3, column=0, columnspan=3,
                                         sticky="w", pady=(4, 0))

        flags = ttk.Frame(frame)
        flags.grid(row=6, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Checkbutton(flags, text="Repair faces the mesher refuses",
                        variable=self.repair).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(flags, text="Read-only result",
                        variable=self.read_only).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(flags, text="Open when finished",
                        variable=self.open_when_done).pack(side="left")

        buttons = ttk.Frame(frame)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 2))
        self.generate_button = ttk.Button(buttons, text="Generate",
                                          command=self.generate)
        self.generate_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="Cancel",
                                        command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        ttk.Label(frame, textvariable=self.status, foreground=MUTED).grid(
            row=9, column=0, columnspan=3, sticky="w")

        self.log_view = tk.Text(frame, height=14, wrap="word", state="disabled")
        self.log_view.grid(row=10, column=0, columnspan=3, sticky="nsew",
                           pady=(6, 0))
        frame.rowconfigure(10, weight=1)
        bar = ttk.Scrollbar(frame, command=self.log_view.yview)
        bar.grid(row=10, column=3, sticky="ns", pady=(6, 0))
        self.log_view.configure(yscrollcommand=bar.set)
        for name, colour in COLOURS.items():
            self.log_view.tag_configure(name, foreground=colour)

    def _sync_enabled(self) -> None:
        self.deflection_entry.configure(
            state="disabled" if self.auto_deflection.get() else "normal")
        self.budget_entry.configure(
            state="normal" if self.budget_mode.get() == "fixed" else "disabled")

    # ---------------------------------------------------------------- pickers

    def _browse_step(self) -> None:
        start = self._remembered("last_step_dir")
        name = filedialog.askopenfilename(title="Pick a STEP file",
                                          filetypes=STEP_TYPES,
                                          initialdir=start)
        if name:
            self.set_step(name)

    def set_step(self, name: str) -> None:
        """Also fills the output path, which is what the CLI's default does."""
        self.step_path.set(name)
        if not self.out_path.get():
            self.out_path.set(str(Path(name).with_suffix(".html")))

    def _browse_out(self) -> None:
        name = filedialog.asksaveasfilename(
            title="Save the HTML as", defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("All files", "*.*")],
            initialdir=self._remembered("last_out_dir"))
        if name:
            self.out_path.set(name)

    def _remembered(self, key: str) -> str:
        return self._config.get(key, "") if hasattr(self, "_config") else ""

    # ---------------------------------------------------------------- running

    def options(self) -> core.Options:
        """The widgets, as the very same Options the CLI builds."""
        if self.budget_mode.get() == "auto":
            budget = "auto"
        elif self.budget_mode.get() == "none":
            budget = "none"
        else:
            megabytes = float(self.budget_mb.get() or 0)
            budget = str(int(megabytes * 1024 * 1024))
        return core.Options(
            step=self.step_path.get().strip(),
            out=self.out_path.get().strip(),
            title=self.title_text.get().strip(),
            deflection="auto" if self.auto_deflection.get()
                       else self.deflection.get().strip(),
            angle=float(self.angle.get()),
            max_bytes=budget,
            repair=self.repair.get(),
            read_only=self.read_only.get(),
        )

    def generate(self) -> None:
        if self.proc is not None:
            return
        try:
            opts = self.options()
        except ValueError as exc:
            self.log(f"error: a number could not be read: {exc}")
            return
        if not opts.step:
            self.log("error: pick a STEP file first")
            return

        self.clear_log()
        self.log(f"Converting {Path(opts.step).name}", "success")
        self._busy(True)
        self.channel = mp.Queue()
        self.proc = mp.Process(target=worker.run, args=(opts, self.channel),
                               daemon=True)
        self.proc.start()
        self._poll()

    def cancel(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        self.log("warning: cancelled")
        self._finish("Cancelled")

    def _poll(self) -> None:
        self._polling = True
        self.pump()
        if self.proc is not None:
            self.root.after(80, self._poll)
        else:
            self._polling = False

    def pump(self) -> None:
        """Drain the channel once. Split out so a test can step the machine
        without a mainloop."""
        # Taken locally: handling "done" or "error" clears self.channel, and
        # reading it again on the next turn of this loop would be a crash.
        channel = self.channel
        while channel is not None:
            try:
                kind, payload = channel.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log(payload)
            elif kind == "progress":
                value, total, label = payload
                self.progress["maximum"] = max(total, 1)
                self.progress["value"] = value
                if label:
                    self.status.set(label)
            elif kind == "error":
                self.log("error: " + str(payload))
                self._finish("Failed")
                break
            elif kind == "done":
                summary, output = payload
                self.log(summary, "success")
                self._finish(summary)
                if self.open_when_done.get() and Path(output).is_file():
                    webbrowser.open(Path(output).as_uri())
                break

        # A child that died without saying anything died hard - an access
        # violation inside OCCT looks exactly like this, and saying so beats
        # a window that just goes quiet.
        if self.proc is not None and not self.proc.is_alive():
            code = self.proc.exitcode
            if code not in (0, None):
                self.log(f"error: the build process stopped with exit code "
                         f"{code}, without reporting anything. That is usually "
                         f"a crash inside OCCT.")
                self._finish("Failed")

    def _finish(self, message: str) -> None:
        if self.proc is not None:
            if self.proc.is_alive():
                self.proc.terminate()
            self.proc = None
        self.channel = None
        self.status.set(message)
        self._busy(False)

    def _busy(self, running: bool) -> None:
        self.generate_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        if running:
            self.progress["value"] = 0
            self.status.set("Working...")

    # ------------------------------------------------------------------- log

    def log(self, message: str, severity: str | None = None) -> None:
        severity = severity or severity_of(message)
        self.log_view.configure(state="normal")
        self.log_view.insert("end", message.rstrip() + "\n",
                             severity or ())
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_view.configure(state="normal")
        self.log_view.delete("1.0", "end")
        self.log_view.configure(state="disabled")

    # ---------------------------------------------------------------- config

    def _load_config(self) -> None:
        self._config = {}
        try:
            self._config = json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return          # absent or unreadable: defaults, quietly
        c = self._config
        self.title_text.set(c.get("title", ""))
        self.auto_deflection.set(bool(c.get("auto_deflection", True)))
        self.deflection.set(str(c.get("deflection", "0.02")))
        self.angle.set(str(c.get("angle", "15")))
        self.budget_mode.set(c.get("budget_mode", "auto"))
        self.budget_mb.set(str(c.get("budget_mb", "")))
        self.repair.set(bool(c.get("repair", True)))
        self.read_only.set(bool(c.get("read_only", False)))
        self.open_when_done.set(bool(c.get("open_when_done", True)))
        geometry = c.get("geometry", "")
        if geometry:
            try:
                self.root.geometry(geometry)
            except tk.TclError:
                pass

    def save_config(self) -> None:
        step = self.step_path.get().strip()
        out = self.out_path.get().strip()
        data = {
            "last_step_dir": str(Path(step).parent) if step else "",
            "last_out_dir": str(Path(out).parent) if out else "",
            "title": self.title_text.get().strip(),
            "auto_deflection": self.auto_deflection.get(),
            "deflection": self.deflection.get().strip(),
            "angle": self.angle.get().strip(),
            "budget_mode": self.budget_mode.get(),
            "budget_mb": self.budget_mb.get().strip(),
            "repair": self.repair.get(),
            "read_only": self.read_only.get(),
            "open_when_done": self.open_when_done.get(),
        }
        try:
            data["geometry"] = self.root.winfo_geometry()
        except tk.TclError:
            pass
        try:
            CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass            # a read-only folder must not stop the window closing

    def _on_close(self) -> None:
        if self.proc is not None and self.proc.is_alive():
            self.proc.terminate()
        self.save_config()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
