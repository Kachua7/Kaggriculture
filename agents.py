"""Sample agents for the local Kaggriculture simulator.

The three simple ones below are baselines, not strategy -- the shipped agent beats all of them in
576 out of 576 episodes, which means every number in this project has so far been measured against
a punchbag. `agent_self` fixes that: it runs the real policy in seat 1, so the agent is scored
against a peer that competes for the same land, the same hires, and above all the same order book.
That last one is the point. Both farms sell into ONE shared market, and melon's only sink is the
town centre's two units a day *for both players combined*, so an opening that floods it is only
free while the opponent is too weak to want it.
"""

import random as _random
from engine import OBJECT_TABLE, SHED_TILES
from kagfarm.policy import PARAMS as _LIVE_PARAMS

# Snapshot of the on-disk parameters, taken at first import in this process.
#
# This matters for sweeps and is easy to get wrong. `eval.run_one` injects a candidate cell by
# mutating `kagfarm.policy.PARAMS` in place -- and it imports THIS module before doing so, so the
# copy below is the pristine incumbent. A pool worker keeps it for the life of the process because
# `sys.modules` caches this module past the reload of `main`. Net effect: during a self-play sweep
# the candidate moves in seat 0 while the opponent stays pinned to what is committed on disk, which
# is the only comparison that answers "is this change better than what I have".
_BASELINE = dict(_LIVE_PARAMS)

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


def make_self_agent(params=None, pinned=True):
    """A `Policy`-backed opponent, for self-play.

    `params` is an overlay on top of the pinned baseline, so `make_self_agent({"n_animals": 0})`
    gives an opponent that is the shipped agent minus livestock -- handy for asking whether a
    change is *robust* or merely *good against weaklings*.

    Three things this has to get right, all of them ways a self-play harness quietly lies:

      One `Policy` per seat. A `Policy` carries a day of routing plans as mutable state, so a
      shared instance would hand this opponent the other seat's queues and both farms would walk
      the same routes. Keyed by `obs["player"]`.

      Reset between episodes. Worker processes are reused across episodes, so the closure below
      outlives the env. A new episode restarts the day counter, which is the signal `main.agent`
      uses too: `day < plan_day` means rebuild.

      Never raise. A crash in seat 1 does not just cost seat 1 -- it aborts the episode and
      silently deletes a sample from whatever panel is running, biasing the result toward whatever
      the surviving seeds happen to say. Falls back to a well-formed PASS with the right number of
      hands, because a `hands` list of the wrong length can get the entire action rejected.
    """
    from kagfarm.policy import Policy

    over = dict(params or {})
    pols = {}

    def cell():
        """Resolve the opponent's parameters at Policy-construction time, not at import time.

        `pinned=False` has to read `_LIVE_PARAMS` here rather than in the enclosing scope. The
        module-level copy is taken when `BUILTIN_AGENTS` is built, which is before
        `eval.run_one` applies the sweep overlay -- so a copy made up there is the incumbent no
        matter what `pinned` says, and `self_live` silently becomes a second `self`. It did, for
        one measurement, and the tell was two columns of identical numbers.
        """
        base = dict(_BASELINE) if pinned else dict(_LIVE_PARAMS)
        base.update(over)
        return base

    def agent_self(obs):
        try:
            seat = obs.get("player", 0)
            pol = pols.get(seat)
            if pol is None or obs.get("day", 0) < pol.plan_day:
                pol = pols[seat] = Policy(params=cell())
            return pol.act(obs)
        except Exception:
            n = 0
            try:
                n = len((obs["farms"][obs.get("player", 0)].get("hands") or []))
            except Exception:
                pass
            return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}

    return agent_self


BUILTIN_AGENTS = {
    "pass": agent_pass,
    "random": agent_random,
    "starter": agent_starter,
    "heuristic": agent_heuristic,
    # The shipped policy, pinned to committed PARAMS. `--opps self` is the only opponent in this
    # dict that is trying to win, and it is brutal: the mirror match scores a quarter of what the
    # built-ins concede, because both farms drain one shared order book.
    "self": make_self_agent(),
    # Mirrors the CANDIDATE instead of the incumbent, so seat 1 moves with the sweep. `self` asks
    # "is this better than what I ship today"; `self_live` asks "what happens if the whole field
    # adopts it" -- a different question, and the answers came out different for `mix_cap`.
    "self_live": make_self_agent(pinned=False),
    # Ablations, so a self-play result can be attributed. `self_noanimal` is the agent as it stood
    # before today; `self_nohaul` is it before the endgame fix, i.e. the strongest opponent that
    # still throws away its last strawberry cohort.
    "self_noanimal": make_self_agent({"n_animals": 0}),
    "self_nohaul": make_self_agent({"haul_trigger": 999.0, "endgame_days": 2}),
    # A peer that RESTRAINS its melon opening. Needed to fill in the other half of the 2x2 over
    # `mix_cap`, which is the only way to tell a Pareto improvement from a dominated strategy:
    # restraint raises both banks, so it looks like a $25k win until you check whether the flooder
    # still takes the episode. It does. See the matrix in `analysis/melon_matrix.py`.
    "self_mix2": make_self_agent({"mix_cap": 2.0}),
}
