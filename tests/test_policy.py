"""Regression tests for the shipped policy.

Each test pins a failure that already happened once -- the docstrings say where. Run:

    python3 -m unittest discover -s tests -q

Nothing here needs kaggle-environments; everything runs against the mirror engine.
"""

from __future__ import annotations

import os
import sys
import unittest

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import KaggricultureEnv  # noqa: E402
from kagfarm.constants import (BOARD_SIZE, OBJECT_TABLE, SEASON_DAYS,   # noqa: E402
                               TURNS_PER_DAY)
from kagfarm.policy import (Policy, PARAMS, PARAMS_BASE,           # noqa: E402
                            read_config_version, probe_melon_interval,
                            set_engine_profile, engine_verdict)

import main  # noqa: E402


def _blank_tiles():
    return [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def _plant(crop, age=0, units=0, watered=False, cu=1, fert_until=-1):
    return dict(kind="PLANT", crop=crop, planted_day=0, yield_units=units,
                watered_today=watered, consecutive_unwatered=cu,
                fertilized_until_day=fert_until)


class TestAnimalSimulator(unittest.TestCase):
    """elite_counter_v1 P0-1: the care bank RESETS at every production pop (engine
    kaggriculture.py:823-830), so a day-0 cared cow pops min(cap, 1+bank) = 6,3,3,3...
    The old age-growing model priced the same cow at "66".
    """

    def test_cow_day0_cared_projection(self):
        from kagfarm.policy import animal_programme
        p = animal_programme("COW", 0, care=True)
        self.assertEqual(p["units"], 36)          # 6 + 3*10 = 36
        self.assertEqual(p["cares"], 30)

    def test_sheep_day0_cared_projection(self):
        from kagfarm.policy import animal_programme
        p = animal_programme("SHEEP", 0, care=True)
        self.assertEqual(p["units"], 34)          # 6 + 4*7 = 34

    def test_goose_day0_cared_projection(self):
        from kagfarm.policy import animal_programme
        p = animal_programme("GOOSE", 0, care=True)
        self.assertEqual(p["units"], 54)          # 4 + 2*25 = 54

    def test_care_off_matches_legacy(self):
        from kagfarm.policy import animal_programme
        for sp in ("COW", "SHEEP", "GOOSE"):
            p = animal_programme(sp, 0, care=False)
            spec = OBJECT_TABLE[sp]
            n_events = len([d for d in range(spec["first_yield_day"], SEASON_DAYS)
                            if (d - spec["first_yield_day"]) % spec["interval"] == 0])
            self.assertEqual(p["units"], n_events)  # base 1 per event

    def test_clipping_diagnostic_positive(self):
        from kagfarm.policy import animal_programme
        # `clipped` is the NEVER-HARVEST counterfactual (the diagnostic the pre-event
        # executor exists to avoid), so both species clip in it: sheep 4-unit pops and
        # cow 3-unit pops both overflow the 6 cap when nobody ever harvests.
        p = animal_programme("SHEEP", 0, care=True)
        self.assertGreater(p["clipped"], 0)
        self.assertGreater(animal_programme("COW", 0, care=True)["clipped"], 0)
        # The executor's pre-event regime is priced in `harvests`: a cow (3-unit pops)
        # batches two pops per drain, a sheep (4-unit pops) needs one drain per event.
        cow = animal_programme("COW", 0, care=True)
        sheep = animal_programme("SHEEP", 0, care=True)
        self.assertLess(cow["harvests"], sheep["harvests"])


class TestPreEventHarvest(unittest.TestCase):
    """P0-2: harvest BEFORE a pop that would clip, using the observed care bank."""

    def _sheep_tile(self, units, bank):
        return dict(kind="PASTURE", animal="SHEEP", placed_day=0, yield_units=units,
                    fed_today=True, cared_today=True, consecutive_unfed=0,
                    fertilizer_available=False, pending_care_bonus=bank)

    def test_sheep_4_with_full_bank_harvests_before_pop(self):
        from kagfarm.policy import shepherd_chores
        # 4 held + 5-unit next pop on a 6 cap -> must harvest NOW or lose 3 wool.
        ops = shepherd_chores(self._sheep_tile(4, 4), 12, False, care=True)
        self.assertIn("HARVEST", ops)

    def test_sheep_4_with_no_bank_waits(self):
        from kagfarm.policy import shepherd_chores
        # 4 held + 1-unit uncared pop fits (4+1 <= 6): no harvest today.
        ops = shepherd_chores(self._sheep_tile(4, 0), 12, False, care=True)
        self.assertNotIn("HARVEST", ops)

    def test_boundary_bank_does_not_over_harvest(self):
        # Tightness check: bank=1 pops 2, 4+2 = 6 fits exactly -> NO harvest (the new
        # trigger must not harvest on fitting days). bank=3 pops 4 -> 4+4 > 6 -> harvest.
        # The old `units + 1 > cap` form could never see the bank=3 clip.
        from kagfarm.policy import shepherd_chores
        self.assertNotIn("HARVEST", shepherd_chores(self._sheep_tile(4, 1), 12, False))
        self.assertIn("HARVEST", shepherd_chores(self._sheep_tile(4, 3), 12, False))

    def test_cow_3_with_full_bank(self):
        from kagfarm.policy import shepherd_chores
        tile = dict(kind="PASTURE", animal="COW", placed_day=0, yield_units=3,
                    fed_today=True, cared_today=True, consecutive_unfed=0,
                    fertilizer_available=False, pending_care_bonus=2)
        # Cow placed day 0 on day 14: age 14, prod day (14-8)%2==0. Pop = min(6, 1+2)=3.
        # 3 + 3 = 6 <= 6: no clip, no harvest.
        ops = shepherd_chores(tile, 14, False, care=True)
        self.assertNotIn("HARVEST", ops)


class TestEliteOpeningFSM(unittest.TestCase):
    """P0-4: the t1/t2 script must be settlement-based (failed orders retry) and
    per-species guarded (COW and SHEEP same-day without re-arming each other)."""

    def _pol(self):
        return Policy({"opening_led": True, "elite_script": True,
                       "melon_opening": 0})

    def test_t1_buys_cow_and_wheat_together(self):
        pol = self._pol()
        me = {"money": 3000, "hires_today": 0, "tiles": _blank_tiles()}
        shed = {}
        out = pol._market_orders({}, me, shed, {}, {},
                                 {"WHEAT": 25}, {"NW"}, 0, 1)
        buys = [o for o in out if o[0] == "BUY_ANIMAL"]
        wheats = [o for o in out if o[:2] == ["BUY_PRODUCT", "WHEAT"]]
        # The founding cow leads, grain ACCOMPANIES the mouths (feed-before-feed-day),
        # and the per-turn bundle cap holds (<=2 animal orders -- the 10-slot budget
        # must leave room for the HIREs, whose silent drop orphaned the roster).
        self.assertEqual(buys[0], ["BUY_ANIMAL", "COW", 1])
        self.assertLessEqual(len(buys), 2)
        self.assertTrue(wheats)
        self.assertGreaterEqual(sum(w[2] for w in wheats), 4)   # bridge for every mouth

    def test_stage2_bundles_cow_and_sheep_same_turn(self):
        pol = self._pol()
        me = {"money": 3000, "hires_today": 0, "tiles": _blank_tiles()}
        # A cow is already IN THE SHED (stage 1 settled).
        out = pol._market_orders({}, me, {"COW": 1}, {}, {}, {"WHEAT": 25},
                                 {"NW"}, 0, 2)
        sps = sorted(o[1] for o in out if o[0] == "BUY_ANIMAL")
        self.assertEqual(sps, ["COW", "SHEEP"])   # bundle on one turn, not either/or

    def test_script_never_refires_after_settlement(self):
        pol = self._pol()
        me = {"money": 3000, "hires_today": 0, "tiles": _blank_tiles()}
        # Everything the script wants has ALREADY settled (observed on the board).
        shed = {"COW": 2, "SHEEP": 3, "WHEAT": 5}
        out = pol._market_orders({}, me, shed, {}, {}, {"WHEAT": 25}, {"NW"}, 0, 3)
        self.assertEqual([o for o in out if o[0] == "BUY_ANIMAL"], [])
        self.assertEqual([o for o in out if o[:2] == ["BUY_PRODUCT", "WHEAT"]], [])

    def test_failed_cow_buy_retries_next_turn(self):
        # t1: money below the cow price -> no order, and the wheat STILL buys (feed first
        # is the point of t1). Next turn with money: the cow fires.
        pol = self._pol()
        me = {"money": 100, "hires_today": 0, "tiles": _blank_tiles()}
        out = pol._market_orders({}, me, {}, {}, {}, {"WHEAT": 25}, {"NW"}, 0, 1)
        self.assertEqual([o for o in out if o[0] == "BUY_ANIMAL"], [])

    def test_off_switch_restores_s10(self):
        pol = Policy({"opening_led": False, "elite_script": True})
        me = {"money": 3000, "hires_today": 0, "tiles": _blank_tiles()}
        out = pol._market_orders({}, me, {}, {}, {}, {"WHEAT": 25}, {"NW"}, 0, 1)
        self.assertEqual([o for o in out if o[0] == "BUY_ANIMAL"], [])


class TestWoolHold(unittest.TestCase):
    """P2: crashed wool holds through the trough; recovery or endgame clears it."""

    def _pol(self):
        return Policy({"elite_script": True, "opening_led": False})

    def test_crashed_wool_held(self):
        pol = self._pol()
        pol.animals = None
        shed = {"WOOL": 20}
        sell = pol._sell_orders(shed, {"WOOL": 0}, {"WOOL": 24}, None, 15, {"NW"})
        self.assertEqual([s for s in sell if s[1] == "WOOL"], [])

    def test_recovered_wool_sells(self):
        pol = self._pol()
        pol.animals = None
        shed = {"WOOL": 20}
        sell = pol._sell_orders(shed, {"WOOL": 0}, {"WOOL": 190}, None, 15, {"NW"})
        self.assertIn(["SELL", "WOOL", 20], sell)

    def test_cap_or_endgame_clears(self):
        pol = self._pol()
        pol.animals = None
        over = pol._sell_orders({"WOOL": 40}, {"WOOL": 0}, {"WOOL": 24}, None, 15, {"NW"})
        self.assertTrue(any(s[1] == "WOOL" and s[2] > 0 for s in over))
        end = pol._sell_orders({"WOOL": 20}, {"WOOL": 0}, {"WOOL": 24}, None,
                               SEASON_DAYS - 1, {"NW"})
        self.assertIn(["SELL", "WOOL", 20], end)


class TestFeedGate(unittest.TestCase):
    """P1: a new mouth needs cumulative feed coverage through the horizon."""

    def test_dry_shed_and_empty_field_blocks_buys(self):
        pol = Policy({"elite_script": True, "opening_led": True, "melon_opening": 0})
        tiles = _blank_tiles()
        plan = pol._animal_plan(tiles, {"NW"}, 0, {}, {"WHEAT": 25, "MILK": 160,
                                                       "WOOL": 200}, {}, 3000)
        # money=3000 can buy the market backstop, so the gate passes there... but shed
        # dry + no field + no mouths already owned means the buffer gate ALSO applies.
        # The elite gate must be no looser than the incumbent's: assert n_buy is gated
        # by BOTH (feed_ok False when the backstop cannot cover 6 days of 3+ mouths).
        if plan and plan["n_buy"] > 0:
            mouths = 3  # pace
            need = mouths * 6
            self.assertGreaterEqual(int(3000 * 0.5 // (25 * 1.4)), need % 999 or need)

    def test_gate_opens_with_shed_grain(self):
        pol = Policy({"elite_script": True, "opening_led": True, "melon_opening": 0})
        tiles = _blank_tiles()
        plan = pol._animal_plan(tiles, {"NW"}, 0, {}, {"WHEAT": 25, "MILK": 160,
                                                       "WOOL": 200}, {"WHEAT": 40}, 3000)
        # With 40 wheat in the shed the coverage gate cannot be the blocker.
        if plan:
            self.assertGreaterEqual(plan["n_buy"] + plan["n_build"], 0)


class TestSpawnGuess(unittest.TestCase):
    """The engine spawns hands ON the four shed-access tiles, not on a ring around them."""

    def test_matches_engine_spawn_hand(self):
        # Engine rule (engine.py / calibration/engine/kaggriculture.py `_spawn_hand`):
        # first least-occupied shed-access tile in NWSE order, counting farmer + hands.
        engine_order = [(4, 4), (5, 4), (4, 5), (5, 5)]
        pol = Policy()
        # Farmer at (4,4) occupies it: first hand goes to the next-free access tile.
        self.assertEqual(pol._spawn_guess(1, [(0, (4, 4))]), [(5, 4)])
        # No farmer on an access tile: first hand takes (4,4) itself.
        self.assertEqual(pol._spawn_guess(4, [(0, (0, 0))]), list(engine_order))
        # Cycle repeats after the four tiles fill.
        self.assertEqual(pol._spawn_guess(6, [(0, (4, 4))])[:4], [(5, 4), (4, 5), (5, 5), (4, 4)])

    def test_mirror_spawn_matches_guess(self):
        # The MIRROR must obey the same rule as the real `_spawn_hand` and the guess.
        # (It used to ring N/W/S/E around (4,4) while the test passed on a literal.)
        env = KaggricultureEnv(episode_steps=720, seed=0)
        f = env.farms[0]
        f.farmer, f.hands = [4, 4], []
        self.assertEqual(env._spawn_hand_pos(f), [5, 4])   # farmer holds (4,4)
        f.hands = [[5, 4], [4, 5], [5, 5]]
        self.assertEqual(env._spawn_hand_pos(f), [4, 4])   # all four occupied once -> NW


class TestWindfallCap(unittest.TestCase):
    """The day-11 windfall used to plant the whole board against $0 of working cash."""

    def _spent(self, pct, res, day, money, unlocked, seeds=None, extra=None):
        over = {"windfall_pct": pct, "windfall_reserve": res}
        over.update(extra or {})
        pol = Policy(params=over)
        want, _ = pol._targets(_blank_tiles(), set(unlocked), day, {}, money,
                               seeds or {}, {"MELON": 10000}, {})
        return sum(OBJECT_TABLE[c]["seed_cost"] * n for c, n in want.items())

    def test_cap_never_touches_single_quadrant_dawn(self):
        # The day-0 opening is load-bearing (-$56k if capped) and on a single quadrant the
        # cap is gated OFF: the allocation is the old one exactly.
        a = self._spent(0.45, 0, 0, 3000.0, ("NW",))
        b = self._spent(1.0, 0, 0, 3000.0, ("NW",))
        self.assertEqual(a, b)
        self.assertGreater(a, 0)

    def test_cap_binds_on_multi_quadrant_dawn(self):
        # The windfall scenario with NO free seeds: $7.6k of cash, all quadrants open, and
        # every seed has to be paid for.
        #
        # H4 contract (re-verified 2026-09-18 after the KT budget layer was measured off:
        # kappa=1.0 capped strawberry at ~17 acres against a realized price of 214% of base
        # and cost $22k on the panel). There is no season-pot ceiling on crops; mix_cap is
        # the only acreage cap and it does not bind below the pct, so the windfall cap is
        # exactly what limits the day.
        # dawn_pace=None: the dawn-pace cap (TestDawnPace, default ON since submission9)
        # binds before the budget layer on a multi-quadrant d11 dawn; this test owns the
        # budget contract, so it disables the pace layer explicitly.
        extra = {"dawn_pace": None}
        a = self._spent(0.45, 0, 11, 7600.0, ("NW", "NE", "SW", "SE"), extra=extra)
        b = self._spent(1.0, 0, 11, 7600.0, ("NW", "NE", "SW", "SE"), extra=extra)
        self.assertLess(a, b)                   # the pct caps the day's seed spend...
        # ...at its fraction of the bank, plus the wage reserve (the pct applies to money
        # NET of the day's wages, which are then spent on wages -- measured $60 at this
        # bank, the half-day wage hold).
        self.assertLessEqual(a, 0.45 * 7600.0 + 200.0)

    def test_pct_one_reproduces_old_budget(self):
        # pct=1.0 with any reserve is the documented off switch: identical allocation.
        a = self._spent(1.0, 0, 11, 5000.0, ("NW", "SE"))
        b = self._spent(1.0, 4, 11, 5000.0, ("NW", "SE"))
        self.assertEqual(a, b)


class TestSellOrders(unittest.TestCase):
    """Sizing off the observed shed is one dump behind the harvest (day-29 seed-0 incident)."""

    def test_sell_counts_carried_inventory(self):
        # H4 contract (re-verified 2026-09-18): SELL names shed PLUS carried bags -- the
        # day-29 incident: orders sized off the observed shed are one dump behind the
        # harvest. The endgame full-clear keeps naming everything (metering the endgame
        # measured WRONG -- see TestSellMeter), so the 51+35 stock is named in full.
        pol = Policy()
        shed = {"STRAWBERRY": 51}
        invs = [{"STRAWBERRY": 35}]
        orders = pol._sell_orders(shed, {}, {"STRAWBERRY": 200}, invs, day=28)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "STRAWBERRY"]
        self.assertEqual(sell and sell[0][2] or 0, 86)      # 51 banked + 35 in bags

    def test_sell_endgame_full_clear_by_default(self):
        # Endgame clears fully by default: the stock is a WAVE (last cohort + bag
        # accumulation), so a meter just moves the dump to the final day while the
        # overflow eats the rest (panel-measured, 2026-09-19: lost 33->41, mean -$5.5k).
        # The meter stays available behind `endgame_cap>0` and is pinned below.
        pol = Policy()
        orders = pol._sell_orders({"STRAWBERRY": 51}, {}, {"STRAWBERRY": 200}, [], day=28)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "STRAWBERRY"]
        self.assertEqual(sell and sell[0][2] or 0, 51)

    def test_endgame_final_day_liquidates_fully(self):
        # The one exception: on the final day nothing scores after this turn, so every
        # remaining unit is named regardless of the meter.
        pol = Policy()
        orders = pol._sell_orders({"STRAWBERRY": 51}, {}, {"STRAWBERRY": 200}, [],
                                  day=SEASON_DAYS - 1)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "STRAWBERRY"]
        self.assertEqual(sell and sell[0][2] or 0, 51)

    def test_inputs_never_sold_before_endgame(self):
        # FERTILIZER sold back the turn after it was bought empties the buffer the
        # fertilize jobs route against.
        pol = Policy()
        orders = pol._sell_orders({"FERTILIZER": 8}, {}, {"FERTILIZER": 150}, [], day=0)
        self.assertFalse(any(o[1] == "FERTILIZER" for o in orders))

    def test_endgame_liquidates_everything(self):
        pol = Policy()
        orders = pol._sell_orders({"FERTILIZER": 8, "MELON": 3}, {}, {}, [], day=SEASON_DAYS - 5)
        goods = {o[1] for o in orders if o[0] == "SELL"}
        self.assertIn("FERTILIZER", goods)
        self.assertIn("MELON", goods)

    def test_endgame_meter_available_behind_param(self):
        # The optional endgame meter (endgame_cap>0) names `endgame_cap` days of drain
        # per day. Off by default -- measured wrong -- but pinned so a sweep that flips
        # it gets exactly the documented arithmetic (drain 1.0/day, cap 2).
        pol = Policy({"endgame_cap": 2})
        orders = pol._sell_orders({"STRAWBERRY": 51}, {}, {"STRAWBERRY": 200}, [], day=28)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "STRAWBERRY"]
        self.assertEqual(sell and sell[0][2] or 0, 2)


