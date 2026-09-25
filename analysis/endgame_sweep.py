"""Endgame (d24-29) audit for ladder episodes.

For each day in the window, for both seats:
- bank at day start / day end, day delta
- gross BUY_PRODUCT spend vs SELL income (settled via money[i] - money[i-1])
- animal purchases (BUY_ANIMAL) and their cost
- number of sell orders issued vs units (from orders, best-effort)

Usage: python3 analysis/endgame_sweep.py ep1.json [ep2.json ...]
"""
import json
import sys


def load(path):
    with open(path) as f:
        return json.load(f)


def seat_banks(ep):
    steps = ep["steps"]
    # steps[i][p]["observation"]["farms"] may not exist; use reward if banks missing
    banks = {0: [], 1: []}
    for i, srow in enumerate(steps):
        for p in (0, 1):
            obs = srow[p].get("observation", {})
            farms = obs.get("farms")
            if farms and p < len(farms) and isinstance(farms[p], dict):
                banks[p].append(farms[p].get("money"))
            else:
                # fallback: cumulative reward
                rew = srow[p].get("reward")
                banks[p].append(rew)
    return banks


def day_of(i):
    return i // 24


def main():
    for path in sys.argv[1:]:
        ep = load(path)
        steps = ep["steps"]
        banks = seat_banks(ep)
        n = len(steps)
        names = ep.get("info", {}).get("TeamNames") or ep.get("teamNames") or ["p0", "p1"]
        print(f"\n=== {path}  ({n} steps)  teams={names} ===")
        for p in (0, 1):
            final = banks[p][-1]
            print(f"\n-- seat {p} ({names[p] if p < len(names) else p})  final={final}")
            start = int(sys.argv[sys.argv.index('--from') + 1]) if '--from' in sys.argv else 20
            for d in range(start, (n + 23) // 24):
                lo, hi = d * 24, min((d + 1) * 24, n)
                if lo >= n:
                    break
                delta = (banks[p][hi - 1] or 0) - (banks[p][lo - 1] if lo > 0 else 0)
                print(f"  d{d:2d}: bank {banks[p][lo] or 0:>9,.0f} -> {banks[p][hi - 1] or 0:>9,.0f}  delta {delta:>+10,.0f}")


if __name__ == "__main__":
    main()
