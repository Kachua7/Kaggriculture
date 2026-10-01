"""Signature check for the census-clone ladder tapes (sub19/sub20).

The six signature numbers vs the elite census program:
  melon0 6-14 (sub20's seed_opening_cap fix -- THE number to verify)
  hires ~280/season (roster re-hired every dawn)
  herd peak ~14 (correct singular tile key `animal` -- the plural key is the
  known herd=0 artifact; telemetry_dump.thirst_and_animals still uses plural,
  so we reuse only its thirst classifier here and census animals ourselves)
  sell days 29-30/30, continuous d12-24 income, thirst low

Usage:
  .venv/bin/python analysis/sub20_signature.py --dir submission20games --label sub20
  .venv/bin/python analysis/sub20_signature.py --dir submission19games --label sub19
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "analysis"))

from profile_replay import profile, our_seat, executed_flow  # noqa: E402
from telemetry_dump import thirst_and_animals  # noqa: E402


def herd_curve(path, seat):
    """Day -> animal count using the SINGULAR `animal` tile key (one per tile)."""
    with open(path) as f:
        d = json.load(f)
    steps = d["steps"]
    curve = {}
    for st in steps:
        o = st[seat].get("observation") or {}
        farm = (o.get("farms") or [None, None])[seat]
        if farm is None:
            continue
        day = o.get("day")
        n = 0
        for row in farm.get("tiles") or []:
            for t in row:
                if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") \
                        and t.get("animal"):
                    n += 1
        curve[day] = max(curve.get(day, 0), n)
    return curve


def tape_row(path, ratings):
    with open(path) as f:
        d = json.load(f)
    teams = d["info"]["TeamNames"]
    if "Pranjal Morwal" not in teams:
        return None
    idx = teams.index("Pranjal Morwal")
    rewards = d["rewards"]
    margin = rewards[idx] - rewards[1 - idx]
    prof = profile(path)
    seat = our_seat(prof, rewards[idx])
    pr = prof[seat]
    mc = dict(pr["money_curve"])
    income_days = sum(1 for day in range(12, 25)
                      if mc.get(day) is not None and mc.get(day - 1) is not None
                      and mc[day] > mc[day - 1])
    herd = herd_curve(path, seat)
    ts = thirst_and_animals(path)
    thirst = sum(ts[seat]["thirst"].values())
    opp = teams[1 - idx]
    return dict(
        eid=re.search(r"(\d{9})", os.path.basename(path)).group(1),
        opp=opp, band=ratings.get(opp, "??"), margin=margin,
        melon0=pr["d0_seeds"].get("MELON", 0),
        hires=pr["hires"], land=pr["land_buys"],
        herd_peak=max(herd.values()) if herd else 0,
        sell_days=len(pr["sell_days"]),
        income_days=income_days,
        milk=executed_flow(pr).get("MILK", 0),
        wool=executed_flow(pr).get("WOOL", 0),
        wheat=executed_flow(pr).get("WHEAT", 0),
        thirst=thirst,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--label", default="sub")
    ap.add_argument("--lb", default=None, help="leaderboard CSV for banding")
    a = ap.parse_args()

    ratings = {}
    lb = a.lb
    if not lb:
        cands = sorted(glob.glob("/tmp/lb_fresh/*.csv") + glob.glob("/tmp/lb_now/*.csv")
                       + glob.glob("/tmp/lb_now2/*.csv"))
        lb = cands[-1] if cands else None
    if lb:
        import csv
        with open(lb) as f:
            for row in csv.DictReader(f):
                ratings[row["TeamName"]] = float(row["Score"])
    print(f"{a.label}  lb={os.path.basename(lb) if lb else 'NONE'}")

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

    rows = []
    for p in sorted(glob.glob(os.path.join(a.dir, "*.json"))):
        try:
            r = tape_row(p, ratings)
        except Exception as e:  # noqa: BLE001
            print(f"  SKIP {os.path.basename(p)}: {e}")
            continue
        if r:
            rows.append(r)
    rows.sort(key=lambda r: int(r["eid"]))
    if not rows:
        print("  no tapes with our team on them.")
        return

    hdr = (f"{'eid':10s} {'band':8s} {'margin':>8s} {'mel0':>4s} {'hire':>4s} "
           f"{'land':>4s} {'hrdPk':>5s} {'sellD':>5s} {'inc12':>5s} "
           f"{'milk':>5s} {'wool':>5s} {'wht':>5s} {'thirst':>6s} opp")
    print(hdr)
    for r in rows:
        print(f"{r['eid']:10s} {band_of(r['band']):8s} {r['margin']:+8.0f} "
              f"{r['melon0']:4d} {r['hires']:4d} {r['land']:4d} {r['herd_peak']:5d} "
              f"{r['sell_days']:5d} {r['income_days']:5d} "
              f"{r['milk']:5d} {r['wool']:5d} {r['wheat']:5d} {r['thirst']:6d} "
              f"{r['opp'][:18]}")

    n = len(rows)
    print(f"\n== {a.label} aggregates (n={n}) ==")
    for key, fmt in (("melon0", "%.1f"), ("hires", "%.0f"), ("land", "%.1f"),
                     ("herd_peak", "%.1f"), ("sell_days", "%.1f"),
                     ("income_days", "%.1f"), ("milk", "%.0f"), ("wool", "%.0f"),
                     ("wheat", "%.0f"), ("thirst", "%.1f")):
        vals = [r[key] for r in rows]
        print(f"  {key:11s} mean {sum(vals)/n:7.1f}  min {min(vals):5.0f}  "
              f"max {max(vals):5.0f}")
    w = sum(1 for r in rows if r["margin"] > 0)
    print(f"  W/L {w}-{n - w}  mean margin {sum(r['margin'] for r in rows)/n:+,.0f}")
    for b in ("<500", "500-540", "540-600", "600-800", "800+"):
        seg = [r for r in rows if band_of(r["band"]) == b]
        if seg:
            sw = sum(1 for r in seg if r["margin"] > 0)
            print(f"  {b:8s} {sw}W-{len(seg) - sw}L  mean margin "
                  f"{sum(r['margin'] for r in seg)/len(seg):+10,.0f}  "
                  f"melon0 {sum(r['melon0'] for r in seg)/len(seg):.1f}  "
                  f"herdPk {sum(r['herd_peak'] for r in seg)/len(seg):.1f}  "
                  f"thirst {sum(r['thirst'] for r in seg)/len(seg):.0f}")


if __name__ == "__main__":
    main()
