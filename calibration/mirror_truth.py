"""
Mirror-side counterpart to dump_truth.py.

Runs the *same* scripted probes against our reimplementation (engine.py) and
emits the same JSON shape, so calibration is a mechanical diff rather than a
reading exercise:

    python calibration/mirror_truth.py          # writes calibration/mirror.json
    python calibration/diff_truth.py            # mirror.json vs truth.json

Probes:
  price_grid   -- price at 20 inventories x 9 goods
  yield_traces -- one tile per crop, watered daily at hour 1, never harvested;
                  the tile dict recorded at the last turn of each day
"""
import json, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from engine import (KaggricultureEnv, price_for, OBJECT_TABLE, MARKET_PARAMS,
                    TURNS_PER_DAY, I0)

OUT = os.path.join(HERE, "mirror.json")

GOODS = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
         "EGG", "MILK", "WOOL", "FERTILIZER"]

# identical inventory grid to dump_truth.py's price_grid probe
INVS = [I0 + d for d in (-2000, -1000, -500, -200, -100, -50, -20, 0, 20, 50,
                         100, 200, 300, 400, 500, 800, 1000, 1500, 2000, 4000)]

CROPS = ("WHEAT", "CARROT", "MELON", "TOMATO", "STRAWBERRY")


def price_grid():
    return {"fn": "price_for", "data":
            {g: {str(inv): price_for(g, float(inv)) for inv in INVS} for g in GOODS}}


def _pass_action():
    return {"farmer": ["PASS"], "hands": [], "market": []}


def yield_trace(crop, fertilize=False, harvest_never=True, days=32):
    """Single tile of `crop` under the farmer at the shed, watered every turn.

    Mirrors _make_probe_agent in dump_truth.py: BUY_SEED x4 on step 0 (farmer
    passes), PLANT on step 1, then WATER on *every* remaining turn.

    Watering every turn rather than once a day is deliberate. A plant is created
    with consecutive_unwatered = 1, so a plant that is not watered on the day it
    goes in dies at that first midnight -- an every-turn WATER removes any
    interaction between the probe's watering schedule and the growth curve we're
    trying to read. The watering-bonus *window* is a separate question and gets
    its own probe.
    """
    env = KaggricultureEnv(episode_steps=days * TURNS_PER_DAY, seed=7)
    trace = []
    planted = False
    while not env.done:
        obs = env._obs()[0]
        step = obs["step"]
        me = obs["farms"][0]
        fx, fy = me["farmer"]
        tile = me["tiles"][fy][fx]
        trace.append({"step": step,
                      "tile": dict(tile) if isinstance(tile, dict) else tile,
                      "money": me["money"]})

        market = []
        if step == 0:
            market = [["BUY_SEED", crop, 4]]
            if fertilize:
                market.append(["BUY_PRODUCT", "FERTILIZER", 8])
            act = {"farmer": ["PASS"], "hands": [], "market": market}
        elif not planted:
            planted = True
            act = {"farmer": ["PLANT", crop], "hands": [], "market": []}
        else:
            hour = step % TURNS_PER_DAY
            if fertilize and hour == 2:
                op = ["FERTILIZE"]
            elif not harvest_never and hour == 23:
                op = ["HARVEST"]
            else:
                op = ["WATER"]
            act = {"farmer": op, "hands": [], "market": []}

        env.step([act, _pass_action()])

    daily = [r for r in trace if r["step"] % TURNS_PER_DAY == 23][:days]
    return {"n_turns": len(trace), "daily": daily, "raw_obs_samples": []}


def yield_traces():
    out = {}
    for crop in CROPS:
        try:
            out[crop] = yield_trace(crop)
        except Exception:
            out[crop] = {"error": traceback.format_exc(limit=4)}
    return out


# ---------------------------------------------------------------------------
# derived summary: the numbers the plan actually depends on
# ---------------------------------------------------------------------------

