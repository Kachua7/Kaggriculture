"""Replay-opponent panel: calibration gate + paired A/B driver (REAL TIER).

Calibration (frozen plan Part B.3): before a replay judge is trusted, measure how
faithfully its recorded actions reproduce the recorded economy. The instrument is
verify_replay.py's method: feed BOTH seats' recorded actions verbatim through the
VENDORED engine (calibration/engine, 1.32.7) — counterplay-free by construction —
and compare the judge seat's executed sales flow and final bank against the
recording. Per good p:

    R_p = resimulated executed sales_p / recorded executed sales_p
    cash_ratio = resimulated final bank / recorded final bank

The mirror CANNOT serve as this instrument: recorded episodes ran on the real engine,
so a mirror resimulation diverges for reasons that have nothing to do with the judge
(shop RNG, price curves, timing). Verified the hard way in this session: mirror
calibration flagged every judge LOW-CONFIDENCE while the same tapes self-sustain on
the real engine.

Executed (settled) sales are counted exactly by wrapping the engine's `_commit_unit`
and matching the committing farm to a seat by object identity within each
interpreter() call. Recorded-side flow comes from the replay's end-of-day shed
deltas (analysis.profile_replay.executed_flow — the only per-good executed signal in
the replay JSON; it undercounts same-day harvest+sell, so R_p > 1 reads as "broadly
right" and R_p < 0.5 as missing pressure).

Gate: cash_ratio >= 0.60 AND <= 2 premium goods with R_p < 0.5 -> OK, else the judge
is reported LOW-CONFIDENCE (it still runs; results carry the flag).

A/B: paired episodes of the live agent vs each replay judge via
bridge.real_env.run_one_real (real tier, sequential — the vendored module is
process-global state). No working-capital subsidy: on the real tier a verbatim judge
self-sustains on its recorded income (private board), which the mirror could not.

Run with .venv/bin/python (the vendored engine imports kaggle_environments.utils).

Usage:
    .venv/bin/python analysis/ab_panel.py --calibrate
    .venv/bin/python analysis/ab_panel.py --seeds 4
    .venv/bin/python analysis/ab_panel.py --seeds 4 --params '{"n_animals": 0}'
"""
import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.profile_replay import profile, executed_flow  # noqa: E402
from replay_opp import MANIFEST_IDS, SPECTATOR_IDS, _find_replay, _replay_seed  # noqa: E402

LIVESTOCK_LED = ("replay_aditya", "replay_sathish", "replay_madhur")
ALL_PANEL = ("replay_air", "replay_aditya", "replay_sathish",
             "replay_kovkin", "replay_madhur", "replay_majkel", "replay_thirdfarm")


def _judge_meta(name):
    """(ep_id, path, judge_seat|None, seed) for both manifest kinds.

    judge_seat None = our-game auto-resolution (bank-first vs our recorded bank).
    Spectator judges carry an EXPLICIT seat from SPECTATOR_IDS -- never auto-resolve
    those: the d0-melon heuristic keys on OUR cohort and would misresolve an elite
    seat (Majkel d0: 6 melon)."""
    for e, (l, _m, _s) in MANIFEST_IDS.items():
        if f"replay_{l}" == name:
            return e, _find_replay(e), None, _s
    for e, seats in SPECTATOR_IDS.items():
        short = name[7:] if name.startswith("replay_") else None
        if short in seats:
            path = _find_replay(e)
            return e, path, seats[short], _replay_seed(path)
    raise KeyError(name)

PREMIUM = ("MELON", "STRAWBERRY", "MILK", "WOOL", "TOMATO")
ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "calibration", "engine")


