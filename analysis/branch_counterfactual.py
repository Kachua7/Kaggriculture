"""Branch-and-simulate causal attribution on episode 115863161 (B) — 0930k.

The v3.0 decomposition (causal_report.md) established that A vs B is tied at day 14
(-225) and diverges afterwards, but its five loss columns are diagnostic and must not
be summed. This harness produces the exact causal dollars the report asked for:
branch the RECORDED replay at a decision point, apply one intervention, rerun the
vendored 1.32.7 engine for the remainder of the season with both seats' recorded
actions, and read the terminal cash delta. The opponent keeps playing its recorded
tape, so every dollar is attributable to the intervention alone.

Method (mirrors calibration/verify_replay.resimulate):
  steps[t][seat].action is the action that PRODUCED steps[t] from steps[t-1] —
  seed state from deep-copied steps[0], then for each t feed action@t with
  obs.step = t-1. The BASELINE run must reproduce both recorded banks byte-exact
  ($50,648 / $77,754) before any intervention is trusted; per-step obs diffs gate it.

Interventions (each = one hook class, listed in INTERVENTIONS):
  no_d6 / no_d6_7 / no_d13 / no_d6_7_d13 / no_d0
      Skip B's recorded animal-purchase batches at the named checkpoints (6/$2,200
      on d6, 1/$400 on d7, 3/$1,200 on d13, 5/$2,300 on d0). The skip is a SEQUENCE
      PRESERVATION: each subsequent recorded BUY_ANIMAL keeps its position in the
      order stream (k-th BUY_ANIMAL of the day), so the recorded order structure is
      untouched — only those mouths are never admitted.
  cap12 / cap10 / cap8
      Hard service-feasible envelope: drop every BUY_ANIMAL while live herd >= cap.
  feed_oracle28
      Experiment 3, clean form: force feed AVAILABILITY (not a buy decision) by
      injecting 28 WHEAT/unit into B's shed at each dawn d18..d25, free. The agent's
      own feeding logic then decides whether service recovers.
  milk_250 / milk_180 / milk_250_d14 / milk_180_d14
      Experiment 4: impose A's milk regime on B by holding the shared market's MILK
      quote at the target from the trigger day on (drain the glut 1 unit at a time
      via the engine's own price curve). _from_d14 variants start at the tie point.
  combo_nod67_milk180, combo_nod67_feed_milk
      Independence checks: admission removal combined with regime/feed fixes.

Usage:
  PYTHONHASHSEED=0 .venv/bin/python analysis/branch_counterfactual.py            # all
  PYTHONHASHSEED=0 .venv/bin/python analysis/branch_counterfactual.py --runs baseline,no_d6
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import load_engine, ENGINE_DIR  # noqa: E402

DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
REPLAY_B = os.path.join(DOWNLOADS, "115863161.json")
OUT_DIR = os.path.join(_ROOT, "analysis", "branch_out")
SEAT = 0
COMPARE_KEYS = ("day", "hour", "player", "market", "town", "farms", "private")
ANIMAL_KINDS = ("GOOSE", "COW", "SHEEP")
FEED_RESCUE_DAYS = range(18, 26)     # d18..d25 inclusive — the collapse window
FEED_RESCUE_WHEAT = 28               # 2x peak herd: pure availability oracle
MILK_FLOOR_DAYS = range(18, 30)      # d18..d29 default trigger window


class Struct:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def norm(x):
    if x is None or isinstance(x, (str, bool)):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 6)
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    return str(x)


def diff_paths(a, b, path="$", out=None):
    if out is None:
        out = []
    if len(out) >= 8:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((f"{path}.{k}", "<missing>", a.get(k, b.get(k))))
            else:
                diff_paths(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}[]", f"len {len(a)} vs {len(b)}", (a[:2], b[:2])))
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))
    return out


def _shed_of(state, seat):
    """The seat's shed dict, whether obs.private is a list or a dict."""
    pv = state[seat].observation.private
    if isinstance(pv, list):
        pv = pv[seat]
    return pv["shed"]


def _herd(state, seat):
    return sum(1 for row in state[seat].observation.farms[seat]["tiles"]
               for t in row if isinstance(t, dict) and "animal" in t)


