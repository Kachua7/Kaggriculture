"""
Ground-truth extraction from the REAL kaggle-environments engine.

Run via:  bash calibrate.sh
Writes:   calibration/truth.json   (constants + price grid + yield traces)

Every probe is independently wrapped, so a failure in one still leaves the rest
usable. Nothing here is imported by the shipped agent.
"""
import json, os, sys, traceback, inspect

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "truth.json")
result = {"probes": {}, "errors": {}}


def probe(name):
    """Decorator: run fn, store result or traceback."""
    def wrap(fn):
        try:
            result["probes"][name] = fn()
            print(f"  [ok]   {name}")
        except Exception:
            result["errors"][name] = traceback.format_exc(limit=6)
            print(f"  [FAIL] {name}")
        return fn
    return wrap


def jsonable(o, depth=0):
    """Best-effort conversion of engine objects to JSON."""
    if depth > 6:
        return "<deep>"
    if o is None or isinstance(o, (bool, int, float, str)):
        return o
    if isinstance(o, dict):
        return {str(k): jsonable(v, depth + 1) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [jsonable(v, depth + 1) for v in o]
    if callable(o):
        try:
            return {"__callable__": o.__name__, "signature": str(inspect.signature(o))}
        except Exception:
            return {"__callable__": str(o)}
    if hasattr(o, "__dict__"):
        return {"__type__": type(o).__name__,
                **{str(k): jsonable(v, depth + 1) for k, v in vars(o).items()
                   if not k.startswith("_")}}
    return repr(o)[:400]


print("== ground-truth extraction ==")
import kaggle_environments as ke
from kaggle_environments.envs.kaggriculture import kaggriculture as K


@probe("module_constants")
def _consts():
    """Every module-level name that is not a function/module/class."""
    out = {}
    for k, v in vars(K).items():
        if k.startswith("__") or inspect.ismodule(v) or inspect.isclass(v):
            continue
        if inspect.isfunction(v):
            out[k] = {"__function__": str(inspect.signature(v))}
        else:
            out[k] = jsonable(v)
    return out


@probe("module_source_len")
def _src():
    return {"file": inspect.getfile(K), "lines": len(inspect.getsource(K).splitlines())}


@probe("price_grid")
def _price_grid():
    """Sample whatever price function the engine exposes over a grid of inventories.

    Resolves calibration item 4: the mirror's T/target values were fitted to a
    4-point table, so they may be right at the checkpoints and wrong between them.
    """
    fn = None
    for cand in ("get_price", "price_for", "calculate_price", "compute_price", "price"):
        f = getattr(K, cand, None)
        if callable(f):
            fn = (cand, f)
            break
    if fn is None:
        return {"note": "no price fn found at module level",
                "candidates": [n for n in vars(K) if "price" in n.lower()]}
    name, f = fn
    goods = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
             "EGG", "MILK", "WOOL", "FERTILIZER"]
    invs = ([10000 + d for d in
             (-2000, -1000, -500, -200, -100, -50, -20, 0, 20, 50, 100, 200, 300,
              400, 500, 800, 1000, 1500, 2000, 4000)])
    grid = {"fn": name, "signature": str(inspect.signature(f)), "data": {}}
    for g in goods:
        row = {}
        for inv in invs:
            for args in ((g, inv), (inv, g), (g, inv, 10000)):
                try:
                    row[str(inv)] = f(*args)
                    break
                except Exception:
                    continue
        grid["data"][g] = row
    return grid


@probe("env_specification")
def _spec():
    env = ke.make("kaggriculture", debug=True)
    return {"configuration": jsonable(dict(env.configuration)),
            "agents": list(getattr(env, "agents", {}) or {}),
            "spec_keys": sorted(list(getattr(env, "specification", {}) or {}))}


CROPS = ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")


def _record(o, trace, raw, step):
    """One row: the tile under the farmer, plus money, shed and carried stock."""
    if step in (0, 1, 2, 24, 25, 48, 96, 240) and len(raw) < 12:
        raw.append({"step": step, "obs": jsonable(o)})
    try:
        me = o.get("farms", [{}])[o.get("player", 0)]
        fx, fy = me["farmer"][0], me["farmer"][1]
        trace.append({"step": step,
                      "tile": jsonable(me["tiles"][fy][fx]),
                      "money": me.get("money"),
                      "shed": jsonable(me.get("shed")),
                      "carried": jsonable(me.get("inventories"))})
    except Exception:
        pass


def _scripted_agent(script, trace, raw):
    """Wrap `script(step, obs) -> action` as a kaggle-environments agent."""
    def agent(obs, config=None):
        o = obs if isinstance(obs, dict) else dict(getattr(obs, "__dict__", {}) or {})
        step = o.get("step", o.get("turn", len(trace)))
        _record(o, trace, raw, step)
        return script(step, o)
    return agent


