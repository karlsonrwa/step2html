"""What every suite needs, and used to carry a copy of.

Four suites, four copies of check() and of the FAILURES list, two of the
face walk, and fifteen degrees written out as a float in three places. One
copy here, so a suite says what it checks rather than how.

Each suite is still a process of its own - see run_all.py - so what is
shared is code, not state: FAILURES is per suite by construction.

Nothing here imports OCP at module level. The suites that need no OCCT at
all - the budget search, the progress bar - come through here too, and an
import at the top would drag ninety megabytes into a test of arithmetic.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# The project root and this folder, so the pipeline and the fixtures import
# from wherever the suite is started.
TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
for _p in (str(ROOT), str(TESTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ANGULAR = 15 * 3.141592653589793 / 180.0      # the CLI default, in radians
FAILURES: list[str] = []

# Where a suite puts what it writes and throws away. tempfile's default is
# the system TEMP on C:, and the user keeps writes off that drive on purpose
# (its endurance is finite and this suite alone writes a few megabytes a
# run); work/ is gitignored and never travels into a mutation copy.
SCRATCH = ROOT / "work" / "tmp"


def scratch(prefix: str = "suite-"):
    """A temporary directory under work/tmp, removed when the with ends."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=str(SCRATCH))


def check(ok, what, detail=""):
    print(f"  {'pass' if ok else 'FAIL'}  {what}"
          + (f"   {detail}" if detail else ""))
    if not ok:
        FAILURES.append(what)


def area(shape) -> float:
    """Surface area, as OCCT's own opinion of it."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, props)
    return props.Mass()


def run(main, title: str) -> int:
    """Print the title, run the suite, and answer 0 only if nothing failed."""
    print(title)
    main()
    return 1 if FAILURES else 0


# Kept open for the life of the process: a desktop disappears with its last
# handle, and the windows on it with it.
_OWN_DESKTOP = None


def keep_windows_off_screen() -> str:
    """Put every window THIS thread creates from now on on a desktop of its
    own - "step2html-tests", in the same Windows session - that nobody looks at.

    Two suites need windows that are really mapped: test_editing, because a
    withdrawn window drops a generated key, and test_gui, whose second,
    third and fourth App live in Toplevels. On the user's desktop they came
    up while the suites ran - measured 2026-09-23, test_editing's main window
    (off every screen, but with a taskbar button, and it takes the foreground
    to get its keys) and two of test_gui's - and a mutation run starts copies
    at once. The user asked for them to go: on a desktop of their own they
    are the same mapped windows, seen by nobody, with no taskbar button, and
    the focus they force is taken from no one. The clipboard is the session's
    all the same, so test_editing's turn stays.

    Must run before the thread's first window - Tk's, at the first Tk().
    Returns "" once done, or why it could not be; the windows are then shown
    as before, which is not a failure of the suite.
    """
    global _OWN_DESKTOP
    if sys.platform != "win32":
        return "not Windows"
    if _OWN_DESKTOP is not None:
        return ""
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.CreateDesktopW.restype = wintypes.HANDLE
    u32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p,
                                   wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    u32.SetThreadDesktop.restype = wintypes.BOOL
    u32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    GENERIC_ALL = 0x10000000
    # Created by the first suite, opened by every later one: CreateDesktopW
    # hands back the existing desktop of that name.
    desktop = u32.CreateDesktopW("step2html-tests", None, None, 0, GENERIC_ALL, None)
    if not desktop:
        return f"CreateDesktopW failed with error {ctypes.GetLastError()}"
    if not u32.SetThreadDesktop(desktop):
        return f"SetThreadDesktop failed with error {ctypes.GetLastError()}"
    _OWN_DESKTOP = desktop
    return ""


# ---- text on the clipboard as real data, never as Tk's promise ----------- #

CF_UNICODETEXT = 13


class ClipboardBusy(Exception):
    """Another program kept the clipboard open past a wait, so whatever needed
    it can be judged neither way. A check that meets it says "not judged" and
    fails nothing: a FAIL the session caused, not the code, makes an unrelated
    mutation read as caught. On 23.10.2026 "Ctrl+X cuts it" failed that way -
    the put waited its 2 s while the owner copied something in his RDP
    session (rdpclip.exe carries such a copy across) - the same rule as
    Simple 3D's round 98."""


