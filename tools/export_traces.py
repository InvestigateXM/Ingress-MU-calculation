"""Export the data files for site/how-it-works.html.

Every number shown by the animation page is computed here by the shipped
calculator (mu_calculator) for a fixed set of example fields and written to
site/traces/a1.json .. a5.json. The page itself only draws these files.

Usage (Linux; needs the population rasters, see README):

    GRUMP_DIR=/path/to/grump/bil python tools/export_traces.py [--out site/traces] [--check]

--check recomputes everything and compares it with the files in --out instead
of writing them. The export fails if an example no longer gives its expected MU.
The output is deterministic.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib  # noqa: E402

from anim.common import DATA, Calc, RecordingCalc, ReplayCalc, ROOT  # noqa: E402


# ---------------------------------------------------------------- main

# One module per trace in tools/anim/, each with build(calc) -> trace dict. Order = page order.
NAMES = ["a0", "a2", "a5g", "a5", "a6", "a3", "a4", "a1g", "a1"]
BUILDERS = [(n, lambda calc, n=n: importlib.import_module(f"anim.{n}").build(calc)) for n in NAMES]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "site" / "traces"))
    ap.add_argument("--check", action="store_true", help="compare with the existing files instead of writing")
    ap.add_argument("only", nargs="*", help="trace ids (default: all)")
    ap.add_argument("--data", default=str(DATA), help="recorded densities and pixels (used when GRUMP_DIR is not set)")
    ap.add_argument("--record", action="store_true", help="with GRUMP_DIR: also rewrite the recorded data file")
    args = ap.parse_args()
    out = Path(args.out)
    if os.environ.get("GRUMP_DIR"):
        calc = RecordingCalc() if args.record else Calc()
    else:
        calc = ReplayCalc(args.data)
    bad = 0
    for name, fn in BUILDERS:
        if args.only and name not in args.only:
            continue
        text = json.dumps(fn(calc), ensure_ascii=False, separators=(",", ":")) + "\n"
        path = out / f"{name}.json"
        if args.check:
            same = path.is_file() and path.read_text(encoding="utf-8") == text
            print(f"{name}: {'unchanged' if same else 'DIFFERS'}")
            bad += not same
        else:
            out.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"{name}: {len(text.encode('utf-8')) / 1024:.1f} KB")
    if isinstance(calc, RecordingCalc):
        calc.write(args.data)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
