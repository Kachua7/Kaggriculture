"""
Frozen engine numbers — the single source of truth shared by the agent and the mirror.

`engine.py` (the mirror simulator) and every module in `kagfarm/` import from here, so a
calibration fix lands in exactly one place and cannot leave the two out of step. That
matters more than it sounds: the entire tuning loop runs against the mirror, so a constant
that drifts between mirror and agent means thousands of episodes spent tuning a different
game from the one we submit into.

Nothing here imports from the mirror, and nothing outside the standard library is imported
at all, because this file ships inside submission.tar.gz.

Provenance is tagged on every block, because the four kinds are not equally trustworthy:

  [doc]     stated in the competition knowledge-transfer doc
  [fitted]  solved by us to reproduce a published 4-point table — right at the
            checkpoints, unverified between them
  [probed]  measured by driving the engine (calibration/mirror_truth.py)
  [real]    checked against a real 720-step episode from the official getting-started
            notebook (calibration/real_engine/tutorial_episode.json). This is the only
            tag that means "the actual engine did this", and it outranks [doc]: where the
            two disagreed, the replay was self-consistent and the doc was not.
  [open]    still unverified against the real engine; see PLAN.md §5.2
"""

from __future__ import annotations
import math

# ---------------------------------------------------------------------------
# Episode and board  [doc]
# ---------------------------------------------------------------------------

EPISODE_STEPS = 720
TURNS_PER_DAY = 24
SEASON_DAYS = EPISODE_STEPS // TURNS_PER_DAY          # 30
BOARD_SIZE = 10
STARTING_MONEY = 3000.0
MAX_MARKET_ORDERS = 10
SHED_CAPACITY = 100
WEED_SPAWN_CHANCE = 0.005
ACT_TIMEOUT_S = 1.0                                    # a single slow turn forfeits

TOWN_SHOP_UNLOCK_INTERVAL_DAYS = 3
TOWN_SHOP_SELL_INTERVAL_TURNS = 4
TOWN_CENTER_SELL_INTERVAL_TURNS = 12   # [real] not 24; see below
MAX_SHOP_INSTANCES = 8
FARM_HAND_COST_MULT = 1

LAND_PRICES = {"NE": 1000, "SW": 2000, "SE": 4000}     # BUY_LAND order
QUADRANT_ORDER = ("NE", "SW", "SE")
SHED_TILES = {"NW": (4, 4), "NE": (5, 4), "SW": (4, 5), "SE": (5, 5)}
FARMER_START = (4, 4)

CROPS_ONE_TIME = ("WHEAT", "CARROT", "MELON")
CROPS_ONGOING = ("TOMATO", "STRAWBERRY")
CROPS = CROPS_ONE_TIME + CROPS_ONGOING
ANIMALS = ("GOOSE", "COW", "SHEEP")
ANIMAL_PRODUCT = {"GOOSE": "EGG", "COW": "MILK", "SHEEP": "WOOL"}
ANIMAL_STRUCTURE = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}

