"""
Economic probe: how much of each good can actually be sold, and what is
each crop/animal worth per tile-day and per labour-action?

Run: python3 analysis/econ_probe.py

One thing to hold onto while reading section 5: there are TWO different "how much can I
sell" numbers and they differ by 4x. The *sustainable* number is the town's drain — sell at
that rate and the price never moves off base. The *depth* number is how far you can flood
inventory before the marginal price falls below some fraction of base. The second is much
larger and much more fragile, because it assumes the opponent is not also flooding.
"""
import sys, os, math, statistics, collections, random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import (MARKET_PARAMS, OBJECT_TABLE, SHOP_TABLE, TOWN_CENTER_PRODUCTS,
                    price_for, I0, fib_hire_cost)
from kagfarm.constants import (drain_per_day_from_shops, MAX_SHOP_INSTANCES,
                               TOWN_SHOP_UNLOCK_INTERVAL_DAYS,
                               TOWN_SHOP_SELL_INTERVAL_TURNS, TURNS_PER_DAY)

GOODS = list(MARKET_PARAMS)
SHOP_NAMES = list(SHOP_TABLE)
DRAIN_TICKS_PER_DAY = TURNS_PER_DAY // TOWN_SHOP_SELL_INTERVAL_TURNS


def sell_curve(good, n_units, start_inv=I0):
    """Revenue from dumping n_units one at a time from start_inv."""
    inv, rev = start_inv, 0.0
    for _ in range(n_units):
        p = price_for(good, inv)
        rev += p
        if p > 1:
            inv += 1
    return rev, inv


def units_until(good, frac):
    """How many units can be sold before marginal price < frac*base."""
    base = MARKET_PARAMS[good]["base"]
    inv, n = I0, 0
    while price_for(good, inv) >= frac * base and n < 200000:
        inv += 1
        n += 1
    return n


print("=" * 100)
print("1. MARGINAL PRICE DEPTH  (units sellable from a fresh market before price decays)")
print("=" * 100)
print(f"{'good':12} {'base':>5} {'T':>5} {'>=90%':>8} {'>=75%':>8} {'>=50%':>8} {'>=25%':>8} "
      f"{'rev@100u':>9} {'avg@100':>8}")
for g in GOODS:
    p = MARKET_PARAMS[g]
    r100, _ = sell_curve(g, 100)
    print(f"{g:12} {p['base']:>5} {p['T']:>5} "
          f"{units_until(g,.90):>8} {units_until(g,.75):>8} {units_until(g,.50):>8} "
          f"{units_until(g,.25):>8} {r100:>9.0f} {r100/100:>8.1f}")

print()
print("=" * 100)
print("2. TOWN DEMAND  (inventory drained per day -> the sustainable sell rate at flat price)")
print("=" * 100)
per_shop_day = {s: {k: v * DRAIN_TICKS_PER_DAY for k, v in b.items()}
                for s, b in SHOP_TABLE.items()}
print(f"{'shop':17} {'units/day':>10}  basket/day")
for s, b in per_shop_day.items():
    print(f"{s:17} {sum(b.values()):>10}  {b}")
print()
print("Town centre: 1/day of each of", len(TOWN_CENTER_PRODUCTS), "goods")
print()
print("Shops are drawn WITH REPLACEMENT from those 8 types, one every 3 days, capped at 8.")
print("So per-good demand is a lottery, not a constant, and averaging the basket hides it:")
print()
print(f"{'good':12} {'baskets':>8} {'P(zero all season)':>19}   season units absorbed")
print(f"{'':12} {'':8} {'':19}   {'p10':>6} {'median':>7} {'mean':>7} {'p90':>6}  spread")


def _draw_schedule(rng):
    """The shop list as it exists on each day of the season, for one random draw."""
    shops, out = [], []
    for day in range(SEASON_DAYS_):
        if day % TOWN_SHOP_UNLOCK_INTERVAL_DAYS == 0 and day > 0 \
                and len(shops) < MAX_SHOP_INSTANCES:
            shops.append(rng.choice(SHOP_NAMES))
        out.append(list(shops))
    return out


