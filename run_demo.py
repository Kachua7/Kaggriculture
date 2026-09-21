"""
Run a Kaggriculture episode locally.

Usage:
    python run_demo.py --p0 heuristic --p1 starter --steps 720 --seed 1
    python run_demo.py --p0 heuristic --p1 random --steps 200 --plot money.png
"""
import argparse
import json
import sys

from engine import KaggricultureEnv
from agents import BUILTIN_AGENTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--p0", default="heuristic", help="builtin name or python file exposing agent(obs)")
    ap.add_argument("--p1", default="starter")
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--every", type=int, default=24, help="print money every N turns")
    ap.add_argument("--plot", default=None, help="path to save a money-over-time PNG")
    ap.add_argument("--dump-replay", default=None, help="path to save full turn-by-turn JSON")
    args = ap.parse_args()

    def resolve(name):
        if name in BUILTIN_AGENTS:
            return name
        # treat as "modulename:function" or a file path with agent()
        if ":" in name:
            mod, fn = name.split(":")
            m = __import__(mod)
            return getattr(m, fn)
        raise ValueError(f"Unknown agent '{name}'. Use one of {list(BUILTIN_AGENTS)} or 'module:function'.")

    p0 = resolve(args.p0)
    p1 = resolve(args.p1)

    env = KaggricultureEnv(episode_steps=args.steps, seed=args.seed)
    fns = [BUILTIN_AGENTS[p0] if isinstance(p0, str) else p0,
           BUILTIN_AGENTS[p1] if isinstance(p1, str) else p1]

    money_series = [[], []]
    obs = env._obs()
    money_series[0].append(obs[0]["farms"][0]["money"])
    money_series[1].append(obs[0]["farms"][1]["money"])

    while not env.done:
        acts = [fns[0](obs[0]), fns[1](obs[1])]
        obs, done = env.step(acts)
        if env.t % args.every == 0 or done:
            m0 = obs[0]["farms"][0]["money"]
            m1 = obs[0]["farms"][1]["money"]
            money_series[0].append(m0)
            money_series[1].append(m1)
            print(f"t={env.t:4d} day={env.day:2d} hour={env.hour:2d}  "
                  f"P0({args.p0})=${m0:9.2f}   P1({args.p1})=${m1:9.2f}   shops={len(env.shops)}")

    final = obs[0]["farms"]
    print()
    print(f"FINAL  P0({args.p0}) = ${final[0]['money']:.2f}   P1({args.p1}) = ${final[1]['money']:.2f}")
    if final[0]["money"] > final[1]["money"]:
        print("Winner: P0")
    elif final[1]["money"] > final[0]["money"]:
        print("Winner: P1")
    else:
        print("Tie")

    if args.dump_replay:
        with open(args.dump_replay, "w") as fh:
            json.dump(env.history, fh, default=str)
        print(f"Replay written to {args.dump_replay}")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = list(range(0, len(money_series[0]) * args.every, args.every))[:len(money_series[0])]
        plt.figure(figsize=(9, 5))
        plt.plot(xs, money_series[0], label=f"P0 ({args.p0})")
        plt.plot(xs, money_series[1], label=f"P1 ({args.p1})")
        plt.xlabel("turn")
        plt.ylabel("bank balance ($)")
        plt.title("Kaggriculture — bank balance over the season")
        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(args.plot, dpi=140)
        print(f"Plot written to {args.plot}")


if __name__ == "__main__":
    main()
