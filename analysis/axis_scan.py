"""Scan one `PARAMS` axis on a large panel and print every metric, not just the mean.

This is the instrument the sweep's own lesson demands. `sweep.py` walks fifteen axes on a small
panel and the winner it reports is partly fitted to that panel -- a 15-axis descent on 32 episodes
once claimed +$4,785 of mean and delivered -$400 on unseen seeds. The response is not to distrust
tuning; it is to change one thing at a time on a panel big enough to resolve it. On 144 episodes
the standard error on the mean is about $1k, so a single-axis move under roughly $500 is a coin
flip and the incumbent should keep the seat.

It prints the mechanism columns as well as the score, because a parameter that buys acreage by
killing plants shows up as a flat mean and a doubled `thirst`, and that is the difference between
a change that holds up against a stronger opponent and one that does not.

    python3 analysis/axis_scan.py max_hands 8,10,12,14,16
    python3 analysis/axis_scan.py labour_slack 1.0,1.2,1.5 --seeds 24 --opps starter,heuristic
"""

from __future__ import annotations

import argparse
import ast
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from eval import evaluate
from kagfarm.policy import PARAMS


def stats(rows):
    banks = sorted(r["bank"] for r in rows)
    n = len(banks)
    return dict(
        n=n, mean=sum(banks) / n, p10=banks[max(0, int(0.1 * n) - 1)], min=banks[0],
        wins=sum(1 for r in rows if r["bank"] > r["opp_bank"]),
        tiles=sum(r["tiles_per_day"] for r in rows) / n,
        thirst=sum(r["thirst"] for r in rows) / n,
        lost=sum(r["lost"] for r in rows) / n,
        idle=100.0 * sum(r["idle_frac"] for r in rows) / n,
        px=100.0 * sum(r["px_all"] for r in rows) / n,
        worst=max(r["worst_ms"] for r in rows),
        bad=sum(1 for r in rows if r["err"] or r["over_budget"]),
    )


def label(val):
    """A column-width name for a parameter value. Dicts get initials: 'M24 S33 W9 C3'."""
    if isinstance(val, dict):
        return " ".join("%s%g" % (k[0], v) for k, v in sorted(val.items(), key=lambda kv: -kv[1]))
    return str(val)


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("axis")
    ap.add_argument("values", help="comma-separated python literals; dicts and tuples are fine")
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--seed0", type=int, default=0,
                    help="first seed; use a disjoint range to re-score a winner on unseen seeds")
    ap.add_argument("--opps", default="starter,heuristic,random")
    ap.add_argument("--workers", type=int, default=0)
    a = ap.parse_args()

    if a.axis not in PARAMS:
        sys.exit("axis_scan: %r is not in PARAMS" % a.axis)
    # Parsed as one bracketed list rather than split on commas, because the interesting axes are
    # not scalars: `mix` is a dict and `always_sell` a tuple, and splitting on "," cuts them in
    # half. Wrapping is safe for the scalar case too -- "8,10,12" becomes [8, 10, 12].
    vals = ast.literal_eval("[" + a.values + "]")
    opps = a.opps.split(",")
    incumbent = PARAMS[a.axis]

    print("%s: incumbent %r, seeds %d-%d x %s = %d episodes per cell\n"
          % (a.axis, incumbent, a.seed0, a.seed0 + a.seeds - 1, ",".join(opps),
             a.seeds * len(opps)))
    print("  %-16s %9s %9s %9s %6s %6s %6s %6s %6s %6s %7s %7s"
          % ("value", "mean", "p10", "min", "wins", "tiles", "thirst", "lost", "idle%",
             "px%", "d_mean", "d_p10"))

    def run(val):
        return stats(evaluate(range(a.seed0, a.seed0 + a.seeds), opps,
                              workers=a.workers or None, quiet=True, params={a.axis: val}))

    # The incumbent is scored first and every delta is against it, so the table answers "should
    # this change?" rather than "which of these is biggest?". Those are different questions and
    # only the first one is actionable.
    base = run(incumbent)
    cells = [(incumbent, base)] + [(v, run(v)) for v in vals if v != incumbent]

    for val, s in cells:
        print("  %-16s $%8.0f $%8.0f $%8.0f %3d/%-3d %6.1f %6.1f %6.1f %6.1f %6.1f %+7.0f %+7.0f%s%s"
              % (label(val), s["mean"], s["p10"], s["min"], s["wins"], s["n"], s["tiles"],
                 s["thirst"], s["lost"], s["idle"], s["px"], s["mean"] - base["mean"],
                 s["p10"] - base["p10"],
                 "  <-- incumbent" if val == incumbent else "",
                 "  !! %d bad episodes" % s["bad"] if s["bad"] else ""))
    print("\n  worst turn across all cells: %.1fms against the 1000ms actTimeout"
          % max(s["worst"] for _, s in cells))

    print("\nDeltas are against %r. On %d episodes the standard error on the mean is roughly "
          "$%.0f;\nanything smaller than that is not a finding."
          % (incumbent, a.seeds * len(opps), 12000.0 / (a.seeds * len(opps)) ** 0.5))


if __name__ == "__main__":
    main_cli()
