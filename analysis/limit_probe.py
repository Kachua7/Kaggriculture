"""Which resource ends the dawn tile allocation, per day, over a seed panel.

`_targets` allocates empty tiles one at a time to the best marginal crop and stops when it runs
out of something. Terminal bank cannot say *what* it ran out of, and that one fact decides which
lever is worth pulling next: a farm that stops on `cash` wants seed financing, one that stops on
`labour` wants hands or a better route, one that stops on `cap` wants its mix widened, and one
that stops on `tiles` wants land. The agent averages 48 live tiles a day on a 100-tile board with
strawberry realizing 204% of base, so there is either acreage headroom worth roughly $1.5k a tile
or a binding constraint that explains why there is not. This tells them apart.

`Policy.limit` records the veto set from the pass that actually failed. Everything else here is
recomputed from the same expressions `_targets` uses, so a divergence between the two is a bug in
this file rather than a finding.

    python3 analysis/limit_probe.py                 # 8 seeds, aggregate + seed 0 trace
    python3 analysis/limit_probe.py --seeds 24 --no-trace
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import KaggricultureEnv
from agents import BUILTIN_AGENTS
from kagfarm.constants import SEASON_DAYS, crop_actions_per_day
from kagfarm.policy import Policy
from kagfarm.route import capacity

import main


def instrument(rows):
    """Wrap `Policy._targets` to record, per dawn, what it saw and what stopped it."""
    original = Policy._targets

    def targets(self, tiles, unlocked, day, prices, money, seeds, inv, shed):
        live, empty = self._board_state(tiles, unlocked)
        want, plan = original(self, tiles, unlocked, day, prices, money, seeds, inv, shed)
        commute = 3.0 + 1.5 * max(0, len(unlocked) - 1)
        visits = (1 + self.p["max_hands"]) * max(1, capacity(commute)) * self.p["labour_slack"]
        load = sum(live[c] * crop_actions_per_day(c) for c in live)
        rows.append(dict(
            day=day, limit=self.limit, owned=25 * max(1, len(unlocked)),
            live=sum(live.values()), empty=empty, planted=sum(want.values()),
            money=money, budget=max(0.0, money - self.wage_reserve), spend=self.seed_spend,
            load=load, visits=visits, headroom=visits - load,
            mix={c: live[c] for c in live},
        ))
        return want, plan

    Policy._targets = targets
    return original


def play(seed, opp_name, rows):
    opp = BUILTIN_AGENTS[opp_name]
    main._POLICIES.clear()
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    while not env.done:
        obs, _ = env.step([main.agent(obs[0]), opp(obs[1])])
    for r in rows:
        r.setdefault("seed", seed)
    return env.farms[0].money


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--opp", default="starter")
    ap.add_argument("--no-trace", action="store_true")
    a = ap.parse_args()

    all_rows = []
    banks = []
    for seed in range(a.seeds):
        rows = []
        instrument(rows)
        banks.append(play(seed, a.opp, rows))
        for r in rows:
            r["seed"] = seed
        all_rows += rows

    if not a.no_trace:
        first = [r for r in all_rows if r["seed"] == 0]
        print("seed 0 dawn-by-dawn (bank $%.0f)\n" % banks[0])
        print("  day  owned  live  empty  plant   cash   budget  spend   load/visits  limit")
        for r in first:
            print("  %3d  %5d  %4d  %5d  %5d  %6.0f  %7.0f  %5.0f  %5.1f/%5.1f   %s"
                  % (r["day"], r["owned"], r["live"], r["empty"], r["planted"], r["money"],
                     r["budget"], r["spend"], r["load"], r["visits"], r["limit"]))

    print("\nlimit reason by season third, share of dawns (%d seeds x %s)" % (a.seeds, a.opp))
    thirds = defaultdict(Counter)
    for r in all_rows:
        thirds[min(2, r["day"] * 3 // SEASON_DAYS)][r["limit"]] += 1
    reasons = sorted({r["limit"] for r in all_rows})
    print("  %-22s %8s %8s %8s" % ("reason", "days 0-9", "10-19", "20-29"))
    for reason in reasons:
        cells = []
        for third in range(3):
            n = sum(thirds[third].values()) or 1
            cells.append(100.0 * thirds[third][reason] / n)
        print("  %-22s %7.0f%% %7.0f%% %7.0f%%" % (reason or "(none)", *cells))

    print("\nmeans by season third")
    print("  %-8s %6s %6s %6s %7s %8s %9s" % ("third", "owned", "live", "empty", "plant",
                                              "budget", "headroom"))
    for third in range(3):
        rs = [r for r in all_rows if min(2, r["day"] * 3 // SEASON_DAYS) == third]
        n = len(rs) or 1
        print("  %-8s %6.1f %6.1f %6.1f %7.1f %8.0f %9.1f"
              % (("0-9", "10-19", "20-29")[third],
                 sum(r["owned"] for r in rs) / n, sum(r["live"] for r in rs) / n,
                 sum(r["empty"] for r in rs) / n, sum(r["planted"] for r in rs) / n,
                 sum(r["budget"] for r in rs) / n, sum(r["headroom"] for r in rs) / n))

    print("\nbank mean $%.0f over %d seeds" % (sum(banks) / len(banks), len(banks)))


if __name__ == "__main__":
    main_cli()