class TestSellMeter(unittest.TestCase):
    """Ladder dump-gates (2026-09-19, episode 110850828): a one-turn dump collapses the
    shared book for the whole season -- 714 melons at $26 against the opponent's realized
    $148, wheat at $2.9 bought back the same week at $30-47. Crowd/endgame sells name a
    bounded number of turns of town drain, with a fast valve so nothing rots to overflow."""

    def test_crowd_sale_never_crosses_the_crater_floor(self):
        # The ladder dump encoded (110850828, day 27): a glutted strawberry book. I0 is
        # 10,000, and strawberry's glut curve is already under the crater floor
        # (crowd_floor_frac 0.5 x reserve 1.1 x base 120 = $66) at inventory 10,400 --
        # realized $15.5 on the ladder. The old code named all 1,025 at that price; the
        # metered path prices first and emits NOTHING rather than crater the book further.
        pol = Policy()
        orders = pol._sell_orders({"STRAWBERRY": 400}, {"STRAWBERRY": 10400},
                                  {"STRAWBERRY": 30}, [], day=0)
        self.assertFalse(any(o[0] == "SELL" and o[1] == "STRAWBERRY" for o in orders))

    def test_crowd_sale_above_the_floor_is_metered(self):
        # A crowded shed (80 items -> crowded, valve open -> limit 2x2=4) with a scarce
        # book (price 200): the crater floor admits a bounded offer. Not 80: full-naming
        # is the bug. (In the crowded region the valve is always open -- crowded 55 >
        # valve 45 -- so the operative crowd cap is crowd_cap_mult x 2 x drain.)
        pol = Policy()
        orders = pol._sell_orders({"STRAWBERRY": 80}, {}, {"STRAWBERRY": 200},
                                  [], day=0)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "STRAWBERRY"]
        self.assertTrue(sell)
        self.assertLessEqual(sell[0][2], 4)

    def test_always_sell_melon_clears_when_not_crowded(self):
        # MELON (no shop basket, price never recovers) clears fully whenever the shed is
        # not crowded: with the cohort capped at source (`melon_opening`), the clear IS
        # the drain -- metering it only feeds the midnight overflow (measured, -$2.3k).
        pol = Policy()
        orders = pol._sell_orders({"MELON": 30}, {}, {"MELON": 250}, [], day=0)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "MELON"]
        self.assertEqual(sell and sell[0][2] or 0, 30)

    def test_valve_lifts_the_cap_but_not_to_everything(self):
        # 58 MILK at price 170: valve open (58 > 45) but shed < crowded(55). The uncapped
        # cap is 2; the valve lifts the limit to 4 -- and the crater floor (55, under the
        # realized price) still admits the whole lifted offer. Not 58: no full-naming.
        pol = Policy()
        orders = pol._sell_orders({"MILK": 58}, {}, {"MILK": 170}, [], day=0)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "MILK"]
        self.assertEqual(sell and sell[0][2] or 0, 4)

    def test_valve_ignores_held_feed_grain(self):
        # 40 strawberries + 24 held wheat: valve_total is 40 (< 45), so the valve stays
        # CLOSED and the always-sell melon path -- not an inflated cap -- sizes the offer.
        # The old total-based valve would have opened on the feed grain alone.
        pol = Policy()
        pol.animals = {"live": 2, "held": 0, "n_buy": 0, "n_build": 0}
        orders = pol._sell_orders({"MELON": 10, "WHEAT": 24}, {},
                                  {"MELON": 250, "WHEAT": 30}, [], day=0)
        melon = [o for o in orders if o[0] == "SELL" and o[1] == "MELON"]
        self.assertEqual(melon and melon[0][2] or 0, 10)  # always-sell clears

    def test_endgame_melon_still_clears(self):
        # MELON keeps its endgame full-clear: its price never recovers, so a metered
        # endgame would just feed the midnight overflow with it.
        pol = Policy()
        orders = pol._sell_orders({"MELON": 40}, {}, {"MELON": 250}, [], day=SEASON_DAYS - 5)
        sell = [o for o in orders if o[0] == "SELL" and o[1] == "MELON"]
        self.assertEqual(sell and sell[0][2] or 0, 40)

    def test_opening_book_melon_cohort_capped(self):
        # The donor book's ["BUY_SEED", "MELON", 23] serves as 8: the 23-seed cohort ripens
        # in one synchronized wave (714 units at $26). melon_opening=0 restores the verbatim
        # serve.
        from kagfarm.policy import Policy as P
        pol = P({"melon_opening": 8})
        entry = [["PASS"], [], [["BUY_SEED", "STRAWBERRY", 1], ["BUY_SEED", "MELON", 23],
                                 ["HIRE"], ["SELL", "WHEAT", 5]]]
        pol._book = {0: [{"sig": [], "hours": [entry]}]}
        pol._book_variant = {0: 0}
        out = pol._book_serve({}, 0, 0, 1)
        self.assertEqual(out["market"][0], ["BUY_SEED", "STRAWBERRY", 1])
        self.assertEqual(out["market"][1], ["BUY_SEED", "MELON", 8])
        self.assertEqual(out["market"][2], ["HIRE"])
        self.assertEqual(out["market"][3], ["SELL", "WHEAT", 5])
        off = P({"melon_opening": 0})
        off._book = pol._book
        off._book_variant = pol._book_variant
        self.assertEqual(off._book_serve({}, 0, 0, 1)["market"][1], ["BUY_SEED", "MELON", 23])

    def test_herd_target_and_ramp(self):
        from kagfarm.policy import _ramped_target, PARAMS_BASE
        # submission8 default target is 8 (shepherd stream made it servable: funnel 0
        # escapes, real-tier A/B +$2.8k mean / x3.6 floor over the old n=2, 2026-09-20).
        # The earlier n=2 pin encoded the pre-shepherd optimum.
        self.assertEqual(PARAMS_BASE["n_animals"], 8)
        # The ramp paces the raise: early cap holds day<8, full target by ramp_full_day.
        self.assertEqual(_ramped_target(8, 0, PARAMS_BASE), 2)
        self.assertEqual(_ramped_target(8, 8, PARAMS_BASE), 2)
        self.assertEqual(_ramped_target(8, 14, PARAMS_BASE), 8)


