"""Capture and validate the opening book (days 0..N-1 donor scripts).

The book is our own best play, recorded. A donor episode's first `--until` days are
written as per-day variants keyed by `opening_book_signature` (public shop unlocks +
our own money/shed/seed totals at that day's dawn). At runtime, an episode whose dawn
signature matches a donor variant serves the donor's recorded moves for that day; any
miss halts the book for the day and the normal planner takes over mid-day.

Why signatures rather than seed hashes: the ladder's opponents are unknown, so a
replay "tape" keyed on engine seed can never engage there. Signature matching engages
whenever OUR opening state is on a donor path regardless of the opponent, which is
exactly the fragile, decision-dense opening we want protected.

Usage:
    python3 analysis/capture_book.py --seeds 0-15 --opps starter,heuristic \
        --until 6 --out kagfarm/opening_book.json --validate 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import KaggricultureEnv  # noqa: E402
import main  # noqa: E402
from kagfarm.policy import Policy, engine_verdict, opening_book_signature  # noqa: E402


def capture_episode(seed, opp_name, until_day):
    """One donor episode -> list of per-day {"sig": [...], "hours": [...]} variants."""
    from agents import BUILTIN_AGENTS
    opp = BUILTIN_AGENTS[opp_name]
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    main._POLICIES.clear()
    days = {}
    while not env.done:
        day = obs[0]["day"]
        act = main.agent(obs[0])
        if day < until_day:
            d = days.setdefault(day, {"sig": None, "hours": []})
            if d["sig"] is None:                      # first observed turn of the day
                d["sig"] = list(opening_book_signature(obs[0]))
            d["hours"].append([list(act["farmer"]),
                               [list(h) for h in act["hands"]],
                               [list(m) for m in act["market"]]])
        obs, _ = env.step([act, opp(obs[1])])
    return [days[d] for d in sorted(days)]


def build(seeds, opps, until_day):
    """Run all donor episodes and merge into the book, deduped by signature."""
    book = {d: [] for d in range(until_day)}
    seen = {d: set() for d in book}
    for seed in seeds:
        for opp_name in opps:
            for day, v in enumerate(capture_episode(seed, opp_name, until_day)):
                key = json.dumps(v["sig"], sort_keys=True)
                if key in seen[day]:
                    continue
                seen[day].add(key)
                book[day].append(v)
    return book


def _validate_one(path, seed, opp_name, until_day):
    """Re-serve one donor episode; the served opening must match the live planner.

    The live planner on the same seed/opponent reproduces the donor moves by
    construction, so served == live over the recorded days means the book round-trips
    without drift: right variant chosen, right moves replayed, planner in sync.
    """
    from agents import BUILTIN_AGENTS
    opp = BUILTIN_AGENTS[opp_name]
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    main._POLICIES.clear()
    pol = Policy({"opening_book": 1, "book_file": path})
    while not env.done:
        served = pol.act(obs[0])
        if obs[0]["day"] < until_day:
            live = main.agent(obs[0])
            if served != live:
                print(f"    drift at day {obs[0]['day']} hour {obs[0]['hour']}:")
                print("      served", served)
                print("      live  ", live)
                return False
        obs, _ = env.step([served, opp(obs[1])])
    return True


def main_cli():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", default="0-15", help="donor seeds, e.g. 0-15 or 1,3,5")
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--until", type=int, default=6, help="days to record (0-based)")
    ap.add_argument("--out", default="kagfarm/opening_book.json")
    ap.add_argument("--validate", type=int, default=2,
                    help="re-serve this many donor seeds x opps; require exact replay")
    a = ap.parse_args()

    def parse_seeds(s):
        out = []
        for part in s.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                out.extend(range(int(lo), int(hi) + 1))
            else:
                out.append(int(part))
        return out

    seeds = parse_seeds(a.seeds)
    opps = a.opps.split(",")
    print(f"capturing {len(seeds)} seeds x {len(opps)} opponents, days 0..{a.until - 1}")
    book = build(seeds, opps, a.until)
    for d in sorted(book):
        print(f"  day {d}: {len(book[d])} distinct opening variants")
    payload = {
        "meta": {
            "donor_seeds": seeds,
            "donor_opps": opps,
            "until_day": a.until,
            "engine_verdict": engine_verdict(),
        },
        "days": {str(d): book[d] for d in sorted(book)},
    }
    with open(a.out, "w") as f:
        json.dump(payload, f)
    print(f"wrote {a.out} ({os.path.getsize(a.out)} bytes)")

    if a.validate:
        bad = 0
        for seed in seeds[:a.validate]:
            for opp_name in opps:
                ok = _validate_one(a.out, seed, opp_name, a.until)
                bad += not ok
                print(f"  validate seed {seed} vs {opp_name}: "
                      f"{'EXACT' if ok else 'DRIFT'}")
        if bad:
            print("!! validation failed -- book is not in a shippable state")
            sys.exit(1)


if __name__ == "__main__":
    main_cli()
