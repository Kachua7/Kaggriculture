"""A2: one row per contested constant — mirror value vs pinned-wheel value, with a verdict.

Reads BOTH sources mechanically (ast over the vendored engine module and over
kagfarm/constants.py; json for the configuration defaults) and emits the table the plan
committed to. Tags:

  REAL     mirror matches the pinned wheel exactly.
  DIVERGE  mirror disagrees with the pinned wheel — the rows that drove the A2 edits and
           the A3 gate.
  DEAD     present in the mirror but absent from the engine (mirror-only invention).
  NEW      present in the engine but absent from the mirror (mirror is missing a rule).

Only the pinned 1.32.7 wheel is the reference here; run fingerprint.py to decide whether
the LIVE ladder agrees with it. Note the mirror folds the engine's single-product-shop 2x
multiplier into SHOP_TABLE and maps wheel field names onto OBJECT_TABLE ones; this script
compares through those mappings rather than assuming textual equality.

Usage:  python3 calibration/diff_source.py
"""

from __future__ import annotations

import ast
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
ENGINE_DIR = os.path.join(_HERE, "engine")

# Names pulled from each source's top-level assignments.
WHEEL_NAMES = ("MARKET_PARAMS", "CROPS", "ANIMALS", "SHOPS", "MAX_SHOP_INSTANCES",
               "FARM_HAND_COST_MULT", "LAND_PRICES", "LAND_ORDER", "MARKET_I0",
               "PRICE_FLOOR", "HINGE_GAIN", "TOWN_CENTER_DEMAND_SCHEDULE",
               "TOWN_CENTER_PRODUCTS")
MIRROR_NAMES = ("MARKET_PARAMS", "OBJECT_TABLE", "SHOP_TABLE", "MAX_SHOP_INSTANCES",
                "FARM_HAND_COST_MULT", "LAND_PRICES", "I0", "SHED_CAPACITY",
                "WEED_SPAWN_CHANCE", "TOWN_CENTER_SELL_INTERVAL_TURNS",
                "TOWN_SHOP_UNLOCK_INTERVAL_DAYS", "TOWN_SHOP_SELL_INTERVAL_TURNS",
                "TOWN_SHOP_SELL_INTERVAL_TURNS", "BOARD_SIZE", "STARTING_MONEY",
                "MAX_MARKET_ORDERS", "EPISODE_STEPS", "TURNS_PER_DAY")


def top_level_assignments(path, names):
    """{name: (value, lineno)} for literal top-level assignments in a python file."""
    tree = ast.parse(open(path).read(), filename=path)
    out = {}
    for node in tree.body:
        targets = []
        value = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        for t in targets:
            if isinstance(t, ast.Name) and t.id in names:
                try:
                    out[t.id] = (ast.literal_eval(value), node.lineno)
                except (ValueError, SyntaxError):
                    pass  # non-literal (e.g. list comprehension); skip mechanically
    return out


def _exec_names(path, names):
    """Fallback for non-literal top-level values (e.g. OBJECT_TABLE's dict(...) calls):
    execute the module in a throwaway namespace and pull the requested names."""
    ns = {"__name__": "_diff_source_extract", "__file__": path}
    try:
        exec(compile(open(path).read(), path, "exec"), ns)
    except Exception:
        return {}
    return {n: (ns[n], 0) for n in names if n in ns}


def load():
    wheel_py = os.path.join(ENGINE_DIR, "kaggriculture.py")
    wheel_json = json.load(open(os.path.join(ENGINE_DIR, "kaggriculture.json")))
    wheel = top_level_assignments(wheel_py, WHEEL_NAMES)
    # Wheel constants embed name references (MARKET_I0, ...) that defeat literal_eval;
    # fill those from exec, with ast results winning on conflicts.
    wheel = {**_exec_names(wheel_py, WHEEL_NAMES), **wheel}
    consts_py = os.path.join(_ROOT, "kagfarm", "constants.py")
    mirror = top_level_assignments(consts_py, MIRROR_NAMES)
    # Fill names literal_eval could not parse (dict(...) calls etc.); ast results win.
    mirror = {**_exec_names(consts_py, MIRROR_NAMES), **mirror}
    return wheel, mirror, wheel_json


def fmt(v):
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {fmt(x)}" for k, x in sorted(v.items()))[:90] + "}"
    return str(v)


