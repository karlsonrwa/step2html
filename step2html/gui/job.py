"""A conversion in a child process, and the channel back from it.

Why a process and not a thread is in worker.py: OpenCASCADE can die outright,
and a child dying on its own leaves the window standing, with an exit code
to report. Cancel is terminate.

Nothing here is Tk. The window hands in four callbacks and calls pump()
from its own timer; a test hands in four lists and calls pump() in a loop
(tests/test_job.py). The messages are the shapes worker.py sends:

    ("log", text)
    ("progress", (value, total, label))
    ("done", (summary, output path))
    ("error", text)
"""
from __future__ import annotations

import multiprocessing as mp
import queue

DIED_SILENTLY = ("the build process stopped with exit code {code}, without "
                 "reporting anything. That is usually a crash inside OCCT.")


class Job:
    """One run of target(*args, channel) in a child process of its own."""

    def __init__(self, target, args, on_log, on_progress, on_done, on_error):
        self.target = target
        self.args = tuple(args)
        self.on_log = on_log
        self.on_progress = on_progress      # (value, total, label)
        self.on_done = on_done              # (summary, output path)
        self.on_error = on_error            # (text)
        self.proc = None
        self.channel = None
        self.finished = None                # "done", "error", "cancelled", "died"

    @property
    def running(self) -> bool:
        return self.proc is not None

    def start(self) -> None:
        self.channel = mp.Queue()
        self.proc = mp.Process(target=self.target,
                               args=(*self.args, self.channel), daemon=True)
        self.proc.start()

    def cancel(self) -> None:
        if self.proc is not None:
            self._close("cancelled")

    def pump(self) -> bool:
        """Drain the channel once. -> True while the child is still running.

        Taken locally: handling "done" or "error" clears the channel, and
        reading it again on the next turn of this loop would be a crash.
        """
        channel = self.channel
        while channel is not None and self.proc is not None:
            try:
                kind, payload = channel.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.on_log(payload)
            elif kind == "progress":
                self.on_progress(*payload)
            elif kind == "error":
                self._close("error")
                self.on_error(str(payload))
                return False
            elif kind == "done":
                summary, output = payload
                self._close("done")
                self.on_done(summary, output)
                return False

        # A child that died without saying anything died hard - an access
        # violation inside OCCT looks exactly like this, and saying so beats
        # a window that just goes quiet.
        if self.proc is not None and not self.proc.is_alive():
            code = self.proc.exitcode
            if code not in (0, None):
                self._close("died")
                self.on_error(DIED_SILENTLY.format(code=code))
                return False
        return self.proc is not None

    def _close(self, how: str) -> None:
        if self.proc is not None:
            if self.proc.is_alive():
                self.proc.terminate()
            self.proc = None
        # Closed, not merely dropped: a Queue carries a feeder thread, and a
        # window that has run a dozen conversions should not be holding a
        # dozen of them.
        if self.channel is not None:
            try:
                self.channel.close()
                self.channel.cancel_join_thread()
            except Exception:
                pass
        self.channel = None
        self.finished = how
