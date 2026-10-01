"""Grid sweep for the windfall cap (windfall_pct x windfall_reserve), peer panel.

The cap is the tail fix from analysis/autopsy.py: the day-11 melon windfall used to plant the
whole board against $0 of working cash, the wage bill then starved the roster, and 70 tiles
died of thirst. This grid finds the peak of the two axes that price the board's upkeep into
the planting decision.

Runs against `self` (the shipped policy in seat 1, pinned to on-disk PARAMS), because that is
the regime the tail lives in. 96 seeds per cell -- a single 48-block cannot separate cells
that differ by less than ~$1k.

    python3 analysis/windfall_grid.py
"""

from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate  # noqa: E402
from kagfarm.policy import PARAMS_BASE  # noqa: E402


def cell(pct, res, seeds):
    over = dict(PARAMS_BASE)
    over["windfall_pct"] = pct
    over["windfall_reserve"] = res
    rows = evaluate(seeds, ["self"], quiet=True, params=over)
    banks = sorted(r["bank"] for r in rows)
    n = len(banks)
    wins = sum(1 for r in rows if r["bank"] > r["opp_bank"])
    return dict(mean=sum(banks) / n, p10=banks[max(0, int(0.1 * n) - 1)],
                min=banks[0], wins=wins, n=n)


def main_cli():
    t0 = time.monotonic()
    seeds = range(96)
    pcts = (0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0)
    ress = (0, 2, 4)
    print("windfall grid, seeds 0-95 vs self (shipped policy as opponent)")
    print("%-6s %-4s %9s %9s %9s %6s" % ("pct", "res", "mean", "p10", "min", "wins"))
    best = None
    for pct in pcts:
        for res in ress:
            m = cell(pct, res, seeds)
            print("%-6.2f %-4d %9.0f %9.0f %9.0f %6d" %
                  (pct, res, m["mean"], m["p10"], m["min"], m["wins"]))
            # objective: mean first, p10 as tiebreak -- a ladder rating is won per episode,
            # but the mean already tracks wins here (they moved together on every block).
            key = (round(m["mean"] / 500), m["p10"])
            if best is None or key > best[0]:
                best = (key, pct, res, m)
    print("\nbest: pct=%.2f reserve=%d  mean $%.0f  p10 $%.0f  (%.0fs)"
          % (best[1], best[2], best[3]["mean"], best[3]["p10"], time.monotonic() - t0))


if __name__ == "__main__":
    main_cli()
