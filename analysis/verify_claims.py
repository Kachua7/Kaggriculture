"""
Verify the two load-bearing claims in PLAN.md section 2.

A) Routing is the binding lever: measure how many tiles the current `heuristic`
   agent actually keeps planted, vs the 100 a serpentine sweep would reach.
B) Melon revenue at realistic volumes, under the mirror's max_yield_day=10 vs
   the KT doc's engine truth of 12.

Run: python3 analysis/verify_claims.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine import KaggricultureEnv, price_for, OBJECT_TABLE, I0
from agents import agent_heuristic, agent_starter

print("=" * 78)
print("A) TILES ACTUALLY FARMED BY THE CURRENT HEURISTIC")
print("=" * 78)

env = KaggricultureEnv(episode_steps=720, seed=1)
obs = env._obs()
samples = []
while not env.done:
    obs, done = env.step([agent_heuristic(obs[0]), agent_starter(obs[1])])
    if env.t % 24 == 0:
        f = env.farms[0]
        planted = sum(1 for row in f.tiles for t in row
                      if isinstance(t, dict) and t.get("kind") == "PLANT")
        weeds = sum(1 for row in f.tiles for t in row
                    if isinstance(t, dict) and t.get("kind") == "WEED")
        unlocked = len(f.unlocked_quadrants) * 25
        samples.append((env.day, planted, weeds, unlocked, len(f.hands), f.money))

print(f"{'day':>4} {'planted':>8} {'weeds':>6} {'unlocked':>9} {'hands':>6} {'bank':>10}")
for d, p, w, u, h, m in samples[::5]:
    print(f"{d:>4} {p:>8} {w:>6} {u:>9} {h:>6} {m:>10.0f}")
peak = max(s[1] for s in samples)
mean = sum(s[1] for s in samples) / len(samples)
print(f"\npeak tiles planted = {peak}   mean = {mean:.1f}   of 100 reachable")
print(f"=> routing/assignment headroom = {100/max(mean,1):.1f}x on tiles alone")

print()
print("=" * 78)
print("B) MELON REVENUE — mirror rule vs KT-doc engine truth")
print("=" * 78)


def melon_rev(n):
    inv, rev = I0, 0.0
    for _ in range(n):
        p = price_for("MELON", inv)
        rev += p
        if p > 1:
            inv += 1
    return rev


spec = OBJECT_TABLE["MELON"]
print(f"mirror melon spec: first_yield_day={spec['first_yield_day']} "
      f"max_yield_day={spec['max_yield_day']} cap={spec['max_yield']}")
for label, mx in (("mirror  max_yield_day=10", 10), ("KT doc  max_yield_day=12", 12)):
    units_unfert = min(spec["max_yield"], mx - spec["first_yield_day"] + 1)
    units_fert = min(spec["max_yield"], 2 * (mx - spec["first_yield_day"] + 1))
    print(f"  {label}: {units_unfert} units/tile unfertilised, {units_fert} fertilised")

print()
print(f"{'melons sold':>12} {'revenue':>10} {'avg price':>10} {'tiles needed @3u':>17}")
for n in (25, 50, 80, 100, 120, 150, 200):
    r = melon_rev(n)
    print(f"{n:>12} {r:>10.0f} {r/n:>10.1f} {n/3:>17.0f}")
print()
print("Read: ~100-120 melons is the sweet spot (avg >$180). Beyond ~150 the marginal")
print("melon is near worthless, so melon *tiles* should be capped around 40, run in")
print("two waves, and the harvest sold ahead of the opponent's.")
