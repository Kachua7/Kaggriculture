"""Animal-funnel on the REAL tier (vendored kaggle-environments).

This is where H4 actually bit: ladder replays showed 2 cows bought, 0 feeds, 0 product
sales. The mirror probe (animal_funnel.py) can't certify the fix because the bug was a
mirror divergence. Run:

    python3 analysis/animal_funnel_real.py [seed ...] [opponent]
"""

import importlib
import os
import sys
import time
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from bridge.real_env import RealEnv, _wrap_sells  # noqa: E402
from agents import BUILTIN_AGENTS  # noqa: E402


def run(seed: int, opp_name: str) -> dict:
    import main as agent_mod
    mod = importlib.reload(agent_mod)

    env = RealEnv(seed)
    opp = BUILTIN_AGENTS[opp_name]
    me_farm = env.state[0].observation.farms[0]

    revenue = defaultdict(float)
    units = defaultdict(int)
    _wrap_sells.farms = [env.state[0].observation.farms[0],
                         env.state[1].observation.farms[1]]
    _wrap_sells(env.eng, 0, revenue, units)

    ops_count = Counter()
    peak_animals = 0
    while not env.done:
        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)
        act0 = mod.agent(obs0, env.config)
        act1 = opp(obs1)

        for op in [act0.get("farmer") or ["PASS"]] + list(act0.get("hands") or []):
            if op and op[0] in ("BUY_ANIMAL", "PLACE", "FEED", "PICKUP"):
                ops_count[op[0]] += 1
        for op in act0.get("market") or []:
            if op and op[0] == "BUY_ANIMAL":
                ops_count["BUY_ANIMAL"] += 1
        live = sum(1 for row in me_farm["tiles"] for t_ in row
                   if isinstance(t_, dict) and t_.get("kind") in ("COOP", "PASTURE")
                   and t_.get("animal"))
        peak_animals = max(peak_animals, live)
        env.step([act0, act1])

    banks = env.banks()
    shed = env.state[0].observation.private.get("shed", {})
    animals_in_shed = {k: v for k, v in shed.items() if k in ("COW", "SHEEP", "GOOSE")}
    return dict(
        seed=seed, opp=opp_name,
        bank=banks[0], opp_bank=banks[1],
        buys=ops_count["BUY_ANIMAL"], places=ops_count["PLACE"], feeds=ops_count["FEED"],
        peak_structures=peak_animals,
        shed_animals=animals_in_shed,
        product_rev={k: round(v) for k, v in revenue.items()
                     if k in ("EGG", "MILK", "WOOL")},
        product_units={k: units[k] for k in ("EGG", "MILK", "WOOL") if units[k]},
    )


def main() -> None:
    args = [a for a in sys.argv[1:]]
    opp = "arch_passive"
    seeds = [0, 1, 2]
    if args and args[-1] in BUILTIN_AGENTS:
        opp = args.pop()
    if args:
        seeds = [int(a) for a in args]
    for s in seeds:
        r = run(s, opp)
        verdict = ("ALIVE" if r["product_units"] else "DEAD") + \
            ("" if not r["shed_animals"] else f"  <-- ROT: {r['shed_animals']}")
        print(f"seed {r['seed']} vs {r['opp']:16s} bank {r['bank']:>9,.0f} / {r['opp_bank']:>9,.0f} | "
              f"buy {r['buys']:>2} place {r['places']:>2} feed {r['feeds']:>3} "
              f"peak {r['peak_structures']} | rev {r['product_rev']} units {r['product_units']} "
              f"[{verdict}]")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"({time.time() - t0:.0f}s)")
