"""How much of the score is trapped behind the first thirteen days.

`limit_probe` says the allocator runs out of *land* on 100% of dawns in days 0-9 while holding a
mean budget of $286 and 103 unused tile-visits. The farm owns 25 tiles, plants all 25, and cannot
buy the $1,000 NE quadrant because the seed for those 25 tiles took the whole $3,000 stake. Land
then arrives all at once on day 13 when the first harvest wave banks $16k. So a third of the season
is played on a quarter of the board, and the question is what that costs.

Two knobs, and they decompose the answer:

  * extra starting cash -- buys seed AND land immediately, so it measures the whole early-game
    gap: what a farm that was never cash-starved would earn.
  * a land discount -- buys land only. If cheap land recovers most of the cash gap then the
    early game is land-starved and the fix is to fund the quadrant ahead of the seed. If it
    recovers little, the tiles were never the problem and the stake is simply too small to
    plant them, which no scheduling change can fix.

Neither knob is submittable; both are engine constants. The number that matters is the size of the
gap, because it is the ceiling on what an early-cash phase -- short-cycle crops on day 0 to fund
the quadrant by day 5 instead of day 13 -- could possibly be worth.

    python3 analysis/early_probe.py
    python3 analysis/early_probe.py --seeds 32 --cash 0,3000,10000 --land 1.0,0.25
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from kagfarm.constants import SEASON_DAYS, TURNS_PER_DAY


def run_cell(job):
    """One episode with the stake raised and/or the land priced down."""
    seed, opp_name, cash, land_mult, shed_cap = job

    import engine
    from kagfarm import policy as _policy
    from kagfarm.constants import LAND_PRICES
    from agents import BUILTIN_AGENTS
    import main

    # Both modules import the cap by name and both must move together: the engine enforces it and
    # the policy's `crowded` test and sell-slot floor are calibrated against it.
    for mod in (engine, _policy):
        mod.SHED_CAPACITY = shed_cap

    # `LAND_PRICES` is one dict imported by name into both the engine and the policy, so mutating
    # it in place moves the price and the agent's view of the price together. Restored below --
    # pool workers are reused across cells and a leaked discount would silently contaminate
    # every later job on the same worker.
    base = dict(LAND_PRICES)
    for q in LAND_PRICES:
        LAND_PRICES[q] = base[q] * land_mult
    try:
        env = engine.KaggricultureEnv(episode_steps=720, seed=seed)
        me = env.farms[0]
        # Not a patch of `STARTING_MONEY`: the Farm dataclass captured that as a default when the
        # class was created, so the module attribute is no longer read. The balance is the thing.
        me.money += cash

        lost = {"n": 0}
        _add = env._add_shed

        def add_shed(f, item, n):
            got = _add(f, item, n)
            if f is me:
                lost["n"] += max(0, n - got)
            return got

        env._add_shed = add_shed

        main._POLICIES.clear()
        opp = BUILTIN_AGENTS[opp_name]
        obs = env._obs()
        tile_days = 0
        early_tiles = 0
        land_day = {}
        while not env.done:
            act = main.agent(obs[0])
            obs, _ = env.step([act, opp(obs[1])])
            live = sum(1 for row in me.tiles for t in row
                       if isinstance(t, dict) and t.get("kind") == "PLANT")
            tile_days += live
            day = env.t // TURNS_PER_DAY
            if day < SEASON_DAYS // 3:
                early_tiles += live
            for q in me.unlocked_quadrants:
                land_day.setdefault(q, day)
    finally:
        LAND_PRICES.update(base)

    third = max(1, (SEASON_DAYS // 3) * TURNS_PER_DAY)
    return dict(cash=cash, land=land_mult, shed=shed_cap, bank=me.money - cash, lost=lost["n"],
                tiles=tile_days / (SEASON_DAYS * TURNS_PER_DAY),
                early=early_tiles / third,
                owned=25 * len(me.unlocked_quadrants),
                last_land=max(land_day.values()) if land_day else 0)


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=24)
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--cash", default="0,2000,7000,20000")
    ap.add_argument("--land", default="1.0,0.1")
    ap.add_argument("--sheds", default="100")
    a = ap.parse_args()

    opps = a.opps.split(",")
    cashes = [float(c) for c in a.cash.split(",")]
    lands = [float(x) for x in a.land.split(",")]
    sheds = [int(s) for s in a.sheds.split(",")]

    jobs = [(seed, opp, cash, land, shed)
            for cash in cashes for land in lands for shed in sheds
            for opp in opps for seed in range(a.seeds)]
    with ProcessPoolExecutor(max_workers=min(os.cpu_count() or 4, 16)) as ex:
        rows = list(ex.map(run_cell, jobs, chunksize=4))

    print("%d episodes per cell (%d seeds x %s)\n" % (a.seeds * len(opps), a.seeds,
                                                      ",".join(opps)))
    print("  %9s %6s %6s %10s %9s %8s %8s %7s %7s %9s"
          % ("+cash", "landx", "shed", "mean", "p10", "tiles", "early", "owned", "lost", "d_mean"))
    base = None
    for cash in cashes:
        for land in lands:
            for shed in sheds:
                cell = [r for r in rows if r["cash"] == cash and r["land"] == land
                        and r["shed"] == shed]
                banks = sorted(r["bank"] for r in cell)
                mean = sum(banks) / len(banks)
                if base is None:
                    base = mean
                print("  %9.0f %6.2f %6d $%9.0f $%8.0f %8.1f %8.1f %7.1f %7.1f %+9.0f"
                      % (cash, land, shed, mean, banks[max(0, int(0.1 * len(banks)) - 1)],
                         sum(r["tiles"] for r in cell) / len(cell),
                         sum(r["early"] for r in cell) / len(cell),
                         sum(r["owned"] for r in cell) / len(cell),
                         sum(r["lost"] for r in cell) / len(cell), mean - base))

    print("\n`mean` is terminal bank with the gifted cash subtracted, so the rows are comparable.\n"
          "`early` is mean live tiles over the first third; `owned` is final unlocked acreage.\n"
          "Deltas are against the first row, which is the shipping configuration. Neither knob is\n"
          "submittable -- the gap is the ceiling on what an early-cash phase could be worth.")


if __name__ == "__main__":
    main_cli()
