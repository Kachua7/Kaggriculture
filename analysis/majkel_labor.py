"""Majkel1337 d8-20 labor census from the restored replay episodes.

Question answered (measured 2026-09-22, before building the care-rate gate):
how many workers does Majkel put on FEED/CARE/HARVEST per day, what raw op
counts that sustains, and what care rate his herd shows -- so the shepherd
ratio and the gate threshold are calibrated to HIS numbers, not an estimate.

Method (no mirror assumptions):
- Seat: Majkel = the seat with the higher final reward (he wins all restored
  episodes; validated against the restored dossier).
- Ops read verbatim from steps[i][seat]["action"]["farmer"/"hands"].
- HARVEST attribution: an animal HARVEST is one issued while the worker stood
  on a PASTURE/COOP tile the turn before (position from the steps[i-1]
  observation); residual crop HARVESTs are counted separately. Per-episode
  attribution ambiguity (co-located crop+animal tiles) is 1.2-5%.
- Care rate: each animal tile's fed_today/cared_today flags at END of day
  (steps[day*24+23] observation) -- raw engine state.
- Worker = farmer (0) or hand index (1..N); one op per worker per turn, so
  "distinct workers on animal ops" == worker-turns spent on animals that day.

Run: python3 analysis/majkel_labor.py
"""
import glob
import json
import os
from collections import defaultdict

ANIMAL_KINDS = ("PASTURE", "COOP")
# Canonical corpus: the 13 restored Majkel episodes + 1 (analysis/replays).
# ~/Downloads deliberately NOT scanned: it mixes unrelated episodes (our own
# early games and newer non-dossier Majkel games) into the census.
DIRS = (os.path.join("analysis", "replays"),)
WINDOW = range(8, 21)          # d8..d20 inclusive
DETAIL_EP = "110886706"
MOVES = ("NORTH", "SOUTH", "EAST", "WEST", "PASS")


def is_episode(path):
    """Cheap filter: episode replays carry a 'steps' key (probed in the first
    2 MB -- 'steps' sits after the large 'configuration' block, so a tiny
    header read misses it). Small non-episode JSONs are rejected cheaply."""
    try:
        if os.path.getsize(path) > 2 * 1024 * 1024:
            return True          # only replays are this big
        with open(path, "rb") as fh:
            head = fh.read(2 * 1024 * 1024)
        return b'"steps"' in head
    except OSError:
        return False


def find_episodes():
    """Dedup by basename across DIRS (Downloads first, then the restored set)."""
    seen = {}
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        for p in sorted(glob.glob(os.path.join(d, "*.json"))):
            if is_episode(p):
                seen.setdefault(os.path.basename(p), p)
    return [seen[k] for k in sorted(seen)]


def op_name(x):
    """Op opcode of a worker action entry ('FEED' / 'CARE' / ... or None)."""
    if isinstance(x, str):
        return x
    if isinstance(x, (list, tuple)) and x and isinstance(x[0], str):
        return x[0]
    return None


def _animal_tiles(farm):
    out = set()
    for y, row in enumerate(farm.get("tiles") or []):
        for x, t in enumerate(row or []):
            if isinstance(t, dict) and t.get("kind") in ANIMAL_KINDS:
                out.add((x, y))
    return out


