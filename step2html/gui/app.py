"""A window around the pipeline.

    python -m step2html.gui

Every command line flag has a control here and nothing else does: the window
builds an Options and hands it to worker.run in a CHILD PROCESS, which is the
same Options the CLI builds. One code path, two front ends - a second
implementation of the pipeline behind a GUI is how the two drift apart.

What is here is the widgets and the wiring between them. The child process
and its channel are job.py, the coloured log is logpane.py, where the window
goes is geometry.py, what it remembers is settings.py, and how a field is
edited - the right-click menu, and Ctrl+C/V under a keyboard layout that is
not Latin - is editing.py; each of them without a window, and three of them
tested without one.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from step2html import __version__


def _cannot_start(problem: BaseException) -> "None":
    """Say it in a WINDOW, because the console is about to disappear.

    Double-clicking a .py hands it to whichever Python the file association
    picks - on Windows usually the py launcher - and on a machine with more
    than one Python installed that need not be the one OCP was installed
    into. The pipeline already reports that clearly, and already reports it
    the only way a console program can: it prints and exits. What the user
    sees is a black window that flashes and closes, and no way to read a word
    of it. Reported from the field twice, with the same workaround both times:
    a batch file, which keeps the console alive.

    tkinter is in the standard library and is present whatever else is
    missing, so the same words can go somewhere they stay - and this names the
    interpreter that is running, which is the one fact that actually settles
    it.
    """
    # Which interpreter is running is the fact that settles this, so the
    # dialog always carries it - and exactly once, since the pipeline's own
    # message about a missing OCP already names it.
    where = ("" if sys.executable in str(problem)
             else f"\n\nStarted with: {sys.executable}")
    text = (f"{problem}{where}\n\n"
            f"The usual cause is a Python other than the one OCP was "
            f"installed into. step2html.cmd, in the project folder, runs a "
            f"Python of your choosing and keeps the console open when "
            f"something goes wrong.")
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("step2html cannot start", text)
        root.destroy()
    except Exception:
        # No display, or no Tk either. Hold the console open instead, which
        # is the whole point - a message nobody can read is not a message.
        print(text)
        try:
            input("\nPress Enter to close...")
        except Exception:
            pass
    raise SystemExit(1)


try:
    from step2html import convert as core
    from step2html import worker
except BaseException as _exc:      # SystemExit included: that is how core says it
    _cannot_start(_exc)

from step2html.gui import editing
from step2html.gui.geometry import (FIRST_RUN_SIZE, centred, parse, reachable,
                                    virtual_screen)
from step2html.gui.job import Job
from step2html.gui.logpane import COLOURS, MUTED, LogPane, severity_of  # noqa: F401 - COLOURS and severity_of are this module's public face too
from step2html.gui.settings import Settings

# The project folder, two levels up from this file: the settings file sits
# beside step2html.cmd, where it always has, and not inside the package.
ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "step2html_config.json"

STEP_TYPES = [("STEP files", "*.step *.stp *.STEP *.STP"), ("All files", "*.*")]


class App:
    """The window. Constructible without mainloop, so it can be driven by a
    test - see tests/test_gui.py."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self.job: Job | None = None
        self._last_normal_geometry = ""

        root.title(f"step2html {__version__}")
        root.minsize(620, 520)

        # The defaults live in Settings, and a settings file overrides them
        # field by field; the widgets are then built from the result.
        s = self.settings = Settings.load(CONFIG)
        self.step_path = tk.StringVar()
        self.out_path = tk.StringVar()
        self.title_text = tk.StringVar(value=s.title)
        self.auto_deflection = tk.BooleanVar(value=s.auto_deflection)
        self.deflection = tk.StringVar(value=s.deflection)
        self.angle = tk.StringVar(value=s.angle)
        self.budget_mode = tk.StringVar(value=s.budget_mode)   # auto | none | fixed
        self.budget_mb = tk.StringVar(value=s.budget_mb)
        self.repair = tk.BooleanVar(value=s.repair)
        self.read_only = tk.BooleanVar(value=s.read_only)
        self.open_when_done = tk.BooleanVar(value=s.open_when_done)
        self.status = tk.StringVar(value="Ready")

        self._build_widgets()
        self._sync_enabled()
        self._restore_geometry()
        root.bind("<Configure>", self._remember_geometry)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def proc(self):
        """The child process while one runs, else None - what a test and the
        frozen build's --selftest wait on."""
        return self.job.proc if self.job is not None else None

    # ---------------------------------------------------------------- layout

    def _build_widgets(self) -> None:
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="STEP file").grid(row=0, column=0, sticky="w", **pad)
        self.step_entry = ttk.Entry(frame, textvariable=self.step_path)
        self.step_entry.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Browse...", command=self._browse_step).grid(
            row=0, column=2, sticky="ew", **pad)

        ttk.Label(frame, text="Output HTML").grid(row=1, column=0, sticky="w", **pad)
        self.out_entry = ttk.Entry(frame, textvariable=self.out_path)
        self.out_entry.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Save as...", command=self._browse_out).grid(
            row=1, column=2, sticky="ew", **pad)

        ttk.Label(frame, text="Title").grid(row=2, column=0, sticky="w", **pad)
        self.title_entry = ttk.Entry(frame, textvariable=self.title_text)
        self.title_entry.grid(row=2, column=1, columnspan=2, sticky="ew", **pad)
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

        self.log_view = LogPane(frame)
        self.log_view.grid(row=10, column=0, columnspan=3, sticky="nsew",
                           pady=(6, 0))
        frame.rowconfigure(10, weight=1)
        bar = ttk.Scrollbar(frame, command=self.log_view.yview)
        bar.grid(row=10, column=3, sticky="ns", pady=(6, 0))
        self.log_view.configure(yscrollcommand=bar.set)

        # Every field takes a paste - by right-click, and by Ctrl+V whatever
        # the keyboard layout - and the log copies the same way. The Spinbox
        # is left to Tk: its arrows are the control. See editing.py.
        for field in (self.step_entry, self.out_entry, self.title_entry,
                      self.deflection_entry, self.budget_entry):
            editing.attach(field, self._frozen)
        editing.attach_shortcuts(self.log_view)

    def _frozen(self) -> bool:
        """Whether the fields take no edits: a build is in flight, and the
        Options were taken when Generate was pressed. What the edit menu asks
        before it shows."""
        return self.job is not None

    def _sync_enabled(self) -> None:
        """State FLAGS, the same mechanism _busy uses. The "state" option is a
        second way of saying it, and two ways of saying one thing eventually
        disagree."""
        self.deflection_entry.state(
            ["disabled"] if self.auto_deflection.get() else ["!disabled"])
        self.budget_entry.state(
            ["!disabled"] if self.budget_mode.get() == "fixed" else ["disabled"])

    # ---------------------------------------------------------------- pickers

    def _browse_step(self) -> None:
        name = filedialog.askopenfilename(title="Pick a STEP file",
                                          filetypes=STEP_TYPES,
                                          initialdir=self._step_dir())
        if name:
            self.set_step(name)

    def _step_dir(self) -> str:
        """Where "Browse..." should open: beside the STEP CURRENTLY chosen.

        The remembered folder is the one this session started in, and it only
        applies until a file has been picked. Reading it every time meant that
        after converting a board from one folder, Browse went back to
        wherever the PREVIOUS session had been - which is the second time a
        remembered folder has overruled the one in front of the user.
        """
        current = self.step_path.get().strip()
        if current:
            return str(Path(current).parent)
        return self.settings.last_step_dir

    def set_step(self, name: str) -> None:
        """Point at a STEP; the output goes BESIDE IT, every time.

        One rule, and it is the command line's rule. Two attempts at being
        clever were both wrong in use. Filling the field in only when empty
        left the second board of a session pointed at the first one's name in
        the first one's folder. Remembering a folder chosen once through
        "Save as..." was worse: restored from the settings file it made every
        later session start as though a destination had been chosen by hand,
        so opening a STEP proposed writing somewhere else entirely.

        Somewhere else is what "Save as..." is for, and it applies to the one
        conversion in front of you.
        """
        chosen = Path(name)
        self.step_path.set(str(chosen))
        self.out_path.set(str(chosen.with_suffix(".html")))

    def _browse_out(self) -> None:
        name = filedialog.asksaveasfilename(
            title="Save the HTML as", defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("All files", "*.*")],
            initialdir=self._out_dir())
        if name:
            # str(Path(...)) throughout: the dialogs hand back forward slashes
            # on Windows while pathlib prints backslashes, and the two fields
            # sitting next to each other in different styles look like a bug.
            self.out_path.set(str(Path(name)))

    def _out_dir(self) -> str:
        """Where "Save as..." should open: at the output already proposed,
        which is beside the STEP. Not at some folder written to in a previous
        session - that is how this got the destination wrong in the first
        place."""
        for candidate in (self.out_path.get().strip(), self.step_path.get().strip()):
            if candidate:
                return str(Path(candidate).parent)
        return ""

    # ---------------------------------------------------------------- running

    def options(self) -> core.Options:
        """The widgets, as the very same Options the CLI builds."""
        if self.budget_mode.get() == "auto":
            budget = "auto"
        elif self.budget_mode.get() == "none":
            budget = "none"
        else:
            typed = self.budget_mb.get().strip()
            if not typed:
                # Empty would reach convert() as "0", which it reads as no
                # limit at all - the opposite of what the radio button says.
                raise ValueError("a size in MB is needed for 'No larger than'")
            budget = str(int(float(typed) * 1024 * 1024))
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
        if self.job is not None:
            return
        try:
            opts = self.options()
        except ValueError as exc:
            self.log(f"error: a number could not be read: {exc}")
            return
        if not opts.step:
            self.log("error: pick a STEP file first")
            return
        # Show the name that will actually be written, before writing it. The
        # rule lives in core.html_target and is applied there too, so the field
        # cannot end up promising something the pipeline does not do - a name
        # typed without ".html" gets one either way.
        target = str(core.html_target(opts.out, Path(opts.step)))
        if target != opts.out:
            self.out_path.set(target)
            opts = self.options()

        self.clear_log()
        self.log(f"Converting {Path(opts.step).name}", "success")
        self._busy(True)
        self.job = Job(worker.run, (opts,), on_log=self.log,
                       on_progress=self._on_progress, on_done=self._on_done,
                       on_error=self._on_error)
        self.job.start()
        self._poll()

    def cancel(self) -> None:
        if self.job is None:
            return
        self.job.cancel()
        self.log("warning: cancelled")
        self._finish("Cancelled")

    def _poll(self) -> None:
        self.pump()
        if self.job is not None:
            self.root.after(80, self._poll)

    def pump(self) -> None:
        """Drain the channel once. Split out so a test can step the machine
        without a mainloop."""
        if self.job is not None:
            self.job.pump()

    def _on_progress(self, value, total, label) -> None:
        self.progress["maximum"] = max(total, 1)
        self.progress["value"] = value
        if label:
            self.status.set(label)

    def _on_done(self, summary: str, output: str) -> None:
        self.log(summary, "success")
        self._finish(summary)
        if self.open_when_done.get():
            self.open_result(Path(output))

    def _on_error(self, text: str) -> None:
        self.log("error: " + text)
        self._finish("Failed")

    @staticmethod
    def open_result(path: Path) -> None:
        """Open the finished file the way double-clicking it would.

        webbrowser.open() with a file:// URI hands the URI to whatever is
        registered for the PROTOCOL, which on Windows need not be the program
        that opens .html files - so the page came up in a browser the user had
        not chosen. os.startfile on the path itself uses the file association,
        which is what "open this file" means.
        """
        if not path.is_file():
            return
        try:
            os.startfile(str(path))          # Windows only, and the right call
        except AttributeError:
            webbrowser.open(path.as_uri())   # everywhere else
        except OSError:
            # No program registered for .html. Nothing to do about it here,
            # and it must not escape: this runs inside the poll loop, and an
            # exception there stops the loop and leaves the window stuck.
            webbrowser.open(path.as_uri())

    def _finish(self, message: str) -> None:
        if self.job is not None:
            self.job.cancel()             # nothing, if it has already ended
            self.job = None
        self.status.set(message)
        self._busy(False)

    def _busy(self, running: bool) -> None:
        """Everything off but Cancel while a build is in flight.

        Walked rather than listed: a control added later and forgotten off a
        list would stay live during a build, and editing a field mid-build
        does nothing to the build in flight - the Options were taken when
        Generate was pressed - so a field that still accepts typing is simply
        lying about what it affects.
        """
        for widget in self._toggleable():
            try:
                widget.state(["disabled"] if running else ["!disabled"])
            except (tk.TclError, AttributeError):
                pass
        self.cancel_button.state(["!disabled"] if running else ["disabled"])
        if not running:
            self._sync_enabled()      # the auto/fixed greying, back as it was
        if running:
            self.progress["value"] = 0
            self.status.set("Working...")

    def _toggleable(self):
        """Every ttk control except Cancel, the bar and the log."""
        keep = {str(self.cancel_button), str(self.progress), str(self.log_view)}
        out = []

        def walk(widget):
            for child in widget.winfo_children():
                if str(child) not in keep and hasattr(child, "state"):
                    if not isinstance(child, (ttk.Label, ttk.Frame,
                                              ttk.LabelFrame, ttk.Scrollbar)):
                        out.append(child)
                walk(child)

        walk(self.root)
        return out

    # ------------------------------------------------------------------- log

    def log(self, message: str, severity: str | None = None) -> None:
        self.log_view.log(message, severity)

    def clear_log(self) -> None:
        self.log_view.clear()

    # --------------------------------------------------- window placement --

    def _screen(self):
        """The whole virtual desktop, with the primary display as the answer
        wherever Windows cannot be asked."""
        return virtual_screen((0, 0, self.root.winfo_screenwidth(),
                               self.root.winfo_screenheight()))

    def _centre(self) -> None:
        """A first run, or a remembered position that is no longer usable."""
        self.root.update_idletasks()
        w, h = FIRST_RUN_SIZE
        h = max(h, self.root.winfo_reqheight())
        self.root.geometry(f"{w}x{h}")
        self.root.update_idletasks()
        x, y = centred(w, h, self.root.winfo_screenwidth(),
                       self.root.winfo_screenheight())
        self.root.geometry(f"+{x}+{y}")

    def _restore_geometry(self) -> None:
        remembered = parse(self.settings.geometry)
        if remembered is not None:
            w, h, x, y = remembered
            if reachable(w, h, x, y, self._screen()):
                self.root.geometry(f"{w}x{h}+{x}+{y}")
                if self.settings.window_state == "zoomed":
                    try:
                        self.root.state("zoomed")
                    except tk.TclError:
                        pass
                return
            self.root.after(200, lambda: self.log(
                "warning: the remembered window position is off-screen (a "
                "monitor may have been disconnected); centred instead"))
        self._centre()

    def _remember_geometry(self, event=None) -> None:
        """Keep the last NON-maximized geometry. Bound to <Configure>.

        Maximizing arrives as a Configure that can still be seen while state()
        reports "normal", so without the second filter the maximized rectangle
        gets recorded as if the user had chosen it, and unmaximizing later
        restores nothing.

        Only the root's own Configure counts. A binding on a toplevel sits in
        the bindtags of every widget under it, so this fires once per field
        and button laid out, and each of those was asking Tk for the geometry
        again.
        """
        if event is not None and event.widget is not self.root:
            return
        try:
            if self.root.state() != "normal":
                return
            geometry = self.root.winfo_geometry()
        except tk.TclError:
            return
        if parse(geometry) is not None:
            self._last_normal_geometry = geometry

    # ---------------------------------------------------------------- config

    def save_config(self) -> None:
        step = self.step_path.get().strip()
        # The NON-maximized rectangle, plus whether it was maximized - so a
        # window closed maximized comes back maximized and unmaximizes to the
        # size it had before, rather than to the whole screen.
        try:
            state = self.root.state()
        except tk.TclError:
            state = "normal"
        Settings(
            # Only where the MODELS are. The output folder is deliberately not
            # remembered - see set_step.
            last_step_dir=str(Path(step).parent) if step else "",
            title=self.title_text.get().strip(),
            auto_deflection=self.auto_deflection.get(),
            deflection=self.deflection.get().strip(),
            angle=self.angle.get().strip(),
            budget_mode=self.budget_mode.get(),
            budget_mb=self.budget_mb.get().strip(),
            repair=self.repair.get(),
            read_only=self.read_only.get(),
            open_when_done=self.open_when_done.get(),
            window_state="zoomed" if state == "zoomed" else "normal",
            geometry=(self._last_normal_geometry
                      or self.settings.geometry
                      or (self.root.winfo_geometry()
                          if state == "normal" else "")),
        ).save(CONFIG)            # a read-only folder must not stop the window closing

    def _on_close(self) -> None:
        if self.job is not None:
            self.job.cancel()
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
