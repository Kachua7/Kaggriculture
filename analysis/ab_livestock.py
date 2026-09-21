"""Real-tier A/B/C for the livestock economy (2026-09-19, ladder 110874286).

The winner earned ~$144k of $199k revenue from animals on a ~22-herd. Our blocker was
assembly speed (n_build=1/n_buy=1 hardcoded). This driver measures the paced mechanism
on the REAL tier only (the mirror is drifted; see calibration/live.md) with the four
failure modes each getting a number:

    python3 analysis/ab_livestock.py --arm a   # default: n=2, pace=1, hands=10 (control)
    python3 analysis/ab_livestock.py --arm b   # livestock: n=20, pace=4, hands=10
    python3 analysis/ab_livestock.py --arm c   # livestock: n=20, pace=4, hands=12

Metrics to read per arm: bank mean/p10/min/max, win, `lost` (shed overflow discards),
`spent` (market cash burned -- wheat-feed spiral shows here), thirst, tiles/day.
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="a", choices=("a", "b", "c", "d"))
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--opps", default="self,arch_passive")
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    params = {
        "a": None,
        "b": {"n_animals": 20, "animal_pace": 4},
        "c": {"n_animals": 20, "animal_pace": 4, "max_hands": 12},
        # Mid-herd bisect: the 20-herd funnel shows all animals escaping (feed chain
        # breaks at scale); 8 is the size the incumbent's feeding historically served.
        "d": {"n_animals": 8, "animal_pace": 3, "max_hands": 11},
    }[a.arm]
    evaluate(range(a.seeds), a.opps.split(","), workers=1, params=params,
             engine="real")
