"""A4 fingerprint: which engine version recorded this replay?

Reads one episode replay JSON (Kaggle format, same shape as
calibration/real_engine/tutorial_episode.json) and prints a verdict table for the
mechanics that changed between kaggle-environments versions or sit between
source-default and competition-config:

  town-center tau        CONFIRMED only on steps where every town-center product drops
                         exactly -1 simultaneously; the inter-event gap names tau (12 vs 24).
  town-center schedule   1.32.2 scaled the centre (1 -> 2 -> 4 units/day by day 10/20);
                         1.32.7 is flat 1. Multi-unit synchronized drops expose it.
  shop draw              any duplicate shop name => with replacement; eight distinct
                         shops by day 24 => without replacement (p = 0.24% otherwise);
                         else UNDECIDED.
  melon growth window    traced tile yield vs age (cap 6, first_yield 10) -- identical in
                         both versions, so this row validates the trace, not the version.
  below-curve family     (inventory, price) pairs from market obs against each version's
                         below_func set, requiring exact reproduction of every point.

The pinned repo reference is 1.32.7 (calibration/engine). A replay that CONFIRMS the
1.32.2 family on tau/curves tells you the ladder is running old mechanics -- re-tag
constants.py from THAT, re-run the A5 sweep gate, and record it in calibration/live.md.

Usage:  .venv/bin/python calibration/fingerprint.py [replay.json]
"""

from __future__ import annotations

import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kagfarm.constants import I0, MARKET_PARAMS, SHOP_TABLE, TOWN_CENTER_PRODUCTS, _f  # noqa: E402

DEFAULT_REPLAY = os.path.join(_HERE, "real_engine", "tutorial_episode.json")

# The two candidate mechanics sets, keyed by version.
CANDIDATES = {
    "1.32.2": {"tau": 12, "schedule": [(20, 4), (10, 2), (0, 1)],
               "below": {"CARROT": ("log", 0.20), "TOMATO": ("linear", 0.40), "EGG": ("linear", 0.40)}},
    "1.32.7": {"tau": 24, "schedule": None,
               "below": {"CARROT": ("hinge", 1.00), "TOMATO": ("hinge", 0.40), "EGG": ("hinge", 0.40)}},
}


def _shape(func, x, T):
    x = max(0.0, x)
    if func == "linear":
        return x
    if func == "sq":
        return x * x
    if func == "sqrt":
        return math.sqrt(x)
    if func == "log":
        return math.log(1.0 + x)
    if func == "hinge":
        u = x / T
        return u + 8.0 * max(0.0, u - 1.0) ** 2
    raise ValueError(func)


def price_at(good, inventory):
    """The pinned engine's marginal price -- used only to frame expectations."""
    p = MARKET_PARAMS[good]
    base, T = p["base"], p["T"]
    d = inventory - I0
    if d < 0:
        f, t, sign = p["below_f"], p["below_t"], +1
    else:
        f, t, sign = p["above_f"], p["above_t"], -1
    fT = _f(f, T, T)
    amp = t * base / fT if fT else 0
    return max(1, round(base + sign * amp * _f(f, abs(d), T)))


def town_center_events(steps):
    """Steps where the ONLY market movements are town-center drops.

    Returns a list of (step, per-good drop dict) for synchronized events with no SELL
    contamination: a drop event qualifies when at least 6 town-center goods fall and no
    good anywhere RISES (a rise means an agent sold that turn).
    """
    tc = set(TOWN_CENTER_PRODUCTS)
    events = []
    for t in range(1, len(steps)):
        inv0 = steps[t - 1][0]["observation"]["market"]["inventory"]
        inv1 = steps[t][0]["observation"]["market"]["inventory"]
        drops, rises = {}, False
        for g, v in inv1.items():
            d = v - inv0.get(g, v)
            if d > 0:
                rises = True
                break
            if d < 0 and g in tc:
                drops[g] = -d
        if rises or len(drops) < len(tc) - 2:
            continue
        events.append((t, drops))
    return events