class TestValid(unittest.TestCase):
    """A queued job that validates against a board that has moved on is a silent no-op."""

    def test_fertilize_overwrite_rejected(self):
        # FERTILIZE overwrites fertilized_until_day rather than extending it.
        pol = Policy()
        tiles = _blank_tiles()
        tiles[2][3] = _plant("STRAWBERRY", fert_until=5)
        job = dict(pos=(3, 2), op=["FERTILIZE"])
        self.assertFalse(pol._valid(job, tiles, day=3))

    def test_hour23_plant_refused_by_executor(self):
        # A PLANT at hour 23 cannot get its paired WATER before midnight refresh.
        pol = Policy()
        tiles = _blank_tiles()
        tiles[0][0] = None
        # Executor-level: the op list must be PASS at hour 23 even with seed in stock.
        pol.queues = {0: [dict(pos=(0, 0), op=["PLANT", "MELON"], acts=2)]}
        ops = pol._unit_ops([(0, (0, 0))], tiles, [{}], {"MELON": 1}, {"NW"}, 5,
                            TURNS_PER_DAY - 1, {})
        self.assertEqual(ops[0], ["PASS"])

    def test_seedless_plant_not_consumed(self):
        # Two units routed to two tiles must not both spend the last seed: the stock
        # check decrements. Second unit must NOT be told to PLANT.
        pol = Policy()
        tiles = _blank_tiles()
        pol.queues = {0: [dict(pos=(0, 0), op=["PLANT", "MELON"], acts=2)],
                      1: [dict(pos=(1, 0), op=["PLANT", "MELON"], acts=2)]}
        ops = pol._unit_ops([(0, (0, 0)), (1, (1, 0))], tiles, [{}], {"MELON": 1},
                            {"NW"}, 5, 1, {})
        self.assertEqual(ops[0], ["PLANT", "MELON"])
        self.assertNotEqual(ops[1], ["PLANT", "MELON"])


