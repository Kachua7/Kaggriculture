"""Trace every animal-path unit op on the vendored engine with failure reasons.

Wraps `eng._apply_unit_action` (module-global lookup at interpreter call time), so the
lens sees exactly what the real engine sees: position, inventory, shed, tile, and
whether FEED actually flipped `fed_today`.

    python3 analysis/feed_trace.py [seed] [opponent]
"""

import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from bridge.real_env import RealEnv  # noqa: E402
from agents import BUILTIN_AGENTS  # noqa: E402


def run(seed: int, opp_name: str) -> None:
    import main as agent_mod
    from agents import BUILTIN_AGENTS

    env = RealEnv(seed)
    eng = env.eng
    orig = eng._apply_unit_action
    ops = Counter()
    clock = {"step": 0}
    orig_interp = eng.interpreter

    def interp_wrapper(state, environment):
        clock["step"] = getattr(state[0].observation, "step", 0) if state else 0
        return orig_interp(state, environment)

    eng.interpreter = interp_wrapper

    def wrapper(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity=100):
        a = action if isinstance(action, list) else []
        op = a[0] if a else "PASS"
        if op in ("FEED", "PICKUP", "PLACE", "CARE", "COLLECT_FERTILIZER"):
            pos = eng._farmer_position(farm, idx)
            inv = eng._farmer_inventory(private, idx)
            tile = farm["tiles"][pos[1]][pos[0]] if pos else None
            shed_w = private["shed"].get("WHEAT", 0)
            kind = tile.get("kind") if isinstance(tile, dict) else tile
            hour = clock["step"] % 24
            on_animal = isinstance(tile, dict) and "animal" in tile
            orig(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity)
            note = ""
            if op == "FEED":
                after = farm["tiles"][pos[1]][pos[0]] if pos else None
                ok = isinstance(after, dict) and after.get("fed_today")
                ops["FEED"] += 1
                ops["FEED_OK"] += 1 if ok else 0
                if not ok:
                    note = (f"  FAIL inv_w={inv.get('WHEAT', 0)} shed_w={shed_w} "
                            f"on_animal={on_animal} fed_before={isinstance(tile, dict) and tile.get('fed_today')}")
            elif op == "PICKUP" and len(a) > 1 and a[1] in ("COW", "SHEEP", "GOOSE"):
                got = eng._farmer_inventory(private, idx).get(a[1], 0)
                ops["PICKUP_ANIMAL"] += 1
                ops["PICKUP_ANIMAL_OK"] += 1 if got else 0
                note = f"  got={got} shed={private['shed'].get(a[1], 0)}"
            elif op == "PLACE" and len(a) > 1 and a[1] in ("COW", "SHEEP", "GOOSE"):
                ops["PLACE"] += 1
                note = "  placed" if isinstance(tile, dict) and "animal" in tile else "  PLACE FAIL"
            print(f"d{day:>2} h{hour:>2} p{idx} {op}{a[1:]} pos={pos} tile={kind} inv={dict(inv)} "
                  f"shedW={shed_w}{note}", flush=True)
            return
        orig(farm, private, idx, action, board_size, day, turns_per_day, shed_capacity)

    eng._apply_unit_action = wrapper

    opp = BUILTIN_AGENTS[opp_name]
    while not env.done:
        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)
        act0 = agent_mod.agent(obs0, env.config)
        act1 = opp(obs1)
        env.step([act0, act1])
    print(f"== seed {seed}: banks {env.banks()} | FEED {ops['FEED_OK']}/{ops['FEED']} ok, "
          f"PICKUP_animal {ops['PICKUP_ANIMAL_OK']}/{ops['PICKUP_ANIMAL']}, PLACE {ops['PLACE']}")


def main() -> None:
    args = sys.argv[1:]
    opp = "arch_passive"
    if args and args[-1] in BUILTIN_AGENTS:
        opp = args.pop()
    seeds = [int(a) for a in args] or [0]
    for s in seeds:
        run(s, opp)


if __name__ == "__main__":
    main()