# ---------------------------------------------------------------------------
# Object table  [real] — every crop number below is read off a real episode
# ---------------------------------------------------------------------------
#
# The growth rule, as the real engine actually implements it (traced tile-by-tile through
# calibration/real_engine/tutorial_episode.json, 23 plantings across both players):
#
#   * a tile is created with yield_units = start_yield and consecutive_unwatered = 1, so a
#     plant that is not watered on the day it goes in is dead at the next dawn. Planting and
#     watering are one atomic job, never two.
#   * WATER adds `1` (`2` fertilized) to yield_units **at the moment the action is taken**,
#     not at the end-of-day refresh, and only while `bonus_start <= age <= bonus_end`. The
#     unit is therefore harvestable the same day it is watered, which makes every one-time
#     cycle a full day shorter than an end-of-day model predicts.
#   * yield_units is clipped to max_yield_unfert without fertilizer, max_yield with.
#   * HARVEST is a no-op before first_yield_day even when yield_units > 0.
#   * one-time crops carry `max_lifespan_step = (planted_day + lifespan_days) * 24` and turn
#     into WEED there whatever their state. Ongoing crops carry -1 and expire instead after
#     their fourth scheduled yield.
#
# The melon row is where the doc and the engine part company, and it is the most expensive
# number in the game. The doc's Object Types table lists melon as first yield 10 / max yield
# 10 / max 6, which read as a gain window of 10..12 and gave 1 + 3 = 4 units at age 12. The
# engine's window opens at age **6**: the traced melon went y1 through age 5, then +1 on each
# of ages 6,7,8,9,10 to reach the cap of 6, and held 6 through ages 11 and 12. It was watered
# at ages 4 and 5 as well and gained nothing, so 6 is the first gain-day and not merely the
# first one observed. The doc's own prose says the same ("bonus window is ages 6-12, but base
# 1 plus one unit per watered day reaches the cap of 6 at age 10"), so the table cell is the
# part that is wrong.
#
#   melon, real      6 units per 10 tile-days, 8 waterings   0.60 units/tile-day
#   melon, as modelled  4 units per 12 tile-days, 8 waterings   0.33 units/tile-day
#
# so the mirror was undercharging melon by 1.8x on the crop carrying a quarter of revenue.
# It also means fertilizer does **nothing** for melon: unfertilized already reaches the
# max_yield of 6, and reaching it at age 8 instead of 10 buys nothing because first_yield_day
# blocks the harvest until 10. FERT_PLAN below is corrected to match.
#
# With `max_yield_day` read as **12** rather than the table's 10, the whole one-time family
# collapses to one rule and every measured number falls out of it:
#
#   bonus_start   = ceil(max_yield_day / 2)     <- the doc states this rule in prose
#   bonus_end     = max_yield_day
#   lifespan_days = max_yield_day + 1
#
#   crop      first  max  ->  bonus    lifespan   measured
#   WHEAT       2     4       2..4        5        mls = +120 turns = 5 days  ok
#   CARROT      2     3       2..3        4        mls = +96  turns = 4 days  ok
#   MELON      10    12       6..12      13        mls = +312 turns = 13 days ok
#
# The three redundant columns are kept rather than derived, because being able to see the
# arithmetic disagree is worth more than the DRY-ness, and because a future episode config
# could break the relation.
#
# start_yield=1 on the one_time crops is confirmed: every traced wheat, carrot and melon
# appears at yield_units 1 on its planting turn, and every tomato and strawberry at 0.

OBJECT_TABLE = {
    "WHEAT":      dict(seed_cost=10,  base_price=25,  first_yield_day=2,  max_yield_day=4,
                       bonus_start=2,  bonus_end=4,  lifespan_days=5,
                       max_yield=6, max_yield_unfert=4, kind="one_time", start_yield=1),
    "CARROT":     dict(seed_cost=20,  base_price=35,  first_yield_day=2,  max_yield_day=3,
                       bonus_start=2,  bonus_end=3,  lifespan_days=4,
                       max_yield=4, max_yield_unfert=3, kind="one_time", start_yield=1),
    "MELON":      dict(seed_cost=80,  base_price=250, first_yield_day=10, max_yield_day=12,
                       bonus_start=6,  bonus_end=12, lifespan_days=13,
                       max_yield=6, max_yield_unfert=6, kind="one_time", start_yield=1),
    "TOMATO":     dict(seed_cost=50,  base_price=60,  sched_days=[8, 9, 10, 11],
                       max_yield=4, kind="ongoing"),
    "STRAWBERRY": dict(seed_cost=100, base_price=120, sched_days=[10, 12, 14, 16],
                       max_yield=4, kind="ongoing"),
    "GOOSE":      dict(buy_cost=300, product="EGG",  base_price=50,  first_yield_day=4,
                       interval=1, max_held=4, structure="COOP"),
    "COW":        dict(buy_cost=400, product="MILK", base_price=160, first_yield_day=8,
                       interval=2, max_held=6, structure="PASTURE"),
    "SHEEP":      dict(buy_cost=500, product="WOOL", base_price=200, first_yield_day=6,
                       interval=3, max_held=6, structure="PASTURE"),
    "FERTILIZER": dict(buy_cost=100, base_price=100),
}

