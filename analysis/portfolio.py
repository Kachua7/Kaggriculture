"""
Season portfolio model: which crops, how many tiles, and when to sell.

A fast analytical stand-in for the real agent. It does not walk the board or
route hands -- it enforces the constraints that actually decide the score, using
yields MEASURED off engine.py rather than assumed:

  1. cash flow      start at $3,000; land costs $1k/$2k/$4k and has to be EARNED
                    before the extra 75 tiles exist
  2. shed           100 items total, silent overflow discard
  3. market flow    the town drains inventory every 4 turns; shops unlock 1 per
                    3 days to a cap of 8. Selling raises inventory (price down),
                    draining lowers it (price up). Not a fixed-size pool.
  4. labour         24 unit-actions per unit per day, ~2 actions per tile-day
                    once movement is counted, Fibonacci wages reset each dawn
  5. horizon        a cycle that does not finish before turn 720 banks nothing

Output: the tile allocation and reserve-price policy that maximise terminal
bank -- the number the agent build is aiming at.

Run: python3 analysis/portfolio.py
"""
import sys, os, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "calibration"))

from engine import (MARKET_PARAMS, OBJECT_TABLE, SHOP_TABLE, TOWN_CENTER_PRODUCTS,
                    price_for, I0, fib_hire_cost, SHED_CAPACITY, LAND_PRICES,
                    STARTING_MONEY)
from kagfarm.constants import (drain_per_day_from_shops, MAX_SHOP_INSTANCES,
                               TOWN_SHOP_UNLOCK_INTERVAL_DAYS, CROP_PLAN, needs_water,
                               tile_visits_per_unit_day)
from mirror_truth import check_harvest_by_day

SEASON_DAYS = 30
DRAIN_TICKS = 6           # town shops buy every 4 turns -> 6 per day
MAX_SHOPS = MAX_SHOP_INSTANCES
SHOP_EVERY = TOWN_SHOP_UNLOCK_INTERVAL_DAYS
CROPS = ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")
QUADS = (("NE", LAND_PRICES["NE"]), ("SW", LAND_PRICES["SW"]), ("SE", LAND_PRICES["SE"]))
SHOP_NAMES = list(SHOP_TABLE)

# Mean one-way walk from the dawn spawn at the shed into each quadrant. Hands vanish where
# they stand at midnight and their carried harvest is auto-dumped, so this is one way, not a
# round trip. Measured in analysis/labour_probe.py §2.
QUAD_COMMUTE = {"NW": 4.0, "NE": 5.0, "SW": 5.0, "SE": 6.0}



def draw_schedule(seed):
    """Shop list per day for one random unlock draw.

    Shops are drawn WITH REPLACEMENT, so the per-good drain is a lottery: carrot appears in
    2 of 8 baskets, wool in 1. Averaging the basket -- which every earlier version of this
    model did -- overstates carrot and tomato demand by ~2.4x and understates strawberry,
    which is exactly the axis this optimiser trades along. So the mix is optimised in
    expectation over a fixed panel of draws instead.
    """
    rng = random.Random(seed)
    shops, out = [], []
    for day in range(SEASON_DAYS):
        if day % SHOP_EVERY == 0 and day > 0 and len(shops) < MAX_SHOPS:
            shops.append(rng.choice(SHOP_NAMES))
        out.append(tuple(shops))
    return out


# A small fixed panel keeps the optimiser deterministic and fast. Six draws is enough to
# separate a mix that only wins when carrot demand is lucky from one that wins generally.
DRAW_PANEL = [draw_schedule(s) for s in (0, 1, 2, 3, 4, 5)]


def measure_crops():
    """units banked and best harvest day, straight off engine.py."""
    out = {}
    for crop in CROPS:
        by_day = {int(k): v for k, v in check_harvest_by_day(crop).items()}
        best = max(by_day, key=lambda d: (by_day[d], -d))
        out[crop] = dict(units=by_day[best], harvest_day=best, cycle=best + 1,
                         seed=OBJECT_TABLE[crop]["seed_cost"],
                         base=OBJECT_TABLE[crop]["base_price"])
    return out


