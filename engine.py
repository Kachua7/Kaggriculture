"""
Kaggriculture simulation engine — an independent, from-scratch reimplementation
of the mechanics described in the competition knowledge-transfer doc.

This is NOT the official `kaggle-environments` package (that's a live, gated
Kaggle competition environment this sandbox can't fetch/install). It's a
faithful best-effort model of the *documented rules* so you can:
  - see the whole game loop end to end,
  - run agents against each other,
  - inspect state turn by turn,
  - and iterate on strategy before touching the real submission.

Where the source doc was precise (market price curves, hire cost, watering/
feeding death rules, town demand), this follows it exactly. Where the doc
described behavior qualitatively (e.g. exact day-by-day crop yield growth),
this uses the most literal reading of the stated rules and flags the
assumption in a comment. Calibrate against real replays before trusting it
for a final submission strategy.

Author: generated for local experimentation.
"""

from __future__ import annotations
import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Engine numbers live in kagfarm/constants.py, NOT here.
#
# The mirror and the shipped agent have to agree on every constant, or the tuning loop
# optimises a different game from the one we submit into. So there is exactly one copy,
# it lives in the package that ships, and the mirror imports it.
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kagfarm.constants import (  # noqa: E402
    EPISODE_STEPS, TURNS_PER_DAY, SEASON_DAYS, BOARD_SIZE, STARTING_MONEY,
    MAX_MARKET_ORDERS, SHED_CAPACITY, WEED_SPAWN_CHANCE,
    TOWN_SHOP_UNLOCK_INTERVAL_DAYS, TOWN_SHOP_SELL_INTERVAL_TURNS,
    TOWN_CENTER_SELL_INTERVAL_TURNS, FARM_HAND_COST_MULT, MAX_SHOP_INSTANCES,
    LAND_PRICES, QUADRANT_ORDER, SHED_TILES, FARMER_START,
    CROPS_ONE_TIME, CROPS_ONGOING, ANIMALS, ANIMAL_PRODUCT, ANIMAL_STRUCTURE,
    OBJECT_TABLE, I0, MARKET_PARAMS, SELLABLE, BUYBACK,
    SHOP_TABLE, TOWN_CENTER_PRODUCTS,
    fib_hire_cost, hire_cost_total, price_for, _f,
)


# ---------------------------------------------------------------------------
# Farm / player state
# ---------------------------------------------------------------------------

@dataclass
class Farm:
    money: float = STARTING_MONEY
    tiles: list = field(default_factory=list)          # tiles[y][x]
    farmer: list = field(default_factory=lambda: list(FARMER_START))
    hands: list = field(default_factory=list)           # list of [x,y]
    unlocked_quadrants: set = field(default_factory=lambda: {"NW"})
    hires_today: int = 0
    shed: dict = field(default_factory=dict)
    seeds: dict = field(default_factory=dict)
    inventories: list = field(default_factory=list)     # [farmer_inv, hand_inv, ...]

    def init_board(self):
        self.tiles = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if not self._quadrant_of(x, y) in self.unlocked_quadrants:
                    self.tiles[y][x] = "LOCKED"

    @staticmethod
    def _quadrant_of(x: int, y: int) -> str:
        if x < 5 and y < 5:
            return "NW"
        if x >= 5 and y < 5:
            return "NE"
        if x < 5 and y >= 5:
            return "SW"
        return "SE"

    def relock_refresh(self):
        """Re-derive LOCKED tiles after a land purchase (keeps existing content elsewhere)."""
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                if self.tiles[y][x] == "LOCKED" and self._quadrant_of(x, y) in self.unlocked_quadrants:
                    self.tiles[y][x] = None


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

