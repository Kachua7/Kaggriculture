"""Replay JSON -> per-seat profile.

The single extractor for ladder replay JSONs, shared by the autopsy scripts and the
replay-opponent panel (`replay_opp.py`). Two format facts this file pins down so
nothing else has to rediscover them:

- `steps[i][p]["observation"]` is the state AFTER `steps[i][p]["action"]` is applied
  (validated to reconcile with final reward within +/- $50 on 20 player-episodes).
- Seat identity by name is unreliable (labels were seat-inverted on the 111xxx batch);
  match final banks instead (`final_money`).

`orders` preserves the exact per-turn market order lists as emitted, which is what
`REPLAY_MARKET_PRESSURE` sparring partners replay verbatim.
"""
import json
from collections import Counter, defaultdict

PRODUCTS = ("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER")


def profile(path):
    """Return {seat: profile} for a replay JSON. Profile keys:

    orders      [(turn, [market_order, ...])] -- verbatim, every turn that emitted any
    money_curve [(day, money)]                -- last observation of each day
    final_money, hires, land_buys, seeds, d0_seeds, anim_buys, sell_days
    sheds       [(day, {good: n})]            -- end-of-day private shed (own seat only)
    shops       [(day, [shop, ...])]          -- unlocked shops as of that day
    n_turns
    """
    d = json.load(open(path))
    steps = d["steps"]
    out = {}
    for p in range(len(steps[0])):
        orders = []
        money_curve = []
        money_by_day = {}
        hires = 0
        land = 0
        seeds = Counter()
        d0_seeds = Counter()
        anim_buys = Counter()
        sells = defaultdict(Counter)  # day -> good -> ordered qty
        sheds = []
        shops = {}
        for i, st in enumerate(steps):
            a = st[p].get("action") or {}
            o = st[p].get("observation") or {}
            day = o.get("day", i // 24)
            mkt = a.get("market") or []
            if isinstance(mkt, dict):
                mkt = [mkt]
            mkt = [list(mo) for mo in mkt if isinstance(mo, (list, tuple)) and mo]
            if mkt:
                orders.append((i, mkt))
            for mo in mkt:
                op = mo[0]
                q = mo[2] if len(mo) > 2 and isinstance(mo[2], int) else 1
                if op == "HIRE":
                    hires += 1
                elif op == "BUY_SEED":
                    seeds[mo[1]] += q
                    if day == 0:
                        d0_seeds[mo[1]] += q
                elif op == "SELL":
                    sells[day][mo[1]] += q
                elif op == "BUY_ANIMAL":
                    anim_buys[mo[1]] += q
                elif op == "BUY_LAND":
                    land += 1
            f = o.get("farms", [None, None])[p]
            if f is not None:
                m = f.get("money")
                if m is not None:
                    money_by_day[day] = m
            town = o.get("town") or {}
            shops[day] = list(town.get("unlocked_shops") or [])
            if p == (o.get("player") if "player" in o else p):
                priv = o.get("private") or {}
                if isinstance(priv, dict) and priv.get("shed") is not None:
                    sheds.append((day, dict(priv["shed"])))
        money_curve = sorted(money_by_day.items())
        out[p] = dict(
            orders=orders,
            money_curve=money_curve,
            final_money=money_curve[-1][1] if money_curve else None,
            hires=hires, land_buys=land,
            seeds=dict(seeds), d0_seeds=dict(d0_seeds),
            anim_buys=dict(anim_buys),
            sell_days={k: dict(v) for k, v in sells.items()},
            sheds=sheds, shops=shops, n_turns=len(steps),
        )
    return out


def our_seat(prof, our_final_money, tol=2.0):
    """Bank-matched seat ID (see module docstring: names are unreliable)."""
    for p, pr in prof.items():
        fm = pr["final_money"]
        if fm is not None and abs(fm - our_final_money) <= tol:
            return p
    raise ValueError(f"no seat matches final bank {our_final_money}")


def executed_flow(pr):
    """Per-good executed (settled) sales, estimated from the recorded shed deltas.

    A settled SELL is a negative shed delta. Not exact -- wheat also leaves the shed
    via PICKUP->FEED, and end-of-day DROP inflow can net against same-day sells -- but
    it is the only per-good executed signal the replay carries, and it is what the
    panel's R_p fidelity gate compares against (mirror-side executed sells are exact).
    """
    flow = Counter()
    prev = {}
    for day, shed in pr["sheds"]:
        for good, n in shed.items():
            if good in PRODUCTS and prev.get(good):
                delta = n - prev[good]
                if delta < 0:
                    flow[good] += -delta
            prev[good] = n
    return dict(flow)


if __name__ == "__main__":
    import sys
    for path in sys.argv[1:]:
        prof = profile(path)
        print("=" * 72)
        print(path.split("/")[-1])
        for p in sorted(prof):
            pr = prof[p]
            print(f" seat {p}: final ${pr['final_money']:,.0f}  hires={pr['hires']}  "
                  f"land={pr['land_buys']}  d0={pr['d0_seeds']}")
            print(f"   seeds={pr['seeds']}")
            print(f"   animals={pr['anim_buys']}")
            print(f"   executed~{executed_flow(pr)}")
