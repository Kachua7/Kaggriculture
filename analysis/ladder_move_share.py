"""Full-season move-share from recorded ladder actions, both seats.

The 69% move-share claim predates submission12; this measures the CURRENT build's
real-field move-share on the fresh tapes to confirm or retire the premise.

Usage: python3 analysis/ladder_move_share.py ep.json [ep2.json ...]
"""
import json
import sys
from collections import defaultdict

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def main():
    for path in sys.argv[1:]:
        ep = json.load(open(path))
        steps = ep["steps"]
        names = ep.get("info", {}).get("TeamNames") or ["p0", "p1"]
        print(f"\n=== {path} ===")
        for p in (0, 1):
            tot = mv = 0
            per_day = defaultdict(lambda: [0, 0])  # day -> [moves, all]
            for i, row in enumerate(steps):
                d = i // 24
                act = row[p].get("action") or {}
                if not isinstance(act, dict):
                    continue
                ops = [act.get("farmer")] + list(act.get("hands") or [])
                for h in ops:
                    if not h:
                        continue
                    op = str(h[0]).upper()
                    tot += 1
                    per_day[d][1] += 1
                    if op in MOVES:
                        mv += 1
                        per_day[d][0] += 1
            share = mv / max(1, tot)
            print(f"{names[p] if p < len(names) else p}: {mv}/{tot} = {share:.1%}")
            row = " ".join(f"d{d}:{c[0] / max(1, c[1]):.0%}" for d, c in sorted(per_day.items())
                           if c[1] >= 10)
            print("  " + row)


if __name__ == "__main__":
    main()
