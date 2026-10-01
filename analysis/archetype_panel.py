"""Robustness panel: the constants must not depend on the opponent being a mirror.

Every adoption gate this project has run scored either `self_live` (a mirror) or the
built-in punchbags. The real ladder field is neither. This panel runs a cell against
four synthetic archetypes — the same Policy with one drive distorted (see agents.py) —
plus the mirror, and reports per-opponent mean/p10/min/win-rate. A cell that only wins
against itself shows up here as a sign flip on one archetype.

    python3 analysis/archetype_panel.py                     # incumbent vs archetypes
    python3 analysis/archetype_panel.py --cells windfall_pct=0.30 windfall_pct=0.55

The question each archetype answers:
    arch_passive  does the melon opening still fund itself with nobody contesting it?
    arch_hoarder  do our prices survive a supply shock from a peer that stockspile-sells?
    arch_flooder  does our sell-timing hold when someone else gluts the melon book?
    arch_snapper  does a maximal-cash-retention land-racer punish our day-11 spend?
"""

from __future__ import annotations

import argparse
import ast
import sys
import os
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate  # noqa: E402

ARCHETYPES = ["arch_passive", "arch_hoarder", "arch_flooder", "arch_snapper", "self_live"]


def _parse_set(spec: str) -> dict:
    """--set windfall_pct=0.30 -> {"windfall_pct": 0.30} (values parsed as python literals)."""
    k, _, v = spec.partition("=")
    try:
        v = ast.literal_eval(v)
    except (ValueError, SyntaxError):
        pass
    return {k.strip(): v}


def _fmt(rows, label):
    banks = sorted(r["bank"] for r in rows)
    wins = sum(1 for r in rows if r["bank"] > r["opp_bank"])
    n = len(rows)
    mean = sum(banks) / n
    p10 = banks[max(0, int(0.10 * n) - 1)]
    return (f"  {label:<14} n={n:>3}  mean ${mean:>9,.0f}  p10 ${p10:>8,.0f}  "
            f"min ${banks[0]:>8,.0f}  win {wins}/{n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="48", help="number of seeds starting at 0")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cells", nargs="*", default=[],
                    help="extra cells as --set specs, e.g. windfall_pct=0.30")
    args = ap.parse_args()

    seeds = list(range(int(args.seeds)))
    cells = [("incumbent", None)] + [(spec, _parse_set(spec)) for spec in args.cells]

    for label, params in cells:
        print(f"== {label}")
        by_opp = defaultdict(list)
        rows = evaluate(seeds, ARCHETYPES, quiet=True, params=params,
                        workers=args.workers)
        for r in rows:
            by_opp[r["opp"]].append(r)
        for opp in ARCHETYPES:
            if by_opp[opp]:
                print(_fmt(by_opp[opp], opp))


if __name__ == "__main__":
    main()
