"""Real-tier shepherd-stream A/B (scope v4, 2026-09-19).

The livestock lane failed twice on turn ECONOMICS (A/B/C/D run: herds of 7 animals all
escaped -- the feed chain never scaled). The shepherd stream fixes the execution layer
(funnel: escapes 0 across 6 episodes at 4-7 live animals). This driver measures whether
the fixed stream actually PAYS on the real tier -- the bar from the approved plan:

    ship if mean >= control + $8k with no p10 collapse

    python3 analysis/ab_shepherd.py --arm a   # control (byte-identical default build)
    python3 analysis/ab_shepherd.py --arm s8  # shepherd stream, 8-herd target
    python3 analysis/ab_shepherd.py --arm s20 # shepherd stream, 20-herd target

Metrics: bank mean/p10/min/max, wins, `lost` (overflow discards), `spent` (the wheat
spiral shows here), thirst, tiles/day. 12 seeds x {self, arch_passive} per arm.
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="a", choices=("a", "s8", "s20"))
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--opps", default="self,arch_passive")
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    params = {
        "a": None,
        # Shares sized to the targets (share ~= target/2 + 1 -- ~2 animals per shepherd
        # unit per the funnel envelope); hands raised one step to fund the extra shepherds.
        "s8": {"n_animals": 8, "animal_pace": 3, "shepherd_mode": 1,
               "shepherd_share": 4, "max_hands": 11},
        "s20": {"n_animals": 20, "animal_pace": 4, "shepherd_mode": 1,
                "shepherd_share": 9, "max_hands": 13},
    }[a.arm]
    evaluate(range(a.seeds), a.opps.split(","), workers=1, params=params,
             engine="real")
