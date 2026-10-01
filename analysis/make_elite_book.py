"""Build kagfarm/opening_book_elite.json — the FULL ELITE CLONE book (mission phase 1).

Source: the 12 restored full 30-day Majkel top-10 replays (analysis/replays/).
Output: per-day, multi-variant donor scripts (per-hour verbatim actions) keyed by
the v2 dawn signature:

    [day, shop_unlocks, money_bucket, herd_size, wool, grain_bucket, fert_bucket]

v2 hardening (both LLM critics, 0930): explicit day key (no cross-day collision),
money/grain/fert BUCKETS ($1-drift kills when opponent trades shift our curve),
herd size + wool as leading divergence indicators, opponent state deliberately
excluded (opponent RNG must not fracture variants prematurely).

Replay convention (verified 719/719-exact via calibration/verify_replay.py on 110886706,
0930c): steps[t][p].action was decided from steps[t-1][p].observation and EXECUTED during
engine step t-1, producing steps[t][p].observation. Equivalently: the action decided from
obs@t is steps[t+1].action. (The pre-0930c window steps[dawn+h].action was off by one hour:
d0/d1 sigs still matched because money/herd are shift-robust, but d2 killed an animal on a
late feed and d3's shop unlock rerolled — a trade crossed the unlock draw's RNG boundary.)
So day d's book is: sig from steps[dawn] (the live dawn's decision state — post-state of
engine step dawn-1), actions from steps[dawn+h+1].action for h in 0..23.

Usage:
  .venv/bin/python analysis/make_elite_book.py            # -> kagfarm/opening_book_elite.json
  .venv/bin/python analysis/make_elite_book.py --until 30 # default: all 30 days
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EIDS = ["110886706", "110900752", "110907373", "110913896", "110920455",
        "110926948", "110932461", "110938064", "110943566", "110948948",
        "110954233", "111016701"]
# TeamNames order IS seat order for these tapes; the four inverted games are known
# (bank-verified on the 0927/0930 autopsies).
SEATS = {"110907373": 1, "110938064": 1, "110943566": 1, "111016701": 1}


def money_bucket(m):
    m = m if m is not None else 0
    if m < 0:
        return -1
    for i, cap in enumerate((0, 500, 1000, 2000, 4000, 8000, 16000, 32000, 64000, 128000)):
        if m <= cap:
            return i
    return 10


def grain_bucket(w):
    w = w or 0
    if w <= 0:
        return 0
    if w <= 4:
        return 1
    if w <= 10:
        return 2
    if w <= 20:
        return 3
    if w <= 40:
        return 4
    return 5


def fert_bucket(f):
    f = f or 0
    if f <= 0:
        return 0
    if f <= 4:
        return 1
    if f <= 10:
        return 2
    if f <= 20:
        return 3
    return 4


def herd_size(tiles):
    n = 0
    for row in (tiles or []):
        for t in row:
            if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") \
                    and t.get("animal"):
                n += 1
    return n


def sig_v2(day, obs):
    """v3 sig shape (0930d): same 7 slots, same bucket edges as v2. The MATCHING
    semantics changed in kagfarm/policy.py, not the recorded values: shop sets are
    stored verbatim (matching compares COUNT ±1), wool ±1, grain ±2, money/fert ±1
    buckets, day/herd exact. Keep the recorded values identical so a rebuilt book
    differs only by the meta note."""
    me = (obs.get("farms") or [{}])[obs.get("player", 0)]
    priv = (obs.get("private") or {})
    shed = priv.get("shed") or {}
    shops = tuple(sorted((obs.get("town") or {}).get("unlocked_shops") or []))
    return [day, list(shops), money_bucket(me.get("money")), herd_size(me.get("tiles")),
            int(shed.get("WOOL", 0) or 0),
            grain_bucket(shed.get("WHEAT", 0) or 0),
            fert_bucket(shed.get("FERTILIZER", 0) or 0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", type=int, default=30)
    ap.add_argument("--out", default=os.path.join(HERE, "kagfarm", "opening_book_elite.json"))
    a = ap.parse_args()

    days = {}
    for eid in EIDS:
        path = os.path.join(HERE, "analysis", "replays", f"{eid}.json")
        d = json.load(open(path))
        steps = d["steps"]
        seat = SEATS.get(eid, 0)
        for day in range(a.until):
            dawn = day * 24
            if dawn >= len(steps):
                break
            obs = dict(steps[dawn][seat].get("observation") or {})
            if "player" not in obs:
                obs["player"] = seat
            sig = sig_v2(day, obs)
            hours = []
            for h in range(24):
                i = dawn + h + 1          # action decided from obs@(dawn+h) lives one later
                if i >= len(steps):
                    break
                act = steps[i][seat].get("action") or {}
                hours.append([list(act.get("farmer") or ["PASS"]),
                              [list(x) for x in (act.get("hands") or [])],
                              [list(m) for m in (act.get("market") or [])]])
            days.setdefault(day, []).append({"sig": sig, "hours": hours, "donor": eid})

    book = {"meta": {"donor": "majkel_top10_restored12_FULL30",
                     "until_day": a.until, "sig_version": 3,
                     "note": "W1 full elite clone (0930d): byte-exact d0-29 of the top-10 "
                             "program; sig v3 matching - day/herd exact, shop COUNT +/-1 "
                             "(names never matched), wool +/-1, grain +/-2, money/fert "
                             "+/-1; rescue tier capped (book_rescue_cap)"},
            "days": {str(k): v for k, v in sorted(days.items())}}
    # 0930d: bundle.py embeds this file inside r'''...''' -- triple quotes or
    # backslashes would corrupt the flattened build. Fail HERE at build time
    # (the 0930d bake caught this only at bundle time: a non-ASCII +/- in the
    # note became a \\u00b1 escape, silently leaving submission/main.py stale).
    payload = json.dumps(book)
    if "'''" in payload or "\\" in payload:
        raise SystemExit("make_elite_book: book payload contains triple quotes or "
                         "backslashes -- keep the meta note ASCII; the raw-string "
                         "embedding is unsafe.")
    open(a.out, "w").write(payload)
    print(f"wrote {a.out} ({os.path.getsize(a.out)} bytes)")
    for day in range(a.until):
        vs = days.get(day, [])
        sigs = {tuple(json.dumps(v["sig"])) for v in vs}
        print(f"  day {day:2d}: {len(vs):2d} variants, {len(sigs)} distinct sigs")


if __name__ == "__main__":
    main()
