"""The child process and its channel, without a window.

What the window relies on: every kind of message reaches the right callback
in order, an error or a done ends the run and reaps the child, a child that
dies without a word is reported with its exit code, and Cancel works while
the child is busy. Each child is a fresh interpreter, so this takes a few
seconds, not milliseconds - but it needs no Tk and no OCCT.
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import time

from harness import check, run
from step2html.gui.job import Job
import fake_worker


def drive(target, timeout=90):
    logs, progress, done, errors = [], [], [], []
    job = Job(target, (), on_log=logs.append,
              on_progress=lambda v, t, l: progress.append((v, t, l)),
              on_done=lambda s, o: done.append((s, o)),
              on_error=errors.append)
    job.start()
    deadline = time.time() + timeout
    while job.pump() and time.time() < deadline:
        time.sleep(0.02)
    return job, logs, progress, done, errors


def main():
    job, logs, progress, done, errors = drive(fake_worker.chatty)
    check(logs == ["hello", "warning: nearly"] and progress == [(5, 10, "half")]
          and done == [("Done: x.html, 1 bytes", "x.html")] and not errors,
          "every kind of message reaches its callback, in order",
          f"logs={logs} progress={progress} done={done} errors={errors}")
    check(job.proc is None and job.channel is None and job.finished == "done"
          and not job.running,
          "and the child is reaped and the queue closed")

    job, logs, progress, done, errors = drive(fake_worker.failing)
    check(logs == ["starting"] and errors == ["No such file: nothing.step"]
          and not done and job.finished == "error",
          "an error ends the run, and nothing follows it",
          f"logs={logs} errors={errors}")

    # A shorter rope than the rest: the child exits at once, and the only
    # way this takes the full timeout is the death going unnoticed - which
    # is exactly what the next line is asking about.
    job, logs, progress, done, errors = drive(fake_worker.dying, timeout=20)
    check(len(errors) == 1 and "exit code 3" in errors[0]
          and "crash" in errors[0] and job.finished == "died" and not done,
          "a child that dies without a word is reported with its exit code",
          errors[0] if errors else "no error reported")

    logs = []
    job = Job(fake_worker.slow, (), on_log=logs.append,
              on_progress=lambda *_a: None, on_done=lambda *_a: None,
              on_error=lambda *_a: None)
    job.start()
    deadline = time.time() + 90
    while job.pump() and not logs and time.time() < deadline:
        time.sleep(0.02)
    check(logs == ["sleeping"] and job.running,
          "a busy child is still running after its first line")
    child = job.proc                  # taken before: cancel forgets it
    job.cancel()
    check(not job.running and job.finished == "cancelled" and job.channel is None,
          "and Cancel stops it at once")
    # The bookkeeping above is what the window reads, and it says "cancelled"
    # just as happily with the terminate() taken out. Cancel is the one
    # thing here that has to reach the operating system.
    child.join(10)
    check(not child.is_alive() and child.exitcode is not None,
          "and the child is really dead, not merely let go",
          f"alive={child.is_alive()}, exit={child.exitcode}")

    fresh = Job(fake_worker.chatty, (), on_log=lambda *_a: None,
                on_progress=lambda *_a: None, on_done=lambda *_a: None,
                on_error=lambda *_a: None)
    check(fresh.pump() is False and fresh.finished is None,
          "pumping a job that was never started is nothing")
    fresh.cancel()
    check(fresh.finished is None, "and cancelling one is nothing either")


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(run(main, "the child process"))
