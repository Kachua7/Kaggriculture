"""Shed occupancy and destroyed items, day by day, for two configurations.

Exists because `eval.py` reports `lost` as one number for the season, and one number cannot
tell you that 74 of 75 destroyed items die in a single midnight dump on day 28 -- which is the
whole difference between a spoilage problem worth tuning and a one-turn logistics bug worth
fixing. Run it after any change to the haul or endgame parameters.

    PYTHONPATH=. python3 analysis/shed_probe.py [n_seeds]

Occupancy is sampled at hour 23, i.e. immediately before `_day_refresh` dumps every unit's bag
into the shed -- so the printed number plus the bags is what `_add_shed` is about to be asked
to hold, and anything over `SHED_CAPACITY` is destroyed.
"""
from __future__ import annotations

import statistics as st
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from engine import KaggricultureEnv                                    # noqa: E402
from kagfarm.constants import SHED_CAPACITY, TURNS_PER_DAY             # noqa: E402


def one(seed, opp_name, over):
    import importlib

    from agents import BUILTIN_AGENTS
    from kagfarm import policy as _policy

    base = dict(_policy.PARAMS)
    _policy.PARAMS.update(over)
    mod = importlib.import_module("main")
    importlib.reload(mod)
    opp = BUILTIN_AGENTS[opp_name]

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    me = env.farms[0]

    lost_by_day = defaultdict(int)
    occ = {}
    carried = {}
    _add = env._add_shed

    def add_shed(f, item, n):
        got = _add(f, item, n)
        if f is me:
            lost_by_day[env.t // TURNS_PER_DAY] += max(0, n - got)
        return got

    env._add_shed = add_shed
    try:
        while not env.done:
            day, hour = env.t // TURNS_PER_DAY, env.t % TURNS_PER_DAY
            if hour == TURNS_PER_DAY - 1:
                occ[day] = sum(me.shed.values())
                carried[day] = sum(sum(i.values()) for i in me.inventories)
            obs, _ = env.step([mod.agent(obs[0]), opp(obs[1])])
        bank = me.money
    finally:
        _policy.PARAMS.clear()
        _policy.PARAMS.update(base)
    return bank, occ, carried, dict(lost_by_day)


def panel(over, seeds, opps=("starter", "heuristic", "random")):
    banks, occ, carr, lost = [], defaultdict(list), defaultdict(list), defaultdict(list)
    for s in range(seeds):
        for o in opps:
            b, oc, ca, lo = one(s, o, over)
            banks.append(b)
            for d, v in oc.items():
                occ[d].append(v)
            for d, v in ca.items():
                carr[d].append(v)
            for d in range(30):
                lost[d].append(lo.get(d, 0))
    return (st.mean(banks),
            {d: st.mean(v) for d, v in occ.items()},
            {d: st.mean(v) for d, v in carr.items()},
            {d: st.mean(v) for d, v in lost.items()})


def main():
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    cfgs = [("before", dict(haul_trigger=999.0, endgame_days=2)),
            ("after", {})]
    out = {}
    for name, over in cfgs:
        out[name] = panel(over, seeds)
        print(f"{name:>7}  mean bank ${out[name][0]:,.0f}   "
              f"destroyed {sum(out[name][3].values()):.1f}/episode")

    print(f"\nshed at hour 23 + bags still in the field, mean over {seeds * 3} episodes "
          f"(cap {SHED_CAPACITY})")
    print(f"{'day':>4} | {'before: shed':>12} {'bags':>6} {'destroyed':>10} "
          f"| {'after: shed':>11} {'bags':>6} {'destroyed':>10}")
    for d in range(30):
        b_o, b_c, b_l = (out["before"][1].get(d, 0), out["before"][2].get(d, 0),
                         out["before"][3].get(d, 0))
        a_o, a_c, a_l = (out["after"][1].get(d, 0), out["after"][2].get(d, 0),
                         out["after"][3].get(d, 0))
        print(f"{d:>4} | {b_o:>12.1f} {b_c:>6.1f} {b_l:>10.1f} "
              f"| {a_o:>11.1f} {a_c:>6.1f} {a_l:>10.1f}")

    print("\ncsv for the roadmap page: day,before_shed,before_bags,before_lost,"
          "after_shed,after_bags,after_lost")
    for d in range(30):
        print(f"{d},{out['before'][1].get(d, 0):.1f},{out['before'][2].get(d, 0):.1f},"
              f"{out['before'][3].get(d, 0):.1f},{out['after'][1].get(d, 0):.1f},"
              f"{out['after'][2].get(d, 0):.1f},{out['after'][3].get(d, 0):.1f}")


if __name__ == "__main__":
    main()
