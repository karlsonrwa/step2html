"""The window, driven without a mainloop and made to do a real conversion.

Tk runs perfectly well with no display on Windows, so there is no excuse for
reviewing a GUI change by reading it. This builds the window, fills it in,
presses Generate, pumps the channel until the child process reports back, and
then looks at what actually came out - the file on disk, the progress bar, and
the colour every log line was tagged with.

It also pins the promise that every command line flag has a control: the two
front ends share one Options, and a flag with nowhere to set it is exactly the
kind of thing nobody notices.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

import tkinter as tk

from harness import ROOT, check, run, scratch
from fixtures import coloured_assembly
from step2html import convert as core
from step2html.gui import app as gui
from step2html.progress import PHASES


def tags_in(app):
    """Which colour tags the log actually used."""
    used = set()
    for name in gui.COLOURS:
        if app.log_view.tag_ranges(name):
            used.add(name)
    return used


def loaded_or_error(path):
    """Settings.load, or the exception it promises never to raise."""
    try:
        return gui.Settings.load(path)
    except Exception as exc:              # noqa: BLE001 - that is the question
        return exc


def check_severity():
    """The colour is read off the FIRST WORD, and off nothing else.

    The window's own checks only ask whether a colour was used at all, which
    a rule of "the word appears anywhere in the line" satisfies just as well
    - and that rule paints a sentence about an error that has been fixed.
    """
    for text, want in (("error: no such file", "error"),
                       ("Traceback (most recent call last):", "error"),
                       ("  warning: two faces are missing", "warning"),
                       ("ignored 3 faces", "warning"),
                       ("ignoring a hole", "warning"),
                       ("the error was in the STEP itself", None),
                       ("Done: board.html, 12 bytes", None)):
        got = gui.severity_of(text)
        check(got == want, f"{text[:34]!r} is {want}", f"got {got}")


def check_startup_failure():
    """A failure to start has to be READABLE.

    Double-clicking gui.py hands it to whichever Python the .py association
    picks, and on a machine with several that need not be the one with OCP in
    it. The message was always right and always printed - into a console that
    closes the instant the process exits, so nothing could be read. It goes
    into a dialog now, and this pins that: the dialog is put up, it names the
    interpreter, and the launcher it recommends actually exists.
    """
    from tkinter import messagebox
    shown = []
    real, messagebox.showerror = messagebox.showerror, \
        lambda title, text, **k: shown.append((title, text))
    try:
        gui._cannot_start(SystemExit("No module named 'OCP'"))
        raised = False
    except SystemExit:
        raised = True
    finally:
        messagebox.showerror = real
    check(raised and len(shown) == 1,
          "a startup failure puts up a dialog and stops",
          f"raised={raised}, dialogs={len(shown)}")
    text = shown[0][1] if shown else ""
    check(sys.executable in text,
          "and the dialog names the Python that is running")
    # The launcher sits in the project folder, two levels above the window
    # module now that the window is a package.
    check("step2html.cmd" in text
          and (Path(gui.__file__).resolve().parents[2] / "step2html.cmd").is_file(),
          "and the launcher it points at is really there")


def main():
    # Everything this suite writes goes under work/tmp on D:, never the system
    # TEMP: tempfile's default is on C:, whose write endurance the user
    # conserves on purpose, and one run of this suite writes a few megabytes.
    with scratch("gui-") as tmp:
        here = Path(tmp).resolve()
        check(here.is_relative_to((ROOT / "work" / "tmp").resolve()),
              "the suite writes under work/tmp, not the system TEMP on C:",
              str(here))

        # The window reads CONFIG in __init__, and until this line that was
        # the developer's own settings file: an angle of 3, a fixed budget of
        # 1 MB and a remembered geometry were the input to everything below,
        # on this machine and on no other. A file of the test's own, which
        # does not exist yet, so the window comes up on its documented
        # defaults. (The one written later, by save_config, is this one too.)
        gui.CONFIG = Path(tmp) / "step2html_config.json"

        root = tk.Tk()
        root.withdraw()
        app = gui.App(root)

        check_startup_failure()
        check_severity()

        # ---- every flag has a control --------------------------------- #
        flags = {f.name for f in core.Options.__dataclass_fields__.values()}
        controls = {"step": app.step_path, "out": app.out_path,
                    "title": app.title_text, "deflection": app.deflection,
                    "angle": app.angle, "max_bytes": app.budget_mode,
                    "repair": app.repair, "read_only": app.read_only}
        check(flags == set(controls), "every Options field has a control",
              f"missing {sorted(flags - set(controls))}"
              if flags - set(controls) else "")
        check(app.angle.get() == "15" and app.budget_mode.get() == "auto"
              and app.repair.get() is True,
              "and a window with no settings file comes up on the defaults",
              f"angle={app.angle.get()!r} budget={app.budget_mode.get()!r}")

        # ---- the budget radio really maps onto the flag ---------------- #
        # ---- what the window remembers, on its own ---------------------- #
        # With a file of its own, not the one this machine happens to have:
        # a settings test that reads the developer's own config proves
        # nothing anywhere else.
        cfg = Path(tmp) / "settings.json"
        cfg.write_text('{"angle": 7, "repair": false, "budget_mb": "2",'
                       ' "a key from a later version": 1}', encoding="utf-8")
        kept = gui.Settings.load(cfg)
        check(kept.repair is False and kept.angle == "7" and kept.budget_mb == "2",
              "each field keeps its own kind, and an unknown key is ignored",
              f"repair={kept.repair!r} angle={kept.angle!r}")
        check(loaded_or_error(Path(tmp) / "no such file.json") == gui.Settings(),
              "an absent settings file is the defaults, and nothing raised",
              repr(loaded_or_error(Path(tmp) / "no such file.json"))[:60])
        cfg.write_text("{not json at all", encoding="utf-8")
        check(loaded_or_error(cfg) == gui.Settings(),
              "and so is one that cannot be read", repr(loaded_or_error(cfg))[:60])
        try:
            refused = gui.Settings().save(Path(tmp) / "no such folder" / "x.json")
        except OSError as exc:
            refused = exc
        check(refused is False,
              "a folder that refuses the file is False, not an exception that "
              "stops the window closing", repr(refused))

        step = coloured_assembly(Path(tmp) / "fixture.step")
        app.set_step(str(step))
        check(app.out_path.get() == str(step.with_suffix(".html")),
              "the output lands beside the STEP", app.out_path.get())

        # A second file must take the output with it, folder and all. Both
        # earlier attempts failed here: one filled the field only when empty,
        # the other kept a folder remembered from a previous session.
        elsewhere = Path(tmp) / "another place"
        elsewhere.mkdir()
        second_step = coloured_assembly(elsewhere / "second.step")
        app.set_step(str(second_step))
        check(app.out_path.get() == str(second_step.with_suffix(".html")),
              "a second STEP moves the output to its own folder",
              app.out_path.get())
        app.set_step(str(step))

        # A name typed by hand usually has no ".html" on it. One rule, in
        # core, and the window applies the same one so the field cannot
        # promise a name the pipeline does not write. Appended and never
        # substituted: a dot that is not an extension is somebody's revision.
        folder = Path(tmp) / "output folder"
        folder.mkdir()
        for typed, want, why in (
                ("board", "board.html", "a bare name gets .html"),
                ("board.html", "board.html", "one that has it is left alone"),
                ("board.HTML", "board.HTML", "whatever case it is written in"),
                ("board.htm", "board.htm", "and .htm is an HTML file too"),
                ("board rev.3", "board rev.3.html",
                 "a dot that is not an extension survives"),
                (str(folder), str(folder / "fixture.html"),
                 "an existing folder takes the STEP's own name")):
            got = core.html_target(
                typed if typed.startswith(str(folder)) else str(Path(tmp) / typed),
                step)
            want_full = (want if want.startswith(str(folder))
                         else str(Path(tmp) / want))
            check(str(got) == want_full, why, str(got))
        check(str(core.html_target("", step)) == str(step.with_suffix(".html")),
              "and an empty field still means beside the STEP")

        app.budget_mode.set("auto")
        check(app.options().max_bytes == "auto", "budget 'auto' reaches Options")
        app.budget_mode.set("none")
        check(app.options().max_bytes == "none", "budget 'none' reaches Options")
        app.budget_mode.set("fixed"); app.budget_mb.set("1.5")
        check(app.options().max_bytes == str(int(1.5 * 1024 * 1024)),
              "megabytes are turned into bytes", app.options().max_bytes)

        app.budget_mode.set("none")          # one build, so the test is quick
        app.auto_deflection.set(True)
        app.open_when_done.set(False)
        app.read_only.set(False)
        # Typed WITHOUT an extension on purpose: this is the whole trip, from
        # a field a user filled in by hand to a file on disk.
        out = Path(tmp) / "from the window.html"
        app.out_path.set(str(Path(tmp) / "from the window"))

        # ---- press Generate, and pump until the child answers ---------- #
        app.generate()
        check(app.proc is not None, "a child process was started")
        # The rule lives in core, and the window applies it to the FIELD as
        # well - so what is written there is the name that will be written
        # on disk. The file landing where it should says nothing about this:
        # core would have appended the suffix either way.
        check(app.out_path.get() == str(out),
              "and the field now shows the name that will really be written",
              app.out_path.get())
        # ttk state FLAGS, not the "state" option: setting the flag leaves
        # the option reading "normal", so asking the option would pass while
        # the control was in fact live.
        # First that the list is a list of controls at all: "none of them is
        # live" and "none of them is stuck" are both true of an empty one,
        # and _toggleable is the code under test here.
        toggleable = app._toggleable()
        check(len(toggleable) >= 8 and app.step_entry in toggleable
              and app.generate_button in toggleable
              and app.cancel_button not in toggleable,
              "the list _busy walks holds the window's controls, and not Cancel",
              f"{len(toggleable)} widgets")
        live = [c.winfo_class() for c in toggleable
                if "disabled" not in c.state()]
        check(not live, "every control is disabled while running", str(live))
        check("disabled" not in app.cancel_button.state(),
              "Cancel is available while running")

        # Subscribed, not sampled. A small model is converted fast enough that
        # every progress message is drained by one pump(), and polling the
        # status afterwards would only ever see the last of them.
        labels = set()
        app.status.trace_add("write", lambda *_a: labels.add(app.status.get()))
        deadline = time.time() + 180
        while app.proc is not None and time.time() < deadline:
            app.pump()
            root.update()
            time.sleep(0.05)

        check(app.proc is None, "the child finished and was reaped")
        check(out.is_file(), "the HTML landed where the window was told",
              f"{out.stat().st_size:,} bytes" if out.is_file() else "missing")
        seen = {p for p in PHASES if any(p in l for l in labels)}
        check(seen == set(PHASES), "every phase was announced",
              ", ".join(sorted(seen)) or "none")
        check(app.progress["value"] == app.progress["maximum"],
              "the bar ends full",
              f"{app.progress['value']} of {app.progress['maximum']}")
        check("success" in tags_in(app), "something was logged as success")
        text = app.log_view.get("1.0", "end")
        check("Every face meshed" in text or "could not be meshed" in text,
              "the pipeline's own lines reached the window")
        check(f"Done: {out.name}" in text
              and f"{out.stat().st_size:,} bytes" in text,
              "and the summary names the file written and its size on disk",
              [l for l in text.splitlines() if l.startswith("Done")] or "no summary")

        # ---- and it opens the result, when and only when asked --------- #
        # Driven by hand rather than by a second conversion, and with the
        # opening itself replaced: a real os.startfile would put a browser
        # on the developer's screen in the middle of a test run.
        opened = []
        real_open, gui.App.open_result = gui.App.open_result, staticmethod(opened.append)
        try:
            app.open_when_done.set(True)
            app._on_done("Done: ticked", str(out))
            app.open_when_done.set(False)
            app._on_done("Done: not ticked", str(out))
        finally:
            gui.App.open_result = real_open
        check(opened == [out],
              "the result is opened when the box is ticked, and only then",
              str(opened))

        # ---- an error is coloured as one ------------------------------ #
        app.step_path.set(str(Path(tmp) / "nothing here.step"))
        app.generate()
        deadline = time.time() + 60
        while app.proc is not None and time.time() < deadline:
            app.pump(); root.update(); time.sleep(0.05)
        # The ERROR LINE has to name the file, not merely the log: the
        # window's own "Converting nothing here.step" carries the name
        # whatever the child says back.
        said = [l for l in app.log_view.get("1.0", "end").splitlines()
                if l.startswith("error:")]
        check("error" in tags_in(app) and said and "nothing here.step" in said[0],
              "a missing file is logged as an error that names the file",
              said[0] if said else "no error line at all")
        check("disabled" not in app.generate_button.state(),
              "Generate comes back after a failure")
        # This used to name a widget that does not exist, guarded by hasattr,
        # so it passed without ever looking at anything. Ask the same list
        # _busy acts on instead.
        stuck = {str(c) for c in app._toggleable() if "disabled" in c.state()}
        # The only two that may still be grey are the ones a setting greys:
        # the deflection box under "auto", and the size box unless the budget
        # is "No larger than".
        conditional = {str(app.deflection_entry), str(app.budget_entry)}
        check(stuck <= conditional, "the fields are editable again",
              f"unexpectedly disabled: {sorted(stuck - conditional)}")

        # An empty megabyte box with "No larger than" chosen must be refused,
        # not quietly turned into no limit at all.
        app.budget_mode.set("fixed"); app.budget_mb.set("")
        # The sentence, not merely a ValueError: float("") raises one of its
        # own, so "did it raise" passes with the guard deleted and the user
        # gets "could not convert string to float: ''".
        refused = ""
        try:
            app.options()
        except ValueError as exc:
            refused = str(exc)
        check("MB" in refused and "No larger than" in refused,
              "an empty size budget is refused, in words of its own",
              refused or "nothing raised")
        app.budget_mode.set("none")

        # ---- the two boxes a setting greys ----------------------------- #
        app.auto_deflection.set(True); app.budget_mode.set("auto")
        app._sync_enabled()
        check("disabled" in app.deflection_entry.state()
              and "disabled" in app.budget_entry.state(),
              "deflection and size are greyed when nothing reads them",
              f"{app.deflection_entry.state()}, {app.budget_entry.state()}")
        app.auto_deflection.set(False); app.budget_mode.set("fixed")
        app._sync_enabled()
        check("disabled" not in app.deflection_entry.state()
              and "disabled" not in app.budget_entry.state(),
              "and live when the tick and the radio say they are used",
              f"{app.deflection_entry.state()}, {app.budget_entry.state()}")
        app.auto_deflection.set(True); app.budget_mode.set("none")
        app._sync_enabled()

        # ---- Cancel, from the window ----------------------------------- #
        app.step_path.set(str(step))
        app.out_path.set(str(Path(tmp) / "cancelled.html"))
        app.clear_log()
        app.generate()
        child = app.proc
        check(child is not None, "a child was started, to be cancelled")
        app.cancel()
        child.join(10)
        check(app.job is None and app.proc is None and not child.is_alive(),
              "Cancel kills the child and the window lets the job go",
              f"alive={child.is_alive()}, exit={child.exitcode}")
        check(app.status.get() == "Cancelled" and "warning" in tags_in(app),
              "and says so, in the status line and in the log",
              f"{app.status.get()!r}, tags {sorted(tags_in(app))}")

        # ---- a number that cannot be read, and no STEP at all ---------- #
        app.budget_mode.set("fixed"); app.budget_mb.set("not a number")
        app.clear_log()
        try:
            app.generate()
            escaped = ""
        except Exception as exc:          # noqa: BLE001 - the whole question
            escaped = repr(exc)
        typed = app.log_view.get("1.0", "end")
        check(not escaped and app.job is None and "could not be read" in typed
              and "error" in tags_in(app),
              "a number that cannot be read is a line in the log, not a "
              "traceback", escaped or typed.strip()[:70] or "nothing logged")
        app.budget_mode.set("none"); app.budget_mb.set("3")

        app.step_path.set("")
        app.clear_log()
        app.generate()
        empty = app.log_view.get("1.0", "end")
        check(app.job is None and "pick a STEP file" in empty,
              "and Generate with no STEP is another", empty.strip()[:70]
              or "nothing logged")
        app.cancel()                  # nothing, unless the guard just let one through
        app.step_path.set(str(step))

        # ---- settings survive a restart ------------------------------- #
        app.angle.set("7.5"); app.budget_mode.set("fixed"); app.budget_mb.set("3")
        # gui.CONFIG has pointed into this folder since the window was built,
        # so nothing here has ever read or written the file the user has.
        check(not gui.CONFIG.exists(), "no settings file has been written yet")
        app.save_config()
        check(gui.CONFIG.is_file(), "the settings file was written")
        second = gui.App(tk.Toplevel(root))
        check(second.angle.get() == "7.5" and second.budget_mode.get() == "fixed"
              and second.budget_mb.get() == "3",
              "a second window comes up with the same settings",
              f"angle={second.angle.get()} mode={second.budget_mode.get()}")
        second.root.destroy()

        # ---- and where it comes UP ------------------------------------- #
        # The screen is asked for rather than assumed, so these hold on one
        # monitor as well as three, and on whatever this machine has today.
        vx, vy, vw, vh = gui.virtual_screen(
            (0, 0, root.winfo_screenwidth(), root.winfo_screenheight()))
        want = (700, 600, vx + 60, vy + 60)
        gui.Settings(geometry="%dx%d+%d+%d" % want).save(gui.CONFIG)
        placed = gui.App(tk.Toplevel(root))
        placed.root.update_idletasks()
        check(gui.parse(placed.root.winfo_geometry()) == want,
              "a remembered position still on a screen is where it comes back",
              placed.root.winfo_geometry())

        # And it is dragging it that is remembered, not the position it was
        # restored to: <Configure> keeps the last non-maximized rectangle.
        moved = f"640x540+{vx + 120}+{vy + 120}"
        placed.root.geometry(moved)
        placed.root.update()
        placed.save_config()
        check(gui.Settings.load(gui.CONFIG).geometry == moved,
              "and where it was last moved to is what gets written down",
              gui.Settings.load(gui.CONFIG).geometry)
        placed.root.destroy()

        # A monitor that has been unplugged: the remembered place cannot be
        # grabbed any more, so it is not used - and the log says why.
        gui.Settings(geometry=f"620x855+{vx - 9000}+{vy - 9000}").save(gui.CONFIG)
        lost = gui.App(tk.Toplevel(root))
        lost.root.update_idletasks()
        here = gui.parse(lost.root.winfo_geometry())
        check(here is not None and gui.reachable(*here, (vx, vy, vw, vh)),
              "one on a monitor that is gone is centred where it can be grabbed",
              lost.root.winfo_geometry())
        deadline = time.time() + 3
        while "off-screen" not in lost.log_view.get("1.0", "end") and time.time() < deadline:
            root.update(); time.sleep(0.05)
        check("off-screen" in lost.log_view.get("1.0", "end"),
              "and the log says why it is not where it was left",
              lost.log_view.get("1.0", "end").strip()[:70] or "nothing logged")
        lost.root.destroy()

    root.destroy()


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(run(main, "the window"))
