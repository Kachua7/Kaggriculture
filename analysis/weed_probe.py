"""Split the weed count by cause: died of thirst, or reached end of life.

`eval.py` reports one `weeds` number, and that number rose monotonically with roster size
(9.7 at four hands, 20.7 at nine), which read like an over-planting failure -- the allocator
committing tiles the roster could not water. But `engine._refresh_plant` turns a tile to WEED
for two unrelated reasons, and only one of them is a failure:

  thirst   `consecutive_unwatered` hits 2. Forfeits the tile's whole remaining cycle. Real cost.
  spent    the crop finished its yield schedule, decayed to zero units and vanished. This is
           what a fully harvested plant is *supposed* to do, and a bigger farm cycles more
           plants through it. Costs nothing.

A metric that adds those together says a productive farm is a wasteful one. This probe wraps
`_refresh_plant`, reads the counter before the engine touches it, and attributes each death.

    python3 analysis/weed_probe.py --seeds 8
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def run_one(seed, opp_name, params=None):
    from engine import KaggricultureEnv
    from agents import BUILTIN_AGENTS
    from kagfarm import policy as _policy
    import main as agent_mod

    if params:
        _policy.PARAMS.update(params)

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    opp = BUILTIN_AGENTS[opp_name]
    me = env.farms[0]
    counts = {"thirst": 0, "spent": 0, "thirst_units": 0}
    orig = env._refresh_plant

    def wrapped(f, x, y, tile):
        before = tile.get("consecutive_unwatered", 0)
        watered = tile.get("watered_today")
        orig(f, x, y, tile)
        after = f.tiles[y][x]
        if isinstance(after, dict) and after.get("kind") == "WEED" and f is me:
            if not watered and before + 1 >= 2:
                counts["thirst"] += 1
                # What the death actually cost: the units still on the plant, plus the units
                # the rest of its schedule would have added had it lived.
                counts["thirst_units"] += tile.get("yield_units", 0)
            else:
                counts["spent"] += 1

    env._refresh_plant = wrapped
    obs = env._obs()
    while not env.done:
        obs, _ = env.step([agent_mod.agent(obs[0]), opp(obs[1])])
    counts["bank"] = me.money
    counts["seed"] = seed
    counts["opp"] = opp_name
    return counts


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--opps", default="starter,heuristic")
    ap.add_argument("--slack", default="")
    a = ap.parse_args()
    slacks = [float(s) for s in a.slack.split(",") if s] or [None]
    for s in slacks:
        params = {"labour_slack": s} if s is not None else None
        rows = [run_one(seed, opp, params)
                for opp in a.opps.split(",") for seed in range(a.seeds)]
        n = len(rows)
        print("slack=%-5s n=%-3d bank $%7.0f | thirst %5.2f (%4.1f units) | spent %5.2f"
              % (s, n, sum(r["bank"] for r in rows) / n,
                 sum(r["thirst"] for r in rows) / n,
                 sum(r["thirst_units"] for r in rows) / n,
                 sum(r["spent"] for r in rows) / n))


if __name__ == "__main__":
    main_cli()
