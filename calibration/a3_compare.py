"""A3 gate: does the pinned real engine move the numbers the plan pre-committed to?

Runs the same 32-seed panel on both tiers — mirror (engine.py) and real (vendored
kaggle-environments via bridge/real_env.py) — and prints the comparison the standing
kill/go rule reads:

  Panel SELF    32 seeds, both seats our policy (the contested-market regime).
                Per-seed bank columns, p10-set membership per engine, Jaccard overlap.
  Panel STARTER 32 seeds vs the official starter (win-rate is only meaningful against a
                distinct opponent).

  GATE: |Δwin-rate| < 1pp AND p10-set Jaccard >= 0.85  ->  KILL A5: keep v1, stop editing
        constants — the contradiction is real on paper but irrelevant to this policy.
        Otherwise                                       ->  GO A5: re-sweep only axes
        touching a DIVERGE row, one cycle, then freeze.

Banks are never compared across engines to the dollar — only membership and deltas,
because the engines differ by design (that is the whole point of A2).

Usage:  .venv/bin/python calibration/a3_compare.py [--seeds 32]
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


def p10_set(banks):
    """Indices of the bottom-decile banks (mirrors eval's p10 index)."""
    n = len(banks)
    k = max(1, int(0.1 * n))
    order = sorted(range(n), key=lambda i: banks[i])
    return set(order[:k])


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=32)
    a = ap.parse_args()
    seeds = range(a.seeds)

    rows = {}
    for engine in ("mirror", "real"):
        for opp in ("self", "starter"):
            print(f"==> {engine} vs {opp} ...", flush=True)
            rows[(engine, opp)] = evaluate(seeds, [opp], "main", quiet=True, engine=engine)

    ms = rows[("mirror", "self")]
    rs = rows[("real", "self")]
    mb = [r["bank"] for r in ms]
    rb = [r["bank"] for r in rs]

    print("\n=== Panel SELF (both seats ours) — per-seed banks ===")
    print(f"{'seed':>4}  {'bank_mirror':>12}  {'bank_real':>12}  {'delta':>10}")
    for i in range(a.seeds):
        print(f"{i:>4}  {mb[i]:>12,.0f}  {rb[i]:>12,.0f}  {rb[i]-mb[i]:>10,.0f}")

    mean_m, mean_r = sum(mb) / len(mb), sum(rb) / len(rb)
    idx = lambda xs: max(0, int(0.1 * len(xs)) - 1)
    p10_m, p10_r = sorted(mb)[idx(mb)], sorted(rb)[idx(rb)]
    set_m, set_r = p10_set(mb), p10_set(rb)
    j = jaccard(set_m, set_r)

    print("\n=== Panel SELF summary ===")
    print(f"mean  mirror ${mean_m:,.0f}   real ${mean_r:,.0f}   delta ${mean_r-mean_m:+,.0f} ({100*(mean_r-mean_m)/max(1,abs(mean_m)):+.1f}%)")
    print(f"p10   mirror ${p10_m:,.0f}   real ${p10_r:,.0f}   delta ${p10_r-p10_m:+,.0f}")
    print(f"p10-set Jaccard: {j:.3f}   (mirror p10 members: {sorted(set_m)}; real: {sorted(set_r)})")

    mw = rows[("mirror", "starter")]
    rw = rows[("real", "starter")]
    wm = sum(1 for r in mw if r["bank"] > r["opp_bank"]) / len(mw)
    wr = sum(1 for r in rw if r["bank"] > r["opp_bank"]) / len(rw)
    dw = wr - wm
    print("\n=== Panel STARTER (win-rate panel) ===")
    print(f"win-rate mirror {wm:.1%}   real {wr:.1%}   delta {dw:+.1%}")

    go = (abs(dw) >= 0.01) or (j < 0.85)
    print("\n=== PRE-COMMITTED GATE ===")
    print(f"|delta win-rate| = {abs(dw):.3f} (< 0.01 required to kill), Jaccard = {j:.3f} (>= 0.85 required to kill)")
    print("VERDICT:", "GO A5 — re-sweep DIVERGE-touching axes only, one cycle, then freeze." if go
          else "KILL A5 — ship v1, stop editing constants; the contradiction is real but irrelevant to this policy.")
    return 1 if go else 0


if __name__ == "__main__":
    sys.exit(main())
