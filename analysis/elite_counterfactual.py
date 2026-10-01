"""Counterfactual book-hold probe — the phase-1 headline metric (0930c).

Run the elite_book policy INSIDE each donor's exact recorded world: the opponent
seat replays its tape actions verbatim, so the only difference from the recorded
episode is our seat's play. If the book holds (serves every dawn), our bank must
converge on the donor's recorded bank — that is the clone validation.

The probe fixes both defects of the two invalidated runs:
  1. obs0 is re-fetched from the live env at the TOP of every turn (the stale-obs
     bug: a view fetched once before the loop never sees the interpreter's writes);
  2. the agent under test is THIS tree's kagfarm.policy.Policy constructed with
     {"elite_book": 1} (the stale-flattened-main.py bug: submission/main.py was
     last bundled at sub23 and contains no elite_book code).

Per-dawn telemetry: the v2 signature the live dawn produced, the donor variants
available that day, which variant matched, and per-day halt classification:
  sig_miss  — no donor variant matched the live signature (the ONLY legitimate
              divergence class in an exact replay; if this fires with money/wool
              in-bucket but herd/wool exact off, it is a drift defect);
  invalid   — the signature matched but the recorded dawn action is not valid
              against the live state (action-validity guard fired);
  short     — the donor tape ends before day 30 (episode-length mismatch);
  ok        — served.

Usage:
  .venv/bin/python analysis/elite_counterfactual.py                # all 12 donors
  .venv/bin/python analysis/elite_counterfactual.py --eids 110886706,110900752
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import RealEnv, ENGINE_DIR  # noqa: E402
from kagfarm import policy as policy_mod         # noqa: E402
from kagfarm.policy import Policy                # noqa: E402

EIDS = ["110886706", "110900752", "110907373", "110913896", "110920455",
        "110926948", "110932461", "110938064", "110943566", "110948948",
        "110954233", "111016701"]
SEATS = {"110907373": 1, "110938064": 1, "110943566": 1, "111016701": 1}


def _run_donor(eid, until_day=30):
    path = os.path.join(_ROOT, "analysis", "replays", f"{eid}.json")
    d = json.load(open(path))
    steps = d["steps"]
    seed = int((d.get("info") or {}).get("seed") or 0)
    seat = SEATS.get(eid, 0)           # the seat the ELITE played on the tape
    opp_seat = 1 - seat

    # The opponent's recorded per-step actions, ALIGNED like the book: the action
    # decided from obs@t is steps[t+1].action (verify_replay convention, 0930c).
    # The tape's opponent bank, for the final comparison.
    opp_actions = [steps[i][opp_seat].get("action") or {} for i in range(len(steps))]

    env = RealEnv(seed, ENGINE_DIR)

    # 0930c A4 rule: params must be applied per-Policy (RealEnv does NOT reload
    # kagfarm.policy, but a probe that mutates the module PARAMS still leaks into
    # later pooled runs). Fresh Policy per seat with the elite switch on.
    pol = Policy(params={"elite_book": 1})
    donor_bank = steps[-1][seat].get("reward")
    if donor_bank is None:
        farms = steps[-1][seat].get("observation", {}).get("farms") or []
        donor_bank = (farms[seat] or {}).get("money") if farms else None

    served_days = 0
    halt_days = []                    # (day, reason)
    sigs = {}                         # day -> live signature at dawn
    bank0 = env.banks()[seat]
    t = 0
    while not env.done:
        obs = env._obs_view(seat)     # FRESH view every turn — the probe bug
        day = int(obs.get("day", t // 24))
        if t % 24 == 0:
            sigs[day] = policy_mod.opening_book_signature(obs)
        a = pol.act(obs, env.config)
        oa = opp_actions[t + 1] if t + 1 < len(opp_actions) else {}
        oa = {k: (list(v) if k == "farmer" and v else v) for k, v in oa.items()}
        acts = [None, None]
        acts[seat] = a
        acts[opp_seat] = oa
        env.step(acts)
        # Post-step: how did the dawn decision go?
        if t % 24 == 0:
            if day in pol._book_decided:
                served_days += 1
            elif day in pol._book_halt_days:
                # classify: sig miss vs invalid action vs short tape
                variants = (pol._book or {}).get(day) or []
                if not variants:
                    halt_days.append((day, "short"))
                elif any(policy_mod._variant_sig_eq(sigs[day], v.get("sig") or [])
                         for v in variants):
                    halt_days.append((day, "invalid"))
                else:
                    halt_days.append((day, "sig_miss"))
        t += 1

    final = env.banks()[seat]
    return dict(eid=eid, seed=seed, seat=seat, donor_bank=donor_bank,
                final=final, delta=final - (donor_bank or 0),
                served=served_days, halts=halt_days, sigs=sigs, bank0=bank0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eids", default=",".join(EIDS))
    ap.add_argument("--until", type=int, default=30)
    a = ap.parse_args()
    eids = [e for e in a.eids.split(",") if e]

    print(f"{'eid':<12}{'seed':<12}{'served':>7}{'halts':>8}"
          f"{'donor bank':>14}{'clone bank':>14}{'delta':>10}")
    rows = []
    for eid in eids:
        r = _run_donor(eid, a.until)
        rows.append(r)
        halts = ",".join(f"d{dy}:{why}" for dy, why in r["halts"]) or "-"
        print(f"{r['eid']:<12}{r['seed']:<12}{r['served']:>7}{len(r['halts']):>8}"
              f"{r['donor_bank']:>14,.0f}{r['final']:>14,.0f}{r['delta']:>+10,.0f}"
              f"  [{halts}]", flush=True)

    held = [r for r in rows if r["served"] >= 8]
    print(f"\nbook-hold >= 8 days: {len(held)}/{len(rows)} games")
    print(f"mean served days: {sum(r['served'] for r in rows) / max(1, len(rows)):.1f}")
    print(f"mean delta vs donor: {sum(r['delta'] for r in rows) / max(1, len(rows)):+,.0f}")
    return rows


if __name__ == "__main__":
    main()
