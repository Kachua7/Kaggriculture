"""Direct Policy probe on the mirror -- surfaces swallowed exceptions.

main.agent's never-raise contract turned the KT regression into silent DEAD funnels.
This drives kagfarm.policy.Policy with the exception handler removed (we call the
policy's act directly, no wrapper) so a crash prints its traceback.

    python3 analysis/kt_trace_probe.py [seed]
"""

import os
import sys
import traceback
from collections import Counter

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import KaggricultureEnv  # noqa: E402
from agents import BUILTIN_AGENTS  # noqa: E402
from kagfarm.policy import Policy  # noqa: E402

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
env = KaggricultureEnv(episode_steps=720, seed=seed)
pol0, pol1 = Policy(), Policy()
obs = env._obs()
ops = Counter()
last_day = -1

while not env.done:
    day = obs[0]["day"]
    if day != last_day:
        # dawn snapshot: animals, shed wheat, bank, roster
        farm = obs[0]["farms"][0]
        shed = obs[0]["private"]["shed"]
        tiles = farm["tiles"]
        animals = sum(1 for row in tiles for t in row
                      if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE") and t.get("animal"))
        print(f"d{day:>2} dawn bank {farm['money']:>8,.0f} shedW {shed.get('WHEAT', 0):>3} "
              f"animals {animals:>2} hands {1 + len(farm['hands']):>2}")
        last_day = day
    try:
        act0 = pol0.act(obs[0])
        act1 = pol1.act(obs[1])
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    for op in [act0.get("farmer") or ["PASS"]] + list(act0.get("hands") or []):
        if op and op[0] in ("BUY_ANIMAL", "PLACE", "FEED", "PICKUP", "CARE", "COLLECT_FERTILIZER"):
            ops[op[0]] += 1
    for m in act0.get("market") or []:
        if m and m[0] == "BUY_ANIMAL":
            ops["MKT_BUY_ANIMAL"] += 1
    obs, _ = env.step([act0, act1])

banks = [obs[0]["farms"][0]["money"], obs[0]["farms"][1]["money"]]
shed = obs[0]["private"]["shed"]
rot = {k: v for k, v in shed.items() if k in ("COW", "SHEEP", "GOOSE") and v}
print(f"\nFINAL bank {banks[0]:,.0f} / opp {banks[1]:,.0f} | ops {dict(ops)} | shed rot {rot}")
