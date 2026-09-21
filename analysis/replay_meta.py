"""Aggregate a folder of downloaded ladder replays into one meta report.

    python3 analysis/replay_meta.py /path/to/replays/          # or: file1.json file2.json

Per episode: teams, self-match flag, result, margin. Per opponent across episodes:
W-L, total margin, and the behavioural fingerprint (HIREs, seed mix, idle-cash) so
the live meta can be tracked as more replays land. This is the data-first workflow's
collection step -- run it after every batch of downloads from the submission page.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict

MOVE_SELL = "SELL"


def load_paths(args):
    out = []
    for a in args:
        if os.path.isdir(a):
            out.extend(sorted(glob.glob(os.path.join(a, "*.json"))))
        elif os.path.isfile(a):
            out.append(a)
        else:
            print(f"(skip, not found: {a})")
    return out


def profile_seat(steps, seat, our_day_lo=13, our_day_hi=25):
    """Behavioural fingerprint from the action stream + observations."""
    hires = sells = 0
    seed = defaultdict(int)
    idle = 0
    for st in steps:
        a = st[seat].get("action") or {}
        for o in a.get("market") or []:
            tok = o[0] if isinstance(o, list) else "?"
            if tok == "HIRE":
                hires += 1
            elif tok == "SELL":
                sells += 1
            elif tok == "BUY_SEED":
                crop = o[1] if isinstance(o, list) and len(o) > 1 else "?"
                q = o[2] if isinstance(o, list) and len(o) > 2 and isinstance(o[2], (int, float)) else 1
                seed[crop] += q
        obs = st[seat].get("observation") or {}
        farms = obs.get("farms") or []
        me = farms[seat] if seat < len(farms) else {}
        d = obs.get("day", 0)
        if our_day_lo <= d <= our_day_hi and (me.get("money") or 0) > 8000:
            idle += 1
    return hires, sells, dict(seed), idle


def main(args):
    paths = load_paths(args)
    if not paths:
        sys.exit(__doc__)
    us_name = "Pranjal Morwal"
    per_opp = defaultdict(lambda: {"w": 0, "l": 0, "t": 0, "margin": 0.0, "eps": []})
    n_self = 0
    for p in paths:
        try:
            with open(p) as f:
                ep = json.load(f)
        except Exception as e:  # noqa: BLE001
            print(f"(unreadable {os.path.basename(p)}: {e})")
            continue
        steps = ep.get("steps") or []
        if not steps:
            continue
        teams = (ep.get("info") or {}).get("TeamNames") or ["?", "?"]
        rewards = ep.get("rewards")
        if rewards is None:
            rewards = [a.get("reward") for a in steps[-1]]
        eid = (ep.get("info") or {}).get("EpisodeId", os.path.basename(p))
        if us_name not in teams:
            print(f"{eid}: we are not in this episode ({teams})")
            continue
        us = teams.index(us_name)
        them = 1 - us
        if teams[us] == teams[them]:
            n_self += 1
            kind = "SELF-MATCH"
            opp = "(ourselves)"
            margin = 0.0
        else:
            opp = teams[them]
            margin = (rewards[us] or 0) - (rewards[them] or 0)
            kind = "W" if margin > 0 else ("L" if margin < 0 else "T")
            rec = per_opp[opp]
            rec["w" if kind == "W" else "l" if kind == "L" else "t"] += 1
            rec["margin"] += margin
        print(f"{eid}: vs {opp:<32} {kind}  margin {margin:+,.0f}  "
              f"(us {rewards[us]:,.0f} / them {rewards[them]:,.0f})")
        if kind != "SELF-MATCH":
            h, s, seed, idle = profile_seat(steps, them)
            per_opp[opp]["eps"].append((eid, h, s, seed, idle))

    print(f"\n=== summary: {len(paths)} files, {n_self} self-matches, "
          f"{sum(len(v['eps']) for v in per_opp.values())} real-opponent episodes ===")
    for opp, rec in sorted(per_opp.items(), key=lambda kv: -kv[1]["l"]):
        wlt = f"{rec['w']}-{rec['l']}" + (f"-{rec['t']}" if rec["t"] else "")
        print(f"\n{opp}: {wlt}  total margin {rec['margin']:+,.0f}")
        for eid, h, s, seed, idle in rec["eps"]:
            print(f"   {eid}: HIRE={h} SELL={s} seed={seed} idle_steps={idle}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