def peak_yields():
    """Max yield_units ever seen on the tile, unfertilised and fertilised.

    This is the single most load-bearing calibration number: melon at 3 units vs
    1 is a 3x swing on the most valuable good in the game.
    """
    out = {}
    for crop in CROPS:
        row = {}
        for label, fert in (("unfert", False), ("fert", True)):
            try:
                tr = yield_trace(crop, fertilize=fert)
                peak, peak_day = 0, None
                for r in tr["daily"]:
                    t = r["tile"]
                    if isinstance(t, dict) and t.get("kind") == "PLANT":
                        if t.get("yield_units", 0) > peak:
                            peak = t["yield_units"]
                            peak_day = r["step"] // TURNS_PER_DAY
                row[label] = {"peak_units": peak, "peak_day": peak_day}
            except Exception:
                row[label] = {"error": traceback.format_exc(limit=3)}
        spec = OBJECT_TABLE[crop]
        row["table_cap_fert"] = spec.get("max_yield")
        row["table_cap_unfert"] = spec.get("max_yield_unfert", spec.get("max_yield"))
        out[crop] = row
    return out


# ---------------------------------------------------------------------------
# rule checks: small scripted scenarios that answer one yes/no question each
# ---------------------------------------------------------------------------

def _scripted(script, days=16, seed=7):
    """Run one farmer against a passing opponent. `script(step, obs) -> action`.

    Returns (final_obs, env) so callers can read shed / tiles / money.
    """
    env = KaggricultureEnv(episode_steps=days * TURNS_PER_DAY, seed=seed)
    last = None
    while not env.done:
        obs = env._obs()[0]
        last = obs
        env.step([script(obs["step"], obs), _pass_action()])
    return env._obs()[0], env


