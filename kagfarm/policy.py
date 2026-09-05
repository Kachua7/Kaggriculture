"""
The policy: one full-day plan at dawn, then a cheap self-correcting step every turn.

Three engine facts set the whole shape of this file.

  The roster resets at midnight.  `_day_refresh` runs `f.hands = []`, `f.hires_today = 0`,
  `f.farmer = FARMER_START`. So there is no such thing as a multi-day route: every dawn the
  farm starts over with everybody standing on the shed, and the Fibonacci hire bill is paid
  again. A day is the natural planning unit, and the commute out to the work is a cost paid
  30 times, not once.

  A turn is one op OR one move.  Which makes routing, not economics, the binding constraint
  on farm size. See `route.py` for the arithmetic; the consequence here is that the planner
  commits each unit to one contiguous serpentine run and does not re-decide mid-day.

  Market orders are free.  `_apply_market_actions` is a separate pass from the unit ops, so
  SELL costs no unit turns and can fire on all 24 turns. The 100-item shed is therefore a
  turnstile rather than a warehouse, and the only way to lose harvest is to still be carrying
  it when the day ends (and on the final day, `_day_refresh` never runs at all, so anything
  carried at step 720 is simply gone).

Everything tunable is in `PARAMS` so Phase 4 can sweep it without touching the logic.
"""

from __future__ import annotations

import time

from .constants import (ANIMAL_PRODUCT, ANIMAL_STRUCTURE, ANIMALS, BOARD_SIZE, CROP_PLAN, CROPS,
                        FERT_PLAN, I0, LAND_PRICES, MARKET_PARAMS, MAX_MARKET_ORDERS, OBJECT_TABLE,
                        QUADRANT_ORDER, SEASON_DAYS, SHED_CAPACITY, SHED_TILES, TURNS_PER_DAY,
                        crop_actions_per_day, drain_per_day_from_shops, fert_doses, fert_gain,
                        fib_hire_cost, gain_days, needs_water, price_for, unlocked_shops_from_obs,
                        yield_cap)
from .route import (MOVES, capacity, manhattan, nearest_shed, serpentine_key, split_runs,
                    step_toward)

# ---------------------------------------------------------------------------
# Tunables. Phase 4 sweeps these; nothing below reads a magic number directly.
# ---------------------------------------------------------------------------

PARAMS = dict(
    # The crops the allocator is allowed to consider, and a soft acreage prior over them.
    # `mix_cap` scales the prior into a hard per-crop ceiling. Above about 12 the ceiling never
    # binds at all and the proportions here are inert -- `_targets` allocates every tile by
    # marginal value instead, which is worth $13k a season over trusting the proportions: they
    # came from analysis/portfolio.py, which optimises terminal bank without modelling the price
    # impact of its own volume, and so asks for 24 melon tiles feeding a market that pays well
    # for about ten. At 6.0 the mean is unchanged and the tails are better (p10 $48.1k vs
    # $47.5k, min $46.6k vs $46.3k), which is the cheapest kind of improvement: the cap only
    # binds on the seeds where marginal allocation had run away with one crop.
    # TOMATO is deliberately absent, and it is the largest single measured gain in this table.
    # It was 74 of 109 thirst deaths across six seeded episodes -- 68% of the most expensive
    # failure the agent has -- and the reason is structural, not a scheduling bug to be fixed.
    # Tomato wants water on days 0,1,3,5,7,8,9,10 of an 11-day cycle, four of them consecutive,
    # so two missed visits anywhere in that run kill it; and at $60 base for 4 units it is the
    # cheapest crop the allocator would plant, so its waterings sort last at TIER_GROW and are
    # exactly the ones that fall off a full day. Worst crop on the board and the most fragile,
    # which is the combination that makes it a trap. Dropping it: mean $88,286 -> $89,418,
    # p10 $54,871 -> $60,527, min $42,917 -> $45,290, thirst 16.5 -> 5.5 plants an episode.
    # MELON is not optional -- without it the farm scores $37k -- and WHEAT earns its place in
    # the tails rather than the mean: dropping it raises the mean another $1k and costs $9k of
    # p10, because wheat's four-day cycle is what funds the first strawberry.
    mix={"WHEAT": 9, "CARROT": 3, "MELON": 24, "STRAWBERRY": 33},
    # The ceiling binds again now that tomato is gone -- with five crops it never did, which is
    # why this was 100.0 and inert. On 144 episodes 3.0 is +$284 mean, +$688 p10, +$668 min:
    # small, but the only candidate out of a fifteen-axis sweep that improved all three.
    #
    # Re-swept 2026-09-05 after a probe showed days 1-9 run 24 of the starting quadrant's 25
    # tiles as MELON -- the one crop in no shop basket, whose only buyer is the town centre's
    # 2/day. That looked like the next big win and it is not one. The opening monoculture is
    # load-bearing:
    #
    #     mix_cap   0.6 -> $26,677     1.0 -> $30,618     1.5 -> $87,143
    #               2.0 -> $86,777     3.0 -> $86,476   100.0 -> $86,816
    #
    # Capping melon to 8.7 opening tiles (1.0) costs FIFTY-SIX THOUSAND DOLLARS. Melon is what
    # funds the strawberry board; nothing else pays before day 12. Every cell from 1.5 up is
    # within noise of every other, holdout included (1.5 is +$458 mean on unseen seeds), so the
    # incumbent stays. The 76.8%-of-base melon price is not a bug to fix, it is the price of the
    # opening -- and once the land unlocks on day 11 the marginal allocator drops melon to under
    # 8 tiles on its own, exactly as `marginal_rank` claims it should. This axis is closed.
    mix_cap=3.0,               # per-crop acreage ceiling, as a multiple of its share of the mix
    max_hands=10,            # roster cap. The 13th hand costs $233/day, the 18th $2,584.
                             # Was 8, where every larger roster measured as a loss -- because
                             # hands hired after the hour-1 re-cut got no route and PASSed all
                             # day. With the growth-triggered re-cut in `_act`, 10 is +$5,709
                             # mean / +$3,827 p10 on seeds 0-47 and +$5,293 / +$3,904 on the
                             # disjoint 48-95, both 144 episodes against a ~$1k standard error.
    # ---------------------------------------------------------------------------------------
    # THE PEER RETUNE. Everything below marked `[peer]` was moved by a coordinate descent run
    # against `--opps self` on the win-fraction objective, not against the built-in agents. It
    # is the single largest change in the project and it is worth reading the reason.
    #
    # All three built-in opponents lose 144/144, so every number tuned against them was tuned
    # in a market with one serious seller. Put the real policy in seat 1 and the season pays
    # **$21,809 instead of $87,000**, because both farms drain one shared order book. The old
    # cell was not a strong policy that happened to score well; it was a policy fitted to an
    # uncontested market, and it collapses in a contested one.
    #
    # The retuned cell, measured (see `analysis/descent.py`, `analysis/blocks.py`):
    #
    #   regime                                 old cell            this cell
    #   vs starter/heuristic/random, 432 eps    $87,345             $87,069      -$276
    #   vs a peer running the OLD cell, 144     $21,829 / 42%       $71,228 / 100%  +$49,399
    #   both seats running THIS cell, 144       $21,235 / 50%       $50,579 / 53%   +$29,345
    #
    # Three things make this adoptable rather than a panel artifact. It replicated on a 96-seed
    # holdout the descent never saw (+55.2pp win, +$49,684). It won every one of three disjoint
    # blocks in both peer regimes. And the third row is the one that matters most: the gain is
    # NOT exploitation of the old policy's specific weakness, because it survives mutual
    # adoption -- if the whole field played this cell the mirror would pay 2.4x what it does now.
    #
    # The cost is $276 an episode against opponents that do not compete, still 144/144 wins on
    # every block. `analysis/blocks.py` prints REJECT for that panel and it is right to; the
    # decision is a two-panel trade and the peer panel is 180x larger.
    # ---------------------------------------------------------------------------------------
    seed_alpha=0.5,          # 0 = fund seeds by $/tile-visit, 1 = by $/seed-dollar. [peer] 0.0
                             # -> 0.5 is +13.5pp win / +$16,871 alone on the holdout, the second
                             # largest single move. Under contention the binding constraint stops
                             # being tile-visits and becomes CASH: the opponent is bidding the
                             # same land away, so ranking seed spend by return per dollar rather
                             # than per visit buys the quadrant first. Against weaklings there is
                             # no race, which is why this axis measured flat for weeks.
    reserve=1.10,            # stop selling a good below this fraction of its base price...
    crowded=0.55,            # ...unless the shed is this full, when refusing a sale destroys it
    always_sell=("MELON",),  # goods no shop ever buys: the price never recovers, so never hold
    land_margin=1.20,        # cash multiple over the land price before buying a quadrant
    plan_ms=250.0,           # wall-clock ceiling for one dawn plan; falls back to the old plan
    weed_dig=True,           # clear weeds so the tile can be replanted
    # Market-order slot budget. Ten orders a turn, and HIRE spends one per hand, so a full
    # roster would eat the lot -- these two hold seed and sales out of its reach.
    seed_slots=2,            # BUY_SEED carries a quantity, so two slots is two crops. [peer] 3
                             # -> 2 is worth -$19 on its own, i.e. nothing; it is in the cell
                             # because the seven-axis cell measured $609 BETTER than the
                             # four-axis one on the built-in panel, consistently across blocks.
    hire_hours=4,            # keep re-attempting deferred hires this far into the day
    seed_grace=1,            # hours a PLANT job waits for its seed before being dropped. [peer]
                             # 3 -> 1, and exactly $0 on its own -- same justification as above.
    # Acreage ceiling as a multiple of the roster's daily tile-visits. Below 1.0 the farm plants
    # less than it can water; measured, that trade is close to flat between 1.0 and unconstrained
    # ($62.8k vs $62.2k on the 48-episode panel) and it halves deaths by thirst, so 1.0 is the
    # cheap insurance rather than a win. Most of what `eval.py` counts as "weeds" is not thirst
    # at all but plants that finished their schedule and decayed -- see analysis/weed_probe.py.
    labour_slack=1.2,        # [peer] 1.0 -> 1.2, +$141 alone. Part of the seven-axis cell.
    # Fertilizer. One dose doubles the units added on every gain-day it covers, and for one_time
    # crops raises the ceiling as well. Measured per tile-cycle (analysis/fert_probe.py): melon
    # +2 units for one dose and one visit, tomato +3, strawberry +3, wheat and carrot negative.
    # `fert_margin` is the gross-to-cost ratio a dose must clear at the marginal price its extra
    # units will actually meet -- not at base, because the extra volume is the thing that moves
    # the price. Worth $7k a season on the 48-episode panel ($62.8k -> $69.8k).
    fert=True,
    fert_margin=3.0,
    # Standing dose buffer. Sharply peaked, and not for the reason you would guess: the shed
    # holds 100 items across every good, so a large buffer starts destroying harvest at midnight.
    # Measured means at margin 1.6: 8 -> $66.5k, 16 -> $69.6k, 40 -> $56.9k, 60 -> $46.5k.
    # [peer] 24 -> 8, worth +$11,399 of bank on its own against a peer while COSTING 11.5pp of
    # win rate alone -- the two objectives disagree on this axis and only the combination is
    # positive on both. Under contention shed slots are scarcer and cash is tighter, so a
    # 24-dose buffer is capital and storage spent on a crop bonus the farm cannot yet fund.
    fert_stock=8,
    # How much of the town's drain over a tile's growing period to credit when pricing that
    # tile. The drain itself is exact -- the observation names the unlocked shops and the
    # engine's baskets are known -- but the opponent sells into the same inventory, so
    # crediting all of it plants against a market someone else is also filling. See
    # `horizon_head`; 0.0 reproduces the old spot-priced behaviour exactly.
    drain_frac=1.0,
    # Ceiling on a planting price, in multiples of base. Needed because the drain lookahead
    # pushes inventory below I0 and `price_for` is unbounded down there -- EGG at zero prices
    # at $136,333. Realized strawberry is 228% of base, so this binds only on fantasy.
    px_cap=2.0,
    # Days at the end of the season on which the reserve floor comes off and the input buffer
    # is liquidated. Produce in the shed scores nothing at step 720, so the error is one-sided:
    # selling a day early costs the reserve-floor premium on one day's stock, holding a day too
    # long costs the stock. Five, and the reason is not the premium at all -- it is that the last
    # strawberry cohort ripens across days 25-30 and a reserve floor during that wave leaves the
    # produce sitting in the shed and the bags with nowhere to go, which is what the haul
    # discipline then has to spend commutes rescuing. Opening the taps five days out clears the
    # shed ahead of the wave instead. Measured on 144 episodes and replicated on the disjoint
    # 144: mean $79.8k -> $85.9k train, $80.8k -> $87.0k held-out, p10 +$4.2k/+$4.4k, and the
    # curve is single-peaked -- 4 is $2.4k worse, 6 is $1.0k worse, 8 gives back half the gain.
    endgame_days=5,
    # Livestock. Structures are free (`BUILD_PASTURE` only requires an empty tile); the cost is
    # the animal, the feed and the visits. Measured on one tile for a full season
    # (`analysis/animal_probe.py`), the best programme is minimum feeding plus daily collection:
    #
    #   animal  prod  fert  visits  wheat   net $/visit at realized prices
    #   COW       11    29      49     15         $96
    #   SHEEP      8    29      49     15         $80
    #   GOOSE     26    29      54     15         $67
    #
    # against melon at $81 and strawberry at $95, so a cow is the best per-visit return on the
    # board. Two findings shape the programme. Feeding does nothing for yield -- `_refresh_animal`
    # gives `base_gain = 1` fed or not, and the care bonus only accrues on non-production days --
    # so feed only to stop the animal escaping at two consecutive misses, which is every other
    # day. And CARE is a trap: on a cow it buys 5 extra units for 35 extra visits.
    #
    # Most of the value is the byproduct. `fertilizer_available` is set every day for any
    # surviving animal regardless of fed or cared, and the farm buys 97 doses a season at a
    # measured mean of $110, so each collection visit is worth $110 -- the best rate on the
    # board, and the reason the count is 3: three animals collect 87 doses and the credit
    # collapses to the product-only rate ($76/visit on a cow) once the fertilizer bill is gone.
    # ON at one animal, measured 2026-09-05 on three DISJOINT 144-episode panels. The old note
    # here said "off, measured" on the strength of a 48-episode panel taken before the engine
    # calibration; re-run after it, one animal improves every metric on every block:
    #
    #     seeds     n=0 mean    n=1 mean    d_mean   d_p10    d_min   lost 0 -> 1
    #       0-47     $85,852     $86,575      +723    +728   +1,300   16.1 -> 12.2
    #      48-95     $86,984     $87,810      +826  +1,265   +1,836   13.4 ->  8.7
    #     96-143     $86,730     $87,651      +921  +1,108     +629   10.8 ->  9.0
    #
    # Three blocks agreeing in sign on mean, p10, min AND spoilage is the strongest signal this
    # harness can produce; ~+$820 is under the $1k standard error on any one panel, which is
    # exactly why it took three. TWO animals is not adoptable and the contrast is the useful
    # part: +$757, +$868, then -$391. It fails the same way the old 48-episode reading did, and
    # for the reason already written below -- the fertilizer bill is only ~97 doses a season, so
    # the second animal's stream is largely unsold surplus that still costs shed slots.
    #
    # The `lost` column is the surprise. An animal REDUCES spoilage, which was not the case made
    # for it: the collection visit routes a hand past the shed more often, so bags get banked
    # before the day-27 wave. It is the same mechanism as the haul discipline above, arrived at
    # from the other direction.
    #
    # One caveat stands, and it is the one `bash bootstrap.sh` settles: the whole case rests on
    # `_refresh_animal` setting `fertilizer_available` daily and unconditionally, which is a
    # MIRROR fact. If the real engine gates that dose the gain shrinks. Bounded downside (~$800)
    # against a consistent p10 gain, so it goes in now and gets re-checked against real source.
    #
    # **[peer] 1 -> 2.** The rejection above stands for the built-in panel -- two animals really do
    # cost $638 there, and the reason given is right: ~97 doses a season is one animal's work, so
    # the second one's output is surplus occupying shed slots. Against a peer it is +5.2pp of win
    # rate and +$2,398, the smallest of the four real moves in the retune. What changes is what
    # the surplus is FOR: milk is the one good on the board the opponent is not flooding, so a
    # second stream of it is revenue that does not have to fight for the order book. The `lost`
    # objection also weakens once `haul_trigger` is 0.55, because bags no longer wait for midnight.
    n_animals=2,
    # A structure has to beat this many dollars per visit to be worth building, judged against
    # the crop it displaces. Melon realizes $81 a visit, which is the number to beat -- but the
    # rank is computed from the shop list as it stands, and on day 0 no shop has opened yet, so
    # the drain credit that makes milk worth $229 rather than $160 is not in it. A cow scores $79
    # at dawn on day 0 and $96 by mid-season; the margin sits below the pessimistic end so the
    # programme starts on day 0, where the fertilizer stream is worth 29 doses instead of 15.
    animal_margin=60.0,
    # Visits a day charged against the crop allocation for each structure the farm owns. Zero,
    # measured: the honest rate is 1.6, and charging it cost $30k a seed by shrinking the farm
    # to make room for work the animals then failed to fill. See `_targets`.
    animal_load=0.0,
    # Wheat held back from sale per animal owned or on order, so the feed is in the shed on the
    # day the PLACE lands. Zero falls back on `BUY_PRODUCT WHEAT`, which settles a turn late.
    feed_hold=6,
    # -- haul discipline. See `_haul_pressure` and the block in `_unit_ops`.
    # Shed slots that shed contents plus every carried bag must fill before a unit will
    # interrupt its run to walk produce home, as a multiple of the 100-slot cap. Two, which
    # is far looser than it looks like it should be and is the whole lesson of this axis.
    # Hauling early is a losing trade: on a normal day midnight banks every bag into the shed
    # for free, so a shed trip buys nothing and costs a 3-5 turn commute out of a day that is
    # already routing-bound. Measured on 48 episodes, tightening this to 0.55 -- the threshold
    # `crowded` uses to force full sells -- drove `lost` to exactly 0.0 and the mean DOWN from
    # $73.6k to $64.0k, with thirst units up 14 -> 90 as the commutes ate the waterings. The
    # loss worth preventing is not spoilage in general, it is the one catastrophic dump at the
    # end of the season, and that only happens when the bags hold multiples of the shed.
    #
    # **[peer] All of that is true against opponents that do not compete, and it is the wrong
    # answer against one that does.** 2.00 -> 0.55 is the single largest move in the peer retune:
    # +25.0pp of win rate and +$21,351 of bank on the 96-seed holdout, on its own. Both readings
    # are correct and the mechanism is the same one from opposite ends. Against a weakling the
    # order book is still there at midnight, so waiting for the free dump is right and the commute
    # is pure waste. Against a peer the book is being drained hour by hour, so produce sitting in
    # a bag is produce sold at the price the opponent leaves behind -- the commute buys the spread,
    # and it buys it every day rather than once on day 28. The old figure quoted here ($73.6k ->
    # $64.0k, thirst 14 -> 90) was measured pre-calibration and re-measured at $85,015 with thirst
    # 75.8 -> 78.0; the direction held, the magnitude was 14x off. Cost against the built-ins is
    # real but small, and `lost` falls 12.2 -> 9.6 as a side effect.
    haul_trigger=0.55,
    # Units in one bag before that trip is worth its commute. Sharp on the high side: at 28 the
    # condition essentially never fires (mean falls back to $73.7k) because no single unit ever
    # carries that much. The plateau is 14-22, flat to about $1k across it.
    haul_min=18,
)

