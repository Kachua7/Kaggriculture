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


def _make_probe_agent(crop, trace, raw, harvest_never=True):
    """Plants one tile of `crop` under the farmer, waters it once a day, never harvests.

    Records the tile dict every turn -> exact yield growth curve. Resolves
    calibration items 1,2,3,6,7 (melon max_yield_day, wheat starting yield_units,
    the growth rule itself, post-peak decay, and the watering bonus window).
    """
    state = {"planted": False}

    def agent(obs, config=None):
        o = obs if isinstance(obs, dict) else dict(getattr(obs, "__dict__", {}) or {})
        step = o.get("step", o.get("turn", len(trace)))
        if step in (0, 1, 2, 24, 25, 48, 96, 240) and len(raw) < 12:
            raw.append({"step": step, "obs": jsonable(o)})
        # best-effort: find my farm's tile grid and the farmer position
        try:
            me = o.get("farms", [{}])[o.get("player", 0)]
            fx, fy = me["farmer"][0], me["farmer"][1]
            trace.append({"step": step, "tile": jsonable(me["tiles"][fy][fx]),
                          "money": me.get("money")})
        except Exception:
            pass
        market = [["BUY_SEED", crop, 4]] if step == 0 else []
        if step == 0:
            return {"farmer": ["PASS"], "hands": [], "market": market}
        if not state["planted"]:
            state["planted"] = True
            return {"farmer": ["PLANT", crop], "hands": [], "market": []}
        hour = step % 24
        op = ["WATER"] if hour == 1 else ["PASS"]
        if not harvest_never and hour == 23:
            op = ["HARVEST"]
        return {"farmer": op, "hands": [], "market": []}

    return agent


@probe("yield_traces")
def _yield_traces():
    out = {}
    for crop in ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY"):
        trace, raw = [], []
        try:
            env = ke.make("kaggriculture", debug=False)
            env.run([_make_probe_agent(crop, trace, raw), "pass"])
            # collapse to one row per day: the tile as of the last turn of each day
            per_day, seen = [], set()
            for row in trace:
                d = row["step"] // 24
                if d not in seen or True:
                    per_day.append(row)
            out[crop] = {"n_turns": len(trace),
                         "daily": [r for r in per_day if r["step"] % 24 == 23][:32],
                         "raw_obs_samples": raw}
        except Exception:
            out[crop] = {"error": traceback.format_exc(limit=4)}
    return out


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


