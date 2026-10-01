"""Telemetry dump — open questions #13/#16/#17/#14 as one pass over every tape.

The 0925o program turns four open questions into DAILY TELEMETRY instead of open
questions. Every new tape should emit:

  money_flow     #13  day -> bank delta d8-24, plus that day's order counts by type
                     (names the sink day and what was bought when the bank bled)
  losses         #16  thirst deaths (PLANT->WEED with consecutive_unwatered>=1, the
                     real_env classifier) per day; animal-count drops per day
                     (unfed/escape proxy — the drip's solvency guard question)
  fallback       #17  BUY_PRODUCT fires per good with quantity and day spread (the
                     drip's re-buy churn) and the SELL side of the same spread
  wheat_outflow  #14  per-day executed wheat shed outflow (the winners' 14-71/day
                     cadence is the bar; pre-drip games showed ~0-5)

Usage:
    .venv/bin/python analysis/telemetry_dump.py path/to/episode.json [more.json ...]
    .venv/bin/python analysis/telemetry_dump.py --dir submission15games
    .venv/bin/python analysis/telemetry_dump.py --dir X --json analysis/telemetry

--json writes one file per tape (merged for both seats) into a directory for the
morning loop; without it the summary prints to stdout only.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.profile_replay import profile, our_seat, executed_flow  # noqa: E402

ORDER_TYPES = ("BUY_SEED", "BUY_ANIMAL", "BUY_LAND", "HIRE", "SELL", "BUY_PRODUCT")


def _tile_kind(t):
    return t.get("kind") if isinstance(t, dict) else None


def thirst_and_animals(path):
    """Per-day thirst deaths and animal-count drops from the tile snapshots.

    Tiles live in the observation every step; the end-of-day refresh is what kills a
    dry plant, so comparing consecutive DAYS' snapshots (last step of day d vs last
    step of day d+1 at the same coordinates) attributes the death to the right night.
    A PLANT->WEED transition with consecutive_unwatered>=1 on the before-tile is
    thirst (same classifier as bridge/real_env._plant_death_kind); any other
    PLANT->WEED is 'spent' (lifespan exhausted). Animals sit on COOP/PASTURE tiles;
    a day-over-day drop in the animal census is the unfed/escape signal #16 asks for.
    """
    with open(path) as f:
        d = json.load(f)
    steps = d["steps"]
    n_seats = len(steps[0])
    out = {}
    for p in range(n_seats):
        thirst = Counter()
        spent = Counter()
        animals = Counter()
        prev_tiles = None
        prev_day = None
        for i, st in enumerate(steps):
            o = st[p].get("observation") or {}
            day = o.get("day", i // 24)
            farm = (o.get("farms") or [None, None])[p]
            if farm is None:
                continue
            tiles = farm.get("tiles") or []
            # census animals on structure tiles (majkel_labor's definition)
            n_an = 0
            for row in tiles:
                for t in row:
                    if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"):
                        n_an += int(t.get("animals", 0) or 0)
            animals[day] = n_an
            if prev_tiles is not None and day != prev_day:
                for y in range(len(tiles)):
                    for x in range(len(tiles[y])):
                        b = _tile_kind(prev_tiles[y][x])
                        a_ = _tile_kind(tiles[y][x])
                        if b == "PLANT" and a_ == "WEED":
                            bt = prev_tiles[y][x]
                            if bt.get("consecutive_unwatered", 0) >= 1 \
                                    and not bt.get("watered_today"):
                                thirst[day] += 1
                            else:
                                spent[day] += 1
            prev_tiles = tiles
            prev_day = day
        out[p] = dict(thirst=dict(thirst), spent=dict(spent),
                      animals={str(k): v for k, v in sorted(animals.items())},
                      animal_drops=_drops(animals))
    return out


def _drops(census):
    """Day -> loss where the animal census shrank day-over-day."""
    drops = {}
    days = sorted(census)
    for a, b in zip(days, days[1:]):
        if census[b] < census[a]:
            drops[b] = census[a] - census[b]
    return drops


def telemetry(path, seat=None):
    """The four signals for one tape. seat=None -> both seats where derivable."""
    prof = profile(path)
    seats = [seat] if seat is not None else sorted(prof)
    tile_stats = thirst_and_animals(path)
    res = {"path": os.path.basename(path), "seats": {}}
    for p in seats:
        pr = prof[p]
        # #13 money flow: bank delta + order mix per day
        mc = dict(pr["money_curve"])
        flow = {}
        order_days = defaultdict(Counter)
        for turn, orders in pr["orders"]:
            day = turn // 24
            for mo in orders:
                if mo and mo[0] in ORDER_TYPES:
                    order_days[day][mo[0]] += 1
        for day in sorted(mc):
            if 8 <= day <= 24:
                prev = mc.get(day - 1)
                flow[day] = {
                    "delta": (mc[day] - prev) if prev is not None else None,
                    "orders": dict(order_days.get(day, {})),
                }
        # #17 fallback fires (BUY_PRODUCT) and the sell side, per good
        buys = Counter()
        sells = Counter()
        buy_days = defaultdict(list)
        for turn, orders in pr["orders"]:
            for mo in orders:
                if not mo:
                    continue
                if mo[0] == "BUY_PRODUCT":
                    buys[mo[1]] += (mo[2] if len(mo) > 2 and isinstance(mo[2], int) else 1)
                    buy_days[mo[1]].append(turn // 24)
                elif mo[0] == "SELL":
                    sells[mo[1]] += (mo[2] if len(mo) > 2 and isinstance(mo[2], int) else 1)
        # #14 wheat outflow: per-day executed shed deltas
        wheat_out = {}
        prev_w = None
        for day, shed in pr["sheds"]:
            w = shed.get("WHEAT", 0)
            if prev_w is not None and w < prev_w:
                wheat_out[day] = prev_w - w
            prev_w = w
        ts = tile_stats.get(p, {})
        res["seats"][p] = dict(
            final_money=pr["final_money"],
            money_flow=flow,
            thirst=ts.get("thirst", {}), spent=ts.get("spent", {}),
            animal_drops=ts.get("animal_drops", {}),
            animal_census=ts.get("animals", {}),
            fallback={g: {"qty": n, "days": sorted(set(buy_days[g]))}
                      for g, n in buys.items()},
            sells_by_good=dict(sells),
            wheat_outflow=wheat_out,
            executed=dict(executed_flow(pr)),
        )
    return res


def _print(res):
    print("=" * 78)
    print(res["path"])
    for p, r in sorted(res["seats"].items()):
        print(f" seat {p}: final ${r['final_money'] or 0:,.0f}")
        flow = {d: v["delta"] for d, v in r["money_flow"].items() if v["delta"] is not None}
        neg = {d: v for d, v in flow.items() if v < 0}
        print(f"   d8-24 bank deltas: {flow}")
        if neg:
            worst = min(neg, key=neg.get)
            print(f"   SINK: d{worst} {neg[worst]:+.0f}  "
                  f"orders that day: {r['money_flow'][worst]['orders']}")
        th = sum(r["thirst"].values())
        sp = sum(r["spent"].values())
        print(f"   losses: thirst={th} spent={sp} animal_drops={r['animal_drops']}")
        fb = r["fallback"]
        if fb:
            print("   fallback(BUY_PRODUCT): " + ", ".join(
                f"{g}x{v['qty']} d{v['days'][0]}-{v['days'][-1]}" for g, v in fb.items()))
        else:
            print("   fallback(BUY_PRODUCT): none")
        wo = r["wheat_outflow"]
        if wo:
            days = sorted(wo)
            print(f"   wheat outflow/day: {wo}  (days {days[0]}-{days[-1]}, "
                  f"total {sum(wo.values())})")
        else:
            print("   wheat outflow/day: none")


def main(argv):
    args = list(argv)
    json_dir = None
    dir_path = None
    seat = None
    paths = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            i += 1
            json_dir = args[i]
        elif a == "--dir":
            i += 1
            dir_path = args[i]
        elif a == "--seat":
            i += 1
            seat = int(args[i])
        elif a.endswith(".json"):
            paths.append(a)
        i += 1
    if dir_path:
        paths.extend(sorted(
            os.path.join(dir_path, f) for f in os.listdir(dir_path)
            if f.endswith(".json")))
    if not paths:
        print(__doc__)
        return
    if json_dir:
        os.makedirs(json_dir, exist_ok=True)
    for path in paths:
        try:
            res = telemetry(path, seat)
        except Exception as e:                       # one bad tape never kills the loop
            print(f"!! {path}: {e!r}")
            continue
        _print(res)
        if json_dir:
            name = os.path.basename(path)
            with open(os.path.join(json_dir, name), "w") as f:
                json.dump(res, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
