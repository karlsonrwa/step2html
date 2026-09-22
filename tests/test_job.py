"""The child process and its channel, without a window.

What the window relies on: every kind of message reaches the right callback
in order, an error or a done ends the run and reaps the child, a child that
dies without a word is reported with its exit code, and Cancel works while
the child is busy. Each child is a fresh interpreter, so this takes a few
seconds, not milliseconds - but it needs no Tk and no OCCT.

It also asks what _close() claims to do, which is more than dropping a
reference: the queue is CLOSED, on every one of the four ways a run can end.
"job.channel is None" is true of a queue nobody closed as well.
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
    # Kept before the run can end: _close() drops the reference, and a queue
    # nobody can reach any more cannot be asked whether it was closed.
    channel = job.channel
    deadline = time.time() + timeout
    while job.pump() and time.time() < deadline:
        time.sleep(0.02)
    return job, channel, logs, progress, done, errors


def still_open(channel) -> str:
    """Why this queue is NOT closed, or "" when it is.

    Measured on Python 3.14.7, from the stdlib source and by hand
    (work/probe_queue_close.py): close() sets a flag and calls the finalizer
    that _start_thread installed - and _start_thread runs on the first PUT.
    In THIS process nothing is ever put: the child does the putting, the
    parent only gets. So there is no feeder thread here and no finalizer
    either, and the pipe handles go when the object does, not when close()
    is called. Asking _reader.closed proves nothing (measured: False both
    before and after a close).

    What close() does leave behind is the flag, and it is not cosmetic: both
    put() and get() consult it and raise ValueError("Queue <...> is closed").
    That is the witness used here. It separates a queue that was CLOSED from
    one that was merely dropped, which "job.channel is None" cannot.
    """
    try:
        channel.put(("log", "after the close"))
    except ValueError as exc:
        if "closed" not in str(exc):
            return f"put() raised the wrong ValueError: {exc}"
    except Exception as exc:                  # noqa: BLE001 - that is the question
        return f"put() raised {exc!r}"
    else:
        return "put() was accepted, so close() was never called"
    try:
        channel.get_nowait()
    except ValueError:
        pass
    except Exception as exc:                  # noqa: BLE001
        return f"get() is still live: {exc!r}"
    else:
        return "get() was accepted, so close() was never called"
    feeder = getattr(channel, "_thread", None)
    if feeder is not None and feeder.is_alive():
        return "the feeder thread is still running"
    return ""


def main():
    job, channel, logs, progress, done, errors = drive(fake_worker.chatty)
    check(logs == ["hello", "warning: nearly"] and progress == [(5, 10, "half")]
          and done == [("Done: x.html, 1 bytes", "x.html")] and not errors,
          "every kind of message reaches its callback, in order",
          f"logs={logs} progress={progress} done={done} errors={errors}")
    check(job.proc is None and job.channel is None and job.finished == "done"
          and not job.running,
          "and the child is reaped and the queue let go")
    why = still_open(channel)
    check(not why, "a run that finished really closed the queue", why)

    job, channel, logs, progress, done, errors = drive(fake_worker.failing)
    check(logs == ["starting"] and errors == ["No such file: nothing.step"]
          and not done and job.finished == "error",
          "an error ends the run, and nothing follows it",
          f"logs={logs} errors={errors}")
    why = still_open(channel)
    check(not why, "an error closed the queue too", why)

    # A shorter rope than the rest: the child exits at once, and the only
    # way this takes the full timeout is the death going unnoticed - which
    # is exactly what the next line is asking about.
    job, channel, logs, progress, done, errors = drive(fake_worker.dying,
                                                       timeout=20)
    check(len(errors) == 1 and "exit code 3" in errors[0]
          and "crash" in errors[0] and job.finished == "died" and not done,
          "a child that dies without a word is reported with its exit code",
          errors[0] if errors else "no error reported")
    why = still_open(channel)
    check(not why, "and a child that died closed it as well", why)

    # The quiet twin: a child that returns without a word and exit code 0.
    # worker.py never does that, but a child that hits an early exit inside
    # something it imported would, and until 0.16.0 the window took it for
    # "still running" and waited for ever - the rope here is the whole of
    # the proof that it does not.
    started = time.time()
    job, channel, logs, progress, done, errors = drive(fake_worker.silent,
                                                       timeout=20)
    check(logs == ["quiet"] and len(errors) == 1 and "exit code 0" in errors[0]
          and "crash" not in errors[0] and job.finished == "died" and not done,
          "a child that ends quietly with code 0 is a death too, and not a crash",
          errors[0] if errors else f"no error reported; logs={logs}")
    check(time.time() - started < 15,
          "and it is noticed as it happens, not at the end of the rope",
          f"{time.time() - started:.1f} s")
    why = still_open(channel)
    check(not why, "and the queue is closed behind it", why)

    logs = []
    job = Job(fake_worker.slow, (), on_log=logs.append,
              on_progress=lambda *_a: None, on_done=lambda *_a: None,
              on_error=lambda *_a: None)
    job.start()
    channel = job.channel
    deadline = time.time() + 90
    while job.pump() and not logs and time.time() < deadline:
        time.sleep(0.02)
    check(logs == ["sleeping"] and job.running,
          "a busy child is still running after its first line")
    child = job.proc                  # taken before: cancel forgets it
    job.cancel()
    check(not job.running and job.finished == "cancelled" and job.channel is None,
          "and Cancel stops it at once")
    why = still_open(channel)
    check(not why, "Cancel closes the queue, it does not merely drop it", why)
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
