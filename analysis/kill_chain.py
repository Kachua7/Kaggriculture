"""Elite kill-chain v2: WHERE the gap opens — four phases, conversion, denial.

Per elite judge (own recorded seed, real tier — the counterfactual contract):

  Phase 0  d0-10 servicing capacity: hands, FEED/CARE/DROP/COLLECT/BUILD throughput
  Phase 1  d8-14 herd compounding: PLACED animals (tile state) vs PURCHASED (hook)
  Phase 2  d15-27 recurring monetization: settled milk/wool units + realized prices,
           product-denial D_p = judge_price x judge_units (control for counter arms)
  Phase 3  d29 terminal conversion: final-day bank delta, both seats
  Summary  first-divergence days (judge cum >= ours + 5) per category, and the
           conversion efficiencies eta_animal / eta_capital

Metric discipline (review-locked):
  - SELL divergence counts SETTLED units (_commit_unit hook), never requested orders
  - HERD divergence counts PLACED animals (tile state), split from PURCHASED
  - feed cost is approximated: wheat bought cash + all wheat consumed valued at its
    realized sale price (upper bound; own-grown feed is not observable as cash)

Usage:
    .venv/bin/python analysis/kill_chain.py --opps replay_majkel,replay_mujtaba
    .venv/bin/python analysis/kill_chain.py --params '{"n_animals": 12}'
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.ab_panel import _judge_meta  # noqa: E402

ANIMAL_GOODS = ("MILK", "WOOL", "EGG")
PX_GOODS = ("MILK", "WOOL", "MELON", "STRAWBERRY", "TOMATO", "WHEAT", "EGG")
PHYSICAL = ("FEED", "CARE", "HARVEST", "DROP", "COLLECT_FERTILIZER",
            "BUILD_COOP", "BUILD_PASTURE", "PLACE", "PICKUP")


def run_trace(seed, opp_name, params=None):
    """One episode; per-day rows + exact economic events. Analysis-only."""
    import importlib

    from bridge.real_env import RealEnv, ENGINE_DIR
    from kagfarm import policy as _policy

    if params:
        _policy.PARAMS.update(params)
    mod = importlib.import_module("main")
    importlib.reload(mod)
    from agents import BUILTIN_AGENTS
    opp = BUILTIN_AGENTS[opp_name]

    env = RealEnv(seed, ENGINE_DIR)
    # A4 (ship 0922): RealEnv's __init__ RELOADS kagfarm.policy (bridge/real_env.py:196),
    # wiping any pre-env PARAMS.update() -- every documented --params sweep silently ran
    # the shipped defaults. Re-apply AFTER the env exists so the knobs actually bind
    # (Policy instances are built lazily on the first act() call, after this point).
    if params:
        _policy.PARAMS.update(params)
    eng = env.eng
    sells = {}                       # (seat, good) -> [cash, units]  SETTLED
    bought_animals = [0, 0]          # PURCHASED (settled BUY_ANIMAL units)
    bought_animal_cash = [0.0, 0.0]
    wheat_bought = [0.0, 0.0]        # cash spent on BUY_PRODUCT WHEAT (feed + shed)
    orig_commit = eng._commit_unit

    def commit_unit(op, item, price, farm, private, market, shed_capacity=100):
        seat = 0 if farm is env.state[0].observation.farms[0] else 1
        if op == "SELL" and private.get("shed", {}).get(item, 0) > 0:
            cell = sells.setdefault((seat, item), [0.0, 0])
            cell[0] += price
            cell[1] += 1
        elif op == "BUY_ANIMAL":
            bought_animals[seat] += 1
            bought_animal_cash[seat] += price or 0.0
        elif op == "BUY_PRODUCT" and item == "WHEAT" and price is not None:
            # mirror the engine: a buy into a full shed is refused uncharged
            if sum(private.get("shed", {}).values()) < shed_capacity:
                wheat_bought[seat] += price
        return orig_commit(op, item, price, farm, private, market, shed_capacity)

    eng._commit_unit = commit_unit

    def herd(farm):
        return sum(1 for row in farm["tiles"] for t in row
                   if isinstance(t, dict) and t.get("kind") in ("COOP", "PASTURE")
                   and t.get("animal"))

    def hands(farm):
        return 1 + len(farm.get("hands") or [])

    farms = [env.state[0].observation.farms[0], env.state[1].observation.farms[1]]
    obs0 = env._obs_view(0)
    obs1 = env._obs_view(1)
    days = {}
    t = 0
    while not env.done:
        a0 = mod.agent(obs0, env.config)
        a1 = opp(obs1)
        c0, c1 = Counter(), Counter()
        for op in [a0.get("farmer") or ["PASS"]] + list(a0.get("hands") or []):
            head = (op or ["PASS"])[0]
            if head in PHYSICAL:
                c0[head] += 1
        for op in [a1.get("farmer") or ["PASS"]] + list(a1.get("hands") or []):
            head = (op or ["PASS"])[0]
            if head in PHYSICAL:
                c1[head] += 1
        env.step([a0, a1])
        day = t // 24
        row = days.setdefault(day, dict(
            b0=0.0, b1=0.0, h0=0, h1=0, a0=0, a1=0,
            f0=0, f1=0, c0=0, c1=0, dr0=0, dr1=0, co0=0, co1=0, bu0=0, bu1=0))
        row["b0"], row["b1"] = farms[0]["money"], farms[1]["money"]
        row["h0"] = max(row["h0"], hands(farms[0]))
        row["h1"] = max(row["h1"], hands(farms[1]))
        row["a0"] = max(row["a0"], herd(farms[0]))      # PLACED animals (state)
        row["a1"] = max(row["a1"], herd(farms[1]))
        row["f0"] += c0["FEED"];        row["f1"] += c1["FEED"]
        row["c0"] += c0["CARE"];        row["c1"] += c1["CARE"]
        row["dr0"] += c0["DROP"];       row["dr1"] += c1["DROP"]
        row["co0"] += c0["COLLECT_FERTILIZER"] + c0["HARVEST"]
        row["co1"] += c1["COLLECT_FERTILIZER"] + c1["HARVEST"]
        row["bu0"] += c0["BUILD_COOP"] + c0["BUILD_PASTURE"]
        row["bu1"] += c1["BUILD_COOP"] + c1["BUILD_PASTURE"]
        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)
        t += 1
    eng._commit_unit = orig_commit
    return days, sells, bought_animals, bought_animal_cash, wheat_bought


def settled(sells, seat, good):
    c = sells.get((seat, good)) or [0.0, 0]
    return c[0], c[1]


def report(name, seed, params):
    days, sells, bought, bought_cash, wheat_cash = run_trace(seed, name, params)
    print(f"\n===== {name}  (seed {seed}) =====")
    print("day |   our$  |   opp$  |  delta gap        | H  A  F  C Dr Co Bu (us) | H  A  F  C Dr Co Bu (opp)")
    prev = 0.0
    for d in sorted(days):
        r = days[d]
        gap = r["b0"] - r["b1"]
        dg = gap - prev
        mark = f" ({dg:+,.0f})" if abs(dg) > 3000 else ""
        print(f"{d:3d} | {r['b0']:7,.0f} | {r['b1']:7,.0f} | {gap:+9,.0f}{mark:12s}"
              f" | {r['h0']:2d} {r['a0']:3d} {r['f0']:3d} {r['c0']:3d} {r['dr0']:3d}"
              f" {r['co0']:3d} {r['bu0']:2d}"
              f" | {r['h1']:2d} {r['a1']:3d} {r['f1']:3d} {r['c1']:3d} {r['dr1']:3d}"
              f" {r['co1']:3d} {r['bu1']:2d}")
        prev = gap

    # --- Phase 2: settled monetization + product denial D_p ---
    print("-- Phase 2 monetization (settled units @ realized $, ours vs judge) --")
    denial = {}
    for g in ("MILK", "WOOL", "EGG"):
        oc, ou = settled(sells, 0, g)
        jc, ju = settled(sells, 1, g)
        if ou or ju:
            opx = oc / max(1, ou)
            jpx = jc / max(1, ju)
            denial[g] = (oc, ou, jc, ju)
            print(f"   {g:5s} ours {ou:4d}u @{opx:5.0f} (${oc:7,.0f})   "
                  f"judge {ju:4d}u @{jpx:5.0f} (${jc:7,.0f})   D_p judge ${jc:,.0f}")

    # --- Phase 3: terminal conversion ---
    d28, d29 = days.get(28), days.get(29, days[max(days)])
    print(f"-- Phase 3 d29 liquidation: ours {d29['b0'] - d28['b0']:+,.0f}   "
          f"judge {d29['b1'] - d28['b1']:+,.0f} --")

    # --- first divergence (judge cum >= ours + 5) ---
    cats = {"DROP": ("dr0", "dr1"), "FEED": ("f0", "f1"), "CARE": ("c0", "c1"),
            "COLLECT+HARVEST": ("co0", "co1"), "BUILD": ("bu0", "bu1"),
            "HERD_PLACED": ("a0", "a1")}
    sells_units_0 = sum(settled(sells, 0, g)[1] for g in PX_GOODS)
    sells_units_1 = sum(settled(sells, 1, g)[1] for g in PX_GOODS)
    div = {}
    cum = {k: [0, 0] for k in cats}
    for d in sorted(days):
        r = days[d]
        for k, (k0, k1) in cats.items():
            if k in div:
                continue
            cum[k][0] += r[k0]
            cum[k][1] += r[k1]
            if cum[k][1] >= cum[k][0] + 5:
                div[k] = d
    print(f"-- First divergence (judge leads by 5): "
          + "  ".join(f"{k}={v}" for k, v in sorted(div.items(), key=lambda kv: kv[1]))
          + f"   SELL_SETTLED total ours {sells_units_0} vs judge {sells_units_1} --")

    # --- conversion efficiencies ---
    ours_feed_care = sum(days[d]["f0"] + days[d]["c0"] for d in days)
    judge_feed_care = sum(days[d]["f1"] + days[d]["c1"] for d in days)
    ours_ap = sum(settled(sells, 0, g)[0] for g in ANIMAL_GOODS)
    judge_ap = sum(settled(sells, 1, g)[0] for g in ANIMAL_GOODS)
    wpx = (settled(sells, 0, "WHEAT")[0] / max(1, settled(sells, 0, "WHEAT")[1])) or 32.0
    ours_feed_cost = wheat_cash[0] + settled(sells, 0, "WHEAT")[1] * wpx
    jpx = (settled(sells, 1, "WHEAT")[0] / max(1, settled(sells, 1, "WHEAT")[1])) or 32.0
    judge_feed_cost = wheat_cash[1] + settled(sells, 1, "WHEAT")[1] * jpx
    eta_a_ours = sum(settled(sells, 0, g)[1] for g in ANIMAL_GOODS) / max(1, ours_feed_care)
    eta_a_judge = sum(settled(sells, 1, g)[1] for g in ANIMAL_GOODS) / max(1, judge_feed_care)
    eta_c_ours = ours_ap / max(1, bought_cash[0] + ours_feed_cost)
    eta_c_judge = judge_ap / max(1, bought_cash[1] + judge_feed_cost)
    print(f"-- Conversion: eta_animal ours {eta_a_ours:.2f} vs judge {eta_a_judge:.2f}   "
          f"eta_capital ours {eta_c_ours:.2f} vs judge {eta_c_judge:.2f}   "
          f"(animals bought {bought[0]} vs {bought[1]}) --")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--opps", default="replay_majkel,replay_thirdfarm,replay_mujtaba,"
                                     "replay_majkel2,replay_tfc2")
    ap.add_argument("--params", default=None)
    a = ap.parse_args()
    params = json.loads(a.params) if a.params else None
    for opp in a.opps.split(","):
        ep_id, path, judge_seat, seed = _judge_meta(opp)
        report(opp, seed, params)


if __name__ == "__main__":
    main()