_ONE_TIME = {c for c in CROPS if OBJECT_TABLE[c]["kind"] == "one_time"}

# Goods the farm buys as inputs and must never sell. FERTILIZER is tradeable in both directions
# and sits in the same shed as the harvest, so without this it would be offered back to the
# market the turn after it was bought -- a round trip that loses the spread and, worse, empties
# the buffer the fertilize jobs are routed against.
_INPUTS = {"FERTILIZER"}

# Key under which feed grain is tracked in `_unit_ops`'s shared stock dict. Prefixed so it cannot
# collide with the WHEAT *seed* count in the same dict.
_FEED = "@WHEAT"


def _base(good):
    return MARKET_PARAMS[good]["base"]


def quadrant_of(x, y):
    if x < 5 and y < 5:
        return "NW"
    if x >= 5 and y < 5:
        return "NE"
    if x < 5 and y >= 5:
        return "SW"
    return "SE"


# ---------------------------------------------------------------------------
# Observation reading, defensively
# ---------------------------------------------------------------------------
#
# The mirror hands back the live tile dicts, so `consecutive_unwatered`, `planted_day` and
# `yield_units` are all readable. The real engine may expose less. Every accessor below has a
# fallback that reconstructs the field from `planted_day` and CROP_PLAN, so a missing key costs
# accuracy rather than raising inside a 1-second turn budget.


def tile_age(tile, day):
    pd = tile.get("planted_day")
    return (day - pd) if pd is not None else 0


def will_die_tonight(tile, day):
    """True if this tile reaches consecutive_unwatered == 2 at midnight and turns to weed.

    PLANT sets the counter to 1, a watered night resets it to 0, an unwatered night adds 1.
    So a tile showing 1 and not yet watered today is one skipped watering from dead, and that
    is the single most expensive job class on the board: skipping it forfeits the tile's whole
    remaining cycle, not one unit of yield.
    """
    if tile.get("watered_today"):
        return False
    cu = tile.get("consecutive_unwatered")
    if cu is None:
        # No counter in the observation: fall back to the planned schedule, which by
        # construction never leaves two consecutive dry nights.
        return needs_water(tile.get("crop", ""), tile_age(tile, day))
    return cu >= 1


def harvestable(tile, day):
    """Yield is banked and the engine's first_yield_day gate has opened."""
    if tile.get("yield_units", 0) <= 0:
        return False
    spec = OBJECT_TABLE.get(tile.get("crop"))
    if not spec:
        return False
    first = spec.get("first_yield_day")
    if first is None:
        first = spec.get("sched_days", [0])[0]
    return tile_age(tile, day) >= first


