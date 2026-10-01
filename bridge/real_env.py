"""Bridge: run repo agents on the VENDORED real engine (kaggle_environments env source).

The mirror (engine.py) answers in ~8 ms but its contested constants are now
version-tagged; this bridge is the confirmation tier. It loads the vendored interpreter
(calibration/engine = pinned 1.32.7, calibration/engine-1.32.2 = the replay-matched
version) and drives full 720-step episodes with repo agents in both seats, exposing the
same flat metrics dict eval.py consumes.

Provenance gate: calibration/verify_replay.py must reproduce the tutorial replay
exactly on the engine dir you run panels against. 1.32.2 passes it by construction
(the replay was recorded on it); running the same replay against 1.32.7 shows the
mechanics delta concretely. Panels mixing engine dirs are meaningless — one table, one
engine.

The policy reads plain dicts (`obs.get(...)`), while the interpreter mutates
attribute-style observation objects, so each turn hands the agent a shallow dict view of
the live Struct; nested farms/market/town/private are the engine's own plain dicts and
are passed through unmodified. Nothing here is importable from the submission — this
file never ships.

Usage:
  .venv/bin/python bridge/real_env.py --seeds 4 --opps self
  .venv/bin/python bridge/real_env.py --seeds 2 --engine-dir calibration/engine-1.32.2 --opps starter
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

ENGINE_DIR = os.path.join(_ROOT, "calibration", "engine")
ENGINE_DIR_1322 = os.path.join(_ROOT, "calibration", "engine-1.32.2")
DEFAULT_CONFIG = dict(
    episodeSteps=720, actTimeout=1, boardSize=10, startingMoney=3000,
    maxMarketOrdersPerTurn=10, turnsPerDay=24, shedCapacity=100,
    weedSpawnChance=0.005, townShopUnlockInterval=3, townShopSellInterval=4,
    townCenterSellInterval=24, farmHandCostMult=1, marketParams=[], seed=None,
)

_ENGINE_CACHE = {}


class _Struct:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _ensure_engine_deps():
    """The vendored engine imports kaggle_environments.utils for the episode seed. Under
    .venv (canonical interpreter) that import is real; under bare python3, install a stub
    that reads env.info['seed'] directly, which is what the framework does for us."""
    try:
        import kaggle_environments.utils  # noqa: F401
        return
    except ImportError:
        import types
        pkg = types.ModuleType("kaggle_environments")
        utils = types.ModuleType("kaggle_environments.utils")
        utils.resolve_episode_seed = lambda env: (env.info or {}).get("seed", 0) or 0
        pkg.utils = utils
        sys.modules.setdefault("kaggle_environments", pkg)
        sys.modules.setdefault("kaggle_environments.utils", utils)


def load_engine(engine_dir: str):
    """Import the vendored interpreter module, cached per directory (and per process)."""
    key = os.path.abspath(engine_dir)
    mod = _ENGINE_CACHE.get(key)
    if mod is None:
        _ensure_engine_deps()
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "kaggriculture_vendored_" + str(len(_ENGINE_CACHE)),
            os.path.join(key, "kaggriculture.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ENGINE_CACHE[key] = mod
    return mod


class RealEnv:
    """A 720-step two-seat episode on the vendored interpreter."""

    def __init__(self, seed: int, engine_dir: str = ENGINE_DIR, episode_steps: int = 720):
        eng = load_engine(engine_dir)
        self.eng = eng
        cfg = dict(DEFAULT_CONFIG)
        cfg["episodeSteps"] = episode_steps
        self.episode_steps = episode_steps
        # The framework derives runtime config from the engine's json defaults; the
        # hardcoded dict above must not shadow them or a 1.32.2 engine dir would silently
        # run tau=24 (it did, before this merge — every pre-existing 1.32.2 bridge panel
        # ran the wrong town-centre rate; nothing adopted depends on those panels).
        try:
            with open(os.path.join(engine_dir, "kaggriculture.json")) as fh:
                spec_cfg = json.load(fh).get("configuration") or {}
            for key, entry in spec_cfg.items():
                if isinstance(entry, dict) and "default" in entry and key in cfg:
                    cfg[key] = entry["default"]
        except Exception:
            pass                       # keep DEFAULT_CONFIG if the json is unreadable
        self.config = _Struct(**cfg)   # handed to agents exactly as the framework would
        self.env = _EnvStruct(configuration=self.config, done=False, info={"seed": int(seed)})
        self.state = [
            _Struct(action=None, observation=_Struct(), status="ACTIVE", reward=0.0, info={})
            for _ in range(2)
        ]
        eng._initialize(self.state, self.env)
        self.t = 0
        self.done = False

    def _obs_view(self, p: int) -> dict:
        o = self.state[p].observation
        view = dict(vars(o))
        view.setdefault("player", p)
        view.setdefault("step", self.t)
        return view

    def banks(self):
        return [f["money"] for f in self.state[0].observation.farms]

    def step(self, actions):
        """actions: [{farmer, hands, market}, {farmer, hands, market}]."""
        if self.done:
            return
        self.state[0].observation.step = self.t
        for p in (0, 1):
            self.state[p].action = actions[p] or {}
        self.eng.interpreter(self.state, self.env)
        self.t += 1
        # Mirror the framework: the interpreter flips status/reward itself at the end.
        self.done = self.t >= self.episode_steps - 1


class _EnvStruct(_Struct):
    """Env stand-in: the engine only touches .configuration, .done and .info."""


# ---------------------------------------------------------------------------
# Metrics on the vendored engine
# ---------------------------------------------------------------------------

def _wrap_sells(eng, pid, revenue, units_sold):
    """Attribute realized SELL revenue for one seat by wrapping the module-level
    commit function (the lockstep market loop resolves the price, we just watch).
    *args passthrough so both 1.32.2 and 1.32.7 signatures work; idempotent across
    pooled episodes by restoring the saved original before each wrap."""
    orig = getattr(eng, "_commit_unit_orig", None)
    if orig is None:
        orig = eng._commit_unit
        eng._commit_unit_orig = orig

    def wrapped(op, item, price, farm, *rest):
        ok = orig(op, item, price, farm, *rest)
        if ok and op == "SELL" and farm is _wrap_sells.farms[pid]:
            revenue[item] += price
            units_sold[item] += 1
        return ok

    eng._commit_unit = wrapped


def _plant_death_kind(before_tile, after_tile):
    """thirst vs spent from tile snapshots around the end-of-day refresh."""
    if not (isinstance(before_tile, dict) and before_tile.get("kind") == "PLANT"):
        return None
    if not (isinstance(after_tile, dict) and after_tile.get("kind") == "WEED"):
        return None
    if before_tile.get("consecutive_unwatered", 0) >= 1 and not before_tile.get("watered_today"):
        return "thirst"
    return "spent"


def run_one_real(args):
    """eval.py-compatible episode on the vendored engine. args = (seed, opp_name, agent_mod,
    params[, engine_dir]); the trailing engine_dir is optional and defaults to the pinned
    calibration/engine."""
    args = tuple(args) + (None,) * (5 - len(args))
    seed, opp_name, agent_mod, params, engine_dir = args[:5]
    engine_dir = engine_dir or ENGINE_DIR
    from kagfarm import policy as _policy

    if params:
        _policy.PARAMS.update(params)
    mod = importlib.import_module(agent_mod)
    importlib.reload(mod)
    from agents import BUILTIN_AGENTS
    opp = BUILTIN_AGENTS[opp_name]

    env = RealEnv(seed, engine_dir)
    me_farm = env.state[0].observation.farms[0]

    revenue = defaultdict(float)
    units_sold = defaultdict(int)
    _wrap_sells.farms = [env.state[0].observation.farms[0], env.state[1].observation.farms[1]]
    _wrap_sells(env.eng, 0, revenue, units_sold)

    deaths = {"thirst": 0, "spent": 0, "thirst_units": 0}
    worst_ms = 0.0
    over_budget = 0
    idle = 0
    unit_turns = 0
    tile_days = 0

    obs0 = env._obs_view(0)
    obs1 = env._obs_view(1)
    while not env.done:
        t0 = time.monotonic()
        act0 = mod.agent(obs0, env.config)
        ms = (time.monotonic() - t0) * 1000.0
        worst_ms = max(worst_ms, ms)
        if ms > 1000.0:
            over_budget += 1
        t1 = time.monotonic()
        act1 = opp(obs1)
        if (time.monotonic() - t1) * 1000.0 > 1000.0:
            over_budget += 0  # opponent budget is its own problem; not gated

        ops = [act0.get("farmer") or ["PASS"]] + list(act0.get("hands") or [])
        unit_turns += len(ops)
        idle += sum(1 for o in ops if not o or o[0] == "PASS")

        # DEEP-copy the plant tiles: the end-of-day refresh mutates tile dicts in place
        # (consecutive_unwatered += 1, watered_today = False) before replacing dead ones,
        # so a shallow row copy would classify spent deaths as thirst.
        tiles_before = [[dict(t_) if isinstance(t_, dict) else t_ for t_ in row]
                        for row in me_farm["tiles"]]

        env.step([act0, act1])

        for y in range(len(tiles_before)):
            for x in range(len(tiles_before[0])):
                kind = _plant_death_kind(tiles_before[y][x], me_farm["tiles"][y][x])
                if kind:
                    deaths[kind] += 1
                    if kind == "thirst":
                        deaths["thirst_units"] += tiles_before[y][x].get("yield_units", 0)
        live_after = sum(1 for row in me_farm["tiles"] for t_ in row
                         if isinstance(t_, dict) and t_.get("kind") == "PLANT")
        tile_days += live_after

        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)

    banks = env.banks()
    pol = getattr(mod, "_POLICIES", {}).get(0)
    sold_units = sum(units_sold.values())
    px_all = ((sum(revenue.values()) / sold_units /
               (sum(25 * units_sold.get("WHEAT", 0) + 35 * units_sold.get("CARROT", 0)
                    + 60 * units_sold.get("TOMATO", 0) + 120 * units_sold.get("STRAWBERRY", 0)
                    + 250 * units_sold.get("MELON", 0) + 50 * units_sold.get("EGG", 0)
                    + 160 * units_sold.get("MILK", 0) + 200 * units_sold.get("WOOL", 0)
                    for _ in [0]) / sold_units))
              if sold_units else 0.0)
    return dict(
        seed=seed, opp=opp_name,
        bank=banks[0], opp_bank=banks[1],
        tiles_per_day=tile_days / 720.0,
        weeds=None, weed_peak=None,
        thirst=deaths["thirst"], thirst_units=deaths["thirst_units"], spent=deaths["spent"],
        lost=None,
        idle_frac=idle / max(1, unit_turns), unit_turns=unit_turns,
        worst_ms=worst_ms, over_budget=over_budget,
        px_all=px_all, px={}, revenue=dict(revenue), units=dict(units_sold),
        err=getattr(pol, "last_error", None) if pol else None,
    )


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--opps", default="self")
    ap.add_argument("--agent", default="main")
    ap.add_argument("--engine-dir", default=ENGINE_DIR)
    a = ap.parse_args()
    jobs = [(s, o, a.agent, None, a.engine_dir) for o in a.opps.split(",") for s in range(a.seeds)]
    t0 = time.monotonic()
    rows = [run_one_real(j) for j in jobs]
    n = len(rows)
    banks = sorted(r["bank"] for r in rows)
    wins = sum(1 for r in rows if r["bank"] > r["opp_bank"])
    print(f"engine : {a.engine_dir}")
    print(f"opps   : {a.opps}  n={n}")
    print(f"bank   : mean ${sum(banks)/n:,.0f}  p10 ${banks[max(0, int(0.1*n)-1)]:,.0f}  "
          f"min ${banks[0]:,.0f}  max ${banks[-1]:,.0f}")
    print(f"wins   : {wins}/{n}")
    print(f"worst  : {max(r['worst_ms'] for r in rows):.1f} ms  over-budget turns: "
          f"{sum(r['over_budget'] for r in rows)}")
    errs = [(r["seed"], r["err"]) for r in rows if r["err"]]
    if errs:
        print(f"ERR    : {errs[:3]}")
    print(f"{n} episodes in {time.monotonic()-t0:.1f}s")


if __name__ == "__main__":
    main_cli()
