"""
Economic probe: how much of each good can actually be sold, and what is
each crop/animal worth per tile-day and per labour-action?

Run: python3 analysis/econ_probe.py
"""
import sys, os, math, statistics, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import (MARKET_PARAMS, OBJECT_TABLE, SHOP_TABLE, TOWN_CENTER_PRODUCTS,
                    price_for, I0, fib_hire_cost)

GOODS = list(MARKET_PARAMS)


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
# 8 shop instances, drain basket every 4 turns => 6 drains/day each. Town centre: 1 each/day.
per_shop_day = {s: {k: v * 6 for k, v in b.items()} for s, b in SHOP_TABLE.items()}
print(f"{'shop':17} {'units/day':>10}  basket/day")
for s, b in per_shop_day.items():
    print(f"{s:17} {sum(b.values()):>10}  {b}")
print()
print("Town centre: 1/day of each of", len(TOWN_CENTER_PRODUCTS), "goods")
print()
# expected drain per good with 8 uniformly-drawn shops
exp = collections.Counter()
for g in TOWN_CENTER_PRODUCTS:
    exp[g] += 1.0
for s, b in per_shop_day.items():
    for k, v in b.items():
        exp[k] += v * 8 / len(SHOP_TABLE)   # 8 instances, uniform draw w/ replacement
print(f"{'good':12} {'exp units drained/day (8 shops)':>34}")
for g in GOODS:
    print(f"{g:12} {exp[g]:>34.1f}")
print(f"{'TOTAL':12} {sum(exp.values()):>34.1f}")

print()
print("=" * 100)
print("3. CROP / ANIMAL YIELD ECONOMICS  (per tile, unfertilised, mirror-engine growth rules)")
print("=" * 100)
print(f"{'crop':12} {'seed':>5} {'base':>5} {'units':>6} {'cycle_d':>8} {'acts':>5} "
      f"{'$/tile-cycle':>13} {'$/tile-day':>11} {'$/action':>9}")


def crop_econ(crop):
    s = OBJECT_TABLE[crop]
    if s["kind"] == "one_time":
        first, last = s["first_yield_day"], s["max_yield_day"]
        units = min(s["max_yield_unfert"], last - first + 1)
        cycle = last + 1                       # plant d0 .. harvest d(last)
        acts = 1 + cycle + 1                   # plant + water each day + harvest
    else:
        sched = s["sched_days"]
        units = min(s["max_yield"], len(sched))
        cycle = sched[-1] + 1
        acts = 1 + cycle + len(sched)          # plant + daily water + one harvest per sched day
    gross = units * s["base_price"]
    net = gross - s["seed_cost"]
    return units, cycle, acts, net


for crop in ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"):
    s = OBJECT_TABLE[crop]
    units, cycle, acts, net = crop_econ(crop)
    print(f"{crop:12} {s['seed_cost']:>5} {s['base_price']:>5} {units:>6} {cycle:>8} {acts:>5} "
          f"{net:>13.0f} {net/cycle:>11.1f} {net/acts:>9.1f}")

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
