"""
How many actions does a tile actually cost per day, and how many tiles can one hand keep?

`portfolio.py` charges "~2 actions per tile-day" as a placeholder. That number sets the hand
count, and through it the whole question of whether 100 tiles is even servicable. So measure
it instead of assuming it.

The measurement that matters is the MINIMUM watering schedule. Two engine rules pull in
opposite directions:

  survival   a plant dies when consecutive_unwatered reaches 2, so watering every OTHER day
             keeps it alive indefinitely
  growth     yield only increases on a night the tile was watered AND the age is inside the
             crop's gain window (one_time: first_yield_day..max_yield_day; ongoing: the
             sched_days list)

Outside the gain window, watering buys nothing but survival. Melon's window is ages 10-12 of
a 13-day cycle, so eight of its twelve watering days are pure overhead -- if the rule reads
the way it looks. This probe finds the minimum schedule by DELETING days one at a time and
re-running the engine, so the answer is measured against `_refresh_plant` rather than derived
from reading it.

Run: python3 analysis/labour_probe.py
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import KaggricultureEnv, OBJECT_TABLE
from kagfarm.constants import (TURNS_PER_DAY, SEASON_DAYS, BOARD_SIZE, SHED_TILES,
                               FARMER_START, fib_hire_cost, CROP_PLAN,
                               tile_visits_per_unit_day)

CROPS = ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")
PASS = {"farmer": ["PASS"], "hands": [], "market": []}


def run_schedule(crop, water_days, harvest_day, n_harvests=1):
    """Units banked from ONE tile, watering only on the days in `water_days`.

    The farmer plants at FARMER_START, which is also a shed tile and where the engine
    respawns it every dawn -- so the tile is under the farmer's feet on every day of the
    cycle and the probe measures growth with zero movement mixed in.
    """
    days = harvest_day + 1
    env = KaggricultureEnv(episode_steps=days * TURNS_PER_DAY, seed=7)
    wd = set(water_days)
    while not env.done:
        step = env.t
        day, hour = step // TURNS_PER_DAY, step % TURNS_PER_DAY
        if step == 0:
            act = {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", crop, 1]]}
        elif step == 1:
            act = {"farmer": ["PLANT", crop], "hands": [], "market": []}
        elif day == harvest_day and hour == 23:
            act = {"farmer": ["HARVEST"], "hands": [], "market": []}
        elif hour == 2 and day in wd:
            act = {"farmer": ["WATER"], "hands": [], "market": []}
        else:
            act = PASS
        env.step([act, PASS])
    f = env.farms[0]
    return f.shed.get(crop, 0) + f.inventories[0].get(crop, 0)


def best_harvest_day(crop):
    """Earliest day that banks the most units, watering every day.

    Earliest matters as much as most: a cycle one day shorter can fit another cycle into
    the 30-day season, which is worth more than a marginal unit.
    """
    spec = OBJECT_TABLE[crop]
    last = spec.get("max_yield_day", max(spec.get("sched_days", [0])))
    best_d, best_n = None, -1
    for d in range(1, last + 5):
        n = run_schedule(crop, range(d + 1), d)
        if n > best_n:
            best_d, best_n = d, n
    return best_d, best_n


def minimal_schedule(crop, harvest_day, target, order):
    """Greedily delete watering days while the harvest holds at `target`.

    Greedy is order-dependent, so the caller tries both directions and keeps the smaller
    result; a second confirmation pass then checks no single remaining day can also go.
    """
    keep = set(range(harvest_day + 1))
    for d in order:
        if d not in keep:
            continue
        if run_schedule(crop, keep - {d}, harvest_day) >= target:
            keep = keep - {d}
    return sorted(keep)


def confirm_minimal(crop, keep, harvest_day, target):
    """True if removing any single day from `keep` loses a unit."""
    for d in keep:
        if run_schedule(crop, set(keep) - {d}, harvest_day) >= target:
            return False
    return True


def commute_cost():
    """Mean Manhattan distance from the dawn spawn at the shed to a tile, per quadrant.

    ONE WAY, deliberately. `_day_refresh` does `f.hands = []` -- a hand simply vanishes
    wherever it is standing, and `_dump_inventory` has already emptied its carried harvest
    into the shed by then. So nothing ever has to walk home, and charging a round trip (as
    the first version of this probe did) doubles the only labour cost that is not amortised
    over a sweep.

    The catch is that the midnight dump is capped at SHED_CAPACITY and silently truncated,
    so 'let it ride until midnight' is only free while the shed has room.
    """
    sx, sy = SHED_TILES["NW"]
    out = {}
    for name, (x0, y0) in (("NW", (0, 0)), ("NE", (5, 0)), ("SW", (0, 5)), ("SE", (5, 5))):
        ds = [abs(x - sx) + abs(y - sy)
              for y in range(y0, y0 + 5) for x in range(x0, x0 + 5)]
        out[name] = sum(ds) / len(ds)
    return out


def jobs_per_unit_day(commute):
    """Tile-visits one unit can complete in a day. Lives in constants.py so the agent,
    portfolio.py and this probe all size the roster off the same arithmetic."""
    return tile_visits_per_unit_day(commute)


def units_needed(jobs, commute):
    per = jobs_per_unit_day(commute)
    if per <= 0:
        return 99
    return int(-(-jobs // per))            # ceil



def main():
    print("=" * 100)
    print("1. MINIMUM WATERING SCHEDULE PER CROP  (measured: days deleted until the harvest drops)")
    print("=" * 100)
    print(f"{'crop':12} {'harv_d':>7} {'units':>6} {'daily_w':>8} {'min_w':>6} {'saved':>6} "
          f"{'acts/cyc':>9} {'acts/tile-day':>14} {'min':>4} {'table':>6}  watering days")
    rows, mismatch = {}, []
    for crop in CROPS:
        hd, units = best_harvest_day(crop)
        full = list(range(hd + 1))
        late = minimal_schedule(crop, hd, units, order=sorted(full, reverse=True))
        early = minimal_schedule(crop, hd, units, order=sorted(full))
        keep = late if len(late) <= len(early) else early
        ok = confirm_minimal(crop, keep, hd, units)
        cycle = hd + 1
        acts = 1 + len(keep) + 1                       # plant + waters + one harvest
        rows[crop] = dict(harvest_day=hd, units=units, cycle=cycle, waters=keep,
                          acts=acts, per_day=acts / cycle)
        plan = CROP_PLAN[crop]
        agrees = (plan["harvest_day"] == hd and plan["units"] == units
                  and len(plan["water_days"]) == len(keep))
        if not agrees:
            mismatch.append(f"{crop}: measured harvest_day={hd} units={units} "
                            f"n_waters={len(keep)} vs table harvest_day={plan['harvest_day']} "
                            f"units={plan['units']} n_waters={len(plan['water_days'])}")
        print(f"{crop:12} {hd:>7} {units:>6} {len(full):>8} {len(keep):>6} "
              f"{len(full) - len(keep):>6} {acts:>9} {acts / cycle:>14.2f} "
              f"{'yes' if ok else 'NO':>4} {'ok' if agrees else 'DIFF':>6}  {keep}")

    print()
    print("   daily_w = watering every day of the cycle, which is what the yield probes do.")
    print("   min_w   = the smallest set that banks the same units. Day 0 is always in it:")
    print("             PLANT sets consecutive_unwatered = 1, so an unwatered planting day")
    print("             kills the tile at the first midnight.")
    print("   min     = confirmation pass -- no single remaining day can also be dropped.")
    print("   table   = agrees with CROP_PLAN in kagfarm/constants.py, which is what the agent")
    print("             and portfolio.py actually plan against. An equal-length schedule with a")
    print("             different phase is fine, so only the COUNT is compared, not the days.")
    if mismatch:
        print()
        print("   *** CROP_PLAN IS STALE — the agent is planning against the wrong schedule ***")
        for m in mismatch:
            print(f"     {m}")


    print()
    print("=" * 100)
    print("2. COMMUTE  (mean one-way Manhattan distance from the dawn spawn at the shed)")
    print("=" * 100)
    print(f"{'quadrant':10} {'mean moves':>11} {'turns left':>11} {'tile-visits/unit-day':>21}")
    cc = commute_cost()
    for q, d in cc.items():
        print(f"{q:10} {d:>11.1f} {TURNS_PER_DAY - d:>11.1f} {jobs_per_unit_day(d):>21}")
    print()
    print("   Hands vanish at midnight wherever they stand and their carried harvest is")
    print("   auto-dumped to the shed first, so nobody walks home -- this is a one-way cost,")
    print("   paid every day by every unit because the roster resets at dawn. It is also the")
    print("   only labour cost a sweep cannot amortise, which is why the far quadrant is worth")
    print("   ~15% fewer tile-visits per hand than the home one.")

    print()
    print("=" * 100)
    print("3. HANDS NEEDED  (measured jobs/day, serpentine sweep, one-way commute of 5)")
    print("=" * 100)
    print(f"{'mix':28} {'jobs/day':>9} {'units':>6} {'hands':>6} {'$/day':>7} {'$/season':>9} "
          f"{'$/tile-szn':>11}")
    COMMUTE = 5.0                                      # board mean over the four quadrants
    for label, mix in (("100 x melon", {"MELON": 100}),
                       ("100 x carrot", {"CARROT": 100}),
                       ("100 x wheat", {"WHEAT": 100}),
                       ("100 x strawberry", {"STRAWBERRY": 100}),
                       ("§2.8 optimum", {"WHEAT": 25, "CARROT": 10, "MELON": 19,
                                         "TOMATO": 11, "STRAWBERRY": 35})):
        jobs = sum(rows[c]["per_day"] * n for c, n in mix.items())
        u = units_needed(jobs, COMMUTE)
        n = max(0, u - 1)                              # the farmer is unit 0 and is free
        cost = sum(fib_hire_cost(i) for i in range(n))
        tiles = sum(mix.values())
        print(f"{label:28} {jobs:>9.0f} {u:>6} {n:>6} {cost:>7,} {cost * SEASON_DAYS:>9,} "
              f"{cost * SEASON_DAYS / tiles:>11,.0f}")

    print()
    print("   Wages are small in absolute terms -- but they are NOT crop-neutral, and that is")
    print("   what portfolio.py currently gets wrong. It charges 2 actions per planted tile per")
    print("   day for every crop, so 100 wheat and 100 strawberry cost the same. Measured, wheat")
    print("   costs 1.20 actions/tile-day against strawberry's 0.65, which is 7x the season wage")
    print("   bill. The fix is to charge per crop from the table in section 1.")
    print()
    print("   Two things this model still does not charge for:")
    print("     - peak vs mean. The rates above are averages over a cycle. Plant 35 strawberry")
    print("       tiles on the same day and their watering days coincide, so the peak day needs")
    print("       roughly double the mean. Staggered planting is worth real hands.")
    print("     - harvest routing. Harvest lands in the UNIT's inventory, and SELL draws from")
    print("       the shed, so anything not walked back and DROPped only becomes sellable at")
    print("       midnight -- and only if the 100-item shed has room for it.")


if __name__ == "__main__":
    main()