def census(path):
    """Per-episode aggregates for the d8-20 summary tables."""
    ep = json.load(open(path))
    steps = ep["steps"]
    rewards = ep.get("rewards") or [0, 0]
    seat = rewards.index(max(rewards))
    epw = defaultdict(set)          # day -> workers doing animal ops
    ep_ops = defaultdict(int)
    ep_herd = ep_fed = ep_cared = 0
    detail = defaultdict(lambda: defaultdict(int))
    is_det = os.path.basename(path).startswith(DETAIL_EP)

    for i in range(1, len(steps)):
        day = i // 24
        in_window = day in WINDOW
        a = steps[i][seat].get("action")
        if not isinstance(a, dict):
            continue
        fa = op_name(a.get("farmer"))
        hlist = [op_name(e) for e in (a.get("hands") or [])]
        has_harvest = "HARVEST" in ([fa] + hlist)
        atiles = _animal_tiles(steps[i - 1][seat]["observation"]["farms"][seat]) \
            if has_harvest else set()
        prev = steps[i - 1][seat]["observation"]["farms"][seat] if has_harvest else None
        for w, op in [(0, fa)] + list(enumerate(hlist, start=1)):
            if not op or op in MOVES:
                continue
            if op in ("FEED", "CARE"):
                if in_window:
                    ep_ops[op] += 1
                epw[day].add(w)
                if is_det:
                    detail[day][w] += 1
            elif op == "COLLECT_FERTILIZER":
                if in_window:
                    ep_ops["FERT"] += 1
                epw[day].add(w)
                if is_det:
                    detail[day][w] += 1
            elif op == "HARVEST":
                on_animal = False
                if prev is not None:
                    try:
                        pos = prev["farmer"] if w == 0 else prev["hands"][w - 1]
                        on_animal = tuple(pos) in atiles
                    except Exception:
                        on_animal = False
                if on_animal:
                    if in_window:
                        ep_ops["HARVan"] += 1
                    epw[day].add(w)
                    if is_det:
                        detail[day][w] += 1
                elif in_window:
                    ep_ops["HARVc"] += 1
            elif in_window:
                ep_ops["oth"] += 1

    hand_days = 0
    hands_total = 0
    for day in range(30):
        try:
            farm = steps[day * 24][seat]["observation"]["farms"][seat]
            hands_total += 1 + len(farm.get("hands") or [])
            hand_days += 1
        except Exception:
            pass
        try:
            farm = steps[day * 24 + 23][seat]["observation"]["farms"][seat]
        except Exception:
            continue
        if day not in WINDOW:
            continue
        nh = nf = nc = 0
        for row in (farm.get("tiles") or []):
            for t in (row or []):
                if isinstance(t, dict) and t.get("kind") in ANIMAL_KINDS:
                    nh += 1
                    nf += 1 if t.get("fed_today") else 0
                    nc += 1 if t.get("cared_today") else 0
        ep_herd += nh
        ep_fed += nf
        ep_cared += nc

    wd = sum(len(epw[d]) for d in WINDOW)
    return dict(
        name=os.path.basename(path)[:9],
        seat=seat,
        rewards=rewards,
        ops=dict(ep_ops),
        workers_per_day=wd / float(len(WINDOW)),
        hands_mean=hands_total / float(max(1, hand_days)),
        herd_mean_d820=ep_herd / float(len(WINDOW)),
        fed_pct=100.0 * ep_fed / max(1, ep_herd),
        cared_pct=100.0 * ep_cared / max(1, ep_herd),
        detail=dict(detail) if is_det else None,
    )


def pooled(paths, n):
    """Per-day pooled op table across all episodes (second pass by design:
    keeps the per-episode and per-day aggregations independent)."""
    pool = defaultdict(lambda: defaultdict(int))
    wkday = defaultdict(int)
    handsum = defaultdict(int)
    cnt_dawn = defaultdict(int)
    herd = defaultdict(int)
    fed = defaultdict(int)
    cared = defaultdict(int)
    for p in paths:
        ep = json.load(open(p))
        steps = ep["steps"]
        rewards = ep.get("rewards") or [0, 0]
        seat = rewards.index(max(rewards))
        ep_wkday = defaultdict(set)   # day -> distinct animal-workers that day
        for i in range(1, len(steps)):
            day = i // 24
            a = steps[i][seat].get("action")
            if not isinstance(a, dict):
                continue
            fa = op_name(a.get("farmer"))
            hlist = [op_name(e) for e in (a.get("hands") or [])]
            has_harvest = "HARVEST" in ([fa] + hlist)
            atiles = _animal_tiles(steps[i - 1][seat]["observation"]["farms"][seat]) \
                if has_harvest else set()
            prev = steps[i - 1][seat]["observation"]["farms"][seat] if has_harvest else None
            for w, op in [(0, fa)] + list(enumerate(hlist, start=1)):
                if not op or op in MOVES:
                    continue
                if op in ("FEED", "CARE", "COLLECT_FERTILIZER"):
                    pool[day][{"COLLECT_FERTILIZER": "FERT"}.get(op, op)] += 1
                    ep_wkday[day].add(w)
                elif op == "HARVEST":
                    on_animal = False
                    if prev is not None:
                        try:
                            pos = prev["farmer"] if w == 0 else prev["hands"][w - 1]
                            on_animal = tuple(pos) in atiles
                        except Exception:
                            on_animal = False
                    pool[day]["HARVan" if on_animal else "HARVc"] += 1
                    if on_animal:
                        ep_wkday[day].add(w)
                else:
                    pool[day]["oth"] += 1
        for day, ws in ep_wkday.items():
            wkday[day] += len(ws)     # +1 per episode per distinct worker
        for day in range(30):
            try:
                farm = steps[day * 24][seat]["observation"]["farms"][seat]
                handsum[day] += 1 + len(farm.get("hands") or [])
                cnt_dawn[day] += 1
            except Exception:
                pass
            try:
                farm = steps[day * 24 + 23][seat]["observation"]["farms"][seat]
            except Exception:
                continue
            nh = nf = nc = 0
            for row in (farm.get("tiles") or []):
                for t in (row or []):
                    if isinstance(t, dict) and t.get("kind") in ANIMAL_KINDS:
                        nh += 1
                        nf += 1 if t.get("fed_today") else 0
                        nc += 1 if t.get("cared_today") else 0
            herd[day] += nh
            fed[day] += nf
            cared[day] += nc
    return pool, wkday, handsum, cnt_dawn, herd, fed, cared


