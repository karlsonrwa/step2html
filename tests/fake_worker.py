"""Stand-ins for worker.run, for tests/test_job.py.

A module of their own so a spawned child can import them by name: on
Windows the child is a fresh interpreter, and a function defined inside a
test cannot be handed to it.
"""
from __future__ import annotations

import os
import time


def chatty(channel):
    channel.put(("log", "hello"))
    channel.put(("progress", (5, 10, "half")))
    channel.put(("log", "warning: nearly"))
    channel.put(("done", ("Done: x.html, 1 bytes", "x.html")))


def failing(channel):
    channel.put(("log", "starting"))
    channel.put(("error", "No such file: nothing.step"))


def dying(channel):
    # No message first: the queue's feeder thread would not get to flush it
    # before the process is gone, and the point is a child that says nothing.
    os._exit(3)


def silent(channel):
    # One line, then a normal return: exit code 0 and no result. A child
    # that runs into an early exit inside something it imported looks
    # like this, and it is not a conversion that finished.
    channel.put(("log", "quiet"))


def slow(channel):
    channel.put(("log", "sleeping"))
    time.sleep(60)