def drain_per_tick(good, day):
    n_shops = min(MAX_SHOPS, day // SHOP_EVERY)
    per_shop = sum(b.get(good, 0) for b in SHOP_TABLE.values()) / len(SHOP_TABLE)
    return n_shops * per_shop


def town_center(good):
    return 1.0 if good in TOWN_CENTER_PRODUCTS else 0.0


def simulate(alloc, crops, reserve=0.75, opp_sell=None, buy_land=True, sched=None,
             max_hands=12):
    """One season under a target allocation {crop: n_tiles} and one shop draw.

    Day loop: unlock land if affordable -> water and harvest everything the roster can
    reach -> plant into whatever labour is left -> sell against the live price curve ->
    pay wages. Returns season totals including everything lost on the way.

    `max_hands` is the roster cap, and it is a real strategic knob rather than a detail.
    Hands are deleted at every midnight, so the Fibonacci bill is paid again every dawn:
    12 hands is $376/day, 18 is $6,764/day. Labour therefore stops being free at exactly
    the point where a mix wants everything watered on the same morning.
    """
    sched = sched or DRAW_PANEL[0]
    bank = STARTING_MONEY
    market = {g: float(I0) for g in MARKET_PARAMS}
    shed = {}
    carried = {}              # harvest sitting in unit inventories: unbounded until midnight
    tiles_unlocked = 25
    quad_i = 0
    planted = []              # list of dicts: crop, planted_on, harvest_on
    revenue = seed_spend = wage_spend = land_spend = 0.0
    overflow = 0
    lost_tiles = 0
    deferred = 0              # visits the roster could not cover even after abandonment
    sold = {g: 0 for g in MARKET_PARAMS}
    realized = {g: 0.0 for g in MARKET_PARAMS}
    target_tiles = sum(alloc.values())
    peak_tiles = 0
    peak_hands = 0
    # cash we must keep back per new tile so a land purchase does not strand us
    seed_reserve = (sum(crops[c]["seed"] * n for c, n in alloc.items())
                    / max(1, target_tiles))

    for day in range(SEASON_DAYS):
        # --- land: buy the next quadrant only when we want it AND can still afford
        # to plant it. Buying greedily on day 0 spends all $3,000 on dirt and the
        # season never starts -- the model has to be allowed to notice that.
        while (buy_land and quad_i < len(QUADS) and target_tiles > tiles_unlocked
               and bank >= QUADS[quad_i][1] + 25 * seed_reserve):
            bank -= QUADS[quad_i][1]
            land_spend += QUADS[quad_i][1]
            tiles_unlocked += 25
            quad_i += 1

        # --- today's labour budget, in tile-visits
        n_quads = max(1, tiles_unlocked // 25)
        commute = sum(QUAD_COMMUTE[q]
                      for q in ("NW", "NE", "SW", "SE")[:n_quads]) / n_quads
        per_unit = tile_visits_per_unit_day(commute)
        budget = (1 + max_hands) * per_unit

        # --- mandatory work first: waterings on schedule and harvests due today.
        #
        # This is the constraint the old flat "2 actions per planted tile" charge could not
        # express. Waterings are not spread evenly -- they are dictated by planting date, so a
        # mix planted all at once has its schedules collide and the peak day needs three times
        # the mean roster. When the roster cannot cover the peak, tiles die, and the cheapest
        # ones are abandoned first because a harvest is never worth skipping for a watering.
        #
        # A harvest counts as TWO visits: HARVEST puts the crop in the unit's own inventory,
        # and SELL draws from the shed, so somebody has to walk it back and DROP it. A unit
        # that sweeps ten tiles pays ten HARVESTs, one DROP and the walk home -- about 1.6
        # visits per harvested tile, rounded up to 2.
        due_water = [p for p in planted if needs_water(p["crop"], day - p["planted_on"])]
        due_harvest = [p for p in planted if p["harvest_on"] == day]
        need = len(due_water) + 2 * len(due_harvest)
        if need > budget:
            # Harvests are never skipped -- a tile at harvest day is worth its whole cycle,
            # against one unit of decay for a missed watering -- so only waterings are shed.
            # If the harvests alone exceed the budget the deficit is left standing rather
            # than silently absorbed, and `deferred` records it so the caller can see that
            # this roster physically cannot service this mix.
            over = min(len(due_water), int(need - budget))
            due_water.sort(key=lambda p: crops[p["crop"]]["units"] * crops[p["crop"]]["base"])
            for p in due_water[:over]:
                planted.remove(p)
            lost_tiles += over
            due_water = due_water[over:]
            need = len(due_water) + 2 * len(due_harvest)
            deferred += max(0, int(need - budget))

        # --- plant into the leftover budget. A new tile costs TWO visits today: PLANT, and
        # the day-0 WATER that keeps consecutive_unwatered from reaching 2 at midnight.
        slots = max(0, int((budget - need) // 2))
        occupied = {}
        for p in planted:
            occupied[p["crop"]] = occupied.get(p["crop"], 0) + 1
        free = min(tiles_unlocked, target_tiles) - len(planted)
        planted_today = 0
        for crop in sorted(alloc, key=lambda c: -crops[c]["units"] * crops[c]["base"]):
            want = alloc[crop] - occupied.get(crop, 0)
            c = crops[crop]
            while (want > 0 and free > 0 and slots > 0 and bank >= c["seed"]
                   and day + c["harvest_day"] < SEASON_DAYS):
                bank -= c["seed"]
                seed_spend += c["seed"]
                planted.append({"crop": crop, "planted_on": day,
                                "harvest_on": day + c["harvest_day"]})
                planted_today += 1
                want -= 1
                free -= 1
                slots -= 1
        peak_tiles = max(peak_tiles, len(planted))

        jobs = need + 2 * planted_today
        units = -(-jobs // per_unit) if per_unit else 99
        n_hands = max(0, units - 1)            # the farmer is unit 0 and costs nothing
        peak_hands = max(peak_hands, n_hands)

        # --- harvest into the harvesting unit's own inventory, which is UNBOUNDED.
        #
        # The 100-item cap is on the shed, not on a unit, and market orders cost no unit
        # actions at all -- SELL lives in a separate list from the tile ops and can fire every
        # turn. So the shed is a turnstile, not a warehouse: it can be filled and emptied many
        # times a day. What actually destroys value is harvest still being CARRIED at midnight,
        # because `_day_refresh` dumps every inventory into the shed and silently truncates.
        still = []
        for p in planted:
            if p["harvest_on"] == day:
                carried[p["crop"]] = carried.get(p["crop"], 0) + crops[p["crop"]]["units"]
            else:
                still.append(p)
        planted = still

        # --- sell, interleaved with the town's drain ticks.
        #
        # Each tick: land as much carried harvest in the shed as fits, then sell dearest-first.
        # Holding a reserve price on a good that has crashed starves every other good of shed
        # space, so the reserve is abandoned once the shed is crowded -- an item we refuse to
        # sell is an item we are about to destroy.
        for tick in range(DRAIN_TICKS):
            for good in sorted(carried, key=lambda g: -price_for(g, market[g])):
                space = SHED_CAPACITY - sum(shed.values())
                move = max(0, min(carried[good], space))
                if move:
                    shed[good] = shed.get(good, 0) + move
                    carried[good] -= move
                if carried[good] == 0:
                    del carried[good]
            while shed:
                # Two reasons to sell a unit. Either the price clears the reserve, or the
                # shed has to make room for harvest still being carried. Forced selling is
                # dearest-first like everything else and stops the moment the backlog fits,
                # so a crowded day sheds as little as it must instead of emptying the shed
                # and crashing every curve at once.
                wanted = min(SHED_CAPACITY, sum(carried.values()))
                forced = SHED_CAPACITY - sum(shed.values()) < wanted
                good = max(shed, key=lambda g: price_for(g, market[g]))
                p = price_for(good, market[good])
                if not forced and p < reserve * MARKET_PARAMS[good]["base"]:
                    break
                shed[good] -= 1
                if shed[good] == 0:
                    del shed[good]
                revenue += p
                bank += p
                sold[good] += 1
                realized[good] += p
                if p > 1:
                    market[good] += 1
            for good in market:
                if opp_sell:
                    market[good] += opp_sell.get(good, 0) / DRAIN_TICKS
                # exact drain for the shops this draw has actually unlocked, spread
                # across the day's ticks (the town-centre unit is inside the helper)
                market[good] = max(0.0, market[good]
                                   - drain_per_day_from_shops(good, sched[day]) / DRAIN_TICKS)

        # --- midnight: every carried inventory dumps into the shed and the excess is gone
        for good in list(carried):
            space = SHED_CAPACITY - sum(shed.values())
            move = max(0, min(carried[good], space))
            if move:
                shed[good] = shed.get(good, 0) + move
            overflow += carried[good] - move
            del carried[good]

        # --- wages: pay for today's roster (deleted again at midnight)
        w = hand_cost(n_hands)
        bank -= w
        wage_spend += w

    return dict(bank=bank, revenue=revenue, seed_spend=seed_spend,
                wage_spend=wage_spend, land_spend=land_spend,
                overflow=overflow, unsold=sum(shed.values()), lost_tiles=lost_tiles,
                deferred=deferred,
                peak_tiles=peak_tiles, tiles_unlocked=tiles_unlocked,
                sold=sold, realized=realized, market=market,
                avg={g: (realized[g] / sold[g] if sold[g] else 0.0) for g in sold},
                hands=peak_hands)


def hand_cost(n_hands):
    return sum(fib_hire_cost(i) for i in range(n_hands))



def simulate_panel(alloc, crops, reserve=0.75, opp_sell=None, panel=None, max_hands=12):
    """Mean season over the whole draw panel, plus the worst draw in it.

    `bank` is the panel mean, so the optimiser maximises expected terminal bank rather than
    its luck on one draw. `bank_worst` comes along because a mix that averages well by
    winning big on two draws and losing on four is not what we want to submit — the ladder
    plays many episodes, but each one is scored on its own.
    """
    panel = panel or DRAW_PANEL
    runs = [simulate(alloc, crops, reserve, opp_sell, sched=s, max_hands=max_hands)
            for s in panel]
    mean = dict(runs[0])
    n = len(runs)
    for k, v in mean.items():
        if isinstance(v, (int, float)):
            mean[k] = sum(r[k] for r in runs) / n
    for k in ("sold", "realized", "market"):
        mean[k] = {g: sum(r[k][g] for r in runs) / n for g in runs[0][k]}
    mean["avg"] = {g: (mean["realized"][g] / mean["sold"][g] if mean["sold"][g] else 0.0)
                   for g in mean["sold"]}
    mean["bank_worst"] = min(r["bank"] for r in runs)
    mean["bank_spread"] = max(r["bank"] for r in runs) - mean["bank_worst"]
    mean["hands"] = max(r["hands"] for r in runs)
    return mean


# ---------------------------------------------------------------------------
# search: random restarts + unit-step local ascent (the coordinate ladder alone
# lands on multiples of its step size and reports fake mixes)
# ---------------------------------------------------------------------------

def local_ascent(alloc, crops, reserve, budget, opp_sell=None, steps=(8, 3, 1),
                 max_hands=12):
    best = simulate_panel(alloc, crops, reserve, opp_sell, max_hands=max_hands)["bank"]
    improved = True
    while improved:
        improved = False
        for s in steps:
            for crop in CROPS:
                for delta in (s, -s):
                    cand = dict(alloc)
                    cand[crop] = max(0, cand[crop] + delta)
                    if sum(cand.values()) > budget:
                        continue
                    b = simulate_panel(cand, crops, reserve, opp_sell,
                                       max_hands=max_hands)["bank"]
                    if b > best + 1e-9:
                        alloc, best, improved = cand, b, True
    return alloc, simulate_panel(alloc, crops, reserve, opp_sell, max_hands=max_hands)


def search(crops, reserve, budget, opp_sell=None, restarts=6, seed=0, max_hands=12):
    rng = random.Random(seed)
    starts = [{c: 0 for c in CROPS}]
    for c in CROPS:                                  # each single-crop monoculture
        starts.append({k: (budget if k == c else 0) for k in CROPS})
    for _ in range(restarts):                        # random simplex points
        cuts = sorted(rng.randint(0, budget) for _ in range(len(CROPS) - 1))
        parts, prev = [], 0
        for cut in cuts + [budget]:
            parts.append(cut - prev)
            prev = cut
        starts.append(dict(zip(CROPS, parts)))

    best_alloc, best_r = None, None
    for st in starts:
        a, r = local_ascent(dict(st), crops, reserve, budget, opp_sell, max_hands=max_hands)
        if best_r is None or r["bank"] > best_r["bank"]:
            best_alloc, best_r = a, r
    return best_alloc, best_r


def mix_str(alloc):
    return " ".join(f"{c[:4].lower()}={n}" for c, n in alloc.items() if n) or "(nothing)"


def main():
    print("measuring crop yields off engine.py ...")
    crops = measure_crops()
    print()
    print(f"{'crop':12} {'units':>6} {'harv_d':>7} {'cycle':>6} {'seed':>5} {'base':>5} "
          f"{'cyc/szn':>8} {'u/tile-szn':>11}")
    for c, v in crops.items():
        n = SEASON_DAYS // v["cycle"]
        print(f"{c:12} {v['units']:>6} {v['harvest_day']:>7} {v['cycle']:>6} "
              f"{v['seed']:>5} {v['base']:>5} {n:>8} {n * v['units']:>11}")

    print()
    print("=" * 100)
    print("A. TILE BUDGET x ROSTER CAP   allocation re-optimised in every cell, mean of 6 draws")
    print("=" * 100)
    print("   Two knobs, and they are not separable. More tiles need more hands, but hands are")
    print("   re-hired every dawn on a Fibonacci curve, so the 13th hand costs $233 for the day")
    print("   and the 18th costs $2,584. The row maximum is therefore the real farm size, and it")
    print("   is not always the biggest one.")
    print()
    CAPS = (6, 8, 10, 12, 16)
    print(f"{'budget':>7} " + " ".join(f"{'cap ' + str(c):>10}" for c in CAPS)
          + f" {'best':>5}  best allocation")
    grid, best_100 = {}, None
    for budget in (25, 50, 75, 100):
        row = {}
        for cap in CAPS:
            row[cap] = search(crops, 0.75, budget, max_hands=cap)
        grid[budget] = row
        top = max(CAPS, key=lambda c: row[c][1]["bank"])
        print(f"{budget:>7} " + " ".join(f"{row[c][1]['bank']:>10,.0f}" for c in CAPS)
              + f" {top:>5}  {mix_str(row[top][0])}")
        if budget == 100:
            best_100 = row[top]

    # the overall best cell, which is what everything downstream should plan against
    best_cell = max(((b, c) for b in grid for c in CAPS),
                    key=lambda k: grid[k[0]][k[1]][1]["bank"])
    b_budget, b_cap = best_cell
    alloc_best, r_best = grid[b_budget][b_cap]
    print()
    print(f"{'':7} " + " ".join(f"{'':>10}" for c in CAPS) + "  detail of the best cell:")
    print(f"{b_budget:>7} tiles, {b_cap} hands: bank {r_best['bank']:,.0f} "
          f"worst {r_best['bank_worst']:,.0f} revenue {r_best['revenue']:,.0f} "
          f"seeds {r_best['seed_spend']:,.0f} land {r_best['land_spend']:,.0f} "
          f"wages {r_best['wage_spend']:,.0f}")
    print(f"{'':7} peak tiles {r_best['peak_tiles']:.0f}, tiles lost to labour "
          f"{r_best['lost_tiles']:.0f}, visits deferred {r_best['deferred']:.0f}, "
          f"overflow {r_best['overflow']:.0f}, unsold {r_best['unsold']:.0f}")

    alloc100, r100 = best_100
    print()
    print("   worst = the weakest of the six draws. A wide gap between bank and worst means")
    print("   the mix is betting on which shops the town happens to open.")
    print("   overflow is now ~0 everywhere, and that is a finding rather than a fix: market")
    print("   orders cost no unit turns, so the 100-item shed can be filled and sold empty at")
    print("   every one of the six drain ticks. The shed is a turnstile, not a warehouse, and")
    print("   the only way to destroy harvest is to still be carrying it at midnight.")
    print()
    print("=" * 100)
    print(f"B. RESERVE PRICE SWEEP   allocation re-optimised at each reserve, "
          f"{b_budget}-tile budget, {b_cap} hands")
    print("=" * 100)
    print(f"{'reserve':>8} {'bank':>10} {'worst':>10} {'revenue':>10} {'sold u':>7} {'ovf':>5} "
          f"{'unsold':>7}  allocation")
    for reserve in (0.20, 0.50, 0.75, 0.90, 1.00, 1.10):
        a, r = search(crops, reserve, b_budget, max_hands=b_cap)
        print(f"{reserve:>8.2f} {r['bank']:>10,.0f} {r['bank_worst']:>10,.0f} "
              f"{r['revenue']:>10,.0f} {sum(r['sold'].values()):>7.0f} {r['overflow']:>5.0f} "
              f"{r['unsold']:>7.0f}  {mix_str(a)}")
    print()
    print("   The reserve barely moves the bank now, and that is the point: with the shed")
    print("   cycling every tick there is no queue for space, so refusing a cheap sale costs")
    print("   nothing and gains nothing. Above 1.00 it starts refusing sales it needed, which")
    print("   is why 1.10 collapses and drops melon out of the mix entirely.")

    print()
    print("=" * 100)
    print(f"C. WHERE THE MONEY COMES FROM   best cell ({b_budget} tiles, {b_cap} hands), per good")
    print("=" * 100)
    alloc, r = alloc_best, r_best
    print(f"   mix: {mix_str(alloc)}    bank ${r['bank']:,.0f} "
          f"(worst draw ${r['bank_worst']:,.0f})")
    print()
    print(f"{'good':12} {'sold':>7} {'revenue':>10} {'avg $':>7} {'base':>5} {'% of base':>10} "
          f"{'end inv':>9}")
    for g, n in sorted(r["sold"].items(), key=lambda kv: -r["realized"][kv[0]]):
        if not n:
            continue
        base = MARKET_PARAMS[g]["base"]
        print(f"{g:12} {n:>7.0f} {r['realized'][g]:>10,.0f} {r['avg'][g]:>7.1f} {base:>5} "
              f"{100 * r['avg'][g] / base:>9.0f}% {r['market'][g]:>9,.0f}")

    print()
    print("=" * 100)
    print("D. OPPONENT PRESSURE   same mix, opponent dumping into our goods every day")
    print("=" * 100)
    print(f"{'opp units/day':>14} {'bank':>10} {'vs solo':>9}   note")
    solo = r["bank"]
    for rate in (0, 2, 5, 10, 25, 50):
        opp = {g: rate for g in CROPS}
        rr = simulate_panel(alloc, crops, 0.75, opp_sell=opp, max_hands=b_cap)
        note = ""
        if rate and rr["bank"] < STARTING_MONEY:
            note = "below starting cash -- price floor reached"
        print(f"{rate:>14} {rr['bank']:>10,.0f} {rr['bank'] - solo:>+9,.0f}   {note}")
    print()
    print("   The rate is units/day of EACH of the five crops, so 10 means 50 units/day and")
    print("   1,500 for the season. This opponent is not rational -- it dumps into a $1 floor")
    print("   it helped create -- so read the table as a worst case, not a forecast. What it")
    print("   does establish: on shared goods our revenue is not ours to plan alone, which is")
    print("   the argument for Phase 5 reading the opponent's sell rate off inventory deltas.")


if __name__ == "__main__":
    main()