def _grow_script(crop, fertilize=False, harvest_on_day=None):
    """Buy seed, plant, then WATER on EVERY remaining turn.

    Watering every turn rather than once a day is deliberate, and the mirror
    proved it necessary. A plant is created with consecutive_unwatered = 1, so a
    plant that is not watered on the day it goes in is a WEED by the first
    midnight. The previous version of this probe watered only at hour 1 — but it
    planted at hour 1 of day 0, so day 0 itself was never watered and every plant
    died. On the mirror that produced an all-zeros yield trace for all five crops.
    Watering every turn removes any interaction between the probe's schedule and
    the growth curve we are trying to read; the watering *bonus window* is a
    separate question and gets its own probe.
    """
    state = {"planted": False}

    def script(step, o):
        if step == 0:
            market = [["BUY_SEED", crop, 4]]
            if fertilize:
                market.append(["BUY_PRODUCT", "FERTILIZER", 8])
            return {"farmer": ["PASS"], "hands": [], "market": market}
        if not state["planted"]:
            state["planted"] = True
            return {"farmer": ["PLANT", crop], "hands": [], "market": []}
        hour = step % 24
        if harvest_on_day is not None and step // 24 == harvest_on_day and hour == 23:
            return {"farmer": ["HARVEST"], "hands": [], "market": []}
        if fertilize and hour == 2:
            return {"farmer": ["FERTILIZE"], "hands": [], "market": []}
        return {"farmer": ["WATER"], "hands": [], "market": []}

    return script


def _make_env(days=None):
    """Env, with a shortened episode when the runner allows it.

    Some probes below need dozens of episodes, so capping episodeSteps keeps this
    script to minutes rather than an afternoon. Falls back to the full 720 turns
    if the override is not honoured, which costs time but not correctness.
    """
    if days is not None:
        want = days * 24
        for key in ("episodeSteps", "episode_steps"):
            try:
                env = ke.make("kaggriculture", configuration={key: want}, debug=False)
                if int(dict(env.configuration).get("episodeSteps", 0)) == want:
                    return env
            except Exception:
                continue
    return ke.make("kaggriculture", debug=False)


def _run(script, days=None):
    """Run one scripted farmer against `pass`. Returns (trace, raw)."""
    trace, raw = [], []
    env = _make_env(days)
    env.run([_scripted_agent(script, trace, raw), "pass"])
    return trace, raw


def _banked(row, crop):
    """Units of `crop` in the shed plus any unit's carried inventory."""
    n = 0
    shed = row.get("shed")
    if isinstance(shed, dict):
        n += int(shed.get(crop, 0) or 0)
    inv = row.get("carried")
    if isinstance(inv, dict):
        inv = list(inv.values())
    if isinstance(inv, list):
        for slot in inv:
            if isinstance(slot, dict):
                n += int(slot.get(crop, 0) or 0)
    return n


@probe("yield_traces")
def _yield_traces():
    out = {}
    for crop in CROPS:
        try:
            trace, raw = _run(_grow_script(crop), days=32)
            out[crop] = {"n_turns": len(trace),
                         "daily": [r for r in trace if r["step"] % 24 == 23][:32],
                         "raw_obs_samples": raw}
            print(f"           yield_trace {crop}: {len(trace)} turns")
        except Exception:
            out[crop] = {"error": traceback.format_exc(limit=4)}
    return out


@probe("peak_yields")
def _peak_yields():
    """Max yield_units ever seen on the tile, unfertilised and fertilised.

    Settles §5.2 item 3: the mirror's growth rule gives melon 4 units
    unfertilised against a documented cap of 6, which is ±50% on the melon
    programme — the single most expensive open number left in the game.
    """
    out = {}
    for crop in CROPS:
        row = {}
        for label, fert in (("unfert", False), ("fert", True)):
            try:
                trace, _ = _run(_grow_script(crop, fertilize=fert), days=20)
                peak, peak_day = 0, None
                for r in trace:
                    t = r.get("tile")
                    if isinstance(t, dict) and (t.get("yield_units") or 0) > peak:
                        peak, peak_day = t["yield_units"], r["step"] // 24
                row[label] = {"peak_units": peak, "peak_day": peak_day}
            except Exception:
                row[label] = {"error": traceback.format_exc(limit=3)}
        out[crop] = row
        print(f"           peak_yields {crop}: {row}")
    return out