def harvest_plan(tile, day):
    """None, or the `(op, then)` pair that banks this tile's yield today.

    Ordering is the entire content of this function, and it exists because the yield bonus
    lands inside the WATER action rather than at midnight. A melon on the morning of age 10 is
    holding 5 units of a possible 6: harvest it and the sixth is gone, water it first and the
    same visit collects all six. Two ops on one tile cost two turns and zero movement, which
    the router already models as `acts=2` — the same mechanism PLANT+WATER uses.

    Three cases, all of them worth real money:

      water then harvest   the common one. Today is a gain-day and the crop is not at its cap,
                           so the last watering is part of the harvest. Every row of CROP_PLAN
                           is built to land here: wheat at age 4, carrot at 3, melon at 10,
                           strawberry at 16. Harvesting first would forfeit a unit on all four.
      harvest then water   a fertilized ongoing crop whose standing yield plus tonight's
                           doubled gain would overflow `max_yield`. HARVEST empties the tile
                           and leaves the plant, so the doubled gain fits — this is the only
                           reason fertilizer pays on strawberry and tomato at all.
      harvest             nothing left to gain today.
    """
    if not harvestable(tile, day):
        return None
    crop = tile.get("crop")
    plan = CROP_PLAN.get(crop)
    if not plan:
        return ["HARVEST"], None
    age = tile_age(tile, day)
    fert = tile.get("fertilized_until_day", -1) >= day
    cap = yield_cap(crop, fert)
    gain = 2 if fert else 1
    on_gain_day = age in gain_days(crop) and not tile.get("watered_today")

    if age >= plan["harvest_day"]:
        if on_gain_day and tile.get("yield_units", 0) < cap:
            return ["WATER"], ["HARVEST"]
        return ["HARVEST"], None

    # Before the planned harvest day the tile is still growing, and the only reason to touch it
    # is the overflow case: emptying it now converts a gain that would have been clipped.
    if (OBJECT_TABLE.get(crop, {}).get("kind") == "ongoing" and fert and on_gain_day
            and any(d > age for d in gain_days(crop))
            and tile.get("yield_units", 0) + gain > cap):
        return ["HARVEST"], ["WATER"]
    return None


def ready_to_harvest(tile, day):
    """Back-compat predicate: is any harvest scheduled for this tile today?"""
    return harvest_plan(tile, day) is not None


def fert_value(tile, day, prices, pipe=None):
    """Dollars the next dose on this tile buys, or 0 if a dose does nothing for it.

    A dose covers four nights, so it is only worth a visit on the morning of a gain-day it
    would otherwise miss: applied a day late it buys nothing for that day, and applied early it
    expires before the gain window opens. Priced per *remaining* gain-day rather than per cycle,
    because a tile two thirds of the way through has fewer doublings left to sell.
    """
    crop = tile.get("crop")
    if crop not in FERT_PLAN or tile.get("fertilized_until_day", -1) >= day:
        return 0.0
    days = gain_days(crop)
    if not days:
        return 0.0
    age = tile_age(tile, day)
    if age not in days:
        return 0.0
    # Gain-days this one dose reaches, and therefore doublings it actually pays for.
    covered = sum(1 for d in days if age <= d <= age + 3)
    if covered <= 0:
        return 0.0
    plan = FERT_PLAN[crop]
    per_dose = fert_gain(crop) / max(1, fert_doses(crop))
    scale = covered / max(1, len(days) / max(1, fert_doses(crop)))
    return per_dose * min(1.5, scale) * prices.get(crop, _base(crop))


# ---------------------------------------------------------------------------
# Job scoring
# ---------------------------------------------------------------------------
#
# Tiers first, value inside a tier second. The tiers are not arbitrary -- they are ordered by
# how much of a tile's season is forfeited by skipping the job for one day:
#
#   RESCUE   the tile turns to weed at midnight: the entire remaining cycle is lost
#   HARVEST  the yield is standing in the field and decays one unit every other day
#   FERT     tonight's gain-day doubles, or is lost to a dose that arrives a day late
#   GROW     one unit of yield that will never be regained (the gain window has moved on)
#   PLANT    a tile-cycle of future value, but only if it can finish before day 30
#   DIG      nothing today; it unblocks a tile for a future PLANT
#
# FERT sits above GROW because a dose is worth more per visit than a watering: on strawberry it
# buys two units for one visit where a watering buys one, and unlike a watering it expires -- a
# dose applied the day after a gain-day buys nothing for that day at all. (This used to say
# "on melon", back when melon's gain window was believed to be three days wide instead of seven.
# Melon reaches its unfertilized cap on its own, so its FERT_PLAN row is now zero and no melon
# fertilize job ever scores above 0.)
#
# Inside a tier the sort is by dollars, so a melon rescue outranks a wheat rescue and the last
# jobs to fall off an over-subscribed day are the cheap ones.

TIER_RESCUE, TIER_HARVEST, TIER_FERT, TIER_GROW, TIER_PLANT, TIER_DIG = 50, 40, 35, 30, 20, 10


def crop_value(crop, prices):
    """Dollars a finished tile of `crop` is worth at current market prices."""
    plan = CROP_PLAN.get(crop)
    units = plan["units"] if plan else 1
    return units * prices.get(crop, _base(crop) if crop in MARKET_PARAMS else 0)


def pipeline_units(tiles, unlocked, shed, crop):
    """Units of `crop` already committed to the market: growing on the board, plus in the shed.

    A tile counts for its full planned yield, not its current one. The decision this feeds is
    whether to plant *another* tile, and by the time that tile is harvested every tile already
    in the ground will have finished and been sold -- so the market this one meets is the one
    the whole standing crop has already been through.
    """
    units = CROP_PLAN[crop]["units"] if crop in CROP_PLAN else 1
    n = 0
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if quadrant_of(x, y) not in unlocked:
                continue
            tile = tiles[y][x]
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == crop:
                n += units
    return n + shed.get(crop, 0)


def marginal_price(crop, head, cap=0.0):
    """Mean price of the next `units` of `crop` sold, starting from market inventory `head`.

    One tile is one indivisible block of `units`, so the number that matters to a planting
    decision is the average over the block, not the price of its first unit.

    `cap`, in multiples of base, bounds the answer. It exists because `head` is now pushed
    *down* by the drain lookahead and `price_for` is unbounded below `I0` on the shallow
    curves -- EGG at inventory zero prices at $136,333. No lookahead is trustworthy that far
    out, and an uncapped one would let a single crop win every tile on the board.
    """
    u = max(1, CROP_PLAN[crop]["units"] if crop in CROP_PLAN else 1)
    px = sum(price_for(crop, head + k) for k in range(u)) / u
    if cap > 0:
        px = min(px, cap * MARKET_PARAMS[crop]["base"])
    return px


def horizon_head(crop, inv, pipe, shops, frac):
    """Market inventory the next tile's harvest will actually meet.

    Three terms: what is in the market now, what this farm has already committed to it, and
    what the town will have eaten by the time the tile is ready. The third term is the one
    that was missing, and it is not a rounding error -- measured over 8 seeds with the shop
    list the observation already reports:

        good         cycle   drain over cycle   price at I0 -> price after drain
        WHEAT          4d          54 u              $25  ->  $32
        CARROT         3d          39 u              $35  ->  $38
        TOMATO        11d          33 u              $60  ->  $64
        STRAWBERRY    16d         134 u             $120  -> $218
        MELON         12d          12 u             $250  -> $272

    Strawberry is in four of the eight shop baskets and melon is in none, so over their
    cycles the town absorbs 134 strawberries and 12 melons. Pricing both at spot understated
    strawberry by 1.8x while melon's own pipeline was the only thing marking it down, and the
    allocator answered by filling the board with melon: 25 tiles on day 0, 148 units a season
    into a market that eats 30, with the last decile realizing $109 -- 44% of base and still
    falling. Strawberry's realized price is flat at 228% of base across every decile, because
    its pipeline never catches its drain.

    `frac` discounts the lookahead. The drain is exact but it is not ours alone: the opponent
    sells into the same inventory, and a fraction below 1 is the cheapest way to say so
    without modelling them.
    """
    cyc = CROP_PLAN[crop]["harvest_day"] if crop in CROP_PLAN else 0
    drain = drain_per_day_from_shops(crop, shops) * cyc * frac
    return inv.get(crop, I0) + pipe - drain


def effective_prices(tiles, unlocked, shed, inv, prices, shops=(), frac=0.0, cap=0.0):
    """Price each crop at the marginal price its NEXT tile's harvest will actually meet.

    The spot price is the wrong number to plant against whenever a crop's own pipeline is
    large relative to what the market absorbs, and melon is the case that decides the
    competition. Its glut curve is quadratic on a $300 scale, the town buys exactly one melon
    a day and no shop basket contains it at all, so the only thing setting melon's price is
    how many melons the two farms have already sold. Measured over a season: +40 units still
    prices at $234, +100 at $150, +184 at the $1 floor. Twenty-four melon tiles put 96 units
    per cycle into that market, so a planner reading spot sees $250 on day 12, plants more
    melon, and realizes 72% of base on the lot.

    Each crop is therefore priced at the mean marginal price of the block one more tile would
    add, stacked on everything already growing and everything already in the shed, and netted
    against the town's drain over that tile's own growing period -- see `horizon_head`, which
    is what makes the pumped crops read as pumped instead of as flat. The opponent's volume is
    not modelled here; it arrives for free in `inv`, since both farms sell into the same
    inventory and the observation reports it.
    """
    out = dict(prices)
    for crop in CROP_PLAN:
        if crop not in MARKET_PARAMS:
            continue
        pipe = pipeline_units(tiles, unlocked, shed, crop)
        out[crop] = marginal_price(crop, horizon_head(crop, inv, pipe, shops, frac), cap)
    return out


def marginal_rank(crop, inv, pipe, alpha, shops=(), frac=0.0, cap=0.0):
    """`seed_rank` for one more tile of `crop`, priced at the market its harvest will meet.

    This is the function the tile allocation in `_targets` maximises, and because `pipe` grows
    by a tile's worth of units after every allocation, re-evaluating it makes the allocation
    self-limiting: melon wins the first tiles at $250 a unit and stops winning once its own
    committed volume has walked the price down to where strawberry -- whose price the town is
    still pumping -- is worth more per visit. A fixed mix cannot do this, because the right
    melon acreage depends on the melon price, which depends on the melon acreage.
    """
    plan = CROP_PLAN[crop]
    acts = 2 + len(plan["water_days"])
    px = marginal_price(crop, horizon_head(crop, inv, pipe, shops, frac), cap)
    net = plan["units"] * px - OBJECT_TABLE[crop]["seed_cost"]
    r = net / acts
    if alpha <= 0 or r <= 0:
        return r
    return r / (OBJECT_TABLE[crop]["seed_cost"] ** alpha)


def in_time(crop, day):
    """Can a tile planted today still be harvested before the episode ends?

    Day 29 is the last day and `_day_refresh` never runs at step 720, so a tile whose
    harvest_day lands past day 29 banks nothing and its seed cost is pure loss.
    """
    plan = CROP_PLAN.get(crop)
    return bool(plan) and day + plan["harvest_day"] < SEASON_DAYS