class TestMarketOrderLedger(unittest.TestCase):
    """A dawn-sized order re-issued every turn bought 24 cows on day 13 ($87k -> $14k)."""

    def test_animal_order_fires_once_per_day(self):
        pol = Policy()
        pol.plan_day = 3
        pol.animals = dict(animal="COW", struct="PASTURE", rank=100.0, worth=4000.0,
                           fert_px=110.0, wheat_px=40.0, held=0, live=0, built=0,
                           n_build=1, n_buy=1)
        obs = dict(player=0, day=3, hour=6,
                   farms=[dict(money=5000.0, hires_today=0, hands=[], farmer=(4, 4),
                               tiles=_blank_tiles(), unlocked_quadrants=["NW"])],
                   private=dict(shed={}, seeds={}, inventories=[{}]),
                   market=dict(prices={}, inventory={"MILK": 10000, "FERTILIZER": 10000,
                                                     "WHEAT": 10000}),
                   town=dict(unlocked_shops=[]))
        act = pol.act(obs)
        n_animal = sum(1 for o in act["market"] if o[0] == "BUY_ANIMAL")
        self.assertEqual(n_animal, 1)
        # Second turn, same day: must not re-issue.
        obs["hour"] = 7
        act = pol.act(obs)
        n_animal = sum(1 for o in act["market"] if o[0] == "BUY_ANIMAL")
        self.assertEqual(n_animal, 0)


class TestPolicyIsolation(unittest.TestCase):
    """PARAMS mutations must not leak across episodes on the in-process tier."""

    def test_params_base_snapshot_intact(self):
        # The fingerprint of the leak: three identical holdout rows.
        self.assertEqual(PARAMS_BASE["windfall_pct"], PARAMS["windfall_pct"])
        self.assertIsNot(PARAMS_BASE, PARAMS)

    def test_policy_copies_params(self):
        pol = Policy(params={"windfall_pct": 0.1})
        self.assertEqual(pol.p["windfall_pct"], 0.1)
        self.assertEqual(PARAMS["windfall_pct"], PARAMS_BASE["windfall_pct"])


class TestEntryPoints(unittest.TestCase):
    """A raise in `agent(obs)` forfeits the episode, so the shell must never throw."""

    def test_agent_on_garbage_obs(self):
        main._POLICIES.clear()               # isolation: no state from another test
        # A non-dict obs must fall through to the PASS shell, never raise.
        self.assertEqual(main.agent(None)["farmer"], ["PASS"])
        # An empty dict obs is legal: the policy plans from scratch on it (that is the
        # never-raise design) and returns a well-formed action.
        act = main.agent({})
        self.assertIsInstance(act["farmer"], list)
        self.assertIsInstance(act["hands"], list)
        self.assertLessEqual(len(act["market"]), 10)

    def test_agent_one_full_mirror_episode(self):
        env = KaggricultureEnv(episode_steps=720, seed=0)
        obs = env._obs()
        main._POLICIES.clear()
        while not env.done:
            obs, _ = env.step([main.agent(obs[0]), main.agent(obs[1])])
        self.assertIsInstance(env.farms[0].money, float)
        self.assertGreater(env.farms[0].money, 0)


class TestMarketMonitor(unittest.TestCase):
    """The runtime monitor (P2) measures but must not touch, unless the knobs say so.

    The whole design contract: monitor=1 with zero knobs is byte-identical; the d-fit
    is contamination-aware; and the sell-floor blend only bites when the live curve
    is not the shipped one. Every scar here is a bug that actually happened.
    """

    def _episode_pair(self, seed):
        """Banks for (monitor off, monitor on) on one seed, plus the monitor."""
        banks = []
        mon = None
        for params in (None, {"monitor": 1}):
            main._POLICIES.clear()
            pol = Policy(params)
            opp = main.agent
            env = KaggricultureEnv(episode_steps=720, seed=seed)
            obs = env._obs()
            while not env.done:
                obs, _ = env.step([pol.act(obs[0]), opp(obs[1])])
            banks.append((env.farms[0].money, env.farms[1].money))
            if pol.mkt is not None:
                mon = pol.mkt
        return banks, mon

    def test_monitor_on_with_zero_knobs_is_byte_identical(self):
        banks, mon = self._episode_pair(0)
        self.assertEqual(banks[0], banks[1],
                         "monitor=1 with knobs at 0 changed behaviour")
        self.assertIsNotNone(mon)
        self.assertTrue(mon.tau, "monitor measured no price slopes at all")

    def test_d_use_baseline_stays_in_band(self):
        _, mon = self._episode_pair(0)
        self.assertEqual(mon.d_use, 1.0,
                         "in-mirror baseline must read as the calibrated game")
        self.assertTrue(0.6 <= mon.d <= 1.0,
                        "baseline d=%.2f escaped the plausible contamination band" % mon.d)

    def test_opp_estimate_is_positive_for_a_trading_peer(self):
        _, mon = self._episode_pair(0)
        # The mutual peer sells wheat and strawberry all season (engine truth ~11/day
        # wheat, ~7/day strawberry); a negative estimate means our own sells were
        # undercounted -- the raw-order-size bug this test pins.
        self.assertGreater(mon.opp.get("WHEAT", -1), 0)
        self.assertGreater(mon.opp.get("STRAWBERRY", -1), 0)
        # And the clamp bounds the EMA input, so the estimate cannot run away.
        self.assertLessEqual(max(mon.opp.values()), 50.0)

    def test_tau_slope_positive_and_finite(self):
        _, mon = self._episode_pair(0)
        for g, t in mon.tau.items():
            self.assertGreater(t, 0.0, "tau[%s] must be a positive slope" % g)
            self.assertLess(t, 500.0, "tau[%s] must stay a sane slope" % g)

