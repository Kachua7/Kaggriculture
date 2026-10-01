"""Morning field pull: both residents' new episodes -> W/L-by-band -> regression flags.

The pre-freeze ritual (run every morning through Sep 29; FREEZE_CHECKLIST.md step 1):
  1. list each resident submission's ladder episodes (kaggle CLI),
  2. download any episode missing on disk (API side-effect file, renamed),
  3. load every local replay, resolve W/L/margin/seat from rewards,
  4. band opponents by the freshest leaderboard CSV available,
  5. print the table + regression flags + a ready-to-paste ledger block.

Usage:
    .venv/bin/python analysis/morning_pull.py
    .venv/bin/python analysis/morning_pull.py --sub 56559743 --sub 56555835 --dir submission17games

Read-only with respect to the repo except: new episode JSONs land in the --dir
folders (that is the point) and nothing else is written.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KAGGLE = os.path.join(HERE, ".venv", "bin", "kaggle")
PY = os.path.join(HERE, ".venv", "bin", "python")

RESIDENTS = [
    ("56559743", "submission17games", "sub17"),
    ("56555835", "submission16games", "sub16"),
]
BANDS = ("<500", "500-540", "540-600", "600-800", "800+", "??")


def _band(score):
    if score is None:
        return "??"
    if score < 500:
        return "<500"
    if score < 540:
        return "500-540"
    if score < 600:
        return "540-600"
    if score < 800:
        return "600-800"
    return "800+"


def freshest_lb_csv():
    cands = sorted(glob.glob("/tmp/lb_now/*.csv")) + \
        sorted(glob.glob("/tmp/lb_fresh/*.csv"))
    return cands[-1] if cands else None


def ladder_episodes(sub_id):
    out = subprocess.run([KAGGLE, "competitions", "episodes", sub_id],
                         capture_output=True, text=True, timeout=120)
    ids = re.findall(r"^\s*(\d{9})\s", out.stdout, re.M)
    return sorted(set(ids), key=int)


def download_missing(ep_id, folder):
    from kaggle.api.kaggle_api_extended import KaggleApi  # noqa
    api = KaggleApi()
    api.authenticate()
    api.competition_episode_replay(int(ep_id), folder)
    src = os.path.join(folder, f"episode-{ep_id}-replay.json")
    for _ in range(20):
        if os.path.exists(src) and os.path.getsize(src) > 1_000_000:
            break
        time.sleep(1)
    if not os.path.exists(src):
        return False
    os.replace(src, os.path.join(folder, f"{ep_id}.json"))
    return True


def load_tapes(folder, ratings):
    eps = {}
    for p in glob.glob(os.path.join(folder, "*.json")):
        m = re.search(r"(\d{9})", os.path.basename(p))
        if not m:
            continue
        eid = m.group(1)
        try:
            j = json.load(open(p))
        except Exception:
            continue
        teams = j["info"]["TeamNames"]
        rewards = j["rewards"]
        if "Pranjal Morwal" not in teams:
            continue
        seat = teams.index("Pranjal Morwal")
        opp = teams[1 - seat]
        eps[eid] = dict(id=eid, opp=opp, seat=seat,
                        margin=rewards[seat] - rewards[1 - seat],
                        rating=ratings.get(opp))
    return eps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sub", action="append", default=None,
                    help="submission id (repeatable); default = both residents")
    ap.add_argument("--dir", default=None, help="folder override (single-sub mode)")
    a = ap.parse_args()

    lb = freshest_lb_csv()
    ratings = {}
    if lb:
        with open(lb) as f:
            for row in csv.DictReader(f):
                ratings[row["TeamName"]] = float(row["Score"])
    print(f"leaderboard CSV: {lb or 'NONE (bands will read ??)'}")

    subs = [(sid, a.dir or f"submission{sid[-2:]}games", f"sub{sid[-2:]}") for sid in a.sub] \
        if a.sub else RESIDENTS
    for sid, folder, name in subs:
        os.makedirs(folder, exist_ok=True)
        ladder = ladder_episodes(sid)
        have = {re.search(r"(\d{9})", os.path.basename(p)).group(1)
                for p in glob.glob(os.path.join(folder, "*.json"))}
        missing = [i for i in ladder if i not in have]
        print(f"\n== {name} ({sid}): {len(ladder)} on ladder, {len(missing)} missing ==")
        for eid in missing:
            ok = download_missing(eid, folder)
            print(f"  download {eid}: {'OK' if ok else 'MISSING'}")
            time.sleep(2)
        eps = load_tapes(folder, ratings)
        eps = {k: v for k, v in eps.items() if k in set(ladder)} or eps
        ordered = sorted(eps.values(), key=lambda e: int(e["id"]))
        if not ordered:
            print("  no tapes.")
            continue
        w = sum(1 for e in ordered if e["margin"] > 0)
        l = sum(1 for e in ordered if e["margin"] < 0)
        mean = sum(e["margin"] for e in ordered) / len(ordered)
        print(f"  ALL: {w}W-{l}L  mean {mean:+,.0f}  n={len(ordered)}")
        for b in BANDS:
            seg = [e for e in ordered if _band(e["rating"]) == b]
            if not seg:
                continue
            sw = sum(1 for e in seg if e["margin"] > 0)
            sm = sum(e["margin"] for e in seg) / len(seg)
            print(f"    {b:8s} {sw}W-{len(seg) - sw}L  mean {sm:+10,.0f}  ({len(seg)})")
        tail = ordered[-10:]
        tw = sum(1 for e in tail if e["margin"] > 0)
        print(f"  last-10: {tw}W-{len(tail) - tw}L")
        # regression flags
        flags = []
        if len(tail) == 10 and tw <= 2:
            flags.append("last-10 win rate <= 20%")
        for b in ("500-540", "540-600"):
            seg = [e for e in ordered if _band(e["rating"]) == b]
            if len(seg) >= 6:
                sw = sum(1 for e in seg if e["margin"] > 0)
                if sw / len(seg) < 0.30:
                    flags.append(f"{b} W% below 30% ({sw}/{len(seg)})")
        if any(e["margin"] < -60000 for e in ordered[-6:]):
            flags.append("a >= -$60k margin in the last 6 games")
        if any(e["rating"] is None for e in ordered[-6:]):
            flags.append("unrated opponent in the last 6 games (band coverage gap)")
        for f in flags:
            print(f"  FLAG: {f}")
        if not flags:
            print("  no regression flags.")
        newest = ordered[-1]
        print(f"  newest: {newest['id']} vs {newest['opp']} "
              f"({'W' if newest['margin'] > 0 else 'L'} {newest['margin']:+,.0f})")


if __name__ == "__main__":
    main()
