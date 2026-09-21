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

import json
import os
import time

from .constants import (ANIMAL_PRODUCT, ANIMAL_STRUCTURE, ANIMALS, BOARD_SIZE, CROP_PLAN, CROPS,
                        FERT_PLAN, I0, LAND_PRICES, MARKET_PARAMS, MAX_MARKET_ORDERS, OBJECT_TABLE,
                        PROFILE_1322, PROFILE_1327, QUADRANT_ORDER, SEASON_DAYS, SHED_CAPACITY,
                        SHED_TILES, TURNS_PER_DAY, apply_engine_profile,
                        crop_actions_per_day, drain_per_day_from_shops, fert_doses, fert_gain,
                        expected_drain_per_day_horizon,
                        fib_hire_cost, gain_days, needs_water, price_for, unlocked_shops_from_obs,
                        yield_cap)


# ---------------------------------------------------------------------------
# Runtime engine fingerprint — which market mechanics is the live engine running?
# ---------------------------------------------------------------------------

def read_config_version(config) -> str | None:
    """Version straight off the harness config, when the harness hands one.

    The real harness calls callable agents as `agent(observation, configuration)`
    (kaggle_environments.agent calls `callable_agent(obs, configuration)`), so on the
    ladder `townCenterSellInterval` is DECISIVE and certain: 24 -> 1.32.7, 12 -> 1.32.2
    (the two wheels differ on exactly five config rows; calibration/live.md's table).
    Returns None when config is absent or lacks the row — the config-less tiers (this
    repo's mirror) fall back to the melon-cadence probe instead.
    """
    try:
        tau = int(getattr(config, "townCenterSellInterval", None)
                  or (config or {}).get("townCenterSellInterval", None) or 0)
    except Exception:
        return None
    if tau == 24:
        return "1.32.7"
    if tau == 12:
        return "1.32.2"
    return None                       # a non-default override: leave the pin alone


def probe_melon_interval(inv_seq) -> int:
    """Town-centre interval read off MELON's inventory declines (config-less fallback).

    MELON sits in no shop basket, so its ONLY drain is the town centre — one unit per
    tick, and the town centre ticks every `tau` turns. The day-gap between consecutive
    observed declines is therefore exactly tau. Farm sells would *raise* inventory, not
    drain it, so any strict decline of a deep book is evidence of drain. The mirror
    clamps inventory at 0, so a book already at 0 hides its ticks — the caller supplies
    a deep-book series. Returns the mode of the gaps, 0 when nothing declined.
    """
    gaps = []
    for a, b in zip(inv_seq, inv_seq[1:]):
        if b < a:
            gaps.append(abs(b - a))
    if not gaps:
        return 0
    return max(set(gaps), key=gaps.count)


def fingerprint_engine(config, melon_inv_seq=()) -> str:
    """Decide which engine profile to run, apply it once, and return the verdict.

    Config first (certain); melon-cadence probe second (strong evidence, only used by
    config-less tiers); the pinned default third. Idempotent per process: the profile is
    applied once and cached, so pooled multi-episode runs keep the first verdict.
    """
    try:
        # Config evidence wins over a cached probe verdict: the config row is certain,
        # the probe is inference, and a config (real harness) arrives on turn 0 before
        # any probe could run. Non-12/24 rows read as None and change nothing.
        verdict = read_config_version(config) or _PROFILE_VERDICT
        if verdict is None and melon_inv_seq:
            tau = probe_melon_interval(melon_inv_seq)
            if tau in (12, 24):
                verdict = "1.32.7" if tau == 24 else "1.32.2"
        set_engine_profile(verdict or "1.32.7")   # the pin — the best-calibrated guess
        return _PROFILE_VERDICT or "1.32.7"
    except Exception:
        return _PROFILE_VERDICT or "1.32.7"    # never raise: the pin is always safe


def set_engine_profile(version: str) -> None:
    """Apply `version`'s profile if it is not already active (idempotent, never raises)."""
    global _PROFILE_VERDICT
    try:
        if version != _PROFILE_VERDICT:
            apply_engine_profile(version)
            _PROFILE_VERDICT = version
    except Exception:
        pass


def engine_verdict() -> str:
    """The active engine profile ("1.32.7" until a fingerprint has run)."""
    return _PROFILE_VERDICT or "1.32.7"


_PROFILE_VERDICT = None
from .route import (MOVES, capacity, manhattan, nearest_shed, serpentine_key, split_runs,
                    step_toward)

# ---------------------------------------------------------------------------
# Tunables. Phase 4 sweeps these; nothing below reads a magic number directly.
# ---------------------------------------------------------------------------

PARAMS_BASE = None  # set at import time, right after the literal below

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
    max_hands=11,            # roster cap: s8 shepherd arm needs the 11th for the stream
                             # (measured as part of the s8 profile, real tier, 24 episodes).
                             # Was 8, where every larger roster measured as a loss -- because
                             # hands hired after the hour-1 re-cut got no route and PASSed all
                             # day. With the growth-triggered re-cut in `_act`, 10 is +$5,709
                             # mean / +$3,827 p10 on seeds 0-47 and +$5,293 / +$3,904 on the
                             # disjoint 48-95, both 144 episodes against a ~$1k standard error.
    # -- THE WINDFALL CAP. The mechanism behind the mutual-adoption tail (p10 $10.9k against a
    # $50.6k mean; see analysis/autopsy.py), and the single largest open lever.
    #
    # Day 11 lands the melon windfall (~$7.6k) and the allocator plants the whole 96-tile board
    # in one dawn -- ~$7.4k of seed against a $3k start. Cash then sits at ~$0 for days 12-16
    # while the new board yields NOTHING (strawberry does not pay until day 21+), but the wages
    # for the roster that same dawn plan created (~$90/day) do not pause. So hands are cut 8 ->
    # 0, 70+ live tiles go unwatered, two dry nights turn them to weeds, and by day 17 the farm
    # is 8 tiles with no mature crop and no cash to re-plant: dead for the remaining two weeks
    # of the season. Seen identically on bad seeds 24/13/17 AND on good seed 4 (which still
    # collapses 97 -> 11 tiles on day 18); the bad seeds are the ones whose early shop draw
    # cannot fund the bridge. `corr(mine, total) = +0.86` says this is a SEED effect, and this
    # is the seed effect.
    #
    # The fix prices the board's own upkeep into the planting decision: the dawn seed budget may
    # spend only `windfall_pct` of the bank (plus half a roster-day of wages per held-back day).
    # The farm lands ~55 tiles on day 11 instead of 96, tops up as harvest income arrives, and
    # keeps its roster alive through the yield gap. `windfall_pct=1.0` with `windfall_reserve=0`
    # reproduces the old behaviour exactly.
    #
    # MEASURED (2026-09-16, analysis/windfall_grid.py + the mutual-adoption meta in
    # `eval.evaluate --opps self_live`, where BOTH seats run the candidate -- the only panel
    # that answers "what if the whole field plays this cell", which is how the peer retune was
    # judged). 96-seed panels, two disjoint halves:
    #
    #   cell            0-95  mine/p10/min              96-191  mine/p10/min
    #   old  1.00/0     $37,019 /  8,773 /  5,645      $39,204 /  9,725 /  6,683
    #   new  0.45/0     $56,184 / 35,748 / 21,791      $53,628 / 32,070 / 25,996
    #
    # +$14-19k of mean, +$22-27k of p10 and +$16-19k of min, with the sign agreeing on both
    # disjoint seed halves -- the largest single adoption in the project, larger than the peer
    # retune. The response surface is a broad plateau from 0.30 to 0.45 (every capped cell
    # lands $51.8-54.1k mutual on the holdout), so the choice is robust rather than lucky.
    #
    # Against the built-in opponents the cap is inert to the dollar (checked on 24 seeds across
    # two opponents and on full 576-episode blocks at 0.55/2): their weak market never
    # depresses the farm's cash, so even the capped budget still buys the whole board. The cap
    # is liquidity-proportional -- it binds exactly when the pot is contested, which is where
    # the tail lives. Head-to-head cells ARE chaotic (0.45/0 beats the old cell 51/96 while
    # 0.55/2 ties it 54/96); the mutual meta is the selector that held, and it is the one whose
    # failure mode -- both farms dead -- is also the ladder's worst outcome for us.
    windfall_pct=0.45,       # fraction of the bank the dawn seed budget may spend. [tail]
    windfall_reserve=0,      # extra days of full-roster wages held back on top of half a day.
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
    plan_ms=-1.0,            # deterministic: no wall-clock gate. A positive value (ms) makes
                             # _replan bail to the previous plan on slow machines, which is
                             # non-deterministic and can flake pack.sh's bank-for-bank gate --
                             # set one only when profiling on loaded hardware.
    # worst measured dawn plan is ~0.3 ms, so the ceiling never bound in practice anyway.
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
    # Expected-drain floor for the lookahead -- MEASURED REJECT, kept off and documented.
    # The hypothesis (AGENTS.md): a late STRAWBERRY-shop draw under-prices strawberry in
    # `horizon_head`, both farms under-plant it, and the p10 tail is the money left on the
    # table. The floor raises the projected drain to `expected_drain_per_day_horizon` while
    # the observed list is below it. Measured on 144 mutual-adoption episodes, 2026-09-08:
    #   weight 0.00: mean $50,579  p10 $10,867  min $7,298  (incumbent)
    #   weight 0.25: mean $50,631  p10 $10,867  min $7,298  (noise)
    #   weight 0.50: mean $50,118  p10 $10,867  min $7,298  (slightly worse)
    #   weight 1.00: mean $36,742  p10 $8,280   min $5,940  (collapses: both farms over-plant
    #               strawberry, shrink the load-bearing melon opening, thirst 50 -> 72)
    # p10 NEVER moves at any weight: the tail is not strawberry under-planting. The floor
    # also compounds `drain_frac=1.0`'s over-credit of demand that is shared, not ours.
    # Reopen this axis only with a mechanism that targets the bad seeds specifically.
    drain_floor_goods=("STRAWBERRY",),   # crops whose lookahead would get the floor
    drain_floor=0.0,                     # weight on that floor; 0.0 = off (measured reject)
    # Runtime market monitor (P2). The engine's market is a public order book and every turn
    # publishes (inventory, price) for every good; the town's drain is computable from the
    # observed shop list, so residual inventory movement attributes the opponent exactly:
    # opp_net = my_buys - my_sells - town_drain - d_inv. The estimator has three clients:
    #   1. a drain-scale diagnostic `d` that catches a ladder config overriding tau or the
    #      draw rule: d = observed/expected town drain (1.0 == 1.32.7), fitted only on deep
    #      books so the book's zero-clamp cannot bias it; scale `drain_per_day_from_shops`
    #      and the `horizon_head` drain by it, dead-banded at +-15%.
    #   2. `opp_credit`: opponent realized supply per day (units/day, goods the farm itself
    #      trades) credited straight into the lookahead's horizon heads at dawn. Static
    #      drain_frac=1.0 becomes self-tuning: vs a passive farm it reads 0, vs a peer it
    #      reads their actual volume.
    #   3. `sell_infer`: blend the price-dependent reserve floor toward the measured tau.
    #      The static floor only bites on glut curves; strawberry's realized price is flat at
    #      228% of base on every decile and wheat's realized exceeds it 40-fold, so the
    #      floor has never once been the margin on a crop we grow -- while a tau read off
    #      the live book generalizes to any price-curve override.
    # Gated off (`monitor=0`) until it wins the block gate; enables for free diagnostics.
    monitor=0,
    opp_credit=0.0,                      # weight on the monitor's opponent-supply estimate
    sell_infer=0.0,                      # weight on the measured tau floor in _sell_orders
    # Work stealing: when a unit's queue drains while other runs still hold tail jobs, it
    # takes the nearest feasible tail rather than PASSing until midnight. Tail-only so the
    # owner keeps its head and the steal costs them at most their last job; `then` jobs
    # (WATER-after-PLANT) are never stolen. Off by default pending the block gate.
    work_steal=1,            # adopted 17 Sep on the corrected mirror: 4-block ADOPT (+$229
                             # aggregate, every block positive, 192 seeds x 3 opponents).
                             # The old INCONCLUSIVE was partly the H2 seat-0 quote bias.
    # Opening book (days 0..book_until_day-1). `opening_book=1` serves the donor script
    # recorded in `book_file` while a per-day signature (public shop unlocks + our own
    # money/shed/seeds totals) matches what the donors saw; any miss halts the book for
    # that day and the normal planner takes over mid-day at zero cost. Market inventory
    # is deliberately NOT in the signature: it is opponent-contaminated, and a different
    # opponent must not disengage an otherwise-identical opening. Off by default pending
    # its gate; the file ships so a replay-informed rebuild can flip it on without a
    # code change (bundle.py's single-file variant tolerates a missing file).
    opening_book=0,
    book_until_day=6,
    book_file=None,          # None -> opening_book.json next to this file (CWD-independent)
    # Engine-version profile. "auto" (ADOPTED 16 Sep) fingerprints the live engine at
    # runtime: the harness config row first — the real harness calls callable agents as
    # agent(obs, configuration), so on the ladder tau=12 vs 24 is READ, not guessed —
    # then the melon-cadence probe for config-less tiers, then the 1.32.7 pin. Every
    # measured branch is >= pin: on a 1.32.7 engine auto is byte-identical (mirror seeds
    # and the real-tier dir run), and on a 1.32.2 engine it is worth +$13.5k on seed 9
    # ($57,685 vs $44,201 mis-detected). A non-default config override reads None and
    # falls back to the pin (the monitor's d diagnostic still covers the override).
    # "pin" reverts to static 1.32.7 constants; "1.32.2"/"1.32.7" force. The runbook's
    # replay-fingerprint step remains the post-hoc confirmation of what auto chose.
    force_engine="auto",
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
    # Ladder dump-gates (2026-09-19, episode 110850828). The in-mirror field shared our own
    # dumping habits, so every previous gate on the sell RATE was measured in a vacuum; live,
    # the winners DRIP (never more than ~30 units of anything a day) and a one-turn dump
    # collapses the shared book for the whole season: our melon sold 714 units at $26 while
    # the opponent's sold at $148, our wheat hit $2.9 on a crowd dump and was bought back at
    # $30-47 the same week, and the endgame liquidation named 1,025 strawberries at $15.5
    # against their realized $175-238. Two caps fix the rate without touching the timing.
    # A fast cap valve (2x cap) opens whenever the shed crosses (1-crowded) * capacity so
    # the un-sold tail cannot be discarded at midnight by overflow -- a lost unit is worse
    # than a bad price. At crowded=0.55 the valve is closed below 55 shed items and
    # open in the top 45 -- the old all-or-nothing `crowded` branch kept its emergency
    # (the valve cap ~= have there) while gaining a graded regime in between.
    crowd_cap_mult=2.0,      # crowded/un-capped sells sized at this many days of town drain
    crowd_floor_frac=0.5,    # price floor for capped sells: this fraction of the `reserve` floor
    endgame_cap=0,           # 0 = endgame full-clear (measured correct); >0 meters endgame sells
    # Melon opening cohort cap (2026-09-19, ladder episode 110850828). The donor day-0 book
    # buys 23 melon seeds; planted same-day they ripen in one synchronized wave and the
    # always-sell branch dumped 714 units at $26 against the opponent's realized $148. Eight
    # seeds keeps the factory without the synchronized glut.
    # PLANNER-PATH enforcement added 2026-09-20, then REVERTED SAME DAY on real-tier
    # evidence. The 0-4 batch (110897820/110918559/110922997/110928677) did show the
    # allocator planting the donor's 23-melon cohort with the book OFF, and the clamp
    # does bind (day-0 BUY_SEED MELON = exactly 8, surplus to carrot/wheat). But the
    # real-tier A/B (12 seeds x self+passive, the tier the ladder itself runs) measured
    # the clamp ALONE at mean $51,162 vs $59,481 caps-off (-$8.3k), strawberry collapsing
    # 134 -> 68 units: the day-0 melon windfall is what FUNDS the d11-12 strawberry
    # spray, so capping the cohort defunds the whole strawberry programme. The ladder's
    # own replay confirms order sizes are not settled units (winners emit 6,000-unit
    # clear-all sells; over-naming is free), so the 834-unit 'dump' overstated the
    # settled wave. Mechanism stays for gated experiments; 0 = allocator unclamped and
    # serve-time trim off (the shipped default behavior).
    melon_opening=0,
    # Dawn-pace cap (2026-09-19, replays 110850828 / 110874286). On the LADDER, when land
    # unlocks on day 11 the dawn planner sprayed a windfall into one crop (61 strawberry +
    # 36 wheat in two dawns; the 0-4 batch sprayed 37-80 strawberry tiles); the cohort
    # ripened synchronized and sold at 23% of base while the winner drip-sold the same crop
    # at 4-7x the unit price off 26 committed tiles.
    # REVERTED 2026-09-20 after a one-day default-ON trial. The flip followed AGENTS.md
    # epistemics (ladder outranks panel) on the strength of the 0-4 batch's d27 strawberry
    # craters; the real-tier A/B then rejected it 3x same-day: ON = $51,023 mean / p10
    # $41,445 vs OFF = $59,481 / $43,767. Per-unit strawberry price DID rise (228% vs
    # 197% -- the price-protection premise is real) but the d11-12 cohort IS the season's
    # main strawberry inventory (12-day cycle): pacing it halved volume and the gross
    # loss dwarfed the price gain. Epistemics refinement for the ledger: the panel's
    # blind spot applies to SELL-side axes (it mirrors our dumping habit); production-
    # VOLUME axes are governed by real engine physics, which the real tier does
    # reproduce. Mechanism stays available behind this param for future gated trials;
    # None = off (the shipped default behavior).
    dawn_pace=None,
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
    n_animals=8,
    # ^ submission8 default (2026-09-20): the shepherd stream made a 6-8 herd servable
    # (funnel: 0 escapes on all 6 probe episodes) and the real-tier A/B measured s8 at
    # +$2.8k mean / +$5.8k p10 / x3.6 disaster floor vs the n=2 control. Milk+fertilizer
    # revenue tripled. The old n=2 rationale (milk as the un-flooded second stream) stands;
    # A structure has to beat this many dollars per visit to be worth building, judged against
    # the crop it displaces. Melon realizes $81 a visit, which is the number to beat -- but the
    # rank is computed from the shop list as it stands, and on day 0 no shop has opened yet, so
    # the drain credit that makes milk worth $229 rather than $160 is not in it. A cow scores $79
    # at dawn on day 0 and $96 by mid-season; the margin sits below the pessimistic end so the
    # programme starts on day 0, where the fertilizer stream is worth 29 doses instead of 15.
    # H4 re-gate (2026-09-17): under the corrected mirror the rank is priced with DAILY feed
    # cost and the observed ladder pool (~10,000 units of each animal product, price floored
    # all season -- replays 110082767/110093672/110088235), which puts an honest cow at 55-58
    # $/visit, i.e. under the old 60 gate and the herd never buys (funnel probe: buys=0 all
    # season). 50 passes cow/sheep while the goose (~40-49) stays out; the two ladder losses
    # ran herds of 9+ and the animal products realized floor price throughout.
    animal_margin=50.0,
    # KT_V2 D2 (source-verified 2026-09-18, ADOPTED): the engine accrues `pending_care_bonus`
    # on every cared-AND-fed day and pops `min(max_held, 1 + bonus)` -- with our daily feeding,
    # daily CARE doubles a cow's milk (11 -> 66 units/season) and triples a sheep's wool.
    # A/B on the panel, both disjoint 24-seed blocks, sign agreeing on all three objectives:
    # mean +$1,603 / +$2,242, p10 +$1,025 / +$1,936, min +$311 / +$655, win 121->126 /
    # 123->124, milk revenue 3.5x. The old "measured, not worth it" verdict was rendered on
    # a mirror with wrong CARE semantics.
    animal_care=True,
    # Dairy recipe (2026-09-19): day-gated herd ramp -- restraint while the farm is
    # cash-poor (the day-0 seed round is the only compounding purchase), releasing the
    # target only once the first yields land. Engine premises verified in vendored
    # source: FEED needs grain from the unit's bag on the animal's tile, BUY_ANIMAL
    # settles into the shed during the market phase, and two unfed days in a row is an
    # escape. Re-gated 2026-09-19 against ladder episode 110850828 (winner realized $89.1k
    # from animals vs our $6.0k milk): raising THIS build's target to 4 was re-measured on
    # the panel and REJECTED again -- mean $54,686 vs $56,852 at n=2 with the same sell
    # fixes, because the ramp's day-14 full-herd leaves too few milk days to pay for the
    # displaced crop labour. The live livestock gap belongs to the livestock-led build
    # (V4, 54% animal revenue), not to this crop-led one; the ramp below stays so any
    # future target raise is paced, and the mechanism is no-op at 2.
    herd_ramp=True,
    ramp_cap_early=2,       # herd ceiling before the first yields (the recipe's day-2 level)
    ramp_full_day=14,       # day the ramp reaches n_animals (first milk ~day 8, full by 14)
    # -- opening_led (2026-09-21, submission10). The five s9 ladder games (ledger) and the
    # Majkel1337 dossier name the same loss: the d0-12 livestock head start. Winners assemble
    # 10-16 animals by d12-15 behind a full roster while this build's first placement lands
    # d15 (s8's deliberate day-0 seed priority). These knobs move the OPENING, not the streams:
    # day-0 animals before seeds, a herd target at the dossier's lower band, a roster floor.
    # Feeding guarantees stay with the shepherd stream and the buffer gates (unchanged).
    opening_led=False,      # False = s8 behaviour byte-identical
    led_cow0=1,             # BUY_ANIMAL COW issued on day 0, before the seed round
    led_wheat0=2,           # feed grain beside it: the shed is stocked before dawn 1
    led_herd_target=12,     # season herd target under opening_led (dossier band: 12-20)
    led_roster_floor=0,     # minimum roster from day 0 -- MEASURED NEGATIVE (mirror seed 0:
                            # -$25k; forced 9-10 hires spend the bank to $0 daily and the
                            # cash-gated herd never assembles). Knob kept at 0 = off.
    # -- elite_counter_v1 (2026-09-21, dossier 63-game spec). The d0 script upgraded from
    # "one cow" to the measured elite order stream: t1 COW+WHEAT-feed, t2 COW+SHEEPx3+HIREx4,
    # then a per-species ramp to a MIXED herd (cow milk engine + sheep wool lane). The knobs
    # below are OFF by default; the arm turns them on together via `elite_script`.
    elite_script=False,     # False = s10 behaviour byte-identical
    led_sheep0=3,           # SHEEP issued on day 0 turn 2 (wool lane, dossier 3/game)
    led_cow2=1,             # second COW issued on day 0 turn 2
    led_hire2=4,            # HIRE orders inside the t2 script block
    herd_cow=9,             # mixed-herd target envelope (dossier: cow 9-11)
    herd_sheep=4,           # sheep lane (dossier: 3-5; wool separates elite wins from losses)
    herd_goose=0,           # geese compete for service turns; off unless the panel prices them in
    wool_floor=0.55,        # elite WOOL sell floor past d12 (x base; trough is $40-80)
    wool_hold_price=150,    # WOOL recovery-hold floor: sell only at or above this ($/unit)
    wool_hold_cap=28,       # shed units of crashed wool held through the trough (dossier: 28)
    seed_floor=300,         # elite opening: seeds never budget below this while cash lasts
    expansion_cash=5,       # elite: at >= this many animal-costs in bank, margin gate opens
    feed_backbone=True,     # wheat planted to close the projected feed deficit (infrastructure)
    service_margin=3,       # slack turns an elite shepherd loop must fit inside its unit's day
    backlog_cap=8,          # max unplaced animals in the shed before new buys pause (2x share)
    feed_bridge=4,          # days of grain that must cover every mouth before an animal buy
    # Visits a day charged against the crop allocation for each structure the farm owns. Zero,
    # measured: the honest rate is 1.6, and charging it cost $30k a seed by shrinking the farm
    # to make room for work the animals then failed to fill. See `_targets`.
    animal_load=0.0,
    # Wheat held back from sale per animal owned or on order, so the feed is in the shed on
    # the day the PLACE lands. Zero falls back on `BUY_PRODUCT WHEAT`, which settles a turn
    # late. H4 re-gate: 6/mouth left the shed at zero on exactly the days the first cow
    # needed feeding (wheat at $25 base is also the cheapest thing on the board, so the sell
    # list clears it first); 12/mouth rides through cap days and still only holds 24-36.
    feed_hold=12,
    # Animals bought AND structures built per dawn (2026-09-19, ladder 110874286: the
    # winner ran ~22 animals against our 2-4). Hardcoded 1/1 means a 20-herd takes 20+
    # dawns to assemble in a 30-day season -- by the time the herd exists there are no
    # milk days left to pay for it, which is why every past herd-raise measured worse.
    # `animal_pace=k` lets a dawn build up to k structures and buy up to k animals (still
    # ONE BUY_ANIMAL order per turn via `self.ordered` -- the 24-cows-on-day-13 guard --
    # and still gated on buffer_ok / in-time / a scaled cash floor), so a raised
    # n_animals target is REACHABLE. Feed, care and roster all already scale with mouths.
    # Default 1 = byte-identical to the incumbent.
    animal_pace=3,
    # ^ submission8 default: the assembly speed the funnel required to reach a 6-8 herd
    # inside the season (1/1 needs 20+ dawns). Still ONE BUY_ANIMAL order per turn via
    # `self.ordered`, still gated on buffer_ok / in-time / the scaled cash floor.
    # -- shepherd stream (2026-09-19, scope v4). Animal chores as a first-class scheduled
    # stream: dedicated units run computed chore loops (shed PICKUP of N wheat -> nearest-
    # neighbor pastures -> FEED/CARE/COLLECT_FERTILIZER/HARVEST -> DROP) sized to a priced
    # turn budget, instead of bidding for spare capacity in the serpentine lottery. The
    # ladder winner's ~$144k animal economy is unreachable without it: the A/B/C/D run
    # showed supply scales with mouths but FEED VISITS do not (7/7 animals escaped with
    # the buffer in the shed). 0 = incumbent byte-identical.
    shepherd_mode=1,
    # ^ submission8 default (2026-09-20): the dedicated chore stream is the layer that made
    # >2 animals viable at all. A/B: +$2.8k mean, +$5.8k p10, floor $12k -> $43k. 0 = the
    # pre-shepherd behaviour, kept as an off-switch.
    shepherd_share=4,       # units dedicateable to shepherding at dawn (s8: ~2 animals/unit,
                            # share must cover the herd's stream)
    shepherd_bag=24,        # shepherd bag cap: DROP segment when the load reaches this
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

