"""Kaggriculture V3 policy.

Doctrine
--------
1. The season pays for units *sold into the town's demand vector*, not units grown. Total town
   demand is near-constant (~1,900-2,700 units a season) but its composition is redrawn every
   game, so every acreage and head-count is derived from `remaining_drain` for that good and
   nothing else. No fixed crop mix.
2. Livestock is the highest-yielding asset on the board once CARE is run daily: a cow banks
   `min(max_held, 1 + interval)` = 3 milk every 2 days instead of 1, plus a free fertilizer
   every day. Animals are bought from turn one and sized to the milk/egg/wool pots.
3. Labour is nearly free (12 hands cost $376/day against a six-figure book) and no unit ever
   idles while a job exists.
4. Nothing is sold that is not in the shed, and nothing synchronises: planting is rate-limited
   so income and labour are smooth and the shed never floods.

Structure: `plan()` runs once per dawn and sets targets; `jobs()` rebuilds the work list every
turn from the observation; `assign()` hands jobs to units by value/distance with sticky
assignments; `market()` emits orders under the 10-slot budget.
"""

from __future__ import annotations

from kagfarm_spec_v3 import (
    ANIMALS, ANIMAL_OF, BOARD, CROPS, LAND_PRICES, MARKET, MAX_ORDERS, PRODUCTS,
    PRODUCT_OF, SEASON, SHED, SHED_CAP, SHOPS, TPD,
    animal_daily_visits, animal_units, base_of, block_price, crop_cycle,
    crop_daily_visits, crop_units, dist, drain_per_day, is_gain_age, nearest_shed,
    price_at, quadrant_of, remaining_drain, shed_tiles, water_ages,
)


# eval-harness shim: mirrors submission-2's main.py contract (one Policy per seat,
# clock-backwards rebuild) so `evaluate(agent_mod="kagfarm_policy_v3")` drives it exactly
# as the ladder would.
_POLICIES = {}


def agent(obs, config=None):
    seat = int(obs["player"])
    pol = _POLICIES.get(seat)
    if pol is None or obs["step"] < pol.last_step:
        pol = _POLICIES[seat] = Policy()
    return pol.act(obs, config)

# --------------------------------------------------------------------------- tunables

P = dict(
    hands=12,                 # 13/14 measured WORSE on the panel (f1/e3 A-B): the fib hire
                              # + wage spend beats the marginal hand's output at this labour
                              # model. The author's 'idle cash' argument was real, but the
                              # cash goes to land+herd instead (see the structure fix).
    hire_reserve=500,         # day's wages for a full roster, held back from every purchase
    hire_cash_frac=0.40,      # only cash may shrink the roster

    # Fraction of a good's remaining season pot we aim to supply ourselves. Below 1.0 on
    # purpose: the opponent sells into the same inventory, and revenue in this market is
    # single-peaked in our own supply -- overshooting a pot is far more expensive than
    # undershooting it.
    # Fraction of a good's remaining season pot we aim to supply. Revenue is single-peaked in
    # our own supply, but the peak sits close to the pot, not at 60% of it: across ten measured
    # ladder games every good we touched closed at 150-230% of base, i.e. under-supplied.
    # The real brake is `min_px` plus the glut term in `_budget`, not a low kappa.
    # kappa stays at V3's measured values. The post-mortem's 'raise kappa' recommendation was
    # fitted to one ladder game where prices ran hot because BOTH farms under-produced; on the
    # 144-episode panel the raised values regress hard (e3 vs f2: identical, e3 vs V4 bundle:
    # -$15k). The author's own 'min_px is the real brake' note is the correct mechanism.
    kappa={"MILK": 0.92, "EGG": 0.95, "WOOL": 0.70,
           "STRAWBERRY": 0.85, "TOMATO": 0.90, "WHEAT": 1.00,
           "CARROT": 1.00, "MELON": 0.50},

    # A crop/animal is only worth a tile if the block its next unit meets clears this multiple
    # of base. Stops the allocator planting into a market it has already filled.
    min_px={"MILK": 0.95, "EGG": 0.85, "WOOL": 0.95,
            "STRAWBERRY": 0.95, "TOMATO": 1.05, "WHEAT": 0.80,
            "CARROT": 0.80, "MELON": 0.75},

    melon_tiles=5,            # d0 opening cohort: front-loads cash before anything else pays
    melon_last_day=2,         # opening window; d11-13 = wave 2, d24+ = wave 3 (block_price cap)
    melon_wave_floor=2.5,     # wave-2/3 buying floor: MELON base is 250, so 2.5x = $625

    sheep_cap=0,              # total sheep; >0 caps the flock. The post-mortem's cap=1 came
                              # from one game where WE crashed wool by dumping 64 units; on
                              # the panel wool is 19.5% of revenue ($21.9k/ep) uncapped, and
                              # capping it cost $14k mean (V4 bundle vs e3). Leave 0.
    open_feed=18,             # wheat bought on day 0 to bridge to the first grown harvest
    seed_cash0=0.30,
    seed_cash=0.55,
    feed_lo=1.2,              # buy feed below this many days per mouth...
    feed_hi=2.0,              # ...and sell surplus only above this. The gap stops churn.
    land_empty=8,
    opp_weight=0.35,
    travel=2.0,               # distance discount in job scoring; higher = more local.
                              # One op OR one move per unit per turn means travel is the whole
                              # efficiency story: an animal cluster on the shed-access tiles
                              # lets one unit PICKUP, FEED, CARE, COLLECT and HARVEST without
                              # ever leaving the tile, because shed ops ignore what is built on
                              # the tile they are performed from.
    land_margin=1.60,
    wheat_tiles_max=20,       # grown feed; the rest is bought
    fert_reserve=6,           # doses held back from sale for the crop bonus

    stagger=0.40,             # max share of a crop's acreage target planted in one day
    labour_slack=0.75,        # planted load may exceed the roster's daily visits by this much
    visits_per_unit=9.0,

    sell_aggr=1.6,           # multiple of the town's per-turn drain we push each turn
    shed_panic=70,            # above this the reserve price comes off; shed cap is 100
    endgame_day=27,           # from here, clear everything
    land_day=2,
    land_stop=9,
    crop_cap=45,
    stock_ahead=3,            # animals allowed to wait in the shed ahead of their structures
    sheep_day=6,              # wool is only worth a tile once the shop draw is visible
    hold_px=0.80,          # do not sell below this multiple of base unless the shed is filling               # earliest quadrant purchase
)

