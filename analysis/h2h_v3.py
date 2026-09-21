"""Direct head-to-head on the REAL tier (vendored 1.32.7): V3 rewrite vs our CARE build.

Each seed is played twice with the seats swapped so position asymmetry cancels:

    python3 analysis/h2h_v3.py --seeds 12
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from bridge.real_env import RealEnv
    import kagfarm_policy_v3 as v3
    import importlib
    main_mod = importlib.import_module("main")

    def play(seed, v3_seat):
        env = RealEnv(seed)
        views = [env._obs_view(0), env._obs_view(1)]
        while not env.done:
            acts = []
            for seat in (0, 1):
                if seat == v3_seat:
                    acts.append(v3.agent(dict(views[seat]), env.config))
                else:
                    acts.append(main_mod.agent(dict(views[seat]), env.config))
            env.step(acts)
            views = [env._obs_view(0), env._obs_view(1)]
        banks = env.banks()
        return banks

    v3_wins = ours_wins = ties = 0
    b3 = b1 = 0.0
    for s in range(a.seeds):
        for v3_seat in (0, 1):
            banks = play(s, v3_seat)
            v3_bank = banks[v3_seat]
            ours_bank = banks[1 - v3_seat]
            b3 += v3_bank
            b1 += ours_bank
            if v3_bank > ours_bank:
                v3_wins += 1
            elif v3_bank < ours_bank:
                ours_wins += 1
            else:
                ties += 1
        print(f"seed {s:3d}: V3 {banks[v3_seat]:8.0f} vs OURS {banks[1 - v3_seat]:8.0f} "
              f"(V3 at seat {v3_seat})")

    n = 2 * a.seeds
    print(f"\nH2H over {n} games: V3 {v3_wins} - OURS {ours_wins} - ties {ties}")
    print(f"mean banks: V3 ${b3 / n:,.0f}  OURS ${b1 / n:,.0f}")
