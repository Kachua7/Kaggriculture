"""Score a parameter change on several DISJOINT seed blocks instead of one panel.

This exists because the harness's failure mode is not noise, it is *confident* noise. A 144-episode
panel reports a standard error around $1k on the mean, so a change worth +$800 looks like a clear
win on one block and can look like a clear loss on the next. `sweep.py` guards against that with a
single holdout; this guards against it harder, by asking the only question that has actually
predicted whether a change survives: **does the sign hold on every block?**

Two changes this season looked adoptable on a tuning panel and were not, and both were caught here:

  `n_animals=2`   +$34, +$43, then -$1,312 and -$1,318 over four blocks. The tuning block also
                  reported a 10th-percentile gain of +$1,494, the largest single-block tail
                  improvement measured all day, and it reversed on the very next 48 seeds.
  a 15-axis descent  reported +$4,785 of mean on its own panel and -$400 on fresh seeds.

So the decision rule is: adopt only if every block agrees in sign, or if the aggregate over all
blocks clears roughly $1k with no block worse than about -$500. Blocks are 48 seeds x 3 opponents
= 144 episodes each, which takes about 2.5s, so a four-block verdict costs well under a minute per
cell. There is no reason left to decide anything on one panel.

    python3 analysis/blocks.py --set n_animals=2 --blocks 4
    python3 analysis/blocks.py --set haul_trigger=0.55 --set haul_min=14 --blocks 3
    python3 analysis/blocks.py --set n_animals=2 --vs n_animals=3   # three-way, shared baseline
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate                      # noqa: E402
from kagfarm.policy import PARAMS              # noqa: E402


def parse_set(items):
    """`["n_animals=2", "haul_trigger=0.55"]` -> `{"n_animals": 2, "haul_trigger": 0.55}`.

    `literal_eval` rather than `float`, so ints stay ints -- `n_animals` indexes a range and
    `2.0` would work by accident today and break the day someone writes `range(n)`.
    """
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit("--set wants key=value, got %r" % it)
        k, v = it.split("=", 1)
        k = k.strip()
        if k not in PARAMS:
            raise SystemExit("unknown param %r (not in PARAMS)" % k)
        try:
            out[k] = ast.literal_eval(v.strip())
        except Exception:
            out[k] = v.strip()
    return out


def metrics(seeds, opps, over, workers):
    rows = evaluate(seeds, opps, workers=workers, quiet=True, params=dict(PARAMS, **over))
    banks = sorted(r["bank"] for r in rows)
    n = len(banks)
    return {
        "n": n,
        "mean": sum(banks) / n,
        "p10": banks[max(0, int(0.1 * n) - 1)],
        "min": banks[0],
        "max": banks[-1],
        "lost": sum(r.get("lost", 0) for r in rows) / n,
        "wins": sum(1 for r in rows if r["bank"] > r.get("opp_bank", 0)),
        "err": sum(1 for r in rows if r["err"]),
        "over_budget": sum(1 for r in rows if r["over_budget"]),
    }


def verdict(deltas, floor=-500.0, need=1000.0):
    """Adopt / reject / inconclusive, from the per-block mean deltas.

    Deliberately conservative in the middle: "inconclusive" is a real answer here and shipping on
    it is how the two reversals above happened.
    """
    if not deltas:
        return "no data"
    agg = sum(deltas) / len(deltas)
    if all(d > 0 for d in deltas):
        return "ADOPT  (every block positive, aggregate %+.0f)" % agg
    if all(d < 0 for d in deltas):
        return "REJECT (every block negative, aggregate %+.0f)" % agg
    if agg >= need and min(deltas) >= floor:
        return "ADOPT  (aggregate %+.0f clears $%.0f, worst block %+.0f)" % (agg, need, min(deltas))
    if agg <= -need and max(deltas) <= -floor:
        return "REJECT (aggregate %+.0f, best block %+.0f)" % (agg, max(deltas))
    return "INCONCLUSIVE (aggregate %+.0f, blocks %s) -- leave the incumbent alone" % (
        agg, " ".join("%+.0f" % d for d in deltas))


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append", default=[],
                    help="param override, key=value; repeatable. This is the CANDIDATE cell.")
    ap.add_argument("--vs", action="append", default=[],
                    help="a second candidate scored against the same baseline; repeatable")
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--block-size", type=int, default=48)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--opps", default="starter,heuristic,random")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    opps = a.opps.split(",")
    workers = a.workers or None
    cands = [("incumbent", {})]
    if a.set:
        cands.append((",".join(a.set), parse_set(a.set)))
    if a.vs:
        cands.append((",".join(a.vs), parse_set(a.vs)))
    if len(cands) == 1:
        raise SystemExit("nothing to compare: pass at least one --set key=value")

    blocks = [(a.start + i * a.block_size, a.start + (i + 1) * a.block_size)
              for i in range(a.blocks)]
    print("%d blocks x %d seeds x %d opponents = %d episodes per cell\n"
          % (a.blocks, a.block_size, len(opps), a.blocks * a.block_size * len(opps)))
    print("%-11s %-26s %9s %9s %9s %6s %5s   %8s %8s"
          % ("block", "cell", "mean", "p10", "min", "lost", "wins", "d_mean", "d_p10"))

    t0 = time.monotonic()
    deltas = {tag: [] for tag, _ in cands[1:]}
    table = []
    for lo, hi in blocks:
        seeds = range(lo, hi)
        base = None
        for tag, over in cands:
            m = metrics(seeds, opps, over, workers)
            if base is None:
                base = m
            d_mean, d_p10 = m["mean"] - base["mean"], m["p10"] - base["p10"]
            if tag in deltas:
                deltas[tag].append(d_mean)
            flag = ""
            if m["err"] or m["over_budget"]:
                flag = "  !! %d err %d over-budget" % (m["err"], m["over_budget"])
            print("%-11s %-26s %9.0f %9.0f %9.0f %6.1f %5d   %+8.0f %+8.0f%s"
                  % ("%d-%d" % (lo, hi - 1), tag[:26], m["mean"], m["p10"], m["min"],
                     m["lost"], m["wins"], d_mean, d_p10, flag))
            table.append(dict(m, block="%d-%d" % (lo, hi - 1), cell=tag,
                              d_mean=d_mean, d_p10=d_p10))
        print()

    print("verdict after %.0fs" % (time.monotonic() - t0))
    for tag in deltas:
        print("  %-26s %s" % (tag[:26], verdict(deltas[tag])))
    if a.out:
        path = os.path.join(_ROOT, a.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump({"rows": table, "deltas": deltas, "opps": a.opps,
                       "blocks": [list(b) for b in blocks]}, fh, indent=2)
        print("wrote %s" % a.out)


if __name__ == "__main__":
    main_cli()
