"""Bisect driver: run kagfarm_policy_v3 on the panel under KAG_OVERRIDE variants.

    python3 analysis/ab_grid.py          # runs the E-matrix, one line per variant
"""
import json
import os
import sys

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", default="e1")
    ap.add_argument("--block", type=int, default=1)
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    KAPPA_V3 = {"MILK": 0.92, "EGG": 0.95, "WOOL": 0.70,
                "STRAWBERRY": 0.85, "TOMATO": 0.90, "WHEAT": 1.00,
                "CARROT": 1.00, "MELON": 0.50}

    variants = {
        # sheep cap off only (wool revenue restored)
        "e1": {"sheep_cap": 0},
        # + kappa back to V3's original
        "e2": {"sheep_cap": 0, "kappa": KAPPA_V3},
        # + hands back to 12  (everything structural but the original tuning)
        "e3": {"sheep_cap": 0, "kappa": KAPPA_V3, "hands": 12},
        # hands off only (kappa stays raised, wool capped)
        "e4": {"hands": 12},
        # everything reverted except the structural fixes (melon, ladder, structures)
        "e5": {"sheep_cap": 0, "kappa": KAPPA_V3, "hands": 12, "hire_reserve": 500},

        # neighbourhood of e3
        "f1": {"sheep_cap": 0, "kappa": KAPPA_V3, "hands": 13},
        "f2": {"sheep_cap": 0, "hands": 12},
        "g1": {"sheep_cap": 0, "kappa": KAPPA_V3, "hands": 12, "melon_wave_floor": 999.0},
    }
    lo, hi = (0, 24) if a.block == 1 else (24, 48)
    for name, over in variants.items():
        if a.grid != "all" and a.grid != name:
            continue
        os.environ["KAG_OVERRIDE"] = json.dumps(over)
        print(f"\n== {name}: {over}")
        evaluate(range(lo, hi),
                 ["arch_passive", "arch_hoarder", "arch_flooder",
                  "arch_snapper", "arch_meta_labor", "arch_meta_allin"],
                 agent_mod="kagfarm_policy_v3", workers=8)
