"""
Mechanical diff: our mirror against the real engine.

    python calibration/diff_truth.py            # after bootstrap.sh + calibrate.sh

Reads `truth.json` (real engine, from dump_truth.py) and `mirror.json` (ours, from
mirror_truth.py) and reports where they disagree. Both files are written by probes with the
same names and shapes, so this is a comparison rather than a reading exercise.

Two design choices worth stating:

  - Findings are ordered by **money at stake**, not alphabetically. A 1% error on melon's
    glut curve costs more than a 30% error on fertilizer, and a report sorted by good name
    buries that.
  - A missing probe is reported, never silently skipped. `truth.json` wraps each probe
    independently, so a partial dump is normal and it matters which half is missing.

Exit status is 0 if everything matched, 1 otherwise, so this can gate a commit.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TRUTH = os.path.join(HERE, "truth.json")
MIRROR = os.path.join(HERE, "mirror.json")

# Ordered by how much of the modelled bank rides on the answer (PLAN.md §2.8, §5.2).
GOOD_STAKES = [
    ("STRAWBERRY", "$36k — largest revenue line; 217% of base rests on its below-curve"),
    ("MELON",      "$31k — sets the shared melon pot and where the $1 floor lands"),
    ("MILK",       "livestock viability; idles at $317 vs $160 base"),
    ("WOOL",       "livestock viability; idles at $247 vs $200 base"),
    ("TOMATO",     "$8k"),
    ("WHEAT",      "$7k, plus it is the animal feed and the buy-back good"),
    ("EGG",        "bottomless filler"),
    ("CARROT",     "$3k, but the best short-cycle backfill crop"),
    ("FERTILIZER", "cost side only"),
]
CROP_STAKES = ["MELON", "STRAWBERRY", "TOMATO", "WHEAT", "CARROT"]

FAILURES = []


def load(path, label):
    if not os.path.exists(path):
        print(f"!! {label} missing: {path}")
        if label == "truth.json":
            print("   Run  bash bootstrap.sh  on the Mac (it chains into calibrate.sh).")
        else:
            print("   Run  python calibration/mirror_truth.py")
        sys.exit(2)
    with open(path) as fh:
        return json.load(fh)


def probe(doc, name):
    return (doc.get("probes") or {}).get(name)


def hr(title):
    print()
    print("=" * 88)
    print(title)
    print("=" * 88)


# ---------------------------------------------------------------------------
# 1. price grid — the single most load-bearing comparison
# ---------------------------------------------------------------------------

def diff_price_grid(truth, mirror):
    hr("1. PRICE CURVE   real engine vs mirror, per good, ordered by money at stake")
    t, m = probe(truth, "price_grid"), probe(mirror, "price_grid")
    if not t or not t.get("data"):
        note = (t or {}).get("note", "probe absent")
        print(f"   [SKIP] real engine exposed no price function: {note}")
        print("          Fall back to reading calibration/real_engine/ directly —")
        print("          bootstrap.sh copies the engine source there, which settles this")
        print("          by reading the rule rather than sampling it.")
        FAILURES.append("price_grid: no real-engine data")
        return
    if not m:
        FAILURES.append("price_grid: no mirror data")
        return

    print(f"   real fn: {t.get('fn')}{t.get('signature', '')}")
    print()
    print(f"{'good':12} {'n':>3} {'exact':>6} {'max err':>9} {'at inv':>8} "
          f"{'side':>6} {'real':>7} {'mirror':>7}  stake")
    for good, stake in GOOD_STAKES:
        tr, mr = (t["data"].get(good) or {}), (m["data"].get(good) or {})
        shared = [k for k in tr if k in mr and isinstance(tr[k], (int, float))]
        if not shared:
            print(f"{good:12} {'-':>3}  no overlapping samples")
            FAILURES.append(f"price_grid {good}: no overlapping samples")
            continue
        worst, exact = None, 0
        for k in shared:
            a, b = float(tr[k]), float(mr[k])
            if abs(a - b) < 1e-9:
                exact += 1
                continue
            rel = abs(a - b) / max(1.0, abs(a))
            if worst is None or rel > worst[0]:
                worst = (rel, k, a, b)
        if worst is None:
            print(f"{good:12} {len(shared):>3} {exact:>6} {'--':>9} {'':>8} "
                  f"{'':>6} {'':>7} {'':>7}  {stake}")
            continue
        rel, inv, a, b = worst
        side = "below" if int(inv) < 10000 else ("at I0" if int(inv) == 10000 else "above")
        print(f"{good:12} {len(shared):>3} {exact:>6} {rel:>8.1%} {inv:>8} "
              f"{side:>6} {a:>7.0f} {b:>7.0f}  {stake}")
        FAILURES.append(f"price_grid {good}: {rel:.1%} off at inv={inv} ({side} curve)")

    print()
    print("   A mismatch on the *below* side means the scarcity premium is wrong, which")
    print("   changes how much the town's drain is worth to us (PLAN.md §2.1). On the")
    print("   *above* side it changes how fast our own selling craters the price, which is")
    print("   the melon land-grab (§2.3). They are different bugs with different fixes.")


# ---------------------------------------------------------------------------
# 2. constants — the real engine's own tables, if it exposes them
# ---------------------------------------------------------------------------

def _find_tables(consts):
    """Pick out anything that looks like our OBJECT_TABLE / MARKET_PARAMS / SHOP_TABLE.

    We do not know the real engine's naming, so match on shape: a dict keyed by goods we
    recognise. That is more robust than guessing names and it surfaces tables we did not
    expect to find.
    """
    known = {g for g, _ in GOOD_STAKES} | {"GOOSE", "COW", "SHEEP"}
    out = {}
    for name, val in (consts or {}).items():
        if not isinstance(val, dict) or not val:
            continue
        keys = {str(k).upper() for k in val}
        if len(keys & known) >= 4:
            out[name] = val
    return out


def diff_constants(truth):
    hr("2. REAL ENGINE CONSTANTS   tables the engine exposes, matched by shape")
    consts = probe(truth, "module_constants")
    if not consts:
        print("   [SKIP] module_constants probe absent.")
        FAILURES.append("module_constants: absent")
        return

    sys.path.insert(0, os.path.dirname(HERE))
    from kagfarm.constants import OBJECT_TABLE, MARKET_PARAMS, SHOP_TABLE, I0

    scalars = {k: v for k, v in consts.items()
               if isinstance(v, (int, float, bool)) and not isinstance(v, bool)}
    print(f"   {len(consts)} module-level names, {len(scalars)} numeric scalars")
    ours = {"EPISODE_STEPS": 720, "TURNS_PER_DAY": 24, "BOARD_SIZE": 10,
            "STARTING_MONEY": 3000.0, "SHED_CAPACITY": 100, "I0": I0,
            "MAX_MARKET_ORDERS": 10, "WEED_SPAWN_CHANCE": 0.005}
    print()
    print(f"{'our name':22} {'ours':>12} {'real (matched by name)':>24}")
    for k, v in ours.items():
        hit = [(n, x) for n, x in scalars.items() if n.upper() == k]
        if not hit:
            hit = [(n, x) for n, x in scalars.items()
                   if abs(float(x) - float(v)) < 1e-9]
            shown = f"= {hit[0][0]}" if hit else "(not found)"
        else:
            shown = f"{hit[0][1]}"
            if abs(float(hit[0][1]) - float(v)) > 1e-9:
                shown += "  <-- MISMATCH"
                FAILURES.append(f"constant {k}: ours {v}, real {hit[0][1]}")
        print(f"{k:22} {v:>12} {shown:>24}")

    tables = _find_tables(consts)
    print()
    if not tables:
        print("   No good-keyed tables found at module level. Read the source in")
        print("   calibration/real_engine/ instead — it is copied there by bootstrap.sh")
        print("   and settles every §5.2 item by reading rather than inferring.")
        FAILURES.append("module_constants: no good-keyed tables found")
        return
    for name, tbl in tables.items():
        print(f"   found table `{name}` with {len(tbl)} entries; sample:")
        for k in list(tbl)[:3]:
            print(f"       {k}: {tbl[k]}")
    print()
    print("   Compare these by hand against kagfarm/constants.py — they are the direct")
    print("   answer to §5.2 items 1, 2 and 4, which are otherwise only sampled.")


# ---------------------------------------------------------------------------
# 3. yield trajectories and 4. rule checks
# ---------------------------------------------------------------------------

def _daily_units(trace):
    """{day: yield_units} from a probe trace, tolerant of a dead or empty tile."""
    out = {}
    for row in (trace or {}).get("daily", []):
        tile = row.get("tile")
        day = row.get("step", 0) // 24
        if isinstance(tile, dict) and tile.get("kind") == "PLANT":
            out[day] = tile.get("yield_units", 0)
        else:
            out[day] = None                     # tile is a weed, or empty
    return out


def diff_yields(truth, mirror):
    hr("3. YIELD TRAJECTORY   yield_units on the tile, per day, watered every turn")
    t, m = probe(truth, "yield_traces"), probe(mirror, "yield_traces")
    if not t or not m:
        print("   [SKIP] one side missing.")
        FAILURES.append("yield_traces: one side missing")
        return
    for crop in CROP_STAKES:
        tt, mm = t.get(crop) or {}, m.get(crop) or {}
        if tt.get("error"):
            print(f"   {crop:12} real-engine probe errored — see truth.json")
            FAILURES.append(f"yield_traces {crop}: real probe errored")
            continue
        a, b = _daily_units(tt), _daily_units(mm)
        days = sorted(set(a) & set(b))
        if not days:
            print(f"   {crop:12} no overlapping days")
            FAILURES.append(f"yield_traces {crop}: no overlapping days")
            continue
        bad = [d for d in days if a[d] != b[d]]
        head = f"   {crop:12} {len(days)} days compared, {len(bad)} differ"
        print(head if bad else head + "   [match]")
        if bad:
            FAILURES.append(f"yield_traces {crop}: {len(bad)}/{len(days)} days differ")
            for d in bad[:8]:
                print(f"       day {d:>2}: real {a[d]!s:>5}   mirror {b[d]!s:>5}")
        if all(v in (None, 0) for v in a.values()):
            print("       !! every real-engine day is dead/empty. That is the "
                  "unwatered-planting-day death — check dump_truth waters EVERY turn.")


def diff_rules(truth, mirror):
    hr("4. RULE CHECKS   yes/no questions that each flip a design decision")
    t, m = probe(truth, "rule_checks"), probe(mirror, "rule_checks")
    if not t or not m:
        print("   [SKIP] one side missing (mirror has them; real dump may predate them).")
        FAILURES.append("rule_checks: one side missing")
        return

    for key, field, label in (
            ("early_harvest_exploit", "exploit_open",
             "same-day melon harvest possible (would be the whole game)"),
            ("unwatered_on_plant_day", "died",
             "plant unwatered on its planting day dies (hard routing constraint)")):
        a = (t.get(key) or {}).get(field)
        b = (m.get(key) or {}).get(field)
        flag = "[match]" if a == b else "[DIFFER]"
        print(f"   {flag:9} {label}")
        print(f"             real {a!s:>7}   mirror {b!s:>7}")
        if a != b:
            FAILURES.append(f"rule_checks {key}: real {a}, mirror {b}")

    print()
    print("   units BANKED if you HARVEST on day D (the number the planner needs):")
    ta, mb = t.get("harvest_by_day") or {}, m.get("harvest_by_day") or {}
    for crop in CROP_STAKES:
        a, b = ta.get(crop) or {}, mb.get(crop) or {}
        days = sorted(set(a) & set(b), key=int)
        if not days:
            print(f"     {crop:12} no overlap")
            FAILURES.append(f"harvest_by_day {crop}: no overlap")
            continue
        cells = []
        bad = 0
        for d in days:
            same = a[d] == b[d]
            bad += 0 if same else 1
            cells.append(f"d{d}={a[d]}" + ("" if same else f"/{b[d]}!"))
        print(f"     {crop:12} {'  '.join(cells)}")
        if bad:
            FAILURES.append(f"harvest_by_day {crop}: {bad}/{len(days)} days differ")
    print()
    print("   Format is d<day>=<real> and, where they disagree, /<mirror>!")
    print("   The peak day matters more than the peak value: strawberry and carrot have")
    print("   ZERO slack (§2.7), so a one-day error there loses a unit per tile per cycle.")


def diff_peaks(truth, mirror):
    hr("5. PEAK YIELDS   unfertilised vs fertilised cap per crop")
    t, m = probe(truth, "peak_yields"), probe(mirror, "peak_yields")
    if not t or not m:
        print("   [SKIP] one side missing.")
        FAILURES.append("peak_yields: one side missing")
        return
    print(f"{'crop':12} {'real unf':>9} {'mir unf':>8} {'real fert':>10} {'mir fert':>9}")
    for crop in CROP_STAKES:
        a, b = t.get(crop) or {}, m.get(crop) or {}
        au = (a.get("unfert") or {}).get("peak_units")
        bu = (b.get("unfert") or {}).get("peak_units")
        af = (a.get("fert") or {}).get("peak_units")
        bf = (b.get("fert") or {}).get("peak_units")
        mark = "" if (au == bu and af == bf) else "   <-- DIFFER"
        print(f"{crop:12} {au!s:>9} {bu!s:>8} {af!s:>10} {bf!s:>9}{mark}")
        if au != bu:
            FAILURES.append(f"peak_yields {crop} unfert: real {au}, mirror {bu}")
        if af != bf:
            FAILURES.append(f"peak_yields {crop} fert: real {af}, mirror {bf}")
    print()
    print("   Melon unfertilised is §5.2 item 3 — the mirror says 4 against a documented")
    print("   cap of 6, and 4 vs 6 is ±50% on the melon programme.")


def _market_rows(trace):
    """Normalise an idle_market_trace probe into [(step, {good: (inv, price)})].

    The two sides record the same thing under different shapes: the mirror always writes
    `market: {inventory: {...}, prices: {...}}`, while dump_truth.py copies whichever of
    several candidate keys the real obs happens to expose, because we do not know the real
    engine's field names in advance. Normalising here keeps that uncertainty out of the
    comparison logic below.
    """
    out = []
    for row in (trace or {}).get("rows", []):
        step = row.get("step")
        blob = None
        for key in ("market", "market_inventory", "inventories", "town", "shops"):
            if isinstance(row.get(key), dict):
                blob = row[key]
                break
        if blob is None:
            continue
        inv = blob.get("inventory") if isinstance(blob.get("inventory"), dict) else blob
        prices = blob.get("prices") if isinstance(blob.get("prices"), dict) else {}
        if not isinstance(inv, dict):
            continue
        cells = {}
        for g, _ in GOOD_STAKES:
            v = inv.get(g)
            if isinstance(v, (int, float)):
                cells[g] = (float(v), prices.get(g))
        if cells:
            out.append((step, cells))
    return out


def diff_idle_market(truth, mirror):
    hr("6. IDLE MARKET DRIFT   both agents passing: does the town drain inventory?")
    t, m = probe(truth, "idle_market_trace"), probe(mirror, "idle_market_trace")
    tr, mr = _market_rows(t), _market_rows(m)
    if not tr:
        keys = sorted({k for row in (t or {}).get("rows", []) for k in row})
        print("   [SKIP] real engine exposed no readable market inventory.")
        print(f"          keys seen on the real obs rows: {keys or '(no rows)'}")
        print("          Read calibration/real_engine/ instead — the obs builder there")
        print("          names the field, which settles this by reading not guessing.")
        FAILURES.append("idle_market_trace: no readable real-engine market data")
        return
    if not mr:
        FAILURES.append("idle_market_trace: no mirror data")
        return

    print("   Nobody sells anything for the whole episode. PLAN.md §2.1 predicts inventory")
    print("   slopes DOWN anyway (the town's shops keep buying), so price sits above base")
    print("   all season and selling late beats selling early. Flat inventory falsifies it.")
    print()
    print(f"{'good':12} {'real d0':>8} {'real end':>9} {'real/day':>9} "
          f"{'mir/day':>9} {'real dir':>9} {'mir dir':>8}  verdict")

    for good, _stake in GOOD_STAKES:
        ta = [(s, c[good][0]) for s, c in tr if good in c]
        mb = [(s, c[good][0]) for s, c in mr if good in c]
        if len(ta) < 2:
            print(f"{good:12} {'-':>8}  real side has no samples")
            FAILURES.append(f"idle_market {good}: no real samples")
            continue
        (s0, v0), (s1, v1) = ta[0], ta[-1]
        days = max(1e-9, (s1 - s0) / 24.0)
        t_rate = (v0 - v1) / days
        m_rate = None
        if len(mb) >= 2:
            (ms0, mv0), (ms1, mv1) = mb[0], mb[-1]
            m_rate = (mv0 - mv1) / max(1e-9, (ms1 - ms0) / 24.0)

        t_dir = "PUMP" if v1 < v0 - 0.5 else ("flat" if abs(v1 - v0) <= 0.5 else "sink")
        m_dir = "-"
        if m_rate is not None:
            m_dir = "PUMP" if m_rate > 0.5 else ("flat" if abs(m_rate) <= 0.5 else "sink")

        if t_dir != m_dir:
            verdict = "DIRECTION DIFFERS"
            FAILURES.append(f"idle_market {good}: real drifts {t_dir}, mirror {m_dir}")
        elif m_rate is not None and abs(t_rate - m_rate) > max(0.5, 0.10 * abs(t_rate)):
            verdict = f"rate off {abs(t_rate - m_rate) / max(1.0, abs(t_rate)):.0%}"
            FAILURES.append(f"idle_market {good}: drain {t_rate:.1f}/day real "
                            f"vs {m_rate:.1f}/day mirror")
        else:
            verdict = "match"
        print(f"{good:12} {v0:>8.0f} {v1:>9.0f} {t_rate:>9.1f} "
              f"{('-' if m_rate is None else f'{m_rate:.1f}'):>9} "
              f"{t_dir:>9} {m_dir:>8}  {verdict}")

    print()
    print("   The drain RATE is what §2.8 spends: it caps how many units of each good the")
    print("   town will absorb near base price over 30 days, and that cap — not our tile")
    print("   count — is what makes wheat a $57k line and melon a 1-unit-a-day trickle.")
    print("   A kink in the slope every few days is the shop unlock cadence (§5.2 item 5);")
    print("   below is the per-good slope measured between consecutive real samples.")
    _print_kinks(tr)


def _print_kinks(rows, goods=("WHEAT", "STRAWBERRY", "MELON"), max_days=30):
    """Day-over-day drain for a few goods, to read the shop unlock cadence off the trace.

    Only hour-0 samples are used. The probe records both hour 0 and hour 23, so consecutive
    raw samples alternate between a 23-hour and a 1-hour gap; differencing those directly
    produces a meaningless zig-zag. One sample per day at the same hour makes each interval
    exactly one day, and then a step up in the slope IS a shop unlocking.
    """
    for good in goods:
        seq = [(s, c[good][0]) for s, c in rows if good in c and s % 24 == 0][:max_days]
        if len(seq) < 3:
            continue
        print()
        print(f"   {good} inventory lost per day, day 0 onward:")
        cells = [f"d{s0 // 24}:{v0 - v1:.0f}" for (s0, v0), (_, v1) in zip(seq, seq[1:])]
        for i in range(0, len(cells), 8):
            print("     " + "  ".join(cells[i:i + 8]))


def main():
    truth = load(TRUTH, "truth.json")
    mirror = load(MIRROR, "mirror.json")

    t_err, m_err = truth.get("errors") or {}, mirror.get("errors") or {}
    print("== mirror vs real engine ==")
    print(f"   truth.json  probes ok: {sorted((truth.get('probes') or {}))}")
    if t_err:
        print(f"               probes FAILED: {sorted(t_err)}")
    print(f"   mirror.json probes ok: {sorted((mirror.get('probes') or {}))}")
    if m_err:
        print(f"               probes FAILED: {sorted(m_err)}")

    diff_price_grid(truth, mirror)
    diff_constants(truth)
    diff_yields(truth, mirror)
    diff_rules(truth, mirror)
    diff_peaks(truth, mirror)
    diff_idle_market(truth, mirror)

    hr("VERDICT")
    if not FAILURES:
        print("   Mirror and real engine agree on every probe. Phase 0 exit met.")
        return 0
    print(f"   {len(FAILURES)} disagreement(s), in the order they should be fixed:")
    for i, f in enumerate(FAILURES, 1):
        print(f"     {i:>2}. {f}")
    print()
    print("   Fix these in kagfarm/constants.py, not in engine.py — the mirror imports")
    print("   from there, so one edit moves both. Then re-run mirror_truth.py and this")
    print("   script, and re-run analysis/portfolio.py, because the tile mix is downstream")
    print("   of every one of these numbers.")
    return 1


if __name__ == "__main__":
    sys.exit(main())