SEASON_DAYS_ = 30
_DRAWS = [_draw_schedule(random.Random(s)) for s in range(2000)]
SEASON_UNITS = {}
for g in GOODS:
    xs = sorted(sum(drain_per_day_from_shops(g, day_shops) for day_shops in sched)
                for sched in _DRAWS)
    SEASON_UNITS[g] = xs
    k = sum(1 for n in SHOP_NAMES if SHOP_TABLE[n].get(g))
    p_zero = ((len(SHOP_NAMES) - k) / len(SHOP_NAMES)) ** MAX_SHOP_INSTANCES
    p10, p50, p90 = xs[len(xs) // 10], xs[len(xs) // 2], xs[len(xs) * 9 // 10]
    print(f"{g:12} {f'{k}/8':>8} {p_zero:>18.1%}   {p10:>6.0f} {p50:>7.0f} "
          f"{statistics.fmean(xs):>7.0f} {p90:>6.0f}  {p90 / max(1, p10):>4.1f}x")

print()
print("   WHEAT (5/8) and STRAWBERRY (4/8) are near-certain demand; WOOL is one basket in")
print("   eight, so a third of episodes drain 30 wool all season and sheep are dead weight.")
print("   MELON is in NO basket: exactly 30 units of demand every episode, shared with the")
print("   opponent. The agent must read the unlocked-shop list (day 3 onward) and size the")
print("   draw-conditional lines then, rather than committing to a fixed portfolio at dawn.")

print()
print("=" * 100)
print("3. CROP ECONOMICS  (MEASURED: units actually banked by driving the engine, not a formula)")
print("=" * 100)
print("   Every number below comes from scripting a single tile through engine.py and reading")
print("   the shed, so it cannot drift from the rules the agent will actually play against.")
print()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "calibration"))
from mirror_truth import check_harvest_by_day  # noqa: E402

FERT_COST = OBJECT_TABLE["FERTILIZER"]["buy_cost"]

print(f"{'crop':12} {'seed':>5} {'base':>5} {'best_d':>7} {'units':>6} {'cycle_d':>8} {'acts':>5} "
      f"{'$/tile-cycle':>13} {'$/tile-day':>11} {'$/action':>9} {'slack_d':>8}")

crop_rows = {}
for crop in ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"):
    s = OBJECT_TABLE[crop]
    by_day = {int(k): v for k, v in check_harvest_by_day(crop).items()}
    best_d = max(by_day, key=lambda d: (by_day[d], -d))
    units = by_day[best_d]
    # how many extra days you can be late before losing a unit -> routing tolerance
    slack = sum(1 for d in sorted(by_day) if d > best_d and by_day[d] >= units)
    cycle = best_d + 1                       # plant on d0, harvest on d(best_d)
    acts = 1 + cycle + 1                     # plant + water each day + harvest
    net = units * s["base_price"] - s["seed_cost"]
    crop_rows[crop] = dict(units=units, best_d=best_d, cycle=cycle, acts=acts, net=net)
    print(f"{crop:12} {s['seed_cost']:>5} {s['base_price']:>5} {best_d:>7} {units:>6} {cycle:>8} "
          f"{acts:>5} {net:>13.0f} {net/cycle:>11.1f} {net/acts:>9.1f} {slack:>8}")

print()
print("   slack_d = extra days you can be late to the harvest before losing a unit.")
print("   0 means the harvest turn is a hard deadline for that tile.")

print()
print(f"{'animal':12} {'buy':>5} {'base':>5} {'prod/30d':>9} {'wheat_fed':>10} {'acts/30d':>9} "
      f"{'$/tile-30d':>11} {'$/action':>9}   (bought day 1, fed+cared daily)")
