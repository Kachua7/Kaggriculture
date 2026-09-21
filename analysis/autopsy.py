"""Autopsy of the bad seeds: why does act 2 never launch?

`mirror_tail.py` established the SHAPE of the mutual-adoption failure -- corr(mine, total)
= +0.86, so bad seeds are bad seasons, not lost races -- and its SIGNATURE: on the worst
quartile the farm sells 144 melon (the day-0 opening, identical on every seed), 2-3 wheat
and 28-44 strawberry all season, while the best quartile sells 150 melon, 245-432 wheat and
160-268 strawberry. The opening is not the problem; the post-melon scale-up (days 11-25) is
what never happens on a bad seed.

This script replays known-bad seeds next to known-good ones with `Policy._targets` and
`Policy._roster` instrumented, and prints one row per dawn:

    money   cash at dawn, before today's seed budget
    own     quadrants owned
    live    live plants on the board
    empty   empty unlocked tiles
    want    what the allocator decided to plant today (crop:count)
    limit   what stopped the allocator (tiles / cash / labour / cap / worthless / late)
    nhire   hands the roster wants; hands = hands actually on the board at hour 0+1
    eff     the pipeline-adjusted prices the allocator planted against

The differences between the columns are the mechanism. Everything else is commentary.

    python3 analysis/autopsy.py                     # 4 worst + 4 best seeds from mirror_tail
    python3 analysis/autopsy.py --seeds 9,13,17     # specific seeds
    python3 analysis/autopsy.py --days 12-22        # only mid-season dawns
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import KaggricultureEnv  # noqa: E402
from agents import BUILTIN_AGENTS  # noqa: E402
from kagfarm.policy import Policy  # noqa: E402

import main  # noqa: E402

# From analysis/mirror_tail.json (seeds 0-47, mutual adoption, sorted by bank).
WORST = (9, 24, 13, 17)
BEST = (36, 4, 26, 31)


def episode(seed, rows):
    """One mutual-adoption episode with the seat-0 planner instrumented."""
    t_orig = Policy._targets
    r_orig = Policy._roster

    def targets(self, tiles, unlocked, day, prices, money, seeds, inv, shed):
        live, empty = self._board_state(tiles, unlocked)
        want, plan = t_orig(self, tiles, unlocked, day, prices, money, seeds, inv, shed)
        eff = self.eff or {}
        rows.append(dict(kind="targets", day=day, money=money, own=25 * max(1, len(unlocked)),
                         live=sum(live.values()), empty=empty,
                         mix={c: live[c] for c in sorted(live) if live[c]},
                         want={c: n for c, n in sorted(want.items()) if n},
                         limit=self.limit, spend=self.seed_spend,
                         eff={g: round(eff.get(g, 0.0)) for g in ("MELON", "STRAWBERRY", "WHEAT", "CARROT")},
                         nshops=len(self.shops or [])))
        return want, plan

    def roster(self, tiles, unlocked, day, prices, me):
        n = r_orig(self, tiles, unlocked, day, prices, me)
        rows.append(dict(kind="roster", day=day, n_hire=n))
        return n

    Policy._targets = targets
    Policy._roster = roster
    try:
        opp = BUILTIN_AGENTS["self"]
        main._POLICIES.clear()
        env = KaggricultureEnv(episode_steps=720, seed=seed)
        obs = env._obs()

        land_day = {}
        shop_day = {}
        seen_q = set(env.farms[0].unlocked_quadrants)
        seen_s = set(env.shops)
        hands_by_day = defaultdict(int)
        while not env.done:
            obs, _ = env.step([main.agent(obs[0]), opp(obs[1])])
            for q in env.farms[0].unlocked_quadrants:
                if q not in seen_q:
                    seen_q.add(q)
                    land_day[q] = env.day
            for s in env.shops:
                if s not in seen_s:
                    seen_s.add(s)
                    shop_day[s] = env.day
            if env.hour == 1:                       # hands arrive over hours 0-4; sample at 1
                hands_by_day[env.day] = len(env.farms[0].hands)

        rows.append(dict(kind="final", seed=seed, bank=env.farms[0].money,
                         opp=env.farms[1].money, land_day=land_day, shop_day=shop_day))
        rows.append(dict(kind="hands", hands=dict(hands_by_day)))
        return env.farms[0].money, env.farms[1].money
    finally:
        Policy._targets = t_orig
        Policy._roster = r_orig


def show(seed, rows, dmin, dmax):
    final = next(r for r in rows if r.get("kind") == "final")
    hands = next(r for r in rows if r.get("kind") == "hands")["hands"]
    dawn = {r["day"]: r for r in rows if r.get("kind") == "targets"}
    hire = {r["day"]: r["n_hire"] for r in rows if r.get("kind") == "roster"}
    print("\n=== seed %-3d   me $%.0f   them $%.0f   pot $%.0f"
          % (seed, final["bank"], final["opp"], final["bank"] + final["opp"]))
    print("  land: " + "  ".join("%s d%d" % (q, d) for q, d in sorted(final["land_day"].items(),
                                                                   key=lambda kv: kv[1])))
    print("  shops: " + " ".join("%s:d%d" % (s.split("_")[0][:4], d)
                                 for s, d in sorted(final["shop_day"].items(), key=lambda kv: kv[1])))
    print("  %3s %7s %4s %4s %4s  %-34s %-16s %5s %5s  %s"
          % ("day", "money", "own", "live", "empt", "want (live mix)", "limit",
             "nhir", "hand", "eff MEL/STR/WHE/CAR"))
    for day in range(dmin, dmax + 1):
        r = dawn.get(day)
        if not r or "mix" not in r:
            continue
        live_s = ",".join("%s:%d" % (c[:2], n) for c, n in r["mix"].items())
        want_s = ",".join("%s:%d" % (c[:2], n) for c, n in r["want"].items()) or "-"
        e = r["eff"]
        print("  %3d %7.0f %4d %4d %4d  %-34s %-16s %5d %5s  %d/%d/%d/%d"
              % (day, r["money"], r["own"], r["live"], r["empty"],
                 (want_s + "  [" + live_s + "]")[:34], r["limit"],
                 hire.get(day, -1), hands.get(day, "?"),
                 e["MELON"], e["STRAWBERRY"], e["WHEAT"], e["CARROT"]))


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=None,
                    help="comma-separated; default = 4 worst + 4 best from mirror_tail")
    ap.add_argument("--days", default="0-29", help="dawn range to print, e.g. 12-22")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    dmin, dmax = (int(x) for x in a.days.split("-"))
    seeds = [int(s) for s in a.seeds.split(",")] if a.seeds else list(WORST) + list(BEST)

    out = {}
    for seed in seeds:
        rows = []
        mine, theirs = episode(seed, rows)
        out[seed] = rows
        show(seed, rows, dmin, dmax)

    print("\nsummary over %d seeds" % len(out))
    banks_all = sorted(
        (next(r for r in rows if r.get("kind") == "final")["bank"], s) for s, rows in out.items()
    )
    n = len(banks_all)
    if n:
        mean = sum(b for b, _ in banks_all) / n
        p10 = banks_all[max(0, n // 10) - 1][0] if n >= 10 else banks_all[0][0]
        print("  mean $%.0f   p10 $%.0f   min $%.0f (seed %d)   max $%.0f (seed %d)"
              % (mean, p10, banks_all[0][0], banks_all[0][1],
                 banks_all[-1][0], banks_all[-1][1]))

    if a.json:
        import json
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
        print("wrote %s" % a.json)


if __name__ == "__main__":
    main_cli()
