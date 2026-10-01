"""One-off (0930e phase 3): perfect-clone ORACLE upper bound.

For each desync donor world, force the policy to serve ITS OWN recorded chain at
every dawn regardless of signature, through the SHIPPED act() path: the policy's
book is restricted to the own donor's single variant per day and _variant_sig_eq
is patched always-true, so the chain branch locks the own world at d0 and serves
it exclusively. The 0930c action-validity guard stays live: an unexecutable own
script halts that day exactly as shipped (and the chain re-fires next dawn --
the oracle ignores sigs by construction). If the oracle cannot hold a desync
world past its measured death dawn, the residual divergence is environmental
(recorded-trajectory RNG sensitivity), not chain selection.
"""
from __future__ import annotations

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bridge.real_env import RealEnv, ENGINE_DIR  # noqa: E402
from kagfarm import policy as policy_mod         # noqa: E402
from kagfarm.policy import Policy                # noqa: E402

EIDS = ["110907373", "110926948", "110954233", "110943566", "111016701"]
SEATS = {"110907373": 1, "110938064": 1, "110943566": 1, "111016701": 1}

_ORIG_EQ = policy_mod._variant_sig_eq


def run(eid):
    path = os.path.join(_ROOT, "analysis", "replays", f"{eid}.json")
    d = json.load(open(path))
    steps = d["steps"]
    seed = int((d.get("info") or {}).get("seed") or 0)
    seat = SEATS.get(eid, 0)
    opp_seat = 1 - seat
    opp_actions = [steps[i][opp_seat].get("action") or {} for i in range(len(steps))]

    full = policy_mod._load_opening_book(
        os.path.join(_ROOT, "kagfarm", "opening_book_elite.json"))
    own = {day: [v for v in vs if v.get("donor") == eid]
           for day, vs in full.items()}
    own = {day: vs for day, vs in own.items() if vs}

    env = RealEnv(seed, ENGINE_DIR)
    pol = Policy(params={"elite_book": 1})
    pol._book = own
    pol._book_worlds = {eid: policy_mod._book_worlds(full)[eid]}
    # ORACLE patch: signatures never gate the own chain (single-variant book, so
    # no cross-chain steal is possible); the validity guard remains the only gate.
    policy_mod._variant_sig_eq = lambda s, ds, tol=2: _ORIG_EQ(
        [0, [], 0, 0, 0, 0, 0], [0, [], 0, 0, 0, 0, 0], tol)

    donor_bank = steps[-1][seat].get("reward")
    if donor_bank is None:
        farms = steps[-1][seat].get("observation", {}).get("farms") or []
        donor_bank = (farms[seat] or {}).get("money") if farms else None

    served = 0
    halts = []
    t = 0
    try:
        while not env.done:
            obs = env._obs_view(seat)
            day = int(obs.get("day", t // 24))
            a = pol.act(obs, env.config)
            if t % 24 == 0:
                if day in pol._book_decided:
                    served += 1
                elif day in pol._book_halt_days:
                    halts.append((day, "invalid"))
            oa = opp_actions[t + 1] if t + 1 < len(opp_actions) else {}
            oa = {k: (list(v) if k == "farmer" and v else v) for k, v in oa.items()}
            acts = [None, None]
            acts[seat] = a
            acts[opp_seat] = oa
            env.step(acts)
            t += 1
    finally:
        policy_mod._variant_sig_eq = _ORIG_EQ

    final = env.banks()[seat]
    return dict(eid=eid, served=served, halts=halts, donor_bank=donor_bank,
                final=final, delta=final - (donor_bank or 0))


def main():
    print(f"{'eid':<12}{'served':>7}{'halts':>7}{'donor bank':>14}{'oracle bank':>14}{'delta':>10}")
    rows = []
    for eid in EIDS:
        r = run(eid)
        rows.append(r)
        halts = ",".join(f"d{dy}" for dy, _ in r["halts"]) or "-"
        print(f"{r['eid']:<12}{r['served']:>7}{len(r['halts']):>7}"
              f"{r['donor_bank']:>14,.0f}{r['final']:>14,.0f}{r['delta']:>+10,.0f}  [{halts}]",
              flush=True)
    print(f"\nmean served: {sum(r['served'] for r in rows) / max(1, len(rows)):.1f}")
    print(f"mean delta: {sum(r['delta'] for r in rows) / max(1, len(rows)):+,.0f}")


if __name__ == "__main__":
    main()
