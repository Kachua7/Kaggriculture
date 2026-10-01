"""Judge bar, W/L first (Bradley-Terry objective).

The ladder scores win/loss only — coin margin does not move rating (official rules,
"A Practical Guide to Kaggriculture" echo: beat a 700-rated peer and the full swing
is yours; lose to a 3200 elite and it costs almost nothing). So the bar's PRIMARY
column is the W/L verdict per judge, margin secondary.

Runs `ab_panel.paired_ab` (each judge on its own recorded seed — the counterfactual
contract) over the 5 field judges and prints both orders. One process per arm: the
vendored engine is process-global state, so never pool arms in one interpreter.

Usage:
    .venv/bin/python analysis/judge_bar.py --label shipped
    .venv/bin/python analysis/judge_bar.py --params '{"decay_urge": 1}' --label b1
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.ab_panel import paired_ab  # noqa: E402

# The promotion bar since 0925i, two tiers:
#   ELITE tier — the 5 field judges (recorded seeds, real tier). W/L here is secondary:
#     Bradley-Terry makes elite losses nearly free; guard against regressions.
#   MIDFIELD tier — the 4 coin-flip-band judges (2400-2900 opponents, our own tapes).
#     This is where rating actually moves; W/L improvement here is the primary verdict.
BAR = "replay_luanhe,replay_juicy,replay_majkel886,replay_majkel900,replay_majkel907"
MIDFIELD = "replay_midfield_tam,replay_midfield_dean,replay_midfield_jiahan,replay_midfield_susutem"
# The WALL tier (0927): the 500-600-band losses that make the actual rating record.
# These judge the candidate on the exact games it must flip.
WALL = ("replay_wall_nottoday,replay_wall_aarya,replay_wall_tnwl,replay_wall_hayday,"
        "replay_wall_mingkang,replay_wall_alexandre,replay_wall_aynrmio")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", default=None, help="JSON dict of PARAMS overrides")
    ap.add_argument("--label", default="arm")
    ap.add_argument("--opps", default=None,
                    help="default: ELITE tier then MIDFIELD tier, judged separately")
    ap.add_argument("--tier", choices=["elite", "midfield", "wall", "both", "all"],
                    default="both")
    a = ap.parse_args()
    params = json.loads(a.params) if a.params else None
    tiers = {"elite": BAR.split(","), "midfield": MIDFIELD.split(","),
             "wall": WALL.split(",")}
    run_tiers = (["elite", "midfield"] if a.tier == "both"
                 else ["elite", "midfield", "wall"] if a.tier == "all"
                 else [a.tier])
    totals = []
    for tier in run_tiers:
        opps = [o for o in (a.opps.split(",") if a.opps else tiers[tier]) if o]
        summary, _ = paired_ab(range(1), opps, params=params, label=a.label)

        print(f"\n== {a.label} [{tier}]: W/L-first bar ==")
        wl = []
        for opp, r in summary.items():
            won = r["margin"] > 0
            wl.append((opp, won, r["margin"]))
            print(f"  {opp:<22} {'W' if won else 'L'}  margin {r['margin']:+9,.0f}"
                  f"  (judge ${r['judge_bank']:8,.0f} vs recorded"
                  f" ${r['judge_recorded']:8,.0f})")
        wins = sum(1 for _, w, _ in wl if w)
        margins = [m for _, _, m in wl]
        print(f"  W/L {wins}-{len(wl) - wins}   mean margin {sum(margins) / len(margins):+9,.0f}"
              f"   best {max(margins):+9,.0f}   worst {min(margins):+9,.0f}")
        totals.append((tier, wins, len(wl) - wins, sum(margins) / len(margins)))
    if a.tier == "both":
        print("\n== promotion rule ==\n"
              "  ELITE: no material regression (guard)\n"
              "  MIDFIELD: W/L improvement is the primary verdict\n"
              + "\n".join(f"  {t}: W/L {w}-{l}   mean {m:+9,.0f}"
                           for t, w, l, m in totals))
    print("  primary verdict: W/L; margin secondary (BT scores only the outcome)")


if __name__ == "__main__":
    main()
