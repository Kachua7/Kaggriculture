"""A/B for the dairy-recipe herd recipe (2026-09-19): 8-cow target vs the incumbent's 2.

    python3 analysis/ab_herd.py --block 1 --arm control   # incumbent n_animals=2
    python3 analysis/ab_herd.py --block 1 --arm ramp      # 8 cows, day-gated ramp
    python3 analysis/ab_herd.py --block 1 --arm ungated   # 8 cows, no ramp (recipe's
                                                          # warned bankruptcy mode)
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=1, choices=(1, 2))
    ap.add_argument("--arm", default="ramp",
                    choices=("control", "ramp", "ungated", "paceoff"))
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    lo, hi = (0, 24) if a.block == 1 else (24, 48)
    params = {
        "control": None,
        "ramp": {"n_animals": 8, "herd_ramp": True, "ramp_cap_early": 2, "ramp_full_day": 14},
        "ungated": {"n_animals": 8, "herd_ramp": False},
        # Dawn-pace bisect (2026-09-19): default build WITH the cap vs this arm WITHOUT.
        "paceoff": {"dawn_pace": None},
    }[a.arm]
    evaluate(range(lo, hi),
             ["arch_passive", "arch_hoarder", "arch_flooder",
              "arch_snapper", "arch_meta_labor", "arch_meta_allin"],
             workers=8, params=params)