# Frozen copy of the shipped defaults. `sweep.score` mutates the live PARAMS dict for the
# episode at hand; on the in-process real-engine tier that mutation survives across
# episodes (there is no pool worker to re-import the module), so every episode must start
# from this snapshot. Sweeps then test candidates against true defaults instead of
# compounding — the holdout rows that all print identical numbers are the fingerprint of
# that bug.
PARAMS_BASE = dict(PARAMS)

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


def horizon_head(crop, inv, pipe, shops, frac, day=0, floor_goods=(), floor_w=0.0,
                 opp=(), d_scale=1.0):
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

    `opp` (units/day, positive = they add) and `d_scale` (observed/expected town drain) come
    from the runtime monitor when PARAMS.monitor is on: the opponent term is credited
    directly into the head, and `d_scale` scales the town drain to whatever the live engine
    is actually doing. Both default to inert.
    """
    cyc = CROP_PLAN[crop]["harvest_day"] if crop in CROP_PLAN else 0
    drain = drain_per_day_from_shops(crop, shops) * cyc * frac * (d_scale if d_scale else 1.0)
    if floor_w > 0 and crop in floor_goods:
        drain = max(drain, expected_drain_per_day_horizon(crop, day, cyc) * cyc * frac * floor_w)
    return inv.get(crop, I0) + pipe - drain + (opp.get(crop, 0.0) * cyc if opp else 0.0)


def effective_prices(tiles, unlocked, shed, inv, prices, shops=(), frac=0.0, cap=0.0,
                      day=0, floor_goods=(), floor_w=0.0, opp=(), d_scale=1.0):
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

    `opp` and `d_scale` come from the runtime monitor when PARAMS.monitor is on: the
    opponent's measured net supply is credited straight into the head, and the town drain
    is scaled to whatever the live engine is actually doing. Both default to inert.
    """
    out = dict(prices)
    for crop in CROP_PLAN:
        if crop not in MARKET_PARAMS:
            continue
        pipe = pipeline_units(tiles, unlocked, shed, crop)
        head = horizon_head(crop, inv, pipe, shops, frac, day, floor_goods, floor_w,
                            opp, d_scale)
        out[crop] = marginal_price(crop, head, cap)
    return out


def marginal_rank(crop, inv, pipe, alpha, shops=(), frac=0.0, cap=0.0,
                  day=0, floor_goods=(), floor_w=0.0, opp=(), d_scale=1.0):
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
    head = horizon_head(crop, inv, pipe, shops, frac, day, floor_goods, floor_w, opp, d_scale)
    px = marginal_price(crop, head, cap)
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
                    # H4: the dose rides in the unit's inventory (real FERTILIZE takes it
                    # from `inv`), so this is a three-act carry job: shed-access PICKUP,
                    # then the dose on the tile. Chained so the two legs cannot split.
                    shed_tile = nearest_shed((x, y), unlocked)
                    ferts.append(dict(pos=shed_tile, op=["PICKUP", "FERTILIZER", 1],
                                      then=["FERTILIZE"], then_pos=(x, y), acts=3,
                                      stock_key="FERTILIZER",
                                      tier=TIER_FERT, value=fv, crop=crop))
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
    # BUILD job that the router never gets to does not silently cost a planting. With the H4
    # fix the placement job RUNS from a shed-access tile (PICKUP needs one), so "farthest from
    # the shed" now costs a real commute on every placement -- but animals are 2-3 tiles a
    # season against ~90 plantings, and the tile-quality term still dominates.
    if animals and animals.get("n_build", 0) > 0:
        struct = "BUILD_COOP" if animals["struct"] == "COOP" else "BUILD_PASTURE"
        sheds = set(SHED_TILES.values())
        built = 0
        # Shepherd geometry (scope v4): with the stream on, new structures take the
        # shed-NEAREST empties instead of the farthest -- a chore loop's cost is the walk,
        # so clustering cuts the per-loop overhead from dozens of turns to single digits.
        # The spawn guarantee is unchanged: the four shed-access tiles stay off-limits
        # (the `spot in sheds` skip below), so hands still deploy cleanly.
        shepherd_near = bool(params["shepherd_mode"]) \
            and day < SEASON_DAYS - params["endgame_days"]
        while built < animals["n_build"] and len(empties) > ei:
            # Never on a shed tile. The engine treats those as ordinary empty ground, but PLACE
            # checks for a structure before it checks for the shed, so a pasture on (4,4) would
            # stop every unit standing there from banking what it carries.
            if shepherd_near:
                spot = min(empties[ei:], key=lambda p: manhattan(p, SHED_TILES["NW"]))
                empties.remove(spot)
            else:
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