def seed_rank(crop, prices, alpha):
    """Funding priority for one seed. `alpha` interpolates between two different questions.

    At alpha = 0 this is `plant_rank`: dollars per tile-visit, the right ranking when the
    roster's turns are the scarce resource. At alpha = 1 it is dollars per seed-dollar, the
    right ranking when cash is scarce -- and cash *is* scarce for the first third of the
    season, because $3,000 does not buy the seed for a 75-tile melon-and-strawberry board
    and neither of those crops pays out before day 12. Wheat wins on capital efficiency
    (six cycles a season off a $10 seed) and loses badly on visits.
    """
    r = plant_rank(crop, prices)
    if alpha <= 0:
        return r
    return r / (OBJECT_TABLE[crop]["seed_cost"] ** alpha)


def collect_jobs(tiles, unlocked, day, prices, want, avail, params, fert_stock=0, animals=None):
    """Every job worth doing on the board today, sorted by value, highest first.

    `want` is the per-crop tile target for planting and `avail` the seed stock those plants
    will draw on -- the seeds already held plus the ones today's budget will buy, since a
    market order placed this turn settles before next turn's unit ops. Passing the *planned*
    stock rather than the current one is what lets dawn on day 0 see any work at all: at
    hour 0 the shed is empty of seed, and a planner that believed the observation would find
    nothing to do and hire nobody.

    `fert_stock` is how many FERTILIZE jobs the shed can actually pay for. Unlike seed, a dose
    is spent from the shed at the moment of use and needs no carrying, so the only cap is the
    stock -- and emitting more FERTILIZE jobs than there are doses would spend visits on
    no-ops.

    `animals` is the livestock plan: which animal to keep, how many structures to raise today,
    how many are in the shed waiting to be placed, and what a collected dose is worth. None
    switches the whole programme off and the board reads exactly as it did before.
    """
    jobs = []
    empties = []
    ferts = []
    for y in range(BOARD_SIZE):
        for x in range(BOARD_SIZE):
            if quadrant_of(x, y) not in unlocked:
                continue
            tile = tiles[y][x]
            if tile is None:
                empties.append((x, y))
                continue
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "WEED":
                if params["weed_dig"]:
                    jobs.append(dict(pos=(x, y), op=["DIG"], tier=TIER_DIG, value=0.0))
                continue
            if kind in ("COOP", "PASTURE"):
                if animals:
                    jobs.extend(animal_jobs(tile, x, y, day, prices, params, animals, unlocked))
                continue
            if kind != "PLANT":
                continue
            crop = tile.get("crop")
            val = crop_value(crop, prices)
            hp = harvest_plan(tile, day)
            if hp:
                op, then = hp
                units = tile.get("yield_units", 1)
                # A water-then-harvest banks the unit that watering is about to add, so the job
                # is worth more than the tile currently shows. Charging `acts` honestly matters
                # as much as the value: the router prices a two-op job at two turns, so it will
                # not silently overbook the day.
                if op[0] == "WATER":
                    units += 2 if tile.get("fertilized_until_day", -1) >= day else 1
                    units = min(units, yield_cap(crop, tile.get("fertilized_until_day", -1) >= day))
                jobs.append(dict(pos=(x, y), op=op, then=then, acts=2 if then else 1,
                                 tier=TIER_HARVEST,
                                 value=units * prices.get(crop, _base(crop)), crop=crop))
                continue
            if params["fert"] and fert_stock > 0:
                fv = fert_value(tile, day, prices)
                # The dose has to beat its own price by a margin, at the marginal price its
                # extra units will meet. Wheat and carrot never clear it: their whole harvest
                # is worth less than the $100 dose.
                if fv > params["fert_margin"] * _base("FERTILIZER"):
                    ferts.append(dict(pos=(x, y), op=["FERTILIZE"], tier=TIER_FERT,
                                      value=fv, crop=crop))
            if tile.get("watered_today"):
                continue
            if will_die_tonight(tile, day):
                jobs.append(dict(pos=(x, y), op=["WATER"], tier=TIER_RESCUE,
                                 value=val, crop=crop))
            elif needs_water(crop, tile_age(tile, day)):
                jobs.append(dict(pos=(x, y), op=["WATER"], tier=TIER_GROW,
                                 value=val / max(1, CROP_PLAN[crop]["units"]), crop=crop))

    # Only as many doses as the shed holds, dearest tile first.
    ferts.sort(key=lambda j: -j["value"])
    jobs.extend(ferts[:fert_stock])

    # PLANT: fill the target, best dollars-per-visit first, only where the cycle finishes.
    order = sorted((c for c in want if want[c] > 0), key=lambda c: -plant_rank(c, prices))
    empties.sort(key=lambda p: manhattan(p, SHED_TILES["NW"]))
    ei = 0

    # Structures take the tiles the crops want least -- farthest from the shed, off the back of
    # the same sorted list -- and are removed from `empties` rather than skipped past, so a
    # BUILD job that the router never gets to does not silently cost a planting. The first
    # version took the tiles *nearest* the shed on the theory that every PICKUP starts there;
    # it does not, `PICKUP` has no location check, so that cost was imaginary and the acreage
    # it spent was not.
    if animals and animals.get("n_build", 0) > 0:
        struct = "BUILD_COOP" if animals["struct"] == "COOP" else "BUILD_PASTURE"
        sheds = set(SHED_TILES.values())
        built = 0
        while built < animals["n_build"] and len(empties) > ei:
            # Never on a shed tile. The engine treats those as ordinary empty ground, but PLACE
            # checks for a structure before it checks for the shed, so a pasture on (4,4) would
            # stop every unit standing there from banking what it carries.
            spot = empties.pop()
            if spot in sheds:
                continue
            jobs.append(dict(pos=spot, op=[struct], tier=TIER_PLANT,
                             value=animals["rank"]))
            built += 1
    for crop in order:
        if not in_time(crop, day):
            continue
        n = min(want[crop], avail.get(crop, 0), len(empties) - ei)
        for _ in range(max(0, n)):
            # PLANT and the first WATER are one job, not two. The engine plants with
            # `consecutive_unwatered = 1`, so a tile planted today and left dry tonight hits 2
            # at midnight and turns to weed -- the seed, the turn and the whole cycle gone.
            # Splitting them risks the routing handing the WATER to a different unit, or to a
            # later slice of the day that the turn budget then drops.
            jobs.append(dict(pos=empties[ei], op=["PLANT", crop], then=["WATER"], acts=2,
                             tier=TIER_PLANT, value=plant_rank(crop, prices), crop=crop))
            ei += 1

    jobs.sort(key=lambda j: (-j["tier"], -j["value"]))
    return jobs


def plant_rank(crop, prices):
    """Dollars per tile-VISIT, which is the resource actually in short supply.

    Not dollars per tile-day and not dollars per cycle. A turn buys one op or one move, so a
    crop competes for the roster's visits: melon returns ~$92 a visit against wheat's ~$15,
    and that gap is most of the argument for the portfolio mix. Using live prices rather than
    base means a melon programme that has already crashed its own price automatically stops
    outranking strawberry.
    """
    plan = CROP_PLAN[crop]
    acts = 2 + len(plan["water_days"])
    net = plan["units"] * prices.get(crop, _base(crop)) - OBJECT_TABLE[crop]["seed_cost"]
    return net / acts


# ---------------------------------------------------------------------------
# Livestock economics
# ---------------------------------------------------------------------------