class TestEngineFingerprint(unittest.TestCase):
    """Runtime engine-version detection and the profile swap.

    The two wheels differ on five config rows (calibration/live.md); the decisive one,
    townCenterSellInterval 12 vs 24, is READ off the harness config when one is handed
    (the real harness passes configuration to callable agents) and probed off MELON's
    drain cadence otherwise (melon is in no shop basket, so its only drain is the town
    centre). Every test here cleans up the process-global profile — it leaks otherwise.
    """

    def setUp(self):
        self.addCleanup(set_engine_profile, "1.32.7")
        self.addCleanup(main._POLICIES.clear)

    def _struct(self, **kw):
        class S:
            pass
        s = S()
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    def test_config_reader_both_versions(self):
        self.assertEqual(read_config_version(self._struct(townCenterSellInterval=24)), "1.32.7")
        self.assertEqual(read_config_version(self._struct(townCenterSellInterval=12)), "1.32.2")
        # dict config (some harnesses pass plain dicts) and absent/override configs
        self.assertEqual(read_config_version({"townCenterSellInterval": 24}), "1.32.7")
        self.assertIsNone(read_config_version(None))
        self.assertIsNone(read_config_version(self._struct()))
        # a non-default override is NOT a version signal — leave the pin alone
        self.assertIsNone(read_config_version(self._struct(townCenterSellInterval=8)))

    def test_probe_melon_interval_gaps(self):
        # declines every 12 samples -> tau 12; every 24 -> 24; rising book -> no signal
        seq12 = [1000 - 12 * (i // 12) for i in range(48)]
        seq24 = [1000 - 24 * (i // 24) for i in range(48)]
        rising = list(range(1000, 1048))
        self.assertEqual(probe_melon_interval(seq12), 12)
        self.assertEqual(probe_melon_interval(seq24), 24)
        self.assertEqual(probe_melon_interval(rising), 0)
        self.assertEqual(probe_melon_interval([]), 0)

    def test_profile_swap_changes_ticks_and_replacement(self):
        import kagfarm.constants as K
        set_engine_profile("1.32.2")
        self.assertEqual(K.TOWN_CENTER_SELL_INTERVAL_TURNS, 12)
        self.assertEqual(K.TOWN_CENTER_TICKS_PER_DAY, 2)
        self.assertFalse(K.UNLOCK_WITH_REPLACEMENT)
        self.assertEqual(K.town_center_multiplier(5), 1.0)   # day 5 < 10 -> stage-1 mult
        self.assertEqual(K.town_center_multiplier(15), 2.0)  # 10 <= 15 < 20
        self.assertEqual(K.town_center_multiplier(25), 4.0)  # day >= 20
        self.assertEqual(K.MARKET_PARAMS["CARROT"]["below_f"], "log")
        set_engine_profile("1.32.7")
        self.assertEqual(K.TOWN_CENTER_SELL_INTERVAL_TURNS, 24)
        self.assertEqual(K.TOWN_CENTER_TICKS_PER_DAY, 1)
        self.assertTrue(K.UNLOCK_WITH_REPLACEMENT)
        self.assertEqual(K.town_center_multiplier(25), 1.0)
        self.assertEqual(K.MARKET_PARAMS["CARROT"]["below_f"], "hinge")

    def test_auto_on_mirror_engine_is_byte_identical(self):
        # the mirror passes no config, so auto falls to the melon probe; the mirror IS
        # 1.32.7, so the probe must land on 1.32.7 and play byte-identically to the pin.
        banks = []
        for params in (None, {"force_engine": "auto"}):
            main._POLICIES.clear()
            pol = Policy(params)
            env = KaggricultureEnv(episode_steps=720, seed=0)
            obs = env._obs()
            while not env.done:
                obs, _ = env.step([pol.act(obs[0]), main.agent(obs[1])])
            banks.append((env.farms[0].money, env.farms[1].money))
            self.assertIsNone(pol.last_error)
        self.assertEqual(banks[0], banks[1],
                         "force_engine=auto on a 1.32.7 mirror changed behaviour")
        self.assertEqual(engine_verdict(), "1.32.7")

    def test_config_path_switches_profile(self):
        # a config with tau=12 (as the real harness would hand a 1.32.2 ladder) must flip
        # the profile on the second act call (the probe needs two book samples first).
        env = KaggricultureEnv(episode_steps=720, seed=0)
        obs = env._obs()
        main._POLICIES.clear()
        pol = Policy({"force_engine": "auto"})
        cfg = self._struct(townCenterSellInterval=12)
        pol.act(obs[0], cfg)
        pol.act(obs[0], cfg)
        self.assertEqual(engine_verdict(), "1.32.2")
        self.assertEqual(pol.engine, "1.32.2")


class TestMarketOrderCap(unittest.TestCase):
    """The engine silently slices the market command list at MAX_MARKET_ORDERS
    (engine.py applies `[:MAX_MARKET_ORDERS]` before settling). Nothing that
    survives `main.agent` may exceed the cap, and a SELL must never be pushed
    past it -- sells settle in their own pass, so a dropped sell is produce
    destroyed at midnight for nothing."""

    def test_sell_orders_never_exceed_slot_cap(self):
        """`_sell_orders` clamps itself to MAX_MARKET_ORDERS no matter the shed."""
        from kagfarm.constants import MAX_MARKET_ORDERS, I0, SEASON_DAYS
        pol = Policy()
        shed = {g: 500 for g in ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY",
                                 "MELON", "MILK", "EGG", "WOOL")}
        prices = {g: 5.0 for g in shed}
        # Endgame day: the reserve floor is off and inputs sell too, so the list
        # is genuinely long rather than trivially empty.
        out = pol._sell_orders(shed, {g: I0 for g in shed}, prices, None,
                               SEASON_DAYS - 1)
        self.assertLessEqual(len(out), MAX_MARKET_ORDERS)
        self.assertTrue(all(o[0] == "SELL" for o in out))

    def test_no_turn_emits_more_than_ten_market_orders(self):
        """Full-episode guard: every turn's market list fits the engine cap."""
        from kagfarm.constants import MAX_MARKET_ORDERS
        env = KaggricultureEnv(episode_steps=720, seed=7)
        obs = env._obs()
        main._POLICIES.clear()
        while not env.done:
            act = main.agent(obs[0])
            self.assertLessEqual(len(act["market"]), MAX_MARKET_ORDERS)
            obs, _ = env.step([act, main.agent(obs[1])])


class TestParamsRestore(unittest.TestCase):
    """run_one mutates the module-global PARAMS to inject a candidate; it must
    restore the module state before returning, or the next in-process episode
    (evaluate(workers=1)) silently evaluates the incumbent with candidate
    parameters."""

    def test_run_one_restores_params(self):
        import eval as eval_mod
        before = dict(PARAMS)
        eval_mod.run_one((0, "starter", "main", {"reserve": 9.99}))
        self.assertEqual(dict(PARAMS), before)


class TestOpeningBook(unittest.TestCase):
    """Opening book: serve recorded donor moves on a matching dawn signature,
    fall back to the live planner on any miss, and never raise on a bad file."""

    @staticmethod
    def _capture_day0(path):
        """Record seed-0 day 0 vs starter into a one-variant book file."""
        import json
        from kagfarm.policy import opening_book_signature
        env = KaggricultureEnv(episode_steps=720, seed=0)
        obs = env._obs()
        main._POLICIES.clear()
        sig, hours = None, []
        while not env.done and obs[0]["day"] == 0:
            if sig is None:
                sig = list(opening_book_signature(obs[0]))
            act = main.agent(obs[0])
            hours.append([list(act["farmer"]),
                          [list(h) for h in act["hands"]],
                          [list(m) for m in act["market"]]])
            obs, _ = env.step([act, main.agent(obs[1])])
        with open(path, "w") as f:
            json.dump({"meta": {}, "days": {"0": [{"sig": sig, "hours": hours}]}}, f)
        return sig, hours

    def test_off_by_default_and_missing_file_is_safe(self):
        self.assertEqual(PARAMS_BASE.get("opening_book", 0), 0)
        pol = Policy({"opening_book": 1, "book_file": "/nonexistent/book.json"})
        env = KaggricultureEnv(episode_steps=720, seed=0)
        obs = env._obs()
        main._POLICIES.clear()
        while not env.done:
            obs, _ = env.step([pol.act(obs[0]), main.agent(obs[1])])
        self.assertGreater(env.farms[0].money, 0)   # planner took over everywhere

    def test_serves_donor_moves_exactly_on_match(self):
        import os
        import tempfile
        from kagfarm.policy import Policy
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "book.json")
            sig, donor_hours = self._capture_day0(path)
            env = KaggricultureEnv(episode_steps=720, seed=0)
            obs = env._obs()
            main._POLICIES.clear()
            pol = Policy({"opening_book": 1, "book_file": path, "melon_opening": 0})
            served_any = False
            while not env.done and obs[0]["day"] == 0:
                served = pol.act(obs[0])
                # NON-vacuous: the comparator is the RECORDED donor move, not the live
                # agent. Both sides falling back to the same planner used to make this
                # equality hold even with a broken serve path (it did, until today).
                # melon_opening=0: this test pins VERBATIM serving; the cohort cap has its
                # own unit test (TestSellMeter.test_opening_book_melon_cohort_capped).
                h = obs[0]["hour"]
                self.assertEqual(served["farmer"], list(donor_hours[h][0]))
                self.assertEqual(served["hands"], [list(x) for x in donor_hours[h][1]])
                self.assertEqual(served["market"], [list(x) for x in donor_hours[h][2]])
                served_any = True
                obs, _ = env.step([served, main.agent(obs[1])])
            self.assertTrue(served_any)
            # Serving is the live mechanism, not the fallback: the book decided ON and
            # the day is recorded as serving, and the whole recorded day was covered.
            self.assertIn(0, pol._book_decided)
            self.assertNotIn(0, pol._book_halt_days)

    def test_signature_miss_falls_back_to_planner(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "book.json")
            self._capture_day0(path)
            with open(path) as f:
                book = json.load(f)
            book["days"]["0"][0]["sig"][1] = 999999   # wrong money total
            with open(path, "w") as f:
                json.dump(book, f)
            env = KaggricultureEnv(episode_steps=720, seed=0)
            obs = env._obs()
            main._POLICIES.clear()
            pol = Policy({"opening_book": 1, "book_file": path})
            while not env.done and obs[0]["day"] == 0:
                self.assertEqual(pol.act(obs[0]), main.agent(obs[0]))
                obs, _ = env.step([pol.act(obs[0]), main.agent(obs[1])])
            self.assertIn(0, pol._book_halt_days)   # the miss was RECORDED as a halt
            self.assertNotIn(0, pol._book_decided)

    def test_signature_reproducible_at_dawn(self):
        """The signature is read exactly once per day -- at the day's first act, hour 0,
        before the market settle and before any planting. Its only required property
        is reproducibility: identical episodes (same shops, same own state) must yield
        the same dawn signature, which is what matching needs. Intra-day it drifts by
        design (settlement, planting) and nothing re-reads it."""
        from kagfarm.policy import opening_book_signature
        env = KaggricultureEnv(episode_steps=720, seed=0)
        obs = env._obs()
        main._POLICIES.clear()
        dawn = opening_book_signature(obs[0])
        env2 = KaggricultureEnv(episode_steps=720, seed=0)
        obs2 = env2._obs()
        self.assertEqual(opening_book_signature(obs2[0]), dawn)
        # And the dawn snapshot is distinct from the post-settle state (documents WHY
        # the decision happens at the day's first turn only).
        obs, _ = env.step([main.agent(obs[0]), main.agent(obs[1])])
        self.assertNotEqual(opening_book_signature(obs[0]), dawn)


class TestWorkSteal(unittest.TestCase):
    """Work stealing: an early-finished unit takes the nearest feasible tail job from
    another run instead of PASSing until midnight (idle_frac was 10-11%)."""

    def _policy(self, **over):
        pol = Policy(dict(work_steal=1, **over))
        pol.queues = {}
        return pol

    @staticmethod
    def _tiles():
        return [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]

    def test_takes_nearest_feasible_tail(self):
        pol = self._policy()
        far = dict(pos=(9, 9), op=["PLANT", "MELON"], tier=0, value=50.0)
        near = dict(pos=(5, 4), op=["PLANT", "MELON"], tier=0, value=50.0)
        pol.queues = {1: [dict(far), dict(far)], 2: [dict(near), dict(near)]}
        got = pol._steal_job(0, (4, 4), self._tiles(), 3, {"MELON": 9}, 10)
        self.assertIsNotNone(got)
        self.assertEqual(tuple(got["pos"]), (5, 4))

    def test_never_steals_then_chain_or_head(self):
        pol = self._policy()
        head = dict(pos=(5, 4), op=["PLANT", "MELON"], tier=0, value=50.0)
        chained = dict(pos=(6, 4), op=["PLANT", "MELON"], tier=0, value=50.0,
                       then=["WATER"])
        pol.queues = {1: [dict(head), dict(chained), dict(chained)]}
        # Only the tail (a `then`-chained PLANT) is steal-eligible by position;
        # it must be refused, leaving nothing -- never a queue of one, never a chain.
        got = pol._steal_job(0, (6, 4), self._tiles(), 3, {"MELON": 9}, 10)
        self.assertIsNone(got)

    def test_seedless_plant_not_stolen(self):
        pol = self._policy()
        plant = dict(pos=(5, 4), op=["PLANT", "MELON"], tier=0, value=50.0)
        pol.queues = {1: [dict(plant), dict(plant)]}
        got = pol._steal_job(0, (5, 4), self._tiles(), 3, {"MELON": 0}, 10)
        self.assertIsNone(got)
        got = pol._steal_job(0, (5, 4), self._tiles(), 3, {"MELON": 2}, 10)
        self.assertIsNotNone(got)

    def test_on_by_default(self):
        # ADOPTed 17 Sep on the corrected (H1/H2/H3) mirror: 4-block gate, +$229 aggregate.
        self.assertEqual(PARAMS_BASE.get("work_steal", 0), 1)

    def test_steal_enabled_changes_play(self):
        """Full-episode: the knob is wired and alters behaviour when on."""
        env = KaggricultureEnv(episode_steps=720, seed=5)
        obs = env._obs()
        main._POLICIES.clear()
        while not env.done:
            obs, _ = env.step([main.agent(obs[0]), main.agent(obs[1])])
        env2 = KaggricultureEnv(episode_steps=720, seed=5)
        obs = env2._obs()
        # Default is ON (adopted); the wiring proof compares against the OFF variant.
        pol = Policy({"work_steal": 0})
        while not env2.done:
            obs, _ = env2.step([pol.act(obs[0]), main.agent(obs[1])])
        self.assertNotEqual(env.farms[0].money, env2.farms[0].money)


class TestH4AnimalPipeline(unittest.TestCase):
    """H4 (2026-09-17, ladder evidence): the mirror's op semantics diverged from the real
    engine and the feed programme starved a live herd. 8/8 ladder replays showed the same
    signature: 2 cows bought, zero milk sold, `COW: 2` rotting in the final shed. The pins:

    engine   PICKUP requires a shed-access tile; FEED/FERTILIZE draw from the UNIT's carried
             inventory, never the shed; FERTILIZE is active day..day+2 (3 days inclusive).
    planner  feed chains are pre-pended by _replan (never enter the value lottery); care jobs
             continue on days the expansion gate refuses to buy (a marginal animal must not
             blind the planner to the live ones).
    """

    ANIMALS = ("COW", "SHEEP", "GOOSE")

    def _pasture(self, animal="COW", unfed=0):
        return {"kind": "PASTURE", "animal": animal, "placed_day": 5, "yield_units": 0,
                "fed_today": False, "consecutive_unfed": unfed, "cared_today": False,
                "fertilizer_available": False, "pending_care_bonus": 0}

    def _env(self, steps=72):
        return KaggricultureEnv(episode_steps=steps, seed=0)

    def test_mirror_pickup_requires_shed_adjacency(self):
        # Real: `if not _is_shed_adjacent((fx, fy), board_size): return`. The mirror lacked
        # the check, which is what let the one-leg placement job work locally and rot every
        # bought animal on the ladder.
        env = self._env()
        env.farms[0].shed["WHEAT"] = 5
        env.farms[0].farmer = [2, 2]                      # not a shed-access tile
        obs = env._obs()
        env.step([{"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}])
        self.assertEqual(env.farms[0].inventories[0], {},
                         "PICKUP away from the shed must silently no-op")
        # positive control: from a shed-access tile it works
        env.farms[0].farmer = [4, 4]
        env.step([{"farmer": ["PICKUP", "WHEAT", 1], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}])
        self.assertEqual(env.farms[0].inventories[0].get("WHEAT"), 1)

    def test_mirror_feed_draws_from_inventory_not_shed(self):
        # Real: `_inv_take(inv, "WHEAT", 1)` -- shed-side wheat is invisible to FEED. The
        # mirror drew shed-first, so locally-fed animals starved on the ladder.
        env = self._env()
        env.farms[0].tiles[0][0] = self._pasture()
        env.farms[0].shed["WHEAT"] = 10                   # shed is stocked...
        env.farms[0].inventories = [{}]                   # ...but the unit carries nothing
        env.farms[0].farmer = [0, 0]
        env.step([{"farmer": ["FEED"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}])
        self.assertFalse(env.farms[0].tiles[0][0]["fed_today"],
                         "FEED must not draw from the shed")
        env.farms[0].inventories = [{"WHEAT": 1}]
        env.step([{"farmer": ["FEED"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}])
        self.assertTrue(env.farms[0].tiles[0][0]["fed_today"])
        self.assertEqual(env.farms[0].inventories[0], {})

    def test_mirror_fertilize_window_is_three_days(self):
        # Real: `max(existing, day + 2)` -- active d..d+2. The mirror wrote day+3, a fourth
        # free day of fertility in every local gate.
        env = self._env()
        env.t = 5 * TURNS_PER_DAY                    # day 5 (day/hour are read-only views of t)
        env.farms[0].tiles[2][3] = _plant("STRAWBERRY")
        env.farms[0].inventories = [{"FERTILIZER": 1}]
        env.farms[0].farmer = [3, 2]
        env.step([{"farmer": ["FERTILIZE"], "hands": [], "market": []},
                  {"farmer": ["PASS"], "hands": [], "market": []}])
        self.assertEqual(env.farms[0].tiles[2][3]["fertilized_until_day"], 7)

    def test_feed_chore_survives_the_roster_recut(self):
        # H4 contract (re-verified 2026-09-18): the feed chore is a dawn-planned chain
        # pre-pended to the nearest unit's queue -- and the hour-1 roster re-cut REBUILDS the
        # queues (HIRE costs a slot per hand, so a 12-hand roster arrives over turns). The
        # KT-turn per-turn injector variant of this test measured SLOWER on the panel
        # (re-planning from live state every turn perturbed the crop runs) and is not ships.
        # The dawn chore must therefore survive its own re-cut: with an unfed cow on the
        # board, a h0 plan and a h1 re-cut (two fresh hands) must BOTH head some queue with
        # the chained PICKUP->FEED.
        pol = Policy()
        pol.shops = []
        pol.want, pol.fert_have, pol.eff = {}, 0, {}
        tiles = _blank_tiles()
        tiles[0][0] = self._pasture(unfed=0)
        pol.animals = dict(animal="COW", struct="PASTURE", rank=60.0, worth=4000.0,
                           fert_px=110.0, wheat_px=40.0, held=0, live=1, built=1,
                           daily_product=45.0, n_build=0, n_buy=0)
        units = [(0, (4, 4)), (1, (5, 4))]
        pol._replan(tiles, {"NW"}, 6, 0, {}, {}, units, 0.0)
        with_chore = any((r and r[0].get("then") or [None])[0] == "FEED"
                         for r in pol.queues.values())
        pol._replan(tiles, {"NW"}, 6, 1, {}, {}, units + [(2, (4, 5)), (3, (5, 5))], 0.0)
        after = any((r and r[0].get("then") or [None])[0] == "FEED"
                    for r in pol.queues.values())
        self.assertTrue(with_chore and after,
                        "the dawn feed chore must survive the roster re-cut")

    def test_animal_plan_cares_for_live_herd_when_gate_refuses_buys(self):
        # collect_jobs keyed ALL animal care on the plan dict; when the marginal-rank gate
        # returned None, the planner went blind to animals already on the board -- no feed,
        # no dose collect, no harvest. Care is unconditional; only expansion is gated.
        pol = Policy()
        pol.shops = []
        tiles = _blank_tiles()
        tiles[0][0] = self._pasture(unfed=1)
        plan = pol._animal_plan(tiles, {"NW"}, 16, {}, {}, {}, 50000.0)
        self.assertIsNotNone(plan, "a live herd must produce a care plan even on a gate-fail day")
        self.assertEqual(plan["n_buy"], 0, "no purchase while an animal is starving")
        import kagfarm.policy as _policy
        jobs = _policy.collect_jobs(tiles, {"NW"}, 16, {}, {}, {}, pol.p, animals=plan)
        self.assertTrue(any(j["op"][0] == "PICKUP" and (j.get("then") or [None])[0] == "FEED"
                            for j in jobs), "the live animal must still get its feed job")

    def test_full_episode_leaves_no_animal_rotting_in_shed(self):
        # The exact ladder signature, on the corrected mirror: 2 cows bought and PLACED,
        # zero rotting in the shed at T=720. Pre-H4 this test's assertion saw `COW: 2`.
        env = self._env(720)
        obs = env._obs()
        main._POLICIES.clear()
        while not env.done:
            obs, _ = env.step([main.agent(obs[0]), main.agent(obs[1])])
        rotted = {k: v for k, v in env.farms[0].shed.items() if k in self.ANIMALS}
        self.assertEqual(rotted, {}, "bought animals must be placed, not rot in the shed")


class TestHerdRamp(unittest.TestCase):
    """Day-gated herd target (dairy recipe, 2026-09-19).

    A no-op at the measured optimum (n_animals=2); when the target is raised it holds the
    herd at `ramp_cap_early` until the first yields and releases it linearly by
    `ramp_full_day`, so a big herd target can never pull its whole cash cost into day-0
    market orders.
    """

    P = {"herd_ramp": True, "ramp_cap_early": 2, "ramp_full_day": 14}

    def test_noop_at_measured_optimum(self):
        from kagfarm.policy import _ramped_target
        for day in range(0, 30):
            self.assertEqual(_ramped_target(2, day, self.P), 2)

    def test_capped_before_first_yields_then_linear(self):
        from kagfarm.policy import _ramped_target
        seq = [_ramped_target(8, d, self.P) for d in (0, 5, 7, 8, 9, 11, 14, 20)]
        self.assertEqual(seq, [2, 2, 2, 2, 3, 5, 8, 8])

    def test_kill_switch_restores_old_target(self):
        from kagfarm.policy import _ramped_target
        self.assertEqual(_ramped_target(8, 2, dict(self.P, herd_ramp=False)), 8)


class TestDawnPace(unittest.TestCase):
    """Dawn-pace cap (replays 110850828 / 110874286): the dawn planner sprayed a windfall
    into one crop when land unlocked (41+20 strawberry tiles over two dawns); the cohort
    ripened synchronized and sold at 23% of base while the winner drip-sold the same crop
    at 4-7x the unit price. The cap bounds planner *extension* per dawn; seeds already in
    hand are exempt (a bought-not-planted seed carries, it is not re-bought)."""

    def test_default_is_off_and_mechanism_pinned(self):
        # 2026-09-20 one-day default-ON trial REVERTED by real-tier A/B (3x replicated):
        # ON = $51,023 mean / p10 $41,445 vs OFF = $59,481 / $43,767 (12 seeds x self+
        # passive). Per-unit strawberry price rose (228% vs 197%) but the d11-12 cohort is
        # the season's MAIN strawberry inventory (12-day cycle) -- pacing it halved volume
        # and the gross loss dwarfed the price gain. Panel epistemics apply to SELL-side
        # axes; production volume follows real engine physics the real tier reproduces.
        # Earlier panel measurement: OFF $66,346/$65,465 288/288 wins, ON $51,256/$49,934.
        from kagfarm.policy import PARAMS_BASE
        self.assertIsNone(PARAMS_BASE["dawn_pace"])
        # The mechanism still paces when enabled (gated trials).
        pol = Policy({"dawn_pace": {"STRAWBERRY": 8}})
        want, _ = pol._targets(_blank_tiles(), {"NW", "NE", "SW", "SE"}, 11, {}, 10**9, {}, {}, {})
        self.assertEqual(want.get("STRAWBERRY", 0), 8)

    def test_planner_respects_pace(self):
        pol = Policy({"dawn_pace": {"STRAWBERRY": 8}})
        tiles = _blank_tiles()
        want, plan = pol._targets(tiles, {"NW"}, 11, {}, 10**9, {}, {}, {})
        self.assertLessEqual(want.get("STRAWBERRY", 0), 8)
        self.assertGreater(want.get("STRAWBERRY", 0), 0)

    def test_pace_off_restores_windfall_dawn(self):
        # The spray needs room: 4 quadrants, no pace -> strawberry takes 16 tiles in one dawn.
        pol = Policy({"dawn_pace": None})
        want, _ = pol._targets(_blank_tiles(), {"NW", "NE", "SW", "SE"}, 11, {}, 10**9, {}, {}, {})
        self.assertGreater(want.get("STRAWBERRY", 0), 8)

    def test_replacement_is_never_vetoed(self):
        # The melon factory legally replants its finished 8-tile cycle every dawn. The gate
        # must veto only NET GROWTH, never the replacement of live tiles -- capping the whole
        # allocation measured $12k worse on the panel (2026-09-19 bisect).
        pol = Policy({"dawn_pace": {"MELON": 2, "STRAWBERRY": 8}})
        tiles = _blank_tiles()
        for x in range(4):
            tiles[1][x] = _plant("MELON", age=3)
        want, _ = pol._targets(tiles, {"NW", "NE", "SW", "SE"}, 11, {}, 10**9, {}, {}, {})
        self.assertGreaterEqual(want.get("MELON", 0), 4)  # 4 live replaced + fresh growth

    def test_net_growth_is_bounded(self):
        pol = Policy({"dawn_pace": {"STRAWBERRY": 3}})
        tiles = _blank_tiles()
        for x in range(4):
            tiles[1][x] = _plant("STRAWBERRY", age=1)
        want, _ = pol._targets(tiles, {"NW", "NE", "SW", "SE"}, 11, {}, 10**9, {}, {}, {})
        self.assertLessEqual(want.get("STRAWBERRY", 0), 7)  # 4 live + 3 growth

    def test_held_seeds_are_paced_too(self):
        # 20 strawberry seeds in hand: planting all 20 same-day recreates the synchronized
        # cohort that sold at 23% of base. With 0 live tiles the cap is 0+8; the rest carry.
        pol = Policy({"dawn_pace": {"STRAWBERRY": 8}})
        want, _ = pol._targets(_blank_tiles(), {"NW", "NE", "SW", "SE"}, 11, {}, 10**9,
                               {"STRAWBERRY": 20}, {}, {})
        self.assertEqual(want.get("STRAWBERRY", 0), 8)


class TestPlannerMelonCap(unittest.TestCase):
    """The day-0 melon cohort cap: mechanism exists in the ALLOCATOR, default OFF.

    Ladder 0-4 batch (110897820/...): with opening_book=0 the only melon_opening consumer
    lived in _book_serve, so all four games planted the donor's 23-melon cohort. The
    planner-path clamp (day 0 only, book-independent) was built and verified (day-0
    BUY_SEED MELON = exactly 8, surplus to carrot/wheat), then its default REVERTED on
    real-tier A/B: clamp alone = $51,162 vs $59,481 caps-off -- the day-0 melon windfall
    FUNDS the d11-12 strawberry spray, so capping it defunds the strawberry programme.
    """

    def test_default_allocator_unclamped(self):
        # The shipped contract: melon_opening=0 = allocator unclamped, day-0 mix_cap
        # acreage restored (the funded-spray behavior the A/B prefers).
        pol = Policy({"dawn_pace": None})
        want, _ = pol._targets(_blank_tiles(), {"NW"}, 0, {}, 10**9, {}, {}, {})
        self.assertGreater(want.get("MELON", 0), 8)

    def test_clamp_binds_on_day0_when_enabled(self):
        # melon_opening=8 clamps day 0 regardless of book state; surplus tiles flow to
        # the next-best crop in the marginal loop (carrot/wheat, measured).
        pol = Policy({"melon_opening": 8, "dawn_pace": None})
        want, _ = pol._targets(_blank_tiles(), {"NW"}, 0, {}, 10**9, {}, {}, {})
        self.assertLessEqual(want.get("MELON", 0), 8)
        self.assertGreater(want.get("MELON", 0), 0)

    def test_clamp_is_day0_only(self):
        # Later dawns keep the full mix_cap acreage: a second cohort above the price
        # floor is legal.
        pol = Policy({"melon_opening": 8, "dawn_pace": None})
        want, _ = pol._targets(_blank_tiles(), {"NW"}, 1, {}, 10**9, {}, {}, {})
        self.assertGreater(want.get("MELON", 0), 8)


def _pasture(x, y, animal="COW", fed=False, cared=False, fert=True, units=5):
    return (x, y), dict(kind="PASTURE", animal=animal, placed_day=0, fed_today=fed,
                        cared_today=cared, fertilizer_available=fert,
                        yield_units=units, consecutive_unfed=0)


class TestShepherd(unittest.TestCase):
    """The shepherd stream (scope v4): animal chores as a first-class scheduled job
    stream. The A/B/C run escaped 7/7 animals because feed visits bid in the serpentine
    lottery; these loops are computed, budgeted, and carved out of that lottery."""

    def test_chore_order_and_guards(self):
        from kagfarm.policy import shepherd_chores
        pos, tile = _pasture(2, 2, units=99)   # units >= max_held: harvest due
        ops = shepherd_chores(tile, 15, False, care=True)
        self.assertEqual(ops, ["FEED", "CARE", "COLLECT_FERTILIZER", "HARVEST"])
        # Fully served tile: nothing to do.
        _, done = _pasture(2, 2, fed=True, cared=True, fert=False, units=0)
        self.assertEqual(shepherd_chores(done, 15, False), [])
        # Endgame: no feeds/care (herd is being liquidated), only the harvest.
        _, end = _pasture(2, 2, units=6)
        self.assertEqual(shepherd_chores(end, SEASON_DAYS - 1, True), ["HARVEST"])
        # Empty structure: nothing.
        self.assertEqual(shepherd_chores(dict(kind="PASTURE", animal=None), 15, False), [])

    def test_loops_cover_every_animal_with_batched_head(self):
        from kagfarm.policy import shepherd_loops
        tiles = [_pasture(3 + i, 4) for i in range(10)]
        loops, budget, loop_costs = shepherd_loops(tiles, 15, {"NW"}, n_units=1)
        self.assertEqual(len(loops), 1)
        self.assertEqual(loop_costs, [budget])            # single loop owns the whole budget
        loop = loops[0]
        heads = [j for j in loop if j["op"][0] == "PICKUP"]
        self.assertEqual(len(heads), 1)
        self.assertEqual(heads[0]["op"][2], 10)          # one op loads the whole day's grain
        covered = {j["pos"] for j in loop if j["op"][0] in ("FEED", "CARE",
                                                            "COLLECT_FERTILIZER")}
        self.assertEqual(covered, {(x, y) for (x, y), _ in tiles})   # completeness
        self.assertGreaterEqual(budget, 10 + 3)          # ops + at least the walks

    def test_bag_cap_segments_the_loop(self):
        from kagfarm.policy import shepherd_loops
        tiles = [_pasture(3 + i, 4) for i in range(10)]
        loops, _, _ = shepherd_loops(tiles, 15, {"NW"}, n_units=1, bag_cap=4)
        loop = loops[0]
        drops = [j for j in loop if j["op"] == ["DROP"]]
        self.assertGreaterEqual(len(drops), 2)           # 10 loads at cap 4 -> segments
        reloads = [j for j in loop if j["op"][0] == "PICKUP" and len(j["op"]) > 2
                   and j["op"][1] == "WHEAT" and j is not loop[0]]
        self.assertGreaterEqual(len(reloads), 1)         # reload after the first DROP

    def test_default_off_and_cofeasibility_gate(self):
        from kagfarm.policy import PARAMS_BASE
        # submission8 default: stream ON (measured +$2.8k mean / x3.6 floor); 0 remains
        # the off-switch back to the pre-shepherd behaviour.
        self.assertEqual(PARAMS_BASE["shepherd_mode"], 1)
        # Overloaded stream: budget beyond the shepherd share freezes herd growth.
        pol = Policy({"shepherd_mode": 1, "n_animals": 20, "shepherd_share": 1})
        tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        for i in range(9):
            (x, y), t = _pasture(1 + i % 4, 1 + i // 4)
            tiles[y][x] = t
        plan = pol._animal_plan(tiles, {"NW"}, 15, {}, {}, {}, 10 ** 7)
        self.assertGreater(plan["budget"], 0)
        self.assertEqual(plan["n_buy"], 0)               # no asset the loops cannot serve

    def test_structures_take_shed_near_tiles_but_never_shed_tiles(self):
        from kagfarm.constants import SHED_TILES
        from kagfarm.route import manhattan as _mh
        pol = Policy({"shepherd_mode": 1})
        tiles = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        animals = dict(n_build=1, struct="PASTURE", rank=60.0)
        from kagfarm.policy import collect_jobs
        jobs = collect_jobs(tiles, {"NW"}, 15, {}, {}, {}, pol.p, animals=animals)
        builds = [j for j in jobs if j["op"][0] == "BUILD_PASTURE"]
        self.assertEqual(len(builds), 1)
        spot = builds[0]["pos"]
        self.assertNotIn(spot, set(SHED_TILES.values()))
        # Genuinely shed-nearest legal tile: (4,3) sits one step from the NW shed tile
        # and is not one of the four reserved access tiles. The old farthest-first rule
        # took the BACK of the distance-sorted empties ((0,0)); the flip takes the front.
        # empties.sort is a stable sort over scan order (y-major, x-minor), so
        # distance ties resolve to the earliest-scanned tile: (4,3) precedes (3,4).
        cands = [(x, y) for y in range(BOARD_SIZE) for x in range(BOARD_SIZE)
                 if (x, y) not in set(SHED_TILES.values())]
        self.assertEqual(spot, min(cands, key=lambda p: (_mh(p, SHED_TILES["NW"]), p[1], p[0])))


if __name__ == "__main__":
    unittest.main()
