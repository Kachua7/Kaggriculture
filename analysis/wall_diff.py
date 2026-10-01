"""Wall diff: our seat vs the opponent's on the 600-800 / 800+ (and close) tapes.

The 600-800 band is 0W-11L across sub19+sub20. This extracts, per seat, per day:
hands, PLANT, WATER, HARVEST, thirst deaths, BUY_SEED units, HIREs, executed sales
(shed deltas), and the money curve -- then prints d10-16 aggregates and season
totals per band, so the losing mechanism (short-handed? short-seeded? dry? priced
out?) is measurable instead of guessed.

Usage:
  .venv/bin/python analysis/wall_diff.py --dirs submission19games,submission20games
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "analysis"))

from profile_replay import profile, our_seat, executed_flow  # noqa: E402
from telemetry_dump import thirst_and_animals  # noqa: E402


def act_counts(eid, seat):
    """Day -> Counter of farmer+hand ACTION verbs (movement excluded)."""
    d = json.load(open(f"{DIR}/{eid}.json"))
    steps = d["steps"]
    per = defaultdict(Counter)
    MOVE = {"NORTH", "SOUTH", "EAST", "WEST", "PASS"}
    for i, st in enumerate(steps):
        day = i // 24
        a = st[seat].get("action") or {}
        hands = a.get("hands") or []
        farmer = a.get("farmer") or []
        for op in ([farmer[0]] if farmer else []) + [h[0] for h in hands if h]:
            if op in MOVE:
                continue
            per[day][op] += 1
    return per


def day_extents(pr, ts, seat, path):
    """Day -> (hands, thirst deaths, animals) from tile snapshots + farms."""
    d = json.load(open(path))
    steps = d["steps"]
    hands, animals = {}, {}
    for i, st in enumerate(steps):
        o = st[seat].get("observation") or {}
        day = o.get("day", i // 24)
        farm = (o.get("farms") or [None, None])[seat]
        if farm is None:
            continue
        hands[day] = max(hands.get(day, 0), len(farm.get("hands") or []))
        n = sum(1 for row in (farm.get("tiles") or []) for t in row
                if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE")
                and t.get("animal"))
        animals[day] = max(animals.get(day, 0), n)
    thirst = defaultdict(int)
    for day, n in ts[seat]["thirst"].items():
        thirst[int(day)] += n
    return hands, thirst, animals


def main():
    global DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--dirs", default="submission19games,submission20games")
    ap.add_argument("--bands", default="600-800,800+,540-600")
    ap.add_argument("--lb", default=None)
    ap.add_argument("--focus", type=int, nargs=2, default=(10, 16),
                    help="focus window (inclusive day range)")
    a = ap.parse_args()
    DIR = None  # act_counts reads per-eid from DIR global; set per tape

    ratings = {}
    lb = a.lb
    if not lb:
        import csv as _csv
        cands = sorted(glob.glob("/tmp/lb_fresh/*.csv") + glob.glob("/tmp/lb_now/*.csv")
                       + glob.glob("/tmp/lb_now2/*.csv"))
        lb = cands[-1] if cands else None
    if lb:
        import csv as _csv
        with open(lb) as f:
            for row in _csv.DictReader(f):
                ratings[row["TeamName"]] = float(row["Score"])

    def band_of(x):
        if x == "??":
            return "??"
        if x < 500:
            return "<500"
        if x < 540:
            return "500-540"
        if x < 600:
            return "540-600"
        if x < 800:
            return "600-800"
        return "800+"

    lo, hi = a.focus
    rows = []
    for dirn in a.dirs.split(","):
        DIR = dirn
        for path in sorted(glob.glob(os.path.join(dirn, "*.json"))):
            eid = re.search(r"(\d{9})", os.path.basename(path)).group(1)
            try:
                d = json.load(open(path))
                teams = d["info"]["TeamNames"]
                if "Pranjal Morwal" not in teams:
                    continue
                idx = teams.index("Pranjal Morwal")
                rewards = d["rewards"]
                prof = profile(path)
                seat = our_seat(prof, rewards[idx])
                pr = prof[seat]
                pr_o = prof[1 - seat]
                ts = thirst_and_animals(path)
                acts = act_counts(eid, seat)
                acts_o = act_counts(eid, 1 - seat)
                hands, thirst, animals = day_extents(pr, ts, seat, path)
                hands_o, thirst_o, animals_o = day_extents(pr_o, ts, 1 - seat, path)

                def sums(acts_, hands_, thirst_, pr_):
                    mc = dict(pr_["money_curve"])
                    flow = executed_flow(pr_)
                    tot = Counter()
                    foc = Counter()
                    for day in range(0, 30):
                        c = acts_.get(day, Counter())
                        tot.update(c)
                        if lo <= day <= hi:
                            foc.update(c)
                        tot["THIRST"] += thirst_.get(day, 0)
                        if lo <= day <= hi:
                            foc["THIRST"] += thirst_.get(day, 0)
                    foc["HANDS"] = sum((hands_.get(day) or 0) for day in range(lo, hi + 1)) / (hi - lo + 1)
                    tot["HANDS"] = sum((hands_.get(day) or 0) for day in range(0, 30)) / 30
                    return tot, foc, mc, flow

                tot, foc, mc, flow = sums(acts, hands, thirst, pr)
                tot_o, foc_o, mc_o, flow_o = sums(acts_o, hands_o, thirst_o, pr_o)
                opp = teams[1 - idx]
                rows.append(dict(
                    eid=eid, dirn=dirn, opp=opp, band=band_of(ratings.get(opp, "??")),
                    margin=rewards[idx] - rewards[1 - idx],
                    hire_f=tot["HIRE"], hire_o=tot_o["HIRE"],
                    hireF=foc["HIRE"], hireO=foc_o["HIRE"],
                    plantF=foc["PLANT"], plantO=foc_o["PLANT"],
                    waterF=foc["WATER"], waterO=foc_o["WATER"],
                    harvestF=foc["HARVEST"], harvestO=foc_o["HARVEST"],
                    thirstF=tot["THIRST"], thirstO=tot_o["THIRST"],
                    thirstF_foc=foc["THIRST"], thirstO_foc=foc_o["THIRST"],
                    handsF=foc["HANDS"], handsO=foc_o["HANDS"],
                    seedF=sum(v for k, v in pr["seeds"].items()), seedO=sum(v for k, v in pr_o["seeds"].items()),
                    milkF=flow.get("MILK", 0), milkO=flow_o.get("MILK", 0),
                    woolF=flow.get("WOOL", 0), woolO=flow_o.get("WOOL", 0),
                    whtF=flow.get("WHEAT", 0), whtO=flow_o.get("WHEAT", 0),
                    strF=flow.get("STRAWBERRY", 0), strO=flow_o.get("STRAWBERRY", 0),
                    melF=flow.get("MELON", 0), melO=flow_o.get("MELON", 0),
                ))
            except Exception as e:  # noqa: BLE001
                print(f"  skip {eid}: {e}", file=sys.stderr)

    def agg(rs, key):
        return (sum(r[key] for r in rs) / len(rs)) if rs else 0.0

    for b in a.bands.split(","):
        seg = [r for r in rows if r["band"] == b]
        if not seg:
            continue
        print(f"\n== band {b}  (n={len(seg)}) ==")
        pairs = (
            ("handsF", "handsO", "hands/day d10-16"),
            ("hireF", "hireO", "hires total"),
            ("plantF", "plantO", "PLANT/day d10-16"),
            ("waterF", "waterO", "WATER/day d10-16"),
            ("harvestF", "harvestO", "HARVEST/day d10-16"),
            ("thirstF_foc", "thirstO_foc", "thirst d10-16"),
            ("thirstF", "thirstO", "thirst total"),
            ("seedF", "seedO", "seed units total"),
            ("milkF", "milkO", "exec milk"),
            ("woolF", "woolO", "exec wool"),
            ("whtF", "whtO", "exec wheat"),
            ("strF", "strO", "exec strawberry"),
            ("melF", "melO", "exec melon"),
        )
        for k1, k2, label in pairs:
            ours = agg(seg, k1)
            oppv = agg(seg, k2)
            print(f"  {label:20s}{ours:9.1f}{oppv:9.1f}{ours - oppv:+9.1f}")
        w = sum(1 for r in seg if r["margin"] > 0)
        print(f"  W/L {w}-{len(seg) - w}  mean margin {sum(r['margin'] for r in seg)/len(seg):+,.0f}")


if __name__ == "__main__":
    main()
