"""0930l P0 book audit — measure elite-book state aliasing and hands-reshape exposure.

The plan's P0 claim: the book signature (day, shops, money_bucket, herd, WOOL,
wheat_bucket, fert_bucket) omits worker count, market state and opponent, so distinct
worlds can alias to the same trajectory, and the server reshapes donor actions
(PASS-pad or truncate) to the live roster — a silent labor-topology mismatch.

Measured here, no engine runs, replays only:
  A. Cross-donor aliasing: for each day, do two donor chains share a signature?
     (Group all donor dawns by sig; a sig held by >1 donor on the same day is an
     aliasing width>1 event.) Cross-tab with hands counts: aliasing events where the
     two donors' rosters differ are the DANGEROUS class — same key, different labor.
  B. Ladder exposure: for each dawn of both ladder episodes, how many donor-chain
     day-entries match the live sig (strict tier), and how many of the matching
     entries imply a hands count different from the live roster (the reshape case)?
  C. Rescue-tier widening: strict-miss dawns that the rescue band (+-1 shop count,
     +-1 wool, +-2 grain) would admit — the plan's "wrong world on purpose" surface.

Donor hands for day d = len(steps[d*24][seat].action.hands) + 1 (farmer), from the
donor's own recording. Live hands = len(obs.farms[seat].hands) + 1.

Usage:
  PYTHONHASHSEED=0 .venv/bin/python analysis/book_audit_0930l.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kagfarm.policy import opening_book_signature  # noqa: E402

REPLAYS_DIR = os.path.join(_ROOT, "analysis", "replays")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
LADDER = [("A", os.path.join(DOWNLOADS, "115866226.json")),
          ("B", os.path.join(DOWNLOADS, "115863161.json"))]
SEATS = {"110907373": 1, "110938064": 1, "110943566": 1, "111016701": 1}
DAYS = range(30)


def load(path):
    with open(path) as f:
        return json.load(f)


def dawn_obs(steps, seat, day):
    """The observation OUR seat acts on at dawn of `day` (action decided here is
    steps[day*24][seat].action per verify_replay alignment... for the BOOK the live
    dawn obs in the harness is env._obs_view at t=day*24, i.e. obs produced BY
    step day*24 — the same object recorded at steps[day*24][seat].observation)."""
    o = steps[day * 24][seat]["observation"]
    v = copy.deepcopy(o)
    v.setdefault("player", seat)
    return v


def hands_of_obs(obs, seat):
    farm = (obs.get("farms") or [{}])[seat]
    return len(farm.get("hands") or []) + 1


def hands_of_action(act):
    return len((act or {}).get("hands") or []) + 1


def in_rescue_band(live, donor):
    """0930d rescue band: shop COUNT +-1, wool +-1, wheat bucket +-2 (raw units),
    fert bucket +-2; day equal; shop NAMES must match; herd equal; money bucket equal."""
    (ld, lshops, lmb, lherd, lwool, lwheat, lfert) = live
    (dd, dshops, dmb, dherd, dwool, dwheat, dfert) = donor
    if ld != dd or lshops != dshops or lmb != dmb or lherd != dherd:
        return False
    return (abs(lwool - dwool) <= 1 and abs(lwheat - dwheat) <= 2 and abs(lfert - dfert) <= 2)


def main():
    # ---- donor dawns ------------------------------------------------------
    donor_dawn = {}          # eid -> {day: (sig, hands, action_hands)}
    for fn in sorted(os.listdir(REPLAYS_DIR)):
        if not fn.endswith(".json"):
            continue
        eid = fn[:-5]
        d = load(os.path.join(REPLAYS_DIR, fn))
        seat = SEATS.get(eid, 0)
        steps = d["steps"]
        per = {}
        for day in DAYS:
            obs = dawn_obs(steps, seat, day)
            sig = opening_book_signature(obs)
            act = steps[day * 24][seat].get("action") or {}
            per[day] = (sig, hands_of_obs(obs, seat), hands_of_action(act))
        donor_dawn[eid] = per

    # ---- A: cross-donor aliasing per day ----------------------------------
    print("== A. Cross-donor signature aliasing (same sig, same day, different eid) ==")
    aliased_days = 0
    aliased_with_hands_mismatch = 0
    for day in DAYS:
        groups = defaultdict(list)
        for eid, per in donor_dawn.items():
            sig, hands, _ = per[day]
            groups[sig].append((eid, hands))
        multi = {s: v for s, v in groups.items() if len(v) > 1}
        mism = [(s, v) for s, v in multi.items()
                if len({h for _, h in v}) > 1]
        if multi:
            aliased_days += 1
        if mism:
            aliased_with_hands_mismatch += 1
            for s, v in mism[:3]:
                print(f"  d{day}: sig={s} donors={v}  <-- HANDS MISMATCH inside one sig")
        elif multi:
            for s, v in list(multi.items())[:2]:
                print(f"  d{day}: sig={s} donors={v}")
    print(f"  days with any aliasing: {aliased_days}/30; "
          f"days where aliased donors differ in hands: {aliased_with_hands_mismatch}/30")

    # donor roster vs donor action hands (reshape exposure even on own chain)
    own_mismatch = sum(1 for eid, per in donor_dawn.items() for day in DAYS
                       if per[day][1] != per[day][2])
    total = 12 * 30
    print(f"  donor own-roster vs own-action-hands mismatches: {own_mismatch}/{total}")

    # ---- B: ladder exposure -----------------------------------------------
    print("\n== B. Ladder dawns: strict-match width and reshape exposure ==")
    for name, path in LADDER:
        d = load(path)
        steps = d["steps"]
        seat = 0
        widths, reshapes, served_total = [], 0, 0
        detail = []
        for day in DAYS:
            obs = dawn_obs(steps, seat, day)
            live = opening_book_signature(obs)
            live_hands = hands_of_obs(obs, seat)
            matching = [(eid, donor_dawn[eid][day][2]) for eid in donor_dawn
                        if donor_dawn[eid][day][0] == live]
            bad = [(eid, dh, live_hands) for eid, dh in matching if dh != live_hands]
            widths.append(len(matching))
            if matching:
                served_total += 1
            if bad:
                reshapes += 1
                detail.append((day, bad[:3], live_hands))
        print(f"  {name}: dawns with >=1 strict donor match: {served_total}/30; "
              f"mean match width {sum(widths)/30:.2f}; dawns where a matching donor's "
              f"hands != live: {reshapes}")
        for day, bad, lh in detail[:6]:
            print(f"     d{day}: live_hands={lh} mismatched donors={bad}")

    # ---- C: rescue widening -------------------------------------------------
    print("\n== C. Rescue-band widening (strict-miss dawns the band would admit) ==")
    for name, path in LADDER:
        d = load(path)
        steps = d["steps"]
        seat = 0
        rescue_days = []
        for day in DAYS:
            obs = dawn_obs(steps, seat, day)
            live = opening_book_signature(obs)
            strict = [eid for eid in donor_dawn if donor_dawn[eid][day][0] == live]
            if strict:
                continue
            band = [(eid, donor_dawn[eid][day][2]) for eid in donor_dawn
                    if in_rescue_band(live, donor_dawn[eid][day][0])]
            if band:
                rescue_days.append((day, band[:4]))
        print(f"  {name}: strict-miss dawns with rescue-band donors: {len(rescue_days)}")
        for day, band in rescue_days[:8]:
            print(f"     d{day}: {band}")

    print("\nAudit done (replays only; no engine runs).")


if __name__ == "__main__":
    main()