def animal_programme(animal, day, care=None):
    """Units, doses, visits and wheat a single animal placed on `day` yields by season end.

    Derived from the spec rather than measured, so it stays true if calibration moves the
    numbers. Reproduces `analysis/animal_probe.py` exactly on all three animals.

    The programme is daily feed plus daily collection. The every-other-day schedule the first
    build shipped is one that a *planner* can follow but a *router* cannot hold: it leaves the
    animal sitting at consecutive_unfed=1 on every off day, so a single dropped job -- cut by
    `ranked[:n]` on a busy day, or beaten to the tile -- is fatal. Measured on the corrected
    mirror (H4 day): 4 animals bought, 3-4 escaped, 7-9 FEEDs executed of ~14 scheduled. One
    extra wheat a day (~$40) against a $300-500 animal and its season is the cheap side of
    that trade, and it makes a missed day non-fatal (unfed=1, tomorrow's feed resets it).

    CARE (re-derived 2026-09-21, elite_counter_v1 -- see the simulator block below): the
    bank accrues +1 per fed-and-cared day and RESETS at every production pop, so a day-0
    season programme is cow 36 milk / sheep 34 wool / goose 54 eggs against 11/8/26
    uncared units. The care multiplier is ~3x on a cow, ~4x on a sheep, ~2x on a goose --
    not the 2x the 2026-09-18 note claimed, and not the age-growing bank the old simulator
    priced (that inflated a day-0 cow to "66"). The cost is one standing visit per
    animal-day. `care` defaults to PARAMS['animal_care'] so every caller stays consistent,
    and False restores the pre-CARE programme exactly.
    """
    if care is None:
        care = bool(PARAMS.get("animal_care", False))
    spec = OBJECT_TABLE[animal]
    first, interval, cap = spec["first_yield_day"], spec["interval"], spec["max_held"]
    left = max(0, SEASON_DAYS - day)
    if left <= first:
        return None
    prod_days = [d for d in range(first, left) if (d - first) % interval == 0]
    if not prod_days:
        return None
    # ENGINE-EXACT EVENT SIMULATOR (elite_counter_v1, 2026-09-21). The old model priced the
    # care bank as if it grew with the animal's AGE forever (`sum(min(cap, 1 + d))` -- a
    # day-0 cow "66 milk"). That double-counts: the bank RESETS at every pop
    # (kaggriculture.py:826-828 pops `pending_care_bonus` and zeroes it) and the production
    # day's own care accrues AFTER the pop (:829-830). The engine sequence, mirrored below:
    # care banks +1 per fed-and-cared day; a production day pops min(cap, 1 + bank) and
    # zeroes the bank; the next bank is the days since the last pop (the first pop's bank
    # is the days since placement). A day-0 cow therefore pops 6,3,3,3... (36 milk), a
    # sheep 6,4,4... (34 wool), a goose 4,2,2... (54 eggs).
    #
    # Harvests are counted by TILE SIMULATION under the executor's pre-event policy
    # (harvest before any pop that would clip -- the P0-2 companion fix), not ceil(units/cap):
    # when the HARVEST lands depends on the held units between pops, and a cared sheep
    # (4-unit pops on a 6-cap tile) must be harvested before EVERY pop or two wool clip
    # per event. `clipped` is the never-harvest diagnostic the tests assert against.
    units = harvests = held = clipped = 0
    nheld = 0                     # a tile nobody ever harvests, for the clipping diagnostic
    bank = first if care else 0   # days of care banked before the first production event
    for d in prod_days:
        pop = min(cap, 1 + bank)
        if held + pop > cap:      # pre-event harvest: the executor empties before the pop
            harvests += 1
            held = 0
        units += pop
        held += pop
        clipped += max(0, (nheld + pop) - cap)
        nheld = min(cap, nheld + pop)
        bank = interval if care else 0   # cared days between consecutive pops
    if held > 0:
        harvests += 1             # final drain: the executor always empties the tile at the end
    cares = left if care else 0
    # A dose is available at the end of every day the animal survives; feeding is daily
    # (see the docstring -- the every-other-day schedule lost 3 of 4 animals to one dropped
    # job); the pack has to be emptied once per `max_held` units and once at the end.
    doses = max(0, left - 1)
    feeds = left
    setup = 3  # BUILD, PICKUP at the shed, PLACE
    return dict(units=units, doses=doses, feeds=feeds, cares=cares, clipped=clipped,
                harvests=harvests,
                visits=setup + feeds + doses + cares + harvests)


def mouths_buffer(shed, animal, built, live):
    """Wheat in the shed beyond the first day's feeding of the mouths it would add.

    Used as the livestock start gate: the first animal must not arrive on a dry shed. One
    animal-day is 1 wheat; the buffer is what remains after feeding everyone standing today.
    """
    return max(0, (shed or {}).get("WHEAT", 0) - max(0, live))


def _ramped_target(want, day, params):
    """Day-gated herd target (dairy recipe, 2026-09-19).

    Before the first yields (day < 8) the herd is capped at `ramp_cap_early`; from day 8
    the target releases linearly to `want` by `ramp_full_day`. A no-op whenever `want`
    is already at or under the early cap -- which is the measured optimum (2) -- so the
    mechanism only bites when a future sweep raises the herd target. One animal a day
    already bounds the SPEND (n_buy); this bounds the TARGET, so a raised target cannot
    order the whole herd on day 0.

    opening_led bypasses the ramp: its whole point is the d0-12 assembly the ramp delays,
    and its day-0 cash gate (the buy fires only when the bank affords it) plus the feed
    buffer gates replace the ramp's protection.
    """
    cap = params.get("ramp_cap_early", 2)
    if (not params.get("herd_ramp", False) or want <= cap
            or params.get("opening_led", False)):
        return want
    if day < 8:
        return cap
    span = max(1, params.get("ramp_full_day", 14) - 8)
    frac = min(1.0, (day - 8) / span)
    return max(cap, int(cap + frac * (want - cap)))


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

    PLACE is reached through the shed, so it is a THREE-act job (H4 fix, 2026-09-17): walk to
    a shed-access tile, PICKUP there (the real engine requires `_is_shed_adjacent`), then walk
    to the structure and PLACE. Emitted as one chained job -- `then`/`then_pos` -- so the legs
    cannot be split across units, which would leave one of them carrying an animal it has no
    instruction to put down. The old one-leg form relied on the mirror's missing location
    check; on the ladder it silently no-opped and every bought animal rotted in the shed.
    """
    out = []
    animal = tile.get("animal")
    if animal is None:
        # elite_counter_v1 P0-3: the shed may hold MORE THAN ONE species (the t2 script
        # buys COW and SHEEP the same day). The plan's primary species is tried first;
        # if its shed count is zero, the per-species shed map offers whatever else is
        # standing in the shed. Without this, bought sheep rot behind a cow-plan's gate.
        pick = None
        if plan.get("held", 0) > 0 and plan.get("animal") \
                and ANIMAL_STRUCTURE[plan["animal"]] == tile.get("kind"):
            pick = plan["animal"]
        else:
            for sp, n in (plan.get("held_by_species") or {}).items():
                if n > 0 and ANIMAL_STRUCTURE[sp] == tile.get("kind"):
                    pick = sp
                    break
        if pick:
            # Leg 1+2 from the shed-access tile the unit is already routed to; leg 3 walks to
            # this structure tile via then_pos. The chained form cannot split across units.
            shed_tile = nearest_shed((x, y), unlocked)
            out.append(dict(pos=shed_tile, op=["PICKUP", pick, 1],
                            then=["PLACE", pick], then_pos=(x, y), acts=3,
                            stock_key=pick,
                            tier=TIER_PLANT, value=plan["rank"], animal=pick))
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
    # Pre-event harvest (elite_counter_v1 P0-2), same trigger as `shepherd_chores`:
    # tonight's pop is min(cap, 1 + pending_care_bonus), so `units + 1 > cap` (the old
    # base-only form) let a cared sheep sit at 4 and clip 2 wool every event.
    next_pop = min(spec["max_held"],
                   1 + tile.get("pending_care_bonus", 0))
    if units > 0 and (endgame or units >= spec["max_held"]
                      or (prod_today and units + next_pop > spec["max_held"])):
        out.append(dict(pos=(x, y), op=["HARVEST"], tier=TIER_HARVEST,
                        value=units * prices.get(product, _base(product)), crop=product))

    if not tile.get("fed_today") and not endgame:
        # Daily feeding: unfed=1 must already outrank crop work (the animal is one miss from
        # escaping), but the ROUTINE feed is priced above ordinary GROW work too -- wheat plus
        # the asset's daily product value. The first build priced the routine feed at wheat_px
        # alone (~$40, cheapest job on the board): busy days cut it in `ranked[:n]` or dropped
        # it in split_runs, animals sat at unfed=1, and 3 of 4 bought animals escaped. The
        # premium is what buys the redundancy that makes a missed day non-fatal.
        due = tile.get("consecutive_unfed", 0) >= 1
        # H4: real FEED takes the wheat from the UNIT'S CARRIED inventory, so feeding is a
        # three-act carry job: shed-access PICKUP of one wheat, then FEED on the tile.
        # Chained so the legs cannot split; rescue feeds (an animal one miss from death)
        # keep their tier advantage over every crop job.
        #
        # The routine feed's honest value is wheat + the product the day would add + the dose
        # the day would make collectable: an unfed animal stops nothing today, but the escape
        # clock runs (two misses = asset gone), and with it the ~$110/day fertilizer stream
        # and the rest of the season's product. Priced at wheat alone (~$40) the job was the
        # cheapest GROW work on the board and lost every router cut; measured on the corrected
        # mirror, 3 of 4 bought animals escaped and the funnel leaked at exactly the days the
        # shed held no wheat. At ~$208 a cow's feed outbids watering honestly, by the same
        # arithmetic `plant_rank` uses everywhere else in this file.
        shed_tile = nearest_shed((x, y), unlocked)
        out.append(dict(pos=shed_tile, op=["PICKUP", "WHEAT", 1],
                        then=["FEED"], then_pos=(x, y), acts=3,
                        stock_key=_FEED,
                        tier=TIER_RESCUE if due else TIER_GROW,
                        value=(plan.get("worth", 4000.0) if due
                               else (plan.get("wheat_px", 40.0)
                                     + plan.get("daily_product", 0.0)
                                     + plan.get("fert_px", 0.0))),
                        animal=animal))

    # KT_V2 D2: one CARE visit a day. The engine accrues the bonus only when the animal was
    # BOTH cared and fed, so this rides on the already-guaranteed daily feed; it is priced at
    # one extra unit of the product (the marginal pop), which at realized prices makes it
    # competitive with watering -- and unlike watering it compounds: every accrued day raises
    # EVERY later pop. Gated on params['animal_care'] (default off) so the switch is the
    # sweep's to throw, and so False reproduces the incumbent exactly.
    if params.get("animal_care") and not tile.get("cared_today") and not endgame:
        out.append(dict(pos=(x, y), op=["CARE"], tier=TIER_GROW,
                        value=max(1.0, prices.get(product, _base(product)))))

    if tile.get("fertilizer_available") and params["fert"] and not endgame:
        out.append(dict(pos=(x, y), op=["COLLECT_FERTILIZER"], tier=TIER_PLANT,
                        value=plan.get("fert_px", _base("FERTILIZER"))))
    return out


def shepherd_chores(tile, day, endgame, care=True):
    """Which chore ops one live-animal structure needs today, in execution order.

    FEED first (the loop's bag is preloaded with the day's grain), then CARE, then the
    COLLECT of last night's single fertilizer drop (the engine sets `fertilizer_available`
    at the midnight tick and refuses a second collection -- the morning loop sweeps it
    exactly once), then HARVEST of banked product. Engine preconditions mirror `_valid`:
    each op is flag-guarded, so a chore emitted for a state that already changed is a
    no-op, never an error.
    """
    if tile.get("animal") is None:
        return []
    ops = []
    if not tile.get("fed_today") and not endgame:
        ops.append("FEED")
    if care and not tile.get("cared_today") and not endgame:
        ops.append("CARE")
    if tile.get("fertilizer_available") and not endgame:
        ops.append("COLLECT_FERTILIZER")
    # Pre-event harvest (elite_counter_v1 P0-2): the pop tonight is min(cap, 1 + bank)
    # where `bank` is the OBSERVED `pending_care_bonus` (the engine pops the bank before
    # today's care accrues, so the morning value is exact -- kaggriculture.py:823-828).
    # The old trigger `units >= cap` let a cared sheep (4-unit pops on a 6-cap tile) sit
    # at 4 and bank only 2 of its next 4: two wool clipped per event, forever. The bank
    # default keeps the trigger at the old behaviour when the field is missing it.
    if tile.get("yield_units", 0) > 0:
        spec = OBJECT_TABLE[tile["animal"]]
        cap = spec["max_held"]
        units = tile.get("yield_units", 0)
        age = day - tile.get("placed_day", day)
        prod_today = age >= spec["first_yield_day"] \
            and (age - spec["first_yield_day"]) % spec["interval"] == 0
        if endgame or units >= cap or (prod_today and units > 0
                                       and units + min(cap, 1 + tile.get("pending_care_bonus",
                                                                        0)) > cap):
            ops.append("HARVEST")
    return ops


def shepherd_loops(struct_tiles, day, unlocked, n_units=1, bag_cap=24, care=True,
                   balance=False):
    """Computed chore loops for the shepherd stream, plus their priced turn budget.

    `struct_tiles` is [(x, y, tile_dict)] over every LIVE structure. Returns
    `(loops, budget, loop_costs)`: `loops` is at most `n_units` job lists (clustered
    nearest-neighbor from the shed tiles, segmented by `bag_cap` so no shepherd ever
    carries 30+ items into a 100-slot shed); `budget` is the total turns one pass over
    every loop costs; `loop_costs[i]` is the exact turn cost of loop `i` — the number
    the elite service gate compares per-unit against one shepherd's day (a loop that
    overruns its own unit's day is cut at the tail, and under elite care budgets the
    tail is a CARE, not a spare op).

    A loop reads: shed PICKUP of the remaining feed count (one op, batched -- the engine
    loads N in one action), then per structure in walk order its chores, a DROP at the
    shed when the bag hits the cap, a reload if feeds remain. Every job after the head
    carries `carried=True` so FEED validity passes on the bag, not the shed counter.
    """
    if n_units <= 0:
        return [], 0, []
    endgame = day >= SEASON_DAYS - 1  # loops never run the endgame: herd is liquidated
    items = []
    for (x, y), tile in struct_tiles:
        ops = shepherd_chores(tile, day, endgame, care=care)
        if ops:
            items.append(((x, y), ops))
    if not items:
        return [], 0, []

    # Cluster nearest-neighbor, seeded one per shed tile so parallel shepherds start apart.
    # The cluster grows only while its own day still fits: one unit's day is ~2 turns per
    # visit (op + walk) with the ~6-turn commute to its run. Without the fit bound the inner
    # loop drains every structure into cluster 1, `loops` stays length 1 no matter what
    # n_units allows, and a 4-herd overloads its single shepherd into missed feeds.
    sheds = [p for q, p in SHED_TILES.items() if q in unlocked] or [SHED_TILES["NW"]]
    # One unlocked quadrant leaves one legal-looking pickup tile -- but every shed-access
    # tile accepts a PICKUP (the engine spawns hands on all four regardless of ownership),
    # so extra shepherds seed from the remaining access tiles instead of folding into
    # cluster 1 and overloading it into missed feeds.
    extra = [p for q, p in SHED_TILES.items() if q not in unlocked]
    sheds = (sheds + extra)[:n_units]
    left = list(items)
    clusters = []
    if balance and n_units > 1:
        # Elite loops: BALANCED, not greedy-nearest. The greedy builder prices each item's
        # leg as its own distance-to-shed, so a chained cluster's real walk cost (item to
        # item to ... to shed) is under-counted and the "fits" cluster really costs up to
        # 2x the shepherd's day -- the executor then cuts its tail (cares first) and the
        # exact gate reads the overload and freezes growth. Dealing the items round-robin
        # (snake order: nearest, farthest, nearest...) gives near-equal loops that each
        # fit the day, so every animal's FEED and CARE actually executes.
        clusters = [[] for _ in range(min(n_units, len(items)))]
        ordered = sorted(left, key=lambda it: manhattan(it[0], sheds[0]))
        for i, it in enumerate(ordered):
            k = i % len(clusters)
            if i // len(clusters) % 2 == 1:
                k = len(clusters) - 1 - k
            clusters[k].append(it)
        left = []
    per_unit_day = 2 * capacity(3.0 + 1.5 * max(0, len(unlocked) - 1))
    for seed in sheds:
        if not left:
            break
        first = min(left, key=lambda it: manhattan(it[0], seed))
        left.remove(first)
        cluster = [first]
        cost = manhattan(first[0], nearest_shed(first[0], unlocked)) + len(first[1])
        while left:
            nxt = min(left, key=lambda it: min(manhattan(it[0], c[0]) for c in cluster))
            step_cost = manhattan(nxt[0], cluster[-1][0]) + len(nxt[1])
            if (cost + step_cost > per_unit_day and len(clusters) < n_units - 1):
                break          # this shepherd's day is full; leave the rest for the next
            left.remove(nxt)
            cluster.append(nxt)
            cost += step_cost
        clusters.append(cluster)

    loops, budget, loop_costs = [], 0, []
    for cluster in clusters:
        feeds = sum(1 for _, ops in cluster if "FEED" in ops)
        head_n = min(feeds, bag_cap)
        loop = []
        if head_n > 0:
            loop.append(dict(pos=nearest_shed(cluster[0][0], unlocked),
                             op=["PICKUP", "WHEAT", head_n], stock_key=_FEED,
                             acts=1, is_loop=True))
        pos, load, served_feeds = cluster[0][0], 0, 0
        # Feeds first. The executor runs the queue until the day runs out, so when a loop
        # overflows, its TAIL is what gets cut -- and in nearest-chain order the tail held
        # the farthest animals' feeds. Every escape in the shepherd traces (seed 0 d18-25)
        # was that cut. Two passes: every FEED at the front of the loop, so an overloaded
        # day sacrifices harvests and cares, never a life.
        ordered_items = ([(p, ["FEED"]) for p, ops in cluster if "FEED" in ops]
                         + [(p, [op for op in ops if op != "FEED"])
                            for p, ops in cluster if any(op != "FEED" for op in ops)])
        for (x, y), ops in ordered_items:
            step = manhattan(pos, (x, y))
            budget += step
            for op in ops:
                job = dict(pos=(x, y), op=[op], acts=1, is_loop=True)
                if op == "FEED":
                    served_feeds += 1
                    load += 1
                    job["carried"] = True
                elif op == "HARVEST":
                    load += 1
                loop.append(job)
                budget += 1
            pos = (x, y)
            # Segment: walk home and DROP before the bag could overflow the shed, reload
            # grain if this cluster still owes feeds (head_n covered only the first bag).
            if load >= bag_cap and (served_feeds < feeds or load > 0):
                loop.append(dict(pos=nearest_shed(pos, unlocked), op=["DROP"], acts=1,
                                 is_loop=True))
                budget += manhattan(pos, loop[-1]["pos"]) + 1
                rest = feeds - served_feeds
                if rest > 0 and not endgame:
                    loop.append(dict(pos=loop[-1]["pos"], op=["PICKUP", "WHEAT",
                                                              min(rest, bag_cap)],
                                     stock_key=_FEED, acts=1, is_loop=True))
                    budget += 1
                load = 0
        if load > 0:
            loop.append(dict(pos=nearest_shed(pos, unlocked), op=["DROP"], acts=1,
                             is_loop=True))
            budget += manhattan(pos, loop[-1]["pos"]) + 1
        loops.append(loop)
        loop_costs.append(budget - sum(loop_costs))   # this loop's own share of the total
    return loops, budget, loop_costs


# ---------------------------------------------------------------------------
# Runtime market monitor
# ---------------------------------------------------------------------------


class _MarketMonitor:
    """Learns the market from the public order book while the episode runs.

    The engine publishes every turn the exact inputs of its own price function --
    (inventory, price) per good -- and the town's drain is reconstructible from the observed
    shop list. Residual inventory movement is therefore attributable, exactly:

        inv1 - inv0 = my_sells + opp_net - town_drain - my_buys

    Three estimates come out of that:

    tau    realized $/unit price slope, per good, as a day-over-day secant of the live
           (inventory, price) pairs. Price is a pure function of inventory, so every day is
           a fresh sample of whatever curve the engine is actually running -- even one the
           ladder substituted for the shipped one. Consumed only by `sell_infer`.
    d      town-drain scale, fitted at dawn on goods this farm never trades (their residual
           is town drain alone), as observed/expected. Consumed through `d_use`, whose
           calibrated band is documented on the property.
    opp    opponent net supply per good, units/day, from the identity above. Zero while this
           farm trades the good exclusively (their private shed is invisible to us), and the
           moment they sell, it is not -- the d15-17 wheat dumps of a peer read +55 u/day.
           Consumed through `opp_credit`.

    With PARAMS.monitor on but both knobs at 0, the monitor measures and touches nothing:
    the policy is byte-identical to monitor off. Everything is wrapped in
    except-and-default: this module must never be the reason an episode forfeits, and a
    malformed observation degrades to the static model, which is what the knobs default to.
    """

    # Goods the tau sampler tracks: everything the farm itself buys or sells.
    _TAU_GOODS = ("WHEAT", "CARROT", "MELON", "STRAWBERRY", "FERTILIZER")
    # Goods this farm never trades: their day-over-day residual is town drain alone (plus
    # the opponent's animal products, which only ever bias the ratio UP -- see the min below).
    _DRAIN_GOODS = ("EGG", "MILK", "WOOL", "TOMATO")

    def __init__(self, params):
        self.p = params
        self.prev_inv = None      # last turn's book
        self.prev_px = {}
        self.day = None
        self.open_inv = {}        # book at this day's first turn
        self.open_px = {}
        self.shop_open = []       # shop list at this day's first turn
        self.shop_closed = []     # shop list at the previous day's first turn (its drain list)
        self.flow = {}            # good -> [buys, sells] committed today
        self.tau = {}             # good -> realized $/unit slope (EMA of daily secants)
        self.d = 1.0              # town-drain scale (EMA)
        self.opp = {}             # good -> opponent net units/day (EMA)
        self.diag = []            # (day, d) per fitted day -- diagnostics only

    @property
    def d_use(self):
        """The drain scale the planner sees. Three gates stand between the raw fit and the
        plan: an evidence gate (at least five fitted days -- a config override persists all
        season, so waiting costs nothing), a contamination band, and the clamp itself.

        The band is calibrated on measured runs, not theory: the in-mirror baseline reads
        d=0.84 (the opponent's own milk/egg/tomato sales depress every ratio a little even
        after the max), while a shop interval doubled to 8 turns reads d=0.61. The lower
        edge therefore sits at 0.72 -- everything above it is indistinguishable from the
        baseline contamination and is treated as exactly 1.0; below it is at least a 39%
        shop-side deficit, which no fair opponent can fake. Known blind spot, measured:
        a town-centre-interval override alone (12 vs 24 turns) reads d=1.02, because every
        untraded good is shop-dominated (milk: 12 shop units vs 1 town-centre unit a day)
        and the opponent contaminates the residual. A curve substitution IS visible, in
        `tau`. Inside the band the planner sees exactly 1.0 -- the static model, byte for
        byte."""
        if len(self.diag) < 5 or 0.72 <= self.d <= 1.30:
            return 1.0
        return max(0.5, min(2.0, self.d))

    def turn(self, obs, issued, shed=None):
        """Sample the book. Called every turn, after the action has been built. `shed` is
        this farm's shed at order time, used to cap the sell bookkeeping below."""
        try:
            market = obs.get("market") or {}
            inv = market.get("inventory")
            if not isinstance(inv, dict):
                return
            px = market.get("prices")
            px = px if isinstance(px, dict) else {}
            day = obs.get("day")
            if isinstance(day, int) and day != self.day:
                self.day = day
                self.open_inv = dict(inv)
                self.open_px = dict(px)
                # A shop unlocked at the start of day N drains during N, not during N-1:
                # the closed day's drain list is the PREVIOUS dawn's list, so keep it
                # before overwriting. Mixing them biased every third day's fit upward.
                self.shop_closed = list(self.shop_open)
                self.shop_open = list(unlocked_shops_from_obs(obs))
                self.flow = {}
            # This turn's committed flows. Market orders settle after the turn's unit ops
            # and before the next observation, so they belong to the inventory delta the
            # next turn sees. Only orders that move the public book count: SELL adds,
            # BUY_PRODUCT removes. BUY_SEED is fixed-price off-book, and HIRE, BUY_LAND and
            # BUY_ANIMAL move no market inventory at all.
            #
            # Both bookkeepings are CAPPED by what could actually have executed, because
            # the engine no-ops an order the farm cannot back: a SELL draws only from the
            # shed (units still carried cannot sell this turn), and a BUY_PRODUCT into a
            # full shed is refused outright. Counting raw order sizes overcounts sells by
            # the carried re-offered-every-turn factor -- measured at ~4x mid-season --
            # and that bias lands entirely on the opponent estimate, negative.
            sell_left = {}
            buy_left = {}
            if isinstance(shed, dict):
                room = SHED_CAPACITY - sum(n for n in shed.values() if isinstance(n, (int, float)))
                for g in self._TAU_GOODS:
                    n = shed.get(g, 0)
                    sell_left[g] = n if isinstance(n, (int, float)) else 0
            for o in issued or []:
                if isinstance(o, list) and len(o) >= 3 and o[1] in self._TAU_GOODS:
                    n = o[2] if isinstance(o[2], int) and o[2] > 0 else 0
                    if o[0] == "SELL":
                        cap = sell_left.get(o[1], n)
                        used = min(n, cap)
                        sell_left[o[1]] = cap - used
                        self.flow.setdefault(o[1], [0, 0])[1] += used
                    elif o[0] == "BUY_PRODUCT":
                        used = min(n, max(0, room)) if isinstance(shed, dict) else n
                        if isinstance(shed, dict):
                            room -= used
                        self.flow.setdefault(o[1], [0, 0])[0] += used
            self.prev_inv = dict(inv)
            self.prev_px = dict(px)
        except Exception:
            self.prev_inv = None

    def dawn(self):
        """Fit the day that just closed. Called from the dawn branch, where `prev_inv` is
        still the finished day's final book and `flow`/`open_inv` are still its own."""
        try:
            if not self.open_inv or self.prev_inv is None or self.day is None:
                return
            closed = self.day
            # -- tau: day-over-day secant of the live curve. Skips clamped endpoints
            # (inventory zeroed by the book's max(0, .) floor prices at $1 and would read
            # as an infinite slope) and quiet days (n0 == n1 carries no slope).
            for g in self._TAU_GOODS:
                n0, n1 = self.open_inv.get(g), self.prev_inv.get(g)
                p0, p1 = self.open_px.get(g), self.prev_px.get(g)
                if not all(isinstance(v, (int, float)) for v in (n0, n1, p0, p1)):
                    continue
                if min(n0, n1) <= 0 or n0 == n1:
                    continue
                slope = (p0 - p1) / float(n1 - n0)   # positive when the book tightened
                if 0.0 < slope < 500.0:
                    self.tau[g] = 0.7 * self.tau.get(g, slope) + 0.3 * slope
            # -- drain scale: goods we never trade. The opponent's supply contaminates
            # every one of them downward (their herd and their tomato rows ADD to the
            # book, which reads as the town draining LESS), so the least-contaminated
            # good carries the highest ratio and the fit takes the MAX, not the mean:
            # if any good is one the opponent does not produce this season, max == the
            # true scale exactly. A deep-book requirement (both endpoints >= 2000) keeps
            # the book's zero-clamp out of the fit.
            ratios = []
            for g in self._DRAIN_GOODS:
                n0, n1 = self.open_inv.get(g), self.prev_inv.get(g)
                if not (isinstance(n0, (int, float)) and isinstance(n1, (int, float))):
                    continue
                if min(n0, n1) < 2000.0 or n1 >= n0:
                    continue
                exp = drain_per_day_from_shops(g, self.shop_closed, day=self.day - 1)
                if exp >= 1.0:
                    ratios.append((n0 - n1) / exp)
            if ratios:
                self.d = 0.7 * self.d + 0.3 * max(0.5, min(2.0, max(ratios)))
                self.diag.append((closed, round(self.d, 3)))
            # -- opponent net supply on the traded goods, given d.
            for g in self._TAU_GOODS:
                if g == "FERTILIZER":          # the town never drains it; residual is all farms
                    continue
                n0, n1 = self.open_inv.get(g), self.prev_inv.get(g)
                if not (isinstance(n0, int) and isinstance(n1, int)):
                    continue
                f = self.flow.get(g, (0, 0))
                exp = drain_per_day_from_shops(g, self.shop_closed, day=self.day - 1) * self.d_use
                opp = (n1 - n0) - f[1] + exp + f[0]
                # Our own sell bookkeeping undercounts on dump days: units that land in
                # the shed mid-turn are sellable the same turn but were not in the shed
                # at order time, so executed sells exceed the capped flow and the
                # residual reads as opponent supply that is really ours. The bias is
                # one-signed and concentrated on the windfall/endgame waves, so a hard
                # per-day clamp at +-50 units (a peer's true sustained volume is well
                # under half of that -- measured ~11 wheat, ~7 strawberry per day)
                # keeps the signal and bounds the contamination.
                opp = max(-50.0, min(50.0, opp))
                self.opp[g] = 0.7 * self.opp.get(g, opp) + 0.3 * opp
        except Exception:
            pass

    def opp_supply(self):
        """Per-crop opponent net daily supply for the horizon heads, weighted by
        PARAMS.opp_credit and clamped to magnitudes a board can physically move."""
        out = {}
        w = self.p.get("opp_credit", 0.0)
        if w <= 0:
            return out
        for g, o in (self.opp or {}).items():
            try:
                out[g] = max(-200.0, min(200.0, float(o))) * float(w)
            except (TypeError, ValueError):
                pass
        return out

    def tau_floor(self, good, anchor_px, anchor_inv, mi):
        """Tau-projected price of unit `mi` (absolute market inventory), anchored at the
        observed (price, inventory). In-mirror the secant slope reproduces the static
        curve, so `sell_infer` only changes behaviour when the live curve is not the
        shipped one. Returns None until a slope has been measured."""
        t = self.tau.get(good)
        if t is None or anchor_px is None or anchor_inv is None:
            return None
        return float(anchor_px) - t * (float(mi) - float(anchor_inv))