# ---------------------------------------------------------------------------
# Market price curve  [fitted] — the highest-value calibration target
# ---------------------------------------------------------------------------
#
#   price = base + sign * (target * base / f(T)) * f(|inventory - I0|)
#
# with a separate curve shape and target for the scarcity side (inventory < I0, price up)
# and the glut side (inventory > I0, price down), and a hard floor of $1.
#
# Every T and target below was SOLVED to reproduce a published 4-point price table, and the
# scarce half of the result is now confirmed exactly against a real episode -- see the note
# under the table. What is still open is the glut half:
#
#   MELON above (sq, 3.60, T=300)        sets the size of the melon pot (~$26k for the
#                                        whole game, shared) and where the $1 floor lands
#   STRAWBERRY above (linear, 1.60)      strawberry is the largest revenue line and the only
#                                        good the agent produces faster than the town drains
#
# See PLAN.md §5.2 items 1, 2 and 4.

I0 = 10000

MARKET_PARAMS = {
    #                  base       T   below curve/target      above curve/target
    "WHEAT":      dict(base=25,  T=400, below_f="sqrt",  below_t=0.80, above_f="log",    above_t=0.20),
    "CARROT":     dict(base=35,  T=450, below_f="log",   below_t=0.20, above_f="sqrt",   above_t=0.70),
    "TOMATO":     dict(base=60,  T=200, below_f="linear",below_t=0.40, above_f="sqrt",   above_t=0.60),
    "STRAWBERRY": dict(base=120, T=100, below_f="sqrt",  below_t=0.70, above_f="linear", above_t=1.60),
    "MELON":      dict(base=250, T=300, below_f="log",   below_t=0.20, above_f="sq",     above_t=3.60),
    "EGG":        dict(base=50,  T=332, below_f="linear",below_t=0.40, above_f="log",    above_t=0.20),
    "MILK":       dict(base=160, T=122, below_f="sqrt",  below_t=0.60, above_f="linear", above_t=1.60),
    "WOOL":       dict(base=200, T=105, below_f="log",   below_t=0.20, above_f="sq",     above_t=3.20),
    "FERTILIZER": dict(base=100, T=200, below_f="linear",below_t=0.40, above_f="linear", above_t=0.40),
}

# The BELOW column above is now [real], not [fitted]. The replay names market inventory and
# every price at all 720 steps, which gives 58-169 distinct (inventory, price) pairs per good
# on the scarce side -- the side the whole season is spent on, because the town drains faster
# than one farm can supply. `price_for` reproduces every one of those points exactly for
# WHEAT, STRAWBERRY, MELON, MILK and WOOL, which is the independent confirmation that solving
# the published 4-point table was the right move: strawberry (sqrt/0.70/T=100) and melon
# (log/0.20/T=300) carry ~90% of revenue and are exact at 169 and 58 real points.
#
# Two were wrong, and not because `hinge` is fake -- it is one of the engine's six shapes
# (`Kaggriculture_FINAL_KT.md` §2.7 quotes it from source as `u + 8*max(0,u-1)**2`). It is
# simply not the shape these goods use below I0; the 4-point table does not identify a curve
# uniquely and the solve picked wrong.
#   CARROT  was hinge/1.00, which missed 101 of 109 real points -- it predicted a flat 35
#           where the real market pays 36 after a single unit leaves. It is log/0.20.
#   TOMATO  was hinge/0.40, wrong on 19 of 121. `hinge` equals `linear` for drawdowns inside
#           T and then adds the quadratic kick; tomato's observed drawdown reaches 266
#           against T=200, so only the points past T were wrong. Plain `linear` is exact.
#   EGG     was also hinge/0.40 and scored 0/145 only because its drawdown peaked at 320,
#           just inside T=332, where hinge and linear coincide. Set to `linear`: identical
#           everywhere observed, and no quadratic waiting past T for a busier season.
# No good now uses `hinge` on either side. `_f` still implements it so this note stays
# checkable, and because a glut observation could yet put it back on the above side.
#
# The ABOVE column remains [fitted] and is the largest open calibration risk in the file.
# Market inventory never once rose above I0 in the replay -- the tutorial agent sold 30 melons
# into a town that drains 134 units a day -- so no glut point is observed. Every price our
# agent realizes when it floods a good (melon at 76.8% of base on 175 units) comes from
# `above_f`/`above_t`, and MELON's above curve is the steepest thing in the table (sq/3.60).
# The shapes there are the same four the below side just validated, which is weak evidence
# they are right. Real evidence needs a glut, and only self-play can produce one.