def check_early_harvest():
    """Can a melon be harvested on its planting day?

    start_yield=1 puts one unit on the tile the moment it is planted. If HARVEST
    ignored first_yield_day, plant-then-harvest would turn an $80 seed into a
    ~$250 melon on the same tile-day, repeatable on every tile every day. That is
    either the whole game or forbidden; there is no middle case, so it gets its
    own probe on both sides of the mirror.
    """
    def script(step, obs):
        if step == 0:
            return {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", "MELON", 1]]}
        if step == 1:
            return {"farmer": ["PLANT", "MELON"], "hands": [], "market": []}
        if step == 2:
            return {"farmer": ["HARVEST"], "hands": [], "market": []}
        return {"farmer": ["PASS"], "hands": [], "market": []}

    obs, env = _scripted(script, days=1)
    f = env.farms[0]
    carried = f.inventories[0].get("MELON", 0)
    return {"melons_in_hand_after_same_day_harvest": carried,
            "expected_if_blocked": 0,
            "exploit_open": carried > 0}


def check_unwatered_on_plant_day():
    """Does a plant that is never watered on the day it goes in survive the night?

    The mirror creates tiles with consecutive_unwatered=1, so the answer is no --
    which makes 'water the tile you just planted, same day' a hard routing
    constraint rather than a nicety. Worth confirming: it changes the dawn plan.
    """
    def script(step, obs):
        if step == 0:
            return {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", "WHEAT", 1]]}
        if step == 1:
            return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        return {"farmer": ["PASS"], "hands": [], "market": []}

    obs, env = _scripted(script, days=2)
    fx, fy = env.farms[0].farmer
    tile = env.farms[0].tiles[fy][fx]
    kind = tile.get("kind") if isinstance(tile, dict) else tile
    return {"tile_after_one_night": kind, "died": kind != "PLANT"}


def check_harvest_by_day(crop, days_to_try=(2, 3, 4, 5, 8, 10, 11, 12, 13, 14, 16)):
    """Units banked when harvesting `crop` at hour 23 of day D, watered every turn.

    This is the number the planner actually needs: not the peak on the tile, but
    how much is in hand if you commit the harvest action on a given day.
    """
    spec = OBJECT_TABLE[crop]
    horizon = spec.get("max_yield_day", max(spec.get("sched_days", [0]))) + 6
    out = {}
    for D in days_to_try:
        if D > horizon:
            continue

        def script(step, obs, D=D):
            if step == 0:
                return {"farmer": ["PASS"], "hands": [], "market": [["BUY_SEED", crop, 1]]}
            if step == 1:
                return {"farmer": ["PLANT", crop], "hands": [], "market": []}
            if step == D * TURNS_PER_DAY + 23:
                return {"farmer": ["HARVEST"], "hands": [], "market": []}
            return {"farmer": ["WATER"], "hands": [], "market": []}

        _, env = _scripted(script, days=D + 1)
        f = env.farms[0]
        # harvest lands in carried inventory, then auto-dumps to the shed at midnight
        got = f.shed.get(crop, 0) + f.inventories[0].get(crop, 0)
        out[str(D)] = got
    return out


def idle_market_trace():
    """Market inventory for every good over a full episode with BOTH agents passing.

    The cheapest probe here and the one that validates the most load-bearing structural
    claim in the plan. PLAN.md §2.1 says the town drains inventory whether or not anyone
    sells, so inventory falls below I0 and prices sit ABOVE base all season. If that holds,
    every good's inventory slopes down here and its price slopes up. If inventory sits flat
    at 10,000 on the real engine, the price-pump argument is wrong and the sell-late
    conclusion inverts.

    The kink pattern in the slope also measures the shop unlock cadence directly, instead
    of assuming 1-per-3-days capped at 8.
    """
    env = KaggricultureEnv(seed=7)
    rows = []
    while not env.done:
        obs = env._obs()[0]
        step = obs["step"]
        if step % TURNS_PER_DAY in (0, 23):
            m = obs["market"]
            rows.append({"step": step,
                         "market": {"inventory": dict(m["inventory"]),
                                    "prices": dict(m["prices"])}})
        env.step([_pass_action(), _pass_action()])
    return {"n_rows": len(rows), "rows": rows[:80],
            "note": "sampled at hour 0 and 23 each day; nobody sells anything"}


def rule_checks():
    out = {"early_harvest_exploit": check_early_harvest(),
           "unwatered_on_plant_day": check_unwatered_on_plant_day(),
           "harvest_by_day": {}}
    for crop in CROPS:
        out["harvest_by_day"][crop] = check_harvest_by_day(crop)
    return out


def main():
    result = {"probes": {}, "errors": {}}
    for name, fn in (("price_grid", price_grid),
                     ("yield_traces", yield_traces),
                     ("peak_yields", peak_yields),
                     ("rule_checks", rule_checks),
                     ("idle_market_trace", idle_market_trace)):
        try:
            result["probes"][name] = fn()
            print(f"  [ok]   {name}")
        except Exception:
            result["errors"][name] = traceback.format_exc(limit=6)
            print(f"  [FAIL] {name}")

    with open(OUT, "w") as fh:
        json.dump(result, fh, indent=1, default=str)
    print(f"\nwrote {OUT} ({os.path.getsize(OUT)} bytes)")

    py = result["probes"].get("peak_yields", {})
    if py:
        print("\n  peak units on the tile (watered every turn)")
        print("  crop         unfert  (day)   fert  (day)   table caps")
        for crop, row in py.items():
            u, f = row.get("unfert", {}), row.get("fert", {})
            print(f"  {crop:<12} {str(u.get('peak_units')):>5}  {str(u.get('peak_day')):>5}"
                  f"  {str(f.get('peak_units')):>6}  {str(f.get('peak_day')):>5}"
                  f"     unfert {row['table_cap_unfert']} / fert {row['table_cap_fert']}")

    rc = result["probes"].get("rule_checks", {})
    if rc:
        print("\n  units banked if you HARVEST at hour 23 of day D:")
        for crop, row in rc["harvest_by_day"].items():
            cells = "  ".join(f"d{d}={n}" for d, n in row.items())
            print(f"    {crop:<12} {cells}")
        print(f"\n  same-day melon harvest exploit open: "
              f"{rc['early_harvest_exploit']['exploit_open']}")
        print(f"  plant left unwatered on its planting day dies: "
              f"{rc['unwatered_on_plant_day']['died']}")

    im = result["probes"].get("idle_market_trace", {})
    if im and im.get("rows"):
        rows = im["rows"]
        first, last = rows[0], rows[-1]
        print(f"\n  idle market drift over {len(rows)} samples "
              f"(step {first['step']} -> {last['step']}), nobody selling:")
        print("  good         inv d0    inv end   price d0   price end   dir")
        for g in GOODS:
            i0 = first["market"]["inventory"].get(g)
            i1 = last["market"]["inventory"].get(g)
            p0 = first["market"]["prices"].get(g)
            p1 = last["market"]["prices"].get(g)
            if i0 is None or i1 is None:
                continue
            direction = "PUMP" if i1 < i0 else ("flat" if i1 == i0 else "sink")
            print(f"  {g:<12} {i0:>6}   {i1:>7}   {str(p0):>8}   {str(p1):>9}   {direction}")
        print("  PUMP = inventory drained below I0 with nobody selling, so price rises")
        print("  all season and selling LATE beats selling early (PLAN.md §2.1-2.2).")



if __name__ == "__main__":
    main()
