"""Famine forensics: WHERE does the v3 rescue change the akilit world's outcome?

Runs the recorded akilit world (seed 986881817, judge replays tape seat 0 verbatim,
one-later aligned — the paired_ab counterfactual convention) twice:
  --params-json {}        the shipped v3 policy (strict tier + rescue tier)
  --strict-only           every match forced to the strict tier (the sub24/v2 pick)
and prints, per dawn: the live sig, which donor variant served (or the halt
reason), and both banks. The diff between the two columns is exactly what phase 2
changed in this world — no knob guessing.

Usage:
  PYTHONHASHSEED=0 .venv/bin/python analysis/famine_forensics.py            # both arms
  PYTHONHASHSEED=0 .venv/bin/python analysis/famine_forensics.py --arm v3   # one arm
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import RealEnv, ENGINE_DIR          # noqa: E402
from kagfarm import policy as policy_mod                 # noqa: E402
from kagfarm.policy import Policy                        # noqa: E402

TAPE = "115165685"          # akilit world
TAPE_SEAT = 0               # the seat the judge replays (akilit's own actions)
OUR_SEAT = 0                # our seat in the rerun engine
OPP_SEAT = 1


def run_arm(over, strict_only):
    src = policy_mod._variant_sig_eq
    if strict_only:
        def _strict_only(sig, donor_sig, tol=2):     # noqa: ARG001
            return src(sig, donor_sig, 2)
        policy_mod._variant_sig_eq = _strict_only
    try:
        d = json.load(open(os.path.join(_ROOT, "analysis", "replays", f"{TAPE}.json")))
        steps = d["steps"]
        seed = int((d.get("info") or {}).get("seed") or 0)
        opp_actions = [steps[i][TAPE_SEAT].get("action") or {} for i in range(len(steps))]

        env = RealEnv(seed, ENGINE_DIR)
        params = dict(policy_mod.PARAMS)
        params.update(over or {})
        pol = Policy(params=params)
        book = policy_mod._load_opening_book(policy_mod._elite_book_path_default()) or {}

        rows = []
        t = 0
        while not env.done:
            obs = env._obs_view(OUR_SEAT)
            day = int(obs.get("day", t // 24))
            a = pol.act(obs, env.config)
            if t % 24 == 0:
                live = policy_mod.opening_book_signature(obs)
                variants = book.get(day) or []
                if day in pol._book_decided:
                    idx = pol._book_variant.get(day)
                    donor = variants[idx].get("donor") if idx is not None else "?"
                    state = f"served#{idx} {donor}"
                elif day in pol._book_halt_days:
                    state = "halt"
                else:
                    state = "off"
                b = env.banks()
                rows.append((day, state, list(live), b[OUR_SEAT], b[OPP_SEAT]))
            oa = opp_actions[t + 1] if t + 1 < len(opp_actions) else {}
            oa = {k: (list(v) if k == "farmer" and v else v) for k, v in oa.items()}
            acts = [None, None]
            acts[OUR_SEAT] = a
            acts[OPP_SEAT] = oa
            env.step(acts)
            t += 1
        banks = env.banks()
        return rows, banks[OUR_SEAT], banks[OPP_SEAT]
    finally:
        policy_mod._variant_sig_eq = src


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["both", "v3", "v2"], default="both")
    a = ap.parse_args()

    arms = {}
    if a.arm in ("both", "v3"):
        arms["v3"] = run_arm({}, False)
    if a.arm in ("both", "v2"):
        arms["v2"] = run_arm({}, True)

    for name, (rows, mine, opp) in arms.items():
        print(f"\n== arm {name}: our final ${mine:,.0f} vs judge ${opp:,.0f} "
              f"(margin {mine - opp:+,.0f}) ==")
        for day, state, live, b_me, b_opp in rows:
            print(f"  d{day:>2} {state:<22} sig={live}  our ${b_me:>9,.0f}  "
                  f"opp ${b_opp:>9,.0f}")

    if "v3" in arms and "v2" in arms:
        r3, m3, _ = arms["v3"]
        r2, m2, _ = arms["v2"]
        print("\n== per-dawn serving diff (v3 vs v2) ==")
        s2 = {d: st for d, st, _, _, _ in r2}
        for day, state, _, b3, _ in r3:
            if s2.get(day) != state:
                print(f"  d{day:>2}: v2={s2.get(day):<18} v3={state:<18} "
                      f"our bank ${b3:,.0f}")


if __name__ == "__main__":
    main()
