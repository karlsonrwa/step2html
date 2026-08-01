"""The one entry point of the frozen build.

No arguments opens the window; arguments go to the command line. One binary
either way, because two would carry two copies of a 300 MB OCCT.

freeze_support() first and before anything else runs: the conversion happens in
a child process, on Windows that child is a fresh copy of this very executable,
and without this line it would open a second window instead of doing the work.
"""
import multiprocessing
import sys


def selftest(step):
    """Drive the WINDOW's own machinery, headless, against a real STEP.

    Worth having because the command line never starts a child process: a
    binary can convert perfectly from a shell and still fail the moment
    somebody presses Generate. This is that path - Tk up, Options built,
    Generate pressed, the channel pumped until the child answers - and it is
    the one thing about a frozen build that cannot be checked any other way.

    The result is a file, deliberately: a windowed build has nowhere to print.

        step2html.exe --selftest some.step   ->   some.selftest.html
    """
    import time
    import tkinter as tk
    from pathlib import Path
    import gui

    out = Path(step).with_suffix(".selftest.html")
    root = tk.Tk()
    root.withdraw()
    app = gui.App(root)
    app.set_step(step)
    app.out_path.set(str(out))
    app.budget_mode.set("none")          # one build, so this stays quick
    app.open_when_done.set(False)
    app.generate()
    if app.proc is None:
        print("FAIL: no child process was started")
        return 1
    deadline = time.time() + 300
    while app.proc is not None and time.time() < deadline:
        app.pump()
        root.update()
        time.sleep(0.05)
    ok = out.is_file() and out.stat().st_size > 0
    print(app.log_view.get("1.0", "end").strip()[-400:])
    print(f"PASS: the child process wrote {out.stat().st_size:,} bytes"
          if ok else "FAIL: nothing was written")
    return 0 if ok else 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    if len(sys.argv) > 1:
        import step_to_html
        sys.exit(step_to_html.main())
    import gui
    sys.exit(gui.main())
