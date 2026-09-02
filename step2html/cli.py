"""The command line: a thin argparse over convert().

    step2html board.step
    python -m step2html board.step -o board.html --title "Board A0"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ConvertError
from .convert import Options, convert
from .meta import tool_version


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Turn a STEP assembly into one self-contained interactive "
                    "HTML file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  step2html "d:/my board/cad/board.step"
      -> writes d:/my board/cad/board.html beside it

  step2html board.step -o "//server/share/board A0.html" \\
         --title "Board A0, rev 3" --read-only

  step2html board.step --max-bytes none
      -> one build at the automatic mesh, instead of searching for the finest
         mesh that still fits inside the size of the STEP

  step2html-gui, or python -m step2html.gui
      -> the same thing with a window around it
""")
    # A tool that stamps its version into every file it makes should be able
    # to say it out loud as well.
    ap.add_argument("--version", action="version",
                    version=f"step2html {tool_version()}")
    ap.add_argument("step", type=Path, help="the STEP file to convert")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="output .html (default: beside the STEP, same name)")
    ap.add_argument("--title", default=None,
                    help="heading shown on the page (default: the file name)")
    ap.add_argument("--deflection", default="auto", metavar="MM",
                    help="linear mesh deflection in mm, or 'auto' (the default) "
                         "to scale it to the size of the model")
    ap.add_argument("--angle", type=float, default=15.0, metavar="DEG",
                    help="angular mesh deflection in degrees (default 15)")
    ap.add_argument("--max-bytes", default="auto", metavar="N",
                    help="size budget for the .html: 'auto' (the default) means "
                         "the size of the STEP itself, 'none' lifts it. The mesh "
                         "is refined as far as the budget allows.")
    ap.add_argument("--no-repair", action="store_true",
                    help="do not try to rescue faces the mesher leaves empty")
    ap.add_argument("--read-only", action="store_true",
                    help="set the read-only attribute on the result, so Notepad "
                         "and friends refuse to save over it")
    args = ap.parse_args(argv)

    opts = Options(
        step=str(args.step),
        out=str(args.out) if args.out else "",
        title=args.title or "",
        deflection=str(args.deflection),
        angle=args.angle,
        max_bytes=str(args.max_bytes),
        repair=not args.no_repair,
        read_only=args.read_only,
    )
    try:
        report = convert(opts, log=print)
    except ConvertError as exc:
        raise SystemExit(str(exc))

    source = Path(opts.step).stat().st_size
    share = f" ({100.0 * report.size / source:.0f}% of the STEP)" if source else ""
    print(f"{report.out}: {report.size:,} bytes HTML{share}"
          f"{' (read-only)' if opts.read_only else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
