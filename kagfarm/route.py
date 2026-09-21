"""
Routing: turn a pile of tile jobs into one full-day walk per unit.

The reason this file exists at all is a turn-budget argument. A unit gets 24 turns a day and
a tile op costs one of them, so the ceiling on a unit is 24 tile-visits — but only if it never
moves. Every MOVE is a turn that produces nothing. Two units doing nearest-target hill-climbing
across a 10x10 board spend most of the day walking past each other; a unit that walks one
contiguous serpentine run spends exactly one move between consecutive tiles and hits
`(24 - commute + 1) // 2` tiles. At a commute of 5 that is 10 tiles per unit against roughly 4
for naive assignment, and it is the difference between servicing a 100-tile farm with 10 hands
and not being able to service it at all.

So the plan is: sort every job into one boustrophedon order over the board, cut that order into
`k` contiguous runs, and hand one run to each unit. Contiguity is what makes the moves cheap;
the cut points are what balance the day.

Nothing here re-derives a route mid-day. The executor in `policy.py` holds each unit's run as a
queue of absolute (x, y, op) targets and re-reads the unit's real position from the observation
every turn, so a move that was blocked or a plan that was one turn optimistic self-corrects
without a replan.
"""

from __future__ import annotations

from .constants import BOARD_SIZE, SHED_TILES, TURNS_PER_DAY

# Move names as the engine spells them, with the delta each applies.
MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


def manhattan(a, b) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def serpentine_key(pos):
    """Boustrophedon order: left-to-right on even rows, right-to-left on odd ones.

    Consecutive tiles in this order are adjacent *including* across row ends, because a row
    traversed rightwards is followed by the row below traversed leftwards. Over a full grid it
    is a Hamiltonian path, so a contiguous slice of it costs exactly one move per step. Any
    order that sorts plain (y, x) pays 9 moves at every row change instead of 1.
    """
    x, y = pos
    return (y, x if y % 2 == 0 else BOARD_SIZE - 1 - x)


def step_toward(src, dst):
    """One move name that reduces the Manhattan distance, or None if already there.

    X before Y, which keeps a unit inside its serpentine row until the row is finished
    instead of cutting diagonally across other units' runs.
    """
    sx, sy = src
    dx, dy = dst
    if sx != dx:
        return "EAST" if dx > sx else "WEST"
    if sy != dy:
        return "SOUTH" if dy > sy else "NORTH"
    return None


def nearest_shed(pos, unlocked):
    """Closest shed tile in an unlocked quadrant -- where DROP works and SELL can see it.

    Only four tiles on the board accept a DROP, all clustered at the board centre, so a unit
    working the far corner is ~5 turns from being able to bank anything it carries.
    """
    cands = [p for q, p in SHED_TILES.items() if q in unlocked] or [SHED_TILES["NW"]]
    return min(cands, key=lambda p: manhattan(pos, p))


def split_runs(jobs, units, turns_left, deliver_reserve=0):
    """Cut a serpentine-ordered job list into one contiguous run per unit.

    `jobs`    serpentine-ordered list of job dicts, each with a "pos" key and an optional
              "acts" count for jobs that occupy their tile for more than one turn (a PLANT
              and its same-day WATER are one such job -- see policy.collect_jobs)
    `units`   [(unit_index, (x, y))] -- real positions read from the observation
    `turns_left`  turns remaining in the day, shared by every unit
    `deliver_reserve`  turns held back so a unit carrying harvest can still reach a shed
                       tile and DROP. Costs a job; on the last day it is the difference
                       between selling the harvest and losing it.

    Returns {unit_index: [job, ...]}. Jobs that fit in nobody's budget are dropped, which is
    the honest outcome: the roster physically cannot service them today, and the caller has
    already sorted `jobs` by value so what falls off the end is the cheapest work.

    Units are matched to runs in serpentine order rather than by nearest-first. Every unit
    spawns within one tile of the shed at the board centre, so "nearest" is a coin flip
    between them, while keeping the assignment monotone in serpentine order stops two runs
    from crossing.
    """
    order = sorted(units, key=lambda u: serpentine_key(u[1]))
    out = {i: [] for i, _ in units}
    if not order:
        return out

    per_unit = max(1, len(jobs) // len(order) + (1 if len(jobs) % len(order) else 0))
    qi = 0
    for slot, (idx, start) in enumerate(order):
        pos = start
        spent = 0
        budget = turns_left - deliver_reserve
        # Leave later units something to do rather than letting unit 0 eat the whole list:
        # the runs are contiguous, so a greedy first unit would take the near half of the
        # board and leave the far half to units that then pay a long commute to reach it.
        take_cap = per_unit if slot < len(order) - 1 else len(jobs)
        while qi < len(jobs) and len(out[idx]) < take_cap:
            j = jobs[qi]
            cost = manhattan(pos, j["pos"]) + j.get("acts", 1)   # walk there, then the ops
            if spent + cost > budget:
                break
            out[idx].append(j)
            spent += cost
            pos = j["pos"]
            qi += 1
    return out


def run_cost(start, jobs):
    """Turns a unit needs to walk a run and perform every op in it."""
    pos, total = start, 0
    for j in jobs:
        total += manhattan(pos, j["pos"]) + j.get("acts", 1)
        pos = j["pos"]
    return total


def capacity(commute_moves, turns=TURNS_PER_DAY):
    """Tile-visits one unit can complete, given a one-way walk to its run.

    A serpentine sweep is `commute + T ops + (T - 1) moves <= turns`. One way, not a round
    trip: the engine deletes the hand roster where it stands at midnight after dumping every
    carried inventory into the shed, so nothing ever walks home. Charging a return leg halves
    the serviceable farm for no reason.
    """
    return max(0, int((turns - commute_moves + 1) // 2))
