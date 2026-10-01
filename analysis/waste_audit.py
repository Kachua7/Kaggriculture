"""Full waste audit: every unit of resource and unit-turn our seat burns.

Waste classes (engine-exact, monkeypatching the mirror engine):
  1. shed overflow    - units discarded by _add_shed (capacity 100), by good
  2. escapes          - animals hitting consecutive_unfed >= 2 (asset dies)
  3. unfed days       - placed-animal days without feed (destroys banked care)
  4. unwatered days   - plant-days without water (two in a row = death)
  5. thirst deaths    - plants lost to consecutive_unwatered >= 2
  6. fert uncollected - animal-days whose fertilizer flag survived to dusk
  7. end-state shed   - unsold inventory at t720 ($0 at the buzzer)
  8. unharvested      - standing units on PLANT tiles at t720 ($0)
  9. unspent seeds    - seeds bought but never planted
 10. idle turns       - PASS ops by employed units on >=6-unit rosters
 11. cash rot         - peak intra-season bank vs final bank

Usage: python3 analysis/waste_audit.py [n_seeds]
"""
import copy
import sys
from collections import defaultdict

sys.path.insert(0, ".")
import kagfarm.policy as P
from engine import KaggricultureEnv
from kagfarm.constants import OBJECT_TABLE
import main

DEFAULTS = copy.deepcopy(P.PARAMS)


def audit_seed(seed):
    P.PARAMS = copy.deepcopy(DEFAULTS)
    main._POLICIES.clear()
    env = KaggricultureEnv(episode_steps=720, seed=seed)

    W = defaultdict(int)
    W_goods = defaultdict(int)
    money_at_dawn = {}
    pass_by_day = defaultdict(int)
    roster_by_day = {}
    fert_missed_by_day = {}

    orig_add = env._add_shed

    def add_shed(f, item, n):
        before = f.shed.get(item, 0)
        r = orig_add(f, item, n)
        if f is env.farms[0]:
            gained = f.shed.get(item, 0) - before
            dropped = n - gained
            if dropped > 0:
                W["overflow_units"] += dropped
                W_goods[item] += dropped
        return r

    env._add_shed = add_shed

    orig_ra = env._refresh_animal

    def refresh_animal(f, tile):
        if f is env.farms[0] and tile.get("animal"):
            if not tile.get("fed_today"):
                W["unfed_animal_days"] += 1
        orig_ra(f, tile)
        if f is env.farms[0] and tile.get("kind") in ("PASTURE", "COOP") \
                and not tile.get("animal"):
            W["escapes"] += 1

    env._refresh_animal = refresh_animal

    died = False

    orig_rp = env._refresh_plant

    def refresh_plant(f, x, y, tile):
        nonlocal died
        died = False
        if f is env.farms[0] and tile.get("kind") == "PLANT":
            if not tile.get("watered_today"):
                W["unwatered_plant_days"] += 1
                # waste-conditioned: a WATER today would have added +1 only inside the
                # gain window and below cap (engine _grant_yield contract). Outside it,
                # skipping water is free -- not waste.
                spec = OBJECT_TABLE.get(tile.get("crop"))
                if spec:
                    age = env.day - tile.get("planted_day", env.day)
                    in_win = (spec.get("bonus_start", 0) <= age <= spec.get("bonus_end", -1)) \
                        if spec.get("kind") == "one_time" \
                        else (age in spec.get("sched_days", []) and tile.get("_sched_done", 0) < len(spec.get("sched_days", [])))
                    if in_win and tile.get("yield_units", 0) < spec.get("max_yield", 0):
                        W["gain_window_missed"] += 1
            died = tile.get("consecutive_unwatered", 0) >= 2
        orig_rp(f, x, y, tile)
        if f is env.farms[0] and died:
            t = f.tiles[y][x]
            if isinstance(t, dict) and t.get("kind") == "WEED":
                W["thirst_deaths"] += 1

    env._refresh_plant = refresh_plant

    obs = env._obs()
    prev_day = None
    while not env.done:
        day = obs[0]["day"]
        if day != prev_day:
            prev_day = day
            farms = obs[0].get("farms") or []
            money_at_dawn[day] = farms[0]["money"] if farms else None
        acts = [main.agent(o) for o in obs]
        a0 = acts[0]
        n_pass = sum(1 for h in (a0.get("hands") or []) if not h or h[0] == "PASS")
        if not a0.get("farmer") or a0["farmer"][0] == "PASS":
            n_pass += 1
        pass_by_day[day] += n_pass
        roster_by_day[day] = len(a0.get("hands") or []) + 1
        obs, _ = env.step(acts)
        hr = obs[0].get("hour", 0)
        farms = obs[0].get("farms") or []
        if farms and hr >= 22:
            tiles = farms[0].get("tiles") or []
            flat = tiles if (tiles and isinstance(tiles[0], dict)) else \
                [t for row in tiles for t in (row or [])]
            missed = 0
            for t in flat:
                if isinstance(t, dict) and t.get("kind") in ("PASTURE", "COOP") \
                        and t.get("animal") and t.get("fertilizer_available"):
                    missed += 1
            fert_missed_by_day[day] = missed

    f0 = env.farms[0]
    end_shed = dict(f0.shed)
    W["end_shed_units"] = sum(end_shed.values())
    standing = defaultdict(int)
    weeds = empties = 0
    for row in f0.tiles:
        for t in row:
            if t is None:
                empties += 1
            elif isinstance(t, dict):
                if t.get("kind") == "PLANT":
                    standing[t.get("crop")] += t.get("yield_units", 0)
                elif t.get("kind") == "WEED":
                    weeds += 1
    W["unharvested_units"] = sum(standing.values())
    W["weeds_at_end"] = weeds
    W["empty_tiles_at_end"] = empties
    W["unspent_seeds"] = sum(f0.seeds.values())
    W["fert_missed_days"] = sum(1 for v in fert_missed_by_day.values() if v > 0)
    W["fert_missed_animal_days"] = sum(fert_missed_by_day.values())
    peak = max(v for v in money_at_dawn.values() if v is not None)
    W["peak_bank"] = peak
    W["final_bank"] = f0.money
    W["cash_rot"] = peak - f0.money
    idle = {d: p for d, p in pass_by_day.items()
            if p >= 6 and roster_by_day.get(d, 0) >= 6}
    return (dict(W), dict(W_goods), end_shed, dict(standing), idle,
            dict(money_at_dawn), fert_missed_by_day)


