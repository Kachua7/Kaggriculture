"""Mirror smoke for elite_counter_v1 (P0 block).

Runs the vendored engine, seed 0, our agent in both seats. Two arms:
  baseline: PARAMS as shipped (elite_script=False)
  elite:    opening_led + elite_script ON

Prints the day-0 market timeline (first 6 turns), the herd timeline, and final banks.
Usage: python3 analysis/smoke_elite.py [--arm elite|baseline] [--seed N]
"""
import argparse
import sys

sys.path.insert(0, ".")

from engine import KaggricultureEnv
from kagfarm import policy as P
import main


def run(seed, arm):
    # Reset knobs first: PARAMS.update from a previous run() call in the same process
    # would otherwise poison the baseline arm (both arms reported identical banks).
    P.PARAMS.update({"opening_led": False, "elite_script": False, "melon_opening": 24})
    P.PARAMS.update({"led_roster_floor": 0, "land_early": False})
    if arm == "elite":
        P.PARAMS.update({"opening_led": True, "elite_script": True, "melon_opening": 0})
    elif arm == "skeleton":
        from kagfarm.constants import majkel_skeleton
        P.PARAMS.update(majkel_skeleton())
    main._POLICIES.clear()
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()
    herd = []          # (day, placed cows, placed sheep, shed animals)
    money = []
    d0_orders = []
    while not env.done:
        day = obs[0]["day"]
        step = obs[0].get("step", 0)
        acts = [main.agent(o) for o in obs]
        if day == 0 and step < 6:
            d0_orders.append((step, acts[0].get("market")))
        obs, _ = env.step(acts)
        farms = obs[0].get("farms") or obs[1].get("farms")
        if farms and obs[0].get("hour", 0) == 0:
            counts = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
            # tiles may be a flat list of tile dicts or a row-major list of rows;
            # handle both so the census never silently counts zero.
            tiles = farms[0].get("tiles") or []
            flat = tiles if (tiles and isinstance(tiles[0], dict)) else \
                [t for row in tiles for t in (row or [])]
            for t in flat:
                if isinstance(t, dict) and t.get("animal") in counts:
                    counts[t["animal"]] += 1
            shed = (obs[0].get("private") or {}).get("shed") or {}
            herd.append((obs[0]["day"], dict(counts),
                         {k: v for k, v in shed.items() if k in counts}))
            money.append((obs[0]["day"], farms[0].get("money", 0)))
    bank = [f.money for f in env.farms] if getattr(env, "farms", None) else None
    return d0_orders, herd, money, bank


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--arm", choices=["elite", "baseline", "skeleton"], default="elite")
    a = ap.parse_args()
    d0, herd, money, bank = run(a.seed, a.arm)
    print(f"== arm={a.arm} seed={a.seed} ==")
    print("day-0 orders (first 6 turns):")
    for s, m in d0:
        print(f"  t{s}: {m}")
    print("herd by day (placed | shed-animals):")
    for d, c, sh in herd[:20]:
        print(f"  d{d}: {c} | {sh}")
    if herd:
        print("  ...")
        for d, c, sh in herd[-6:]:
            print(f"  d{d}: {c} | {sh}")
    print("bank checkpoints:", money[:6], "...", money[-4:])
    print("final banks:", bank)
