"""Engine-exact constants and derived economics.

Every number here is transcribed from kaggle_environments/envs/kaggriculture/kaggriculture.py
(module_version 1.32.7). Nothing is inferred from a mirror. Where the old kagfarm/constants.py
disagreed, the engine wins.

Key corrections against the previous build's assumptions:

  * one_time crops gain yield ON `WATER`, inside the age window
    [ (max_yield_day+1)//2 , max_yield_day ], and start life with yield_units = 1.
    They do NOT gain at dawn.
  * ongoing crops gain at dawn, `+2` only when the tile was watered that day AND
    `fertilized_until_day >= current_day`. `max_yield` caps STANDING units, so a fertilized
    tile must be harvested between gain days or the bonus is silently clipped.
  * FERTILIZE sets `fertilized_until_day = day + 2` -> covers day, day+1, day+2 (3 days).
  * the animal care bonus accrues only when the animal was BOTH cared and fed that day, and is
    consumed on a production day only if it was fed that day. Daily feeding is mandatory.
  * PICKUP / DROP / shed-PLACE require standing on a shed-access tile; those four tiles are
    reachable even while LOCKED because shed ops resolve before the LOCKED guard.
  * there is no engine cap on hand count -- only the Fibonacci hire price.
  * a SELL that clears at the $1 floor does not add to market inventory.
"""

import math

BOARD = 10
TPD = 24                     # turns per day
SEASON = 30                  # days 0..29
LAST_STEP = 718              # interpreter fires DONE at episodeSteps-2; money then is the score
I0 = 10000
PRICE_FLOOR = 1
SHED_CAP = 100
MAX_ORDERS = 10
SHOP_UNLOCK_EVERY = 3
MAX_SHOPS = 8
SHOP_TICKS_PER_DAY = TPD // 4        # town shops consume every 4 steps

CROPS = {
    "WHEAT":      dict(seed=10,  first=2,  maxd=4,  interval=0, maxy=6, ongoing=False),
    "CARROT":     dict(seed=20,  first=2,  maxd=3,  interval=0, maxy=4, ongoing=False),
    "TOMATO":     dict(seed=50,  first=8,  maxd=8,  interval=1, maxy=4, ongoing=True),
    "STRAWBERRY": dict(seed=100, first=10, maxd=10, interval=2, maxy=4, ongoing=True),
    "MELON":      dict(seed=80,  first=10, maxd=12, interval=0, maxy=6, ongoing=False),
}

ANIMALS = {
    "GOOSE": dict(cost=300, struct="COOP",    first=4, interval=1, maxh=4, product="EGG"),
    "COW":   dict(cost=400, struct="PASTURE", first=8, interval=2, maxh=6, product="MILK"),
    "SHEEP": dict(cost=500, struct="PASTURE", first=6, interval=3, maxh=6, product="WOOL"),
}
PRODUCT_OF = {a: s["product"] for a, s in ANIMALS.items()}
ANIMAL_OF = {s["product"]: a for a, s in ANIMALS.items()}

PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]
TOWN_CENTER = [p for p in PRODUCTS if p != "FERTILIZER"]

HINGE_GAIN = 8.0
MARKET = {
    "WHEAT":      dict(base=25,  T=400, bf="sqrt",   bt=0.80, af="log",    at=0.20),
    "CARROT":     dict(base=35,  T=450, bf="hinge",  bt=1.00, af="sqrt",   at=0.70),
    "TOMATO":     dict(base=60,  T=200, bf="hinge",  bt=0.40, af="sqrt",   at=0.60),
    "STRAWBERRY": dict(base=120, T=100, bf="sqrt",   bt=0.70, af="linear", at=1.60),
    "MELON":      dict(base=250, T=300, bf="log",    bt=0.20, af="sq",     at=3.60),
    "EGG":        dict(base=50,  T=332, bf="hinge",  bt=0.40, af="log",    at=0.20),
    "MILK":       dict(base=160, T=122, bf="sqrt",   bt=0.60, af="linear", at=1.60),
    "WOOL":       dict(base=200, T=105, bf="log",    bt=0.20, af="sq",     at=3.20),
    "FERTILIZER": dict(base=100, T=200, bf="linear", bt=0.40, af="linear", at=0.40),
}