@probe("rule_checks")
def _rule_checks():
    """Three yes/no questions, one scripted episode each, plus harvest-by-day.

    These exist because each answer flips a design decision rather than nudging a
    number, so they are worth isolating from the growth trace.
    """
    out = {}

    # (a) Can a melon be harvested on its planting day? The mirror plants one_time
    # crops with yield_units = 1, so if HARVEST ignored first_yield_day this would
    # turn an $80 seed into a ~$250 melon on the same tile-day, on every tile,
    # every day. That is either the whole game or forbidden; no middle case.
    def same_day(step, o):
        if step == 0:
            return {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", "MELON", 1]]}
        if step == 1:
            return {"farmer": ["PLANT", "MELON"], "hands": [], "market": []}
        if step == 2:
            return {"farmer": ["HARVEST"], "hands": [], "market": []}
        return {"farmer": ["PASS"], "hands": [], "market": []}

    try:
        trace, _ = _run(same_day, days=1)
        carried = _banked(trace[-1], "MELON") if trace else None
        out["early_harvest_exploit"] = {
            "melons_in_hand_after_same_day_harvest": carried,
            "expected_if_blocked": 0,
            "exploit_open": bool(carried)}
    except Exception:
        out["early_harvest_exploit"] = {"error": traceback.format_exc(limit=3)}

    # (b) Does a plant left unwatered on its planting day survive the night?
    # The mirror says no, which makes "water the tile you just planted, same day"
    # a hard routing constraint rather than a nicety.
    def unwatered(step, o):
        if step == 0:
            return {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", "WHEAT", 1]]}
        if step == 1:
            return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        return {"farmer": ["PASS"], "hands": [], "market": []}

    try:
        trace, _ = _run(unwatered, days=2)
        tile = trace[-1].get("tile") if trace else None
        kind = tile.get("kind") if isinstance(tile, dict) else tile
        out["unwatered_on_plant_day"] = {"tile_after_one_night": kind,
                                         "died": kind != "PLANT"}
    except Exception:
        out["unwatered_on_plant_day"] = {"error": traceback.format_exc(limit=3)}

    # (c) Units actually BANKED when you commit HARVEST on day D. This, not the
    # peak on the tile, is the number the planner needs -- it also pins down the
    # post-peak decay rule (§5.2 item 7) as a side effect.
    out["harvest_by_day"] = {}
    for crop in CROPS:
        row = {}
        for D in (2, 3, 4, 5, 8, 10, 11, 12, 13, 14, 16):
            try:
                trace, _ = _run(_grow_script(crop, harvest_on_day=D), days=D + 1)
                row[str(D)] = _banked(trace[-1], crop) if trace else None
            except Exception:
                row[str(D)] = None
        out["harvest_by_day"][crop] = row
        print(f"           harvest_by_day {crop}: {row}")
    return out


@probe("idle_market_trace")
def _idle_market():
    """Market inventory for every good over a full episode with BOTH agents passing.

    This is the cheapest probe here — one episode, no actions — and it validates the most
    load-bearing structural claim in the plan. §2.1 says the town drains inventory whether
    or not anyone sells, so inventory falls below I0 and prices sit ABOVE base all season.
    If that is right, this trace shows every good's inventory sloping down and its price
    sloping up; if inventory sits flat at 10,000, the whole 'town is a price pump' argument
    is wrong and the sell-late conclusion inverts back.

    It also measures the shop unlock cadence directly (§5.2 item 5) as the kink pattern in
    the slope, rather than assuming 1-per-3-days capped at 8.
    """
    rows = []

    def watcher(obs, config=None):
        o = obs if isinstance(obs, dict) else dict(getattr(obs, "__dict__", {}) or {})
        step = o.get("step", o.get("turn", len(rows)))
        if step % 24 in (0, 23):
            snap = {"step": step}
            for key in ("market", "inventories", "market_inventory", "town", "shops"):
                if key in o:
                    snap[key] = jsonable(o[key])
            rows.append(snap)
        return {"farmer": ["PASS"], "hands": [], "market": []}

    env = _make_env()
    env.run([watcher, "pass"])
    return {"n_rows": len(rows), "rows": rows[:80],
            "note": "keys are whatever the obs exposes; sampled at hour 0 and 23 each day"}


@probe("builtin_baselines")
def _baselines():
    out = {}
    for foe in ("pass", "random", "starter"):
        try:
            env = ke.make("kaggriculture", debug=False)
            env.run(["starter", foe])
            out[f"starter_vs_{foe}"] = [jsonable(s.get("reward")) for s in env.steps[-1]]
        except Exception:
            out[f"starter_vs_{foe}"] = traceback.format_exc(limit=3)
    return out


with open(OUT, "w") as fh:
    json.dump(result, fh, indent=1, default=str)
print(f"\nwrote {OUT}  ({os.path.getsize(OUT)} bytes)")
print(f"probes ok: {sorted(result['probes'])}")
if result["errors"]:
    print(f"probes failed: {sorted(result['errors'])} — see truth.json for tracebacks")