def verdict_tau(events):
    """Clean tau = every town-center product dropping exactly 1, on a fixed period."""
    clean = [(t, d) for t, d in events if all(v == 1 for v in d.values()) and len(d) == len(TOWN_CENTER_PRODUCTS)]
    if len(clean) < 3:
        return "UNDECIDED", "only %d clean single-unit events" % len(clean)
    gaps = [b[0] - a[0] for a, b in zip(clean, clean[1:]) if b[0] - a[0] < 200]
    if not gaps:
        return "UNDECIDED", "no two clean events within a season of each other"
    period = min(gaps)
    if all(g % period == 0 for g in gaps):
        tau = 24 if period == 24 else (12 if period == 12 else None)
        if tau:
            return "CONFIRMED", "synchronized -1 across all 8 town-center goods every %d turns" % tau
        return "UNDECIDED", "period %d matches neither candidate" % period
    return "UNDECIDED", "irregular gaps %s" % gaps[:6]


def verdict_schedule(events):
    """1.32.2's centre scales 1 -> 2 -> 4 by day 10/20; 1.32.7 is flat 1."""
    by_day = {}
    for t, d in events:
        day = t // 24
        units = set(d.values())
        if len(units) == 1:
            by_day.setdefault(day, set()).add(next(iter(units)))
    scaled = [day for day, units in sorted(by_day.items()) if units & {2, 3, 4}]
    if scaled:
        return "CONFIRMED", "multi-unit centre drops on days %s -> 1.32.2 schedule" % scaled[:8]
    if by_day:
        return "CONFIRMED", "flat 1-unit centre drops all season -> 1.32.7"
    return "UNDECIDED", "no single-valued centre events"


def verdict_shops(steps):
    names = []
    for row in steps:
        tl = row[0]["observation"].get("town", {}).get("unlocked_shops") or []
        if len(tl) > len(names):
            names = list(tl)
    if not names:
        return "UNDECIDED", "no shop list in the observations"
    dupes = len(names) - len(set(names))
    if dupes:
        return "CONFIRMED", "duplicate shop(s) present => WITH replacement"
    if len(names) >= 8 and len(set(names)) == 8:
        return "CONFIRMED", "eight distinct shops => WITHOUT replacement (p=0.24%% under replacement)"
    return "UNDECIDED", "%d shops unlocked, no duplicate yet and not all 8 distinct" % len(names)


def verdict_melon(steps):
    """Trace every melon tile's (age, yield) pairs; the cap/window family is shared."""
    best = {}
    for row in steps:
        for farm in row[0]["observation"]["farms"]:
            tiles = farm["tiles"]
            for y in range(len(tiles)):
                for x in range(len(tiles[y])):
                    tile = tiles[y][x]
                    if isinstance(tile, dict) and tile.get("kind") == "PLANT" and tile.get("crop") == "MELON":
                        age = row[0]["observation"]["day"] - tile["planted_day"]
                        u = tile["yield_units"]
                        if u > best.get(age, -1):
                            best[age] = u
    if not best:
        return "UNDECIDED", "no melon tile ever planted"
    capped_at_6 = any(v >= 6 for v in best.values())
    first6 = min((a for a, v in best.items() if v >= 6), default=None)
    if capped_at_6 and first6 is not None and first6 <= 12:
        return "CONFIRMED", "melon reaches 6 units by age %d (cap 6, window open by 6..12)" % first6
    return "UNDECIDED", "yield trajectory %s does not pin the window" % dict(sorted(best.items())[:6])