def main():
    paths = find_episodes()
    res = [census(p) for p in paths]
    n = len(res)
    pool, wkday, handsum, cnt_dawn, herd, fed, cared = pooled(paths, n)

    print(f"episodes: {n} (Majkel seat = higher final reward)")
    if n == 0:
        print("no episode replays found in:", ", ".join(DIRS))
        return
    print("\nper-day pooled: ops issued; distinct animal-workers/day; dawn hands;")
    print("herd at end of day; end-of-day fed/cared rate")
    print("".join(["day", " FEED", " CARE", "  HARan", " HARVc", " FERT", "  oth",
                   "  wk/day", " hands", "  herd", "  fed%", " care%"]))
    wdays = n * len(WINDOW)
    totA = sum(pool[d]["FEED"] + pool[d]["CARE"] + pool[d]["HARVan"] for d in WINDOW)
    totW = sum(wkday[d] for d in WINDOW)
    totH = sum(herd[d] for d in WINDOW)
    totF = sum(fed[d] for d in WINDOW)
    totC = sum(cared[d] for d in WINDOW)
    for day in range(30):
        nh = herd[day]
        fp = 100.0 * fed[day] / nh if nh else 0.0
        cp = 100.0 * cared[day] / nh if nh else 0.0
        star = "*" if day in WINDOW else " "
        print(f"{star}{day:3d} {pool[day]['FEED']:5d} {pool[day]['CARE']:5d} "
              f"{pool[day]['HARVan']:6d} {pool[day]['HARVc']:5d} {pool[day]['FERT']:5d} "
              f"{pool[day]['oth']:6d} {wkday[day] / float(n):7.2f} "
              f"{handsum[day] / float(max(1, cnt_dawn[day])):6.1f} {nh / float(n):6.1f} "
              f"{fp:6.1f} {cp:6.1f}")
    print()
    print(f"d8-20 totals ({wdays} episode-days): FEED+CARE+HARVan = {totA} ops, "
          f"{totW / float(wdays):.2f} distinct animal-workers per episode-day, "
          f"mean herd {totH / float(wdays):.2f}")
    print(f"d8-20 end-of-day fed rate {100.0 * totF / max(1, totH):.1f}%, "
          f"cared rate {100.0 * totC / max(1, totH):.1f}%")
    print()
    print("per-episode d8-20 (seat, finals, workers/day, mean hands, F/C/H, "
          "herd, fed%, care%):")
    for r in sorted(res, key=lambda r: -r["rewards"][r["seat"]]):
        o = r["ops"]
        other = r["rewards"][1 - r["seat"]]
        print(f"  {r['name']} s{r['seat']} {r['rewards'][r['seat']]:>7.0f}/{other:>7.0f} "
              f"wk {r['workers_per_day']:4.2f} hands {r['hands_mean']:4.1f} "
              f"F{o.get('FEED', 0):4d} C{o.get('CARE', 0):4d} H{o.get('HARVan', 0):4d}  "
              f"herd {r['herd_mean_d820']:5.2f}  fed {r['fed_pct']:5.1f}  "
              f"care {r['cared_pct']:5.1f}")
    det = next((r for r in res if r["detail"] is not None), None)
    if det:
        print()
        print(f"{det['name']} detail: animal-op turns per worker id per day (0=farmer):")
        for day in WINDOW:
            rowmap = det["detail"].get(day)
            if not rowmap:
                print(f"  d{day:2d}: -")
                continue
            parts = "  ".join(f"w{k}:{v}" for k, v in sorted(rowmap.items()))
            print(f"  d{day:2d}: {parts}")


if __name__ == "__main__":
    main()
