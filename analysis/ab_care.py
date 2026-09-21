"""A/B driver for the CARE switch on the panel, by seed block.

    python3 analysis/ab_care.py --block 1 --care on
    python3 analysis/ab_care.py --block 2 --care off
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=1, choices=(1, 2))
    ap.add_argument("--care", default="on", choices=("on", "off"))
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    lo, hi = (0, 24) if a.block == 1 else (24, 48)
    params = {"animal_care": True} if a.care == "on" else None
    evaluate(range(lo, hi),
             ["arch_passive", "arch_hoarder", "arch_flooder",
              "arch_snapper", "arch_meta_labor", "arch_meta_allin"],
             workers=8, params=params)
