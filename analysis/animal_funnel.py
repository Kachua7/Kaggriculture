"""Animal-funnel trace: where do product units leak between BUY and SELL?

Stages counted per episode: BUY_ANIMAL orders, PICKUP-animal ops, PLACE ops, peak live
animals, FEED ops, escapes (`consecutive_unfed >= 2` at midnight), and product units left
in the shed at T=720. Run:

    python3 analysis/animal_funnel.py [seed]
"""

import importlib
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from engine import KaggricultureEnv                          # noqa: E402
from agents import BUILTIN_AGENTS                            # noqa: E402
from kagfarm.constants import ANIMALS, ANIMAL_PRODUCT        # noqa: E402


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    import main as agent_mod
    mod = importlib.reload(agent_mod)
    # Optional arm injection: ANIMAL_ARM=b/c applies the livestock profile (see
    # ab_livestock.py). Default runs the shipped build.
    arm = os.environ.get("ANIMAL_ARM")
    if arm:
        import kagfarm.policy as _policy
        over = {"b": {"n_animals": 20, "animal_pace": 4},
                "c": {"n_animals": 20, "animal_pace": 4, "max_hands": 12},
                # Shepherd arms: the dedicated-stream build. shepherd_share caps the stream's
                # own unit count AND the reachable herd (~2 animals/unit): share=2 froze the
                # 8-target at 4 live, so the arms carry the share their target needs.
                "shepherd8": {"n_animals": 8, "animal_pace": 3, "shepherd_mode": 1,
                              "shepherd_share": 4, "max_hands": 11},
                "shepherd20": {"n_animals": 20, "animal_pace": 4, "shepherd_mode": 1,
                               "shepherd_share": 9, "max_hands": 13}}[arm]
        _policy.PARAMS.update(over)
        importlib.reload(mod)

    env = KaggricultureEnv(episode_steps=720, seed=seed)
    opp = BUILTIN_AGENTS["arch_passive"]
    counts = Counter()
    peak_live = 0

    orig_refresh = env._refresh_animal

    def refresh_animal(f, tile):
        was = tile.get("animal")
        unfed = tile.get("consecutive_unfed", 0)
        orig_refresh(f, tile)
        if f is env.farms[0] and was is not None and tile.get("animal") is None and unfed >= 1:
            counts["escaped"] += 1

    env._refresh_animal = refresh_animal

    obs = env._obs()
    while not env.done:
        act = mod.agent(obs[0])
        for o in act.get("market") or []:
            tok = o[0] if isinstance(o, list) else "?"
            if tok == "BUY_ANIMAL":
                counts["buy_orders"] += 1
        for a in [act.get("farmer")] + list(act.get("hands") or []):
            if not a:
                continue
            if a[0] == "FEED":
                counts["feed_ops"] += 1
            elif a[0] == "PICKUP" and len(a) > 1 and a[1] in ANIMALS:
                counts["animal_pickups"] += 1
            elif a[0] == "PLACE" and len(a) > 1 and a[1] in ANIMALS:
                counts["place_ops"] += 1
        obs, _ = env.step([act, opp(obs[1])])
        live = sum(1 for row in env.farms[0].tiles for t in row
                   if isinstance(t, dict) and t.get("animal"))
        peak_live = max(peak_live, live)

    prods = set(ANIMAL_PRODUCT.values())
    shed_prod = sum(env.farms[0].shed.get(g, 0) for g in prods)
    structs = sum(1 for row in env.farms[0].tiles for t in row
                  if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE"))
    print(f"seed {seed}: buys={counts['buy_orders']} pickups={counts['animal_pickups']} "
          f"places={counts['place_ops']} structs_end={structs} peak_live={peak_live} "
          f"feed_ops={counts['feed_ops']} escaped={counts['escaped']} "
          f"shed_prod_end={shed_prod}")


if __name__ == "__main__":
    main()