for a in ("GOOSE", "COW", "SHEEP"):
    s = OBJECT_TABLE[a]
    first, iv, days = s["first_yield_day"], s["interval"], 29
    prod = sum(1 for age in range(days + 1) if age >= first and (age - first) % iv == 0)
    wheat = days                                     # 1 wheat/day
    acts = days * 2 + prod + 2                       # feed+care daily, harvest on prod days, build+place
    gross = prod * s["base_price"]
    net = gross - s["buy_cost"] - wheat * 25         # wheat at base price = opportunity cost
    print(f"{a:12} {s['buy_cost']:>5} {s['base_price']:>5} {prod:>9} {wheat:>10} {acts:>9} "
          f"{net:>11.0f} {net/acts:>9.1f}")

print()
print("=" * 100)
print("4. LABOUR BUDGET")
print("=" * 100)
cum = 0
for n in range(12):
    cum += fib_hire_cost(n)
    if n + 1 in (1, 4, 6, 8, 10, 12):
        print(f"  hire {n+1:>2} hands/day -> ${cum:>4} /day, ${cum*30:>5} /season, "
              f"{(n+2)*24:>4} unit-actions/day")
print()
print("  A serpentine row sweep costs 1 move between adjacent tiles, so a hand that walks")
print("  a 10-tile row spends 10 WATER + 9 MOVE = 19 of its 24 turns and covers 10 tiles.")
print("  10 hands x 10 tiles = 100 tiles/day = the whole board, IF routing is near-optimal.")
print("  Naive nearest-target assignment wastes 2-4x that, which caps the farm at ~25-40 tiles.")

print()
print("=" * 100)
print("5. SEASON CAPACITY  (how much of each good the MARKET will absorb, shared by both players)")
print("=" * 100)
print("   Depth alone is the wrong model. The town drains inventory every 4 turns whether or not")
print("   anyone sells, so a good is not a fixed-size pool -- it is a *flow*. Sell at the drain")
print("   rate and the price sits at base indefinitely; sell nothing and the price drifts ABOVE")
print("   base because the town keeps buying. Three corrections vs a naive depth count:")
print("     - shops unlock 1 per 3 days, capped at 8, so the drain ramps in over the first 3 weeks")
print("     - the drain is 6 ticks per day, interleaved with selling, not one lump at midnight")
print("     - crop cycles do not divide the season evenly: strawberry (17d) completes ONE cycle")
print()

SEASON_DAYS = SEASON_DAYS_
SHOP_UNLOCK_EVERY = TOWN_SHOP_UNLOCK_INTERVAL_DAYS
MAX_SHOPS = MAX_SHOP_INSTANCES


