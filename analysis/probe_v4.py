"""Behavior probe: does the patched V3 fire the fixes the seed-466488175 post-mortem asked for?

Run on the REAL tier (vendored 1.32.7), self-play, seed 466488175 by default:

    python3 analysis/probe_v4.py --seed 466488175 [--mod kagfarm_policy_v3]
"""
import argparse
import collections
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=466488175)
    ap.add_argument("--mod", default="kagfarm_policy_v3")
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from bridge.real_env import RealEnv

    mod = __import__(a.mod)

    env = RealEnv(a.seed)
    views = [env._obs_view(0), env._obs_view(1)]

    melon_seeds = [0, 0]
    animal_buys = [collections.Counter(), collections.Counter()]
    land_buys = [0, 0]
    dawn = {}          # day -> (cash0, cash1, hands0, hands1, past0, coop0, anim0, anim1)
    hire_ops = [0, 0]

    while not env.done:
        acts = []
        for seat in (0, 1):
            view = dict(views[seat])
            view["player"] = seat          # never trust setdefault: a stale 0 shares one Policy
            view["step"] = env.t
            act = mod.agent(view, env.config)
            acts.append(act)
            mkt = act.get("market") or []
            for o in mkt:
                if o[0] == "BUY_SEED" and o[1] == "MELON":
                    melon_seeds[seat] += o[2]
                elif o[0] == "BUY_ANIMAL":
                    animal_buys[seat][o[1]] += o[2]
                elif o[0] == "BUY_LAND":
                    land_buys[seat] += 1
                elif o[0] == "HIRE":
                    hire_ops[seat] += 1
            if view.get("hour") == 0 and seat == 0:
                d = views[seat]["day"]
                f = view["farms"][0]
                tiles = f["tiles"]
                past = sum(1 for row in tiles for t in row
                           if isinstance(t, dict) and t.get("kind") == "PASTURE")
                coop = sum(1 for row in tiles for t in row
                           if isinstance(t, dict) and t.get("kind") == "COOP")
                anim = sum(1 for row in tiles for t in row
                           if isinstance(t, dict) and "animal" in t)
                dawn[d] = (f["money"], view["farms"][1]["money"],
                           len(f["hands"]), len(view["farms"][1]["hands"]),
                           past, coop, anim,
                           sum(1 for row in tiles for t in row
                               if isinstance(t, dict) and t.get("kind") == "PLANT"
                               and t.get("crop") == "MELON"))
        env.step(acts)
        views = [env._obs_view(0), env._obs_view(1)]

    banks = env.banks()
    print(f"seed {a.seed}  mod={a.mod}")
    print(f"final banks: p0 ${banks[0]:,.0f}   p1 ${banks[1]:,.0f}")
    print(f"melon seeds bought: p0={melon_seeds[0]}  p1={melon_seeds[1]}")
    print(f"animal buys: p0={dict(animal_buys[0])}  p1={dict(animal_buys[1])}")
    print(f"land buys: p0={land_buys[0]}  p1={land_buys[1]}")
    print(f"hire orders: p0={hire_ops[0]}  p1={hire_ops[1]}")
    print("\nday |  cash_p0  cash_p1 | hands0 hands1 | past coop anim0 anim1 | melon_tiles0")
    for d in sorted(dawn):
        c0, c1, h0, h1, pa, co, an, mel = dawn[d]
        print(f"{d:3d} | {c0:8.0f} {c1:8.0f} | {h0:5d} {h1:6d} | {pa:4d} {co:4d} {an:5d} {an:5d} | {mel:4d}")
