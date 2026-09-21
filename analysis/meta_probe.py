"""Quick probe: incumbent vs the live-meta archetypes on a handful of seeds.

The B2 gap: every gate so far ran against the synthetic panel (starter/heuristic/random
+ our own ablations). The two autopsied ladder losses (calibration/live.md, 2026-09-17
night) are the first opponents that resemble the actual field. This probe quantifies it:

    python3 analysis/meta_probe.py --seeds 6

Rows print per-opponent W/L and margin, incumbent PARAMS only -- no overlay, pure
baseline read of how the shipped cell does against the live-meta shape locally.
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate                      # noqa: E402

OPPS = ["arch_meta_labor", "arch_meta_allin", "self", "heuristic"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    rows = evaluate(range(a.seeds), OPPS, workers=a.workers, quiet=True)
    by = {}
    for r in rows:
        by.setdefault(r["opp"], []).append(r)
    print(f"\nincumbent vs panels ({a.seeds} seeds each, mirror engine)")
    print(f"{'opponent':<18} {'W-L':>5} {'win%':>6} {'meanΔ':>10} {'p10Δ':>9}")
    for opp in OPPS:
        rs = by.get(opp, [])
        if not rs:
            continue
        deltas = [r["bank"] - r["opp_bank"] for r in rs]
        wins = sum(1 for d in deltas if d > 0)
        ds = sorted(deltas)
        mean = sum(deltas) / len(deltas)
        p10 = ds[max(0, int(0.1 * len(ds)) - 1)]
        print(f"{opp:<18} {wins:>2}-{len(rs)-wins:<2} {100*wins/len(rs):>5.0f}% {mean:>+10,.0f} {p10:>+9,.0f}")


if __name__ == "__main__":
    main()