def clipboard_owned_here() -> bool:
    """Whether the clipboard's owner is a window of this process: then text
    on it put with Tk's clipboard_append - or Tk's own Copy - is this
    process's own promise."""
    if sys.platform != "win32":
        return False
    import ctypes
    import os
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.GetClipboardOwner.restype = wintypes.HWND
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    owner = u32.GetClipboardOwner()
    if not owner:
        return False
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(owner, ctypes.byref(pid))
    return pid.value == os.getpid()


def _busy(what: str) -> str:
    """The clipboard stayed out of reach: raise ClipboardBusy - unless this
    process owns it. Then what keeps it out of reach is this process's own
    promise, a reader sitting on a render this process never gives: under
    the mutation that puts the user's text back with Tk, rdpclip.exe opened
    the clipboard to read the promise and stayed (23.10.2026). That defect is
    this process's, so *what* comes back for the caller to fail on."""
    if clipboard_owned_here():
        return f"{what}, while the clipboard is this process's own promise"
    raise ClipboardBusy(f"{what}: another program kept the clipboard open")


def clipboard_shown(text, own=()) -> str:
    """What a check may print of text that came off the clipboard, or out of
    a widget it was pasted into: the text when every line of it is one of the
    suite's own (*own*), or when there is none - else only its length. The
    clipboard holds whatever the user last copied, a password as easily as a
    path, and this suite prints a check's detail even when it passes: on
    23.10.2026 the owner's copied text went into 18 stress logs on the 4090
    that way."""
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not text or all(line in own for line in lines):
        return repr(text)
    return f"{len(text)} characters that are not this suite's"


def put_clipboard_text(text, seconds: float = 10.0, pump=None) -> str:
    """Put *text* on the Windows clipboard as real data - or empty it, for
    None. Returns "" once done, or why it could not be; raises ClipboardBusy
    when another program keeps the clipboard open for *seconds*.

    *pump* - a Tk window's update - is called while the put waits. A copy of
    Tk's own (the app's Copy, Ctrl+C) is a promise, and a reader that opens
    the clipboard to read it - rdpclip.exe does on every change, in an RDP
    session - sits there until this process renders it: a put that waits
    without pumping waits for that reader, which waits for the put. 1 of 8
    parallel copies failed "Ctrl+X cuts it" that way, the put giving up after
    10 s with the clipboard still this process's own (23.10.2026).

    Not with Tk's clipboard_clear/clipboard_append. Those make a Tk window
    the clipboard's OWNER and only promise the text: Windows asks the owner
    for it when somebody reads (delayed rendering), so a reader waits for the
    owner's event loop - up to 30 s, after which it gets nothing - and the
    text dies with the process. Measured for Simple 3D on the 4090 (its
    round 96, 23.10.2026): an owner asleep 8 s held a reader 7.5 s, one past
    30 s left it with nothing after exactly 30.0 s, one that had exited left
    no text at all; text put here was read at once while its writer slept.
    And here the same day, in session 0 of the 4090, where nobody else uses
    the clipboard (work/clip96/defect_probe.py): the text the clipboard held
    before test_editing was gone after it in 6 runs of 6, because the suite
    "put it back" through Tk and exited; a reader that took the turn the
    moment the suite gave it away waited 0.2 s for the dying owner and got
    nothing - which is what the next copy to take the turn, of this suite or
    of Simple 3D's (it takes the turn by name), reads as the user's text.

    Opened with no owner window, so nobody's event loop is ever needed and
    the text outlives this process. Another process may hold the clipboard
    open for a while - DefenderSessionHelper.exe for a moment, rdpclip.exe
    while it reads a change - so the put waits up to *seconds* and then
    leaves the verdict to _busy, never to a plain failure. (A put that gave
    up after 2 s in the owner's session was put down to the owner's copy
    over RDP; it was the same check, right after the app's Cut, as the
    deadlock above - which of the two it was is not measured.)
    """
    if sys.platform != "win32":
        return "not Windows"
    import ctypes
    import time
    from ctypes import wintypes

    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    u32.SetClipboardData.restype = wintypes.HANDLE
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalLock.restype = wintypes.LPVOID
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    deadline = time.monotonic() + seconds
    while not u32.OpenClipboard(None):
        if time.monotonic() >= deadline:
            return _busy(f"OpenClipboard failed for {seconds:g} s")
        if pump:
            pump()
        time.sleep(0.02)
    try:
        if not u32.EmptyClipboard():
            return f"EmptyClipboard failed (error {ctypes.GetLastError()})"
        if text is None:
            return ""
        data = (str(text) + "\0").encode("utf-16-le")
        handle = k32.GlobalAlloc(0x0002, len(data))           # GMEM_MOVEABLE
        if not handle:
            return f"GlobalAlloc failed (error {ctypes.GetLastError()})"
        ctypes.memmove(k32.GlobalLock(handle), data, len(data))
        k32.GlobalUnlock(handle)
        if not u32.SetClipboardData(CF_UNICODETEXT, handle):
            k32.GlobalFree(handle)          # still ours: only a success hands it over
            return f"SetClipboardData failed (error {ctypes.GetLastError()})"
        return ""
    finally:
        u32.CloseClipboard()


