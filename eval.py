"""
Offline evaluation harness. `python3 eval.py` prints one table and exits.

The point of this file is that a single episode is not evidence. The engine seeds the shop
draw, and the shop draw decides which goods the town pumps -- a season where two YARN_STOREs
open pays wool 4 units a tick, and one where none do pays it nothing. A mix tuned on seed 1
can be a mix tuned on a coincidence. So every measurement here is a mean over a seed panel
crossed with an opponent pool, and every number that gets quoted back into PLAN.md or into
`PARAMS` comes out of this file rather than out of a single run.

It also measures the things terminal bank hides. Bank is one number at step 720 and it cannot
distinguish a farm that banked $50k cleanly from one that banked $50k while destroying 40
plants and idling half its roster -- and the second one has the larger headroom. The per-metric
columns below are there to find that headroom:

  tiles/day     mean live plants over the season. The farm's actual size, not its ambition.
  thirst        plants that hit two dry nights and turned to weed. Every one forfeits a whole
                remaining cycle, so this is the most expensive failure the agent can have.
                Counted separately from plants that simply finished their schedule and decayed,
                which look identical on the board and are not a failure at all -- a metric that
                added the two together said a productive farm was a wasteful one, and sent me
                looking for a labour bug that was not there.
  spent         plants that reached end of life and vanished. Costs nothing; scales with size.
  idle          unit-turns spent on PASS. Wages paid for nothing; also the slack that a
                bigger farm could have used.
  lost          items destroyed by shed overflow, at 100 items a shed. Counted at the moment
                the engine refuses them, which is the only place it is visible.
  px%           realized sale price as a fraction of base, weighted by units. Under 100%
                means selling into a glut we created; the town is a net price pump, so a
                well-behaved agent should sit above it.
  worst         slowest single turn in ms, against the engine's 1s `actTimeout`. A single
                breach forfeits the whole episode, so this column is a hard gate, not a
                statistic.

Runs in-process across a `ProcessPoolExecutor`, because 720 steps of the mirror is about
8 ms and the interesting sweep sizes are in the thousands of episodes.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from kagfarm.constants import BOARD_SIZE, MARKET_PARAMS, SEASON_DAYS, TURNS_PER_DAY, price_for


def _count_tiles(farm):
    """(live plants, weeds) over the whole board, locked quadrants included.

    Read off the engine's own farm object rather than the observation, so it stays true even
    if a future observation redacts tile detail.
    """
    live = weeds = 0
    for row in farm.tiles:
        for tile in row:
            if not isinstance(tile, dict):
                continue
            if tile.get("kind") == "WEED":
                weeds += 1
            elif tile.get("kind") == "PLANT":
                live += 1
    return live, weeds


def run_one(args):
    """One full 720-step episode. Returns a flat dict of metrics for player 0.

    Imports inside the function because this runs in a worker process, and re-imports the
    agent module fresh so `main._POLICIES` cannot leak state between episodes in a pool
    worker that gets reused.

    `params` overrides `kagfarm.policy.PARAMS` for this episode only. `Policy.__init__` copies
    that dict, so mutating the module-level one is how a sweep injects a candidate without
    threading a config object through the submission entry point -- which has to stay a bare
    `agent(obs)` for Kaggle.

    `args` may carry a trailing engine tag: "mirror" (default, engine.py, ~8 ms, the
    screening tier) or "real" (the vendored kaggle-environments interpreter via
    bridge/real_env.py, the confirmation tier -- see its docstring for the provenance
    gate). Bank values are only comparable within one engine.
    """
    args = tuple(args) + (None,) * (5 - len(args))
    seed, opp_name, agent_mod, params, engine = args[:5]
    if engine == "real":
        from bridge.real_env import run_one_real
        return run_one_real((seed, opp_name, agent_mod, params))
    from engine import KaggricultureEnv
    from agents import BUILTIN_AGENTS
    from kagfarm import policy as _policy

    saved_params = {k: _policy.PARAMS[k] for k in params if k in _policy.PARAMS} if params else {}
    if params:
        _policy.PARAMS.update(params)
        # Restored just before returning: PARAMS is module-global process state and
        # `evaluate(workers=1)` runs every episode in this same interpreter, so the next
        # in-process episode would otherwise inherit this episode's parameters -- a holdout
        # run placed after a candidate run silently evaluated the *incumbent* with the
        # candidate's constants. (Pool workers > 1 fork per job and never see the mutation.)
        # If the episode itself raises, the executor re-raises in the caller, so the
        # failure is loud -- there is no silent leak on that path.
    mod = importlib.import_module(agent_mod)
    importlib.reload(mod)
    opp = BUILTIN_AGENTS[opp_name]

    # REPLAY_MARKET_PRESSURE judges carry a working-capital floor (see replay_opp.py):
    # the recorded opponents survive their d0-14 trough on a windfall the mirror world
    # halves, and a bankrupt judge applies zero market pressure. The runner — never the
    # agent, which the engine would not let mint money — tops the judge up to the floor
    # each turn and reports the total, so calibration can price the subsidy honestly.
    judge_meta = getattr(opp, "replay_meta", None)
    subsidy = (judge_meta or {}).get("subsidy_floor", 0.0)
    subsidy_given = 0.0
    if subsidy:
        _apply_units = env._apply_unit_actions

        def apply_with_floor(pi, act):
            nonlocal subsidy_given
            if pi == 1:
                f = env.farms[1]
                if f.money < subsidy:
                    subsidy_given += subsidy - f.money
                    f.money = subsidy
            return _apply_units(pi, act)

        env._apply_unit_actions = apply_with_floor

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    me = env.farms[0]

    # Attribute every plant death and every destroyed item, by wrapping the two engine methods
    # where they are the only observable. A tile that turned to WEED looks the same on the board
    # whether it died of thirst or finished its schedule, and shed overflow is discarded inside
    # `_add_shed` without leaving a trace anywhere else.
    deaths = {"thirst": 0, "spent": 0, "thirst_units": 0}
    lost = {"n": 0}
    _refresh = env._refresh_plant
    _add = env._add_shed

    def refresh_plant(f, x, y, tile):
        was_dry = not tile.get("watered_today")
        before = tile.get("consecutive_unwatered", 0)
        units = tile.get("yield_units", 0)
        _refresh(f, x, y, tile)
        if f is me and isinstance(f.tiles[y][x], dict) and f.tiles[y][x].get("kind") == "WEED":
            if was_dry and before + 1 >= 2:
                deaths["thirst"] += 1
                deaths["thirst_units"] += units
            else:
                deaths["spent"] += 1

    def add_shed(f, item, n):
        got = _add(f, item, n)
        if f is me:
            lost["n"] += max(0, n - got)
        return got

    env._refresh_plant = refresh_plant
    env._add_shed = add_shed

    # Price what actually settles, not what was ordered. The agent deliberately over-orders --
    # a SELL naming more than the shed holds is free, and it is the only way to cover produce
    # that the units dump *during* the same turn -- so counting ordered units overstates
    # revenue several-fold. `_settle_one_unit` is where a sale becomes real.
    revenue = defaultdict(float)
    units_sold = defaultdict(int)
    _settle = env._settle_one_unit

    def settle_one_unit(pi, resource, op, price=None):
        if pi == 0 and op == "SELL" and me.shed.get(resource, 0) > 0:
            revenue[resource] += (price if price is not None
                                  else price_for(resource, env.market_inventory[resource]))
            units_sold[resource] += 1
        return _settle(pi, resource, op, price)

    env._settle_one_unit = settle_one_unit

    worst_ms = 0.0
    over_budget = 0
    idle = 0
    unit_turns = 0
    tile_days = 0
    weed_peak = 0
    weeds_seen = 0
    prev_weeds = 0
    prev_money = me.money
    prev_shed_total = 0

    while not env.done:
        t0 = time.monotonic()
        act = mod.agent(obs[0])
        ms = (time.monotonic() - t0) * 1000.0
        worst_ms = max(worst_ms, ms)
        if ms > 1000.0:
            over_budget += 1

        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        unit_turns += len(ops)
        idle += sum(1 for o in ops if not o or o[0] == "PASS")

        obs, _ = env.step([act, opp(obs[1])])

        live, weeds = _count_tiles(me)
        tile_days += live
        weed_peak = max(weed_peak, weeds)
        if weeds > prev_weeds:
            weeds_seen += weeds - prev_weeds
        prev_weeds = weeds

        shed_total = sum(me.shed.values())
        prev_shed_total = shed_total
        prev_money = me.money

    px = {}
    for good, cash in revenue.items():
        n = units_sold[good]
        if n:
            px[good] = cash / n / MARKET_PARAMS[good]["base"]
    sold_units = sum(units_sold.values())
    px_all = (sum(revenue.values()) / sold_units /
              (sum(MARKET_PARAMS[g]["base"] * units_sold[g] for g in units_sold) / sold_units)
              if sold_units else 0.0)

    pol = getattr(mod, "_POLICIES", {}).get(0)
    if params:
        _policy.PARAMS.update(saved_params)
        for k in params:
            if k not in saved_params:
                _policy.PARAMS.pop(k, None)
    return dict(
        seed=seed, opp=opp_name,
        bank=me.money, opp_bank=env.farms[1].money,
        judge_subsidy=subsidy_given,
        tiles_per_day=tile_days / (SEASON_DAYS * TURNS_PER_DAY),
        weeds=weeds_seen, weed_peak=weed_peak,
        thirst=deaths["thirst"], thirst_units=deaths["thirst_units"], spent=deaths["spent"],
        lost=lost["n"],
        idle_frac=idle / max(1, unit_turns), unit_turns=unit_turns,
        worst_ms=worst_ms, over_budget=over_budget,
        px_all=px_all, px=px, revenue=dict(revenue), units=dict(units_sold),
        err=getattr(pol, "last_error", None) if pol else None,
    )


def _fmt_group(name, rows):
    def avg(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    def fmt(key, scale=1.0, prec=1, suffix=""):
        v = avg(key)
        return ("-" if v is None else f"{v * scale:.{prec}f}{suffix}")

    n = len(rows)
    bank = sorted(r["bank"] for r in rows)
    mean = sum(bank) / n
    wins = sum(1 for r in rows if r["bank"] > r["opp_bank"])
    errs = [(r["seed"], r["err"]) for r in rows if r["err"]]
    return ("vs %-10s n=%-3d  bank mean $%8.0f  p10 $%8.0f  min $%8.0f  max $%8.0f | "
            "win %d/%d | tiles/day %5s  thirst %5s (%5s)  spent %5s  lost %5s  "
            "idle %6s  px %6s | worst %5.1fms over %d%s"
            % (name, n, mean, bank[max(0, int(0.1 * n) - 1)], bank[0], bank[-1], wins, n,
               fmt("tiles_per_day"),
               fmt("thirst"), fmt("thirst_units"),
               fmt("spent"), fmt("lost"),
               fmt("idle_frac", 100.0, 1, "%"),
               fmt("px_all", 100.0, 1, "%"),
               max(r["worst_ms"] for r in rows),
               sum(r["over_budget"] for r in rows),
               ("  ERR %s" % errs[:2]) if errs else ""))


def evaluate(seeds, opps, agent_mod="main", workers=None, quiet=False, params=None, engine="mirror"):
    jobs = [(s, o, agent_mod, params, engine) for o in opps for s in seeds]
    t0 = time.monotonic()
    workers = workers or min(os.cpu_count() or 4, 16)
    if engine == "real":
        workers = 1  # the vendored engine module is process-global state; no pool
    if workers <= 1:
        rows = [run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(run_one, jobs, chunksize=max(1, len(jobs) // (workers * 4))))
    if not quiet:
        by_opp = defaultdict(list)
        for r in rows:
            by_opp[r["opp"]].append(r)
        for opp in opps:
            if by_opp[opp]:
                print(_fmt_group(opp, by_opp[opp]))
        print(_fmt_group("ALL", rows))
        rev = defaultdict(float)
        units = defaultdict(int)
        for r in rows:
            for g, v in r["revenue"].items():
                rev[g] += v
            for g, v in r["units"].items():
                units[g] += v
        total = sum(rev.values()) or 1.0
        print("\nrevenue by good (mean per episode, share, realized price vs base):")
        for g in sorted(rev, key=lambda g: -rev[g]):
            print("  %-11s $%7.0f  %5.1f%%  %5.0f units  px %5.1f%%"
                  % (g, rev[g] / len(rows), 100.0 * rev[g] / total, units[g] / len(rows),
                     100.0 * rev[g] / units[g] / MARKET_PARAMS[g]["base"]))
        print("\n%d episodes in %.1fs (%.0f/s)"
              % (len(rows), time.monotonic() - t0, len(rows) / max(1e-9, time.monotonic() - t0)))
    return rows


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=16)
    ap.add_argument("--opps", default="starter,heuristic,random")
    ap.add_argument("--agent", default="main")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--engine", choices=("mirror", "real"), default="mirror",
                    help="mirror = engine.py screening tier; real = vendored pinned engine")
    a = ap.parse_args()
    evaluate(range(a.seeds), a.opps.split(","), a.agent, a.workers or None, engine=a.engine)


if __name__ == "__main__":
    main_cli()