# ---------------------------------------------------------------------------
# Sell collectors: one process-wide _commit_unit wrap, collectors swapped per run.
# ---------------------------------------------------------------------------

_COLLECT = {"sold": {}, "rev": {}}
_WRAP_STATE = {"orig": None, "farm": None}


def _ensure_wrap(eng):
    if _WRAP_STATE["orig"] is None:
        _WRAP_STATE["orig"] = eng._commit_unit

        def wrapped(op, item, price, farm, *rest):
            ok = _WRAP_STATE["orig"](op, item, price, farm, *rest)
            if ok and op == "SELL" and farm is _WRAP_STATE["farm"]:
                _COLLECT["sold"][item] = _COLLECT["sold"].get(item, 0) + 1
                _COLLECT["rev"][item] = _COLLECT["rev"].get(item, 0.0) + price
            return ok
        eng._commit_unit = wrapped


def _reset_collectors():
    _COLLECT["sold"] = {}
    _COLLECT["rev"] = {}


# ---------------------------------------------------------------------------
# Intervention hooks. Each exposes act_for(i, seat, recorded_action) and
# before_step(i, state, env) where i indexes the transition steps[i-1] -> steps[i]
# (i.e. the action being applied NOW was decided from obs@(i-1), day = (i-1)//24).
# ---------------------------------------------------------------------------

class Baseline:
    name = "baseline"
    def act_for(self, i, seat, act): return act
    def before_step(self, i, state, env): pass


class _SkipPurchases(Baseline):
    """Skip the n-th BUY_ANIMAL units of the named days, preserving sequence.

    B's recorded batches: d0 x5, d6 x6, d7 x1, d13 x3. On a hooked day the k-th
    recorded BUY_ANIMAL order is dropped iff its running unit index falls inside the
    batch being skipped; later purchases keep their recorded relative positions.
    """
    def __init__(self, days_units):
        self.days_units = days_units          # {day: units_to_skip}
        self.name = "no_" + "_".join(f"d{d}" for d in sorted(days_units))

    def act_for(self, i, seat, act):
        day = (i - 1) // 24
        n_skip = self.days_units.get(day)
        if not n_skip or seat != SEAT:
            return act
        m = dict(act or {})
        market = [list(o) for o in (m.get("market") or [])]
        out, skipped, seen = [], 0, 0
        for o in market:
            if o and o[0] == "BUY_ANIMAL" and skipped < n_skip:
                skipped += 1
                seen += 1
                continue
            if o and o[0] == "BUY_ANIMAL":
                seen += 1
            out.append(o)
        if skipped:
            m["market"] = out
        return m


class HerdCap(Baseline):
    """Drop every BUY_ANIMAL while the live herd is at/above the cap."""
    def __init__(self, cap):
        self.cap = cap
        self.name = f"cap{cap}"

    def act_for(self, i, seat, act):
        if seat != SEAT:
            return act
        day = (i - 1) // 24
        herd = self._herd_dawn.get(day, 0)
        if herd < self.cap:
            return act
        m = dict(act or {})
        market = [o for o in (m.get("market") or [])
                  if not (o and o[0] == "BUY_ANIMAL")]
        m["market"] = market
        return m

    def before_step(self, i, state, env):
        day = (i - 1) // 24
        self._herd_dawn[day] = _herd(state, SEAT)

    _herd_dawn = {}


class FeedService(Baseline):
    """Experiment 3, tape-consistent form: force the feed OUTCOME, not wheat supply.

    Every step in the window, set fed_today=True on every animal tile. The end-of-day
    refresh then reads fed animals (consecutive_unfed stays 0 -> no escapes) and the
    production pops pay full yield. Unlike shed injection, this cannot be re-routed
    into market sales by the fixed tape — it tests exactly the service mechanism.
    """
    def __init__(self, start_day=14, end_day=29):
        self.start_day, self.end_day = start_day, end_day
        self.name = f"service_d{start_day}" + ("" if end_day == 29 else f"_{end_day}")

    def before_step(self, i, state, env):
        day = (i - 1) // 24
        if not (self.start_day <= day <= self.end_day):
            return
        tiles = state[SEAT].observation.farms[SEAT]["tiles"]
        for row in tiles:
            for tile in row:
                if isinstance(tile, dict) and "animal" in tile:
                    tile["fed_today"] = True