class KaggricultureEnv:
    def __init__(self, episode_steps: int = EPISODE_STEPS, seed: Optional[int] = None, verbose: bool = False):
        self.episode_steps = episode_steps
        self.rng = random.Random(seed)
        self.verbose = verbose
        self.reset()

    # -- lifecycle ---------------------------------------------------------

    def reset(self):
        self.t = 0
        self.farms = [Farm(), Farm()]
        for f in self.farms:
            f.init_board()
            f.inventories = [{}]  # farmer inventory only at first
        self.market_inventory = {r: float(I0) for r in MARKET_PARAMS}
        self.shops: list[str] = []
        self.done = False
        self.log = []
        return self._obs()

    @property
    def day(self):
        return self.t // TURNS_PER_DAY

    @property
    def hour(self):
        return self.t % TURNS_PER_DAY

    # -- observation ---------------------------------------------------------

    def _public_farm(self, i: int) -> dict:
        f = self.farms[i]
        return {
            "money": f.money,
            "tiles": f.tiles,
            "farmer": list(f.farmer),
            "hands": [list(h) for h in f.hands],
            "unlocked_quadrants": sorted(f.unlocked_quadrants),
            "hires_today": f.hires_today,
        }

    def _obs(self) -> list[dict]:
        market = {
            "inventory": {r: int(v) for r, v in self.market_inventory.items()},
            "prices": {r: price_for(r, v) for r, v in self.market_inventory.items()},
        }
        town = {"unlocked_shops": list(self.shops)}
        base = {
            "step": self.t,
            "day": self.day,
            "hour": self.hour,
            "farms": [self._public_farm(0), self._public_farm(1)],
            "market": market,
            "town": town,
        }
        obs = []
        for i, f in enumerate(self.farms):
            o = dict(base)
            o["player"] = i
            o["private"] = {
                "shed": dict(f.shed),
                "seeds": dict(f.seeds),
                "inventories": [dict(inv) for inv in f.inventories],
            }
            obs.append(o)
        return obs

    # -- helpers ---------------------------------------------------------

    def _units(self, f: Farm):
        """Yield (index, pos_list) for farmer (index 0) then hands (1..)."""
        yield 0, f.farmer
        for i, h in enumerate(f.hands):
            yield i + 1, h

    def _add_shed(self, f: Farm, item: str, n: int):
        cur = f.shed.get(item, 0)
        space = SHED_CAPACITY - sum(v for k, v in f.shed.items())
        add = max(0, min(n, space))
        if add:
            f.shed[item] = cur + add
        return add

    def _dump_inventory(self, f: Farm, inv: dict):
        for item, n in list(inv.items()):
            added = self._add_shed(f, item, n)
            # overflow discarded regardless
        inv.clear()

    def _tile(self, f: Farm, x: int, y: int):
        if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
            return f.tiles[y][x]
        return None

    def _in_bounds(self, x, y):
        return 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE

    # -- one full step ---------------------------------------------------------

    def step(self, actions: list[dict]):
        """actions: [action_p0, action_p1] each {'farmer':[...], 'hands':[[...],...], 'market':[[...],...]}"""
        if self.done:
            raise RuntimeError("episode already finished")

        # 1+2: player unit actions (movement / tile ops), treated as simultaneous
        for pi, act in enumerate(actions):
            self._apply_unit_actions(pi, act)

        # 3: market actions
        self._apply_market_actions(actions)

        # 4: town buy actions
        self._town_tick()

        # 5: update observations / day refresh
        self.t += 1
        if self.t % TURNS_PER_DAY == 0 and self.t < self.episode_steps:
            self._day_refresh()
        if self.t >= self.episode_steps:
            self.done = True

        return self._obs(), self.done

    # -- unit actions ---------------------------------------------------------

    MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}

    def _apply_unit_actions(self, pi: int, act: dict):
        f = self.farms[pi]
        farmer_op = act.get("farmer") or ["PASS"]
        hand_ops = act.get("hands") or []
        ops = [(0, f.farmer, farmer_op)]
        for i, h in enumerate(f.hands):
            op = hand_ops[i] if i < len(hand_ops) else ["PASS"]
            ops.append((i + 1, h, op))

        # PLANT is all-or-nothing across units within a turn [real]: the engine validates the
        # whole batch against the seed count before applying any of it, so one seed and two
        # PLANT ops produce ZERO plants, not one. Modelled here so a planner regression that
        # over-commits seeds shows up in eval instead of only on the ladder. Measured with
        # /tmp/plant_probe.py over six episodes: 0 over-commits against 959 plantings, so this
        # guard is currently inert -- which is the point of adding it while it is free.
        want: dict[str, int] = {}
        for _, _, op in ops:
            if op and op[0] == "PLANT" and len(op) > 1:
                want[op[1]] = want.get(op[1], 0) + 1
        voided = {c for c, n in want.items() if n > f.seeds.get(c, 0)}
        if voided:
            ops = [(u, p, (["PASS"] if (o and o[0] == "PLANT" and len(o) > 1
                                        and o[1] in voided) else o))
                   for u, p, o in ops]

        for unit_idx, pos, op in ops:
            if not op:
                continue
            name = op[0]
            args = op[1:]
            try:
                self._dispatch_unit_op(f, unit_idx, pos, name, args)
            except Exception:
                pass  # invalid actions are silent no-ops

    def _dispatch_unit_op(self, f: Farm, unit_idx: int, pos: list, name: str, args: list):
        if name in self.MOVES:
            dx, dy = self.MOVES[name]
            nx, ny = pos[0] + dx, pos[1] + dy
            if self._in_bounds(nx, ny):
                pos[0], pos[1] = nx, ny
            return
        if name == "PASS":
            return

        x, y = pos
        tile = self._tile(f, x, y)
        while len(f.inventories) <= unit_idx:
            f.inventories.append({})
        inv = f.inventories[unit_idx]
        at_shed = (x, y) in SHED_TILES.values()

        if name == "PICKUP":
            item, n = args[0], (args[1] if len(args) > 1 else 1)
            have = f.shed.get(item, 0)
            take = min(have, n)
            if take > 0:
                f.shed[item] = have - take
                if f.shed[item] == 0:
                    del f.shed[item]
                inv[item] = inv.get(item, 0) + take
            return

        if name == "DROP":
            if at_shed:
                self._dump_inventory(f, inv)
            return

        if name == "PLACE":
            item = args[0]
            n = args[1] if len(args) > 1 else 1
            if tile is not None and tile != "LOCKED" and isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE"):
                # place animal from inventory onto matching empty structure
                needed_struct = ANIMAL_STRUCTURE.get(item)
                if tile["kind"] == needed_struct and tile.get("animal") is None and inv.get(item, 0) > 0:
                    tile["animal"] = item
                    tile["placed_day"] = self.day
                    tile["yield_units"] = 0
                    tile["fed_today"] = False
                    tile["consecutive_unfed"] = 0
                    tile["cared_today"] = False
                    tile["fertilizer_available"] = False
                    tile["pending_care_bonus"] = 0
                    inv[item] -= 1
                    if inv[item] == 0:
                        del inv[item]
            elif at_shed:
                have = inv.get(item, 0)
                move = min(have, n)
                added = self._add_shed(f, item, move)
                inv[item] = have - added
                if inv[item] <= 0 and item in inv:
                    del inv[item]
            return

        if tile == "LOCKED" or tile is None and name not in ("PLANT", "BUILD_COOP", "BUILD_PASTURE"):
            # most tile ops no-op on locked or (for non-plant ops) empty tiles below;
            # PLANT / BUILD are handled explicitly and check emptiness themselves
            if tile == "LOCKED":
                return

        if name == "PLANT":
            crop = args[0]
            if tile is not None or crop not in OBJECT_TABLE:
                return
            if f.seeds.get(crop, 0) <= 0:
                return
            f.seeds[crop] -= 1
            spec = OBJECT_TABLE[crop]
            # [real] one_time crops carry a hard expiry stamped at planting; ongoing crops
            # carry -1 and expire after their last scheduled yield instead. Confirmed on every
            # planted tile in calibration/real_engine/tutorial_episode.json: CARROT +96 turns,
            # WHEAT +120, MELON +312 from planted_day * 24, and -1 for every TOMATO and
            # STRAWBERRY regardless of when it went in.
            life = spec.get("lifespan_days")
            mls = (self.day + life) * TURNS_PER_DAY if life else -1
            f.tiles[y][x] = {
                "kind": "PLANT", "crop": crop, "planted_day": self.day,
                "watered_today": False, "consecutive_unwatered": 1,
                "yield_units": spec.get("start_yield", 0),
                "max_lifespan_step": mls, "fertilized_until_day": -1,
                "_sched_done": 0,  # internal: scheduled productions completed (ongoing crops)
                "_decaying": False,
            }
            return

        if name == "WATER":
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                # [real] The yield bonus is granted HERE, inside the action, not at the
                # midnight refresh: at steps 144->145 of the tutorial replay a melon goes
                # 1 -> 2 units on the same turn its WATER is applied, at day 6 hour 1. All
                # eleven yield increases in that episode coincide with a WATER on that tile,
                # at whatever hour the farmer happened to arrive. So a unit is harvestable
                # the same day it is watered, and every one-time cycle is a full day shorter
                # than an end-of-day model predicts.
                #
                # Guarded on `watered_today` so a second hand watering the same tile in the
                # same turn is a no-op. The real engine's behaviour with duplicate waterings
                # is not observable in the replay; idempotence is the conservative choice,
                # because the alternative invents a "water one melon six times" exploit that
                # the planner would happily find and the real engine would not honour.
                if not tile["watered_today"]:
                    tile["watered_today"] = True
                    self._grant_yield(tile)
            return

        if name == "HARVEST":
            if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("yield_units", 0) > 0:
                crop = tile["crop"]
                spec = OBJECT_TABLE[crop]
                # KT doc: HARVEST before first_yield_day is a no-op even if yield_units > 0.
                # This matters because WHEAT starts at yield_units=1.
                first = spec.get("first_yield_day", spec.get("sched_days", [0])[0])
                if self.day - tile["planted_day"] < first:
                    return
                n = tile["yield_units"]
                inv[crop] = inv.get(crop, 0) + n
                if spec["kind"] == "one_time":
                    f.tiles[y][x] = None
                else:
                    tile["yield_units"] = 0
                return
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                n = tile.get("yield_units", 0)
                if n > 0:
                    product = ANIMAL_PRODUCT[tile["animal"]]
                    inv[product] = inv.get(product, 0) + n
                    tile["yield_units"] = 0
            return

        if name == "FERTILIZE":
            if isinstance(tile, dict) and tile.get("kind") == "PLANT":
                have = f.shed.get("FERTILIZER", 0)
                if have > 0:
                    f.shed["FERTILIZER"] = have - 1
                    if f.shed["FERTILIZER"] == 0:
                        del f.shed["FERTILIZER"]
                    tile["fertilized_until_day"] = self.day + 3
            return

        if name == "BUILD_COOP" or name == "BUILD_PASTURE":
            if tile is None:
                f.tiles[y][x] = {
                    "kind": "COOP" if name == "BUILD_COOP" else "PASTURE",
                    "animal": None, "placed_day": self.day, "yield_units": 0,
                    "fed_today": False, "consecutive_unfed": 0, "cared_today": False,
                    "fertilizer_available": False, "pending_care_bonus": 0,
                }
            return

        if name == "FEED":
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                have = f.shed.get("WHEAT", 0) or inv.get("WHEAT", 0)
                # spend from shed first, then carried inventory
                if f.shed.get("WHEAT", 0) > 0:
                    f.shed["WHEAT"] -= 1
                    if f.shed["WHEAT"] == 0:
                        del f.shed["WHEAT"]
                    tile["fed_today"] = True
                elif inv.get("WHEAT", 0) > 0:
                    inv["WHEAT"] -= 1
                    if inv["WHEAT"] == 0:
                        del inv["WHEAT"]
                    tile["fed_today"] = True
            return

        if name == "COLLECT_FERTILIZER":
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and tile.get("fertilizer_available"):
                inv["FERTILIZER"] = inv.get("FERTILIZER", 0) + 1
                tile["fertilizer_available"] = False
            return

        if name == "CARE":
            if isinstance(tile, dict) and tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                tile["cared_today"] = True
            return

        if name == "DIG":
            if isinstance(tile, dict):
                if tile.get("kind") == "WEED":
                    f.tiles[y][x] = None
                elif tile.get("kind") == "PLANT":
                    f.tiles[y][x] = None
                elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal") is None:
                    f.tiles[y][x] = None
            return

    # -- market ---------------------------------------------------------

    def _apply_market_actions(self, actions: list[dict]):
        orders = [list((act.get("market") or [])[:MAX_MARKET_ORDERS]) for act in actions]

        # First: fixed-price / non price-curve orders, own order, per player, in order.
        # We process these before the price-curve SELL/BUY_PRODUCT interleave so that
        # HIRE/BUY_LAND/BUY_SEED/BUY_ANIMAL never depend on interleave order.
        remaining = [[], []]
        for pi in (0, 1):
            f = self.farms[pi]
            for order in orders[pi]:
                op = order[0]
                if op in ("SELL", "BUY_PRODUCT"):
                    remaining[pi].append(order)
                    continue
                self._apply_fixed_order(pi, f, order)

        # Then: SELL / BUY_PRODUCT, grouped by resource, interleaved unit-by-unit
        # between the two players (Section 11.3).
        by_resource = {}
        for pi in (0, 1):
            for order in remaining[pi]:
                op, resource = order[0], order[1]
                n = order[2] if len(order) > 2 else 1
                by_resource.setdefault(resource, {}).setdefault(pi, []).append((op, n))

        for resource, per_player in by_resource.items():
            q0 = self._expand_units(per_player.get(0, []))
            q1 = self._expand_units(per_player.get(1, []))
            i0 = i1 = 0
            while i0 < len(q0) or i1 < len(q1):
                if i0 < len(q0):
                    self._settle_one_unit(0, resource, q0[i0])
                    i0 += 1
                if i1 < len(q1):
                    self._settle_one_unit(1, resource, q1[i1])
                    i1 += 1

    @staticmethod
    def _expand_units(ops: list[tuple[str, int]]) -> list[str]:
        """Turn [('SELL', 3), ('BUY_PRODUCT', 2)] into ['SELL','SELL','SELL','BUY_PRODUCT','BUY_PRODUCT']."""
        out = []
        for op, n in ops:
            out.extend([op] * max(0, int(n)))
        return out

    def _settle_one_unit(self, pi: int, resource: str, op: str):
        f = self.farms[pi]
        inv = self.market_inventory[resource]
        if op == "SELL":
            have = f.shed.get(resource, 0)
            if have <= 0:
                return
            price = price_for(resource, inv)  # pre-sell inventory
            f.shed[resource] = have - 1
            if f.shed[resource] == 0:
                del f.shed[resource]
            f.money += price
            if price > 1:  # floor units are bought but not added to market inventory
                self.market_inventory[resource] = inv + 1
        elif op == "BUY_PRODUCT":
            if resource not in BUYBACK:
                return
            post_inv = inv - 1
            if post_inv < 0:
                return
            price = price_for(resource, post_inv)  # post-buy inventory
            if f.money < price:
                return
            f.money -= price
            self._add_shed(f, resource, 1)
            self.market_inventory[resource] = post_inv

    def _apply_fixed_order(self, pi: int, f: Farm, order: list):
        op = order[0]
        if op == "BUY_SEED":
            crop, n = order[1], (order[2] if len(order) > 2 else 1)
            spec = OBJECT_TABLE.get(crop)
            if not spec or "seed_cost" not in spec:
                return
            cost = spec["seed_cost"]
            for _ in range(n):
                if f.money < cost:
                    break
                f.money -= cost
                f.seeds[crop] = f.seeds.get(crop, 0) + 1
        elif op == "BUY_ANIMAL":
            animal, n = order[1], (order[2] if len(order) > 2 else 1)
            spec = OBJECT_TABLE.get(animal)
            if not spec or "buy_cost" not in spec:
                return
            cost = spec["buy_cost"]
            for _ in range(n):
                if f.money < cost:
                    break
                f.money -= cost
                self._add_shed(f, animal, 1)
        elif op == "HIRE":
            cost = fib_hire_cost(f.hires_today)
            if f.money >= cost:
                f.money -= cost
                f.hires_today += 1
                f.hands.append(self._spawn_hand_pos(f))
                f.inventories.append({})
        elif op == "BUY_LAND":
            for q, cost in LAND_PRICES.items():
                if q not in f.unlocked_quadrants:
                    if f.money >= cost:
                        f.money -= cost
                        f.unlocked_quadrants.add(q)
                        f.relock_refresh()
                    break

    def _spawn_hand_pos(self, f: Farm) -> list:
        sx, sy = SHED_TILES["NW"]
        candidates = [(sx, sy - 1), (sx - 1, sy), (sx, sy + 1), (sx + 1, sy)]  # N W S E
        occ = {(f.farmer[0], f.farmer[1])}
        for h in f.hands:
            occ.add((h[0], h[1]))
        counts = []
        for cx, cy in candidates:
            counts.append(sum(1 for (ox, oy) in occ if ox == cx and oy == cy))
        best = min(counts)
        for (cx, cy), c in zip(candidates, counts):
            if c == best:
                return [cx, cy]
        return list(candidates[0])

    # -- town ---------------------------------------------------------

    def _town_tick(self):
        t = self.t + 1  # this tick completes turn self.t; check on 1-indexed elapsed turns
        if t % TOWN_SHOP_SELL_INTERVAL_TURNS == 0:
            for shop in self.shops:
                basket = SHOP_TABLE[shop]
                for product, qty in basket.items():
                    self.market_inventory[product] = max(0.0, self.market_inventory[product] - qty)
        if t % TOWN_CENTER_SELL_INTERVAL_TURNS == 0:
            for product in TOWN_CENTER_PRODUCTS:
                self.market_inventory[product] = max(0.0, self.market_inventory[product] - 1)

    # -- day refresh ---------------------------------------------------------

    def _day_refresh(self):
        new_day = self.day  # self.t already advanced past midnight
        # Unlock a new shop every N days, cap 8, sampled WITHOUT replacement.  [real]
        # The replay unlocks ICE_CREAM_SHOP, YARN_STORE, BRUNCH_SPOT, SMOOTHIE_SHOP,
        # PIZZA_SHOP, PET_CAFE, BAKERY, FARMERS_MARKET on days 3,6,...,24 — all eight types,
        # no repeats. Under the with-replacement draw this used to do, eight distinct draws
        # from eight types has probability 8!/8^8 = 0.24%, so the real engine is permuting.
        # This is not a cosmetic fix: with replacement the expected number of distinct shops
        # by day 24 is 5.2, not 8, so the mirror was understating late-season demand for
        # everything in the baskets by roughly a third.
        if new_day % TOWN_SHOP_UNLOCK_INTERVAL_DAYS == 0 and new_day > 0 and len(self.shops) < MAX_SHOP_INSTANCES:
            remaining = [s for s in SHOP_TABLE if s not in self.shops]
            self.shops.append(self.rng.choice(remaining or list(SHOP_TABLE.keys())))

        for f in self.farms:
            # dump every unit's inventory into the shed
            for inv in f.inventories:
                if inv:
                    self._dump_inventory(f, inv)
            # weeds: roll on every empty unlocked tile
            for y in range(BOARD_SIZE):
                for x in range(BOARD_SIZE):
                    tile = f.tiles[y][x]
                    if tile is None and Farm._quadrant_of(x, y) in f.unlocked_quadrants:
                        if self.rng.random() < WEED_SPAWN_CHANCE:
                            f.tiles[y][x] = {"kind": "WEED"}

            # plants / animals day-refresh
            for y in range(BOARD_SIZE):
                for x in range(BOARD_SIZE):
                    tile = f.tiles[y][x]
                    if not isinstance(tile, dict):
                        continue
                    if tile.get("kind") == "PLANT":
                        self._refresh_plant(f, x, y, tile)
                    elif tile.get("kind") in ("COOP", "PASTURE") and tile.get("animal"):
                        self._refresh_animal(f, tile)

            # farm hands vanish; farmer respawns at shed
            f.hands = []
            f.hires_today = 0
            f.farmer = list(FARMER_START)
            f.inventories = [{}]  # farmer only; hand inventories are recreated on hire

    def _grant_yield(self, tile: dict):
        """Add the watering bonus to a plant, at the moment WATER is applied.  [real]

        The gain window is `bonus_start..bonus_end` for one-time crops, which is NOT the same
        as `first_yield_day..max_yield_day`. They coincide for wheat and carrot, and they are
        6..12 versus 10..10 for melon: the replay shows melon gaining +1 at ages 6, 7, 8, 9
        and 10 and reaching its cap of 6 on the day HARVEST first becomes legal, then holding
        6 through ages 11 and 12 while the tutorial agent waited. `first_yield_day` gates the
        harvest, not the growth.

        Gains depend only on watering today and on the age, not on any streak: the one carrot
        gain in the replay landed with `consecutive_unwatered = 1`.
        """
        spec = OBJECT_TABLE[tile["crop"]]
        age = self.day - tile["planted_day"]
        fertilized = tile["fertilized_until_day"] >= self.day
        gain = 2 if fertilized else 1

        if spec["kind"] == "one_time":
            if not (spec["bonus_start"] <= age <= spec["bonus_end"]):
                return
            cap = spec["max_yield"] if fertilized else spec["max_yield_unfert"]
            tile["yield_units"] = min(cap, tile["yield_units"] + gain)
        else:
            sched = spec["sched_days"]
            if age not in sched or tile["_sched_done"] >= len(sched):
                return
            # `max_yield` caps STANDING units, not lifetime ones, so an ongoing crop that is
            # harvested between scheduled yields collects more than the cap over its life.
            tile["yield_units"] = min(spec["max_yield"], tile["yield_units"] + gain)
            tile["_sched_done"] += 1

    def _refresh_plant(self, f: Farm, x: int, y: int, tile: dict):
        """Midnight bookkeeping: thirst, then expiry. Growth happens in WATER, not here."""
        spec = OBJECT_TABLE[tile["crop"]]
        age = self.day - tile["planted_day"]  # self.day has already rolled: days survived
        watered = tile["watered_today"]
        tile["watered_today"] = False

        if not watered:
            tile["consecutive_unwatered"] += 1
        else:
            tile["consecutive_unwatered"] = 0

        if tile["consecutive_unwatered"] >= 2:
            f.tiles[y][x] = {"kind": "WEED"}
            return

        # [real] Hard expiry for one-time crops. The replay's single observed case: a carrot
        # with max_lifespan_step 120 was alive at step 120 hour 0 holding 2 units, lost one at
        # step 121 and was WEED by step 123 — so past the stamp an unharvested crop rots away
        # over about three turns and leaves a weed to dig. Modelled as a kill at the midnight
        # itself, which is up to three turns early. That is deliberate: the alternative hands
        # the planner an hour-0-to-hour-3 grace window to schedule harvests into, and if the
        # real engine's rot is even slightly faster the whole harvest is lost. The rule the
        # planner should obey is the same either way — a one-time crop must be harvested by the
        # end of age `lifespan_days - 1`, and every row of CROP_PLAN does.
        mls = tile.get("max_lifespan_step", -1)
        if mls >= 0 and self.t >= mls:
            f.tiles[y][x] = {"kind": "WEED"}
            return

        if spec["kind"] != "one_time":
            # Ongoing crops carry mls = -1 and expire once their schedule is exhausted. The
            # replay never kept a tomato or strawberry alive to its first scheduled yield, so
            # the timing here is [doc] only; WEED-on-completion is the conservative reading
            # because it forces the planner to harvest the last yield promptly.
            sched = spec["sched_days"]
            if tile["_sched_done"] >= len(sched) and age > sched[-1]:
                f.tiles[y][x] = {"kind": "WEED"}

    def _refresh_animal(self, f: Farm, tile: dict):
        animal = tile["animal"]
        spec = OBJECT_TABLE[animal]
        age = self.day - tile["placed_day"]
        fed = tile["fed_today"]
        cared = tile["cared_today"]

        if not fed:
            tile["consecutive_unfed"] += 1
        else:
            tile["consecutive_unfed"] = 0

        if tile["consecutive_unfed"] >= 2:
            tile["animal"] = None  # escapes, unrecoverable
            tile["yield_units"] = 0
            tile["pending_care_bonus"] = 0
            return

        # fertilizer: 1 unit available at end of every day regardless of fed/cared,
        # doesn't stack
        tile["fertilizer_available"] = True

        first = spec["first_yield_day"]
        interval = spec["interval"]
        is_production_day = age >= first and (age - first) % interval == 0

        if is_production_day:
            base_gain = 1
            if fed:
                total = base_gain + tile.get("pending_care_bonus", 0)
                tile["yield_units"] = min(spec["max_held"], tile["yield_units"] + total)
            else:
                tile["yield_units"] = min(spec["max_held"], tile["yield_units"] + base_gain)
            tile["pending_care_bonus"] = 0
        else:
            if fed and cared:
                tile["pending_care_bonus"] = tile.get("pending_care_bonus", 0) + 1

        tile["fed_today"] = False
        tile["cared_today"] = False

    # -- convenience: run a whole episode ---------------------------------------------------------

    def run(self, agents: list) -> "KaggricultureEnv":
        """agents: list of two callables agent(obs)->action dict, or the strings
        'pass' / 'random' / 'starter' for the built-in opponents."""
        from agents import BUILTIN_AGENTS
        fns = [BUILTIN_AGENTS[a] if isinstance(a, str) else a for a in agents]
        obs = self._obs()
        history = [obs]
        while not self.done:
            acts = [fns[0](obs[0]), fns[1](obs[1])]
            obs, done = self.step(acts)
            history.append(obs)
        self.history = history
        return self
