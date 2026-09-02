"""python -m step2html.gui - the window, from a checkout.

freeze_support() first: the conversion runs in a child process, which on
Windows starts as a fresh interpreter running this very module, and without
that line it would open a second window instead of doing the work.
"""
import multiprocessing as mp
import sys

from .app import main

if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
