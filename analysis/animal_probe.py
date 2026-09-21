"""What one animal tile is worth per visit, measured on the engine.

Livestock is the only production class the agent does not touch, and the reason to look at it
is not the product -- it is `_refresh_animal`:

    tile["fertilizer_available"] = True     # every day, regardless of fed/cared

One FERTILIZER a day, per animal, unconditionally. The agent currently buys about 90 doses a
season at roughly $100 each, and the fertilizer programme is worth $7k, so the byproduct alone
may pay for the animal.

The product arithmetic has one non-obvious lever. `_refresh_animal` gives `base_gain = 1` on a
production day whether or not the animal was fed; feeding only matters because

    if fed and cared:  pending_care_bonus += 1        # on NON-production days

and that bonus lands on the next production day, again only if fed. So a SHEEP (interval 3)
can bank 1 + 2 = 3 units every three days instead of 1, at the cost of two CARE visits. Missing
two consecutive feeds loses the animal outright and unrecoverably, which puts a hard floor of
one FEED every other day on any programme that keeps the animal at all.

Four programmes per animal, each on a single tile for a full season, with the unit teleported
onto the tile so that walking costs nothing and the numbers isolate the yield arithmetic:

  keep      feed every other day, harvest when full. The cheapest way to hold the animal.
  feed      feed daily, harvest when full. No care.
  care      feed daily, care on non-production days, harvest before the cap clips a gain.
  care+fert as care, plus COLLECT_FERTILIZER every day it is available.

    python3 analysis/animal_probe.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import KaggricultureEnv
from kagfarm.constants import (ANIMAL_PRODUCT, ANIMAL_STRUCTURE, MARKET_PARAMS, OBJECT_TABLE,
                               SEASON_DAYS, TURNS_PER_DAY)

PASS = {"farmer": ["PASS"], "hands": [], "market": []}
TILE = (0, 0)

# What the farm gives up to feed an animal: WHEAT it would otherwise have sold. Realized wheat
# is about 162% of base on the eval panel, so the feed bill is not the $25 sticker.
WHEAT_COST = MARKET_PARAMS["WHEAT"]["base"] * 1.62


def is_production_day(animal, age):
    spec = OBJECT_TABLE[animal]
    first, interval = spec["first_yield_day"], spec["interval"]
    return age >= first and (age - first) % interval == 0


def run(animal, feed_daily=True, care=False, collect=False):
    """One structure tile, one animal, a full season. Returns a metrics dict."""
    spec = OBJECT_TABLE[animal]
    product = ANIMAL_PRODUCT[animal]
    build = "BUILD_COOP" if ANIMAL_STRUCTURE[animal] == "COOP" else "BUILD_PASTURE"
    cap = spec["max_held"]

    env = KaggricultureEnv(episode_steps=720, seed=0)
    f = env.farms[0]
    f.money = 10 ** 7
    f.shed["WHEAT"] = 900
    f.shed[animal] = 1

    got = {product: 0, "FERTILIZER": 0}
    visits = wheat0 = 0
    wheat0 = f.shed["WHEAT"]
    escaped = None

    while not env.done:
        f.farmer = list(TILE)
        tile = f.tiles[TILE[1]][TILE[0]]
        day, hour = env.day, env.hour
        op = ["PASS"]

        if tile is None:
            op = [build]
        elif tile.get("animal") is None and escaped is None and (
                f.shed.get(animal, 0) or f.inventories[0].get(animal, 0)):
            # BUY_ANIMAL lands the animal in the shed; PLACE takes it from the unit's
            # inventory, so it has to be picked up first. Two visits, once per animal --
            # and the PICKUP empties the shed, so the guard has to look at both places.
            op = ["PICKUP", animal, 1] if not f.inventories[0].get(animal) else ["PLACE", animal]
        elif tile.get("animal") is None:
            if escaped is None and day > 0:
                escaped = day
        else:
            age = day - tile["placed_day"]
            prod = is_production_day(animal, age)
            units = tile.get("yield_units", 0)
            # Harvest before tonight's gain would be clipped by max_held, and on the last day.
            gain = 1 + (tile.get("pending_care_bonus", 0) if tile["fed_today"] else 0)
            must_harvest = units > 0 and (day >= SEASON_DAYS - 1
                                          or (prod and units + gain > cap))
            need_feed = not tile["fed_today"] and (feed_daily
                                                   or tile.get("consecutive_unfed", 0) >= 1)
            if must_harvest and hour >= TURNS_PER_DAY - 3:
                op = ["HARVEST"]
            elif need_feed and f.shed.get("WHEAT", 0) > 0:
                op = ["FEED"]
            elif collect and tile.get("fertilizer_available"):
                op = ["COLLECT_FERTILIZER"]
            elif care and not prod and not tile["cared_today"] and tile["fed_today"]:
                op = ["CARE"]
            elif units >= cap:
                op = ["HARVEST"]

        if op[0] != "PASS":
            visits += 1
        env.step([{"farmer": op, "hands": [], "market": []}, PASS])
        for inv in f.inventories:
            for g in list(inv):
                if g in got:
                    got[g] += inv.pop(g)
        for g in list(f.shed):
            if g in got and g != animal:
                got[g] += f.shed.pop(g)

    wheat = wheat0 - f.shed.get("WHEAT", 0)
    return dict(units=got[product], fert=got["FERTILIZER"], visits=visits,
                wheat=wheat, escaped=escaped)


def main():
    print("one structure tile, one animal, full season, unit teleported onto the tile\n")
    print("%-7s %-10s %5s %5s %6s %6s  %8s %8s %8s  %9s"
          % ("animal", "programme", "prod", "fert", "visits", "wheat",
             "product $", "fert $", "feed $", "net $/visit"))
    rows = {}
    for animal in ("GOOSE", "COW", "SHEEP"):
        product = ANIMAL_PRODUCT[animal]
        pbase = MARKET_PARAMS[product]["base"]
        fbase = MARKET_PARAMS["FERTILIZER"]["base"]
        buy = OBJECT_TABLE[animal]["buy_cost"]
        for tag, kw in (("keep", dict(feed_daily=False)),
                        ("keep+fert", dict(feed_daily=False, collect=True)),
                        ("feed", dict()),
                        ("care", dict(care=True)),
                        ("care+fert", dict(care=True, collect=True))):
            r = run(animal, **kw)
            rows[(animal, tag)] = r
            gross = r["units"] * pbase
            fert = r["fert"] * fbase
            feed = r["wheat"] * WHEAT_COST
            net = gross + fert - feed - buy
            r["net"] = net
            print("%-7s %-10s %5d %5d %6d %6d  %8.0f %8.0f %8.0f  %9.1f%s"
                  % (animal, tag, r["units"], r["fert"], r["visits"], r["wheat"],
                     gross, fert, feed, net / max(1, r["visits"]),
                     "  ESCAPED d%d" % r["escaped"] if r["escaped"] else ""))
        print()

    print("for scale, the crops the allocator actually plants, at realized (not base) price:")
    print("  MELON       4 units / 10 visits @ $203 realized ->  $81/visit")
    print("  STRAWBERRY  4 units / 11 visits @ $252 realized ->  $95/visit")
    print("  ...and a PASS costs a wage and returns $0/visit, which is the real comparison")
    print("  if the roster has slack.\n")

    # The two halves of an animal price completely differently, and the table above hides that
    # by averaging them. Split them: what does the collect programme add over the same
    # programme without it?
    print("marginal value of the COLLECT_FERTILIZER visits alone (keep+fert minus keep):")
    for animal in ("GOOSE", "COW", "SHEEP"):
        a, b = rows[(animal, "keep")], rows[(animal, "keep+fert")]
        dv = b["visits"] - a["visits"]
        dn = b["net"] - a["net"]
        print("  %-7s +%2d visits  +$%5.0f  ->  $%5.1f/visit" % (animal, dv, dn, dn / max(1, dv)))
    print("\nand the animal-keeping half on its own (the 'keep' row): the price of standing")
    print("access to that fertilizer, which cannot be bought separately.")


if __name__ == "__main__":
    main()
