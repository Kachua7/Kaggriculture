"""Paired-seat, paired-seed A/B: our policy vs our policy, seats swapped per seed.

Protocol (KT 4.2 / LADDER_AB_PROTOCOL anchor-rule addendum): for every seed run
TWO games on the same world — A as seat 0 vs B as seat 1, then B as seat 0 vs A
as seat 1 — and count A's W/L across the pair. Unpaired single-seat win rates
are anti-correlated with ladder performance; the seat-swap cancels first-mover
and market-position asymmetries.

Usage:
    .venv/bin/python analysis/paired_harness.py --a '{"route_weight": 1.0}' \
        --b '{}' --seeds 12 --label rw1_vs_shipped

Output: A's W-L-T, mean margin (A perspective), per-seat splits, per-seed pair
verdicts. Deterministic given seeds. Never raises on agent error: an exception
inside a policy forfeits that seat's episode exactly as on the ladder (the
engine sees whatever the policy returned last / PASS).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import KaggricultureEnv          # noqa: E402
from kagfarm import policy as policy_mod     # noqa: E402

DEFAULT_SEEDS = "1000,1001,1002,1003,1004,1005,1006,1007,1008,1009,1010,1011"


def _make(params_over):
    base = dict(policy_mod.PARAMS)
    base.update(params_over or {})
    return policy_mod.Policy(params=base)


def _play(seed, over_a, over_b):
    """One episode, A seat 0 vs B seat 1. Returns (bank_a, bank_b, err_a, err_b)."""
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    pol_a = _make(over_a)
    pol_b = _make(over_b)
    err = [None, None]
    while not env.done:
        act0 = pol_a.act(obs[0])
        act1 = pol_b.act(obs[1])
        if err[0] is None and getattr(pol_a, "last_error", None):
            err[0] = pol_a.last_error
        if err[1] is None and getattr(pol_b, "last_error", None):
            err[1] = pol_b.last_error
        obs, _ = env.step([act0, act1])
    return env.farms[0].money, env.farms[1].money, err[0], err[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default='{"route_weight": 1.0}', help="candidate overrides")
    ap.add_argument("--b", default="{}", help="incumbent overrides")
    ap.add_argument("--seeds", default=DEFAULT_SEEDS, help="comma list of seeds")
    ap.add_argument("--label", default="pair")
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
        m2 = b1_b - b0_b  # A is seat 1 here
        rows.append(dict(seed=seed, m1=m1, m2=m2,
                         errs=(ea0, ea1, eb0, eb1)))
        pair = ("W" if (m1 > 0) + (m2 > 0) > 1 else
                "L" if (m1 > 0) + (m2 > 0) == 0 else "S")
        print(f"seed {seed}: seatswapped margins {m1:+10,.0f} / {m2:+10,.0f} "
              f"-> pair {pair}", flush=True)
        for e in rows[-1]["errs"]:
            if e:
                print(f"    !! agent error: {e[:160]}", flush=True)

    w = sum(1 for r in rows if r["m1"] > 0) + sum(1 for r in rows if r["m2"] > 0)
    n = 2 * len(rows)
    t = n - w - sum(1 for r in rows for m in (r["m1"], r["m2"]) if m < 0)
    margins = [m for r in rows for m in (r["m1"], r["m2"])]
    seat0 = sum(r["m1"] for r in rows) / len(rows)
    seat1 = sum(r["m2"] for r in rows) / len(rows)
    print(f"\n== {a.label}: A vs B, paired seats, {len(rows)} seeds ({n} games) ==")
    print(f"  A: {w}W-{n - w - t}L-{t}T   W/L {w / (n - t) if n > t else 0:.3f}")
    print(f"  mean margin {sum(margins) / n:+,.0f}   median {sorted(margins)[n // 2]:+,.0f}")
    print(f"  seat-0 mean {seat0:+,.0f}   seat-1 mean {seat1:+,.0f}")
    worst = min(margins)
    print(f"  worst game {worst:+,.0f}")
    errs = [e for r in rows for e in r["errs"] if e]
    if errs:
        print(f"  !! {len(errs)} agent errors across games")


if __name__ == "__main__":
    main()