def drain_per_tick(good, day):
    """Units of `good` removed per drain tick on `day`, averaged over the shop draw.

    This is the mean-basket approximation, and section 2 shows how wrong it can be for a
    single episode: it gives WOOL 13 units/day where two thirds of episodes see 1. It is
    used only for the flood-depth columns below, where what matters is the rough shape of
    the price decay rather than the exact per-good rate. The *sustainable* columns come
    from SEASON_UNITS, which is the exact distribution over draws.
    """
    n_shops = min(MAX_SHOPS, day // SHOP_UNLOCK_EVERY)
    per_shop = sum(b.get(good, 0) for b in SHOP_TABLE.values()) / len(SHOP_TABLE)
    return n_shops * per_shop


def town_center_per_day(good):
    return 1.0 if good in TOWN_CENTER_PRODUCTS else 0.0


def season_capacity(good, frac=0.75, sellers=1):
    """Units *we* can sell across the season holding marginal price >= frac*base.

    sellers=2 splits the flow with an opponent selling at the same rate.
    Returns (units, revenue, avg_price, final_inventory).
    """
    base = MARKET_PARAMS[good]["base"]
    inv, units, rev = float(I0), 0, 0.0
    for day in range(SEASON_DAYS):
        d_tick = drain_per_tick(good, day)
        for tick in range(DRAIN_TICKS_PER_DAY):
            while units < 100000:
                p = price_for(good, inv)
                if p < frac * base:
                    break
                rev += p
                units += 1
                if p > 1:
                    inv += 1
                if sellers > 1:            # opponent sells one for each of ours
                    inv += (sellers - 1)
            inv = max(0.0, inv - d_tick)
        inv = max(0.0, inv - town_center_per_day(good))
    return units, rev, (rev / units if units else 0.0), inv


def idle_price(good):
    """Price at end of season if NOBODY ever sells this good -- the scarcity premium.

    Anything above base here is free money for whichever player notices first.
    """
    inv = float(I0)
    for day in range(SEASON_DAYS):
        inv -= DRAIN_TICKS_PER_DAY * drain_per_tick(good, day) + town_center_per_day(good)
        inv = max(0.0, inv)
    return price_for(good, inv), inv


def cycles_per_season(cycle_days):
    """Completed plant->harvest cycles in a 30-day season. Integer: a cycle that
    does not finish before the last turn banks nothing."""
    return max(0, SEASON_DAYS // cycle_days)


print(f"{'good':12} {'base':>5} {'sustain p10':>11} {'med':>5} {'p90':>5} {'rev@med':>8} "
      f"{'idle $':>7} {'depth75':>8} {'rev':>9} {'avg $':>6} {'dual':>7} {'u/tile':>7} {'tiles':>6}")

alloc = {}
for good in GOODS:
    if good == "FERTILIZER":
        continue
    cap, rev, avg, _ = season_capacity(good, sellers=1)
    cap2, rev2, avg2, _ = season_capacity(good, sellers=2)
    idle, _ = idle_price(good)
    xs = SEASON_UNITS[good]
    s10, s50, s90 = xs[len(xs) // 10], xs[len(xs) // 2], xs[len(xs) * 9 // 10]
    base = MARKET_PARAMS[good]["base"]
    rev_sustain = s50 * base            # sold at the drain rate, price never leaves base
    row = crop_rows.get(good)
    if row:
        n_cyc = cycles_per_season(row["cycle"])
        u_per_tile = row["units"] * n_cyc
        tiles = s50 / u_per_tile if u_per_tile else 0
        alloc[good] = dict(cap=cap, rev=rev, avg=avg, cap2=cap2, rev2=rev2,
                           sustain=s50, sustain_lo=s10, sustain_hi=s90,
                           rev_sustain=rev_sustain, tiles=tiles,
                           u_per_tile=u_per_tile, n_cyc=n_cyc, row=row)
        tail = f"{u_per_tile:>7.0f} {tiles:>6.1f}"
    else:
        tail = f"{'(animal)':>7} {'-':>6}"
    print(f"{good:12} {base:>5} {s10:>11.0f} {s50:>5.0f} {s90:>5.0f} {rev_sustain:>8.0f} "
          f"{idle:>7} {cap:>8} {rev:>9.0f} {avg:>6.1f} {cap2:>7} {tail}")

print()
print("   sustain     season units the town DRAINS, p10 / median / p90 over the shop draw.")
print("               Sell at this rate and the marginal price never leaves base, so this is")
print("               revenue you can bank without moving the price against yourself.")
print("   rev@med     median sustain x base price -- the safe revenue line for that good.")
print("   idle $      price on the last day if NOBODY sells that good all season.")
print("   depth75     units you can FLOOD in at >=75% of base, ignoring the drain. Much")
print("               bigger than sustain, and much more fragile: it assumes the opponent is")
print("               not flooding too, and it leaves inventory 1000s above I0 all season.")
print("   dual        same flood, if the opponent matches us unit for unit.")
print("   u/tile      units one tile produces in 30 days, INTEGER cycles only.")
print("   tiles       tiles of that crop whose season output fills the MEDIAN sustain flow.")
print()
print("   The gap between sustain and depth75 is the whole selling policy. Everything up to")
print("   sustain is free; past it, each extra unit is priced by our own glut curve, so it")
print("   belongs in an endgame dump when there is no tomorrow left to sell into.")