def clipboard_sequence() -> int:
    """The clipboard's sequence number: every change moves it, whoever makes
    it, and reading never does - so a test that notes it right after its own
    put, or its own copy, knows whether anybody has changed the clipboard
    since. The user's own copy is one: Simple 3D's round 96 saw notepad++.exe
    take the clipboard in the middle of a paste check, twice in 220 runs.
    Measured here (work/clip96/seq_probe.py, session 0 of the 4090): a put
    moves it by 5, Tk's own copy by 10, and another process reading a text
    Tk only promised - Tk rendering it - not at all."""
    if sys.platform != "win32":
        return 0
    import ctypes

    return ctypes.windll.user32.GetClipboardSequenceNumber()


def put_back_clipboard_text(text, ours: int) -> tuple:
    """Put the user's *text* back as put_clipboard_text does - unless the
    clipboard changed since *ours* (clipboard_sequence() right after this
    test's own last change): what is on it then is newer than *text*, most
    likely the user's own copy, and it is left there.

    Returns ("put", ""), ("left", why) or ("failed", why); ClipboardBusy as
    put_clipboard_text raises it."""
    if clipboard_sequence() != ours:
        return "left", "the clipboard changed since this test's own last change"
    why = put_clipboard_text(text)
    return ("failed", why) if why else ("put", "")


def clipboard_open_elsewhere() -> bool:
    """Whether a window of another process has the clipboard open right now.
    OpenClipboard then fails (error 5), and so does Tk's read - "clipboard
    cannot be opened, another application grabbed it" - which an entry's
    <<Paste>> swallows, pasting nothing. Opened with no window, the clipboard
    bars nobody. Measured for Simple 3D, 23.10.2026."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    u32.OpenClipboard.argtypes = [wintypes.HWND]
    if u32.OpenClipboard(None):
        u32.CloseClipboard()
        return False
    return True


_HOLD_OPEN = """\
import ctypes, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u.OpenClipboard.argtypes = [wintypes.HWND]
# A message-only window (parent HWND_MESSAGE), never shown anywhere: opened
# with no window at all, the clipboard bars nobody else from opening it.
hwnd = u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
for _ in range(250):
    if hwnd and u.OpenClipboard(hwnd):
        break
    time.sleep(0.02)
else:
    sys.exit(3)
sys.stdout.write("open\\n")
sys.stdout.flush()
time.sleep(float(sys.argv[1]))
u.CloseClipboard()
"""


_READ_HELD = """\
import ctypes, json, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.CreateWindowExW.restype = wintypes.HWND
u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
u.OpenClipboard.argtypes = [wintypes.HWND]
u.GetClipboardData.restype = wintypes.HANDLE
u.GetClipboardData.argtypes = [wintypes.UINT]
u.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
k.GlobalLock.restype = wintypes.LPVOID
k.GlobalLock.argtypes = [wintypes.HGLOBAL]
k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
fmt = u.RegisterClipboardFormatW(sys.argv[1]) if len(sys.argv) > 1 else 13
hwnd = u.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, wintypes.HWND(-3), None, None, None)
for _ in range(250):
    if hwnd and u.OpenClipboard(hwnd):
        break
    time.sleep(0.02)
else:
    sys.exit(3)
sys.stdout.write("open\\n")
sys.stdout.flush()
sys.stdin.readline()            # "go": the caller pumps no more
h = u.GetClipboardData(fmt)
text = None
if h:
    text = ctypes.wstring_at(k.GlobalLock(h))
    k.GlobalUnlock(h)
