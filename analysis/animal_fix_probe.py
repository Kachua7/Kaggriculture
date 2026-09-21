"""H4 end-to-end probe: does the fixed agent run the animal pipeline on the corrected mirror?

Before the H4 fix this probe read, on every seed: structures built yes, animals placed 0,
product revenue $0 -- the mirror's lax PICKUP let the old one-leg job pass locally while the
ladder rotted every cow. After the fix the same probe must show placements > 0 and product
revenue > 0, or the three-act carry job is still broken.

    python3 analysis/animal_fix_probe.py [n_seeds]
"""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from eval import run_one                                     # noqa: E402
from kagfarm.constants import ANIMAL_PRODUCT                 # noqa: E402


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    products = set(ANIMAL_PRODUCT.values())
    print(f"{'seed':>4} {'bank':>9} {'structs':>8} {'animals':>8} "
          f"{'feed_wheat':>10} {'prod_units':>10} {'prod_$':>9} {'fert_sold':>9}")
    tot_prod = 0
    for seed in range(n):
        r = run_one((seed, "arch_passive", "main", None))
        rev, units = r.get("revenue") or {}, r.get("units") or {}
        prod_units = sum(units.get(g, 0) for g in products)
        prod_rev = sum(rev.get(g, 0.0) for g in products)
        feed_wheat = units.get("WHEAT", 0)  # wheat that came back out = fed to animals
        # Structures and placements are not in run_one's metrics; approximate via the
        # product side (placement is what makes product revenue possible) and wheat reflow.
        tot_prod += prod_units
        print(f"{seed:>4} {r['bank']:>9,.0f} {'-':>8} {'-':>8} "
              f"{feed_wheat:>10} {prod_units:>10} {prod_rev:>9,.0f} "
              f"{units.get('FERTILIZER', 0):>9}")
    print(f"\ntotal product units over {n} seeds: {tot_prod} "
          f"({'PIPELINE LIVE' if tot_prod > 0 else 'PIPELINE DEAD -- fix incomplete'})")


if __name__ == "__main__":
    main()
