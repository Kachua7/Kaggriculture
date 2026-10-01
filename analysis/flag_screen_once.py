"""0930f herd-protection screening: each flag ON vs the shipped baseline, mirror tier.

The twin-vs-twin mirror world reproduces the loss conditions measured on the ladder
(both seats run the 9+5 cow/sheep envelope -> shared MILK inventory gluts -> milk
price craters -> the no-shop-drain pile crowds the feed grain). Metrics per arm:
  herd29   animals alive at the final dawn (the escape metric)
  herd22   animals alive at d22 (before the ladder's escape window closed)
  shedW22  shed WHEAT at d22 dawn (the feed-buffer metric through the crowded window)
  milk22   shed MILK at d22 dawn (the dead-pile metric)
  min_feed minimal per-day FEED count d18-24 (the chore metric)

Usage:  PYTHONHASHSEED=0 .venv/bin/python analysis/flag_screen_once.py
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
    ("shed_endgame_chore", {"shed_endgame_chore": 1}),
    ("grain_release", {"grain_release": 1}),
    ("no_shop_valve", {"no_shop_valve": 1}),
    ("milk_dead_hold_release", {"milk_dead_hold_release": 1}),
    ("all_four", {"shed_endgame_chore": 1, "grain_release": 1,
                  "no_shop_valve": 1, "milk_dead_hold_release": 1}),
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
    return dict(herd29=herd29, herd22=herd22, shedW22=shedW22, milk22=milk22,
                min_feed=feed_d1824, sum_bank=bank)


def main():
    print(f"{'arm':<24}{'herd22':>7}{'herd29':>7}{'shedW22':>8}{'milk22':>7}"
          f"{'minfeed':>8}{'sumbank':>10}")
    for name, arms in ARMS:
        r = run(arms)
        print(f"{name:<24}{r['herd22']:>7}{r['herd29']:>7}{r['shedW22']:>8}"
              f"{r['milk22']:>7}{r['min_feed']:>8}{r['sum_bank']:>10,.0f}", flush=True)


if __name__ == "__main__":
    main()