# ---------------------------------------------------------------------------
# Opening book (replay-informed donor scripts for days 0..5)
# ---------------------------------------------------------------------------

_BOOK_MISSING = object()   # "never attempted" sentinel, distinct from a failed load (None)


def _sig_eq(a, b):
    """Signature component equality, tolerant of JSON's tuple->list round trip."""
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        return tuple(a) == tuple(b)
    return a == b


def _variant_sig_eq(sig, donor_sig):
    """Component-wise signature equality between the live dawn and a donor variant."""
    return len(sig) == len(donor_sig) and all(
        _sig_eq(sig[k], donor_sig[k]) for k in range(len(sig)))


def _book_path_default():
    """Book location resolved from THIS file, not the process CWD.

    The harness exec's main.py with an arbitrary CWD, so a relative "kagfarm/..." path
    would silently never load there; policy.py is properly imported in every context,
    so its own __file__ is the one reliable anchor.
    """
    try:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "opening_book.json")
    except NameError:                     # exotic exec context: fall back to CWD-relative
        return "kagfarm/opening_book.json"


def _load_opening_book(path):
    """Read the donor book, or None if absent/corrupt. Never raises.

    A missing or unreadable book must be indistinguishable from `opening_book=0` -- the
    submission entry point's whole contract is that nothing here can forfeit an episode,
    and a data file is exactly the kind of thing a sandbox strips.
    """
    try:
        with open(path) as f:
            raw = json.load(f)
        # days: {"0": [ {"sig": [...], "hours": [...]}, ... ]} -- keep the variants.
        return {int(d): list(v) for d, v in (raw.get("days") or {}).items()}
    except Exception:
        return None