SELLABLE = list(MARKET_PARAMS.keys())      # anything can be SELL'd
BUYBACK = {"WHEAT", "FERTILIZER"}          # only these support BUY_PRODUCT

# ---------------------------------------------------------------------------
# Town demand  [real] — the reason prices sit ABOVE base all season
# ---------------------------------------------------------------------------
#
# Each open shop buys its basket every 4 turns whether or not anyone sells, and shops
# unlock one per 3 days up to 8. At full ramp that is ~134 units/day across all goods,
# against which one farm can supply 14-28%. So market inventory drifts BELOW I0 and prices
# drift ABOVE base — the town is a price pump, not a sink. PLAN.md §2.1.
#
# All eight baskets below were confirmed exactly, by differencing market inventory across
# the shop-only consumption ticks of a real episode as each shop came online: ICE_CREAM on
# day 3, YARN day 6, BRUNCH day 9, SMOOTHIE day 12, PIZZA day 15, PET_CAFE day 18, BAKERY
# day 21, FARMERS_MARKET day 24. Shops tick at hours 1,5,9,13,17,21 and the town centre at
# hours 1 and 13 — so `TOWN_CENTER_SELL_INTERVAL_TURNS` is 12, giving the town centre TWO
# units of every product a day, not one. The doc's configuration table says 24; the runtime
# configuration in the replay says 12 and the inventory deltas agree with the runtime.
#
# MELON is the exception that decides the competition: it is in no basket, so its only
# drain is the town centre's 2/day — 60 units for the whole season, shared between both
# players — and its price never recovers once pushed down.

SHOP_TABLE = {
    "BAKERY":         {"EGG": 1, "WHEAT": 1},
    "PIZZA_SHOP":     {"MILK": 1, "TOMATO": 1, "WHEAT": 1},
    "BRUNCH_SPOT":    {"EGG": 1, "WHEAT": 1, "STRAWBERRY": 1},
    "YARN_STORE":     {"WOOL": 2},
    "ICE_CREAM_SHOP": {"STRAWBERRY": 1, "MILK": 1, "WHEAT": 1},
    "PET_CAFE":       {"CARROT": 2},
    "SMOOTHIE_SHOP":  {"STRAWBERRY": 1, "MILK": 1},
    "FARMERS_MARKET": {"WHEAT": 1, "CARROT": 1, "TOMATO": 1, "STRAWBERRY": 1},
}

TOWN_CENTER_PRODUCTS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
                        "EGG", "MILK", "WOOL"]
TOWN_CENTER_TICKS_PER_DAY = TURNS_PER_DAY // TOWN_CENTER_SELL_INTERVAL_TURNS   # [real] 2

# ---------------------------------------------------------------------------
# Pure functions over the tables above  [doc]
# ---------------------------------------------------------------------------


def fib_hire_cost(n_already_hired_today: int) -> int:
    """Cost of the (n+1)-th hire today. Sequence 1,1,2,3,5,8,13,21,34,55,...

    Resets at dawn, so labour is cheap in absolute terms — ten hands is $143/day, $4,290
    for the season, against a five-figure book. Farm size is therefore a routing question,
    not a budget question. PLAN.md §2.5.
    """
    a, b = 1, 1
    for _ in range(n_already_hired_today):
        a, b = b, a + b
    return FARM_HAND_COST_MULT * a


def hire_cost_total(n_hands: int) -> int:
    """Total to field `n_hands` in one day."""
    return sum(fib_hire_cost(i) for i in range(n_hands))


def _f(kind: str, x: float, T: float) -> float:
    if kind == "linear":
        return x
    if kind == "sqrt":
        return math.sqrt(max(0.0, x))
    if kind == "sq":
        return x * x
    if kind == "log":
        return math.log(1 + x)
    if kind == "log10":
        return math.log10(1 + x)
    if kind == "hinge":
        u = x / T
        return u + 8 * max(0.0, u - 1) ** 2
    raise ValueError(f"unknown curve {kind}")


def price_for(resource: str, inventory: float) -> int:
    """Marginal price of one unit of `resource` at the given market inventory.

    Both players sell into the same inventory, which is what makes MELON a land-grab:
    see PLAN.md §2.3.
    """
    p = MARKET_PARAMS[resource]
    base, T = p["base"], p["T"]
    diff = inventory - I0
    if diff == 0:
        return round(base)
    if diff < 0:                                    # scarcity -> price up
        f_kind, target, sign = p["below_f"], p["below_t"], +1
    else:                                           # glut -> price down
        f_kind, target, sign = p["above_f"], p["above_t"], -1
    fT = _f(f_kind, T, T)
    amp = target * base / fT if fT != 0 else 0
    val = base + sign * amp * _f(f_kind, abs(diff), T)
    return max(1, round(val))