SHOPS = {
    "BAKERY":         ["EGG", "WHEAT"],
    "PIZZA_SHOP":     ["MILK", "TOMATO", "WHEAT"],
    "BRUNCH_SPOT":    ["EGG", "WHEAT", "STRAWBERRY"],
    "YARN_STORE":     ["WOOL"],
    "ICE_CREAM_SHOP": ["STRAWBERRY", "MILK", "WHEAT"],
    "PET_CAFE":       ["CARROT"],
    "SMOOTHIE_SHOP":  ["STRAWBERRY", "MILK"],
    "FARMERS_MARKET": ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY"],
}
# A one-product shop consumes 2 per tick; everything else consumes 1 of each.
SHOP_UNITS = {name: {g: (2 if len(b) == 1 else 1) for g in b} for name, b in SHOPS.items()}
# Expected units/tick a not-yet-drawn shop will contribute, drawn uniformly with replacement.
EXP_PER_SHOP = {}
for _g in PRODUCTS:
    EXP_PER_SHOP[_g] = sum(SHOP_UNITS[s].get(_g, 0) for s in SHOPS) / float(len(SHOPS))

LAND_PRICES = [1000, 2000, 4000]
LAND_ORDER = ["NE", "SW", "SE"]


# --------------------------------------------------------------------------- market

def _shape(func, x, T=None):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "hinge":
        if not T or T <= 0:
            return x
        u = x / T
        return u + HINGE_GAIN * max(0.0, u - 1.0) ** 2
    return x


def price_at(item, inventory):
    """Exact copy of the engine's market_price for the default params."""
    p = MARKET[item]
    base, T = p["base"], p["T"]
    if inventory < I0:
        amp = p["bt"] * base / _shape(p["bf"], T, T)
        px = base + amp * _shape(p["bf"], I0 - inventory, T)
    else:
        amp = p["at"] * base / _shape(p["af"], T, T)
        px = base - amp * _shape(p["af"], inventory - I0, T)
    return max(PRICE_FLOOR, int(round(px)))