def main():
    wheel, mirror, spec = load()
    rows = []  # (group, name, mirror_val, wheel_val, wheel_where, tag)

    # -- configuration intervals: engine json defaults vs constants.py --------------------
    cfg = spec.get("configuration", {})
    CFG_ROWS = [
        ("townCenterSellInterval", "TOWN_CENTER_SELL_INTERVAL_TURNS"),
        ("townShopUnlockInterval", "TOWN_SHOP_UNLOCK_INTERVAL_DAYS"),
        ("townShopSellInterval", "TOWN_SHOP_SELL_INTERVAL_TURNS"),
        ("shedCapacity", "SHED_CAPACITY"),
        ("weedSpawnChance", "WEED_SPAWN_CHANCE"),
        ("boardSize", "BOARD_SIZE"),
        ("startingMoney", "STARTING_MONEY"),
        ("maxMarketOrdersPerTurn", "MAX_MARKET_ORDERS"),
        ("episodeSteps", "EPISODE_STEPS"),
        ("turnsPerDay", "TURNS_PER_DAY"),
    ]
    for cfg_key, mirror_key in CFG_ROWS:
        node = cfg.get(cfg_key, {})
        wv = node.get("default") if isinstance(node, dict) else node
        mv = mirror.get(mirror_key, ("?", 0))[0]
        tag = "REAL" if wv == mv else "DIVERGE"
        rows.append(("config", cfg_key, mv, wv, "json default", tag))

    # -- market curves, per good / per field ----------------------------------------------
    wm = wheel.get("MARKET_PARAMS", ({}, 0))[0]
    mm = mirror.get("MARKET_PARAMS", ({}, 0))[0]
    FIELD_MAP = [("base", "base"), ("T", "T"),
                 ("below_func", "below_f"), ("below_target", "below_t"),
                 ("above_func", "above_f"), ("above_target", "above_t")]
    for good in sorted(wm):
        wp, mp = wm[good], mm.get(good)
        if mp is None:
            rows.append(("market", good, "-", fmt(wp), "source", "NEW"))
            continue
        for wf, mf in FIELD_MAP:
            wv, mv = wp.get(wf), mp.get(mf)
            if wv != mv:
                rows.append(("market", f"{good}.{wf}", mv, wv, "MARKET_PARAMS", "DIVERGE"))
    for good in sorted(set(mm) - set(wm)):
        rows.append(("market", good, fmt(mm[good]), "-", "-", "NEW"))

    # -- crops: wheel CROPS vs mirror OBJECT_TABLE ----------------------------------------
    wc = wheel.get("CROPS", ({}, 0))[0]
    ot = mirror.get("OBJECT_TABLE", ({}, 0))[0]
    CROP_MAP = [("seed", "seed_cost"), ("first_yield_day", "first_yield_day"),
                ("max_yield_day", "max_yield_day"), ("max_yield", "max_yield")]
    for crop in sorted(wc):
        w, m = wc[crop], ot.get(crop)
        if m is None:
            rows.append(("crop", crop, "-", fmt(w), "CROPS", "NEW"))
            continue
        # Representation mapping: ongoing crops store first_yield_day as sched_days[0];
        # the engine's max_yield_day for ongoing crops is derived (= first_yield_day),
        # so it has no independent mirror counterpart.
        effective = dict(m)
        if m.get("kind") == "ongoing" and m.get("sched_days"):
            effective.setdefault("first_yield_day", m["sched_days"][0])
        for wf, mf in CROP_MAP:
            if wf == "max_yield_day" and m.get("kind") == "ongoing":
                continue  # derived in engine, absent by design in mirror
            if w.get(wf) != effective.get(mf):
                rows.append(("crop", f"{crop}.{wf}", effective.get(mf), w.get(wf), "CROPS", "DIVERGE"))
        # growth schedule: wheel interval/ongoing vs mirror sched_days/kind
        if bool(w.get("ongoing")) != (m.get("kind") == "ongoing"):
            rows.append(("crop", f"{crop}.ongoing", m.get("kind"), w.get("ongoing"), "CROPS", "DIVERGE"))
        if w.get("interval") != (0 if m.get("kind") == "one_time" else
                                 (m.get("sched_days", [0, 1])[1] - m.get("sched_days", [0, 1])[0])):
            rows.append(("crop", f"{crop}.interval", m.get("sched_days"), w.get("interval"), "CROPS", "DIVERGE"))
        if "max_yield_unfert" in m:
            rows.append(("crop", f"{crop}.max_yield_unfert", m["max_yield_unfert"],
                         "absent from engine", "CROPS", "DEAD"))

    # -- animals ---------------------------------------------------------------------------
    wa = wheel.get("ANIMALS", ({}, 0))[0]
    ANI_MAP = [("cost", "buy_cost"), ("first_yield_day", "first_yield_day"),
               ("interval", "interval"), ("max_held", "max_held"),
               ("product", "product"), ("structure", "structure")]
    for animal in sorted(wa):
        w, m = wa[animal], ot.get(animal)
        if m is None:
            rows.append(("animal", animal, "-", fmt(w), "ANIMALS", "NEW"))
            continue
        for wf, mf in ANI_MAP:
            if w.get(wf) != m.get(mf):
                rows.append(("animal", f"{animal}.{wf}", m.get(mf), w.get(wf), "ANIMALS", "DIVERGE"))

    # -- shops: wheel unit baskets vs mirror (2x folded for single-product shops) ----------
    ws = wheel.get("SHOPS", ({}, 0))[0]
    ms = mirror.get("SHOP_TABLE", ({}, 0))[0]
    for shop in sorted(set(ws) | set(ms)):
        w = ws.get(shop)
        m = ms.get(shop)
        if w is None or m is None:
            rows.append(("shop", shop, fmt(m), fmt(w), "SHOPS", "NEW" if w else "DEAD"))
            continue
        mult = 2 if len(w) == 1 else 1
        expect = {good: mult for good in w}
        if expect != m:
            rows.append(("shop", shop, fmt(m), fmt(expect) + " (x%d folded)" % mult, "SHOPS", "DIVERGE"))

    # -- report ----------------------------------------------------------------------------
    counts = {}
    for _, _, _, _, _, tag in rows:
        counts[tag] = counts.get(tag, 0) + 1
    print(f"reference: {ENGINE_DIR} (pinned 1.32.7 — see MANIFEST.sha256)")
    print(f"rows: {len(rows)}   " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())) + "\n")
    hdr = f"{'group':8} {'name':30} {'mirror':40} {'wheel':40} tag"
    print(hdr)
    print("-" * len(hdr))
    for group, name, mv, wv, where, tag in rows:
        print(f"{group:8} {name:30} {str(mv)[:38]:40} {f'{wv} [{where}]'[:38]:40} {tag}")
    print("\nDIVERGE rows are the deltas the A2 edits resolved (constants follow the pin);")
    print("DEAD rows are mirror-only inventions kept as inert data; NEW rows are engine")
    print("rules the mirror does not model. Re-run after any engine re-pin.")


if __name__ == "__main__":
    main()
