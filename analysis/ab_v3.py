"""Head-to-head: our CARE build (`main`) vs the V3 rewrite (`kagfarm_policy_v3`).

Same seeds x opponents for both arms; the panel is the project's 24-seed x 6-arch
synthetic field. Run block 1 and block 2 separately for the disjoint-seed gate:

    python3 analysis/ab_v3.py --block 1
    python3 analysis/ab_v3.py --block 2

The two arms must be separate *processes* (one --arm each) because both register
a module named `kagfarm.policy`-alike under different names but share PARAMS
machinery via eval.py's params channel; keeping them in their own process makes
the comparison exactly the shipped behavior of each build.
"""
import argparse
import sys

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int, default=1, choices=(1, 2))
    ap.add_argument("--v3mod", default="kagfarm_policy_v3")
    ap.add_argument("--arm", required=True, choices=("ours", "v3"))
    a = ap.parse_args()

    sys.path.insert(0, ".")
    from eval import evaluate

    lo, hi = (0, 24) if a.block == 1 else (24, 48)
    agent = "main" if a.arm == "ours" else a.v3mod
    evaluate(range(lo, hi),
             ["arch_passive", "arch_hoarder", "arch_flooder",
              "arch_snapper", "arch_meta_labor", "arch_meta_allin"],
             agent_mod=agent, workers=8)
