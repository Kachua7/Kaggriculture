"""Desync probe — WHY does the elite book halt in the 5 sig_miss worlds (0930d, phase 2)?

Runs the clone inside each donor world (same conventions as elite_counterfactual.py:
fresh obs every turn, opp actions aligned one-later) and records, at every dawn:

  live      — the v2 signature the live state produced;
  variants  — for EVERY stored variant that day: per-component delta vs the live sig
              (day, shops, money bucket, herd, wool, grain, fert) and whether
              _variant_sig_eq accepts it;
  served    — which variant index (and donor eid) served this dawn, and whether the
              identity continued from the previous dawn (the continuity table —
              identity thrash vs genuine state divergence).

Miss classification at each halt dawn:
  near      — some variant matches on all EXACT keys (day, shops, herd, wool) but a
              bucket (money/grain/fert) sits just outside tolerance → a threshold
              relaxation could have kept the clone alive;
  shops     — the shop set itself differs (a trade crossed the unlock draw's RNG
              boundary — different world branch, script is untrustworthy);
  herdwool  — an exact state key (herd/wool) drifted: real divergence, no stored
              script honestly matches;
  none      — no variant within one bucket on anything.

Usage:
  .venv/bin/python analysis/book_desync_probe.py                       # 5 desyncs
  .venv/bin/python analysis/book_desync_probe.py --eids 110886706,...  # custom
  .venv/bin/python analysis/book_desync_probe.py --max-day 16          # stop early
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import RealEnv, ENGINE_DIR          # noqa: E402
from kagfarm import policy as policy_mod                 # noqa: E402
from kagfarm.policy import Policy                        # noqa: E402

DESYNCS = ["110907373", "110926948", "111016701", "110954233", "110943566"]
CONTROLS = ["110886706", "110932461"]
SEATS = {"110907373": 1, "110938064": 1, "110943566": 1, "111016701": 1}
# sig index -> (name, exact?)
COMPONENTS = [(0, "day", True), (1, "shops", True), (2, "money", False),
              (3, "herd", True), (4, "wool", True), (5, "grain", False),
              (6, "fert", False)]


def _deltas(live, donor_sig):
    """Per-component delta strings: '0' for equal, '+n'/'-n' for the distance."""
    out = []
    for i, name, exact in COMPONENTS:
        lv, dv = live[i], (donor_sig[i] if i < len(donor_sig) else None)
        if i == 1:                           # shop sets: membership diff
            ls, ds = set(lv or []), set(dv or [])
            d = f"+{len(ls - ds)}-{len(ds - ls)}"
        else:
            try:
                diff = int(lv) - int(dv)
            except (TypeError, ValueError):
                d = "?"
            else:
                d = "0" if diff == 0 else f"{diff:+d}"
        out.append((name, d, exact))
    return out


def _classify(live, variants):
    """Classify a sig_miss using the stored variants of this day."""
    best = None
    for v in variants:
        sig = v.get("sig") or []
        comps = _deltas(live, sig)
        exact_bad = [name for name, d, exact in comps
                     if exact and d not in ("0", "+0-0")]
        bucket_off = {name: d for name, d, exact in comps
                      if not exact and d not in ("0",)}
        if not exact_bad:
            # all exact keys match, buckets outside tolerance -> near-miss
            return "near", dict(donor=v.get("donor"), buckets=bucket_off, comps=comps)
        score = len(exact_bad)
        if best is None or score < best[0]:
            best = (score, dict(donor=v.get("donor"), exact_bad=exact_bad,
                                buckets=bucket_off, comps=comps))
    if best is None:
        return "none", {}
    if "shops" in best[1]["exact_bad"]:
        return "shops", best[1]
    return "herdwool", best[1]


def run(eid, max_day=30):
    path = os.path.join(_ROOT, "analysis", "replays", f"{eid}.json")
    d = json.load(open(path))
    steps = d["steps"]
    seed = int((d.get("info") or {}).get("seed") or 0)
    seat = SEATS.get(eid, 0)
    opp_seat = 1 - seat
    opp_actions = [steps[i][opp_seat].get("action") or {} for i in range(len(steps))]

    env = RealEnv(seed, ENGINE_DIR)
    pol = Policy(params={"elite_book": 1})
    # The book as the policy sees it (loaded directly: pol._book is a sentinel until
    # the first act() runs, and the variant tables must be available at d0).
    book = policy_mod._load_opening_book(policy_mod._elite_book_path_default()) or {}

    dawns = []                            # per-dawn telemetry dicts
    t = 0
    while not env.done:
        obs = env._obs_view(seat)
        day = int(obs.get("day", t // 24))
        a = pol.act(obs, env.config)      # the dawn decision happens INSIDE act
        if t % 24 == 0 and day <= max_day:
            live = policy_mod.opening_book_signature(obs)
            variants = book.get(day) or []
            rec = dict(day=day, live=list(live),
                       served=None, served_donor=None, cont=None,
                       variants=[dict(donor=v.get("donor"), sig=v.get("sig"),
                                      eq=bool(policy_mod._variant_sig_eq(live, v.get("sig") or [])))
                                for v in variants])
            if day in pol._book_decided:
                idx = pol._book_variant.get(day)
                rec["served"] = idx
                rec["served_donor"] = (variants[idx].get("donor")
                                       if idx is not None and idx < len(variants) else None)
                prev = dawns[-1] if dawns else None
                rec["cont"] = (prev["served_donor"] == rec["served_donor"]
                               if prev and prev.get("served_donor") else None)
            elif day in pol._book_halt_days:
                if not variants:
                    rec["miss"] = ("short", {})
                elif any(r["eq"] for r in rec["variants"]):
                    rec["miss"] = ("invalid", {})
                else:
                    rec["miss"] = _classify(live, variants)
            dawns.append(rec)
        oa = opp_actions[t + 1] if t + 1 < len(opp_actions) else {}
        oa = {k: (list(v) if k == "farmer" and v else v) for k, v in oa.items()}
        acts = [None, None]
        acts[seat] = a
        acts[opp_seat] = oa
        env.step(acts)
        t += 1
        if day > max_day:
            break

    return dict(eid=eid, seed=seed, seat=seat, final=env.banks()[seat],
                donor_bank=steps[-1][seat].get("reward"), dawns=dawns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eids", default=",".join(DESYNCS + CONTROLS))
    ap.add_argument("--max-day", type=int, default=30)
    ap.add_argument("--full", action="store_true",
                    help="print every dawn's variant table (default: served days compact + misses full)")
    a = ap.parse_args()

    for eid in [e for e in a.eids.split(",") if e]:
        r = run(eid, a.max_day)
        print(f"\n=== {eid} (seed {r['seed']}, seat {r['seat']}) "
              f"clone ${r['final']:,.0f} vs donor ${r['donor_bank'] or 0:,.0f} ===")
        for rec in r["dawns"]:
            tag = ""
            if rec.get("served_donor"):
                tag = f"served #{rec['served']} {rec['served_donor']}" + \
                      ("" if rec["cont"] else "  << identity switched")
            if "miss" in rec:
                why, info = rec["miss"]
                tag = f"MISS {why} {info}"
            if a.full or "miss" in rec or not rec.get("served_donor") or not rec["cont"]:
                print(f"  d{rec['day']:>2} live={rec['live']}")
                if a.full:
                    for v in rec["variants"]:
                        comps = ", ".join(f"{n}:{d}" for n, d, _ in _deltas(rec["live"], v["sig"]))
                        print(f"        vs {v['donor']} eq={v['eq']}  [{comps}]")
                if tag:
                    print(f"        -> {tag}")


if __name__ == "__main__":
    main()
