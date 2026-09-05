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
    # `mix_cap` is the only handle on the OPENING. Measured over days 0-29 on 4 seeds, the
    # per-crop ceiling never binds once the land opens -- melon sits at 1-8 tiles against a
    # ceiling of 104 -- but on the single starting quadrant it caps melon at 26.1 against 25
    # tiles of land, so days 1-9 run 24/25 tiles of melon, the one crop no shop buys. 1.0 caps
    # melon at 8.7 tiles there; 0.6 at 5.2. This axis is really "how much of the opening is
    # allowed to be one crop", and it is scored below.
    "mix_cap":     [0.6, 1.0, 1.5, 2.0, 3.0, 100.0],
    "seed_alpha":  [0.0, 0.15, 0.3, 0.5, 0.8, 1.0],
    "max_hands":   [6, 8, 10, 12, 14, 16, 20],
    "reserve":     [0.0, 0.6, 0.9, 1.1, 1.3],
    "crowded":     [0.4, 0.55, 0.7, 0.85],
    "seed_slots":  [2, 3, 4, 5],
    "hire_hours":  [2, 4, 6, 8],
    "seed_grace":  [1, 3, 6],
    "labour_slack": [0.7, 0.85, 1.0, 1.2, 1.5, 3.0],
    "fert_margin": [1.2, 1.6, 2.0, 2.3, 2.6, 3.0],
    "fert_stock":  [8, 12, 14, 16, 20, 24],
    "drain_frac":  [0.0, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0],
    # Incumbent is 5 and the curve is single-peaked around it: 4 is $2.4k worse, 6 is $1.0k
    # worse, 8 gives back half the gain. The old list stopped at 4, which meant any descent
    # over this axis silently regressed the largest win in the project.
    "endgame_days": [3, 4, 5, 6, 8],
    # Haul discipline. Both sharp, and both measured the wrong way round from intuition -- see
    # the comments on `haul_trigger` in policy.py. 0.55 drives spoilage to zero and costs $9.6k.
    "haul_trigger": [0.55, 1.0, 1.5, 2.0, 2.5, 999.0],
    "haul_min":    [10, 14, 18, 22, 28],
    "n_animals":   [0, 1, 2, 3, 4],
}
# Dropped: `land_margin` and `px_cap`. Both measured flat across their whole candidate range on
# 144 episodes -- every cell within noise of the incumbent -- so they only spent evaluations.


def score(params, seeds, opps, workers, objective="mean"):
    """Panel score for one cell, or a large negative on any veto.

    A raise inside `Policy.act` is caught by its own guard and recorded in `last_error`, so it
    shows up as a silently worse episode rather than a crash -- which is exactly why it has to
    be vetoed explicitly here instead of being left to the mean.

    Two objectives, and against a peer they disagree:

      `mean`  (mean bank, p10 bank). Right against the built-in opponents, where every episode is
              won anyway and the only question is how much is banked.
      `wins`  (win fraction, mean bank). Right against `self`, because a ladder rating is won per
              episode rather than per dollar -- and in the peer regime a cell can bank far more
              while losing far more matches. Capping the melon opening does exactly that: +$25k
              of bank, -14pp of win rate. See `analysis/melon_matrix.py`.
    """
    rows = evaluate(seeds, opps, workers=workers, quiet=True, params=params)
    banks = sorted(r["bank"] for r in rows)
    if any(r["err"] for r in rows) or any(r["over_budget"] for r in rows):
        return -1e12, -1e12
    n = len(banks)
    mean = sum(banks) / n
    if objective == "wins":
        wins = sum(1 for r in rows if r["bank"] > r.get("opp_bank", 0)) / n
        return wins, mean
    return mean, banks[max(0, int(0.1 * n) - 1)]


def _fmt(s, objective):
    if objective == "wins":
        return "win %6.1f%%  mean $%8.0f" % (100 * s[0], s[1])
    return "mean $%8.0f  p10 $%8.0f" % (s[0], s[1])


def sweep(seeds, opps, axes, rounds, workers, objective="mean"):
    best = {k: PARAMS[k] for k in axes}
    cur = score(best, seeds, opps, workers, objective)
    print("start %s -> %s" % (best, _fmt(cur, objective)))
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
                s = score(cand, seeds, opps, workers, objective)
                evals += 1
                flag = ""
                if s > cur:
                    best, cur, changed, flag = cand, s, True, "  <-- best"
                print("  %-12s = %-6s  %s%s" % (axis, val, _fmt(s, objective), flag))
            if best[axis] != incumbent:
                print("  %-12s : %s -> %s" % (axis, incumbent, best[axis]))
        print("round %d done: %s  (%d evals, %.0fs)"
              % (rnd, _fmt(cur, objective), evals, time.monotonic() - t0))
        if not changed:
            break
    return best, cur


def holdout(best, seeds, opps, workers, objective="mean"):
    """Re-score the winning cell and the incumbent on seeds the descent never saw.

    Reported per axis as well as for the block, because the block is usually carried by one or
    two axes and the rest are fitted noise -- and it is cheaper to find that out here than to
    ship it.
    """
    inc = {k: PARAMS[k] for k in best}
    rows = [("incumbent", score(inc, seeds, opps, workers, objective))]
    for axis in best:
        if best[axis] != inc[axis]:
            rows.append(("%s = %s" % (axis, best[axis]),
                         score(dict(inc, **{axis: best[axis]}), seeds, opps, workers, objective)))
    rows.append(("all changes together", score(best, seeds, opps, workers, objective)))
    base = rows[0][1]
    a, b = ("win%", "mean") if objective == "wins" else ("mean", "p10")
    print("\nHOLDOUT on %d seeds x %s, %d episodes" % (len(seeds), ",".join(opps),
                                                       len(seeds) * len(opps)))
    print("  %-28s %10s %10s   %9s %9s" % ("cell", a, b, "d_" + a, "d_" + b))
    for tag, s in rows:
        k = 100.0 if objective == "wins" else 1.0
        print("  %-28s %10.1f %10.0f   %+9.1f %+9.0f"
              % (tag, k * s[0], s[1], k * (s[0] - base[0]), s[1] - base[1]))
    return rows


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--axes", default=",".join(AXES))
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--objective", default="mean", choices=("mean", "wins"),
                    help="'wins' for self-play: rank by episodes taken, tiebreak on bank")
    ap.add_argument("--holdout", type=int, default=24,
                    help="how many unseen seeds to re-score the winner on; 0 to skip")
    ap.add_argument("--out", default="analysis/sweep_best.json")
    a = ap.parse_args()
    axes = [x for x in a.axes.split(",") if x in AXES]
    opps = a.opps.split(",")
    best, s = sweep(range(a.seeds), opps, axes, a.rounds, a.workers or None, a.objective)
    print("\nTUNING PANEL %s\n%s" % (_fmt(s, a.objective), json.dumps(best, indent=2)))
    hold = None
    if a.holdout:
        hold = holdout(best, range(a.seeds, a.seeds + a.holdout), opps, a.workers or None,
                       a.objective)
    path = os.path.join(_HERE, a.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"params": best, "score_a": s[0], "score_b": s[1],
                   "objective": a.objective, "seeds": a.seeds, "opps": a.opps,
                   "holdout": [[t, list(v)] for t, v in (hold or [])]}, fh, indent=2)
    print("wrote %s" % a.out)


if __name__ == "__main__":
    main_cli()