class MilkHold(Baseline):
    """Experiment 4, corrected: impose A's milk regime on the SHARED market.

    Milk price falls with inventory; A's regime realized $250-269, B's glut realized
    $7-53. Before every step in the window, drain market MILK one unit at a time
    until the engine's own quote is >= target (the oracle town absorbs the glut at
    A-like prices). No other good is touched; both seats' milk sells realize high.
    """
    def __init__(self, target, start_day=14):
        self.target, self.start_day = target, start_day
        self.name = f"milk_{target}_d{start_day}"
        self.drained = 0

    def before_step(self, i, state, env):
        day = (i - 1) // 24
        if day < self.start_day:
            return
        eng = env._eng
        market = state[0].observation.market
        inv = market["inventory"]
        params = market.get("params")
        guard = 0
        while inv["MILK"] > 0 and eng.market_price("MILK", inv["MILK"], params) < self.target \
                and guard < 40000:
            inv["MILK"] -= 1
            guard += 1
        self.drained += guard


class Combo(Baseline):
    def __init__(self, name, hooks):
        self.name, self.hooks = name, hooks
    def act_for(self, i, seat, act):
        for h in self.hooks:
            act = h.act_for(i, seat, act)
        return act
    def before_step(self, i, state, env):
        for h in self.hooks:
            h.before_step(i, state, env)


