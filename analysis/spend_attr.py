"""Spend/income attribution per day from a ladder episode.

Alignment (KT_V2 validated): steps[i][p]["action"] causes money[i] - money[i-1].
Classifies each turn's action, sums money deltas by class and day.

Usage: python3 analysis/spend_attr.py ep.json [day_lo day_hi]
"""
import json
import sys


def main():
    path = sys.argv[1]
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 11
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 19
    ep = json.load(open(path))
    steps = ep["steps"]
    names = ep.get("info", {}).get("TeamNames") or ["p0", "p1"]

    def acts_of(row):
        act = row.get("action") or {}
        if isinstance(act, dict):
            out = []
            f = act.get("farmer")
            if f:
                out.append(("F", f))
            for h in act.get("hands") or []:
                out.append(("H", h))
            for m in act.get("market") or []:
                out.append(("M", m))
            return out
        return []

    def klass(a):
        if not a:
            return None
        a = str(a[0]).upper() if isinstance(a, (list, tuple)) and a else str(a).upper()
        if a in ("MOVE", "EAST", "WEST", "NORTH", "SOUTH"):
            return "MOVE"
        if a == "HIRE":
            return "HIRE"
        if a == "BUILD":
            return "BUILD"
        if a == "BUY_ANIMAL":
            return "ANIMAL"
        if a == "BUY_PRODUCT":
            return "BUYPRD"
        if "SEED" in a:
            return "SEED"
        if a in ("SELL", "SELL_PRODUCT"):
            return "SELL"
        if a in ("PASS",):
            return None
        return a.capitalize()

    for p in (0, 1):
        # banks from observation or fallback cumulative reward
        banks = []
        for srow in steps:
            obs = srow[p].get("observation", {})
            farms = obs.get("farms")
            if farms and p < len(farms) and isinstance(farms[p], dict):
                banks.append(farms[p].get("money"))
            else:
                banks.append(srow[p].get("reward"))
        if banks[0] is None:
            banks[0] = 0
        print(f"\n=== {names[p] if p < len(names) else p} (seat {p}) d{lo}-{hi} ===")
        # aggregate: class -> day -> delta
        agg = {}
        counts = {}
        for i in range(max(1, lo * 24), min(hi * 24 + 1, len(steps))):
            d = i // 24
            delta = (banks[i] or 0) - (banks[i - 1] or 0)
            for who, a in acts_of(steps[i][p]):
                k = klass(a)
                if k is None:
                    continue
                agg.setdefault(k, {}).setdefault(d, 0)
                agg[k][d] += delta / max(1, len(acts_of(steps[i][p])))
                counts.setdefault(k, {}).setdefault(d, 0)
                counts[k][d] += 1
        classes = sorted(agg.keys(), key=lambda k: -sum(agg[k].values()))
        days = list(range(lo, hi + 1))
        hdr = "cls".ljust(12) + "".join(f"d{d:<7}" for d in days) + "  n"
        print(hdr)
        for k in classes:
            row = k.ljust(12)
            for d in days:
                v = agg[k].get(d)
                row += (f"{v:>+8,.0f}" if v else "       .") + " "
            row += f" {sum(counts[k].values()):>4}"
            print(row)
        net = sum(sum(v.values()) for v in agg.values())
        print(f"NET d{lo}-{hi}: {net:+,.0f}")


if __name__ == "__main__":
    main()