u.CloseClipboard()
sys.stdout.write(json.dumps(text))
"""


def read_clipboard_in_background(fmt_name=None, pump=None):
    """Another process that opens the clipboard with a window of its own and,
    told "go" on its stdin, reads the text in the format *fmt_name* (plain
    text for None) - waiting, while that is this process's promise, for this
    process to render it, as rdpclip.exe does with Tk's copy: the Popen once
    the clipboard is open, or None if it never was. Its last line is the
    text, as JSON.

    *pump* runs while the reader opens the clipboard: a reader of another
    program may hold it open meanwhile, sitting on a promise of this
    process's, and gets out only once this process renders it. Waited for
    without pumping, the reader never got in, in 53 stress runs of 100 in
    the owner's session, and the window that held the clipboard was
    rdpclip.exe's (job 11 and work/clip96/pump_probe2.py, 23.10.2026)."""
    if sys.platform != "win32":
        return None
    import subprocess
    import threading

    reader = subprocess.Popen([sys.executable, "-c", _READ_HELD] + ([fmt_name] if fmt_name else []),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    first = []
    waiter = threading.Thread(target=lambda: first.append(reader.stdout.readline()), daemon=True)
    waiter.start()
    while waiter.is_alive():
        if pump is not None:
            pump()
        waiter.join(0.02)
    if not first or first[0].strip() != b"open":
        reader.wait(10)
        return None
    return reader


class ClipboardPromise:
    """Text this thread only promises, in a clipboard format of the test's
    own: a message-only window takes the clipboard and renders the text when
    a reader asks, from this thread's message loop - as a Tk window does with
    its copy, and root.update() runs that loop for every window of the
    thread. `renders` gets the time of each render, so a check can tell a
    reader that waited on the promise from one that found it rendered.

    Tk's own text would not do in the owner's session: rdpclip.exe opens the
    clipboard for it on every change, and the test's reader either never got
    in or found nothing to wait for - of 100 stress runs 53 unjudged and 2
    failed on a reader that read nothing, and the row for the rule survived
    (job 11, 23.10.2026). A format of the test's own nobody else asked for:
    no render before the reader's, and nobody holding the clipboard after
    the promise, in 6 runs of 6 there (work/clip96/pump_probe2.py). `why`
    says why there is no promise, "" when there is one; close() ends it.
    *pump* runs while the clipboard is out of reach, as in
    put_clipboard_text."""

    def __init__(self, text: str, fmt_name: str, pump=None):
        self.text, self.renders, self.why, self.hwnd = text, [], "", None
        if sys.platform != "win32":
            self.why = "not Windows"
            return
        import ctypes
        import os
        import time
        from ctypes import wintypes

        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        lresult = ctypes.c_ssize_t
        proc_type = ctypes.WINFUNCTYPE(lresult, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM)

        class WndClass(ctypes.Structure):
            _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", proc_type),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

        u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        u32.DefWindowProcW.restype = lresult
        u32.RegisterClassW.argtypes = [ctypes.POINTER(WndClass)]
        u32.RegisterClassW.restype = wintypes.ATOM
        u32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        u32.CreateWindowExW.restype = wintypes.HWND
        u32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        u32.DestroyWindow.argtypes = [wintypes.HWND]
        u32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
        u32.OpenClipboard.argtypes = [wintypes.HWND]
        u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        u32.SetClipboardData.restype = wintypes.HANDLE
        k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        k32.GetModuleHandleW.restype = wintypes.HMODULE
        k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        k32.GlobalAlloc.restype = wintypes.HGLOBAL
        k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalLock.restype = wintypes.LPVOID
        k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        k32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        self._u32, fmt = u32, u32.RegisterClipboardFormatW(fmt_name)

        def render(hwnd, msg, wparam, lparam):
            if msg == 0x0305 and wparam == fmt:              # WM_RENDERFORMAT
                self.renders.append(time.monotonic())
                data = (self.text + "\0").encode("utf-16-le")
                handle = k32.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
                if not handle:
                    self.why = f"GlobalAlloc failed at the render (error {ctypes.GetLastError()})"
                    return 0
                ctypes.memmove(k32.GlobalLock(handle), data, len(data))
                k32.GlobalUnlock(handle)
                if not u32.SetClipboardData(fmt, handle):
                    self.why = f"SetClipboardData failed at the render (error {ctypes.GetLastError()})"
                    k32.GlobalFree(handle)
                return 0
            return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc = proc_type(render)       # kept alive: Windows calls it while the window lives
        self._hinst = k32.GetModuleHandleW(None)
        self._class = f"step2html-test-promise-{os.getpid()}-{id(self)}"
        if not u32.RegisterClassW(ctypes.byref(WndClass(lpfnWndProc=self._proc, hInstance=self._hinst,
                                                        lpszClassName=self._class))):
            self.why = f"RegisterClassW failed (error {ctypes.GetLastError()})"
            return
        self.hwnd = u32.CreateWindowExW(0, self._class, None, 0, 0, 0, 0, 0, wintypes.HWND(-3),
                                        None, self._hinst, None)
        if not self.hwnd:
            self.why = f"CreateWindowExW failed (error {ctypes.GetLastError()})"
            return
        deadline = time.monotonic() + 10
        while not u32.OpenClipboard(self.hwnd):
            if time.monotonic() >= deadline:
                self.why = "OpenClipboard failed for 10 s"
                return
            if pump is not None:
                pump()
            time.sleep(0.02)
        try:
            if not u32.EmptyClipboard():                     # this window is the owner now
                self.why = f"EmptyClipboard failed (error {ctypes.GetLastError()})"
            else:
                u32.SetClipboardData(fmt, None)              # NULL: rendered when asked
        finally:
            u32.CloseClipboard()

    def close(self) -> None:
        if self.hwnd:
            self._u32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if getattr(self, "_class", None):
            self._u32.UnregisterClassW(self._class, self._hinst)
            self._class = None


def hold_clipboard_open(seconds: float):
    """Another process that opens the clipboard with a window of its own and
    holds it *seconds*, as a program that reads it on every change does for
    a moment (rdpclip.exe does, in an RDP session): the Popen once the
    clipboard is open, or None if it never was. Wait for it to end."""
    if sys.platform != "win32":
        return None
    import subprocess

    holder = subprocess.Popen([sys.executable, "-c", _HOLD_OPEN, str(seconds)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if holder.stdout.readline().strip() != b"open":
        holder.wait(10)
        return None
    return holder


_CLIP_PROBE = """\
import ctypes, json, sys, time
from ctypes import wintypes
u = ctypes.windll.user32
k = ctypes.windll.kernel32
u.OpenClipboard.argtypes = [wintypes.HWND]
u.GetClipboardData.restype = wintypes.HANDLE
u.GetClipboardData.argtypes = [wintypes.UINT]
k.GlobalLock.restype = wintypes.LPVOID
k.GlobalLock.argtypes = [wintypes.HGLOBAL]
k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
deadline = time.monotonic() + float(sys.argv[1])
while not u.OpenClipboard(None):
    if time.monotonic() >= deadline:
        sys.exit(3)
    time.sleep(0.02)
try:
    h = u.GetClipboardData(13)
    text = None
    if h:
        text = ctypes.wstring_at(k.GlobalLock(h))
        k.GlobalUnlock(h)
finally:
    u.CloseClipboard()
sys.stdout.write(json.dumps(text))
"""


def clipboard_text_elsewhere(seconds: float = 10.0) -> tuple:
    """What ANOTHER process reads from the clipboard while this one waits for
    it and pumps no messages: (text, "") - text None when there is none - or
    (None, why) when it could not; ClipboardBusy when another program kept
    the clipboard open for half of *seconds* (_busy).

    Text this process only promised (Tk's clipboard_append) cannot be read
    this way: the reader waits for this process's event loop, which is
    blocked right here, until Windows gives up after 30 s - so *seconds*
    under 30 makes the promise a failure instead of a long wait. The probe
    opens the clipboard within the first half of *seconds*, so an open it
    never gets (busy) and a read it never finishes (a promise) come apart."""
    if sys.platform != "win32":
        return None, "not Windows"
    import json
    import subprocess

    try:
        done = subprocess.run([sys.executable, "-c", _CLIP_PROBE, str(seconds / 2)],
                              capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:
        return None, f"another process could not read the clipboard within {seconds:g} s"
    if done.returncode == 3:
        return None, _busy(f"another process could not open the clipboard for {seconds / 2:g} s")
    if done.returncode:
        return None, f"the clipboard probe failed with exit code {done.returncode}"
    return json.loads(done.stdout.decode("utf-8") or "null"), ""
