"""0930o P0-D: the strategy-zoo rollout evaluator — the plan's ΔV measurement.

Runs each STRATEGY_ZOO expert (a complete PARAMS delta on top of the shipped E0 state)
against the W/L-moving judge tiers and prints W/L + margin per expert. This is the
offline scorer the zoo needs until an in-episode rollout policy exists: the elite book
becomes E0, one expert among several, and deviating from it is a MEASURED choice.

Usage:
  PYTHONHASHSEED=0 .venv/bin/python analysis/zoo_rollout.py --experts E0_elite_prior,E1_livestock_lean
  PYTHONHASHSEED=0 .venv/bin/python analysis/zoo_rollout.py --tier midfield --experts all
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

TIERS = {
    "midfield": ("replay_midfield_tam", "replay_midfield_dean",
                 "replay_midfield_jiahan", "replay_midfield_susutem"),
    "famine": ("replay_famine_scharf", "replay_famine_akilit"),
    "wall": ("replay_wall_nottoday", "replay_wall_aarya", "replay_wall_tnwl",
             "replay_wall_hayday", "replay_wall_mingkang", "replay_wall_alexandre",
             "replay_wall_aynrmio"),
    "elite": ("replay_majkel886", "replay_majkel900", "replay_majkel907"),
}


def main():
    from kagfarm.policy import STRATEGY_ZOO
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="midfield,famine")
    ap.add_argument("--experts", default="all")
    a = ap.parse_args()
    experts = (sorted(STRATEGY_ZOO) if a.experts == "all"
               else [e.strip() for e in a.experts.split(",") if e.strip()])
    unknown = [e for e in experts if e not in STRATEGY_ZOO]
    if unknown:
        raise SystemExit(f"unknown experts: {unknown}")
    opps = [o for t in a.tier.split(",") for o in TIERS[t.strip()]]

    print(f"zoo rollout: {len(experts)} experts x {len(opps)} judges (real tier)")
    print(f"{'expert':<24}{'W/L':>6}{'mean':>10}{'best':>10}{'worst':>10}")
    for name in experts:
        delta = STRATEGY_ZOO[name]
        params = dict(delta) if delta else None
        sys.path.insert(0, _ROOT)
        from analysis.ab_panel import paired_ab
        summary, _ = paired_ab(range(1), opps, params=params, label=name)
        wl = [(o, r["margin"] > 0, r["margin"]) for o, r in summary.items()]
        wins = sum(1 for _, w, _ in wl if w)
        margins = [m for _, _, m in wl]
        print(f"{name:<24}{wins:>3}-{len(wl) - wins}"
              f"{sum(margins) / max(1, len(margins)):>+10,.0f}"
              f"{max(margins):>+10,.0f}{min(margins):>+10,.0f}", flush=True)
    print("\nVerdict rule (plan §27): an expert graduates only if its W/L beats E0's on "
          "the same judges; margin alone never promotes.")


if __name__ == "__main__":
    main()
