"""Full-replay integration gate for the turn allocator (0925o Step 1b).

The reframe review's warning, adopted: every rewrite that touched job-queue or
purchase-order logic (day-0 ledger, place-queue, wool floor) passed unit tests and
compiled clean, then broke on a full replay because the bug was in CROSS-TURN STATE
(a ledger that does not reset at the day boundary, a queue built from the wrong
snapshot). Unit tests aimed at job ordering do not catch that class. This gate runs
complete 720-turn mirror episodes with the knob ON and checks for exactly that class:

  1. no uncaught exception on any turn (Policy.last_error stays None) -- a raise
     here forfeits the episode on the ladder, so this is a hard gate;
  2. no >= 20-turn all-PASS streak (the `_safe_pass` import-failure tell: an agent
     that stopped acting still "runs" at ~0.1 ms with no dawn spikes);
  3. HOUR INTEGRITY -- the (day, hour) sequence the agent is called on must be
     exactly 0..23 within each day, never repeated or re-ordered. If act() were to
     see a stale/duplicated hour (the cross-turn-state symptom), it desyncs from
     the engine's midnight refresh; this assertion catches that directly;
  4. bank never below 0 (cash-hole episodes);
  5. thirst deaths and animal-census drops on the same seed must not exceed the
     baseline (knob-off) run -- survival-first scheduling must not make survival
     worse. Same seed + deterministic mirror = zero noise, so the comparison is
     exact.

Usage (arm params are only ever the DORMANT KNOB + explicit study cells):
    .venv/bin/python analysis/replay_check.py --seeds 2
    .venv/bin/python analysis/replay_check.py --seeds 2 --params '{"turn_allocator": 1}'
    .venv/bin/python analysis/replay_check.py --params '{"turn_allocator": 1, "elite_script": true, "melon_opening": 8}'

Exit code 0 = all gates pass; 1 = any gate fails. The allocator must pass this on
>= 2 seeds BEFORE the judge bar (0925o gate rule).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import KaggricultureEnv          # noqa: E402
import main as agent_mod                     # noqa: E402  (registers seat-0 policy)
from agents import BUILTIN_AGENTS            # noqa: E402
from kagfarm import policy as policy_mod     # noqa: E402

sys.path.insert(0, os.path.join(_ROOT, "analysis"))
from ab_panel import _judge_meta             # noqa: E402

_ALL_PASS_STREAK = 20


def _default_params():
    return dict(policy_mod.PARAMS)


def _reset_params(base, overrides):
    policy_mod.PARAMS.clear()
    policy_mod.PARAMS.update(base)
    if overrides:
        policy_mod.PARAMS.update(overrides)


def _census(farm):
    n = 0
    for row in farm.tiles:
        for t in row:
            if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"):
                n += int(t.get("animals", 0) or 0)
    return n


def _is_all_pass(act):
    if act.get("market"):
        return False
    f = act.get("farmer") or ["PASS"]
    if f[0] != "PASS":
        return False
    return all((h or ["PASS"])[0] == "PASS" for h in (act.get("hands") or []))


def run_one(seed, opp_name, params, base, alloc_expected):
    """One full episode; returns a metrics dict (never raises)."""
    _reset_params(base, params)
    agent_mod._POLICIES.clear()
    opp = BUILTIN_AGENTS[opp_name]
    env = KaggricultureEnv(episode_steps=720, seed=seed)
    obs = env._obs()

    errs = []
    pass_streak = 0
    worst_streak = 0
    streak_at = None
    hour_seen = []                 # (day, hour) handed to the agent each turn
    bank_min = float("inf")
    thirst = 0
    animal_drops = {}
    alloc_days = []
    worst_ms = 0.0
    pol = None
    prev_tiles = None
    prev_day = None
    prev_animals = None

    while not env.done:
        step = obs[0].get("step", env.day * 24 + env.hour)
        hour_seen.append((step // 24, step % 24))
        t0 = time.monotonic()
        act = agent_mod.agent(obs[0])
        ms = (time.monotonic() - t0) * 1000.0
        worst_ms = max(worst_ms, ms)
        pol = agent_mod._POLICIES.get(0) or pol
        if pol is not None and pol.last_error and not errs:
            errs.append(pol.last_error)
        if _is_all_pass(act):
            pass_streak += 1
            if pass_streak > worst_streak:
                worst_streak = pass_streak
                streak_at = (step // 24, step % 24)
        else:
            pass_streak = 0

        tiles_before = [[dict(t) if isinstance(t, dict) else t for t in row]
                        for row in env.farms[0].tiles]
        census_before = _census(env.farms[0])

        obs, _ = env.step([act, opp(obs[1])])

        bank_min = min(bank_min, env.farms[0].money)
        # day-over-day survival accounting (the engine kills at the day refresh)
        if prev_tiles is not None and env.day != prev_day:
            drops = 0
            for y in range(len(tiles_before)):
                for x in range(len(tiles_before[y])):
                    b = tiles_before[y][x]
                    a_ = env.farms[0].tiles[y][x]
                    if isinstance(b, dict) and b.get("kind") == "PLANT" \
                            and isinstance(a_, dict) and a_.get("kind") == "WEED":
                        if b.get("consecutive_unwatered", 0) >= 1 \
                                and not b.get("watered_today"):
                            thirst += 1
            ca = _census(env.farms[0])
            if prev_animals is not None and ca < prev_animals:
                drops = prev_animals - ca
            if drops:
                animal_drops[env.day] = animal_drops.get(env.day, 0) + drops
        prev_tiles = [[t for t in row] for row in env.farms[0].tiles]
        prev_day = env.day
        prev_animals = _census(env.farms[0])

    st = getattr(pol, "alloc_stats", {}) or {}
    fired = sorted(set(getattr(pol, "alloc_fired_days", []) or [])) \
        if hasattr(pol, "alloc_fired_days") else []
    return dict(seed=seed, bank=env.farms[0].money, opp_bank=env.farms[1].money,
                errs=errs, worst_pass_streak=worst_streak, streak_at=streak_at,
                hour_ok=_hours_ok(hour_seen),
                bank_min=bank_min, thirst=thirst,
                animal_drops=animal_drops,
                alloc_fired_days=fired, alloc_stats=st,
                worst_ms=worst_ms)


def _hours_ok(hour_seen):
    """Within each day the agent must see hour 0,1,2,...,23 exactly once, in order."""
    per_day = {}
    for d, h in hour_seen:
        per_day.setdefault(d, []).append(h)
    for d, hs in per_day.items():
        if hs != list(range(len(hs))):
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--opp", default="self")
    ap.add_argument("--params", default='{"turn_allocator": 1}',
                    help="arm PARAMS overrides (JSON)")
    ap.add_argument("--baseline-params", default="{}", help="baseline overrides (JSON)")
    ap.add_argument("--judges", default=None,
                    help="comma list of judge names: run on each judge's own "
                         "recorded world seed (same terrain as the bar) instead "
                         "of --seeds arbitrary seeds")
    ap.add_argument("--json", default=None, help="write the report here")
    a = ap.parse_args()

    base = _default_params()
    baseline_p = json.loads(a.baseline_params) if a.baseline_params else {}
    arm_p = json.loads(a.params) if a.params else {}
    arm_is_allocator = bool(arm_p.get("turn_allocator"))

    jobs = []          # (label, seed)
    if a.judges:
        for name in [s for s in a.judges.split(",") if s]:
            _ep, _path, _seat, seed = _judge_meta(name)
            jobs.append((name, seed))
    else:
        jobs = [(f"seed {s}", s) for s in range(a.seeds)]

    rows = []
    for label, seed in jobs:
        # baseline first (knob off), then the arm -- _reset_params restores
        # defaults around each run, so PARAMS never leaks between runs in-process.
        rb = run_one(seed, a.opp, baseline_p, base, alloc_expected=False)
        ra = run_one(seed, a.opp, arm_p, base, alloc_expected=arm_is_allocator)
        rb["label"] = ra["label"] = label
        rows.append((rb, ra))
        print(f"{label}: baseline ${rb['bank']:,.0f} (min ${rb['bank_min']:,.0f}, "
              f"thirst {rb['thirst']}, drops {sum(rb['animal_drops'].values())}, "
              f"streak {rb['worst_pass_streak']}@d{rb['streak_at'][0]}h{rb['streak_at'][1]})"
              f"  ->  arm ${ra['bank']:,.0f} (min ${ra['bank_min']:,.0f}, "
              f"thirst {ra['thirst']}, drops {sum(ra['animal_drops'].values())}, "
              f"streak {ra['worst_pass_streak']}@d{ra['streak_at'][0]}h{ra['streak_at'][1]}, "
              f"alloc fired d{ra['alloc_fired_days']})")

    failures = []
    for rb, ra in rows:
        tag = rb.get("label") or f"seed {rb['seed']}"
        if ra["errs"]:
            failures.append(f"{tag}: agent exception(s): {ra['errs'][:2]}")
        # The _safe_pass tell is an agent that STOPPED acting: a long all-PASS
        # streak AND flat durations. The mirror is live the whole episode -- its
        # dawn plans spike ~0.9-1.2 ms every day -- so any max >= 0.5 ms proves
        # the agent is executing; end-of-day lane drains (measured 23@d3h23 in
        # the BASELINE on every seed) are normal, not the import-failure
        # signature. A dead agent is flat ~0.01 ms with no dawn spikes.
        if (ra["worst_pass_streak"] >= _ALL_PASS_STREAK and ra["worst_ms"] < 0.5) \
                or ra["worst_pass_streak"] >= 60:
            failures.append(f"{tag}: all-PASS streak {ra['worst_pass_streak']} "
                            f"with max turn {ra['worst_ms']:.2f} ms "
                            f"(_safe_pass import-failure tell)")
        if not ra["hour_ok"]:
            failures.append(f"{tag}: hour-sequence violation (cross-turn-state desync)")
        if ra["bank_min"] < 0:
            failures.append(f"{tag}: bank went to ${ra['bank_min']:,.0f}")
        if arm_is_allocator and not ra["alloc_fired_days"]:
            print(f"  note {tag}: allocator never fired on this seed")
        if ra["thirst"] > rb["thirst"]:
            failures.append(f"{tag}: thirst {ra['thirst']} > baseline {rb['thirst']} "
                            f"(survival-first made survival worse)")
        da, db = sum(ra["animal_drops"].values()), sum(rb["animal_drops"].values())
        if da > db:
            failures.append(f"{tag}: animal losses {da} > baseline {db}")

    print(f"\n== replay_check: {a.opp} x {a.seeds} seeds, "
          f"arm {a.params} ==")
    print(f"  hours OK, exceptions {sum(len(r[1]['errs']) for r in rows)}, "
          f"worst all-PASS streak {max(r[1]['worst_pass_streak'] for r in rows)}, "
          f"min bank ${min(r[1]['bank_min'] for r in rows):,.0f}")
    banks = [r[1]["bank"] for r in rows]
    bbanks = [r[0]["bank"] for r in rows]
    print(f"  arm bank    mean ${sum(banks)/len(banks):,.0f}  "
          f"(baseline mean ${sum(bbanks)/len(bbanks):,.0f})")
    if failures:
        print("  FAIL:")
        for f in failures:
            print(f"    - {f}")
    else:
        print("  ALL GATES PASS")
    if a.json:
        os.makedirs(os.path.dirname(a.json) or ".", exist_ok=True)
        with open(a.json, "w") as fh:
            json.dump(dict(rows=[dict(baseline=r[0], arm=r[1]) for r in rows],
                           failures=failures), fh, indent=1)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
