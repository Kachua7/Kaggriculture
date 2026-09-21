"""Ladder replay autopsy: what actually happened in one Kaggle episode JSON.

Usage:
    .venv/bin/python analysis/replay_autopsy.py /path/to/episode.json

Prints, from the replay alone:
  teams / episode id / module_version    who played, on what engine build
  rewards + winner + margin              the only thing BT scores
  SELF-MATCH flag                        both seats the same team (guaranteed W+L,
                                         ~zero rating EV, no information)
  money curve every 2 days               where the gap opened
  day-0 action identity                  24/24 identical => deterministic opening
                                         (book serve or twin play) confirmed on ladder
  crop mix / market profile              what each seat actually did
  final leftovers                        shed + standing-crop value at T=720 (B11 on ladder)

Engine-version verdict is fingerprint.py's job (re-simulation); this tool reads
ep.facts only. Run both.
"""
from __future__ import annotations

import json
import os
import sys

MOVE = {"NORTH", "SOUTH", "EAST", "WEST", "PASS", "HARVEST", "WATER", "DIG", "DROP"}


def _market_tokens(order):
    if isinstance(order, list) and order:
        return str(order[0]), (order[1] if len(order) > 1 else None)
    if isinstance(order, dict):
        return order.get("type", "?"), order.get("crop") or order.get("good")
    return "?", None


def main(path: str) -> None:
    with open(path) as f:
        ep = json.load(f)
    steps = ep["steps"]
    n = len(steps)
    info = ep.get("info") or {}
    teams = info.get("TeamNames") or ["?", "?"]
    version = ep.get("module_version", "?")
    rewards = ep.get("rewards") or [a.get("reward") for a in steps[-1]]
    statuses = ep.get("statuses") or [a.get("status") for a in steps[-1]]
    seed = (info.get("seed"), (ep.get("configuration") or {}).get("seed"))

    print(f"episode  : {info.get('EpisodeId', ep.get('id', '?'))}  seed={seed}")
    print(f"engine   : module_version {version}   steps={n}")
    print(f"teams    : {teams}")
    print(f"status   : {statuses}   rewards: {rewards:,.0f}" if not isinstance(rewards, list)
          else f"status   : {statuses}   rewards: {[f'{r:,.0f}' for r in rewards]}")
    if isinstance(rewards, list) and len(rewards) == 2:
        w = 0 if rewards[0] > rewards[1] else 1 if rewards[1] > rewards[0] else None
        if w is None:
            print("result   : TIE")
        else:
            print(f"result   : seat {w} ({teams[w]}) wins by ${abs(rewards[0]-rewards[1]):,.0f}")
    self_match = len(set(teams)) == 1
    print(f"SELF-MATCH: {'YES -- guaranteed W+L for the team, ~zero rating EV' if self_match else 'no'}")

    # money curves (per-seat) from each seat's own observation; shed lives in private
    money = [[], []]
    shed_final = [None, None]
    for st in steps:
        for i in range(2):
            obs = st[i].get("observation") or {}
            farms = obs.get("farms") or []
            me = farms[i] if i < len(farms) else {}
            money[i].append(me.get("money") or 0)
            if st is steps[-1]:
                priv = obs.get("private") or {}
                shed_final[i] = priv.get("shed", me.get("shed"))
    print("\nmoney every 2 days (24 steps):")
    print("  day |    seat0 |    seat1 |     gap")
    for s in range(0, n, 48):
        print(f" {s//24:3d} | {money[0][s]:8.0f} | {money[1][s]:8.0f} | {money[0][s]-money[1][s]:+7.0f}")
    print(f" end | {money[0][-1]:8.0f} | {money[1][-1]:8.0f} | {money[0][-1]-money[1][-1]:+7.0f}")

    # day-0 action identity (twin/serve check)
    same = sum(1 for s in range(min(24, n)) if steps[s][0].get("action") == steps[s][1].get("action"))
    print(f"\nday-0 identical actions: {same}/24"
          f"  ({'deterministic opening confirmed on ladder' if same == 24 else 'seats diverged on day 0'})")

    # per-seat behaviour profile
    prof = [{} for _ in range(2)]
    for st in steps:
        for i in range(2):
            a = st[i].get("action") or {}
            for o in a.get("market") or []:
                tok, crop = _market_tokens(o)
                key = f"{tok}{('_' + str(crop)) if crop and tok in ('BUY_SEED',) else ''}"
                prof[i][key] = prof[i].get(key, 0) + 1
            for h in a.get("hands") or []:
                for tok in (h if isinstance(h, list) else [h]):
                    if tok in MOVE:
                        prof[i][tok] = prof[i].get(tok, 0) + 1
    for i in range(2):
        seeds = {k: v for k, v in prof[i].items() if k.startswith("BUY_SEED")}
        sells = sum(v for k, v in prof[i].items() if k.startswith("SELL"))
        hires = prof[i].get("HIRE", 0)
        print(f"seat {i}: SELL={sells} HIRE={hires} seed-buys={seeds or '{}'}")

    print(f"final shed: {shed_final}")
    print("\nengine verdict: run calibration/fingerprint.py on this same file (re-simulation)")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isfile(sys.argv[1]):
        sys.exit(__doc__)
    main(sys.argv[1])