def opening_book_signature(obs):
    """The per-dawn book key: what our own opening does and what the world drew.

    Public randomness (the day's shop unlock draw) plus our own observable state (money,
    shed total, seed total). Market inventory is deliberately excluded -- it is
    opponent-contaminated and must not disengage an otherwise-identical opening.
    """
    me = (obs.get("farms") or [{}])[(obs.get("player", 0))]
    priv = obs.get("private") or {}
    shops = tuple(sorted((obs.get("town") or {}).get("unlocked_shops") or []))
    return (shops,
            int(round(me.get("money", 0.0))),
            int(round(sum((priv.get("shed") or {}).values()))),
            int(round(sum((priv.get("seeds") or {}).values()))))


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
        self._book = _BOOK_MISSING
        self._book_halt_days = set()   # days whose signature missed; halted for the day
        self._book_decided = set()     # days currently serving
        self._book_variant = {}        # day -> index of the matched book variant
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
        # -- market monitor: fitted price curves, inferred town drain scale and opponent
        # supply (see PARAMS.monitor), updated from the public book every turn.
        self.mkt = _MarketMonitor(self.p) if self.p.get("monitor") else None
        self.opp = {}             # per-crop opponent net supply, from the monitor
        # Set by `_sell_orders` each turn, read by `_market_orders` in the same turn.
        self.crowded = False
        self.pressure = 0.0
        # A full roster costs $143 for the day against $80 for one melon seed, so wages are
        # simply held out of the seed budget rather than traded off against it.
        self.wage_reserve = sum(fib_hire_cost(i) for i in range(self.p["max_hands"]))
        self.last_error = None
        # engine fingerprint state (inert while PARAMS.force_engine == "pin")
        self.engine = None            # verdict once detection has run
        self.melon_hist = []          # MELON book depth per turn, for the cadence probe

    # -- entry point -------------------------------------------------------

    def act(self, obs, config=None):
        t0 = time.monotonic()
        try:
            return self._act(obs, t0, config)
        except Exception as e:                    # a raise here forfeits the episode
            self.last_error = repr(e)
            n = len(self._me(obs).get("hands") or [])
            return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}

    @staticmethod
    def _me(obs):
        i = obs.get("player", 0)
        return (obs.get("farms") or [{}, {}])[i]

    def _act(self, obs, t0, config=None):
        me = self._me(obs)
        day = obs.get("day", obs.get("step", 0) // TURNS_PER_DAY)
        hour = obs.get("hour", obs.get("step", 0) % TURNS_PER_DAY)
        priv = obs.get("private") or {}
        tiles = me.get("tiles") or [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        unlocked = set(me.get("unlocked_quadrants") or ["NW"])
        prices = (obs.get("market") or {}).get("prices") or {}
        inv = (obs.get("market") or {}).get("inventory") or {}
        # -- engine fingerprint (PARAMS.force_engine): which market mechanics is live?
        # "pin" (default) = 1.32.7 constants, byte-identical to the shipped build;
        # "auto" = config row if the harness hands one, else the melon-cadence probe;
        # "1.32.2"/"1.32.7" = force. Applied at most once per process (see
        # `fingerprint_engine`), so pooled multi-episode runs keep the first verdict.
        if self.p.get("force_engine", "pin") != "pin":
            hist = self.melon_hist
            hist.append(inv.get("MELON", I0))
            if len(hist) > 40:
                del hist[:len(hist) - 40]
            mode = self.p["force_engine"]
            if mode in ("1.32.2", "1.32.7"):
                set_engine_profile(mode)
            elif self.engine is None:
                self.engine = fingerprint_engine(config, hist if len(hist) > 1 else ())
            self.engine_detected = engine_verdict()
        # -- opening book: decide once per dawn whether this episode is a replayed opening.
        # After a halt (signature missed the book) the planner takes over for the rest of
        # the day at zero cost; served days must skip the local plan so the donor's dawn
        # commitments (market orders, roster) are the ones that get routed.
        book_on = self.p.get("opening_book")
        if book_on:
            if self._book is _BOOK_MISSING:
                self._book = _load_opening_book(self.p.get("book_file") or _book_path_default())
            if day < self.p["book_until_day"] and day not in self._book_halt_days:
                if day in self._book_decided:
                    # Decided at this day's dawn: serve the whole day. The signature
                    # necessarily drifts within the day (market orders settle), so it
                    # is checked ONCE at dawn; mid-day divergence (weeds, weevil) is
                    # caught by the next dawn's check.
                    self._book_use = True
                else:
                    sig = opening_book_signature(obs)
                    variant_idx = None
                    if self._book:
                        variant_idx = next(
                            (i for i, v in enumerate(self._book.get(day) or [])
                             if _variant_sig_eq(sig, v.get("sig") or [])), None)
                    self._book_use = variant_idx is not None
                    if self._book_use:
                        # Record WHICH variant matched: _book_serve reads the donor moves
                        # from it (this index used to be re-derived there incorrectly, and
                        # the TypeError was swallowed into a silent planner takeover).
                        self._book_variant[day] = variant_idx
                        self._book_decided.add(day)
                    else:
                        self._book_halt_days.add(day)
            else:
                self._book_use = False
        else:
            self._book_use = False
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
            # Fit the day that just closed, then read this morning's estimates. With the
            # monitor off (default) both stay empty and every model below is byte-identical
            # to the static one.
            if self.mkt is not None:
                self.mkt.dawn()
                self.opp = self.mkt.opp_supply()
            self.eff = effective_prices(tiles, unlocked, shed, inv, prices, self.shops,
                                        self.p["drain_frac"], self.p["px_cap"], day,
                                        self.p["drain_floor_goods"], self.p["drain_floor"],
                                        self.opp, self.mkt.d_use if self.mkt else 1.0)
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

        if self._book_use:
            served = self._book_serve(obs, day, hour, len(units))
            if served is not None:
                return served
            # No donor move for this hour (book shorter than the day, or a malformed
            # entry): the planner takes over mid-day, and it has a current plan because
            # the dawn branch always runs its normal local planning while serving.
        ops = self._unit_ops(units, tiles, invs, seeds, unlocked, day, hour, shed)
        market = self._market_orders(obs, me, shed, seeds, inv, prices, unlocked, day, hour)
        out_market = market[:MAX_MARKET_ORDERS]
        if self.mkt is not None:
            self.mkt.turn(obs, out_market, shed)
        return {"farmer": ops[0], "hands": ops[1:], "market": out_market}

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
        # The windfall cap (see PARAMS): the seed budget may not spend the whole bank, because
        # the board it buys has to be watered by a roster whose wages do not pause for the
        # yield gap. Half a day of wages plus `windfall_reserve` more stays out of reach on
        # every dawn; on an ordinary dawn the wage reserve is already the tighter constraint
        # and this min() is inert. Gated on more than one quadrant being unlocked, because the
        # whole mechanism is a post-land-expansion event: the day-0 opening spends ~$2k of the
        # $3k stake into a single quadrant, it is the measured load-bearing move (-$56k if
        # capped), and on a single-quadrant dawn the old budget is the tighter number anyway.
        if self.p["windfall_pct"] < 1.0 and len(unlocked) > 1:
            keep = self.wage_reserve * (0.5 + max(0, self.p["windfall_reserve"]))
            budget = min(budget, keep + self.p["windfall_pct"] * max(0.0, money))
        land = 25 * max(1, len(unlocked))
        cap = {c: self.p["mix_cap"] * mix[c] / total * land for c in mix}
        # Day-0 melon cohort cap (see PARAMS `melon_opening`). Ladder 0-4 batch: with the
        # book OFF the allocator filled day 0 with the donor's 23-melon cohort in all four
        # games (834 units dumped day 10) because the only trim lived in `_book_serve`.
        # The cap is a property of the allocator now: it binds on every dawn-0 path, book
        # ON or OFF, and the marginal loop sends the surplus tiles to the next-best crop.
        mo = self.p.get("melon_opening", 0)
        if day == 0 and mo and "MELON" in cap:
            cap["MELON"] = min(cap["MELON"], mo)
        # -- wheat backbone (elite_counter_v1 P1): the herd's feed is INFRASTRUCTURE, not
        # inventory. Reserve a wheat block sized to the mouths it must feed: mouths x
        # (turns_per_day x feed_days) tiles, enforced as a floor on WHEAT's cap in the
        # marginal allocation. The 173-seed elite number is an OUTCOME of feed coverage,
        # not a target; the coverage math is the policy.
        if self.p["elite_script"] and self.p["feed_backbone"]:
            mouths_n = ((self.animals.get("live", 0) + self.animals.get("held", 0)
                         + self.animals.get("n_buy", 0) + self.animals.get("n_build", 0))
                        if self.animals else 0)
            # Dawn-0/1: the script's herd is CERTAIN to arrive within a day (settlement
            # FSM keeps retrying) -- plan for it, not for the still-empty shed, or the
            # backbone is a day late and the animals eat the bridge dry.
            if day <= 1:
                script_herd = (self.p["led_cow0"] + self.p["led_cow2"]
                               + self.p["led_sheep0"])
                mouths_n = max(mouths_n, script_herd)
            # A tile yields ~4 units/cycle (~1 unit/tile-day over its 4-day cycle +
            # replant), so a mouth needs ~1.5 tiles standing: 5 mouths = 8 tiles.
            wheat_floor = -(-mouths_n * 3 // 2)
            if wheat_floor and "WHEAT" in cap:
                cap["WHEAT"] = max(cap["WHEAT"], wheat_floor)
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

        # -- MANDATORY backbone allocation (elite, smoke-caught): a cap alone did nothing
        # -- the marginal loop still ranked melon above wheat, the seed round bought 4
        # melons and zero wheat, the field never fed, and the whole d0 herd escaped at
        # d8-9 with grain $0 in the shed. Feed is infrastructure: the wheat tiles are
        # allocated FIRST, ahead of the marginal contest, whenever a herd stands or is
        # on order.
        if self.p["elite_script"] and self.p["feed_backbone"] and wheat_floor > 0 \
                and "WHEAT" in cap:
            n_w = min(wheat_floor - live.get("WHEAT", 0), cap["WHEAT"], empty)
            cost = OBJECT_TABLE["WHEAT"]["seed_cost"]
            short = max(0, n_w - seeds.get("WHEAT", 0))
            # Invades the wage reserve if it must: the backbone is the herd's survival
            # and $80 of wheat seed outranks a hypothetical hand. The roster is demand-
            # sized, so on a light day the reserve is idle cash anyway.
            if short * cost <= max(0.0, budget - spent) + self.wage_reserve:
                want["WHEAT"] = plan["WHEAT"] = n_w
                spent += short * cost
                pipe["WHEAT"] += n_w * CROP_PLAN["WHEAT"]["units"]
                load += n_w * crop_actions_per_day("WHEAT")
                empty -= n_w

        # Why the loop stops is the only diagnostic that says where the next acre is. It is
        # recorded per pass and read after the break, so `self.limit` describes the pass that
        # actually failed rather than an accumulation over the whole allocation.
        veto = {}

        while empty > 0:
            best, best_r = None, 0.0
            veto = {}
            # Dawn-pace gate (replays 110850828/110874286): a dawn may REPLACE the crop's
            # live board and grow it by at most `dawn_pace` tiles. Replacing is not the crime
            # -- the melon factory replants its finished 8-tile cycle every dawn and blocking
            # that cost $12k on the panel -- the crime is the windfall spray that multiplied
            # committed acreage in one morning (1 -> 42 strawberry tiles) and ripened it as
            # one synchronized glut. The day-0 book serve never reaches this loop.
            pace = self.p["dawn_pace"]
            for crop in mix:
                if pace is not None and want.get(crop, 0) >= live[crop] + pace.get(crop, 8):
                    veto[crop] = "pace"
                    continue
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
                                  self.p["drain_frac"], self.p["px_cap"], day,
                                  self.p["drain_floor_goods"], self.p["drain_floor"],
                                  self.opp, self.mkt.d_use if self.mkt else 1.0)
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
        self.limit = "tiles" if empty <= 0 else "+".join(sorted(set(veto.values()), key=str))
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
        # Expansion threshold (elite smoke, seed 0): with $30k in the bank and idle
        # service capacity, both product ranks sit under `animal_margin` (in-mirror both
        # prices have crashed by d15) and the plan freezes at the opening herd -- the
        # margin was calibrated to gate EARLY buys against crop opportunity cost, not
        # to veto mid-season expansion when the cash has no better use.
        elite_margin = self.p["animal_margin"]
        if (self.p["elite_script"]
                and money >= self.p["expansion_cash"] * max(
                    OBJECT_TABLE[sp]["buy_cost"] for sp in ("COW", "SHEEP", "GOOSE"))):
            elite_margin = 0.0
        best, best_r, best_prog = None, elite_margin, None
        ranks = {}
        for animal in ANIMALS:
            r, prog = animal_rank(animal, day, inv, self.shops, self.p["drain_frac"],
                                  self.p["px_cap"], fert_px, wheat_px)
            ranks[animal] = (r, prog)
            if prog is not None and r > best_r:
                best, best_r, best_prog = animal, r, prog

        # Count what is already standing. The incumbent species wins over the theoretical best:
        # a structure is built for one species, and re-ranking mid-season would strand a pasture
        # or leave a half-grown cow for a fresh sheep.
        built = live = 0
        incumbent = None
        starving = False
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
                        starving = starving or tile.get("consecutive_unfed", 0) >= 1
        for animal in ANIMALS:
            if shed.get(animal, 0):
                incumbent = incumbent or animal
        best = incumbent or best
        if best is None:
            return None
        # Care is unconditional; expansion is not. The incumbent's own rank may sit under the
        # margin gate on a given day (the gate prices the MARGINAL animal against the farm's
        # spare labour) -- but the animals already bought are on the board regardless, and the
        # old single gate blinded the planner to all of them: no feed, no dose collect, no
        # harvest on any gate-fail day, which starved a live herd because the NEXT animal was
        # not worth it. `ranks` above keeps the incumbent's own evaluation for the values below.
        best_r, best_prog = ranks.get(best, (best_r, best_prog))
        rank_ok = best_prog is not None and best_r > elite_margin

        held = shed.get(best, 0)
        # -- elite_counter_v1 P0-3: the herd is a PORTFOLIO, not one species. The dossier's
        # day-0 script is COW+SHEEP (milk engine + wool lane), and the rank table already
        # prices each species through its own product's shop-keyed curve -- so the species
        # mix falls out of ranking each species' MARGINAL next animal rather than one global
        # winner. Per-species ordered guards keep the t2 bundle (COW + SHEEPx3) legal, and
        # the per-species `ordered` guard in `_market_orders` keeps each day's buys to one
        # order per species. The envelope (herd_cow/herd_sheep/herd_goose) is a search
        # space, not a quota: expansion stops when the marginal rank is not worth it.
        per_species_want = None
        if self.p["elite_script"]:
            env = {"COW": self.p["herd_cow"], "SHEEP": self.p["herd_sheep"],
                   "GOOSE": self.p["herd_goose"]}
            counts, incumbent_by_species = {"COW": 0, "SHEEP": 0, "GOOSE": 0}, {}
            for y2 in range(BOARD_SIZE):
                for x2 in range(BOARD_SIZE):
                    if quadrant_of(x2, y2) not in unlocked:
                        continue
                    t3 = tiles[y2][x2]
                    if isinstance(t3, dict) and t3.get("kind") in ("COOP", "PASTURE") \
                            and t3.get("animal"):
                        counts[t3["animal"]] = counts.get(t3["animal"], 0) + 1
            for sp, n in (shed or {}).items():
                if sp in counts:
                    counts[sp] = counts.get(sp, 0) + n
            # Marginal portfolio: pick the species whose NEXT animal ranks highest, but only
            # up to its envelope. The incumbent lock (below) still governs STRUCTURE choice
            # for the single-species `best`; the portfolio only adds species.
            sp_best, sp_r = None, elite_margin
            for sp in ("COW", "SHEEP", "GOOSE"):
                if counts.get(sp, 0) >= env.get(sp, 0):
                    continue
                r, prog = ranks.get(sp, (0.0, None))
                if prog is not None and r > sp_r:
                    sp_best, sp_r = sp, r
            if sp_best is not None:
                # The portfolio's species becomes the plan's species for TODAY's buy/build:
                # `best` still names the incumbent's standing herd (feeds/care/harvest are
                # species-specific and already counted per tile), but the next BUY is
                # sp_best, priced by its own rank. The want override happens below, after
                # the opening_led/ramp branch has set the single-species baseline.
                best = sp_best
                best_r, best_prog = ranks[sp_best]
                rank_ok = best_prog is not None and best_r > elite_margin
                held = shed.get(best, 0)
                per_species_want = (sp_best, env[sp_best] - counts.get(sp_best, 0),
                                    sum(env.values()))
        if self.p["opening_led"]:
            # Dossier herd target, uniform. The SHOP KEYING lives in `animal_rank`: it prices
            # each species' product against the unlocked shop schedule, so a YARN_STORE draw
            # ranks sheep first and a pizza/ice/smoothie draw ranks cows first -- the rank
            # chooses the species instead of a hard key, which keeps the two known bad
            # placements (wool into a no-yarn season, milk into a milk-flooded season) out
            # by pricing rather than by table. 12 is the dossier's lower band; the upper
            # band is the panel's job to price.
            want = self.p["led_herd_target"]
        else:
            want = _ramped_target(self.p["n_animals"], day, self.p)
        # Portfolio override (P0-3, after the single-species baseline is set): the envelope
        # total becomes the season target, but never below what the standing herd already
        # needs so a mixed herd is never starved of builds by a smaller uniform number.
        if per_species_want is not None:
            sp, sp_left, env_total = per_species_want
            live_sp = max(0, counts.get(sp, 0) - shed.get(sp, 0))
            want = max(env_total, live_sp + shed.get(sp, 0))
        # The routine-feed premium is priced off the animal's mean daily product value, so the
        # feed job bids at what a missed day actually risks (goose ~$90, cow ~$45, sheep ~$30
        # at base) rather than at the wheat alone. Computed from the season programme, not
        # spot prices, so a glut day does not starve the herd's insurance.
        bp = best_prog if best_prog else animal_programme(best, day)
        daily_product = ((bp["units"] * prices.get(ANIMAL_PRODUCT[best], _base(ANIMAL_PRODUCT[best]))
                          / max(1, SEASON_DAYS - day)) if bp else 0.0)
        # Build only while a placed animal would still reach its first yield -- past that a
        # structure is a tile spent on nothing. Building itself is free, so it is not gated on
        # cash; buying is, and one a day keeps the animals from crowding out day-0 seed, which
        # is the only compounding purchase the farm makes.
        #
        # Buying additionally waits for the feed buffer to be in the shed: the funnel trace
        # caught the first cow arriving on a day the shed held ZERO wheat, then starving by
        # day 16 while later orders trickled in (an animal on day 0-10 eats from a shed the
        # early-season cash cannot stock -- the day-0 seed round is the only compounding
        # purchase). Livestock starts with the first big money day, when the buffer can be
        # bought in one order. `mouths > 0` keeps already-owned animals out of the gate.
        in_time_ = rank_ok and animal_programme(best, day) is not None
        # The d16 trace failure: the plan bought a cow while the incumbent sat at unfed>=1.
        # A herd expands from a stable base -- no purchase while any placed animal is one
        # missed feed from escaping.
        buffer_ok = ((not starving)
                     and (mouths_buffer(shed, best, built, live) > 0 or (live + held) > 0))
        # -- feed-coverage gate (elite_counter_v1 P1, time-indexed). A new mouth must be
        # coverable on the day it eats, not "eventually": the bucket that counts is
        # cumulative feed-days SUPPLIED by that day. Three buckets, each dated: the shed
        # (feedable now), the field (wheat crops enter on their own harvest day -- a
        # growing crop never feeds an earlier mouth), and the market backstop
        # (BUY_PRODUCT, priced to stay affordable). The gate: for every day D up to the
        # next realistic field income, cumulative demand <= cumulative supply. Without
        # the time index a growing 20-tile wheat field "covers" mouths that starve
        # waiting for it -- the exact d11-13 dry-shed failure from the funnel traces.
        feed_ok = True
        if self.p["elite_script"] and self.p["feed_backbone"]:
            mouths_now = live + held + self.p["animal_pace"]   # this dawn's pending buys
            if mouths_now > 0:
                horizon = min(SEASON_DAYS, day + 6)            # until field income lands
                demand = [0] * (horizon - day + 1)
                for dd in range(day, horizon + 1):
                    demand[dd - day] = mouths_now * (dd - day + 1)
                supply = [0] * (horizon - day + 1)
                shed_w = int(shed.get("WHEAT", 0) or 0)
                field = []
                for yy in range(BOARD_SIZE):
                    for xx in range(BOARD_SIZE):
                        if quadrant_of(xx, yy) not in unlocked:
                            continue
                        t4 = tiles[yy][xx]
                        if isinstance(t4, dict) and t4.get("kind") == "PLANT" \
                                and t4.get("crop") == "WHEAT":
                            hd = t4.get("planted_day", day) + CROP_PLAN["WHEAT"]["harvest_day"]
                            if hd <= horizon:
                                field.append(hd)
                for dd in range(day, horizon + 1):
                    got = shed_w
                    got += sum(1 for hd in field if hd <= dd) * CROP_PLAN["WHEAT"]["units"]
                    # Market backstop: what the bank could still buy at a pessimistic
                    # 1.4x base (the curve rises as we buy), capped by the 10-slot
                    # reality that a 20-unit order is one slot.
                    px_w = prices.get("WHEAT", _base("WHEAT"))
                    got += int(max(0.0, money * 0.5) // (px_w * 1.4))
                    supply[dd - day] = got
                feed_ok = all(supply[i] >= demand[i] for i in range(len(demand)))
        # -- shepherd stream (scope v4): price the chores like any other job stream, then
        # make herd GROWTH conditional on the stream actually fitting the roster. The
        # already-live herd is served regardless (its rescue path survives in _replan);
        # what the gate refuses is buying animals the loops cannot keep fed -- the exact
        # failure that escaped 7/7 animals in the A/B/C run with the buffer in the shed.
        loops, budget = [], 0
        n_buy_cap = self.p["animal_pace"]   # shepherd-off default: no stream, no cap
        if self.p["shepherd_mode"] and live > 0:
            live_structs = []
            for yy in range(BOARD_SIZE):
                for xx in range(BOARD_SIZE):
                    if quadrant_of(xx, yy) not in unlocked:
                        continue
                    t2 = tiles[yy][xx]
                    if isinstance(t2, dict) and t2.get("kind") in ("COOP", "PASTURE") \
                            and t2.get("animal"):
                        live_structs.append(((xx, yy), t2))
            loops, budget = [], 0
            # Unit count is a WORKLOAD decision: take the smallest share whose planned
            # loops fit the stream's own days (raw turns -- a visit is an op plus its walk,
            # ~2 turns). One shepherd cannot serve 4 animals (30-turn loop > 20-turn day).
            per_unit = 2 * capacity(3.0 + 1.5 * max(0, len(unlocked) - 1)) - 4
            # The -4 prices what the loop builder cannot see: the unit's dawn position to
            # its shed head (shepherds spawn on the access tiles but finish yesterday
            # wherever the loop ended), plus scheduling slack. Without it the cap admits
            # loops whose real execution overruns the day and cuts feeds -- the 1-3
            # residual escapes in the funnels.
            # elite_script (P1): the gate becomes EXACT -- per-loop costs must EACH fit
            # one unit's day, not just the average. Under a care budget the loop tail is a
            # CARE, so an average-fitting overload cuts cares first and silently halves
            # the herd's yield multiplier.
            svc_margin = self.p["service_margin"] if self.p["elite_script"] else 0
            for n_sh in range(1, self.p["shepherd_share"] + 1):
                l_try, b_try, c_try = shepherd_loops(
                    live_structs, day, unlocked, n_units=n_sh,
                    bag_cap=self.p["shepherd_bag"], care=self.p["animal_care"],
                    balance=self.p["elite_script"])
                # The latest attempt is ALWAYS kept: the plan's budget feeds diagnostics
                # and the live herd is served even on an overloaded dawn (the old
                # `or n_sh == share` semantics -- losing it blanked the budget to 0).
                loops, budget = l_try, b_try
                if (b_try <= n_sh * per_unit
                        and (max(c_try, default=0) <= per_unit + svc_margin
                             or n_sh == self.p["shepherd_share"])):
                    break
            # Co-feasibility, NON-STICKY: n_buy is capped when even a full-share stream
            # cannot fit the projected herd's chores in its units' days. No memory -- the
            # earlier `want=live` freeze was sticky: one overloaded dawn froze the ramp
            # permanently even after wages freed capacity and buffer_ok re-opened (the
            # buys=2 stall in the shepherd8 funnel). When the load test passes again the
            # next dawn, buys resume; the live herd is served unconditionally.
            _, b_full, c_full = shepherd_loops(
                live_structs, day, unlocked, n_units=self.p["shepherd_share"],
                bag_cap=self.p["shepherd_bag"], care=self.p["animal_care"],
                balance=self.p["elite_script"])
            full_ok = b_full <= self.p["shepherd_share"] * per_unit
            if self.p["elite_script"] and full_ok:
                full_ok = max(c_full, default=0) <= per_unit + svc_margin
            n_buy_cap = 0 if not full_ok else self.p["animal_pace"]
        # Backlog gate (hardening #3): animals in the shed are mouths that eat but produce
        # nothing until PLACEd. Past a small backlog, new buys only deepen the pile --
        # placement is gated by shepherd loops and structure builds, not by cash.
        backlog = sum(int(shed.get(sp, 0) or 0) for sp in ANIMALS)
        if self.p["elite_script"] and backlog > self.p["backlog_cap"]:
            n_buy_cap = 0
        # Bound first: n_build's pending-mouths test reads the same value, and dict
        # literals evaluate keys in order -- referencing `n_buy` from n_build's value
        # raised NameError (the buy entry below is not yet bound at that point).
        n_buy_val = (max(0, min(self.p["animal_pace"], n_buy_cap, want - live - held))
                     if (in_time_ and buffer_ok and feed_ok
                         and money > self.p["animal_pace"]
                         * OBJECT_TABLE[best]["buy_cost"] * 2) else 0)
        return dict(animal=best, struct=ANIMAL_STRUCTURE[best], rank=best_r,
                    worth=best_r * (best_prog["visits"] if best_prog else 40),
                    fert_px=fert_px, wheat_px=wheat_px, held=held, live=live, built=built,
                    daily_product=daily_product, loops=loops, budget=budget,
                    held_by_species={sp: int(shed.get(sp, 0) or 0) for sp in ANIMALS
                                     if shed.get(sp, 0)},
                    # Elite build gate: a structure is only raised when a mouth is waiting
                    # (held) or arriving (n_buy) to fill it -- the s10 build-ahead rule
                    # raised 9 empty structures by d15 (13 built / 4 filled) because n_build
                    # ran off the season target, not off pending placements. Baseline keeps
                    # the original build-ahead form byte-identical.
                    n_build=(min(self.p["animal_pace"], want - built)
                             if (in_time_ and not self.p["elite_script"])
                             else (min(self.p["animal_pace"],
                                       max(0, min(held + n_buy_val, want - built)))
                                   if (in_time_ and held + n_buy_val > 0) else 0)),
                    n_buy=n_buy_val)


    def _spawn_guess(self, n, units):
        """Where the engine will put `n` new hands: on the shed-access tiles themselves.

        The engine's `_spawn_hand` spawns each hand on the first *least-occupied* of the four
        shed-access tiles (4,4), (5,4), (4,5), (5,5) -- the tiles that accept a DROP -- with
        ties broken in NWSE order, counting the farmer and the already-spawned hands as
        occupants. The previous guess here predicted an N/W/S/E *ring* around the shed, a set
        that does not even contain (4,4): harmless at hour 0 (the hour-1 re-cut re-partitions
        against the real positions) but wrong, and this file's whole discipline is to mirror
        the engine's spawn exactly so a probe reading `predicted` never argues with a trace.
        """
        order = [(4, 4), (5, 4), (4, 5), (5, 5)]   # _shed_access_tiles, NWSE order
        occ = {p for _, p in units}
        out = []
        for i in range(n):
            counts = [sum(1 for q in list(occ) + out if q == c) for c in order]
            best = min(counts)
            out.append(next(c for c, k in zip(order, counts) if k == best))
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
        # opening_led roster floor: the winners hire ~10/day from day 0 and never idle the
        # roster, while our demand-sized roster hires 0-4 on d1-9 (ledger: the d1-9 labour
        # trough, ~30-40 orders of early capacity wasted). The Fibonacci cash cap below
        # still applies -- the floor is a floor on INTENT, not on spend.
        if self.p["opening_led"]:
            n = max(n, min(self.p["led_roster_floor"], self.p["max_hands"]))
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
        if self.p["plan_ms"] > 0 and (time.monotonic() - t0) * 1000.0 > self.p["plan_ms"]:
            return
        ranked = collect_jobs(tiles, unlocked, day, prices, self.want, avail, self.p,
                              fert_stock=self.fert_have, animals=self.animals)
        # Animal feed chains never enter the value lottery. The traced failure (feed_trace.py,
        # seed 0): the routine feed (~$246 at GROW) loses the `ranked[:n]` / serpentine
        # coin-flip every other day, the engine kills at two consecutive misses, and the RESCUE
        # tier can lose too -- on d16 the due feed dropped while the plan bought a replacement
        # cow for the animal it was starving. Feeding is a chore, not a bid: pull the chains out
        # of `ranked` and prepend each to the unit nearest its animal, so the chain executes in
        # the first turns of the day -- which also keeps it clear of the midnight wipe that
        # strands an h20 PICKUP's carried tail (the d19 failure in the same trace).
        feed_chains = [j for j in ranked
                       if j["op"][0] == "PICKUP" and (j.get("then") or [None])[0] == "FEED"]
        if feed_chains:
            ranked = [j for j in ranked
                      if not (j["op"][0] == "PICKUP" and (j.get("then") or [None])[0] == "FEED")]
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
            if self.p["plan_ms"] > 0 and (time.monotonic() - t0) * 1000.0 > self.p["plan_ms"]:
                break
        # Shepherd assignment (scope v4): the dedicated chore units come OUT of the
        # serpentine pool -- their loops are multi-step objects that must not be cut by
        # the value lottery (that lottery is exactly how the 20-herd starved). Shepherds
        # are the units already nearest the shed; everyone else shares what remains.
        shepherds = set()
        if self.p["shepherd_mode"] and self.animals and self.animals.get("loops"):
            loops = self.animals["loops"]
            sheds_open = [pp for q, pp in SHED_TILES.items() if q in unlocked] \
                or [SHED_TILES["NW"]]
            shepherds = {i for i, _ in sorted(
                units, key=lambda u: min(manhattan(u[1], p) for p in sheds_open)
            )[:len(loops)]}
            by_pos = {i: p for i, p in units}
            for si, loop in zip(sorted(shepherds), loops):
                start = by_pos.get(si)
                if start is not None:
                    loop[0]["pos"] = start if loop[0]["op"][0] != "PICKUP" else loop[0]["pos"]
                self.queues = self.queues or {}
                self.queues[si] = [dict(j, carried=j.get("carried", j["op"][0] != "PICKUP"))
                                   for j in loop]
        # The serpentine pool excludes the shepherds; if none remain the day is livestock.
        serp_units = [(i, p) for i, p in units if i not in shepherds] or units
        if shepherds and self.animals:
            # Runs were cut for the full roster; re-cut for the reduced pool.
            runs = split_runs(take, serp_units, turns_left, deliver_reserve=reserve)
            self.queues.update({i: list(r) for i, r in runs.items() if i not in shepherds})
        else:
            self.queues = {i: list(r) for i, r in runs.items()}
        # Prepend the feed chores after the runs are cut: the chore displaces the
        # geometrically-last crop job of one unit, which is exactly the right thing to displace,
        # and running first is what makes the chain immune to both the value cut and midnight.
        # (Skipped while the shepherd stream runs: its loops already own every feed.)
        if feed_chains and not (self.p["shepherd_mode"] and self.animals
                                and self.animals.get("loops")):
            pos_of = {i: p for i, p in units}
            for fj in feed_chains:
                tx, ty = fj.get("then_pos") or fj["pos"]
                uid = min(pos_of, key=lambda i: abs(pos_of[i][0] - tx) + abs(pos_of[i][1] - ty))
                runs.setdefault(uid, [])
                runs[uid].insert(0, dict(fj))
                pos_of[uid] = (tx, ty)
            self.queues = {i: list(r) for i, r in runs.items()}

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
            # The animal / grain / dose is bought or sits in the shed; a market order settles
            # at the end of the turn, so a PICKUP whose goods have not landed is early rather
            # than invalid -- same shape as a PLANT waiting on seed, handled the same way in
            # `_unit_ops`. The check spends `stock_key`, not `op[1]`: a feed pickup of one
            # WHEAT draws the shared grain counter (_FEED), never a planting sack.
            return (stock is None or stock.get(job.get("stock_key", job["op"][1]), 0) > 0
                    or hour <= self.p["seed_grace"])
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
                # A carried tail (the FEED leg of a shed-pickup chain) holds its wheat in the
                # bag -- the shed counter was already spent by the PICKUP leg, so re-checking
                # it here would drop the job mid-chain and strand the grain.
                return not tile.get("fed_today") and (stock is None or job.get("carried")
                                                      or stock.get(_FEED, 0) > 0)
            if op == "CARE":
                return not tile.get("cared_today")
            return tile.get("yield_units", 0) > 0
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return False
        if op == "FERTILIZE":
            # A dose already on the tile is not topped up, it is wasted: FERTILIZE overwrites
            # `fertilized_until_day` rather than extending it, and the old dose still had
            # nights left. The shed-stock check is skipped for a carried tail -- the dose is
            # in the bag; the PICKUP leg already spent the counter.
            return (tile.get("fertilized_until_day", -1) < day
                    and (stock is None or job.get("carried")
                         or stock.get("FERTILIZER", 0) > 0))
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

    def _book_serve(self, obs, day, hour, n_units):
        """Replay the donor's moves for this turn; planner takeover if the book is short.

        Mirrors `main.agent`'s never-raise contract: a malformed entry degrades to a safe
        PASS, it never forfeits an episode.
        """
        try:
            vi = self._book_variant.get(day)
            variant = (self._book or {}).get(day, [])[vi] if vi is not None else None
            entry = variant["hours"][hour]
            farmer = list(entry[0] or ["PASS"])
            hands = [list(h) for h in entry[1]]
            market = [list(m) for m in entry[2]]
        except Exception:
            return None
        # Ladder evidence (110850828): the donor's 23-melon cohort ripens in one synchronized
        # wave and the always-sell branch named 714 units at $26 in a single turn against the
        # opponent's realized $148. An 8-seed cohort still lands in one BUY_SEED order (same
        # slot count) but staggers the harvest; the planting plan fills the rest of day 0 with
        # the planner's own mix. The melon wave logic re-enters on later days only above the
        # price floor, so nothing here forecloses a second cohort.
        market = [list(m) for m in entry[2]]
        mo = self.p.get("melon_opening", 0)
        if mo and day == 0:
            for m in market:
                if (len(m) > 2 and m[0] == "BUY_SEED" and m[1] == "MELON"
                        and isinstance(m[2], int)):
                    m[2] = min(m[2], mo)
        while len(hands) < n_units - 1:
            hands.append(["PASS"])
        del hands[max(0, n_units - 1):]      # hands list EXCLUDES the farmer: n_units - 1 entries
        # Market orders go straight back to the engine verbatim; the donor's own cap
        # arithmetic applies because the moves ARE the donor's.
        return {"farmer": farmer, "hands": hands, "market": market}

    def _steal_job(self, me_idx, pos, tiles, day, stock, hour):
        """The nearest feasible job from another unit's queue tail, or None.

        A unit whose run finished early PASSes until midnight while other runs still hold
        tail jobs it could reach faster than their owners -- idle_frac runs 10-11% over a
        season, and the tail of a serpentine run is precisely the work its owner reaches
        last. The tail-only rule means the owner loses at most their final job and never
        their current head, so a steal cannot cascade into a replan; and the stale-job case
        (the owner got there first) is already handled by `_valid`, which drops it -- the
        next idle unit steals again. Self-healing.

        Ties on distance broken by the owner's remaining queue length (a shorter queue is
        less likely to reach its tail today), then by value -- do not steal the wheat when
        a melon rescue is equally close. PLANT jobs must pass the seed-stock check too:
        stealing a seedless PLANT just converts one idle turn into another.
        """
        px, py = pos
        best = None
        best_key = None
        for i, q in self.queues.items():
            if i == me_idx or len(q) < 2:
                continue
            # Tail always; the second-from-tail too, but only on a queue of 3+ (on a
            # 2-queue the second-from-tail IS the head, and the head is never stolen).
            for k in ((len(q) - 1,) if len(q) == 2 else (len(q) - 1, len(q) - 2)):
                j = q[k]
                if j.get("then") or j.get("carried") or j.get("stock_key"):
                    # never split a PLANT from its same-day WATER, and never steal a leg of a
                    # shed-pickup chain: the head unit may already be carrying the goods, and
                    # the tail is worthless (or a stranded bag) in anyone else's hands.
                    continue
                op, crop = j["op"][0], (j["op"][1] if len(j["op"]) > 1 else None)
                if op == "PLANT" and stock is not None and stock.get(crop, 0) <= 0:
                    continue
                x, y = j["pos"]
                dist = abs(px - x) + abs(py - y)
                key = (dist, len(q) - 1 - k, -j.get("value", 0.0))
                if best_key is None or key < best_key:
                    if not self._valid(j, tiles, day, stock, hour):
                        continue
                    best_key = key
                    best = j
        return best

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
                        and stock.get(q[0].get("stock_key", q[0]["op"][1]), 0) <= 0
                        and len(q) > 1):
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
                    and q[0]["op"][0] != "DROP"
                    and not (q[0].get("carried") or q[0].get("stock_key"))):
                q.insert(0, dict(pos=nearest_shed(pos, unlocked), op=["DROP"],
                                 tier=0, value=0.0))
            if not q:
                if carrying:
                    # Nothing left to do and a full pack: bank it. On normal days midnight
                    # would dump it anyway, but a load in the shed can be SOLD today, and
                    # today's price is the only one this load is guaranteed to see.
                    q.append(dict(pos=nearest_shed(pos, unlocked), op=["DROP"],
                                  tier=0, value=0.0))
                elif self.p.get("work_steal") and hour < TURNS_PER_DAY - 2:
                    # Queue drained while other runs still have work: take the nearest
                    # feasible TAIL job off another unit's queue. The tail is the job its
                    # owner reaches last, so a fresh unit walking straight there almost
                    # always beats them to it, and the owner never loses their current
                    # head. If the owner wins the race anyway, the normal `_valid` check
                    # drops the stale job and this unit steals again -- self-healing.
                    stolen = self._steal_job(idx, pos, tiles, day, stock, hour)
                    if stolen is not None:
                        q.append(stolen)
                    else:
                        ops.append(["PASS"])
                        continue
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
                if hour >= TURNS_PER_DAY - 1:
                    # PLANT at hour 23 cannot get its paired WATER before the midnight
                    # refresh (consecutive_unwatered 1 -> 2 = weed), and hour 0's replan
                    # schedules the tile fresh anyway. Spend the turn instead of
                    # killing the seed.
                    ops.append(["PASS"])
                    continue
                if stock.get(crop, 0) <= 0:
                    # Standing on the tile with the seed still in flight -- the purchase for
                    # it settles at the end of this turn. Wait one turn rather than dropping
                    # the job; this only happens at hour 0, and only on day 0 in practice.
                    ops.append(["PASS"])
                    continue
                stock[crop] -= 1
            elif job["op"][0] == "PICKUP":
                # Same story as a seed: the BUY_ANIMAL settles at the end of the turn. The
                # counter is `stock_key` -- a WHEAT pickup for a feed chain draws the shared
                # grain bag (_FEED), not a planting sack.
                skey = job.get("stock_key", job["op"][1])
                if stock.get(skey, 0) <= 0:
                    ops.append(["PASS"])
                    continue
                stock[skey] -= 1
            elif job["op"][0] == "FEED":
                if not job.get("carried"):
                    stock[_FEED] = stock.get(_FEED, 0) - 1
            elif job["op"][0] == "FERTILIZE":
                if not job.get("carried"):
                    stock["FERTILIZER"] = stock.get("FERTILIZER", 0) - 1
            ops.append(list(job["op"]))
            if job.get("then"):
                # Multi-op job: run the next op next turn, on this tile unless the job names
                # another. Used for the WATER that has to follow a PLANT on the same day, and for
                # the PICKUP at the shed that has to be followed by a PLACE / FEED / FERTILIZE.
                # `carried` tells the tail (and `_valid`) that its input is now in the bag: the
                # shed counter was spent by the PICKUP leg, so the tail must neither re-check
                # nor re-decrement it.
                q[0] = dict(job, op=job["then"], then=None, acts=1, carried=True,
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

    @staticmethod
    def _placed_counts(me):
        """Animals actually PLACED on the board, per species, from the farm observation.

        The settlement half of the elite opening FSM (P0-4): `self.ordered` only proves an
        order was EMITTED -- an order can fail for cash or shed room, and a flag-guarded
        script would then never retry. Counting observed placements (plus the shed, at the
        call site) makes the script's stages self-correcting: a failed purchase is simply
        attempted again next turn.
        """
        counts = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
        tiles = me.get("tiles") or []
        for row in tiles:
            for tile in (row or []):
                if isinstance(tile, dict) and tile.get("animal") in counts:
                    counts[tile["animal"]] += 1
        return counts

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

        # opening_led day-0 script: animals before seeds. Emitted into `d0` so the seed and
        # hire sizing below sees the REDUCED bank -- the day-0 seed round stays the only
        # compounding purchase, but the herd is the first compounding ASSET (dossier:
        # every elite game opens BUY_ANIMAL COW + grain on turn 1, before any seed).
        d0 = []
        # The FSM window is d0-d1: a slot-capped turn (10 orders max) spills the bundle's
        # tail into the next turn, and `day == 0` alone cut the third sheep off forever
        # (t1 emitted 1 of 2 sheep, then the gate closed at dawn 1 -- mirror seed 0).
        if self.p["opening_led"] and day <= 1:
            # Settlement-based guards (elite_script P0-4): count OBSERVED purchases
            # (placed + in-shed) so a failed or partial order retries next turn instead
            # of being swallowed by a flag. The umbrella `animal` key still blocks the
            # main slot WITHIN a turn -- an unguarded day-0 script re-fires for all 24
            # hours; measured before any guard, it bought 7 cows on day 0 alone and
            # ended the episode at $937.
            placed = self._placed_counts(me)
            have = dict(placed)
            for sp in ("COW", "SHEEP", "GOOSE"):
                have[sp] = have.get(sp, 0) + int(shed.get(sp, 0) or 0)
            # Only PLACED mouths eat from the shed today -- a bought animal's first FEED
            # day is its PLACEMENT day (the PICKUP->PLACE chain takes 1-3 days). Sizing
            # the bridge off have (placed+shed) bought 28 grain for 5 animals still in
            # the shed: $500 of dead working capital, and the dossier's d0 residual
            # after the script is ~$300-500 of seed money, not $108.
            placed_mouths = sum(placed.values())
            cow_cost = OBJECT_TABLE["COW"]["buy_cost"]
            sheep_cost = OBJECT_TABLE["SHEEP"]["buy_cost"]
            px_w = prices.get("WHEAT", _base("WHEAT"))
            grain = int(shed.get("WHEAT", 0) or 0)
            mouths = sum(have.values())
            bridge = self.p["feed_bridge"]
            # Per-turn bundle cap (the smoke-caught slot failure): the whole script is
            # ~9 orders; crammed into ONE turn it exceeds MAX_MARKET_ORDERS=10, the tail
            # (the HIREs) is silently dropped, and the roster never spawns. The dossier
            # spreads the same bundle over t1-t4 anyway. The settlement FSM delivers the
            # remainder over the next turns -- that is what "settlement-based" buys.
            n_animals_turn = 0

            def _top_grain(target):
                # Emitted grain orders SETTLE IN LIST ORDER with the animal buys, so a
                # top-up placed before the next animal buy is in the shed by the time
                # that mouth's first FEED day arrives. NO per-day guard here: within a
                # turn the `grain` closure counts what was already emitted, and across
                # turns `shed.get("WHEAT")` is the settlement truth -- a top-up that
                # settled cannot re-fire. (The old `ordered["wheat"]` guard BLOCKED the
                # bundle: set at t0, it vetoed every later same-day top-up, stage 2
                # starved on its own coverage gate, and the herd stayed a lone cow.)
                nonlocal grain, money
                if grain < target:
                    n = min(target - grain, int(money // px_w))
                    if n > 0:
                        d0.append(["BUY_PRODUCT", "WHEAT", n])
                        money -= n * px_w
                        grain += n

            # Stage 1, the dossier's t1: the founding cow, then its grain, same turn.
            if have.get("COW", 0) < self.p["led_cow0"] and money >= cow_cost \
                    and n_animals_turn < 2:
                d0.append(["BUY_ANIMAL", "COW", 1])
                money -= cow_cost
                self.ordered["animal"] = 1   # umbrella: blocks the main slot, not the script
                have["COW"] = have.get("COW", 0) + 1
                mouths += 1
                n_animals_turn += 1
                _top_grain(max(self.p["led_wheat0"], bridge * max(1, placed_mouths)))
            if self.p["elite_script"]:
                # Stage 2 (the elite t2 bundle): the second cow plus the sheep wool lane.
                # EVERY mouth is gated on the shed covering `bridge` days of feed for the
                # herd it joins -- the smoke-caught failure mode: capital all spent on
                # animals, shed dry at d3, five animals burn their escape clocks and the
                # whole d0 script is a $2.4k write-off. A mouth that cannot be fed is
                # not a purchase, it is a loss.
                if have.get("COW", 0) >= min(1, self.p["led_cow0"]) \
                        and have.get("COW", 0) < self.p["led_cow0"] + self.p["led_cow2"] \
                        and money >= cow_cost and n_animals_turn < 2:
                    _top_grain(bridge * max(1, placed_mouths))
                    if grain >= bridge * max(1, placed_mouths):
                        d0.append(["BUY_ANIMAL", "COW", 1])
                        money -= cow_cost
                        self.ordered["animal"] = 1
                        have["COW"] += 1
                        mouths += 1
                        n_animals_turn += 1
                        _top_grain(bridge * max(1, placed_mouths))
                while have.get("SHEEP", 0) < self.p["led_sheep0"] \
                        and have.get("COW", 0) >= 1 \
                        and n_animals_turn < 2:      # per-turn bundle cap (see below)
                    _top_grain(bridge * max(1, placed_mouths))
                    if grain < bridge * max(1, placed_mouths) or money < sheep_cost:
                        break
                    d0.append(["BUY_ANIMAL", "SHEEP", 1])
                    money -= sheep_cost
                    self.ordered["animal"] = 1
                    have["SHEEP"] = have.get("SHEEP", 0) + 1
                    mouths += 1
                    n_animals_turn += 1
                    _top_grain(bridge * max(1, placed_mouths))

        # -- elite capital reservation (the smoke-caught failure). The script's UNSETTLED
        # remainder is invisible to the seed sizing below: t0 emitted cow+grain, the seed
        # round then spent the rest of the $3k on melons+fertilizer, stage 2 never had its
        # ~$1,900, the shed dried after two feeds and the first cow escaped (mirror seed 0:
        # placed d2, gone by d6). The seed budget must be net of the whole script, not of
        # the part that happens to fire this turn.
        # DOUBLE-COUNT GUARD (second smoke finding): `money` above is already net of the
        # orders the d0 block EMITTED this turn, so the reserve must cover only the
        # remainder that is unsettled AND NOT EMITTED HERE -- otherwise t0's seed budget
        # goes to zero (reserve = whole bank again) and the farm plants nothing.
        elite_reserve = 0.0
        if self.p["elite_script"] and day <= 1:
            have0 = self._placed_counts(me)
            for sp in ("COW", "SHEEP", "GOOSE"):
                have0[sp] = have0.get(sp, 0) + int(shed.get(sp, 0) or 0)
            emitted_cow = sum(1 for o in d0 if o[0] == "BUY_ANIMAL" and o[1] == "COW")
            emitted_sheep = sum(1 for o in d0 if o[0] == "BUY_ANIMAL" and o[1] == "SHEEP")
            emitted_wheat = sum(o[2] for o in d0 if o[:2] == ["BUY_PRODUCT", "WHEAT"])
            owe = (max(0, self.p["led_cow0"] + self.p["led_cow2"]
                       - have0.get("COW", 0) - emitted_cow)
                   * OBJECT_TABLE["COW"]["buy_cost"]
                   + max(0, self.p["led_sheep0"] - have0.get("SHEEP", 0) - emitted_sheep)
                   * OBJECT_TABLE["SHEEP"]["buy_cost"])
            owe += max(0, self.p["led_wheat0"] - int(shed.get("WHEAT", 0) or 0)
                       - emitted_wheat) * prices.get("WHEAT", _base("WHEAT"))
            elite_reserve = min(owe, max(0.0, money))
        # Plus the feed bridge: grain to cover every owned-or-scripted mouth until field
        # wheat lands (~d4 at the earliest; 6 days is safe). Without this the script's
        # animals starve on a technically "settled" script.
        if self.p["elite_script"] and day <= 1:
            # Placed mouths only (see the script block): shed animals do not eat yet.
            mouths_now = max(1, sum(self._placed_counts(me).values()))
            owe_bridge = max(0, mouths_now * self.p["feed_bridge"]
                             - int(shed.get("WHEAT", 0) or 0)) \
                * prices.get("WHEAT", _base("WHEAT"))
            elite_reserve = min(max(elite_reserve, owe_bridge), max(0.0, money))

        # Sized before hiring so they cannot be crowded out of the slot budget. Under the
        # elite script the day-0/1 seed budget is net of the UNSETTLED script remainder
        # (the smoke-caught failure: the seed round spent what stage 2 needed).
        # Opening wage reserve: the standard `wage_reserve` prices a FULL roster, but a
        # day-0 elite opening has no roster yet -- a full-roster reserve at $108 cash
        # zeroed the seed budget and the farm planted nothing all week (the deadlock:
        # no seeds -> no jobs -> no roster -> no income). In the opening window the
        # reserve prices the 4-6 hires the opening actually needs.
        opening_wage_reserve = self.wage_reserve
        if self.p["elite_script"] and day <= 1:
            opening_wage_reserve = sum(fib_hire_cost(i) for i in range(6))
        # While the script OWES animals, it outranks every seed: the herd is the asset
        # the whole season compounds on, and a melon bought on d0 instead of the third
        # sheep delays the wool lane's first pop by a week (wool is the win-separator).
        # Hires are NOT suppressed -- the roster is what serves the herd that arrives.
        # The seed floor: the field is the season's income engine and it must open
        # WITH the herd, not after the last sheep settles (elite smoke seed 0: the
        # raw netting zeroed the budget for ten straight days -- $1-27 cash d4-10,
        # zero income until d13, a cow lost at d14). The floor spends down to $300
        # on seeds inside the script window; the settlement FSM re-fires stage 2
        # the moment the d6 wool wave refills the bank. Outside the window the
        # budget is the standard net-of-wages form.
        if elite_reserve > 0:
            seed_budget = min(money - opening_wage_reserve,
                              max(money - opening_wage_reserve - elite_reserve,
                                  self.p["seed_floor"]))
        else:
            seed_budget = money - opening_wage_reserve
        seed = self._seed_orders(seeds, prices, max(0.0, seed_budget),
                                 self.p["seed_slots"])
        seed_cost = sum(o[2] * OBJECT_TABLE[o[1]]["seed_cost"] for o in seed)
        sell = self._sell_orders(shed, minv, prices, (obs.get("private") or {}).get("inventories"),
                                 day, unlocked=unlocked)

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

        out = d0 + seed + hire
        money -= seed_cost + sum(fib_hire_cost(me.get("hires_today", 0) + i)
                                 for i in range(len(hire)))

        # Fertilizer, one slot with a quantity. Ahead of land because a dose is the best-value
        # visit measured on the board -- +2 melon units for one visit and ~$100 -- while a
        # quadrant only pays if there is seed and labour spare to work it. Suspended while the
        # shed is crowded: a dose bought into a shed at 100 items displaces a strawberry worth
        # $110 that the engine then discards without a word.
        n_fert = self._fert_buy(shed, money, day) if not self.crowded else 0
        # Capital hierarchy (elite): animal setup > feed > roster > crops > fertilizer/land.
        # While the d0 script is unsettled, a dose or a quadrant spends what stage 2 (or
        # the herd's first feeds) need -- mirror seed 0: fert $800 + land $1,000 left the
        # shed dry at d4 and both cows escaped by d6.
        if self.p["elite_script"] and day <= 1 and elite_reserve > 0:
            n_fert = 0
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
        if a and a["n_buy"] > 0:
            # ONE order per SPECIES per day (the day cap is the point: the dawn plan is
            # recomputed once, `_market_orders` runs every turn, and an order sized from
            # a dawn snapshot would be re-issued for all 24 hours -- measured on seed 0
            # before the guard went in, that bought 24 cows on day 13 and took the bank
            # from $87k to $14k). Keyed per species now: the elite portfolio buys COW
            # and SHEEP the same day without re-arming each other's refire guard.
            sp = a["animal"]
            if sp not in self.ordered and money >= OBJECT_TABLE[sp]["buy_cost"]:
                out.append(["BUY_ANIMAL", sp, 1])
                money -= OBJECT_TABLE[sp]["buy_cost"]
                self.ordered[sp] = 1
        # Feed of last resort. WHEAT is one of the two goods the engine will sell back, and an
        # animal two days unfed is gone for good along with the rest of its season, so a farm
        # whose own wheat has run down buys the grain rather than lose the asset. Sized against
        # animals owned *or on order*, because the grain has to be in the shed on the day the
        # PLACE lands: measured on the first build, which sized this off `live` alone, the shed
        # held zero wheat for the whole early season and two to five animals starved.
        # mouths includes n_build: the supply must precede the BUILD, not just the mouth.
        # Sized off live+held+n_buy alone the chain deadlocked on the real tier -- the dawn
        # plan gated n_buy on a shed buffer that only fills when mouths>0, so the pasture
        # built (day 11), the shed stayed dry, and no cow was ever ordered (funnel trace,
        # real tier seed 0: buys=0 all season, two empty pastures). A pasture under
        # construction is a mouth one day away: wheat lands the day the build starts, the
        # BUY_ANIMAL clears the buffer gate the next dawn, the PLACE lands into a stocked
        # shed.
        mouths = (a["live"] + a["held"] + a["n_buy"] + a.get("n_build", 0)) if a else 0
        # Buffer, not ration: the ladder winners hold ~100 wheat against their herds
        # (replay 110082767: 100 units bought), while our mouths*3 ration left the shed at
        # ZERO wheat on the exact days the first cow needed feeding (funnel trace, seed 0:
        # cow placed day 13, shed wheat 0 on days 11-13, escaped day 16). Six days per mouth
        # rides through the order-cap days and the price spikes without ever starving.
        need = mouths * 6 - shed.get("WHEAT", 0) if mouths else 0
        if need > 0 and "wheat" not in self.ordered and day < SEASON_DAYS - 1 \
                and money >= need * price_for("WHEAT", minv.get("WHEAT", I0)) \
                and sum(shed.values()) < SHED_CAPACITY:
            # The shed-room condition mirrors the real engine's refusal: a BUY_PRODUCT into
            # a full shed is dropped uncharged (see engine.py's mirror of `_commit_unit`).
            out.append(["BUY_PRODUCT", "WHEAT", need])
            self.ordered["wheat"] = need

        nxt = next((q for q in QUADRANT_ORDER if q not in unlocked), None)
        # Only when the allocator actually ran out of tiles, and only while a bought quadrant
        # still has time to return the money: the shortest cycle is carrot at four days, and a
        # quadrant bought after that cannot be planted into anything that finishes.
        if nxt and self.tile_limited and day + CROP_PLAN["CARROT"]["harvest_day"] < SEASON_DAYS \
                and not (self.p["elite_script"] and day <= 1 and elite_reserve > 0):
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

    def _sell_orders(self, shed, minv, prices, invs=None, day=0, unlocked=None):
        """Sell orders sized against the shed *plus* what the units are still carrying.

        contract: units settle SELL from private["shed"] ONLY (`_commit_unit` reads the shed),
        and unit actions run BEFORE _process_market — so a same-turn DROP funds a same-turn
        SELL, but units still carrying at settlement are unnameable. Sizing off shed+carried
        (the old pool) burns slots on phantom units and mis-signals what is actually
        monetized. Carried units are still worth naming as a free MARGIN on top of the
        shed-backed count: an unfunded tail unit is skipped silently, costs neither a slot
        nor a dollar (under-ordering is what costs). Measured on episode 110850828's
        day-28 tail: 23.6 strawberries stranded at step 720.

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
        # Carried units are NOT part of the sell POOL (see settlement contract above); they
        # are a free margin added per-good below. They still count toward the CROWD metrics:
        # bags bank into the shed at midnight and overflow it, so `total` (which feeds the
        # `crowded` flag and the fast valve) must stay shed+carried exactly as shipped.
        carried = {}
        for inv in (invs or []):
            for good, n in (inv or {}).items():
                carried[good] = carried.get(good, 0) + n
        endgame = day >= SEASON_DAYS - self.p["endgame_days"]
        total = sum(pool.values()) + sum(carried.values())
        crowded = total > self.p["crowded"] * SHED_CAPACITY
        # Published for `_market_orders`: a crowded shed changes the whole turn's priorities, not
        # just this list. Buying more input into a shed that is already discarding output is the
        # worst trade on the board, and the slot the purchase takes is a slot a sale needed.
        self.crowded = crowded
        hold = {}
        # A live shepherd herd eats through the final day -- its d27-29 milk is worth more
        # than the grain. Endgame liquidation of the FEED BUFFER starved a stable 9-day herd
        # at d28 (shepherd8 funnel: shed 20 -> 1 -> 0 as endgame sales drained it, escape at
        # d28 h0 with grain $15 in the pool). While the stream runs, the buffer holds like
        # mid-season; mode=0 keeps the shipped endgame behaviour byte-identical.
        herd_endgame = (self.p["shepherd_mode"] and self.animals
                        and (self.animals["live"] + self.animals["held"]) > 0)
        if self.animals and (not endgame or herd_endgame) and not crowded:
            # Grain kept back for the feed programme, counted against animals owned or on order
            # so the shed is stocked before the first PLACE rather than after the first miss.
            # Wheat is the cheapest good on the board at $25 base, so holding a dozen costs the
            # farm ~$480 of sales against a $400 animal it keeps alive -- but only while there is
            # room for it. The shed discards silently at 100 items and the goods it would discard
            # instead are strawberries at $110, so a crowded shed sells the grain and the
            # `BUY_PRODUCT WHEAT` fallback buys it back on the day it is needed.
            # n_build is in the count: the funnel trace (real tier, seed 2) caught the
            # chicken-and-egg where the buffer order bought 6 wheat every turn and the sell pass
            # sold the same 6 back the same turn -- mouths=0 held nothing, shedW sat at 0 every
            # dawn for 12 days, the buffer gate never opened, and the herd never started. The
            # pasture under construction is a mouth: the supply must survive the sell pass to
            # ever meet it.
            mouths = (self.animals["live"] + self.animals["held"] + self.animals["n_buy"]
                      + self.animals.get("n_build", 0))
            if mouths:
                hold["WHEAT"] = self.p["feed_hold"] * mouths
        # Shed animals are mouths TOO, regardless of the dawn-stale plan. The elite smoke
        # (seed 0) caught the catastrophic form: the d0 script bought 2C+3S across t0-t2,
        # the plan computed at dawn still said mouths=0, and the sell pass sold the whole
        # 28-unit feed bridge back to the town at t1-t3 -- the herd starved, escaped by d5,
        # the field never planted (no cash, no mouths to plan for), and the season ended at
        # $2.7k of liquidated fertilizer. An animal sitting in the shed will eat from that
        # shed the day it is placed; its feed may not be sold out from under it.
        shed_mouths = sum(int(shed.get(sp, 0) or 0)
                          for sp in ("COW", "SHEEP", "GOOSE"))
        if shed_mouths and (not endgame or herd_endgame) and not crowded:
            hold["WHEAT"] = max(hold.get("WHEAT", 0),
                                self.p["feed_hold"] * shed_mouths)
        # Live-herd feed is never inventory. The funnel trace (shepherd8, all seeds): the
        # herd stood stable d17-26, then the ENDGAME sell pass dumped the buffer and an
        # animal starved at d27 with $15 of grain in the shed -- exactly the working-capital
        # error. While animals stand (shepherd stream runs), one day of feed per mouth stays
        # unsellable even in endgame/crowded sheds; the rest of the buffer still clears.
        if (self.p["shepherd_mode"] and self.animals
                and (self.animals["live"] + self.animals["held"] + shed_mouths) > 0):
            hold["WHEAT"] = max(hold.get("WHEAT", 0),
                                self.animals["live"] + self.animals["held"] + shed_mouths)        # -- WOOL recovery hold (elite_counter_v1 P2). Wool's pot is tiny and its crash is
        # the deepest on the board (3.2x per glut unit): the dossier's winners hold crashed
        # wool through the trough -- up to 28 shed units d12-20 -- and sell after recovery
        # at ~$190, while the farm that dumped early sold the same wool for a fraction.
        # Held only mid-season, only under the cap (an over-cap shed sells down normally),
        # only while the price sits under the recovery floor, and never in a crowded shed
        # -- storage risk beats price recovery once midnight overflow is live. Milk never
        # holds: its scarcity window is now-or-never (drip seller unchanged).
        # WINDOW (elite smoke, seed 0): the hold is OFF through d11. Our FIRST pop is the
        # season's cheapest capital: the d6 wool wave is ~28 units x ~$80 = $2.2k, and the
        # dossier converts it to 5-6 cows SAME DAY. Holding it until d12-20 starved the
        # whole farm to $1-27 d6-10 -- no field, no reinvestment, and a cow lost at d14.
        # After d12 the trough is real (both herds saturate wool), so the hold starts.
        if (self.p["elite_script"] and day >= 12 and not endgame and not crowded):
            wool_shed = int(pool.get("WOOL", 0) or 0)
            if (0 < wool_shed < self.p["wool_hold_cap"]
                    and prices.get("WOOL", _base("WOOL")) < self.p["wool_hold_price"]):
                hold["WOOL"] = wool_shed
        out = []
        for good in sorted(set(pool) | set(carried), key=lambda g: -prices.get(g, 0)):
            if good not in MARKET_PARAMS:
                continue
            if good in _INPUTS and not endgame:
                continue
            # Shed-backed stock plus the carried margin (engine skips unfunded tail units).
            # A carried-ONLY good is still named: a same-turn DROP lands it in the shed
            # before settlement, so the order is free upside either way.
            have = pool.get(good, 0) - hold.get(good, 0) + carried.get(good, 0)
            if have <= 0:
                continue
            # Days of town drain a capped sell names. The unlocked shop list is threaded in
            # by `_market_orders` from the observation, so `drain_per_day_from_shops` is
            # exact on the ladder; an empty list falls back to town-centre-only, which
            # understates the drain -- the conservative direction for a cap.
            d = drain_per_day_from_shops(good, unlocked, day)
            if d <= 0:
                d = 1.0
            # Fast valve: shed nearly full. The held-back feed grain is excluded -- with a
            # real herd the hold alone would pin the valve open every day and cap the whole
            # farm's throughput for nothing.
            valve_total = total - sum(hold.values())
            valve = valve_total > (1.0 - self.p["crowded"]) * SHED_CAPACITY
            capn = max(1, int(round(self.p["crowd_cap_mult"] * d)))
            endcapn = max(capn, self.p["endgame_cap"] * int(round(d)))
            if endgame:
                # Endgame: the reserve floor comes OFF and the stock clears at whatever
                # the book pays. METERING HERE IS A MEASURED MISTAKE (panel, 2026-09-19):
                # our endgame stock is a WAVE -- the last cohort ripens days 25-30 and
                # season-long bag accumulation lands with it -- so a 2/day meter spreads
                # 10 units and dumps ~1,000 on the final day anyway, while the stock sits
                # exposed to midnight overflow in between (lost 33 -> 41, mean -$5.5k).
                # The winners never hold this stock because their PRODUCTION is drip-
                # sized (continuous replanting), not because their sell is capped.
                if day >= SEASON_DAYS - 1 or good in self.p["always_sell"] \
                        or self.p["endgame_cap"] <= 0:
                    n = have                       # final day: nothing scores after this
                else:
                    n = min(have, endcapn)
            elif crowded or good in self.p["always_sell"]:
                # Mid-season crowded-shed emergency. Metered at `capn` days of drain
                # (doubled by the fast valve) with a crater floor at `crowd_floor_frac` x
                # the reserve floor -- the wheat dump at $2.9, bought back the same week
                # at $30-47, was a crowded sale with no floor. always_sell goods (MELON)
                # still clear fully: with the cohort capped at source (`melon_opening`),
                # the clear IS the drain, and metering it only feeds the midnight
                # overflow -- measured, the cap variant cost $2.3k mean and 19 lost units
                # on the panel. Ladder evidence (110850828) agrees: the winner's 100
                # melons realized $81/unit because the COHORT was 9 seeds, not because
                # the sell was slow.
                lim = 2 * capn if valve else capn
                if good in self.p["always_sell"]:
                    n = have
                else:
                    n, mi = 0, minv.get(good, 0)
                    floor = self.p["crowd_floor_frac"] * self.p["reserve"] * _base(good)
                    while n < have and n < lim and price_for(good, mi) >= floor:
                        n += 1
                        mi += 1
            else:
                n, mi = 0, minv.get(good, 0)
                floor = self.p["reserve"] * _base(good)
                # Elite wool window (P2, smoke): past d12 the trough is real, so WOOL's
                # reserve floor drops to the recovery floor -- the trough price is $40-80
                # and the 0.9x reserve floor parks every pop in the shed for weeks.
                if (self.p["elite_script"] and good == "WOOL"
                        and 12 <= day < SEASON_DAYS - self.p["endgame_days"]):
                    floor = self.p["wool_floor"] * _base("WOOL")
                # Blend in the monitor's measured curve when it is seeded. In-mirror the
                # projection reproduces the static floor's arithmetic, so this only bites
                # when the live curve is not the shipped one.
                if self.mkt is not None and self.p["sell_infer"] > 0:
                    tf = self.mkt.tau_floor(good, self.mkt.prev_px.get(good),
                                            (self.mkt.prev_inv or {}).get(good), mi)
                    if tf is not None:
                        w = self.p["sell_infer"]
                        floor = max(floor * (1.0 - w), tf * w)
                while n < have and price_for(good, mi) >= floor:
                    n += 1
                    mi += 1
            if n > 0:
                out.append(["SELL", good, n])
        return out
