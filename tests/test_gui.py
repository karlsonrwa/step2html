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
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk

import gui
import step_to_html as core
from fixtures import coloured_assembly

FAILURES = []


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def tags_in(app):
    """Which colour tags the log actually used."""
    used = set()
    for name in gui.COLOURS:
        if app.log_view.tag_ranges(name):
            used.add(name)
    return used


def main():
    root = tk.Tk()
    root.withdraw()
    app = gui.App(root)

    # ---- every flag has a control ------------------------------------- #
    flags = {f.name for f in core.Options.__dataclass_fields__.values()}
    controls = {"step": app.step_path, "out": app.out_path,
                "title": app.title_text, "deflection": app.deflection,
                "angle": app.angle, "max_bytes": app.budget_mode,
                "repair": app.repair, "read_only": app.read_only}
    check(flags == set(controls), "every Options field has a control",
          f"missing {sorted(flags - set(controls))}" if flags - set(controls) else "")

    # ---- the budget radio really maps onto the flag -------------------- #
    with tempfile.TemporaryDirectory() as tmp:
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
        out = Path(tmp) / "from the window.html"
        app.out_path.set(str(out))

        # ---- press Generate, and pump until the child answers ---------- #
        app.generate()
        check(app.proc is not None, "a child process was started")
        # ttk state FLAGS, not the "state" option: setting the flag leaves
        # the option reading "normal", so asking the option would pass while
        # the control was in fact live.
        live = [c.winfo_class() for c in app._toggleable()
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
        seen = {p for p in core.PHASES if any(p in l for l in labels)}
        check(seen == set(core.PHASES), "every phase was announced",
              ", ".join(sorted(seen)) or "none")
        check(app.progress["value"] == app.progress["maximum"],
              "the bar ends full",
              f"{app.progress['value']} of {app.progress['maximum']}")
        check("success" in tags_in(app), "something was logged as success")
        text = app.log_view.get("1.0", "end")
        check("Every face meshed" in text or "could not be meshed" in text,
              "the pipeline's own lines reached the window")

        # ---- an error is coloured as one ------------------------------ #
        app.step_path.set(str(Path(tmp) / "nothing here.step"))
        app.generate()
        deadline = time.time() + 60
        while app.proc is not None and time.time() < deadline:
            app.pump(); root.update(); time.sleep(0.05)
        check("error" in tags_in(app), "a missing file is logged as an error")
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
        refused = False
        try:
            app.options()
        except ValueError:
            refused = True
        check(refused, "an empty size budget is refused rather than ignored")
        app.budget_mode.set("none")

        # ---- settings survive a restart ------------------------------- #
        app.angle.set("7.5"); app.budget_mode.set("fixed"); app.budget_mb.set("3")
        gui.CONFIG = Path(tmp) / "step2html_config.json"
        app.save_config()
        check(gui.CONFIG.is_file(), "the settings file was written")
        second = gui.App(tk.Toplevel(root))
        check(second.angle.get() == "7.5" and second.budget_mode.get() == "fixed"
              and second.budget_mb.get() == "3",
              "a second window comes up with the same settings",
              f"angle={second.angle.get()} mode={second.budget_mode.get()}")

    root.destroy()
    return 1 if FAILURES else 0


if __name__ == "__main__":
    mp.freeze_support()
    print("the window")
    sys.exit(main())
