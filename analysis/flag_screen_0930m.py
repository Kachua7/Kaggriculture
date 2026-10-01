"""0930m plan-item screening: each new flag ON vs the shipped baseline, mirror tier.

Same world and metrics as the 0930f precedent (twin-vs-twin mirror, seed 0 - the
world that reproduces the ladder's shared-MILK glut / feed-crunch loss conditions).
Arms are the 0930m plan items, all default-off in the ship block:
  opp_pace     opp_supply_pace=1     (anticipate the rival's milk supply - 0930k evidence)
  feed_floor   feed_demand_floor=1   (shed wheat pinned to mouths at any price, incl. endgame)
  route_skip   route_skip_stuck=1    (split_runs skips over-budget jobs instead of stranding)
  combo        all three together
  marginal_fix marginal_sell=1 with the repaired 8-arg call (expected to reproduce its
               measured reject; proves the signature repair does not silently change it)

sell_gate_always is not screened: its default equals always_sell and the only engine
site that reads it (the endgame pause) is itself dormant (endgame_floor=0, measured
reject), so it is inert by construction; the tests pin the default equality.

Also reports summed `Policy._fallback_errors` per arm (the 0930m exception-to-PASS
counter) - expected 0 everywhere; nonzero means the never-raise guard is hiding work.

Usage:  PYTHONHASHSEED=0 .venv/bin/python analysis/flag_screen_0930m.py
"""
from __future__ import annotations

import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from kagfarm.policy import Policy            # noqa: E402
from engine import KaggricultureEnv          # noqa: E402

ARMS = [
    ("shipped", {}),
    ("opp_pace", {"opp_supply_pace": 1}),
    ("feed_floor", {"feed_demand_floor": 1}),
    ("route_skip", {"route_skip_stuck": 1}),
    ("combo", {"opp_supply_pace": 1, "feed_demand_floor": 1, "route_skip_stuck": 1}),
    ("marginal_fix", {"marginal_sell": 1}),
]
SEATS = (0, 1)


def snapshot(obs, seat):
    me = (obs.get("farms") or [{}])[seat]
    shed = (obs.get("private") or {}).get("shed") or {}
    tiles = me.get("tiles") or []
    herd = sum(1 for r in tiles for t in r
               if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE")
               and t.get("animal"))
    return herd, int(shed.get("WHEAT", 0) or 0), int(shed.get("MILK", 0) or 0)


def run(arms):
    env = KaggricultureEnv(episode_steps=720, seed=0)
    pols = [Policy(dict(arms)) for _ in SEATS]
    obs = env._obs()
    herd29 = herd22 = shedW22 = milk22 = None
    feeds = {0: {}, 1: {}}
    t = 0
    while not env.done:
        acts = [pols[s].act(obs[s]) for s in SEATS]
        for s, a in enumerate(acts):
            day = t // 24
            for cmd in [a.get("farmer")] + list(a.get("hands") or []):
                if cmd and cmd[0] == "FEED":
                    feeds[s][day] = feeds[s].get(day, 0) + 1
        obs, _ = env.step(acts)
        t += 1
        if t % 24 == 0:
            day = t // 24
            for s in SEATS:
                h, w, m = snapshot(obs[s], s)
                if day == 22:
                    herd22, shedW22, milk22 = h, w, m
                if day >= 29:
                    herd29 = h
    feed_d1824 = min(min(feeds[s].get(d, 0) for d in range(18, 25)) for s in SEATS)
    bank = env.farms[0].money + env.farms[1].money
    errs = sum(getattr(p, "_fallback_errors", 0) for p in pols)
    return dict(herd29=herd29, herd22=herd22, shedW22=shedW22, milk22=milk22,
                min_feed=feed_d1824, sum_bank=bank, errs=errs)


def main():
    print(f"{'arm':<14}{'herd22':>7}{'herd29':>7}{'shedW22':>8}{'milk22':>7}"
          f"{'minfeed':>8}{'sumbank':>10}{'fberr':>6}")
    for name, arms in ARMS:
        r = run(arms)
        print(f"{name:<14}{r['herd22']:>7}{r['herd29']:>7}{r['shedW22']:>8}"
              f"{r['milk22']:>7}{r['min_feed']:>8}{r['sum_bank']:>10,.0f}{r['errs']:>6}",
              flush=True)


if __name__ == "__main__":
    main()
