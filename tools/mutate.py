"""Mutation audit: break the code a test claims to protect, run the test, see.

    python tools/mutate.py                       # every row of tests/mutations.json
    python tools/mutate.py --changed             # only what the uncommitted changes touch
    python tools/mutate.py --changed HEAD~3      # ...since some other revision
    python tools/mutate.py budget-target edges-  # rows whose id contains a piece
    python tools/mutate.py --list --changed      # show the selection, run nothing
    python tools/mutate.py --spec work/rows.json # a table kept somewhere else

Each mutation is {id, file, old, new, suites, why}: `file` and every suite are
paths from the repository root.  `old` must occur exactly once in the file, or
the mutation is refused (an unasserted replacement proves nothing).  A suite is
CAUGHT when its exit code is non-zero with the mutation in place; a mutation is
caught when any of its suites catches it.

Nothing here ever writes into the working tree.  Every worker owns a private
COPY of it under work/mutants/run-<time>-<pid>/w<i>/ and breaks that; the
copies run in parallel; the mutated file is restored from the bytes read before
the write and the restore is proved by SHA-256.  A killed run leaves a folder
under work/ and nothing else.

Why copies (2026-09-21, BaroSim, 212 mutations): the in-place design needed a
lock file, a leftover check, a bytecode purge and a rule that nobody edits
while it runs, and still cost four accidents in one week - two hours of edits
silently reverted by a background run, an `if False:` left behind by a killed
run, an hour lost to a stale .pyc of the same length, a mutated line that
failed five tests.  On copies the full table went from 26.6 min in place to
6.5-6.8 min on 4-8 copies, and two mutations that had counted as "caught"
turned out to survive: one lived in a branch dead behind a flag, one was caught
only by the developer's gitignored settings file.  A copy has only what is
under version control plus what you deliberately give it - that is the point.

This file is the shared harness of the test-audit skill
(~/.claude/skills/test-audit/mutate.py) with three lines of its own: the
default table is tests/mutations.json, the default root is this repository,
and neither input/ - 69 MB of the user's boards, which no suite reads - nor
the window's own settings file travels into a copy.  The cheap sentinel that
proves this job is still asking its questions is tests/test_mutations.py.

----------------------------------------------------------------------------
Traps this harness handles, each of which has cost a real run:

1. CRLF.  Read and write BYTES; translate the pattern to the file's own ending.
   In text mode every multi-line pattern matches zero times and the run
   reports "refused" instead of an answer.
2. STALE BYTECODE.  Python validates a .pyc from the source's (mtime, size), so
   a same-length replacement written in the same second is invisible to it -
   or the mutated bytecode outlives the restore.  A copy is made without any
   __pycache__ and the children run with -B, so there is nothing to go stale.
3. A REPLACEMENT THAT DOES NOT REMOVE THE ORIGINAL (an early `return` shadowing
   the line).  Still refused: `old` staying in the file makes the check of the
   restore meaningless and the mutation ambiguous.
4. A MUTATION LEFT IN THE WORKING TREE by some other tool or a hand edit: the
   copies would inherit it and the baseline would go red for a reason that is
   not the suite's.  Checked once at start - the replacement present AND the
   original absent; the replacement alone is usually a substring of the
   healthy line.
5. CONSOLE ENCODING.  PYTHONUTF8=1 and PYTHONIOENCODING=utf-8 for the child, or
   one non-ASCII FAIL line kills it on a cp1251 console.
6. A REFUSED MUTATION IS NOT A PASS: the pattern stopped matching because the
   file was refactored, and the rule has had no proof since.  Counted as
   unproven and named at the end.
----------------------------------------------------------------------------
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tests" / "mutations.json"
PY = sys.executable
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
           PYTHONIOENCODING="utf-8")
# What never travels into a copy.  Add a project's heavy inputs with --exclude.
# The window's own settings file stays out too: a copy has only what is
# under version control, so a check that passes only thanks to what the
# developer's window remembered fails here, where it should.
IGNORE = ("__pycache__", "*.pyc", ".git", "work", "build", "dist",
          ".pytest_cache", "node_modules", ".venv", "venv",
          "input", "*.egg-info", "step2html_config.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_source(path: Path) -> tuple:
    """The file as text with newlines normalised, and whether it had CRLF."""
    data = path.read_bytes()
    return data.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in data, data


def copy_tree(root: Path, dst: Path, exclude: tuple = ()) -> int:
    """Copy `root` into `dst` minus IGNORE and `exclude`; the number of files.

    copytree copies with copy2, so mtimes survive: anything a suite builds
    afterwards (a DLL, a cache) is newer than every source.
    """
    ignore = shutil.ignore_patterns(*IGNORE, *exclude)
    shutil.copytree(root, dst, ignore=ignore, symlinks=True)
    return sum(1 for p in dst.rglob("*") if p.is_file())


def run_suite(copy: Path, suite: str) -> tuple:
    """(exit code, seconds, output) of one suite run inside `copy`."""
    script = copy / suite
    if not script.exists():
        return 2, 0.0, f"no such suite: {suite}"
    started = time.monotonic()
    done = subprocess.run([PY, "-B", str(script)], capture_output=True, text=True,
                          cwd=str(copy), env=ENV, encoding="utf-8", errors="replace")
    return done.returncode, time.monotonic() - started, (done.stdout or "") + (done.stderr or "")


def left_behind(root: Path, spec: list) -> list:
    """Mutations that look applied in the WORKING tree (trap 4)."""
    dirty = []
    for m in spec:
        path = root / m["file"]
        if not path.exists():
            continue
        text, _crlf, _data = read_source(path)
        if m["new"] in text and m["old"] not in text:
            dirty.append(f"{m['file']}: {m['id']} looks applied")
    return dirty


def mutate_once(copy: Path, m: dict, base: dict) -> tuple:
    """Apply `m` in `copy`, run its suites there, put the file back.

    Returns (verdict, id, seconds, detail); verdict is "caught", "SURVIVED"
    or "REFUSED".  Raises RuntimeError if the restore did not reproduce the
    original bytes - the copy is then unfit for further jobs.
    """
    path = copy / m["file"]
    if not path.exists():
        return "REFUSED", m["id"], 0.0, f"no such file: {m['file']}"
    text, crlf, original = read_source(path)
    digest = sha(original)
    hits = text.count(m["old"])
    if hits != 1:
        return "REFUSED", m["id"], 0.0, f"`old` occurs {hits} times in {m['file']}"
    mutated = text.replace(m["old"], m["new"])
    if crlf:
        mutated = mutated.replace("\n", "\r\n")
    spent, caught, fails = 0.0, [], ""
    try:
        path.write_bytes(mutated.encode("utf-8"))
        for suite in m["suites"]:
            if base.get(suite):
                continue                         # already red on the clean tree
            code, seconds, out = run_suite(copy, suite)
            spent += seconds
            if code:
                caught.append(suite)
                lines = [l.strip() for l in out.splitlines() if "FAIL" in l]
                fails = lines[0][:90] if lines else f"exit {code}"
                break                            # one suite is enough
    finally:
        path.write_bytes(original)
        # A file compiled into something the suites load (a C source into a
        # host DLL) may have been built from the mutant: drop what the copy
        # built under work/ so the next job rebuilds it.
        if path.suffix in (".c", ".h", ".cpp", ".ld"):
            shutil.rmtree(copy / "work", ignore_errors=True)
    if sha(path.read_bytes()) != digest:
        raise RuntimeError(f"{m['file']} was not restored in {copy}")
    if caught:
        return "caught", m["id"], spent, f"{caught[0]}: {fails}"
    return "SURVIVED", m["id"], spent, "green in " + ", ".join(m["suites"])


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{done.stderr.strip()}")
    return done.stdout


def changed_paths(root: Path, rev: str) -> set:
    edited = git(root, "diff", "--name-only", rev).splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return {p.strip() for p in edited + untracked if p.strip()}


def spec_at(root: Path, spec_path: Path, rev: str) -> list:
    """The spec as committed at `rev`, or [] when it is not in the repository."""
    try:
        rel = spec_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return []
    done = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{rel}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if done.returncode != 0:
        return []
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return []


def select_changed(spec: list, changed: set, previous: list) -> list:
    """Rows whose file or any suite changed, or which are new/edited since REV."""
    before = {json.dumps(m, sort_keys=True) for m in previous}
    return [m for m in spec
            if m["file"] in changed or any(s in changed for s in m["suites"])
            or json.dumps(m, sort_keys=True) not in before]


def select(spec: list, pieces: list) -> list:
    """Rows whose id contains any of `pieces`; every row when there are none."""
    return [m for m in spec if not pieces or any(p in m["id"] for p in pieces)]


def parse(argv: list) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("ids", nargs="*", help="only rows whose id contains one of these (default: all)")
    p.add_argument("--spec", default=str(SPEC),
                   help="JSON list of {id, file, old, new, suites, why} (default %(default)s)")
    p.add_argument("--root", default=str(ROOT), help="the project (default: this repository)")
    p.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) // 2),
                   help="copies running at once (default %(default)s: half the logical "
                        "cores; on 4 physical cores 8 copies were 5%% faster than 4 and "
                        "left the machine unusable)")
    p.add_argument("--exclude", action="append", default=[], metavar="PAT",
                   help="glob of names never copied (repeatable), e.g. research or *.pdf")
    p.add_argument("--changed", nargs="?", const="HEAD", metavar="REV",
                   help="only rows whose file, suite or spec entry differ from REV "
                        "(default HEAD)")
    p.add_argument("--list", action="store_true", help="print the selection, run nothing")
    p.add_argument("--keep", action="store_true", help="leave the copies behind")
    p.add_argument("--no-baseline", action="store_true")
    return p.parse_args(argv)


def main(argv: list) -> int:
    args = parse(argv)
    root = Path(args.root).resolve()
    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    muts = select(spec, args.ids)
    if args.changed is not None:
        changed = changed_paths(root, args.changed)
        muts = select_changed(muts, changed, spec_at(root, spec_path, args.changed))
        print(f"{len(changed)} paths differ from {args.changed}; {len(muts)} of "
              f"{len(spec)} mutations touch them or are new")
    if not muts:
        print("no mutation matches")
        return 0 if args.changed is not None else 2
    if args.list:
        for m in muts:
            print(f"  {m['id']:<40} {m['file']:<36} {', '.join(m['suites'])}")
        return 0

    invisible = [m["id"] for m in muts if m["old"] in m["new"]]
    if invisible:
        print("REFUSED - the replacement keeps the original text (trap 3):", *invisible)
        return 2
    dirty = left_behind(root, spec)
    if dirty:
        print("the working tree carries a mutation, and every copy would inherit it:")
        for line in dirty:
            print("   ", line)
        return 3

    workers = max(1, min(args.workers, len(muts)))
    run_dir = root / "work" / "mutants" / f"run-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"
    copies = [run_dir / f"w{i}" for i in range(workers)]
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as copier:
        files = sum(copier.map(lambda c: copy_tree(root, c, tuple(args.exclude)), copies))
    print(f"root: {root}\n{workers} copies under {run_dir}, {files} files, "
          f"{time.monotonic() - started:.1f} s; the working tree is not touched")

    free: queue.Queue = queue.Queue()
    for c in copies:
        free.put(c)

    def with_copy(job, *rest):
        copy = free.get()
        try:
            return job(copy, *rest)
        except RuntimeError:
            shutil.rmtree(copy, ignore_errors=True)   # unfit: a fresh copy instead
            copy_tree(root, copy, tuple(args.exclude))
            raise
        finally:
            free.put(copy)

    suites = sorted({s for m in muts for s in m["suites"]})
    base = {s: 0 for s in suites}
    times = {s: 0.0 for s in suites}
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        if args.no_baseline:
            print("=== baseline skipped by request ===")
        else:
            print("=== baseline (clean copies) ===")
            for suite, (code, seconds, _out) in zip(suites, pool.map(
                    lambda s: with_copy(run_suite, s), suites)):
                base[suite], times[suite] = code, seconds
                print(f"  {suite:<40} exit={code}  {seconds:5.1f}s"
                      + ("   <-- ALREADY RED" if code else ""))
        # Longest suites first, so the tail is not one slow suite started last.
        jobs = sorted(muts, key=lambda m: -max(times.get(s, 0.0) for s in m["suites"]))
        futures = [pool.submit(with_copy, mutate_once, m, base) for m in jobs]
        try:
            for future in concurrent.futures.as_completed(futures):
                verdict, mid, spent, detail = future.result()
                results.append((verdict, mid, spent, detail))
                print(f"  {verdict:<8} {mid:<40} {spent:5.1f}s  {detail}")
        except RuntimeError as exc:
            print(f"ERROR {exc}")
            return 3

    if not args.keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    wall = time.monotonic() - started
    work = sum(r[2] for r in results) + sum(times.values())
    caught = [r for r in results if r[0] == "caught"]
    print(f"\ncaught {len(caught)} of {len(results)}; {wall:.0f} s of wall for "
          f"{work:.0f} s of suite runs on {workers} copies")
    unproven = [r for r in results if r[0] != "caught"]
    if unproven:
        print("not proved (a REFUSED mutation is a rule with no evidence, not a pass):")
        for verdict, mid, _spent, detail in unproven:
            print(f"  {verdict:<8} {mid}: {detail}")
    return 1 if unproven else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