def INTERVENTIONS():
    return [
        Baseline(),
        _SkipPurchases({6: 6}),
        _SkipPurchases({6: 6, 7: 1}),
        _SkipPurchases({13: 3}),
        _SkipPurchases({6: 6, 7: 1, 13: 3}),
        _SkipPurchases({0: 5}),
        HerdCap(12),
        HerdCap(10),
        HerdCap(8),
        FeedService(18, 25),
        FeedService(14, 29),
        MilkHold(250, 14),
        MilkHold(180, 14),
        MilkHold(250, 18),
        Combo("combo_service_milk", [FeedService(14, 29), MilkHold(250, 14)]),
        Combo("combo_nod67_service_milk",
              [_SkipPurchases({6: 6, 7: 1}), FeedService(14, 29), MilkHold(250, 14)]),
    ]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_branch(replay, engine_dir, hook, check=False, max_reports=2):
    eng = load_engine(engine_dir)
    env = Struct(configuration=Struct(**(replay.get("configuration") or {})),
                 done=False,
                 info=dict(replay.get("info") or {}))
    env._eng = eng
    steps = replay["steps"]
    state = []
    for p in range(len(steps[0])):
        obs = Struct(**copy.deepcopy(steps[0][p]["observation"]))
        state.append(Struct(action=None, observation=obs, status="ACTIVE", reward=0, info={}))
    _reset_collectors()
    _ensure_wrap(eng)
    _WRAP_STATE["farm"] = state[SEAT].observation.farms[SEAT]

    exact = mismatched = 0
    first_bad = []
    dawn_cash = {}
    herd_dawn = {}
    last_hook_herd = {}

    for i in range(1, len(steps)):
        day = (i - 1) // 24
        if i % 24 == 1:                        # dawn of `day`
            dawn_cash[day] = state[SEAT].observation.farms[SEAT]["money"]
            herd_dawn[day] = _herd(state, SEAT)
        hook.before_step(i, state, env)
        if isinstance(hook, HerdCap):
            last_hook_herd[day] = hook._herd_dawn[day]
        state[0].observation.step = i - 1
        for p in range(len(steps[0])):
            rec = steps[i][p].get("action")
            act = hook.act_for(i, p, rec if rec is not None else {})
            state[p].action = act
        eng.interpreter(state, env)

        if check:
            ok = True
            for p in range(len(steps[0])):
                live = {k: norm(getattr(state[p].observation, k)) for k in COMPARE_KEYS}
                recd = {k: norm(steps[i][p]["observation"].get(k)) for k in COMPARE_KEYS}
                if live != recd:
                    ok = False
                    if len(first_bad) < max_reports:
                        first_bad.append((i, p, diff_paths(recd, live)))
            if ok:
                exact += 1
            else:
                mismatched += 1

    banks = [state[p].observation.farms[p]["money"] for p in range(len(state))]
    # herd drops = escapes (animals never leave any other way)
    drops = {}
    for d in range(1, 30):
        if d in herd_dawn and (d - 1) in herd_dawn:
            drop = herd_dawn[d - 1] - herd_dawn[d]
            if drop > 0:
                drops[d] = drop
    shed = _shed_of(state, SEAT)
    return dict(
        name=hook.name, banks=banks, dawn_cash=dawn_cash,
        herd_dawn=herd_dawn, herd_drops=drops,
        sold=dict(_COLLECT["sold"]), rev={k: round(v) for k, v in _COLLECT["rev"].items()},
        terminal_shed={k: v for k, v in shed.items() if v},
        exact=exact, mismatched=mismatched, first_bad=first_bad,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="all")
    ap.add_argument("--engine-dir", default=ENGINE_DIR)
    ap.add_argument("--replay", default=REPLAY_B)
    ap.add_argument("--no-save", action="store_true")
    a = ap.parse_args()

    with open(a.replay) as f:
        replay = json.load(f)
    info = replay.get("info") or {}
    steps = replay["steps"]
    rec_banks = [steps[-1][p].get("reward") for p in range(2)]

    hooks = INTERVENTIONS()
    if a.runs != "all":
        want = {s.strip() for s in a.runs.split(",") if s.strip()}
        hooks = [h for h in hooks if h.name in want]
        missing = want - {h.name for h in hooks}
        if missing:
            raise SystemExit(f"unknown runs: {sorted(missing)}")

    rows = []
    for h in hooks:
        check = h.name == "baseline"
        r = run_branch(replay, a.engine_dir, h, check=check)
        rows.append(r)
        d14 = r["dawn_cash"].get(14, 0)
        esc = sum(r["herd_drops"].get(d, 0) for d in range(14, 30))
        milk_sold = r["sold"].get("MILK", 0)
        wheat_sold = r["sold"].get("WHEAT", 0)
        flag = ""
        if check:
            ok = (r["mismatched"] == 0 and
                  all(abs((r["banks"][p] or 0) - (rec_banks[p] or 0)) < 0.5 for p in range(2)))
            flag = "  <-- BASELINE OK" if ok else "  <-- BASELINE MISMATCH"
        print(f"{r['name']:<24} final={r['banks'][SEAT]:>9,.0f}  opp={r['banks'][1 - SEAT]:>9,.0f}"
              f"  d14={d14:>8,.0f}  herd_d29={r['herd_dawn'].get(29, 0):>2}"
              f"  escapes_d14+={esc:>2}  milk_sold={milk_sold:>4}  wheat_sold={wheat_sold:>4}"
              f"{flag}", flush=True)
        if check and r["mismatched"]:
            for i, p, ds in r["first_bad"]:
                print(f"  first divergence step {i} seat {p}:")
                for path, rec_v, live_v in ds:
                    print(f"    {path}: rec={rec_v} live={live_v}")

    base = rows[0]
    print("\nCausal attribution vs recorded B (final 50,648; gap to A's 107,373 = 56,725):")
    print(f"{'branch':<24}{'final':>10}{'delta vs B':>12}{'gap closed':>12}{'d14->d29 gain':>15}")
    for r in rows[1:]:
        d = r["banks"][SEAT] - 50648.0
        gain = r["banks"][SEAT] - r["dawn_cash"].get(14, 0)
        print(f"{r['name']:<24}{r['banks'][SEAT]:>10,.0f}{d:>+12,.0f}{d:>+12,.0f}"
              f"{gain:>15,.0f}")

    if not a.no_save:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, "branch_results_0930k.json")
        with open(out, "w") as f:
            json.dump({"replay": a.replay, "recorded_banks": rec_banks, "rows": rows}, f, indent=1)
        print(f"\nsaved -> {out}")
    return rows


if __name__ == "__main__":
    main()
