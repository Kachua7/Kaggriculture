"""Engine ground truth vs the policy's market-monitor estimates.

The monitor (`kagfarm/policy.py::_MarketMonitor`) infers town drain, its scale and the
opponent's net supply from the public book. This script checks those estimates against
what the mirror engine ACTUALLY did, using two inert hooks:

  env._exec_hook        -- set to a Counter by this script; `engine._settle_one_unit`
                           increments it once per EXECUTED (seat, good, op) unit. An
                           order the engine refused (empty shed, broke farm) never counts,
                           which is the whole point: order *sizes* are not flows.
  KaggressiveEnv._town_tick wrap -- actual town subtractions per (day, good), unclamped
                           at the source so the book's max(0, .) floor cannot hide them.

    python3 analysis/monitor_truth.py --seed 9

Read the output as: monitor estimate vs engine truth, per good. The monitor's estimates
are permitted to differ within its documented bias controls (AGENTS.md, "Market monitor"):
the ±50/day clamp, the contamination band on `d`, and the closed-day shop list.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import main  # noqa: E402
from agents import BUILTIN_AGENTS  # noqa: E402
from engine import KaggricultureEnv  # noqa: E402
from kagfarm.policy import Policy  # noqa: E402

GOODS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON", "EGG", "MILK", "WOOL")


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=9)
    a = ap.parse_args()

    exec_hits = Counter()                      # (seat, good, op) -> executed units
    town = defaultdict(Counter)                # day -> {good: actual town subtraction}
    orig_tick = KaggricultureEnv._town_tick

    def town_tick(self):
        before = dict(self.market_inventory)
        orig_tick(self)
        for g, n in self.market_inventory.items():
            x = before.get(g, 0) - n
            if x:
                town[self.day][g] += x

    KaggricultureEnv._town_tick = town_tick
    try:
        main._POLICIES.clear()
        pol = Policy({"monitor": 1})
        opp = BUILTIN_AGENTS["self"]
        env = KaggressiveEnv = KaggricultureEnv(episode_steps=720, seed=a.seed)
        env._exec_hook = exec_hits
        obs = env._obs()
        while not env.done:
            obs, _ = env.step([pol.act(obs[0]), opp(obs[1])])
    finally:
        KaggricultureEnv._town_tick = orig_tick

    m = pol.mkt
    print("seed %d: we banked $%.0f, they banked $%.0f"
          % (a.seed, env.farms[0].money, env.farms[1].money))
    print("monitor: d=%.2f d_use=%.2f  diag tail=%s"
          % (m.d, m.d_use, m.diag[-3:]))
    print()
    print("%-11s | %13s %13s | %12s %12s" % ("good", "monitor opp/day", "truth opp/day",
                                             "truth we/day", "town drain/day"))
    print("-" * 70)
    for g in GOODS:
        o1 = exec_hits.get((1, g, "SELL"), 0)
        o0 = exec_hits.get((0, g, "SELL"), 0)
        b1 = exec_hits.get((1, g, "BUY_PRODUCT"), 0)
        b0 = exec_hits.get((0, g, "BUY_PRODUCT"), 0)
        drain = sum(town[d].get(g, 0) for d in town) / 30.0
        if o0 + o1 + b0 + b1 + drain == 0:
            continue
        est = m.opp.get(g)
        est_s = "%13.1f" % est if est is not None else "%13s" % "-"
        print("%-11s | %13s %13.1f | %12.1f %12.1f"
              % (g, est_s, (o1 - b1) / 30.0, (o0 - b0) / 30.0, drain))
    print()
    print("(estimates carry the monitor's documented bias controls; see AGENTS.md)")


if __name__ == "__main__":
    main_cli()