def main_run(n_seeds=5):
    agg = defaultdict(int)
    for s in range(n_seeds):
        W, Wg, shed, standing, idle, mdawn, fm = audit_seed(s)
        for k, v in W.items():
            agg[k] += v
        g = lambda k: W.get(k, 0)
        print(f"seed {s}: bank={g('final_bank'):.0f} overflow={g('overflow_units')} "
              f"escapes={g('escapes')} unfed={g('unfed_animal_days')} "
              f"unwatered={g('unwatered_plant_days')} thirst={g('thirst_deaths')} "
              f"fert_missed={g('fert_missed_animal_days')} "
              f"end_shed={g('end_shed_units')} unharvested={g('unharvested_units')} "
              f"seeds={g('unspent_seeds')} weeds={g('weeds_at_end')} "
              f"peak={g('peak_bank'):.0f} cash_rot={g('cash_rot'):.0f} "
              f"idle_days={len(idle)}")
        if idle:
            print("    idle days:", dict(sorted(idle.items())[:8]))
        if Wg:
            print("    overflow goods:", Wg)
        print("    end shed:", shed)
        print("    standing:", standing)
        late = {d: v for d, v in fm.items() if d >= 12 and v > 0}
        if late:
            print("    fert-missed d12+:", late)
    print("\nAGGREGATE over", n_seeds, "seeds:")
    for k in sorted(agg):
        print(f"  {k}: {agg[k]}")


if __name__ == "__main__":
    main_run(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