def animal_programme(animal, day):
    """Units, doses, visits and wheat a single animal placed on `day` yields by season end.

    Derived from the spec rather than measured, so it stays true if calibration moves the
    numbers. Reproduces `analysis/animal_probe.py` exactly on all three animals.

    The programme is minimum-feed plus daily collection. Feeding is a survival cost and nothing
    else: `_refresh_animal` grants `base_gain = 1` on a production day whether or not the animal
    ate, and the only thing feeding buys is that `consecutive_unfed` resets, so the schedule is
    the loosest one that never reaches two -- one FEED every other day. CARE is skipped because
    its bonus accrues only on non-production days and only while fed, which means paying for
    daily feeding as well as the care visits: on a cow that is 35 extra visits for 5 extra units.
    """
    spec = OBJECT_TABLE[animal]
    first, interval, cap = spec["first_yield_day"], spec["interval"], spec["max_held"]
    left = max(0, SEASON_DAYS - day)
    if left <= first:
        return None
    units = sum(1 for d in range(first, left) if (d - first) % interval == 0)
    if units <= 0:
        return None
    # A dose is available at the end of every day the animal survives; feeding is every other
    # day; the pack has to be emptied once per `max_held` units and once at the end.
    doses = max(0, left - 1)
    feeds = left // 2
    harvests = max(1, -(-units // cap))
    setup = 3  # BUILD, PICKUP at the shed, PLACE
    return dict(units=units, doses=doses, feeds=feeds,
                visits=setup + feeds + doses + harvests)


def animal_rank(animal, day, inv, shops, frac, cap, fert_px, wheat_px):
    """Dollars per visit for one more animal, on the same footing as `plant_rank`.

    Two revenue terms and two costs. The product is priced through `marginal_price` like a crop,
    with the drain lookahead run over the whole remaining season rather than one cycle -- an
    animal is a standing asset, not a tile-cycle, and the market its last unit meets is the one
    the town has been eating from for a month. The byproduct is priced at what the farm actually
    pays for a dose, because that is what a collected one saves.

    The fertilizer term dominates, and it is the reason the count is capped rather than ranked:
    the credit is real only while the farm would otherwise have bought the dose.
    """
    prog = animal_programme(animal, day)
    if prog is None:
        return 0.0, None
    product = ANIMAL_PRODUCT[animal]
    days_left = max(1, SEASON_DAYS - day)
    head = (inv.get(product, I0) + prog["units"]
            - drain_per_day_from_shops(product, shops) * days_left * frac)
    px = marginal_price(product, head, cap)
    gross = prog["units"] * px + prog["doses"] * fert_px
    cost = prog["feeds"] * wheat_px + OBJECT_TABLE[animal]["buy_cost"]
    return (gross - cost) / max(1, prog["visits"]), prog


def animal_jobs(tile, x, y, day, prices, params, plan, unlocked):
    """Today's work on one structure tile, tiered by what skipping it forfeits.

    FEED is emitted twice over, at two different tiers, and the duplication is the point. The
    day it is *due* -- `consecutive_unfed >= 1`, one more miss from `tile["animal"] = None` and
    an asset the engine offers no way to recover -- it is a rescue and outranks every crop
    rescue on the board. On any other unfed day it is offered at GROW instead, cheap insurance
    at one wheat (~$40 realized) against a $2,000 animal plus the rest of its season. Measured
    on the first integration build, rescue-only feeding lost two to five animals an episode:
    one job, on one tile, on the one day it mattered, and any turn where the router could not
    reach it was fatal.

    COLLECT_FERTILIZER sits at PLANT and bids against the plantings on value. That is the
    comparison the probe actually measured -- a dose is $110 for one visit against strawberry's
    $95 and melon's $81 -- and it is the honest one. It was at GROW, above every watering, and
    that is what turned the programme into a $30k regression: the doses were taken ahead of the
    crop maintenance that pays for the farm.

    PLACE is reached through the shed, so it is a two-stage job: PICKUP where the animal landed,
    then walk to the structure and PLACE. Emitted as one job with `then_pos` so the pair cannot
    be split across two units, which would leave one of them carrying an animal it has no
    instruction to put down.
    """
    out = []
    animal = tile.get("animal")
    if animal is None:
        if plan.get("held", 0) > 0 and plan.get("animal") \
                and ANIMAL_STRUCTURE[plan["animal"]] == tile.get("kind"):
            # PICKUP has no location check in the engine -- it draws straight from the shed
            # wherever the unit is standing -- so the pair runs on the structure tile and the
            # walk to the shed and back is saved. Emitted as one job with `then` so the two
            # halves cannot be split across units, which would leave one of them carrying an
            # animal it has no instruction to put down.
            out.append(dict(pos=(x, y), op=["PICKUP", plan["animal"], 1],
                            then=["PLACE", plan["animal"]], acts=2,
                            tier=TIER_PLANT, value=plan["rank"], animal=plan["animal"]))
        return out

    spec = OBJECT_TABLE[animal]
    product = ANIMAL_PRODUCT[animal]
    units = tile.get("yield_units", 0)
    age = day - tile.get("placed_day", day)
    first, interval = spec["first_yield_day"], spec["interval"]
    prod_today = age >= first and (age - first) % interval == 0
    endgame = day >= SEASON_DAYS - params["endgame_days"]

    # Harvest before tonight's gain would be clipped by `max_held`, and on the way out: produce
    # left on the tile at step 720 scores nothing.
    if units > 0 and (endgame or units >= spec["max_held"]
                      or (prod_today and units + 1 > spec["max_held"])):
        out.append(dict(pos=(x, y), op=["HARVEST"], tier=TIER_HARVEST,
                        value=units * prices.get(product, _base(product)), crop=product))

    if not tile.get("fed_today") and not endgame:
        due = tile.get("consecutive_unfed", 0) >= 1
        out.append(dict(pos=(x, y), op=["FEED"],
                        tier=TIER_RESCUE if due else TIER_GROW,
                        value=plan.get("worth", 4000.0) if due else plan.get("wheat_px", 40.0),
                        animal=animal))

    if tile.get("fertilizer_available") and params["fert"] and not endgame:
        out.append(dict(pos=(x, y), op=["COLLECT_FERTILIZER"], tier=TIER_PLANT,
                        value=plan.get("fert_px", _base("FERTILIZER"))))
    return out


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


class Policy:
    """One instance per episode. `act(obs)` returns the engine's action dict.

    State between turns is the day's plan: `self.queues[unit] = [job, ...]`. The queues hold
    absolute board positions, never turn indices, so the executor re-reads each unit's real
    position from the observation every turn and walks one step. A blocked move, a tile the
    opponent's weeds got to first, or a hire that failed for lack of cash all self-correct
    without a replan.
    """

    def __init__(self, params=None):
        self.p = dict(PARAMS)
        if params:
            self.p.update(params)
        self.queues = {}
        self.plan_day = -1
        self.plan_cut_for = 0     # unit count the live route plan was cut for; see `_act`
        self.want = {}
        self.seed_plan = {}
        self.eff = {}             # pipeline-adjusted crop prices, recomputed each dawn
        self.shops = []           # unlocked shop names as of this dawn; sets the drain rates
        self.seed_spend = 0.0
        self.n_hire = 0
        self.tile_limited = False
        self.limit = ""           # which resource ended the dawn allocation; probes only
        self.fert_have = 0        # doses the dawn plan may route, shed stock plus today's buy
        self.animals = None       # livestock plan for the day; None means the programme is off
        # One-shot market orders already issued today. `_market_orders` runs every turn against a
        # plan that is only recomputed at dawn, so anything sized from that plan has to record
        # that it went out or it goes out 24 times.
        self.ordered = {}
        # Set by `_sell_orders` each turn, read by `_market_orders` in the same turn.
        self.crowded = False
        self.pressure = 0.0
        # A full roster costs $143 for the day against $80 for one melon seed, so wages are
        # simply held out of the seed budget rather than traded off against it.
        self.wage_reserve = sum(fib_hire_cost(i) for i in range(self.p["max_hands"]))
        self.last_error = None

    # -- entry point -------------------------------------------------------

    def act(self, obs):
        t0 = time.monotonic()
        try:
            return self._act(obs, t0)
        except Exception as e:                    # a raise here forfeits the episode
            self.last_error = repr(e)
            n = len(self._me(obs).get("hands") or [])
            return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}

    @staticmethod
    def _me(obs):
        i = obs.get("player", 0)
        return (obs.get("farms") or [{}, {}])[i]

    def _act(self, obs, t0):
        me = self._me(obs)
        day = obs.get("day", obs.get("step", 0) // TURNS_PER_DAY)
        hour = obs.get("hour", obs.get("step", 0) % TURNS_PER_DAY)
        priv = obs.get("private") or {}
        tiles = me.get("tiles") or [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        unlocked = set(me.get("unlocked_quadrants") or ["NW"])
        prices = (obs.get("market") or {}).get("prices") or {}
        inv = (obs.get("market") or {}).get("inventory") or {}
        shed = dict(priv.get("shed") or {})
        seeds = dict(priv.get("seeds") or {})
        invs = priv.get("inventories") or [{}]
        units = [(0, tuple(me.get("farmer") or (4, 4)))]
        for i, h in enumerate(me.get("hands") or []):
            units.append((i + 1, tuple(h)))
        # How close the farm is to destroying its own harvest at the next midnight dump. Read by
        # `_unit_ops` to decide whether a carried load is worth a shed trip, and by `_replan` to
        # decide whether the day's runs must end within walking distance of one.
        self.pressure = self._haul_pressure(shed, invs)

        # --- dawn: fund the seeds, size the roster, then plan. At hour 0 neither the hands
        # nor the seeds exist yet -- both are market orders, and market orders settle after
        # the turn's unit ops -- so the plan is built against what this turn is about to buy
        # and re-cut at hour 1 against what actually arrived.
        if day != self.plan_day:
            self.plan_day = day
            self.plan_cut_for = len(units)
            self.ordered = {}
            # Plant against the price the harvest will meet, not the price on the board today.
            # See `effective_prices`: melon's own volume is what sets melon's price, and the
            # town's drain over the growing period is what sets everything else's.
            self.shops = unlocked_shops_from_obs(obs)
            self.eff = effective_prices(tiles, unlocked, shed, inv, prices, self.shops,
                                        self.p["drain_frac"], self.p["px_cap"])
            self.animals = self._animal_plan(tiles, unlocked, day, inv, prices, shed,
                                             me.get("money", 0.0))
            self.want, self.seed_plan = self._targets(tiles, unlocked, day, self.eff,
                                                     me.get("money", 0.0), seeds, inv, shed)
            self.n_hire = self._roster(tiles, unlocked, day, self.eff, me)
            # Doses the day can spend: what is in the shed plus what this turn's top-up buys.
            # Same reasoning as seed -- the BUY_PRODUCT settles after this turn's unit ops, so a
            # planner that believed the observation would refuse to route the first dose of the
            # season and then never need one.
            self.fert_have = shed.get("FERTILIZER", 0) + self._fert_buy(shed, me.get("money", 0.0), day)
            predicted = units + [(len(units) + i, p)
                                 for i, p in enumerate(self._spawn_guess(self.n_hire, units))]
            self._replan(tiles, unlocked, day, hour, self.eff, self.seed_plan, predicted, t0)
        elif len(units) > self.plan_cut_for and hour < TURNS_PER_DAY - 4:
            self.plan_cut_for = len(units)
            # Re-cut whenever the roster grows, not just at hour 1. `HIRE` costs one market slot
            # per hand and the ten-slot book is shared with seed, fertilizer, land and sells, so a
            # twelve-hand roster arrives over three or four turns. Re-cutting once at hour 1 gave
            # lanes to whoever had shown up by then and left the rest PASSing all day: measured at
            # `max_hands=12`, idle was exactly `roster - 6` from hour 2 to midnight, six hands
            # standing in the dirt for twenty-two turns. That, not the shed, is why every
            # acreage-increasing parameter read as a loss.
            #
            # Re-planning mid-day is safe because `collect_jobs` reads the board, so finished work
            # is already invisible to it and the re-cut only re-partitions what is left over the
            # turns that remain.
            #
            # Still the *planned* seed stock, not the observed one: re-deriving the job list from
            # `seeds` would delete every PLANT job whose seed order was deferred by the slot cap --
            # and since the seed order is sized off those jobs, deleting them stops the seed from
            # ever being bought.
            self._replan(tiles, unlocked, day, hour, self.eff, self.seed_plan, units, t0)

        ops = self._unit_ops(units, tiles, invs, seeds, unlocked, day, hour, shed)
        market = self._market_orders(obs, me, shed, seeds, inv, prices, unlocked, day, hour)
        return {"farmer": ops[0], "hands": ops[1:], "market": market[:MAX_MARKET_ORDERS]}

    # -- planning ----------------------------------------------------------

    def _board_state(self, tiles, unlocked):
        """Live crop counts and the empty-tile count over unlocked land."""
        live = {c: 0 for c in self.p["mix"]}
        empty = 0
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if quadrant_of(x, y) not in unlocked:
                    continue
                tile = tiles[y][x]
                if tile is None:
                    empty += 1
                elif isinstance(tile, dict) and tile.get("kind") == "PLANT":
                    c = tile.get("crop")
                    if c in live:
                        live[c] += 1
        return live, empty

    def _targets(self, tiles, unlocked, day, prices, money, seeds, inv, shed):
        """Tiles to plant per crop today, and the seed stock that pays for them.

        Tiles are allocated one at a time to whichever crop has the best `marginal_rank`, and
        the crop's committed volume is incremented after each one so the next tile is priced
        against a market that already contains it. That loop is the answer to a circularity a
        fixed mix cannot resolve: the right melon acreage depends on the melon price, and the
        melon price depends on the melon acreage. Greedy marginal allocation converges on the
        acreage where the last melon tile is worth exactly as much per visit as the strawberry
        tile it displaced, which is the definition of the optimum when visits are the binding
        resource.

        Two constraints ride on top. Cash binds early -- the full board needs about $5,700 of
        seed against $3,000 of starting money, and neither melon (day 12) nor strawberry
        (day 16) returns a cent before then -- so a crop is skipped once its next seed does not
        fit in the budget, which under a nonzero `seed_alpha` also tilts the ranking toward
        wheat's six cycles off a $10 seed. And `mix` survives as a soft acreage cap
        (`mix_cap` x its share of unlocked land) purely as a hedge: the marginal ranking is
        computed from calibrated prices, and if those prices are wrong the cap is what stops a
        single mistake from becoming a monoculture.
        """
        mix = self.p["mix"]
        total = sum(mix.values()) or 1
        live, empty = self._board_state(tiles, unlocked)
        budget = max(0.0, money - self.wage_reserve)
        land = 25 * max(1, len(unlocked))
        cap = {c: self.p["mix_cap"] * mix[c] / total * land for c in mix}
        pipe = {c: pipeline_units(tiles, unlocked, shed, c) for c in mix}
        alpha = self.p["seed_alpha"]

        # Labour ceiling. A tile is not an asset until somebody waters it, and the measured
        # cost of over-planting is weeds: at nine hands the farm loses ~21 plants a season to
        # two dry nights against ~10 at four hands, because the extra acreage the bigger roster
        # buys is acreage it cannot then maintain, and every weed forfeits a whole remaining
        # cycle rather than one unit of yield. So the allocation is capped by the roster's daily
        # tile-visits, charging each crop its measured maintenance rate: strawberry needs 0.65
        # visits per tile-day against carrot's 1.25, which is most of the reason strawberry
        # outgrows carrot on the same roster.
        commute = 3.0 + 1.5 * max(0, len(unlocked) - 1)
        visits = (1 + self.p["max_hands"]) * max(1, capacity(commute)) * self.p["labour_slack"]
        load = sum(live[c] * crop_actions_per_day(c) for c in live)
        # Livestock does NOT charge against this ceiling by default, and the measurement is why.
        # Charging it 1.6 visits a tile-day -- the honest maintenance rate -- shrank the farm from
        # 51.7 to 40.1 live tiles a day and took strawberry from 296 units to 134, while *idle*
        # unit-turns went up from 14.4% to 18.1%. The capacity the crops gave up was not then
        # used by the animals; it was simply not used. There is slack on this board (15 empty
        # unlocked tiles and ~570 idle unit-turns a season), so the animal work belongs in the
        # slack, not in front of the acreage. Kept as a parameter because that conclusion is a
        # property of the current roster size and the sweep should be able to retest it.
        if self.animals:
            load += self.p["animal_load"] * max(self.animals["live"], self.animals["built"])
        want, plan, spent = {}, {}, 0.0

        # Why the loop stops is the only diagnostic that says where the next acre is. It is
        # recorded per pass and read after the break, so `self.limit` describes the pass that
        # actually failed rather than an accumulation over the whole allocation.
        veto = {}

        while empty > 0:
            best, best_r = None, 0.0
            veto = {}
            for crop in mix:
                if not in_time(crop, day):
                    veto[crop] = "late"
                    continue
                if live[crop] + want.get(crop, 0) >= cap[crop]:
                    veto[crop] = "cap"
                    continue
                if load + crop_actions_per_day(crop) > visits:
                    veto[crop] = "labour"
                    continue
                cost = OBJECT_TABLE[crop]["seed_cost"]
                # A seed already held is free to plant; otherwise it has to fit the budget.
                if want.get(crop, 0) >= seeds.get(crop, 0) and spent + cost > budget:
                    veto[crop] = "cash"
                    continue
                r = marginal_rank(crop, inv, pipe[crop], alpha, self.shops,
                                  self.p["drain_frac"], self.p["px_cap"])
                if r > best_r:
                    best, best_r = crop, r
                else:
                    veto[crop] = "worthless"
            if best is None:
                break
            want[best] = plan[best] = want.get(best, 0) + 1
            if want[best] > seeds.get(best, 0):
                spent += OBJECT_TABLE[best]["seed_cost"]
            pipe[best] += CROP_PLAN[best]["units"]
            load += crop_actions_per_day(best)
            empty -= 1

        # Which constraint stopped the loop is the land-purchase signal, and it is a measured
        # one rather than a threshold: if the allocator ran out of *tiles* while it still had
        # cash and profitable crops, another quadrant converts cash into acreage at once. If it
        # ran out of cash or of crops worth planting, a quadrant is $1,000 of nothing.
        self.tile_limited = (empty <= 0)
        # The same question with more resolution, for `analysis/limit_probe.py`: "tiles" means
        # the board is full, anything else names the resource that ran out first. Read by probes
        # only -- nothing in the policy branches on it -- so it can change shape freely.
        self.limit = "tiles" if empty <= 0 else "+".join(sorted(set(veto.values())))
        self.seed_spend = spent
        return want, plan


    def _animal_plan(self, tiles, unlocked, day, inv, prices, shed, money):
        """Which animal to keep, how many structures to raise today, and what a dose is worth.

        Returns None when livestock is off or not worth it, which restores the crop-only board
        exactly. Everything downstream reads this one dict, so the programme has a single switch.

        The animal is chosen by `animal_rank` rather than fixed, because which product is worth
        keeping depends on the shop draw: MILK is in three of the eight baskets and WOOL in one,
        so on a season that opens a YARN_STORE wool prices above milk and on one that does not it
        is drained a single unit a day by the town centre and craters. The count is capped rather
        than ranked because the dominant term does not scale -- the byproduct is only worth what
        the farm would otherwise have paid for a dose, and three animals already cover the
        season's 97-dose bill.
        """
        if self.p["n_animals"] <= 0:
            return None
        # A dose is worth the price the farm pays for one, not base: BUY_PRODUCT walks the curve
        # upward and the measured mean over a season is $110 against a $100 base.
        fert_px = price_for("FERTILIZER", max(1, inv.get("FERTILIZER", I0) - 1)) \
            if self.p["fert"] else 0.0
        wheat_px = prices.get("WHEAT", _base("WHEAT"))
        best, best_r, best_prog = None, self.p["animal_margin"], None
        for animal in ANIMALS:
            r, prog = animal_rank(animal, day, inv, self.shops, self.p["drain_frac"],
                                  self.p["px_cap"], fert_px, wheat_px)
            if prog is not None and r > best_r:
                best, best_r, best_prog = animal, r, prog

        # Count what is already standing. The incumbent species wins over the theoretical best:
        # a structure is built for one species, and re-ranking mid-season would strand a pasture
        # or leave a half-grown cow for a fresh sheep.
        built = live = 0
        incumbent = None
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if quadrant_of(x, y) not in unlocked:
                    continue
                tile = tiles[y][x]
                if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
                    built += 1
                    if tile.get("animal"):
                        live += 1
                        incumbent = incumbent or tile["animal"]
        for animal in ANIMALS:
            if shed.get(animal, 0):
                incumbent = incumbent or animal
        best = incumbent or best
        if best is None:
            return None

        held = shed.get(best, 0)
        want = self.p["n_animals"]
        # Build only while a placed animal would still reach its first yield -- past that a
        # structure is a tile spent on nothing. Building itself is free, so it is not gated on
        # cash; buying is, and one a day keeps the animals from crowding out day-0 seed, which
        # is the only compounding purchase the farm makes.
        in_time_ = animal_programme(best, day) is not None
        return dict(animal=best, struct=ANIMAL_STRUCTURE[best], rank=best_r,
                    worth=best_r * (best_prog["visits"] if best_prog else 40),
                    fert_px=fert_px, wheat_px=wheat_px, held=held, live=live, built=built,
                    n_build=1 if (in_time_ and built < want) else 0,
                    n_buy=1 if (in_time_ and live + held < want
                                and money > OBJECT_TABLE[best]["buy_cost"] * 2) else 0)


    def _spawn_guess(self, n, units):
        """Where the engine will put `n` new hands: the four tiles around the NW shed.

        `_spawn_hand_pos` picks the least-occupied of (N, W, S, E) neighbours of the shed and
        breaks ties in that order, so the roster fans out N, W, S, E, N, ... Getting this wrong
        costs at most one turn of walking, and hour 1 re-cuts the runs against the real
        positions anyway -- the guess exists only so the farmer has productive work at hour 0.
        """
        sx, sy = SHED_TILES["NW"]
        ring = [(sx, sy - 1), (sx - 1, sy), (sx, sy + 1), (sx + 1, sy)]
        occ = {p for _, p in units}
        out = []
        for i in range(n):
            counts = [sum(1 for q in list(occ) + out if q == c) for c in ring]
            best = min(counts)
            out.append(next(c for c, k in zip(ring, counts) if k == best))
        return out

    def _roster(self, tiles, unlocked, day, prices, me):
        """How many hands to hire this dawn.

        Sized off the actual job count, not the tile count: the jobs are what cost turns, and a
        100-tile farm of strawberry generates half the daily jobs of 100 tiles of carrot. Then
        capped by `max_hands` and by cash. The cash cap almost never binds -- ten hands cost
        $143 for the day -- and it is deliberately not a fraction of the balance: starving the
        roster to afford one more melon seed trades ten tile-visits for $80 of stock.
        """
        jobs = collect_jobs(tiles, unlocked, day, prices, self.want, self.seed_plan, self.p,
                            animals=self.animals)
        # `acts` counts turns spent standing on the tile. A harvest costs one more than that:
        # HARVEST fills the unit's own inventory and SELL draws from the shed, so somebody has
        # to walk the load back and DROP it. Checked against `then` as well as `op`, because a
        # water-then-harvest job carries the HARVEST in `then`.
        n_jobs = sum(j.get("acts", 1)
                     + (1 if "HARVEST" in (j["op"][0], (j.get("then") or [None])[0]) else 0)
                     for j in jobs)
        commute = 3.0 + 1.5 * max(0, len(unlocked) - 1)      # mean one-way walk into the farm
        per_unit = max(1, capacity(commute))
        need = -(-n_jobs // per_unit)                        # ceil
        money = me.get("money", 0.0)
        n = max(0, min(self.p["max_hands"], need - 1))
        while n > 0 and sum(fib_hire_cost(i) for i in range(n)) > money:
            n -= 1
        return n

    def _replan(self, tiles, unlocked, day, hour, prices, avail, units, t0):
        """Rebuild every unit's run. Falls back to the previous plan if the clock runs short.

        Two sorts, in this order, and the order is the whole trick. Value decides WHICH jobs
        make the day; geometry decides the ORDER they are walked in. Sorting only by value
        gives a route that criss-crosses the board and completes a third of it; sorting only by
        geometry drops a melon rescue in the far corner to water wheat near the shed.

        `split_runs` charges the real commute, so a job list that looks affordable by turn count
        may not fit once the walking is priced. When that happens the jobs that fall off are the
        geometrically last ones rather than the cheapest, which is the wrong end -- so shrink the
        candidate list to what actually fitted and re-cut. It converges in one or two passes.
        """
        if (time.monotonic() - t0) * 1000.0 > self.p["plan_ms"]:
            return
        ranked = collect_jobs(tiles, unlocked, day, prices, self.want, avail, self.p,
                              fert_stock=self.fert_have, animals=self.animals)
        turns_left = TURNS_PER_DAY - hour
        # On the final day nothing is dumped at midnight -- `_day_refresh` does not run at
        # step 720 -- so every unit must reach a shed tile under its own steam or its whole
        # carried load is forfeited. Reserve the walk home.
        #
        # Only on the last day: firing this whenever the shed was already near its cap at dawn
        # was measured at -$77 mean / -$115 min on 144 episodes, i.e. nothing. `_unit_ops` haul
        # discipline reacts to the same condition without spending a job on all ten units.
        last = (day >= SEASON_DAYS - 1)
        reserve = 5 if last else 0
        n = len(units) * max(1, (turns_left - reserve) // 2)
        runs = {}
        for _ in range(3):
            take = ranked[:n]
            take.sort(key=lambda j: serpentine_key(j["pos"]))
            runs = split_runs(take, units, turns_left, deliver_reserve=reserve)
            fitted = sum(len(r) for r in runs.values())
            if fitted >= len(take) or fitted <= 0:
                break
            n = fitted
            if (time.monotonic() - t0) * 1000.0 > self.p["plan_ms"]:
                break
        self.queues = {i: list(r) for i, r in runs.items()}

    # -- execution ---------------------------------------------------------

    def _valid(self, job, tiles, day, stock=None, hour=0):
        """Is this job still worth the turn, given the board as it is now?

        Cheap re-validation beats replanning. A tile can change under a plan for reasons the
        planner cannot see coming -- a weed spawned on it at midnight, another unit got there
        first, the yield decayed to nothing -- and the fix is to drop that one job and walk on,
        not to rebuild the day.
        """
        x, y = job["pos"]
        tile = tiles[y][x]
        op = job["op"][0]
        if op == "PLANT":
            if tile is not None:
                return False
            # A PLANT whose seed has not arrived is not invalid, only early: `_unit_ops` parks
            # it and works something else. Past the grace window the order plainly never
            # cleared -- the slot cap or the budget refused it -- so drop the job and let the
            # tile reappear in tomorrow's deficit at no cost.
            if hour > self.p["seed_grace"] and stock is not None \
                    and stock.get(job["op"][1], 0) <= 0:
                return False
            return True
        if op == "DIG":
            return isinstance(tile, dict) and tile.get("kind") == "WEED"
        if op == "DROP":
            return True
        if op in ("BUILD_COOP", "BUILD_PASTURE"):
            return tile is None
        if op == "PICKUP":
            # The animal is bought with a market order that settles at the end of the turn, so a
            # PICKUP whose animal has not landed is early rather than invalid -- same shape as a
            # PLANT waiting on seed, and handled the same way in `_unit_ops`.
            return stock is None or stock.get(job["op"][1], 0) > 0 or hour <= self.p["seed_grace"]
        if op == "PLACE":
            return (isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE")
                    and tile.get("animal") is None)
        if op in ("FEED", "CARE", "COLLECT_FERTILIZER") or (
                op == "HARVEST" and isinstance(tile, dict)
                and tile.get("kind") in ("COOP", "PASTURE")):
            if not (isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE")):
                return False
            if op == "COLLECT_FERTILIZER":
                return bool(tile.get("fertilizer_available"))
            # Everything else needs the animal to still be there. It may not be: two missed
            # feeds and the engine removes it mid-plan, which turns every queued job on the tile
            # into a turn spent on nothing.
            if tile.get("animal") is None:
                return False
            if op == "FEED":
                return not tile.get("fed_today") and (stock is None
                                                      or stock.get(_FEED, 0) > 0)
            if op == "CARE":
                return not tile.get("cared_today")
            return tile.get("yield_units", 0) > 0
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return False
        if op == "FERTILIZE":
            # A dose already on the tile is not topped up, it is wasted: FERTILIZE overwrites
            # `fertilized_until_day` rather than extending it, and the old dose still had
            # nights left. The stock check matters too -- a FERTILIZE with an empty shed is a
            # silent no-op that costs the turn anyway.
            return (tile.get("fertilized_until_day", -1) < day
                    and (stock is None or stock.get("FERTILIZER", 0) > 0))
        if op == "WATER":
            return not tile.get("watered_today")
        if op == "HARVEST":
            return harvestable(tile, day)
        return True

    @staticmethod
    def _haul_pressure(shed, invs):
        """Shed slots that shed contents plus every carried bag would fill, as a fraction of 100.

        This is the number that decides whether produce still in a bag is safe. `_day_refresh`
        empties every bag into the shed at midnight and `_add_shed` silently discards whatever
        does not fit, so above 1.0 the farm is about to destroy its own harvest. Seeds are not
        counted because they live in an uncapped slot of their own; fertilizer and animals are,
        because `_add_shed` counts every key in the shed dict.
        """
        carried = sum(sum((inv or {}).values()) for inv in (invs or []))
        return (sum((shed or {}).values()) + carried) / float(SHED_CAPACITY)

    def _unit_ops(self, units, tiles, invs, seeds, unlocked, day, hour, shed=None):
        """One op per unit: perform the head job if standing on it, otherwise step toward it.

        Positions come from the observation every turn rather than from a simulated plan, so
        the executor cannot drift out of sync with the engine.

        `stock` is the seed count the plan is allowed to spend this turn, decremented as PLANT
        ops are issued. Without it two units routed to two empty tiles would both be told to
        plant the last melon seed and one of them would burn its turn on a no-op. FERTILIZER
        rides in the same dict -- it is drawn from the shed rather than from `seeds`, but it is
        the same kind of shared, decrementable stock and the key cannot collide with a crop.
        """
        stock = dict(seeds)
        stock["FERTILIZER"] = (shed or {}).get("FERTILIZER", 0)
        # Feed grain and the animals themselves ride in the same dict: both are drawn from the
        # shed rather than from `seeds`, and both are shared between units, which is the property
        # `stock` exists to track. Feed grain gets a prefixed key because "WHEAT" is already
        # taken -- `seeds["WHEAT"]` counts sacks to plant, and validating a PLANT against the
        # grain in the shed would let two units plant one seed.
        stock[_FEED] = (shed or {}).get("WHEAT", 0)
        for animal in ANIMALS:
            stock[animal] = (shed or {}).get(animal, 0)
        ops = []
        for idx, pos in units:
            q = self.queues.setdefault(idx, [])
            while q and not self._valid(q[0], tiles, day, stock, hour):
                q.pop(0)
            # Head job's seed has not landed yet -- the order for it settles at the end of this
            # turn. Park it at the back and do something else: the tile is still plantable
            # later today, whereas a turn spent waiting is gone. Bounded by the queue length,
            # so a queue of nothing but seedless PLANTs falls through to PASS rather than
            # spinning.
            for _ in range(len(q)):
                if not (q and q[0]["op"][0] in ("PLANT", "PICKUP")
                        and stock.get(q[0]["op"][1], 0) <= 0 and len(q) > 1):
                    break
                q.append(q.pop(0))
                while q and not self._valid(q[0], tiles, day, stock, hour):
                    q.pop(0)
            carrying = sum((invs[idx] or {}).values()) if idx < len(invs) else 0
            # -- haul discipline. SELL settles from the shed and HARVEST fills a bag, so
            # produce is worth nothing until somebody walks it home. On a normal day midnight
            # does that for free -- occupancy peaks in the thirties and nothing is lost -- so
            # interrupting a run to deliver would be a wasted commute. The end of the season
            # breaks that assumption. Measured over six episodes, 74 of the 75 items destroyed
            # per episode die in one midnight dump on day 28; on the worst seed 142 strawberries,
            # about $40k at that turn's price, went in a single `_add_shed` call because the bags
            # held 219 units against a shed with 77 slots free. The SELL issued that turn asked
            # for 215 and settled 23, because 196 of those strawberries were in bags.
            #
            # So the trigger is projected midnight occupancy rather than carried load alone, and
            # the trip is gated on the shed having somewhere to put the load: if the shed is
            # itself full the answer is to sell, not to haul, and `crowded` is already doing that
            # with the same threshold.
            room = SHED_CAPACITY - sum((shed or {}).values())
            if (q and carrying >= self.p["haul_min"] and room >= self.p["haul_min"]
                    and self.pressure > self.p["haul_trigger"]
                    and q[0]["op"][0] != "DROP"):
                q.insert(0, dict(pos=nearest_shed(pos, unlocked), op=["DROP"],
                                 tier=0, value=0.0))
            if not q:
                if carrying:
                    # Nothing left to do and a full pack: bank it. On normal days midnight
                    # would dump it anyway, but a load in the shed can be SOLD today, and
                    # today's price is the only one this load is guaranteed to see.
                    q.append(dict(pos=nearest_shed(pos, unlocked), op=["DROP"],
                                  tier=0, value=0.0))
                else:
                    ops.append(["PASS"])
                    continue
            job = q[0]
            if tuple(pos) != tuple(job["pos"]):
                mv = step_toward(pos, job["pos"])
                ops.append([mv] if mv else ["PASS"])
                continue
            if job["op"][0] == "PLANT":
                crop = job["op"][1]
                if stock.get(crop, 0) <= 0:
                    # Standing on the tile with the seed still in flight -- the purchase for
                    # it settles at the end of this turn. Wait one turn rather than dropping
                    # the job; this only happens at hour 0, and only on day 0 in practice.
                    ops.append(["PASS"])
                    continue
                stock[crop] -= 1
            elif job["op"][0] == "PICKUP":
                # Same story as a seed: the BUY_ANIMAL settles at the end of the turn.
                if stock.get(job["op"][1], 0) <= 0:
                    ops.append(["PASS"])
                    continue
                stock[job["op"][1]] -= 1
            elif job["op"][0] == "FEED":
                stock[_FEED] = stock.get(_FEED, 0) - 1
            elif job["op"][0] == "FERTILIZE":
                stock["FERTILIZER"] = stock.get("FERTILIZER", 0) - 1
            ops.append(list(job["op"]))
            if job.get("then"):
                # Multi-op job: run the next op next turn, on this tile unless the job names
                # another. Used for the WATER that has to follow a PLANT on the same day, and for
                # the PICKUP at the shed that has to be followed by a PLACE on the structure.
                q[0] = dict(job, op=job["then"], then=None, acts=1,
                            pos=job.get("then_pos", job["pos"]), then_pos=None)
            else:
                q.pop(0)
        return ops

    # -- market ------------------------------------------------------------
    #
    # Market orders are the cheapest thing in the game: they are applied in a pass of their own,
    # so none of this costs a unit turn. Ten orders per turn, unbounded quantity per order,
    # 24 turns a day. The only real budget here is cash and the ten-order slot count.

    def _fert_buy(self, shed, money, day=0):
        """Doses to buy this turn: a standing stock, topped up, bounded by cash and shed room.

        A standing stock rather than an order sized to the day's jobs, because the two cannot be
        computed in that order -- the job list is built at dawn from the stock, and the stock
        would have to be sized from the job list. A buffer breaks the circularity for about
        $2,400 of working capital, which comes back as the doses are used.

        Bounded by shed room as well as cash: the shed holds 100 items in total across every
        good, and anything over that at midnight is destroyed, so a large fertilizer buffer
        would quietly start eating the harvest it exists to increase.

        Nothing is bought once the endgame liquidation has started. The two rules together
        otherwise churn: the top-up rebuys the buffer the sell just emptied, and because
        `BUY_PRODUCT` charges `price_for(inv - 1)` while `SELL` pays `price_for(inv)` the round
        trip is exactly break-even -- 168 units a season through the market for zero dollars,
        burning a slot on the one day the produce needs every slot it can get.
        """
        if not self.p["fert"] or day >= SEASON_DAYS - self.p["endgame_days"]:
            return 0
        have = shed.get("FERTILIZER", 0)
        room = SHED_CAPACITY - sum(shed.values())
        want = min(self.p["fert_stock"] - have, max(0, room - 10))
        if want <= 0:
            return 0
        # Priced pessimistically off base: BUY_PRODUCT walks the curve upward as it buys, and
        # `money` here is already net of seed and wages.
        afford = int(max(0.0, money) // (_base("FERTILIZER") * 1.2))
        return max(0, min(want, afford))

    def _market_orders(self, obs, me, shed, seeds, minv, prices, unlocked, day, hour):
        """Seed, then wages, then land, then sales -- inside a ten-slot budget.

        The engine applies fixed-price orders in the order given and settles SELL afterwards,
        so the order of this list *is* the cash priority for the turn, and its length is
        capped at `MAX_MARKET_ORDERS`. Both matter, and the slot cap bites harder than the
        cash does, because `HIRE` carries no quantity: one slot per hand. A full roster is
        therefore ten slots -- the entire turn's budget -- which starves seed and sales on
        exactly the days the farm is big enough to need them. That failure is silent and
        self-sustaining: no seed bought means no PLANT job survives the hour-1 re-cut, and
        the seed order is sized off those very jobs, so the farm stops planting for good.

        So the greedy list is built in reverse priority: seed and sales are sized first,
        `HIRE` gets whatever slots are left over (never fewer than two), and the rest of the
        roster arrives over the following turns. Delaying a hand by a turn costs one
        tile-visit; the Fibonacci price is indexed by `hires_today`, so it does not change.

        Seed leads on cash because it is the only compounding purchase, but its budget is net
        of the day's wage bill so it cannot starve the roster it depends on. Land comes last
        because it is the one purchase that returns nothing this season unless there is seed
        and labour to work it -- an unplanted quadrant is $1,000 of nothing.
        """
        money = me.get("money", 0.0)

        # Sized before hiring so they cannot be crowded out of the slot budget.
        seed = self._seed_orders(seeds, prices, max(0.0, money - self.wage_reserve),
                                self.p["seed_slots"])
        seed_cost = sum(o[2] * OBJECT_TABLE[o[1]]["seed_cost"] for o in seed)
        sell = self._sell_orders(shed, minv, prices, (obs.get("private") or {}).get("inventories"),
                                 day)

        # Hiring, early in the day only -- a hand hired at noon gets half a shift for the same
        # money. `hires_today` comes from the observation, so a hire that failed for lack of
        # cash, or one deferred by the slot cap, is simply re-attempted next turn.
        hire = []
        if hour <= self.p["hire_hours"]:
            slots = max(2, MAX_MARKET_ORDERS - len(seed) - min(len(sell), 3) - 1)
            done = me.get("hires_today", 0)
            cash = money - seed_cost
            for i in range(min(slots, max(0, self.n_hire - done))):
                c = fib_hire_cost(done + i)
                if cash < c:
                    break
                hire.append(["HIRE"])
                cash -= c

        out = seed + hire
        money -= seed_cost + sum(fib_hire_cost(me.get("hires_today", 0) + i)
                                 for i in range(len(hire)))

        # Fertilizer, one slot with a quantity. Ahead of land because a dose is the best-value
        # visit measured on the board -- +2 melon units for one visit and ~$100 -- while a
        # quadrant only pays if there is seed and labour spare to work it. Suspended while the
        # shed is crowded: a dose bought into a shed at 100 items displaces a strawberry worth
        # $110 that the engine then discards without a word.
        n_fert = self._fert_buy(shed, money, day) if not self.crowded else 0
        if n_fert > 0:
            out.append(["BUY_PRODUCT", "FERTILIZER", n_fert])
            money -= sum(price_for("FERTILIZER", max(0, minv.get("FERTILIZER", I0) - k - 1))
                         for k in range(n_fert))

        # Livestock, one slot each and at most one animal a day. The day cap is the point: the
        # dawn plan is recomputed once, `_market_orders` runs every turn, and an order sized from
        # a dawn snapshot would be re-issued for all 24 hours -- measured on seed 0 before the
        # guard went in, that bought 24 cows on day 13 and took the bank from $87k to $14k.
        # `BUY_ANIMAL` is a fixed-price order settled before the SELL pass, and it lands the
        # animal in the shed for a PICKUP to collect, so it is bought a day ahead of the PLACE.
        a = self.animals
        if a and a["n_buy"] > 0 and "animal" not in self.ordered \
                and money >= OBJECT_TABLE[a["animal"]]["buy_cost"]:
            out.append(["BUY_ANIMAL", a["animal"], 1])
            money -= OBJECT_TABLE[a["animal"]]["buy_cost"]
            self.ordered["animal"] = 1
        # Feed of last resort. WHEAT is one of the two goods the engine will sell back, and an
        # animal two days unfed is gone for good along with the rest of its season, so a farm
        # whose own wheat has run down buys the grain rather than lose the asset. Sized against
        # animals owned *or on order*, because the grain has to be in the shed on the day the
        # PLACE lands: measured on the first build, which sized this off `live` alone, the shed
        # held zero wheat for the whole early season and two to five animals starved.
        mouths = (a["live"] + a["held"] + a["n_buy"]) if a else 0
        need = mouths * 2 - shed.get("WHEAT", 0) if mouths else 0
        if need > 0 and "wheat" not in self.ordered and day < SEASON_DAYS - 1 \
                and money >= need * price_for("WHEAT", minv.get("WHEAT", I0)):
            out.append(["BUY_PRODUCT", "WHEAT", need])
            self.ordered["wheat"] = need

        nxt = next((q for q in QUADRANT_ORDER if q not in unlocked), None)
        # Only when the allocator actually ran out of tiles, and only while a bought quadrant
        # still has time to return the money: the shortest cycle is carrot at four days, and a
        # quadrant bought after that cannot be planted into anything that finishes.
        if nxt and self.tile_limited and day + CROP_PLAN["CARROT"]["harvest_day"] < SEASON_DAYS:
            if money >= LAND_PRICES[nxt] * self.p["land_margin"]:
                out.append(["BUY_LAND"])
                money -= LAND_PRICES[nxt]

        # Sales last in the list and first to survive the cap: they settle in their own pass,
        # so their position among the fixed orders is irrelevant, and unsold stock is the only
        # thing here that can be destroyed outright by a shed overflow at midnight. Three slots
        # are guaranteed normally and five once the shed is crowded, because the sell list is
        # sorted dearest-first and it is the cheap tail -- the wheat and the eggs -- that both
        # fails to make the cut and fills the shed that discards the strawberries.
        floor = 5 if self.crowded else 3
        room = MAX_MARKET_ORDERS - len(out)
        if room < len(sell):
            out = out[:MAX_MARKET_ORDERS - min(len(sell), floor)]
        return out + sell[:MAX_MARKET_ORDERS - len(out)]

    def _seed_orders(self, seeds, prices, money, slots):
        """Buy exactly the seed the queued PLANT jobs are short of, within `slots` orders.

        The target is read off the live routing queues rather than off the dawn budget, and
        that is not a detail. A target expressed as a *holding* -- "hold 11 strawberry seeds"
        -- re-opens every time a seed is planted, so it buys the day's stock twice: once at
        dawn and again as the roster spends it. Counting outstanding jobs instead settles to
        zero, and it also means the spend is capped by what the routing actually fitted into
        the day. Seed for a tile no unit can reach today is cash locked up for nothing.

        Seeds survive the midnight refresh -- `_day_refresh` never touches `f.seeds` -- so
        anything bought and not planted is simply stock for tomorrow, not waste.

        Dearest crop first, because `BUY_SEED` takes a quantity: one slot covers a whole
        crop's order however large, so the only thing the slot cap can cost is a crop, and
        the cheapest crop is the cheapest to defer.
        """
        if slots <= 0:
            return []
        queued = {}
        for q in self.queues.values():
            for j in q:
                if j["op"][0] == "PLANT":
                    queued[j["op"][1]] = queued.get(j["op"][1], 0) + 1
        out = []
        for crop in sorted(queued, key=lambda c: -OBJECT_TABLE[c]["seed_cost"]):
            if len(out) >= slots:
                break
            short = queued[crop] - seeds.get(crop, 0)
            if short <= 0:
                continue
            cost = OBJECT_TABLE[crop]["seed_cost"]
            n = min(short, int(money // cost))
            if n <= 0:
                continue
            out.append(["BUY_SEED", crop, n])
            money -= n * cost
        return out

    def _sell_orders(self, shed, minv, prices, invs=None, day=0):
        """Sell orders sized against the shed *plus* what the units are still carrying.

        Carried units are counted because a SELL that names more than the shed holds is free:
        `_settle_one_unit` returns silently once `f.shed[resource]` is gone, so over-ordering
        costs neither a slot nor a dollar. Under-ordering is what costs. Market orders settle
        after the turn's unit ops, so a sell sized off the observed shed is always one dump
        behind the harvest -- measured on day 29 of seed 0, the agent saw 51 strawberries and
        ordered 51 while another 35 landed in the shed during that same turn. Over a season
        that lag stranded 23.6 strawberries at step 720 and destroyed another 11.6 to shed
        overflow during the final harvest wave: about $9.6k, 13% of bank, on one off-by-one.

        On the last days the reserve floor comes off and the input goods go too. Produce in the
        shed scores nothing at step 720, so any price beats holding, and the fertilizer buffer
        is $1.4k of working capital that has no remaining cycle to pay for.

        Feed grain is held back while any animal is alive. Wheat is the farm's cheapest crop and
        the shed's most tempting thing to clear, but a FEED with an empty shed is a silent no-op,
        and two of those in a row remove the animal permanently -- $400 and the rest of its
        fertilizer stream for $32 of grain. The hold is a rolling few days' worth rather than the
        season's, because the shed only has room for 100 items in total.
        """
        pool = dict(shed)
        for inv in (invs or []):
            for good, n in (inv or {}).items():
                pool[good] = pool.get(good, 0) + n
        endgame = day >= SEASON_DAYS - self.p["endgame_days"]
        total = sum(pool.values())
        crowded = total > self.p["crowded"] * SHED_CAPACITY
        # Published for `_market_orders`: a crowded shed changes the whole turn's priorities, not
        # just this list. Buying more input into a shed that is already discarding output is the
        # worst trade on the board, and the slot the purchase takes is a slot a sale needed.
        self.crowded = crowded
        hold = {}
        if self.animals and not endgame and not crowded:
            # Grain kept back for the feed programme, counted against animals owned or on order
            # so the shed is stocked before the first PLACE rather than after the first miss.
            # Wheat is the cheapest good on the board at $25 base, so holding a dozen costs the
            # farm ~$480 of sales against a $400 animal it keeps alive -- but only while there is
            # room for it. The shed discards silently at 100 items and the goods it would discard
            # instead are strawberries at $110, so a crowded shed sells the grain and the
            # `BUY_PRODUCT WHEAT` fallback buys it back on the day it is needed.
            mouths = self.animals["live"] + self.animals["held"] + self.animals["n_buy"]
            if mouths:
                hold["WHEAT"] = self.p["feed_hold"] * mouths
        out = []
        for good in sorted(pool, key=lambda g: -prices.get(g, 0)):
            if good not in MARKET_PARAMS:
                continue
            if good in _INPUTS and not endgame:
                continue
            have = pool[good] - hold.get(good, 0)
            if have <= 0:
                continue
            if endgame or crowded or good in self.p["always_sell"]:
                # MELON is in no shop basket, so its only drain is one unit a day from the
                # town centre and its price never recovers once pushed down. Holding it back
                # cannot earn a better price later -- it can only let the opponent, who sells
                # into the same inventory, take the top of the curve first.
                n = have
            else:
                n, mi, floor = 0, minv.get(good, 0), self.p["reserve"] * _base(good)
                while n < have and price_for(good, mi) >= floor:
                    n += 1
                    mi += 1
            if n > 0:
                out.append(["SELL", good, n])
        return out
