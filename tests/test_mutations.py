"""The mutation table is still aimed at the code: every pattern in
tests/mutations.json matches its file exactly once, at HEAD, today.

`python tools/mutate.py` is the expensive job: it breaks the code the way
each row says, in a private copy of the tree, runs the suites the row names
and reports which mutations were caught. It is not in run_all - it costs
minutes, not seconds. What IS cheap is asking whether that job is still
asking its questions at all, and it stops asking one the moment the file it
targets is refactored and the `old` text is gone: the harness prints REFUSED
and moves on, and the rule that row stood for has had no evidence since the
refactor. A refusal is not a pass.

So this suite applies nothing and runs no mutant. Per row it checks what the
harness would check before applying it - the file exists, `old` occurs
exactly once, `new` differs and does not contain `old` (an early `return`
shadowing the line leaves the original in place), the suites it names exist,
the id is unique - and then two things about the harness itself: that a copy
made the way a worker makes one carries every file a row names, byte for
byte, and no bytecode; and that `--changed` picks rows by the file, the suite
and the row, nothing else. It fails in the same round as the refactor that
broke the pattern.
"""
from __future__ import annotations

import json
import shutil
import sys

from harness import ROOT, check, run

sys.path.insert(0, str(ROOT / "tools"))
import mutate                                          # noqa: E402

TABLE = ROOT / "tests" / "mutations.json"
# Just under the table's size when this was last raised: half the rows could
# not vanish and still pass. The number only ever grows.
MIN_ROWS = 150
FIELDS = ("id", "file", "old", "new", "suites", "why")


def main():
    print("[1] the table itself")
    check(TABLE.is_file(), "tests/mutations.json exists")
    if not TABLE.is_file():
        return
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    check(isinstance(table, list) and all(isinstance(m, dict) for m in table),
          "it is a list of rows")
    check(len(table) >= MIN_ROWS, f"it holds at least {MIN_ROWS} rows", str(len(table)))
    ids = [m.get("id") for m in table]
    check(len(ids) == len(set(ids)), "every id is unique",
          ", ".join(sorted({i for i in ids if ids.count(i) > 1})))
    short = [m.get("id", "?") for m in table
             if any(k not in m for k in FIELDS) or not str(m.get("why", "")).strip()]
    check(not short, "every row has every field, and says why", ", ".join(short))

    print("[2] every pattern still matches exactly once, and would apply")
    sources: dict = {}
    for m in table:
        mid = m.get("id", "?")
        path = ROOT / m.get("file", "")
        exists = path.is_file()
        check(exists, f"{mid}: {m.get('file')} exists")
        if not exists:
            continue
        if path not in sources:
            # Normalised the way the harness reads it, so a CRLF file and an
            # LF pattern count the same here as there.
            sources[path] = mutate.read_source(path)[0]
        text = sources[path]
        old, new = m["old"], m["new"]
        n = text.count(old)
        check(n == 1, f"{mid}: old occurs exactly once in {m['file']}", f"{n} times")
        check(new != old and old not in new,
              f"{mid}: new differs from old and removes it")
        check(not (new in text and old not in text),
              f"{mid}: new is not already in the file (a leftover of a killed run)")
    check(not mutate.left_behind(ROOT, table),
          "and the harness's own leftover check agrees the tree is clean")

    print("[3] every suite a row names exists")
    named = sorted({s for m in table for s in m.get("suites", [])})
    check(bool(named), "at least one suite is named")
    for s in named:
        check((ROOT / s).is_file(), f"suite {s} exists")
    covered = sorted({m["file"].split("/")[0] + ("/viewer" if "/viewer/" in m["file"] else "")
                      for m in table if "file" in m})
    check("step2html" in covered and "step2html/viewer" in covered,
          "the table reaches both the pipeline and the viewer", ", ".join(covered))

    print("[4] the copy a worker mutates is the tree, minus what can go stale")
    copy = ROOT / "work" / "sentinel-copy"
    shutil.rmtree(copy, ignore_errors=True)
    copied = mutate.copy_tree(ROOT, copy)
    check(copied > 50, "the copy has files at all", str(copied))
    wanted = sorted({m["file"] for m in table} | set(named))
    missing = [rel for rel in wanted if not (copy / rel).is_file()]
    check(not missing, "every file and every suite a row names is in the copy",
          ", ".join(missing[:5]))
    differ = [rel for rel in sorted({m["file"] for m in table})
              if (copy / rel).is_file()
              and (copy / rel).read_bytes() != (ROOT / rel).read_bytes()]
    check(not differ, "and each file a row breaks is byte for byte the tree's",
          ", ".join(differ[:5]))
    stale = [str(p.relative_to(copy)) for p in copy.rglob("*")
             if p.name == "__pycache__" or p.suffix == ".pyc"]
    check(not stale, "no bytecode travels with it", ", ".join(stale[:5]))
    heavy = [name for name in (".git", "work", "build", "dist", "input",
                               "step2html_config.json")
             if (copy / name).exists()]
    check(not heavy, "neither .git, work/, build/, dist/, input/ nor the "
          "window's settings file does",
          ", ".join(heavy))
    for rel in ("tests/harness.py", "tests/fixtures.py", "tests/golden.json",
                "step2html/viewer/viewer.html", "tests/viewer.test.js"):
        check((copy / rel).is_file(), f"what the suites read is there: {rel}")
    shutil.rmtree(copy, ignore_errors=True)

    print("[5] --changed picks what a change can have left unproved, nothing else")
    rows = [{"id": "a-rule", "file": "step2html/a.py", "old": "x = 1", "new": "x = 2",
             "suites": ["tests/test_a.py"], "why": "a"},
            {"id": "b-rule", "file": "step2html/b.py", "old": "y = 1", "new": "y = 2",
             "suites": ["tests/test_b.py"], "why": "b"},
            {"id": "c-rule", "file": "step2html/c.py", "old": "z = 1", "new": "z = 2",
             "suites": ["tests/test_c.py"], "why": "c"}]

    def picked(changed, previous):
        return [m["id"] for m in mutate.select_changed(rows, changed, previous)]

    check(picked(set(), rows) == [], "nothing changed, nothing selected")
    check(picked({"step2html/a.py"}, rows) == ["a-rule"],
          "the file a row breaks changed: it runs")
    check(picked({"tests/test_b.py"}, rows) == ["b-rule"],
          "the suite that must catch it changed: the claim moved, so it runs too")
    check(picked({"README.md", "step2html/gui/app.py"}, rows) == [],
          "an unrelated file changed: nothing runs")
    edited = [rows[0], dict(rows[1], new="y = 3")]
    check(picked(set(), edited) == ["b-rule", "c-rule"],
          "a row that is new or edited since the revision runs")
    check(len(mutate.select_changed(rows, set(), [])) == 3,
          "with no previous table at all, everything runs")
    check([m["id"] for m in mutate.select(rows, ["b-", "c-"])] == ["b-rule", "c-rule"]
          and len(mutate.select(rows, [])) == 3,
          "ids select by substring, any piece, and none means all")
    changed = mutate.changed_paths(ROOT, "HEAD")
    check(all("\\" not in p for p in changed),
          "git answers with repository paths, forward slashes",
          ", ".join(sorted(changed)[:3]))
    check(isinstance(mutate.spec_at(ROOT, TABLE, "HEAD"), list),
          "and the table as committed reads back as a list (empty before its first commit)")


if __name__ == "__main__":
    sys.exit(run(main, "the mutation table"))
