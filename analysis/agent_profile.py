"""Profile one BUILTIN_AGENTS opponent over a mirror episode: the observable
fingerprint (HIRE count, per-crop seed orders, SELLs, idle-cash steps) that
replay_autopsy prints for ladder replays, so archetypes can be FITTED to the
real opponents' numbers instead of guessed.

    python3 analysis/agent_profile.py arch_meta_labor
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from agents import BUILTIN_AGENTS              # noqa: E402
from engine import KaggricultureEnv          # noqa: E402


def _pass_like(obs):
    me = obs.get("farms", [None])[obs.get("player", 0)] or {}
    n = len(me.get("hands") or [])
    return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "arch_meta_labor"
    opp = BUILTIN_AGENTS[name]
    env = KaggricultureEnv(episode_steps=720, seed=0)
    obs = env._obs()
    hires = sells = 0
    seed_orders = {}
    idle_cash_steps = 0
    while not env.done:
        ours = _pass_like(obs[0])
        a = opp(obs[1])
        for o in a.get("market") or []:
            tok = o[0] if isinstance(o, list) else "?"
            if tok == "HIRE":
                hires += 1
            elif tok == "SELL":
                sells += 1
            elif tok == "BUY_SEED":
                crop = o[1] if len(o) > 1 else "?"
                q = o[2] if len(o) > 2 else 1
                seed_orders[crop] = seed_orders.get(crop, 0) + q
        me = obs[1].get("farms", [None, None])[1] or {}
        d = obs[1].get("day", 0)
        if 13 <= d <= 25 and (me.get("money") or 0) > 8000:
            idle_cash_steps += 1
        obs, _ = env.step([ours, a])
    print(f"{name}: HIRE={hires} SELL={sells} seed_units={seed_orders} "
          f"idle(>$8k, d13-25)={idle_cash_steps}  bank=${env.farms[1].money:,.0f}")
    print("ladder reference (Farmageddon): HIRE=314 SELL=142 "
          "seed={'WHEAT': 58-orders, ...} idle=262/312  bank=$108,029")


if __name__ == "__main__":
    main()
