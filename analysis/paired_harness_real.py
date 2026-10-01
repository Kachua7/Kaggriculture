"""Paired-seat, paired-seed A/B on the REAL tier (vendored 1.32.7) — the ladder-faithful gate.

The mirror (engine.py) is the screening tier: its contested constants and RNG streams
differ from the vendored interpreter, and 0930c measured the consequence for the book —
the elite opening book serves d0-1 on the mirror (halted at d2 by a fert-bucket artifact
the real engine does not produce) vs a mean 20.5 served days across the 12 donor worlds.
Any paired verdict about opening-book behavior must come from the engine the ladder
actually scores.

Protocol identical to analysis/paired_harness.py: for every seed run TWO games on the
same world — A as seat 0 vs B as seat 1, then B as seat 0 vs A as seat 1 — and count
A's W/L across the pair. The seat swap cancels first-mover and market-position
asymmetry. Real-tier runtime is ~100x the mirror, so the default panel is 6 seeds
(12 games) with --seeds taking a comma list for the full gate.

Policies are constructed DIRECTLY from kagfarm.policy.Policy with explicit params
(the A4 rule: no module-level PARAMS mutation, no dependency on a possibly-stale
flattened main.py).

Usage:
    .venv/bin/python analysis/paired_harness_real.py --a '{"elite_book": 1}' --b '{}' \
        --seeds 2000,2001,2002,2003,2004,2005
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import RealEnv           # noqa: E402
from kagfarm import policy as policy_mod      # noqa: E402
from kagfarm.policy import Policy             # noqa: E402

DEFAULT_SEEDS = "2000,2001,2002,2003,2004,2005"


def _make(params_over):
    base = dict(policy_mod.PARAMS)
    base.update(params_over or {})
    return Policy(params=base)


def _play(seed, over_a, over_b):
    """One episode on the vendored engine: A seat 0 vs B seat 1."""
    env = RealEnv(seed)
    pol_a = _make(over_a)
    pol_b = _make(over_b)
    views = [env._obs_view(0), env._obs_view(1)]
    err = [None, None]
    while not env.done:
        act0 = pol_a.act(views[0], env.config)
        act1 = pol_b.act(views[1], env.config)
        if err[0] is None and getattr(pol_a, "last_error", None):
            err[0] = pol_a.last_error
        if err[1] is None and getattr(pol_b, "last_error", None):
            err[1] = pol_b.last_error
        env.step([act0, act1])
        views = [env._obs_view(0), env._obs_view(1)]
    banks = env.banks()
    return banks[0], banks[1], err[0], err[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default='{"elite_book": 1}', help="candidate overrides")
    ap.add_argument("--b", default="{}", help="incumbent overrides")
    ap.add_argument("--seeds", default=DEFAULT_SEEDS, help="comma list of seeds")
    ap.add_argument("--label", default="pair_real")
    a = ap.parse_args()
    over_a = json.loads(a.a)
    over_b = json.loads(a.b)
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]

    rows = []
    for seed in seeds:
        # Game 1: A seat 0, B seat 1. Game 2: seats swapped, SAME world.
        b0_a, b1_a, ea0, ea1 = _play(seed, over_a, over_b)
        m1 = b0_a - b1_a
        b0_b, b1_b, eb0, eb1 = _play(seed, over_b, over_a)
        m2 = b1_b - b0_b          # A is seat 1 here
        rows.append(dict(seed=seed, m1=m1, m2=m2, errs=(ea0, ea1, eb0, eb1)))
        pair = ("W" if (m1 > 0) + (m2 > 0) > 1 else
                "L" if (m1 > 0) + (m2 > 0) == 0 else "S")
        print(f"seed {seed}: seatswapped margins {m1:+10,.0f} / {m2:+10,.0f} "
              f"-> pair {pair}", flush=True)
        for e in rows[-1]["errs"]:
            if e:
                print(f"    !! agent error: {e[:160]}", flush=True)

    w = sum(1 for r in rows if r["m1"] > 0) + sum(1 for r in rows if r["m2"] > 0)
    n = 2 * len(rows)
    l = sum(1 for r in rows for m in (r["m1"], r["m2"]) if m < 0)
    t = n - w - l
    margins = [m for r in rows for m in (r["m1"], r["m2"])]

    print(f"\n== {a.label}: A vs B, paired seats, {len(seeds)} seeds ({n} games, REAL tier) ==")
    print(f"  A: {w}W-{l}L-{t}T   W/L {w / n:.3f}")
    print(f"  mean margin {sum(margins) / n:+,.0f}   median {sorted(margins)[n // 2]:+,.0f}")
    print(f"  best {max(margins):+,.0f}   worst {min(margins):+,.0f}")


if __name__ == "__main__":
    main()
