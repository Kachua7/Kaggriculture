"""Per-day income decomposition: elite money curves vs ours (0925n).

For each game, per seat: day -> (money_delta, executed shed outflow by good).
Prints the d10-d24 window where the mid-game stall lives.

Usage: python3 analysis/top10_curves.py file.json [file2.json ...]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.profile_replay import profile, PRODUCTS


def day_income(pr):
    """day -> (delta, {good: shed_outflow}) from money_curve + sheds."""
    out = {}
    prev_m = None
    prev_shed = {}
    for d, m in pr["money_curve"]:
        delta = (m - prev_m) if prev_m is not None else 0
        prev_m = m
        out[d] = [delta, {}]
    prev = {}
    for day, shed in pr["sheds"]:
        for g in PRODUCTS:
            n = shed.get(g, 0)
            if g in prev and n < prev[g]:
                out.setdefault(day, [0, {}])[1][g] = out[day][1].get(g, 0) + (prev[g] - n)
            prev[g] = n
    return out


def main(paths):
    for pth in paths:
        d = json.load(open(pth))
        teams = d.get("info", {}).get("TeamNames", ["?", "?"])
        prof = profile(pth)
        print("=" * 78)
        print(os.path.basename(pth), teams)
        inc = {p: day_income(prof[p]) for p in prof}
        days = sorted(set().union(*[set(i) for i in inc.values()]))
        for p in sorted(prof):
            tot = sum(v[0] for k, v in inc[p].items() if 10 <= k <= 24)
            print(" seat%d %-20s d10-24 net $%+.0f" % (p, teams[p] if p < len(teams) else "?", tot))
        print("  day | " + " | ".join(
            "s%d $%-7s out" % (p, "") for p in sorted(prof)))
        for day in [dd for dd in days if 8 <= dd <= 26]:
            row = " %3d |" % day
            for p in sorted(prof):
                delta, outflow = inc[p].get(day, [0, {}])
                of = ",".join("%s:%d" % (g[:3], n) for g, n in
                              sorted(outflow.items(), key=lambda kv: -kv[1])[:3])
                row += " %+8.0f %-18s |" % (delta, of)
            print(row)


if __name__ == "__main__":
    main(sys.argv[1:])
