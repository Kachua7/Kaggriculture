"""What one unit of FERTILIZER is actually worth, per crop, measured on the engine.

`_refresh_plant` applies fertilizer in two ways and the second one is easy to miss:

    gain = 2 if fertilized else 1                  # units added per gain-day
    cap  = max_yield if fertilized else max_yield_unfert   # one_time crops only

For one_time crops the cap is the visible lever (wheat 6 vs 4). For ongoing crops there is no
`max_yield_unfert` at all, so reading the table suggests fertilizer does nothing for strawberry
-- but the doubled gain still applies, and `max_yield` caps *standing* units, not lifetime ones.
HARVEST on an ongoing crop sets `yield_units = 0` and leaves the plant alive, so a mid-cycle
harvest empties the tile and lets the doubled gains keep landing. Whether that is worth an extra
visit is a measurement, not an argument.

This probe drives a single tile through a full cycle four ways -- plain, fertilized, plain with
mid-cycle harvests, fertilized with mid-cycle harvests -- and reports units banked against
visits spent. The farmer is teleported onto the tile each turn so that walking costs nothing and
the numbers isolate the yield arithmetic.

    python3 analysis/fert_probe.py
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import KaggricultureEnv
from kagfarm.constants import CROP_PLAN, MARKET_PARAMS, OBJECT_TABLE, TURNS_PER_DAY

PASS = {"farmer": ["PASS"], "hands": [], "market": []}
TILE = (0, 0)


def _spec_days(crop):
    """The ages on which the engine can add yield to this crop."""
    spec = OBJECT_TABLE[crop]
    if spec["kind"] == "one_time":
        return list(range(spec["first_yield_day"], spec["max_yield_day"] + 1))
    return list(spec["sched_days"])


def run(crop, fertilize, midcycle, horizon=None):
    """Plant one tile of `crop` at day 0 and work it to the end of its cycle.

    Returns (units banked, tile-visits spent, fertilizer units spent).
    """
    spec = OBJECT_TABLE[crop]
    plan = CROP_PLAN[crop]
    water = set(plan["water_days"])
    gain_days = _spec_days(crop)
    cap = spec["max_yield"]
    last = plan["harvest_day"] if horizon is None else horizon

    env = KaggricultureEnv(episode_steps=720, seed=0)
    f = env.farms[0]
    f.seeds[crop] = 5
    f.shed["FERTILIZER"] = 40
    f.money = 10 ** 7

    banked = visits = fert = 0
    obs = env._obs()
    while not env.done and env.day <= last:
        f.farmer = list(TILE)
        day, hour = env.day, env.hour
        tile = f.tiles[TILE[1]][TILE[0]]
        op = ["PASS"]

        if tile is None and day == 0:
            op = ["PLANT", crop]
        elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
            age = day - tile["planted_day"]
            units = tile.get("yield_units", 0)
            covered = tile.get("fertilized_until_day", -1) >= day
            # Dose on the morning of a gain-day the current dose does not reach, and only then.
            # One dose runs day..day+3, so fertilizing earlier than the first gain-day wastes
            # it outright -- which is most of the difference between fertilizer looking like a
            # loss and looking like the best visit on the board.
            if fertilize and not covered and age in gain_days and hour == 0:
                op = ["FERTILIZE"]
                fert += 1
            elif age == last and units > 0:
                op = ["HARVEST"]
            # Mid-cycle harvest: bank what is standing before tonight's gain would be clipped
            # by the cap. Only ongoing crops survive their own harvest.
            elif (midcycle and spec["kind"] == "ongoing" and hour == TURNS_PER_DAY - 1
                    and units > 0 and age in gain_days
                    and units + (2 if covered else 1) > cap
                    and any(d > age for d in gain_days)):
                op = ["HARVEST"]
            elif age in water and not tile.get("watered_today"):
                op = ["WATER"]

        if op[0] != "PASS":
            visits += 1
        obs, _ = env.step([{"farmer": op, "hands": [], "market": []}, PASS])
        banked += sum(inv.get(crop, 0) for inv in f.inventories)
        for inv in f.inventories:
            inv.pop(crop, None)
        banked += f.shed.pop(crop, 0)

    return banked, visits, fert


def main():
    print("units banked / tile-visits spent, one tile, one cycle, minimum watering\n")
    print("%-11s %-18s %-18s %-18s %-18s" %
          ("crop", "plain", "+fert", "+midharvest", "+fert+mid"))
    rows = {}
    for crop in CROP_PLAN:
        cells = []
        for fz, mid in ((0, 0), (1, 0), (0, 1), (1, 1)):
            u, v, fr = run(crop, fz, mid)
            cells.append((u, v, fr))
            rows[(crop, fz, mid)] = (u, v, fr)
        print("%-11s " % crop + " ".join(
            "%-18s" % ("%du %dv %df" % c) for c in cells))

    print("\nvalue of the fertilized programme at base prices, per tile-cycle:")
    print("%-11s %-8s %-8s %-9s %-9s %-9s" %
          ("crop", "d units", "d visits", "fert $", "gross $", "net $/visit"))
    for crop in CROP_PLAN:
        u0, v0, _ = rows[(crop, 0, 0)]
        best = max(((1, 0), (1, 1), (0, 1)),
                   key=lambda k: rows[(crop, k[0], k[1])][0])
        u1, v1, f1 = rows[(crop, best[0], best[1])]
        base = MARKET_PARAMS[crop]["base"]
        gross = (u1 - u0) * base
        cost = f1 * MARKET_PARAMS["FERTILIZER"]["base"]
        dv = max(1, v1 - v0)
        print("%-11s %-8d %-8d %-9d %-9d %-9.0f  best=%s"
              % (crop, u1 - u0, v1 - v0, cost, gross, (gross - cost) / dv,
                 {(1, 0): "fert", (1, 1): "fert+mid", (0, 1): "mid"}[best]))


if __name__ == "__main__":
    main()
