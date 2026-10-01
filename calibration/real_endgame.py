"""Real-tier re-measurement of the endgame axes and the `lost` overflow metric.

The open item from calibration/live.md (the A5 block): `endgame_days` and `lost` were
re-measured on the mirror only. This script re-runs the decisive cells on the REAL tier
(vendored kaggle-environments via bridge/real_env.py) -- both seats ours, the regime
where the endgame sell wave and shed overflow actually bite:

    cells   endgame_days in {3, 5 (incumbent), 7}
    seeds   --seeds (default 24), disjoint from nothing: this is a confirmation, not a
            search -- the mirror already measured the curve shape (single-peaked at 5).

    python3 -m calibration.real_endgame --seeds 24          (needs the real-tier venv)
    python3 calibration/real_endgame.py --seeds 24 --engine mirror   (sanity / mirror side)

`lost` is reported per cell because that is the half of the question the mirror answered
only implicitly: shed overflow at midnight destroys goods the farm grew, and the
endgame tap-opening exists to stop exactly that.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--engine", default="real", choices=("real", "mirror"))
    a = ap.parse_args()
    seeds = range(a.seeds)

    print("engine=%s  seeds=%d  both seats ours (self_live)\n" % (a.engine, a.seeds))
    print("(the `lost` overflow counter is mirror instrumentation; on the real tier it "
          "prints n/a)\n")
    print("%-14s %9s %9s %9s %8s %6s" % ("cell", "mean", "p10", "min", "lost", "err"))
    base = None
    for ed in (5, 3, 7):          # incumbent first: every other cell prints a delta
        over = {} if ed == 5 else {"endgame_days": ed}
        rows = evaluate(seeds, ["self_live"], quiet=True, engine=a.engine, params=over)
        banks = sorted(r["bank"] for r in rows)
        n = len(banks)
        mean = sum(banks) / n
        p10 = banks[max(0, int(0.1 * n) - 1)]
        lost_vals = [r.get("lost") for r in rows]
        lost = ("%.1f" % (sum(v for v in lost_vals if isinstance(v, (int, float))) / n)
                if any(isinstance(v, (int, float)) for v in lost_vals) else "n/a")
        err = sum(1 for r in rows if r["err"])
        tag = "endgame_days=%d%s" % (ed, "  [inc]" if ed == 5 else "")
        print("%-14s %9.0f %9.0f %9.0f %8s %6d" % (tag, mean, p10, banks[0], lost, err))
        if base is None:
            base = mean
        else:
            print("%-14s %+9.0f vs incumbent\n" % ("delta", mean - base))


if __name__ == "__main__":
    main()