def verdict_curves(steps):
    """Exact-fit test of each version's below-curve family on observed (inv, price) pairs."""
    pairs = {}
    for row in steps:
        m = row[0]["observation"]["market"]
        for g, inv in m["inventory"].items():
            px = m["prices"][g]
            if inv < I0 and (g, inv) not in pairs:
                pairs[(g, inv)] = px
    out = {}
    for good in ("CARROT", "TOMATO", "EGG"):
        pts = [(inv, px) for (g, inv), px in pairs.items() if g == good]
        if len(pts) < 20:
            out[good] = "UNDECIDED (only %d points)" % len(pts)
            continue
        hits = {}
        for ver, spec in CANDIDATES.items():
            func, target = spec["below"][good]
            T = MARKET_PARAMS[good]["T"]
            base = MARKET_PARAMS[good]["base"]
            fT = _f(func, T, T)
            amp = target * base / fT if fT else 0
            ok = all(max(1, round(base + amp * _f(func, I0 - inv, T))) == px for inv, px in pts)
            hits[ver] = ok
        if all(hits.values()):
            out[good] = "UNDECIDED (both families fit %d points)" % len(pts)
        elif any(hits.values()):
            ver = next(v for v, ok in hits.items() if ok)
            out[good] = "%s family exact on %d/%d points" % (ver, len(pts), len(pts))
        else:
            out[good] = "REFUTED both (%d points match neither)" % len(pts)
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REPLAY
    with open(path) as f:
        replay = json.load(f)
    steps = replay["steps"]
    cfg = replay.get("configuration", {})

    print(f"replay: {path}")
    print(f"recorded configuration says townCenterSellInterval = {cfg.get('townCenterSellInterval')}")
    print(f"module_version at record time: {replay.get('module_version', '?')}\n")

    # PRIMARY verdict: re-simulate the recorded episode under each vendored engine. A
    # replay matches exactly one mechanics set — nothing else is needed to date it.
    sys.path.insert(0, _HERE)
    from verify_replay import resimulate, ENGINE_DIR_1322, ENGINE_DIR
    for tag, d in (("1.32.2", ENGINE_DIR_1322), ("1.32.7", ENGINE_DIR)):
        try:
            exact, failed, first_bad = resimulate(replay, d)
            if failed == 0:
                print(f"RE-SIMULATION under {tag}: EXACT — {exact}/{len(steps)-1} steps reproduce.")
                print(f"  ==> The recording IS {tag} mechanics. Constants follow {tag} for every row this pins.\n")
            else:
                fb = first_bad[0] if first_bad else None
                where = f"(first divergence at step {fb[0]}, field {fb[2][0][0] if fb and fb[2] else '?'})" if fb else ""
                print(f"RE-SIMULATION under {tag}: {failed}/{len(steps)-1} steps mismatched {where}")
                print(f"  ==> NOT {tag} mechanics.\n")
        except Exception as e:  # engine dir missing, interpreter crash, ...: report, continue
            print(f"RE-SIMULATION under {tag}: unavailable ({e})\n")

    # SUPPORTING detail: heuristic rows, kept because they work even on a replay with no
    # recorded actions and because they name the discriminating events for a human.
    print("Supporting heuristic rows (robust even without recorded actions):")
    events = town_center_events(steps)
    v_tau, d_tau = verdict_tau(events)
    print(f"  town-center drain period  : {v_tau:10}  {d_tau}")
    v_sh, d_sh = verdict_shops(steps)
    print(f"  shop draw                 : {v_sh:10}  {d_sh}")
    v_me, d_me = verdict_melon(steps)
    print(f"  melon growth window       : {v_me:10}  {d_me}")
    curves = verdict_curves(steps)
    for g, v in curves.items():
        print(f"  below-curve {g:<8}      : {v}")

    print("\nInterpretation: the re-simulation block dates the replay to one mechanics set.")
    print("A CONFIRMED 1.32.2 result means the ladder is running pre-1.32.7 rules: re-tag")
    print("constants.py from that set (tau, schedule, hinge vs log/linear, replacement),")
    print("re-run the A5 gate, and record the verdict in calibration/live.md. UNDECIDED rows")
    print("on a LADDER replay mean: wait for a second replay. Never guess.")


if __name__ == "__main__":
    main()
