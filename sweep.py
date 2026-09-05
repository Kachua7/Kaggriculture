"""
Parameter sweeps over `kagfarm.policy.PARAMS`, scored on the `eval.py` seed panel.

Coordinate descent, not a grid. The grid over eight parameters at four levels each is 65,536
cells and most of them are uninteresting; coordinate descent walks one axis at a time, keeps
the best value, and moves on, then repeats until a full pass changes nothing. It finds a local
optimum rather than the global one, which is the right trade here because the objective is
noisy: two cells within a few hundred dollars of each other are not distinguishable on a
16-seed panel, so the extra resolution a full grid buys is mostly noise.

The score is the MEAN bank over the panel with a p10 tiebreak, and a hard veto on any cell
that raises an exception or breaches the turn budget. Mean alone would happily accept a cell
that wins big on eight seeds and collapses on the other eight -- and the ladder pairs us
against one opponent at a time, so a collapse is a lost match, not an averaged-down one.

**Every run ends on a holdout, and the reason is a measurement.** A 15-axis descent on 16 seeds
x 2 opponents once reported +$4,785 of mean and +$16,354 of p10 over the incumbent. Re-scored on
seeds 24-47 the same cell was -$400 on the mean. 125 evaluations against a 32-episode panel is
enough resolution to fit the panel, so the tuning panel's own number is not evidence; the number
printed under HOLDOUT is. Treat any axis whose holdout delta is under about $500 as noise and
leave the incumbent alone -- with a 144-episode panel the standard error on the mean is still
around $1k, so a single-axis "win" below that is a coin flip with extra steps.

    python3 sweep.py --seeds 12 --axes mix_cap,seed_alpha,max_hands
    python3 sweep.py --seeds 24 --rounds 3          # everything, twice over
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from eval import evaluate
from kagfarm.policy import PARAMS

# Candidate values per axis. Ordered so the incumbent default is somewhere in the middle,
# which makes a no-change pass cheap to recognise.
AXES = {
    "mix_cap":     [0.6, 1.0, 1.5, 2.0, 3.0, 100.0],
    "seed_alpha":  [0.0, 0.15, 0.3, 0.5, 0.8, 1.0],
    "max_hands":   [6, 8, 10, 12, 14, 16, 20],
    "land_margin": [1.0, 1.05, 1.2, 1.5, 2.0],
    "reserve":     [0.0, 0.6, 0.9, 1.1, 1.3],
    "crowded":     [0.4, 0.55, 0.7, 0.85],
    "seed_slots":  [2, 3, 4, 5],
    "hire_hours":  [2, 4, 6, 8],
    "seed_grace":  [1, 3, 6],
    "labour_slack": [0.7, 0.85, 1.0, 1.2, 1.5, 3.0],
    "fert_margin": [1.2, 1.6, 2.0, 2.3, 2.6, 3.0],
    "fert_stock":  [8, 12, 14, 16, 20, 24],
    "drain_frac":  [0.0, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0],
    "px_cap":      [1.5, 2.0, 2.5, 3.0],
    "endgame_days": [1, 2, 3, 4],
}


def score(params, seeds, opps, workers):
    """(mean bank, p10 bank) over the panel, or a large negative on any veto.

    A raise inside `Policy.act` is caught by its own guard and recorded in `last_error`, so it
    shows up as a silently worse episode rather than a crash -- which is exactly why it has to
    be vetoed explicitly here instead of being left to the mean.
    """
    rows = evaluate(seeds, opps, workers=workers, quiet=True, params=params)
    banks = sorted(r["bank"] for r in rows)
    if any(r["err"] for r in rows) or any(r["over_budget"] for r in rows):
        return -1e12, -1e12
    n = len(banks)
    return sum(banks) / n, banks[max(0, int(0.1 * n) - 1)]


def sweep(seeds, opps, axes, rounds, workers):
    best = {k: PARAMS[k] for k in axes}
    cur = score(best, seeds, opps, workers)
    print("start %s -> mean $%.0f p10 $%.0f" % (best, cur[0], cur[1]))
    t0 = time.monotonic()
    evals = 1
    for rnd in range(rounds):
        changed = False
        for axis in axes:
            incumbent = best[axis]
            for val in AXES[axis]:
                if val == incumbent:
                    continue
                cand = dict(best, **{axis: val})
                s = score(cand, seeds, opps, workers)
                evals += 1
                flag = ""
                if s > cur:
                    best, cur, changed, flag = cand, s, True, "  <-- best"
                print("  %-12s = %-6s  mean $%8.0f  p10 $%8.0f%s"
                      % (axis, val, s[0], s[1], flag))
            if best[axis] != incumbent:
                print("  %-12s : %s -> %s" % (axis, incumbent, best[axis]))
        print("round %d done: mean $%.0f p10 $%.0f  (%d evals, %.0fs)"
              % (rnd, cur[0], cur[1], evals, time.monotonic() - t0))
        if not changed:
            break
    return best, cur


def holdout(best, seeds, opps, workers):
    """Re-score the winning cell and the incumbent on seeds the descent never saw.

    Reported per axis as well as for the block, because the block is usually carried by one or
    two axes and the rest are fitted noise -- and it is cheaper to find that out here than to
    ship it.
    """
    inc = {k: PARAMS[k] for k in best}
    rows = [("incumbent", score(inc, seeds, opps, workers))]
    for axis in best:
        if best[axis] != inc[axis]:
            rows.append(("%s = %s" % (axis, best[axis]),
                         score(dict(inc, **{axis: best[axis]}), seeds, opps, workers)))
    rows.append(("all changes together", score(best, seeds, opps, workers)))
    base = rows[0][1]
    print("\nHOLDOUT on %d seeds x %s, %d episodes" % (len(seeds), ",".join(opps),
                                                       len(seeds) * len(opps)))
    print("  %-28s %10s %10s   %9s %9s" % ("cell", "mean", "p10", "d_mean", "d_p10"))
    for tag, s in rows:
        print("  %-28s $%9.0f $%9.0f   %+9.0f %+9.0f"
              % (tag, s[0], s[1], s[0] - base[0], s[1] - base[1]))
    return rows


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--axes", default=",".join(AXES))
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--holdout", type=int, default=24,
                    help="how many unseen seeds to re-score the winner on; 0 to skip")
    ap.add_argument("--out", default="analysis/sweep_best.json")
    a = ap.parse_args()
    axes = [x for x in a.axes.split(",") if x in AXES]
    opps = a.opps.split(",")
    best, s = sweep(range(a.seeds), opps, axes, a.rounds, a.workers or None)
    print("\nTUNING PANEL mean $%.0f p10 $%.0f\n%s" % (s[0], s[1], json.dumps(best, indent=2)))
    hold = None
    if a.holdout:
        hold = holdout(best, range(a.seeds, a.seeds + a.holdout), opps, a.workers or None)
    path = os.path.join(_HERE, a.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"params": best, "mean": s[0], "p10": s[1],
                   "seeds": a.seeds, "opps": a.opps,
                   "holdout": [[t, list(v)] for t, v in (hold or [])]}, fh, indent=2)
    print("wrote %s" % a.out)


if __name__ == "__main__":
    main_cli()