RESCUE, FEED_T, HARV_T, GROW_T, BUILD_T, PLANT_T, HAUL_T, IDLE_T = 8, 7, 6, 5, 4, 3, 2, 1


def _g(d, k, default=None):
    if isinstance(d, dict):
        return d.get(k, default)
    return getattr(d, k, default)


class Policy:
    def __init__(self):
        import os as _os, json as _json
        _ov = _os.environ.get("KAG_OVERRIDE")
        if _ov:
            try:
                P.update(_json.loads(_ov))
            except Exception:
                pass
        self.plan_day = -1
        self.assign = {}
        self.sold = {}
        self.bought = {}
        self.cum_drain = {}
        self.targets = {}
        self.planted_today = {}
        self.last_step = -1
        self.hand_count = 0

    # ----------------------------------------------------------------- entry point
    def act(self, obs, config=None):
        try:
            return self._act(obs, config)
        except Exception:
            return self._pass(obs)

    @staticmethod
    def _pass(obs):
        try:
            me = (_g(obs, "farms") or [])[_g(obs, "player", 0)]
            n = len(_g(me, "hands") or [])
        except Exception:
            n = 0
        return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}

    # ----------------------------------------------------------------- main
    def _act(self, obs, config=None):
        farms = _g(obs, "farms") or []
        me = _g(obs, "player", 0)
        farm = farms[me]
        priv = _g(obs, "private") or {}
        market = _g(obs, "market") or {}
        town = _g(obs, "town") or {}

        self.day = int(_g(obs, "day", 0))
        self.hour = int(_g(obs, "hour", 0))
        self.step = self.day * TPD + self.hour
        self.shops = list(_g(town, "unlocked_shops") or [])
        self.inv = dict(_g(market, "inventory") or {})
        self.px = dict(_g(market, "prices") or {})
        self.shed = dict(_g(priv, "shed") or {})
        self.seeds = dict(_g(priv, "seeds") or {})
        self.invs = list(_g(priv, "inventories") or [{}])
        self.tiles = _g(farm, "tiles")
        self.money = float(_g(farm, "money", 0.0))
        self.unlocked = set(_g(farm, "unlocked_quadrants") or ["NW"])
        self.hands = list(_g(farm, "hands") or [])
        self.hires_today = int(_g(farm, "hires_today", 0))
        self.nunits = 1 + len(self.hands)
        self.pos = [tuple(_g(farm, "farmer") or (4, 4))] + [tuple(h) for h in self.hands]

        self._scan()
        self._track_market()

        if self.day != self.plan_day:
            self.plan_day = self.day
            self.assign = {}
            self.planted_today = {}
            self._plan()

        jobs = self._jobs()
        ops = self._assign(jobs)
        orders = self._market()

        return {"farmer": ops[0], "hands": ops[1:self.nunits], "market": orders[:MAX_ORDERS]}

    # ----------------------------------------------------------------- board scan
    def _scan(self):
        self.empty = []
        self.weeds = []
        self.plants = []          # (x, y, tile)
        self.animals = []         # (x, y, tile)
        self.structs = []         # empty structures (x, y, tile)
        self.standing = {}        # good -> units still to come off the board
        self.n_mouths = 0
        self.crop_tiles = {}

        for y in range(BOARD):
            row = self.tiles[y]
            for x in range(BOARD):
                t = row[x]
                if t == "LOCKED":
                    continue
                if t is None:
                    self.empty.append((x, y))
                    continue
                if not isinstance(t, dict):
                    continue
                kind = t.get("kind")
                if kind == "WEED":
                    self.weeds.append((x, y))
                elif kind == "PLANT":
                    crop = t["crop"]
                    self.plants.append((x, y, t))
                    self.crop_tiles[crop] = self.crop_tiles.get(crop, 0) + 1
                    age = self.day - t["planted_day"]
                    left = self._tile_units_left(crop, age, t)
                    self.standing[crop] = self.standing.get(crop, 0.0) + left
                elif "animal" in t:
                    self.animals.append((x, y, t))
                    self.n_mouths += 1
                    a = t["animal"]
                    g = PRODUCT_OF[a]
                    self.standing[g] = (self.standing.get(g, 0.0)
                                        + t.get("yield_units", 0)
                                        + animal_units(a, t.get("placed_day", self.day), self.day))
                elif kind in ("PASTURE", "COOP"):
                    self.structs.append((x, y, t))

        for g, n in self.shed.items():
            if g in MARKET and n:
                self.standing[g] = self.standing.get(g, 0.0) + n

    def _tile_units_left(self, crop, age, tile):
        c = CROPS[crop]
        cur = tile.get("yield_units", 0)
        if c["ongoing"]:
            done = 0 if age < c["first"] else (age - c["first"]) // c["interval"] + 1
            remaining = max(0, c["maxy"] - done)
            horizon = (SEASON - 1 - self.day) // max(1, c["interval"])
            return cur + min(remaining, max(0, horizon)) * 1.6
        gains = [a for a in range((c["maxd"] + 1) // 2, c["maxd"] + 1) if a > age]
        return min(c["maxy"], cur + len(gains) * 1.4)

    # ----------------------------------------------------------------- opponent tracking
    def _track_market(self):
        """Estimate the opponent's cumulative supply per good.

        total_supply(both) = (inv - I0) + cumulative town drain. Ours is measured directly from
        our own fills, so the residual is theirs. Used only to shrink our own budget, so a noisy
        estimate is safe: it errs toward producing less of a contested good.
        """
        if self.step != self.last_step:
            self.last_step = self.step
            if self.step % 4 == 0:
                for s in self.shops:
                    for g, n in SHOPS and self._shop_units(s).items():
                        self.cum_drain[g] = self.cum_drain.get(g, 0) + n
            if self.step % TPD == 0:
                for g in PRODUCTS:
                    if g != "FERTILIZER":
                        self.cum_drain[g] = self.cum_drain.get(g, 0) + 1

    @staticmethod
    def _shop_units(name):
        b = SHOPS.get(name) or []
        m = 2 if len(b) == 1 else 1
        return {g: m for g in b}

    def _opp_supply(self, good):
        total = (self.inv.get(good, 10000) - 10000) + self.cum_drain.get(good, 0)
        mine = self.sold.get(good, 0) - self.bought.get(good, 0)
        return max(0.0, total - mine)

    def _opp_projection(self, good):
        """Project the opponent's remaining supply at their observed rate so far."""
        if self.day < 4:
            return 0.0
        rate = self._opp_supply(good) / float(max(1, self.day))
        return rate * max(0, SEASON - self.day)

    # ----------------------------------------------------------------- daily plan
    def _budget(self, good):
        """Units of `good` we may still add to the market this season."""
        pot = remaining_drain(good, self.day, self.shops)
        k = P["kappa"].get(good, 0.7)
        glut = max(0.0, self.inv.get(good, 10000) - 10000)
        return (k * pot
                - self.standing.get(good, 0.0)
                - P["opp_weight"] * self._opp_projection(good)
                - 2.0 * glut)

    def _season_units(self, crop):
        """Units one tile of `crop` yields between now and the end of the season.

        A carrot tile runs seven cycles in a season and a strawberry tile runs one; dividing a
        season pot by a single cycle's yield asks for seven times the carrot acreage the town
        can absorb, which is exactly the failure this corrects.
        """
        per = crop_units(crop, self.day, fert=(crop in ("STRAWBERRY", "TOMATO")))
        if per <= 0:
            return 0.0
        cycles = max(1.0, (SEASON - self.day) / float(crop_cycle(crop)))
        return per * cycles

    def _acceptable(self, good, n_units):
        """Does the block our next tile/head would add still clear the price floor?"""
        head = self.inv.get(good, 10000) - int(round(0.45 * remaining_drain(good, self.day, self.shops)))
        head = max(1, head)
        return block_price(good, head, max(1, int(n_units))) >= P["min_px"].get(good, 0.9) * base_of(good)

    def _plan(self):
        # `_plan` runs at dawn, when the engine has just cleared the roster, so the live
        # hand count is always 0 here. Size the plan off the roster we will hire today.
        self.roster = 1 + P["hands"]
        self.capacity = self.roster * P["visits_per_unit"]
        cap = self.capacity * P["labour_slack"]

        n_tiles = sum(1 for y in range(BOARD) for x in range(BOARD)
                      if quadrant_of(x, y) in self.unlocked)
        land_room = max(0, n_tiles - len(self.animals) - len(self.structs)
                         - self.crop_tiles.get("__struct__", 0))

        # ---- per-unit value/visit for every candidate asset, animals and crops alike.
        # Labour and land are ONE shared budget: an animal on a far corner of the board costs
        # the same travel as a crop tile there, and a herd sized off its season pot alone (as
        # V3's first cut did) reliably wants 25+ head, which floods the board, pushes new
        # structures into 8-tile-distant corners, and starves the crop board of both room and
        # visits. The knapsack below buys the single best-value unit repeatedly, whichever
        # asset it belongs to, until labour or land runs out -- so a mediocre 9th cow loses a
        # slot to a good wheat tile instead of both existing at half efficiency.
        self.rank = {}
        cap_units = {}
        visit_cost = {}
        for crop in CROPS:
            if crop == "MELON":
                continue
            per = self._season_units(crop)          # season-total units, one tile
            if per <= 0:
                cap_units[("crop", crop)] = 0
                continue
            budget = self._budget(crop)
            cap_units[("crop", crop)] = max(0, int(budget // per)) if self._acceptable(
                crop, crop_units(crop, self.day)) else 0
            visit_cost[("crop", crop)] = crop_daily_visits(crop)
            px = self.px.get(crop, base_of(crop))
            # `crop_daily_visits` is already amortised per day over one cycle, so multiplying
            # it by the remaining days -- not by one cycle -- gives the season-total visit
            # cost, matching how `per` (season-total units) and the animal rank below are both
            # normalised. Dividing season-total value by a single cycle's visits (the previous
            # version) over-ranked every short-cycle crop by its cycle count -- carrot repeats
            # roughly seven times a season, so it was valued 7x, which is why carrot and wheat
            # crowded livestock out of the knapsack entirely.
            visits_total = crop_daily_visits(crop) * max(1, SEASON - self.day)
            # A one-time crop needs a fresh seed every cycle it replants; an ongoing crop is
            # seeded once for its whole run. `_season_units`'s own cycle count keeps this
            # consistent with the units figure above.
            cycles = max(1.0, (SEASON - self.day) / float(crop_cycle(crop)))
            seed_cost = CROPS[crop]["seed"] * (cycles if not CROPS[crop]["ongoing"] else 1.0)
            net = per * px - seed_cost
            self.rank[("crop", crop)] = net / max(1.0, visits_total)
        for a in ANIMALS:
            g = PRODUCT_OF[a]
            per = animal_units(a, self.day, self.day)
            if per <= 0 or (a == "SHEEP" and self.day < P["sheep_day"]):
                cap_units[("animal", a)] = 0
                continue
            if a == "SHEEP" and P["sheep_cap"] > 0:
                cap_units[("animal", a)] = P["sheep_cap"]
                continue
            budget = self._budget(g)
            cap_units[("animal", a)] = max(0, int(budget // per)) if self._acceptable(
                g, min(per, 12)) else 0
            visit_cost[("animal", a)] = animal_daily_visits(a)
            px = self.px.get(g, base_of(g))
            visits = animal_daily_visits(a) * max(1, SEASON - self.day)
            fert = max(0, SEASON - self.day - 1) * 0.8 * self.px.get("FERTILIZER", 100)
            net = (per * px + fert - ANIMALS[a]["cost"]
                   - max(0, SEASON - self.day) * self.px.get("WHEAT", 30))
            self.rank[("animal", a)] = net / max(1.0, visits)

        # ---- knapsack: repeatedly buy the best remaining $/visit unit
        have = {}
        for a in ANIMALS:
            have[("animal", a)] = sum(1 for _, _, t in self.animals if t.get("animal") == a) \
                + self.shed.get(a, 0)
        for c in CROPS:
            if c != "MELON":
                have[("crop", c)] = self.crop_tiles.get(c, 0)
        want = dict(have)
        spent_visits = sum(animal_daily_visits(t.get("animal")) for _, _, t in self.animals)
        spent_visits += sum(crop_daily_visits(t["crop"]) for _, _, t in self.plants)
        spent_land = len(self.animals) + len(self.structs) + len(self.plants)
        remaining_visits = max(0.0, cap - spent_visits)
        remaining_land = max(0, n_tiles - spent_land)
        keys = [k for k in cap_units if cap_units[k] > 0 and self.rank.get(k, -1e9) > 0]
        keys.sort(key=lambda k: -self.rank[k])
        # A crude but effective knapsack: pass over the ranked list repeatedly, taking one unit
        # of the best-still-affordable asset each pass, until nothing more fits.
        progress = True
        while progress and (remaining_visits > 0.05 and remaining_land > 0):
            progress = False
            for k in keys:
                if want[k] >= have[k] + cap_units[k]:
                    continue
                vc = visit_cost[k]
                if vc > remaining_visits + 1e-6 or remaining_land <= 0:
                    continue
                want[k] += 1
                remaining_visits -= vc
                remaining_land -= 1
                progress = True
                if remaining_visits <= 0.05 or remaining_land <= 0:
                    break

        want_animals = {a: want.get(("animal", a), 0) for a in ANIMALS}
        want_crop = {c: want.get(("crop", c), 0) for c in CROPS if c != "MELON"}

        # Melon is wave-only and outside the knapsack: its pot (30 units/season) is tiny, so
        # value = selling each wave's head units into a thin market before the next supply
        # lands. Wave 1 is the d0 opening cohort; waves 2/3 (d11-13, d24+) are gated on the
        # live price being well above base, so we only re-enter when the town is hungry.
        want_crop["MELON"] = P["melon_tiles"] if self.day <= P["melon_last_day"] else (
            P["melon_tiles"]
            if self.day in (11, 12, 13, 24, 25)
            and self.px.get("MELON", 250) >= P["melon_wave_floor"] * 250
            else 0)

        # MELON has no rank entry (it is skipped in the loops above), but the placement loop
        # and the seed ladder both iterate `rank` -- give it one so the ladder can see it.
        if want_crop["MELON"]:
            self.rank[("crop", "MELON")] = 1e6      # ordered first, gated by want/cash below
        else:
            self.rank.pop(("crop", "MELON"), None)

        # wheat doubles as feed; keep a floor of grown feed regardless of the knapsack outcome
        mouths = self.n_mouths + sum(self.shed.get(a, 0) for a in ANIMALS)
        self.mouths = mouths
        self.feed_lo = int(mouths * P["feed_lo"]) + 3
        self.feed_hi = int(mouths * P["feed_hi"]) + 12
        feed_tiles = int(min(P["wheat_tiles_max"], mouths * 1.1))
        want_crop["WHEAT"] = max(want_crop.get("WHEAT", 0), min(feed_tiles, land_room))

        self.want_animals = want_animals
        self.want_crop = want_crop

        # ---- labour ceiling: how much standing work the roster can actually service today
        load = sum(animal_daily_visits(t.get("animal")) for _, _, t in self.animals)
        load += sum(crop_daily_visits(t["crop"]) for _, _, t in self.plants)
        self.load = load
        self.headroom = cap - load

    # ----------------------------------------------------------------- job list
    def _jobs(self):
        jobs = []
        add = jobs.append
        endgame = self.day >= P["endgame_day"]
        last_day = self.day >= SEASON - 1
        fert_px = self.px.get("FERTILIZER", 100)
        have_fert = self.shed.get("FERTILIZER", 0)

        # ---------- animals
        for x, y, t in self.animals:
            a = t["animal"]
            spec = ANIMALS[a]
            g = PRODUCT_OF[a]
            gpx = self.px.get(g, base_of(g))
            units = t.get("yield_units", 0)
            age = self.day - t.get("placed_day", self.day)
            prod_today = age >= spec["first"] and (age - spec["first"]) % spec["interval"] == 0

            if not t.get("fed_today") and not last_day:
                due = t.get("consecutive_unfed", 0) >= 1
                # Feeding is what keeps the care bonus alive AND what stops the animal walking
                # off the board, so it outranks nearly everything.
                add(dict(pos=(x, y), op=["FEED"], need="WHEAT",
                         tier=RESCUE if due else FEED_T,
                         value=(3000.0 if due else 400.0) + gpx))
            if not t.get("cared_today") and not last_day and t.get("fed_today") is not None:
                add(dict(pos=(x, y), op=["CARE"], tier=GROW_T,
                         value=gpx * min(spec["maxh"] - 1, 1) + 40.0))
            if units > 0 and (endgame or prod_today or units >= spec["maxh"] - 1):
                add(dict(pos=(x, y), op=["HARVEST"], tier=HARV_T, value=units * gpx))
            if t.get("fertilizer_available") and not last_day:
                add(dict(pos=(x, y), op=["COLLECT_FERTILIZER"], tier=GROW_T, value=fert_px * 0.9))

        # ---------- livestock in transit: PICKUP at the shed, then PLACE on a structure.
        # Held as two independent single-op jobs rather than one chained job, because the job
        # list is rebuilt every turn and a chained job cannot survive that rebuild -- the
        # previous build looped PICKUP forever and never placed a single animal.
        free_slots = {}
        for x, y, t in self.structs:
            free_slots.setdefault(t.get("kind"), []).append((x, y))
        for k in free_slots:
            free_slots[k].sort(key=lambda p: dist(p, nearest_shed(p)))
        claimed = set()
        for u in range(self.nunits):
            inv = self.invs[u] if u < len(self.invs) else {}
            for a in ANIMALS:
                if inv.get(a, 0) <= 0:
                    continue
                slots = [p for p in free_slots.get(ANIMALS[a]["struct"], []) if p not in claimed]
                if not slots:
                    continue
                tgt = min(slots, key=lambda p: dist(self.pos[u], p))
                claimed.add(tgt)
                add(dict(pos=tgt, op=["PLACE", a], tier=RESCUE, value=4000.0, unit=u))
        for a in ANIMALS:
            held = self.shed.get(a, 0)
            if held <= 0:
                continue
            slots = [p for p in free_slots.get(ANIMALS[a]["struct"], []) if p not in claimed]
            for _ in range(min(held, len(slots))):
                add(dict(pos=(4, 4), op=["PICKUP", a, 1], tier=BUILD_T, value=2600.0,
                         anyshed=True))

        # ---------- plants
        for x, y, t in self.plants:
            crop = t["crop"]
            c = CROPS[crop]
            age = self.day - t["planted_day"]
            cpx = self.px.get(crop, base_of(crop))
            units = t.get("yield_units", 0)
            watered = t.get("watered_today")
            dry = t.get("consecutive_unwatered", 0)

            if not watered:
                gain = is_gain_age(crop, age)
                if dry >= 1:
                    add(dict(pos=(x, y), op=["WATER"], tier=RESCUE,
                             value=1200.0 + (cpx * 2 if gain else 0)))
                elif gain:
                    fertd = t.get("fertilized_until_day", -1) >= self.day
                    add(dict(pos=(x, y), op=["WATER"], tier=GROW_T,
                             value=cpx * (2 if fertd else 1) + 15.0))
                elif age in water_ages(crop):
                    add(dict(pos=(x, y), op=["WATER"], tier=GROW_T, value=60.0))

            if units > 0 and age >= c["first"]:
                # Ongoing crops must be emptied between gain days or `max_yield` clips the
                # fertilizer bonus; one-time crops start bleeding units once past max_yield_day.
                ripe = (units >= c["maxy"]
                        or (c["ongoing"] and units >= 2)
                        or (not c["ongoing"] and age >= c["maxd"])
                        or endgame)
                if ripe:
                    add(dict(pos=(x, y), op=["HARVEST"], tier=HARV_T, value=units * cpx + 25.0))

            if (c["ongoing"] and have_fert > 0 and not endgame
                    and t.get("fertilized_until_day", -1) < self.day):
                nxt = self._next_gain_age(crop, age)
                if nxt is not None and nxt - age <= 2 and self.day + (nxt - age) < SEASON:
                    covered = sum(1 for k in range(0, 3)
                                  if is_gain_age(crop, age + k) and self.day + k < SEASON)
                    if covered >= 1:
                        add(dict(pos=(x, y), op=["FERTILIZE"], need="FERTILIZER", tier=GROW_T,
                                 value=covered * cpx - fert_px))

        # ---------- new tiles
        if not endgame:
            jobs += self._placement_jobs()

        # ---------- weeds
        if self.weeds and not last_day:
            want_space = len(self.empty) < 6
            for (x, y) in self.weeds[:8]:
                add(dict(pos=(x, y), op=["DIG"], tier=IDLE_T,
                         value=45.0 if want_space else 12.0))

        # ---------- haul produce to the shed so it can be sold today
        for i in range(self.nunits):
            inv = self.invs[i] if i < len(self.invs) else {}
            carried = sum(v for k, v in inv.items() if k in MARKET and k != "WHEAT")
            if carried >= (2 if last_day else 9):
                s = nearest_shed(self.pos[i])
                add(dict(pos=s, op=["DROP"], tier=HAUL_T if not last_day else HARV_T,
                         value=carried * 12.0 + (400.0 if last_day else 0.0), unit=i))
        return jobs

    @staticmethod
    def _next_gain_age(crop, age):
        c = CROPS[crop]
        if not c["ongoing"]:
            lo = (c["maxd"] + 1) // 2
            if age < lo:
                return lo
            return age if age <= c["maxd"] else None
        for i in range(c["maxy"]):
            a = c["first"] + i * c["interval"]
            if a >= age:
                return a
        return None

    def _placement_jobs(self):
        """Plant / build on empty tiles, rate-limited so cohorts never synchronise."""
        out = []
        if not self.empty:
            return out
        if self.headroom <= 0:
            return out

        shed_pts = shed_tiles()
        empties = sorted(self.empty, key=lambda p: min(dist(p, s) for s in shed_pts))

        # structures first, and closest to the shed: they are visited 3-4x a day
        # A structure is a tile spent on nothing until an animal stands in it, so build only
        # slightly ahead of what the bank can actually stock.
        need_struct = {}
        for a, n in self.want_animals.items():
            kind = ANIMALS[a]["struct"]
            live = sum(1 for _, _, t in self.animals if t.get("animal") == a)
            held = self.shed.get(a, 0)
            empty_slots = sum(1 for _, _, t in self.structs if t.get("kind") == kind)
            afford = int(self.money // ANIMALS[a]["cost"]) + held
            room = min(n - live, live + held + afford + 1) - empty_slots - held
            need_struct[kind] = max(need_struct.get(kind, 0), room)
        # Seed-466488175: budgeting structures out of CROP labour headroom deadlocked the herd
        # -- once crops filled the roster (headroom ~0 from d16), `min(n, 0, 4)` built nothing
        # and two cows sat in the shed for the whole rest of the season. Structures are one
        # BUILD op each, so gate them on empty tiles + cash instead: build if the board has
        # room and the bank can stock what the structure would hold.
        budget = max(1, int(self.headroom // 3.5)) if len(self.empty) > P["land_empty"] else 0
        for kind, n in need_struct.items():
            if n <= 0:
                continue
            op = "BUILD_PASTURE" if kind == "PASTURE" else "BUILD_COOP"
            for p in empties[:min(n, max(0, budget), 4)]:
                out.append(dict(pos=p, op=[op], tier=BUILD_T, value=900.0))
                empties = [e for e in empties if e != p]

        # crops, best value per visit first, staggered
        ranked = sorted(((v, k) for k, v in self.rank.items() if k[0] == "crop"), reverse=True)
        for _, key in ranked:
            crop = key[1]
            want = self.want_crop.get(crop, 0)
            have = self.crop_tiles.get(crop, 0)
            room = want - have
            if room <= 0:
                continue
            cap_day = max(1, int(round(want * P["stagger"])))
            if crop == "MELON":
                cap_day = room
            done = self.planted_today.get(crop, 0)
            n = min(room, cap_day - done, self.seeds.get(crop, 0),
                    int(max(0, self.headroom) // max(0.35, crop_daily_visits(crop))))
            if n <= 0:
                continue
            for p in empties[:n]:
                out.append(dict(pos=p, op=["PLANT", crop], tier=PLANT_T,
                                value=self.rank[key] * 6.0, crop=crop))
            empties = [e for e in empties if e not in set(empties[:n])]
        return out

    # ----------------------------------------------------------------- assignment
    def _assign(self, jobs):
        ops = [["PASS"] for _ in range(max(1, self.nunits))]
        if not jobs:
            self.assign = {}
            return self._fill_idle(ops)

        # sticky: keep an assignment whose job still exists
        live = {}
        for j in jobs:
            live.setdefault((j["pos"], tuple(j["op"])), j)
        keep = {}
        for u, j in self.assign.items():
            if u >= self.nunits:
                continue
            k = (j["pos"], tuple(j["op"]))
            if k in live and not j.get("done"):
                keep[u] = live.pop(k)
        free = [u for u in range(self.nunits) if u not in keep]

        pool = list(live.values())
        pinned = [j for j in pool if j.get("unit") is not None]
        for j in pinned:
            u = j["unit"]
            if u in free:
                keep[u] = j
                free.remove(u)
                pool.remove(j)
        pool = [j for j in pool if j.get("unit") is None]
        pool.sort(key=lambda j: (-j["tier"], -j["value"]))
        # Rescue-tier work is worth a long walk; everything else is scored from the unit's own
        # position so a unit keeps working the patch it is standing in.
        for u in sorted(free):
            if not pool:
                break
            best, best_s = None, -1e18
            for j in pool:
                d = self._cost(u, j)
                sc = (j["tier"] * 1e6 + j["value"]) / (1.0 + P["travel"] * d)
                if sc > best_s:
                    best, best_s = j, sc
            keep[u] = best
            pool.remove(best)
        free = [u for u in range(self.nunits) if u not in keep]

        self.assign = keep
        plants_this_turn = {}
        for u in range(self.nunits):
            j = keep.get(u)
            if j is None:
                continue
            op = self._execute(u, j, plants_this_turn)
            ops[u] = op
        return self._fill_idle(ops)

    def _cost(self, u, j):
        p = self.pos[u]
        d = dist(p, j["pos"])
        if j.get("need"):
            inv = self.invs[u] if u < len(self.invs) else {}
            if inv.get(j["need"], 0) <= 0:
                s = nearest_shed(p)
                d = dist(p, s) + dist(s, j["pos"])
        return d

    def _execute(self, u, j, plants_this_turn):
        p = self.pos[u]
        inv = self.invs[u] if u < len(self.invs) else {}
        need = j.get("need")

        if need and inv.get(need, 0) <= 0:
            s = nearest_shed(p)
            if p == s:
                have = self.shed.get(need, 0)
                if have <= 0:
                    return ["PASS"]
                n = min(have, 6 if need == "WHEAT" else 3)
                self.shed[need] = have - n
                return ["PICKUP", need, n]
            return self._step(p, s)

        target = tuple(j["pos"])
        if j.get("anyshed"):
            target = nearest_shed(p)
        if p != target:
            return self._step(p, target)

        op = list(j["op"])
        if op[0] == "PLANT":
            crop = op[1]
            n = plants_this_turn.get(crop, 0) + 1
            # The engine drops EVERY plant order for a crop if the turn's total exceeds seeds.
            if n > self.seeds.get(crop, 0):
                return ["PASS"]
            plants_this_turn[crop] = n
            self.planted_today[crop] = self.planted_today.get(crop, 0) + 1
        if op[0] == "PICKUP" and op[1] in ANIMALS:
            have = self.shed.get(op[1], 0)
            if have <= 0:
                return ["PASS"]
            self.shed[op[1]] = have - 1
        j["done"] = True
        return op

    def _step(self, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if abs(dx) >= abs(dy):
            if dx: return ["EAST"] if dx > 0 else ["WEST"]
            if dy: return ["SOUTH"] if dy > 0 else ["NORTH"]
        else:
            if dy: return ["SOUTH"] if dy > 0 else ["NORTH"]
            if dx: return ["EAST"] if dx > 0 else ["WEST"]
        return ["PASS"]

    def _fill_idle(self, ops):
        """No unit ever passes while it can carry, dig, or pre-position."""
        for u in range(self.nunits):
            if ops[u][0] != "PASS":
                continue
            p = self.pos[u]
            inv = self.invs[u] if u < len(self.invs) else {}
            carried = sum(v for k, v in inv.items() if k in MARKET)
            if carried:
                s = nearest_shed(p)
                ops[u] = ["DROP"] if p == s else self._step(p, s)
                continue
            if self.weeds:
                tgt = min(self.weeds, key=lambda w: dist(p, w))
                ops[u] = ["DIG"] if p == tgt else self._step(p, tgt)
                continue
            dry = [(x, y) for x, y, t in self.plants
                   if not t.get("watered_today") and t.get("consecutive_unwatered", 0) >= 1]
            if dry:
                tgt = min(dry, key=lambda w: dist(p, w))
                ops[u] = ["WATER"] if p == tgt else self._step(p, tgt)
                continue
            if self.animals:
                tgt = min((a[:2] for a in self.animals), key=lambda w: dist(p, w))
                if p != tgt:
                    ops[u] = self._step(p, tgt)
                    continue
            s = nearest_shed(p)
            if p != s:
                ops[u] = self._step(p, s)
        return ops

    # ----------------------------------------------------------------- market
    def _market(self):
        """Orders under a strict cash ladder.

        Priority is hires -> feed -> livestock -> seed -> land, and the ladder is walked with a
        running cash figure because the engine fills orders in the order they are submitted. The
        previous build's failure mode was the reverse: it bought seed for the whole season on
        day 0, ended the day with $14, and could then afford neither hands nor animals for the
        rest of the game.
        """
        out = []
        endgame = self.day >= P["endgame_day"]
        last = self.day >= SEASON - 1
        fill = sum(self.shed.values())
        cash = self.money

        sells = self._sell_orders(endgame, last, fill)
        # Selling first funds everything below it and costs nothing.
        take = len(sells) if (endgame or fill >= P["shed_panic"]) else min(4, len(sells))
        out += sells[:take]
        cash += sum(self.px.get(o[1], 0) * o[2] for o in sells[:take]) * 0.9

        if not last and self.hour <= 3 and len(out) < MAX_ORDERS:
            target = P["hands"]
            while target > 0 and _hire_total(self.hires_today, target) > cash * P["hire_cash_frac"]:
                target -= 1
            n = max(0, min(target - len(self.hands), MAX_ORDERS - len(out)))
            if n:
                cash -= _hire_total(self.hires_today, len(self.hands) + n)
                out += [["HIRE"]] * n

        if not last:
            for order, cost in self._buy_ladder(cash, endgame, fill):
                if len(out) >= MAX_ORDERS:
                    break
                if cost > cash:
                    continue
                cash -= cost
                out.append(order)

        if len(out) < MAX_ORDERS and take < len(sells):
            out += sells[take:MAX_ORDERS - len(out)]
        return out[:MAX_ORDERS]

    def _buy_ladder(self, cash, endgame, fill):
        """(order, expected_cost) pairs in strict priority order."""
        out = []
        room_shed = SHED_CAP - fill
        mouths = self.n_mouths + sum(self.shed.get(a, 0) for a in ANIMALS)
        wheat_px = max(1.0, self.px.get("WHEAT", 25))

        # 0. melon wave, BEFORE the rest of the ladder. Hires, feed and livestock all outrank a
        # seed economically, but they can be bought an hour later; a melon cohort that misses
        # its 3-day window is worth zero (seed-466488175: the d0/d1 wallet was gone by the time
        # the seed section ran, so no melon seed was ever bought all game). Cap the spend at
        # the same cash fraction the seed ladder uses.
        if not endgame:
            mwant = self.want_crop.get("MELON", 0)
            mneed = mwant - self.seeds.get("MELON", 0)
            if mneed > 0:
                frac = P["seed_cash0"] if self.day <= 1 else P["seed_cash"]
                mcost = CROPS["MELON"]["seed"]
                n = int(min(mneed, cash * frac // mcost))
                if n > 0:
                    out.append((["BUY_SEED", "MELON", n], n * mcost))
                    cash -= n * mcost

        # 1. feed. An unfed animal leaves the board and takes its whole remaining season with it.
        have_wheat = self.shed.get("WHEAT", 0)
        if self.day <= 1 and have_wheat < P["open_feed"]:
            n = int(min(P["open_feed"] - have_wheat, cash * 0.22 // wheat_px))
            if n > 0:
                out.append((["BUY_PRODUCT", "WHEAT", n], n * wheat_px * 1.1))
        if mouths and room_shed > 4 and not endgame and have_wheat < getattr(self, "feed_lo", 6):
            want = getattr(self, "feed_hi", 12) - have_wheat
            want = int(min(want, room_shed - 4, 20, cash * 0.5 // wheat_px))
            if want > 0:
                out.append((["BUY_PRODUCT", "WHEAT", want], want * wheat_px * 1.15))

        # 2. livestock, best rank first, but never more mouths than the shed can feed.
        fed_ok = self.shed.get("WHEAT", 0) >= min(8, max(2, mouths)) or self.day == 0
        if not endgame and room_shed > 2 and self.day <= SEASON - 10 and fed_ok:
            # Always leave the day's wages and a few days of feed on the table.
            reserve = P["hire_reserve"] + 25 * mouths
            for a in sorted(ANIMALS, key=lambda k: -self.rank.get(("animal", k), -1e9)):
                n = self.want_animals.get(a, 0)
                live = sum(1 for _, _, t in self.animals if t.get("animal") == a)
                held = self.shed.get(a, 0)
                struct = ANIMALS[a]["struct"]
                slots = sum(1 for _, _, t in self.structs if t.get("kind") == struct)
                if self.rank.get(("animal", a), 0) <= 0 or live + held >= n:
                    continue
                cost = ANIMALS[a]["cost"]
                k = int(max(0.0, cash - reserve) // cost)
                k = min(k, n - live - held, max(0, slots + P["stock_ahead"] - held), 5)
                if k > 0:
                    out.append((["BUY_ANIMAL", a, k], k * cost))
                break

        # 3. seed, only for what can actually go in the ground in the next two days.
        seed_cash = max(0.0, cash * (P["seed_cash0"] if self.day <= 1 else P["seed_cash"]))
        ranked = sorted(((v, k[1]) for k, v in self.rank.items() if k[0] == "crop"), reverse=True)
        picks = 0
        for _v, crop in ranked:
            if picks >= 3 or seed_cash <= 0:
                break
            want = self.want_crop.get(crop, 0) - self.crop_tiles.get(crop, 0)
            if want <= 0:
                continue
            if crop == "MELON":
                # Bought at ladder slot 0 (a wave that misses its window is worth zero);
                # `seeds` on hand stops a re-buy here.
                continue
            per_day = max(1, int(round(self.want_crop.get(crop, 0) * P["stagger"])))
            need = min(want, per_day * 2, len(self.empty) + 4) - self.seeds.get(crop, 0)
            if need <= 0:
                continue
            cost = CROPS[crop]["seed"]
            n = int(min(need, seed_cash // cost))
            if n > 0:
                out.append((["BUY_SEED", crop, n], n * cost))
                seed_cash -= n * cost
                picks += 1

        # 4. land, only when the board is genuinely full and the roster can work more of it.
        extra = len(self.unlocked) - 1
        if extra < 3 and self.day >= P["land_day"] and self.day <= SEASON - P["land_stop"]:
            price = LAND_PRICES[extra]
            tight = len(self.empty) <= P["land_empty"]
            if cash > price * P["land_margin"] and (tight or extra == 0):
                out.append((["BUY_LAND"], price))
        return out

    def _sell_orders(self, endgame, last, shed_fill):
        out = []
        for g in sorted(MARKET, key=lambda k: -self.px.get(k, 0) * self.shed.get(k, 0)):
            have = self.shed.get(g, 0)
            if have <= 0:
                continue
            if g == "WHEAT" and not endgame:
                # Dead band: sell only above the high-water mark, buy only below the low one.
                have = have - getattr(self, "feed_hi", 12) if have > getattr(self, "feed_hi", 12) else 0
            if g == "FERTILIZER" and not endgame:
                have -= P["fert_reserve"]
            if have <= 0:
                continue
            px = self.px.get(g, base_of(g))
            panic = shed_fill >= P["shed_panic"]
            # Holding back only pays while the shed has room. Past that the midnight drop
            # discards the overflow, so a bad price beats no sale.
            if not (endgame or panic or have >= 10):
                if px < P["hold_px"] * base_of(g) and g != "MELON":
                    continue
            meter = max(1, int(round(drain_per_day(g, self.shops) / 6.0 * P["sell_aggr"])))
            if g == "FERTILIZER":
                meter = max(meter, 3)           # no town drain at all; only our own curve
            if g == "WOOL" and px < 0.30 * base_of(g):
                meter = max(meter, 8)           # measured crash: drip it out, never a wave
            if have >= 10:
                meter = max(meter, have // 3)
            if endgame:
                meter = max(meter, 14)
            if panic:
                meter = max(meter, max(10, have // 2))
            if last:
                meter = have
            out.append(["SELL", g, int(min(have, meter))])
        return out


def _fib(n):
    a, b = 1, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def _hire_total(already, target):
    """Cost of topping the roster up to `target` given `already` hires today."""
    return sum(_fib(already + k) for k in range(max(0, target - already)))