def block_price(item, inventory, n):
    """Mean unit price of selling `n` units starting from `inventory` (walks the curve down)."""
    n = max(1, int(n))
    if n == 1:
        return float(price_at(item, inventory))
    tot, inv = 0.0, inventory
    step = 1 if n <= 24 else max(1, n // 24)
    got = 0
    while got < n:
        k = min(step, n - got)
        tot += price_at(item, inv) * k
        inv += k
        got += k
    return tot / n


def base_of(item):
    return MARKET[item]["base"]


# --------------------------------------------------------------------------- town demand

def shops_by_day(day):
    """Shop instances unlocked by the start of `day` (engine: one per 3 days, capped at 8)."""
    return min(MAX_SHOPS, day // SHOP_UNLOCK_EVERY)


def known_per_tick(good, shops):
    return sum(SHOP_UNITS[s].get(good, 0) for s in shops if s in SHOP_UNITS)


def drain_per_day(good, shops):
    """Units of `good` the town removes per day given the currently unlocked shop list."""
    return known_per_tick(good, shops) * SHOP_TICKS_PER_DAY + (1 if good in TOWN_CENTER else 0)


def remaining_drain(good, day, shops):
    """Units the town will remove from `day` through the end of the season.

    Shops already drawn are counted exactly; shops that will unlock later are counted at their
    expected basket contribution. This is the season pot the farm is competing for, and it is
    the number every acreage and head-count decision divides into.
    """
    n_now = len(shops)
    known = known_per_tick(good, shops)
    exp = EXP_PER_SHOP.get(good, 0.0)
    tc = 1 if good in TOWN_CENTER else 0
    total = 0.0
    for d in range(max(0, day), SEASON):
        extra = max(0, shops_by_day(d) - n_now)
        total += (known + extra * exp) * SHOP_TICKS_PER_DAY + tc
    return total


# --------------------------------------------------------------------------- yields

def animal_units(animal, placed_day, day, care=True):
    """Units an animal placed on `placed_day` will still produce from `day` onward.

    Engine: at the end of every day D the animal yields when
    `(D+1) - placed_day - first >= 0` and `((D+1) - placed_day - first) % interval == 0`,
    adding `min(max_held, 1 + pending_care_bonus)`. With daily CARE+FEED the bonus at a
    production day equals `interval`, so each yield is `min(max_held, 1 + interval)`.
    The last usable dawn is the start of day SEASON-1.
    """
    s = ANIMALS[animal]
    per = min(s["maxh"], 1 + (s["interval"] if care else 0))
    n = 0
    d = placed_day + s["first"]
    while d < SEASON:
        if d >= day:
            n += 1
        d += s["interval"]
    return n * per


def animal_daily_visits(animal, care=True):
    """FEED + CARE + COLLECT_FERTILIZER every day, HARVEST once per interval."""
    s = ANIMALS[animal]
    return 1 + (1 if care else 0) + 1 + 1.0 / max(1, s["interval"])


def crop_units(crop, day, fert=True):
    """Units one tile planted on `day` banks, 0 if it cannot finish in time."""
    c = CROPS[crop]
    if c["ongoing"]:
        n = 0
        d = day + c["first"]
        k = 0
        while k < c["maxy"] and d < SEASON:
            n += 1
            k += 1
            d += c["interval"]
        return n * (2 if fert else 1)
    if day + c["maxd"] > SEASON - 1:
        return 0
    gains = c["maxd"] - (c["maxd"] + 1) // 2 + 1
    return min(c["maxy"], 1 + gains * (2 if fert else 1))


def crop_cycle(crop):
    c = CROPS[crop]
    if c["ongoing"]:
        return c["first"] + c["interval"] * (c["maxy"] - 1) + 1
    return c["maxd"] + 1


def crop_daily_visits(crop):
    """Plant + waterings + harvests + fertilizes, amortised over the tile's cycle."""
    c = CROPS[crop]
    cyc = crop_cycle(crop)
    if c["ongoing"]:
        waters = len(water_ages(crop))
        harvests = c["maxy"]
        ferts = 2
    else:
        waters = len(water_ages(crop))
        harvests = 1
        ferts = 1
    return (1 + waters + harvests + ferts) / float(cyc)


_WATER_CACHE = {}


def water_ages(crop):
    """Ages on which the tile must be watered: every gain day, plus survival days.

    A plant dies at `consecutive_unwatered >= 2`, and PLANT sets it to 1, so the planting day
    itself must be watered. After that a gap of one day is safe and a gap of two is fatal.
    """
    if crop in _WATER_CACHE:
        return _WATER_CACHE[crop]
    c = CROPS[crop]
    if c["ongoing"]:
        gains = [c["first"] + i * c["interval"] for i in range(c["maxy"])]
        end = gains[-1]
    else:
        gains = list(range((c["maxd"] + 1) // 2, c["maxd"] + 1))
        end = c["maxd"]
    need = set(gains)
    need.add(0)
    ages = sorted(need)
    out, last = [], None
    for a in range(0, end + 1):
        if a in need:
            out.append(a)
            last = a
        elif last is not None and a - last >= 2:
            out.append(a)
            last = a
    _WATER_CACHE[crop] = out
    return out


def is_gain_age(crop, age):
    c = CROPS[crop]
    if c["ongoing"]:
        d = age - c["first"]
        return d >= 0 and d % c["interval"] == 0 and d // c["interval"] < c["maxy"]
    return (c["maxd"] + 1) // 2 <= age <= c["maxd"]


# --------------------------------------------------------------------------- geometry

def quadrant_of(x, y):
    half = BOARD // 2
    return ("N" if y < half else "S") + ("W" if x < half else "E")


def shed_tiles():
    half = BOARD // 2
    return [(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)]


SHED = set(shed_tiles())


def dist(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def nearest_shed(pos):
    return min(shed_tiles(), key=lambda t: dist(pos, t))