def _run_one_cal(name, max_reports=0):
    """Resimulate the recorded episode both-seats-verbatim on the vendored engine,
    counting the judge seat's settled sells. Returns dict(flow, bank, exact,
    mismatched, flow_ours)."""
    from calibration.verify_replay import load_engine_module, Struct, norm, COMPARE_KEYS

    ep_id, path, judge_seat, rec_seed = _judge_meta(name)
    replay = json.load(open(path))
    steps = replay["steps"]

    # Seat attribution: explicit for spectator judges; bank-first otherwise (names
    # are unreliable on our batch).
    prof = profile(path)
    opp_seat = our_seat = None
    if judge_seat is not None:
        opp_seat = judge_seat
        our_seat = 1 - judge_seat
    else:
        _, our_money, _ = MANIFEST_IDS[ep_id]
        for p, pr in prof.items():
            fm = pr["final_money"]
            if fm is not None and abs(fm - our_money) <= 2.0:
                our_seat = p
            else:
                opp_seat = p

    eng = load_engine_module(ENGINE_DIR)
    flow = {0: {}, 1: {}}
    orig_commit = eng._commit_unit

    # The wrapper needs the committing seat. The engine calls _commit_unit from inside
    # _process_market with (op, item, price, farms[pid], privates[pid], market, cap);
    # pid is not passed. Resolve by identity against the live state each call via a
    # per-call box: we set the box before invoking interpreter() and map farm objects
    # at that moment (observation objects persist across steps within a session).
    def make_wrapper():
        state_ref = {}

        def wrapper(op, item, price, farm, private, market, shed_capacity=100):
            if op == "SELL" and private.get("shed", {}).get(item, 0) > 0:
                st = state_ref.get("state")
                if st is not None:
                    for pi in (0, 1):
                        if farm is st[pi].observation.farms[pi]:
                            flow[pi][item] = flow[pi].get(item, 0) + 1
                            break
            return orig_commit(op, item, price, farm, private, market, shed_capacity)

        return wrapper, state_ref

    wrapper, state_ref = make_wrapper()
    eng._commit_unit = wrapper

    try:
        env = Struct(configuration=Struct(**replay["configuration"]),
                     done=False,
                     info=dict(replay.get("info") or {}))
        state = []
        for p in range(2):
            obs = Struct(**copy.deepcopy(steps[0][p]["observation"]))
            state.append(Struct(action=None, observation=obs, status="ACTIVE",
                                reward=0, info={}))
        state_ref["state"] = state

        exact = mismatched = 0
        for t in range(1, len(steps)):
            state[0].observation.step = t - 1
            for p in range(2):
                act = steps[t][p].get("action")
                state[p].action = act if act is not None else {}
            eng.interpreter(state, env)
            ok = True
            for p in range(2):
                live = {k: norm(getattr(state[p].observation, k)) for k in COMPARE_KEYS}
                rec = {k: norm(steps[t][p]["observation"].get(k)) for k in COMPARE_KEYS}
                if live != rec:
                    ok = False
            if ok:
                exact += 1
            else:
                mismatched += 1
        banks = [state[p].observation.farms[p]["money"] for p in range(2)]
    finally:
        eng._commit_unit = orig_commit

    return dict(flow=flow[opp_seat], flow_ours=flow[our_seat],
                bank=banks[opp_seat], bank_ours=banks[our_seat],
                exact=exact, mismatched=mismatched,
                rec_flow=executed_flow(prof[opp_seat]),
                rec_bank=prof[opp_seat]["final_money"])