def expected_shop_drain_per_tick(good: str, day: int) -> float:
    """Units of `good` the town removes per drain tick on `day`.

    Shops unlock one per `TOWN_SHOP_UNLOCK_INTERVAL_DAYS` up to `MAX_SHOP_INSTANCES`, drawn
    from the eight types **without replacement** [real], so the expected per-shop basket is
    the mean basket while shops are still arriving and the total becomes *exact* from day 24,
    when all eight are open. Before then this is an expectation over which subset arrived, and
    the agent should prefer `drain_per_day_from_shops` on the observed list.
    """
    n_shops = min(MAX_SHOP_INSTANCES, day // TOWN_SHOP_UNLOCK_INTERVAL_DAYS)
    per_shop = sum(b.get(good, 0) for b in SHOP_TABLE.values()) / len(SHOP_TABLE)
    return n_shops * per_shop


def expected_drain_per_day(good: str, day: int) -> float:
    """Total daily drain: every shop tick plus the town centre's two units.

    Use this only to plan *before* the shops are known. Once the observation names the
    unlocked shops, `drain_per_day_from_shops` is exact, and early in the season the
    difference is large: which three shops arrived by day 9 decides whether strawberry is
    draining 18 units a day or 6. Averaging the basket washes that out and mis-sizes exactly
    the good we are about to over-plant.
    """
    ticks = TURNS_PER_DAY // TOWN_SHOP_SELL_INTERVAL_TURNS
    tc = TOWN_CENTER_TICKS_PER_DAY if good in TOWN_CENTER_PRODUCTS else 0.0
    return ticks * expected_shop_drain_per_tick(good, day) + tc


def drain_per_day_from_shops(good: str, shops) -> float:
    """Exact daily drain of `good` given the list of currently unlocked shop names.

    Summed over the list rather than over the distinct set, which costs nothing now that the
    draw is known to be without replacement [real] and keeps this correct if a future episode
    config does allow repeats. Unknown names are ignored rather than raising, because the real
    engine may ship shop types our table does not have; an unknown shop then understates the
    drain, which is the safe direction (we plant less than the town would have absorbed
    instead of gluting our own price).
    """
    ticks = TURNS_PER_DAY // TOWN_SHOP_SELL_INTERVAL_TURNS
    per_tick = sum(SHOP_TABLE[s].get(good, 0) for s in (shops or []) if s in SHOP_TABLE)
    tc = TOWN_CENTER_TICKS_PER_DAY if good in TOWN_CENTER_PRODUCTS else 0.0
    return ticks * per_tick + tc


def unlocked_shops_from_obs(obs) -> list:
    """Best-effort read of the unlocked-shop list out of an observation.

    The mirror puts it at obs["town"]["unlocked_shops"]; the real engine's field name is
    still open (PLAN.md §5.2 item 5), so this tries the plausible spellings and returns []
    rather than raising. [] makes `drain_per_day_from_shops` fall back to town-centre-only,
    which is the conservative floor.
    """
    if not isinstance(obs, dict):
        return []
    for container in (obs.get("town"), obs.get("market"), obs):
        if not isinstance(container, dict):
            continue
        for key in ("unlocked_shops", "shops", "open_shops", "shop_instances"):
            v = container.get(key)
            if isinstance(v, list) and all(isinstance(s, str) for s in v):
                return v
            if isinstance(v, dict):                      # {name: count} form
                out = []
                for name, n in v.items():
                    out.extend([name] * int(n or 0))
                return out
    return []


# ---------------------------------------------------------------------------
# Minimum watering schedules  [real] — re-derived from the verified growth rule
# ---------------------------------------------------------------------------
#
# Two engine rules pull against each other, and the gap between them is the single largest
# labour saving in the game:
#
#   survival   a plant dies when consecutive_unwatered hits 2, so watering every OTHER day
#              keeps it alive forever
#   growth     yield only rises on a day the tile was watered AND its age is inside the
#              crop's gain window (one_time: bonus_start..bonus_end; ongoing: sched_days)
#
# Outside the gain window a watering buys survival and nothing else, so the minimum schedule
# is: water on day 0 (forced — PLANT sets consecutive_unwatered = 1), then every second day
# until the window opens, then every day inside the window up to the harvest.
#
#   crop         cycle  gains at    minimum waterings        units  acts/tile-day  units/tile-day
#   WHEAT          5     2,3,4      0,2,3,4                    4        1.20          0.80
#   CARROT         4     2,3        0,2,3                      3        1.25          0.75
#   MELON         11     6..10      0,2,4,6,7,8,9,10           6        0.91          0.55
#   TOMATO        12     8..11      0,2,4,6,8,9,10,11          4        0.83          0.33
#   STRAWBERRY    17     10,12,14,16 0,2,4,6,8,10,12,14,16     4        0.65          0.24
#
# The last column is the check that these are right: it reproduces the competition doc's
# published "Yield / tile / day" column for all five crops to the digit. The previous melon
# row (harvest at 12 for 4 units) gave 0.31 against a published 0.55, which was the doc
# disagreeing with itself in plain sight.
#
# Melon is the row that moved: its window opens at age 6, not 10, so it banks 6 units on the
# day of its fifth in-window watering — age 10, which is also the first day HARVEST is legal.
# Nothing is gained by holding it to 12.
#
# Note that an equal-length alternative phase exists for the long crops (melon can run
# 0,1,3,5,6,7,8,9,10 instead of 0,2,4,6,7,8,9,10 at the cost of one extra visit). The planner
# can use that to de-synchronise tiles planted on the same day, which matters because these
# rates are cycle AVERAGES — 35 strawberry tiles planted together have their watering days
# coincide, and the peak day needs about double the mean.

CROP_PLAN = {
    "WHEAT":      dict(harvest_day=4,  units=4, water_days=(0, 2, 3, 4)),
    "CARROT":     dict(harvest_day=3,  units=3, water_days=(0, 2, 3)),
    "MELON":      dict(harvest_day=10, units=6, water_days=(0, 2, 4, 6, 7, 8, 9, 10)),
    "TOMATO":     dict(harvest_day=11, units=4, water_days=(0, 2, 4, 6, 8, 9, 10, 11)),
    "STRAWBERRY": dict(harvest_day=16, units=4,
                       water_days=(0, 2, 4, 6, 8, 10, 12, 14, 16)),
}


def crop_cycle_days(crop: str) -> int:
    """Plant-to-harvest inclusive, so 30 // cycle is completed cycles per season."""
    return CROP_PLAN[crop]["harvest_day"] + 1


def crop_actions_per_cycle(crop: str) -> int:
    """PLANT + minimum waterings + one HARVEST. One tile-visit each."""
    return 2 + len(CROP_PLAN[crop]["water_days"])


def crop_actions_per_day(crop: str) -> float:
    return crop_actions_per_cycle(crop) / crop_cycle_days(crop)


# ---------------------------------------------------------------------------
# Fertilizer  [probed] — analysis/fert_probe.py, melon row corrected [real]
# ---------------------------------------------------------------------------
#
# A dose does two things: `gain = 2 if fertilized else 1` on every gain-day, and for one_time
# crops it raises the ceiling from `max_yield_unfert` to `max_yield`. Ongoing crops have no
# `max_yield_unfert` at all, which reads as "fertilizer does nothing for strawberry" -- but
# `max_yield` caps *standing* units, not lifetime ones, and HARVEST on an ongoing crop banks the
# yield and leaves the plant alive. So the doubled gains do land, as long as somebody empties the
# tile before the cap clips them.
#
# One dose covers four nights (`fertilized_until_day = day + 3`), so the dose count is set by how
# far apart the crop's gain-days are spread, and the timing matters more than the amount: dosing
# before the first gain-day wastes the unit outright.
#
#   crop         plain    fertilized   doses  extra visits   extra $ at base   per extra visit
#   WHEAT        4u        6u            1      1             +$50               -$50
#   CARROT       3u        4u            1      1             +$35               -$65
#   MELON        6u        6u            —      —              $0                 n/a
#   TOMATO       4u        7u            1      2             +$180              +$40
#   STRAWBERRY   4u        7u            2      3             +$360              +$53
#
# Wheat and carrot lose money at $100 a dose: their whole harvest is worth less than the
# fertilizer. Tomato and strawberry need the mid-cycle harvest to collect at all, and at their
# realized prices (181% and 241% of base) they clear comfortably.
#
# **Melon's row went to zero and that is a real loss, not a correction of a rounding error.**
# This block used to read "a melon FERTILIZE is worth about four melon PLANTs per visit", which
# made it the single best action on the board. It was an artifact of the wrong growth window:
# with a gain window believed to be 10-12, three doubled gains took 4u to 6u. The real window is
# 6-12, so the plain crop already collects `max_yield_unfert = max_yield = 6` — there is no
# higher ceiling to unlock and no extra gain-day to double. Fertilizer buys melon exactly one
# thing, reaching 6 units at age 8 instead of age 10, and `first_yield_day = 10` blocks the
# harvest until 10 anyway. `fert_units=0` makes the policy's margin test refuse it, which is
# what we want: melon FERTILIZE is now a $100 no-op that also costs a market slot and a visit.
#
# `fert_units` is the EXTRA units, so the decision rule is
# `fert_units * marginal_price(crop) > dose_cost * fert_margin`, priced at the market the extra
# volume will actually meet rather than at base.

FERT_PLAN = {
    "WHEAT":      dict(fert_units=2, doses=1, visits=1),
    "CARROT":     dict(fert_units=1, doses=1, visits=1),
    "MELON":      dict(fert_units=0, doses=0, visits=0),
    "TOMATO":     dict(fert_units=3, doses=1, visits=2),
    "STRAWBERRY": dict(fert_units=3, doses=2, visits=3),
}


def gain_days(crop: str) -> tuple:
    """Ages at which WATER can add yield to this crop.

    Read off OBJECT_TABLE rather than tabulated, because the two crop kinds spell it
    differently: one_time crops give a closed range, ongoing crops an explicit list.

    [real] The one_time range is `bonus_start..bonus_end`, NOT
    `first_yield_day..max_yield_day`. Those two coincide for wheat and carrot, which is why
    the old reading survived so long, and they are 6..12 versus 10..10 for melon, which is
    why it was wrong by 1.8x on the crop carrying a quarter of revenue. `first_yield_day`
    gates HARVEST, not growth.
    """
    spec = OBJECT_TABLE.get(crop)
    if not spec:
        return ()
    if spec.get("kind") == "one_time":
        return tuple(range(spec["bonus_start"], spec["bonus_end"] + 1))
    return tuple(spec.get("sched_days") or ())


def fert_gain(crop: str) -> int:
    """Extra units one full fertilized cycle banks over an unfertilized one."""
    return FERT_PLAN.get(crop, {}).get("fert_units", 0)


def fert_doses(crop: str) -> int:
    """Doses that cycle needs, given four nights of cover each."""
    return FERT_PLAN.get(crop, {}).get("doses", 1)


def yield_cap(crop: str, fertilized: bool) -> int:
    """The ceiling `_refresh_plant` clips `yield_units` to tonight."""
    spec = OBJECT_TABLE.get(crop) or {}
    if spec.get("kind") == "one_time" and not fertilized:
        return spec.get("max_yield_unfert", spec.get("max_yield", 1))
    return spec.get("max_yield", 1)


def needs_water(crop: str, age_days: int) -> bool:
    """Is today one of `crop`'s minimum watering days, `age_days` after planting?

    Past the end of the schedule the answer is False: the tile is either being harvested
    today or already decaying, and watering a decaying tile does not recover a unit.
    """
    plan = CROP_PLAN.get(crop)
    if not plan:
        return False
    return age_days in plan["water_days"]


def tile_visits_per_unit_day(commute_moves: float) -> int:
    """Tile-visits one unit can complete in a day, given a one-way walk to its run.

    A serpentine sweep costs `commute + T actions + (T-1) moves <= TURNS_PER_DAY`. One way,
    not a round trip: `_day_refresh` deletes the hand roster where it stands and dumps every
    carried inventory into the shed first, so nothing ever walks home. Charging a return leg
    halves the farm for no reason.
    """
    return max(0, int((TURNS_PER_DAY - commute_moves + 1) // 2))





