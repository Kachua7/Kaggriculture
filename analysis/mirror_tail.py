"""The mirror's bad half: is the tail a property of the seed, or of the match?

Two copies of the shipped agent meet and the result is not a distribution, it is two
distributions. Mean $50,579, but the 10th percentile is $10,867 and the best case is $78,095.
Something on a large minority of seeds ends the season with one farm gutted, and the ladder is
scored per episode, so that tail is the score.

There are only two shapes this can have, and they want opposite fixes:

  SEED EFFECT -- both farms are poor on those seeds. The season itself is bad: the shop draw
    never opened a sink for what we grow, so there is less money on the table for anybody. The
    fix is to read the draw and grow something else. Nothing to do with the opponent.

  SYMMETRY BREAK -- the pot is normal size and one farm takes nearly all of it. Some early
    accident compounds: whoever gets a cohort to market first depresses the price the other one
    was counting on, which delays their land, which delays their next cohort. The fix is to stop
    being the loser of that race, which is a policy change and worth a great deal, because half
    of those episodes are currently being handed away.

The tell is `total = mine + theirs`. A seed effect moves the total; a symmetry break moves only
the split. This script measures the correlation between the two, then dumps the day-by-day
divergence for the worst seeds so the compounding step is visible rather than assumed.

Nothing here is contested except the order book. Boards, land prices, hire costs and shed
capacity are all per-farm -- verified in engine.py, where `unlocked_quadrants` hangs off `Farm`
and `market_inventory` hangs off the env. So any advantage one farm takes over the other has to
arrive through realized price, and the trajectory dump is built to show exactly that.

    python3 analysis/mirror_tail.py --seeds 48          # the shape question, fast
    python3 analysis/mirror_tail.py --seeds 144 --dump 4 # plus per-day traces of the worst
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kagfarm.constants import MARKET_PARAMS, SEASON_DAYS, TURNS_PER_DAY, price_for  # noqa: E402

GOODS_WATCH = ("MELON", "STRAWBERRY", "WHEAT", "MILK")


def episode(seed, trace=False):
    """One mutual-adoption episode. Returns terminal facts, and optionally a per-day trace.

    Both seats run the committed policy: seat 0 through `main.agent` exactly as Kaggle calls
    it, seat 1 through `agents.self`, which is pinned to the same on-disk PARAMS. Imports live
    inside the function so a pool worker cannot carry `main._POLICIES` across episodes.
    """
    import importlib
    from engine import KaggricultureEnv
    from agents import BUILTIN_AGENTS

    mod = importlib.import_module("main")
    importlib.reload(mod)
    opp = BUILTIN_AGENTS["self"]

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()

    # Realized revenue per seat, priced where a sale actually becomes real. Ordering more than
    # the shed holds is free and the agent does it deliberately, so counting ordered units
    # overstates revenue several-fold.
    rev = [defaultdict(float), defaultdict(float)]
    units = [defaultdict(int), defaultdict(int)]
    _settle = env._settle_one_unit

    def settle_one_unit(pi, resource, op, price=None):
        if op == "SELL" and env.farms[pi].shed.get(resource, 0) > 0:
            rev[pi][resource] += (price if price is not None
                                  else price_for(resource, env.market_inventory[resource]))
            units[pi][resource] += 1
        return _settle(pi, resource, op, price)

    env._settle_one_unit = settle_one_unit

    # Day each quadrant came off the lock, per seat. Land is private, but it is bought with
    # money that is not, so this is where a price disadvantage first becomes a capacity one.
    land_day = [{}, {}]
    seen = [set(f.unlocked_quadrants) for f in env.farms]

    rows = []
    day = 0
    while not env.done:
        obs, _ = env.step([mod.agent(obs[0]), opp(obs[1])])
        for pi, f in enumerate(env.farms):
            for q in f.unlocked_quadrants:
                if q not in seen[pi]:
                    seen[pi].add(q)
                    land_day[pi][q] = env.day
        if trace and env.day != day:
            day = env.day
            rows.append([
                day,
                int(env.farms[0].money), int(env.farms[1].money),
                len(env.farms[0].unlocked_quadrants), len(env.farms[1].unlocked_quadrants),
                len(env.farms[0].hands), len(env.farms[1].hands),
                int(sum(rev[0].values())), int(sum(rev[1].values())),
                {g: int(env.market_inventory[g]) for g in GOODS_WATCH},
            ])

    def px(pi, good):
        n = units[pi][good]
        return rev[pi][good] / n / MARKET_PARAMS[good]["base"] if n else 0.0

    out = dict(
        seed=seed,
        mine=env.farms[0].money, theirs=env.farms[1].money,
        total=env.farms[0].money + env.farms[1].money,
        land0=len(env.farms[0].unlocked_quadrants), land1=len(env.farms[1].unlocked_quadrants),
        land_day0=land_day[0], land_day1=land_day[1],
        hands0=len(env.farms[0].hands), hands1=len(env.farms[1].hands),
        px0={g: round(px(0, g), 3) for g in GOODS_WATCH},
        px1={g: round(px(1, g), 3) for g in GOODS_WATCH},
        u0={g: units[0][g] for g in GOODS_WATCH},
        u1={g: units[1][g] for g in GOODS_WATCH},
        shops=list(env.shops),
    )
    if trace:
        out["trace"] = rows
    return out


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs) or 1e-9
    syy = sum((b - my) ** 2 for b in ys) or 1e-9
    return sxy / (sxx * syy) ** 0.5


def _pct(vals, q):
    s = sorted(vals)
    return s[max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--dump", type=int, default=0, help="per-day trace for the N worst seeds")
    ap.add_argument("--json", default=os.path.join(_HERE, "mirror_tail.json"))
    a = ap.parse_args()

    res = [episode(s) for s in range(a.start, a.start + a.seeds)]
    res.sort(key=lambda r: r["mine"])

    mine = [r["mine"] for r in res]
    tot = [r["total"] for r in res]
    print("mutual adoption, seeds %d-%d" % (a.start, a.start + a.seeds - 1))
    print("  mine   mean %9.0f  p10 %8.0f  p50 %8.0f  p90 %8.0f" %
          (sum(mine) / len(mine), _pct(mine, .10), _pct(mine, .50), _pct(mine, .90)))
    print("  total  mean %9.0f  p10 %8.0f  p50 %8.0f  p90 %8.0f" %
          (sum(tot) / len(tot), _pct(tot, .10), _pct(tot, .50), _pct(tot, .90)))

    # THE SHAPE QUESTION. If my bank tracks the size of the pot, the bad seeds are bad seasons
    # and the opponent is incidental. If it tracks my share of it, they are lost races.
    share = [r["mine"] / r["total"] if r["total"] else 0.5 for r in res]
    print("\n  corr(mine, total) = %+.3f      <- high: bad SEEDS, the whole season is poor" %
          _pearson(mine, tot))
    print("  corr(mine, share) = %+.3f      <- high: lost RACES, the pot is normal size" %
          _pearson(mine, share))

    k = max(1, len(res) // 4)
    lo, hi = res[:k], res[-k:]

    def agg(rows, key):
        return sum(r[key] for r in rows) / len(rows)

    print("\n  %-22s %12s %12s" % ("bottom vs top quartile", "worst %d" % k, "best %d" % k))
    for lab, key in (("my bank", "mine"), ("opponent bank", "theirs"), ("pot", "total")):
        print("  %-22s %12.0f %12.0f" % (lab, agg(lo, key), agg(hi, key)))
    print("  %-22s %12.2f %12.2f" % ("my share of pot",
                                     agg(lo, "mine") / max(1, agg(lo, "total")),
                                     agg(hi, "mine") / max(1, agg(hi, "total"))))
    for lab, key in (("my quadrants", "land0"), ("their quadrants", "land1"),
                     ("my hands", "hands0"), ("their hands", "hands1")):
        print("  %-22s %12.2f %12.2f" % (lab, agg(lo, key), agg(hi, key)))

    # Land timing, which is where a price disadvantage turns into a capacity one.
    for q in ("NE", "SW", "SE"):
        def day_of(rows, k_):
            got = [r[k_].get(q) for r in rows if r[k_].get(q) is not None]
            return (sum(got) / len(got), len(got))
        (dl, nl), (dh, nh) = day_of(lo, "land_day0"), day_of(hi, "land_day0")
        print("  %-22s   day %5.1f (%2d/%d)  day %5.1f (%2d/%d)" %
              ("bought " + q, dl, nl, k, dh, nh, k))

    print("\n  realized price, fraction of base")
    print("  %-22s %12s %12s" % ("", "worst", "best"))
    for g in GOODS_WATCH:
        print("  %-22s %12.3f %12.3f" % (g.lower() + " (me)",
                                         agg(lo, "px0")[g] if False else
                                         sum(r["px0"][g] for r in lo) / k,
                                         sum(r["px0"][g] for r in hi) / k))
        print("  %-22s %12.1f %12.1f" % ("  units sold",
                                         sum(r["u0"][g] for r in lo) / k,
                                         sum(r["u0"][g] for r in hi) / k))

    out = {"cfg": vars(a), "rows": res}
    if a.dump:
        out["traces"] = []
        print("\n  per-day traces, %d worst seeds" % a.dump)
        for r in res[:a.dump]:
            t = episode(r["seed"], trace=True)
            out["traces"].append(t)
            print("\n  seed %d   me $%d  them $%d" % (r["seed"], t["mine"], t["theirs"]))
            print("   day |     my $     their $ | land  hands |    my rev  their rev | melon inv")
            for row in t["trace"]:
                d, m0, m1, l0, l1, h0, h1, r0, r1, inv = row
                if d % 2 and d not in (1, 29):
                    continue
                print("   %3d | %9d %9d | %d/%d  %d/%d | %9d %9d | %5d" %
                      (d, m0, m1, l0, l1, h0, h1, r0, r1, inv["MELON"]))

    with open(a.json, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print("\nwrote %s" % a.json)


if __name__ == "__main__":
    main()