def calibrate(names):
    """Print the fidelity card per judge. Returns {name: verdict dict}."""
    out = {}
    for name in names:
        r = _run_one_cal(name)
        rps = {}
        for g in set(r["rec_flow"]) | set(r["flow"]):
            rec = r["rec_flow"].get(g, 0)
            sim = r["flow"].get(g, 0)
            rps[g] = (sim / rec) if rec else (1.0 if sim == 0 else 9.99)
        flagged = [g for g in PREMIUM if rps.get(g, 0) < 0.5 and r["rec_flow"].get(g, 0) > 0]
        cash_ratio = (r["bank"] / r["rec_bank"]) if r["rec_bank"] else 0.0
        ok = cash_ratio >= 0.60 and len(flagged) <= 2
        out[name] = dict(rp=rps, cash_ratio=cash_ratio, flagged=flagged, ok=ok,
                         exact=r["exact"], mismatched=r["mismatched"])
        flag_s = ",".join(f"{g}:{rps[g]:.2f}" for g in flagged) or "none"
        print(f"{name:16s} cash_ratio {cash_ratio:5.2f} (resim ${r['bank']:,.0f} vs "
              f"rec ${r['rec_bank']:,.0f})  steps exact/mismatch {r['exact']}/{r['mismatched']}")
        print(f"  R_p: " + " ".join(f"{g}={rps.get(g, 0):.2f}" for g in sorted(rps)))
        print(f"  flagged R_p<0.5 (premium): {flag_s}  ->  "
              f"{'OK' if ok else 'LOW-CONFIDENCE'}")
    return out


def paired_ab(seeds, opps, params=None, label="arm"):
    """Real-tier paired A/B on each judge's OWN recorded seed.

    The verbatim judge is seed-locked: its tape assumes its recorded world (shop draw,
    unlock timing). On a foreign seed the tape buys garbage and the judge becomes a
    $0 bystander — a test that is too easy. On the recorded seed the only difference
    from the recorded episode is our seat's play: the counterfactual. The judge's
    recorded bank (printed) is the bar to beat; `judge_mean` shows what our play did
    to their economy.
    """
    from bridge.real_env import run_one_real
    import agents  # noqa: F401  (registers replay judges)

    print(f"== {label} ==  (real tier, each judge on its own recorded seed)")
    summary = {}
    rows_all = []
    for opp in opps:
        ep_id, path, judge_seat, rec_seed = _judge_meta(opp)
        if rec_seed is None:                      # defensive; manifest entries carry it
            rec_seed = _replay_seed(path)
        if judge_seat is not None:
            # Spectator judge: the recorded bar is that seat's own recorded bank.
            opp_rec_bank = profile(path)[judge_seat]["final_money"]
        else:
            rec_bank = MANIFEST_IDS[ep_id][1]     # OUR recorded bank in that game
            opp_rec_bank = None
            for p, pr in profile(path).items():
                fm = pr["final_money"]
                if fm is not None and abs(fm - rec_bank) > 2.0:
                    opp_rec_bank = fm
        rows = [run_one_real((rec_seed, opp, "main", params))]
        banks = sorted(r["bank"] for r in rows)
        n = len(banks)
        wins = sum(1 for r in rows if r["bank"] > r["opp_bank"])
        margins = sorted(r["bank"] - r["opp_bank"] for r in rows)
        errs = [r["err"] for r in rows if r["err"]]
        print(f"  vs {opp:16s} seed={rec_seed}  our bank ${banks[-1]:8,.0f}  "
              f"judge bank ${rows[0]['opp_bank']:8,.0f} (recorded ${opp_rec_bank:,.0f})  "
              f"margin ${margins[-1]:+8,.0f}"
              + (f"  ERR {errs[:1]}" if errs else ""))
        summary[opp] = dict(mean=banks[-1], p10=banks[0], wins=wins, n=n,
                            margin=margins[-1], judge_bank=rows[0]["opp_bank"],
                            judge_recorded=opp_rec_bank)
        rows_all.extend(rows)
    return summary, rows_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--params", default=None, help="JSON dict of PARAMS overrides")
    ap.add_argument("--opps", default=",".join(ALL_PANEL))
    ap.add_argument("--label", default="arm")
    a = ap.parse_args()
    opps = [o for o in a.opps.split(",") if o]
    if a.calibrate:
        calibrate(opps)
        return
    params = json.loads(a.params) if a.params else None
    paired_ab(range(a.seeds), opps, params=params, label=a.label)


if __name__ == "__main__":
    main()
