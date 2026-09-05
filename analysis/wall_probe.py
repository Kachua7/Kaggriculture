"""Which engine limit is throttling the farm: the shed, the order book, or neither.

Every change that grows the farm reports the same shape. `max_hands` 8 -> 10 buys 1.7 live tiles a
day and loses $2,205; `labour_slack` 1.0 -> 1.5 buys 2.1 tiles and loses $486; both raise `lost`
-- items destroyed by shed overflow -- from 2 an episode to 10 or 11. Meanwhile the dawn allocator
reports `labour` as the binding constraint on two days out of three (`analysis/limit_probe.py`)
while sitting on 18 to 40 empty tiles and $10k to $18k of unspent cash. Something between the
field and the bank is full, and the candidates are the 100-item shed and the ten market orders a
turn.

So raise them, one at a time, and see which one the money was waiting on. Both are engine
constants, which makes this a counterfactual rather than a proposal -- the point is not that the
shed could be bigger, it is to learn whether a bigger farm would pay if the produce could get
out. If the mean recovers with a deeper shed, harvest scheduling and sell throughput are worth
real work and the acreage parameters should be re-scanned afterwards. If it does not, the farm is
limited by something else and acreage is not the lever at all.

    python3 analysis/wall_probe.py                       # 24 seeds x 2 opponents per cell
    python3 analysis/wall_probe.py --seeds 48 --hands 8,12,16
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from kagfarm.constants import SEASON_DAYS, TURNS_PER_DAY


def run_cell(job):
    """One episode with the engine's shed and order-book limits overridden."""
    seed, opp_name, shed_cap, slots, hands = job

    import engine
    from kagfarm import policy as _policy
    from agents import BUILTIN_AGENTS
    import main

    # Both modules import these by name, and both need to move together: the engine enforces the
    # limit and the policy's `crowded` test and sell-slot floor are calibrated against it. Patching
    # only the engine would measure a bigger shed that the agent never learns it has.
    for mod in (engine, _policy):
        mod.SHED_CAPACITY = shed_cap
        mod.MAX_MARKET_ORDERS = slots
    _policy.PARAMS["max_hands"] = hands

    lost = {"n": 0}
    env = engine.KaggricultureEnv(episode_steps=720, seed=seed)
    me = env.farms[0]
    _add = env._add_shed

    def add_shed(f, item, n):
        got = _add(f, item, n)
        if f is me:
            lost["n"] += max(0, n - got)
        return got

    env._add_shed = add_shed

    main._POLICIES.clear()
    opp = BUILTIN_AGENTS[opp_name]
    obs = env._obs()
    tile_days = idle = unit_turns = 0
    while not env.done:
        act = main.agent(obs[0])
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        unit_turns += len(ops)
        idle += sum(1 for o in ops if not o or o[0] == "PASS")
        obs, _ = env.step([act, opp(obs[1])])
        tile_days += sum(1 for row in me.tiles for t in row
                         if isinstance(t, dict) and t.get("kind") == "PLANT")

    return dict(shed=shed_cap, slots=slots, hands=hands, bank=me.money,
                lost=lost["n"], tiles=tile_days / (SEASON_DAYS * TURNS_PER_DAY),
                idle=100.0 * idle / max(1, unit_turns))


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--hands", default="8,12")
    ap.add_argument("--sheds", default="100,300")
    ap.add_argument("--slots", default="10,30")
    a = ap.parse_args()

    opps = a.opps.split(",")
    hands = [int(h) for h in a.hands.split(",")]
    sheds = [int(s) for s in a.sheds.split(",")]
    slots = [int(s) for s in a.slots.split(",")]

    jobs = [(seed, opp, shed, slot, hand)
            for hand in hands for shed in sheds for slot in slots
            for opp in opps for seed in range(a.seeds)]
    with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 4, 16)) as ex:
        rows = list(ex.map(run_cell, jobs, chunksize=8))

    n_ep = a.seeds * len(opps)
    print("%d episodes per cell (%d seeds x %s)\n" % (n_ep, a.seeds, ",".join(opps)))
    print("  %6s %6s %6s %10s %8s %7s %7s %9s"
          % ("hands", "shed", "slots", "mean", "p10", "tiles", "lost", "idle%"))
    base = None
    for hand in hands:
        for shed in sheds:
            for slot in slots:
                cell = [r for r in rows if r["hands"] == hand and r["shed"] == shed
                        and r["slots"] == slot]
                banks = sorted(r["bank"] for r in cell)
                mean = sum(banks) / len(banks)
                p10 = banks[max(0, int(0.1 * len(banks)) - 1)]
                if base is None:
                    base = mean
                print("  %6d %6d %6d $%9.0f $%7.0f %7.1f %7.1f %8.1f%%   %+.0f"
                      % (hand, shed, slot, mean, p10,
                         sum(r["tiles"] for r in cell) / len(cell),
                         sum(r["lost"] for r in cell) / len(cell),
                         sum(r["idle"] for r in cell) / len(cell), mean - base))

    print("\nDeltas are against the first row, which is the shipping configuration.\n"
          "A bigger shed or a longer order book is NOT submittable -- they are engine constants.\n"
          "What is submittable is harvest scheduling and sell throughput, and the size of the\n"
          "gap here is the upper bound on what that work can be worth.")


if __name__ == "__main__":
    main_cli()
