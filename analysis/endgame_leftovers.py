"""Endgame leftovers audit: how many dollars score zero at turn 720?

Score = bank at turn 720; unsold shed stock and standing crops are worth nothing. The
`endgame_days=5` liquidation was tuned on banks and never on the leftover itself — this
closes that loop by measuring the three leftovers directly, per episode:

  shed_$     unsold units sitting in the shed at the final whistle
  board_$    live plants still on the board, priced as would-be units at the final book
  lost       units the shed discarded for being over capacity (season total)

If shed_$ + board_$ is tens of dollars against a $50k+ bank, the endgame-shaping axis is
closed with data; if it is thousands, the liquidation schedule is leaving money dead.

    python3 analysis/endgame_leftovers.py                 # 48 seeds vs self_live + starter
    python3 analysis/endgame_leftovers.py --seeds 96 --opps self_live
"""

from __future__ import annotations

import argparse
import sys
import os
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _one(seed, opp_name, params):
    """One episode with leftovers instrumented. Mirrors eval.run_one's hooks."""
    from engine import KaggricultureEnv
    from agents import BUILTIN_AGENTS
    from kagfarm import policy as _policy
    from kagfarm.constants import price_for, CROP_PLAN

    if params:
        _policy.PARAMS.update(params)
    import main
    import importlib
    importlib.reload(main)
    opp = BUILTIN_AGENTS[opp_name]

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    me = env.farms[0]

    lost = {"n": 0}
    _add = env._add_shed

    def add_shed(f, item, n):
        got = _add(f, item, n)
        if f is me:
            lost["n"] += max(0, n - got)
        return got

    env._add_shed = add_shed

    while not env.done:
        obs, _ = env.step([main.agent(obs[0]), opp(obs[1])])

    # -- leftovers, priced at the final book -------------------------------------
    shed_val = 0.0
    for item, n in (me.shed or {}).items():
        if n and item in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                          "EGG", "MILK", "WOOL"):
            shed_val += n * price_for(item, env.market_inventory.get(item, 10000))

    board_val = 0.0
    for row in me.tiles:
        for tile in row:
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                crop = tile.get("crop")
                plan = CROP_PLAN.get(crop)
                if plan is None:
                    continue
                age = env.day - tile.get("planted_day", env.day)
                would_be = tile.get("yield_units", 0) + max(0, plan["harvest_day"] - age)
                board_val += would_be * price_for(crop, env.market_inventory.get(crop, 10000))

    return dict(bank=me.money, opp_bank=env.farms[1].money, shed=shed_val, board=board_val,
                lost=lost["n"])


def _pct(sorted_vals, p):
    return sorted_vals[max(0, int(p * len(sorted_vals)) - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--opps", nargs="*", default=["self_live", "starter"])
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    from concurrent.futures import ProcessPoolExecutor
    jobs = [(s, o, None) for o in args.opps for s in range(args.seeds)]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_one, [j[0] for j in jobs], [j[1] for j in jobs],
                           [j[2] for j in jobs]))

    by_opp = defaultdict(list)
    per = args.seeds
    for i, o in enumerate(args.opps):
        by_opp[o] = rows[i * per:(i + 1) * per]

    for o, rs in by_opp.items():
        banks = sorted(r["bank"] for r in rs)
        sheds = sorted(r["shed"] for r in rs)
        boards = sorted(r["board"] for r in rs)
        lost = sum(r["lost"] for r in rs)
        left = sorted(r["shed"] + r["board"] for r in rs)
        n = len(rs)
        print(f"== {o}  (n={n})")
        print(f"  bank       mean ${sum(banks)/n:>10,.0f}   p10 ${_pct(banks, .10):>9,.0f}"
              f"   min ${banks[0]:>9,.0f}")
        print(f"  shed_$     mean ${sum(sheds)/n:>10,.0f}   p10 ${_pct(sheds, .10):>9,.0f}"
              f"   max ${sheds[-1]:>9,.0f}")
        print(f"  board_$    mean ${sum(boards)/n:>10,.0f}   p10 ${_pct(boards, .10):>9,.0f}"
              f"   max ${boards[-1]:>9,.0f}")
        print(f"  leftover   mean ${sum(left)/n:>10,.0f}   p10 ${_pct(left, .10):>9,.0f}"
              f"   max ${left[-1]:>9,.0f}   lost-units {lost}")


if __name__ == "__main__":
    main()
