"""Sample agents for the local Kaggriculture simulator."""

import random as _random
from engine import OBJECT_TABLE, SHED_TILES

_rng = _random.Random(0)


def agent_pass(obs):
    return {"farmer": ["PASS"], "hands": [], "market": []}


def agent_random(obs):
    me = obs["farms"][obs["player"]]
    moves = ["NORTH", "SOUTH", "EAST", "WEST", "PASS"]
    n_hands = len(me["hands"])
    return {
        "farmer": [_rng.choice(moves)],
        "hands": [[_rng.choice(moves)] for _ in range(n_hands)],
        "market": [],
    }


def agent_starter(obs):
    """Direct port of the official wheat-loop sketch from the knowledge-transfer doc
    (Section 14): buy a wheat seed, plant/water/harvest on repeat, sell what's in
    the shed. Deliberately simple — useful as a baseline, not a strategy."""
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]
    fx, fy = me["farmer"]
    tile = me["tiles"][fy][fx]

    market = []
    if private["seeds"].get("WHEAT", 0) == 0 and me["money"] >= 10:
        market.append(["BUY_SEED", "WHEAT", 1])
    wheat_in_shed = private["shed"].get("WHEAT", 0)
    if wheat_in_shed > 0:
        market.append(["SELL", "WHEAT", wheat_in_shed])

    if tile is None and private["seeds"].get("WHEAT", 0) > 0:
        return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": market}
    if isinstance(tile, dict) and tile.get("kind") == "PLANT":
        crop_age = obs["day"] - tile["planted_day"]
        if crop_age >= 2:
            return {"farmer": ["HARVEST"], "hands": [], "market": market}
        if not tile["watered_today"]:
            return {"farmer": ["WATER"], "hands": [], "market": market}

    return {"farmer": ["PASS"], "hands": [], "market": market}


# ---------------------------------------------------------------------------
# A somewhat smarter heuristic agent: farms a small wheat patch with the main
# farmer, hires a couple of hands once money allows, and sells shed contents
# every turn. This is meant as a step above `starter`, not a finished strategy
# — a good next move is to replace its planning with something that reasons
# about the price curve and labor allocation explicitly.
# ---------------------------------------------------------------------------

def _find_target(me, private, kind_wanted):
    """Find nearest tile matching a simple need, scanning unlocked NW quadrant."""
    tiles = me["tiles"]
    best = None
    best_d = 999
    fx, fy = me["farmer"]
    for y in range(5):
        for x in range(5):
            t = tiles[y][x]
            ok = False
            if kind_wanted == "empty" and t is None:
                ok = True
            elif kind_wanted == "unwatered" and isinstance(t, dict) and t.get("kind") == "PLANT" and not t.get("watered_today"):
                ok = True
            elif kind_wanted == "ready" and isinstance(t, dict) and t.get("kind") == "PLANT" and t.get("yield_units", 0) > 0:
                ok = True
            if ok:
                d = abs(x - fx) + abs(y - fy)
                if d < best_d:
                    best_d, best = d, (x, y)
    return best


def _step_toward(pos, target):
    px, py = pos
    tx, ty = target
    if px < tx:
        return "EAST"
    if px > tx:
        return "WEST"
    if py < ty:
        return "SOUTH"
    if py > ty:
        return "NORTH"
    return None


def _unit_op(me, private, pos):
    x, y = pos
    tile = me["tiles"][y][x]
    ready = _find_target(me, private, "ready")
    if ready and pos == list(ready):
        return ["HARVEST"]
    unwatered = _find_target(me, private, "unwatered")
    if unwatered and pos == list(unwatered):
        return ["WATER"]
    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and not tile.get("watered_today"):
        return ["WATER"]
    if tile is None and private["seeds"].get("WHEAT", 0) > 0:
        return ["PLANT", "WHEAT"]
    if ready:
        mv = _step_toward(pos, ready)
        if mv:
            return [mv]
    if unwatered:
        mv = _step_toward(pos, unwatered)
        if mv:
            return [mv]
    empty = _find_target(me, private, "empty")
    if empty:
        mv = _step_toward(pos, empty)
        if mv:
            return [mv]
    return ["PASS"]


def agent_heuristic(obs):
    player = obs["player"]
    me = obs["farms"][player]
    private = obs["private"]

    market = []
    seeds_have = private["seeds"].get("WHEAT", 0)
    if seeds_have < 3 and me["money"] >= 10:
        market.append(["BUY_SEED", "WHEAT", min(3 - seeds_have, 5)])

    wheat_in_shed = private["shed"].get("WHEAT", 0)
    if wheat_in_shed > 2:
        # keep a couple aside as a rainy-day buffer, sell the rest
        market.append(["SELL", "WHEAT", wheat_in_shed - 2])

    # hire a hand or two once we can comfortably afford it
    if me["money"] >= 200 and me["hires_today"] < 2:
        market.append(["HIRE"])

    farmer_op = _unit_op(me, private, me["farmer"])
    hand_ops = [_unit_op(me, private, h) for h in me["hands"]]

    return {"farmer": farmer_op, "hands": hand_ops, "market": market[:10]}


BUILTIN_AGENTS = {
    "pass": agent_pass,
    "random": agent_random,
    "starter": agent_starter,
    "heuristic": agent_heuristic,
}
