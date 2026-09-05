# Kaggriculture — build plan

Written 5 Sep 2026. Entry deadline **23 Sep 2026** — 18 days.
Target: top of the Kaggle ladder, with a presentable demo layer that doubles as debugging tooling.

---

## 1. Where we actually stand

| Thing | Status |
|---|---|
| Knowledge transfer doc | Complete and trustworthy (`Kaggriculture_FINAL_KT.md`) |
| `kagfarm/` v1 agent (17 tests passing) | **Gone.** Lived in a sandbox that reset. Rebuild from the doc. |
| Local mirror simulator (`engine.py`, 801 lines) | **Survives, and it works.** Runs a full 720-turn episode in a few seconds. |
| Sample agents (`agents.py`) | Toy level. `heuristic` ends the season on **$5,825** from a $3,000 start. |
| Real `kaggle-environments` engine | Not installed anywhere. Cannot be reached from my sandbox (PyPI and GitHub are both egress-blocked). |
| Git | Not initialised. |

Two consequences that shape everything below:

1. **The mirror sim is the iteration loop, not the real engine.** I can run thousands of
   episodes against `engine.py` at high speed. That is how knobs get tuned — you cannot
   tune 15 parameters through a Kaggle submission queue. The real engine's role is
   *periodic validation*, and it has to run on your machine, not mine.
2. **The mirror is uncalibrated in exactly the places that matter most.** Its market
   curve reproduces the official 4-point price table exactly, but its crop *yield growth*
   rules were inferred from prose. Section 5 lists the specific divergences. Two of them
   change melon economics by 3×, and melon turns out to be the most valuable good in the
   game — so calibration is Phase 0, not an afterthought.

---

## 2. What the numbers say the strategy has to be

I ran an economic probe over the mirror's market model (`analysis/econ_probe.py`).
The results are lopsided enough to dictate the strategy rather than merely inform it.

### 2.1 Market depth is the real constraint, and it is wildly asymmetric

Units sellable from a fresh market before the marginal price decays below a threshold:

| Good | base | ≥90% | ≥75% | ≥50% | revenue for first 100 units |
|---|---|---|---|---|---|
| **Melon** | 250 | 51 | 80 | 113 | **$21,721** |
| Wool | 200 | 19 | 30 | 42 | $7,969 |
| Milk | 160 | 8 | 20 | 39 | $6,205 |
| Tomato | 60 | 7 | 38 | 144 | $4,318 |
| **Egg** | 50 | 24 | **1,422** | ∞ | $4,371 |
| Strawberry | 120 | 7 | 16 | 32 | $3,847 |
| Carrot | 35 | 10 | 55 | 230 | $2,738 |
| **Wheat** | 25 | 20 | **2,421** | ∞ | $2,193 |

Three distinct classes, and they want three different behaviours:

- **Melon is the prize.** Its glut curve is `sq`, which is almost flat near `I0`, so the
  first ~80 melons clear above $187 each. One hundred melons is $21.7k — more than three
  seasons of the current heuristic agent's entire output. Nothing else comes close.
- **Wheat and egg are bottomless** (`log` glut curves). They never fall below half base,
  no matter how much you dump. They are the grind: low unit value, unlimited scale.
- **Everything else is thin.** Strawberry dies after 16 units, milk after 20, wool after
  30. These are worth farming only in quantities matched to town demand.

### 2.2 The market only degrades, so selling early beats selling late

Market inventory rises when anyone sells and falls only through town consumption and
`BUY_PRODUCT`. So the book is a depleting shared resource, and unsold inventory scores
zero at turn 720. Two hard consequences: front-load premium sales, and ramp to full
liquidation over the last day regardless of price.

### 2.3 On the thin goods, being second means selling at the $1 floor

Both players sell into the same book. Melon hits the floor 300 units above `I0`; if the
opponent dumps 150 melons before we do, our melons are worth nothing. This is the one
place where genuine opponent modelling pays, and it pays a lot.

### 2.4 Labour is nearly free, so routing quality sets farm size

Hire cost is the Fibonacci of hires already made that day, reset at dawn:

| Hands hired/day | Cost/day | Cost/season | Unit-actions/day |
|---|---|---|---|
| 6 | $20 | $600 | 168 |
| 8 | $54 | $1,620 | 216 |
| **10** | **$143** | **$4,290** | **264** |
| 12 | $376 | $11,280 | 312 |

Ten hands cost $4,290 for the season — trivial against a $20k+ melon book. So labour is
not a budget question, it is a *routing* question. A hand walking a 10-tile row spends
10 `WATER` + 9 moves = 19 of its 24 turns and covers 10 tiles. Ten hands on ten rows
covers the entire 100-tile board in one day, with slack to spare. Greedy
nearest-target assignment — what v1 did, and what `agents.py` still does — wastes two to
four times that, which caps the farm at roughly 25–40 tiles.

**This is the single biggest lever in the project.** Farm size drives revenue, and
routing drives farm size.

### 2.5 Logistics are free if you exploit the midnight dump

Seeds live in an uncapped slot that `PLANT` draws from directly, and every unit's carried
inventory auto-dumps into the shed at midnight. So a unit never needs to walk to the shed
to plant or to deliver a harvest — only to collect fertilizer or wheat for feeding.

The binding logistics constraint is instead the **100-item shed cap**, since midnight
overflow is silently discarded. Sell the shed down to empty each day and you can absorb
~100 harvested items per night. Selling itself is nearly free: 10 orders per turn × 24
turns, and each order carries any quantity.

### 2.6 Measured, not assumed

I instrumented an episode to check the two claims the plan leans on
(`analysis/verify_claims.py`):

- The current `heuristic` agent keeps a **mean of 11.4 tiles planted, peak 16, out of 100
  reachable**. It never buys land, and it lets weeds accumulate to 13 tiles by day 21
  without ever digging them. Roughly **8.8× headroom on tile count alone** — which is the
  §2.4 routing argument, confirmed rather than asserted.
- Melon revenue by volume: 80 units → $18.3k (avg $229), 120 → $24.3k (avg $203),
  150 → $26.4k (avg $176), 200 → $26.5k (avg $133). So the marginal melon past ~150 is
  worthless. **Cap the melon program near 120–150 units** — about 40–50 tiles at 3
  units/tile, or 20–25 fertilized at 6 — run in two waves, sold ahead of the opponent.
- Under the mirror's `max_yield_day=10`, a melon tile yields **1** unit. Under the KT doc's
  engine truth of **12**, it yields 3 (6 fertilized). That single constant is worth 3× on
  the best good in the game, which is why calibration leads the schedule.

### 2.7 The number to beat

| Scenario | Terminal bank |
|---|---|
| Current `heuristic` in the mirror | $5,825 |
| Full board, good routing, wheat only | ~$25–30k |
| Same plus a front-loaded melon book | **~$40–60k** |

So there is roughly an order of magnitude of headroom over what exists today. Treat
$40k in the mirror as the target and the ladder as the referee.

---

## 3. Target architecture

Keep the KT doc's layered `kagfarm/` design — it is well factored, one idea per file,
imports flowing one way, and it is what actually ships. Add offline siblings that never
ship.

```
kaggriculture/
├── main.py                 # agent(obs) entry point — the submission
├── pack.sh                 # -> submission.tar.gz
├── kagfarm/                # THE ONLY THING THAT SHIPS
│   ├── agent.py            #   wiring + wall-clock guard + PASS shield
│   ├── constants.py        #   frozen engine numbers (shared source of truth)
│   ├── config.py           #   sweepable knobs, nothing else
│   ├── state.py            #   obs parsing (dict or struct)
│   ├── geometry.py         #   coords, BFS, and the route builder
│   ├── biology.py          #   crop/animal clocks
│   ├── economy.py          #   price model, hire cost, reserve prices
│   ├── planner.py          #   WHAT work exists, in urgency bands
│   ├── routes.py           #   NEW: dawn sweep-route construction
│   ├── assign.py           #   WHO does it
│   ├── market.py           #   the order book
│   └── actions.py          #   Job -> op compiler
├── sim/                    # the mirror engine (was engine.py)
├── harness/                # parallel eval, sweeps, self-play pool
├── analysis/               # econ probes, replay diffing
├── viz/                    # replay viewer + metrics dashboard (demo layer)
└── tests/
```

`routes.py` is the one genuinely new file relative to the v1 design, and it exists
because of §2.4.

---

## 4. Schedule

Eighteen days. Each phase ends in something submittable, because a phase that cannot be
submitted cannot be measured.

### Phase 0 — Ground truth (5–6 Sep)

The only phase that requires your machine rather than mine.

- `git init`, commit what exists, add `.gitignore` for `__pycache__`, `artifacts/`.
- `pip install -U kaggle-environments` on the Mac.
- Dump the real engine's constants and the price curve at a grid of inventories; diff
  against `MARKET_PARAMS` in the mirror. The mirror's `T` and target values were solved
  to fit a 4-point table, so they may be right at the checkpoints and wrong between them.
- Resolve the yield-growth divergences in §5.
- Extract `kagfarm/constants.py` and have the mirror import from it, so the agent and the
  simulator can never drift apart.

**Exit:** mirror and real engine agree on price at 20 sampled inventories per good, and on
yield trajectory for a hand-scripted single-tile episode per crop.

### Phase 1 — kagfarm v2 with real routing (6–9 Sep)

Rebuild the shipped package. Not a port of v1 — v1's greedy assignment is the thing to
replace.

- Dawn planner: partition owned tiles into row-serpentine sweeps, one per hand, balanced
  by workload. Each hand gets a *full-day route* it follows, re-planned only on
  disruption (weed appears, plant dies, land unlocked).
- Urgency bands stay as the doc has them: survive tonight → yield today → finish
  structure → expand → dig weeds.
- Wall-clock guard in `agent.py`: budget ~250 ms, and if a turn exceeds it, emit the
  cached route step. A timeout is a forfeit; this must be belt-and-braces.
- All four quadrants unlocked on the schedule the sweep says pays for itself (v1's
  turn-0 land purchase before any seed is in the ground is probably wrong).

**Exit:** ≥$20k in the mirror against `heuristic`, and the first real Kaggle submission.

### Phase 2 — Eval harness (9–11 Sep)

- Parallel headless runner across seeds × opponent pool, one process per core.
- Metrics that diagnose rather than just score: tiles maintained per day, wasted
  unit-actions, **items destroyed by shed overflow**, revenue by good, realized price as
  a fraction of base, plants lost to weeds, turns over the time budget.
- Regression gate: a change that lowers mean terminal bank across the seed set is
  reverted, not argued about.

**Exit:** 200 episodes in under two minutes, with a one-command metrics table.

### Phase 3 — Market brain (11–14 Sep)

Replace fixed sell fractions with marginal-price reasoning.

- For each good, sell while marginal price ≥ a reserve price. The reserve starts high and
  decays as the season runs out, because inventory is worth zero at turn 720.
- Credit expected town drain: a good the shops eat 19 units of per day can be sold at that
  rate indefinitely without moving the price.
- Endgame liquidation ramp over the last 24–48 turns, everything out the door.
- Buy back wheat when it is cheap and we need feed, which the `log` curve makes viable.

**Exit:** realized price ≥ 80% of base on melon and ≥ 70% on wool/milk across the seed set.

### Phase 4 — Crop portfolio and livestock (13–17 Sep)

- Enable melon first — it is the whole ballgame — timed so the first wave matures around
  day 11–13 and a second wave lands before the endgame.
- Then wool and milk sized to town drain, then eggs as bottomless filler.
- Sweep: coordinate descent over the knobs first, then CMA-ES over the survivors, against
  an opponent pool that includes frozen earlier versions of ourselves.

**Exit:** ≥$35k in the mirror; ladder rank trending up across submissions.

### Phase 5 — Opponent awareness (16–20 Sep)

- Estimate the opponent's per-good sell rate from market inventory deltas, which are
  public.
- On thin goods, pre-empt: if they are about to flood melon, sell into the strength first.
- Self-play tuning so the policy is not overfitted to `heuristic`.

**Exit:** wins ≥60% of head-to-head episodes against the Phase 4 build.

### Phase 6 — Debug viz and final submissions (18–23 Sep)

Kaggle is the hackathon (see §8), so nothing here is judge-facing.

- Replay viewer, as a debugging tool: board state, unit routes, bank curve, market book
  over time. Built to answer "where is a hand wasting turns" and "when did the melon book
  get away from us", not to impress anyone.
- Daily submissions through the deadline; freeze the last known-good build 48 hours early.
- Time reclaimed from the dropped pitch/slides work is spent on Phases 4 and 5.

---

## 5. Calibration checklist (mirror vs real engine)

These are the specific places the mirror is guessing. Ranked by how much money rides on
the answer.

| # | Question | Mirror says | KT doc says | Money at stake |
|---|---|---|---|---|
| 1 | Melon `max_yield_day` | 10 | **12** | Melon yields 1 unit/tile vs 3 (or 6 fertilized). 3× on the best good in the game. |
| 2 | Does wheat start at `yield_units = 1`? | No | **Yes** | +33% on every wheat tile. |
| 3 | Exact yield growth rule | +1 per watered day in the window | prose only | Sets every crop's value. |
| 4 | Market `T` and target per good | fitted to 4 checkpoints | table only | Sell sizing. Wrong `T` means systematically over- or under-selling. |
| 5 | Do animals eat wheat, 1/day? | assumed yes | implied | Livestock viability. |
| 6 | Post-peak decay of unharvested crops | 1 unit every other day, then weed | unspecified | Harvest timing. |
| 7 | Watering bonus window mechanics | folded into growth | `[(max+1)//2, max]`, applied at WATER time | Up to +2/tile. |

Items 1 and 2 are documented in the KT doc as engine truth and the mirror simply
contradicts them — fix those on sight in Phase 0. Items 3–7 need a real episode to settle.

---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| **1s act timeout** — a single slow turn forfeits the episode | Hard wall-clock budget in `agent.py`, cached-plan fallback, and a harness metric that counts turns over budget |
| Mirror diverges from the real engine, so we tune for the wrong game | Phase 0 calibration; re-diff after any real-engine run; never let a knob be tuned on an uncalibrated rule |
| `hands` list length must exactly equal `len(hands)` | Enforced in `actions.emit_all`, asserted in tests |
| Shed overflow silently destroys harvested value | Explicit metric; sell-down policy keyed to tomorrow's expected harvest |
| Overfitting to `heuristic` as the only opponent | Self-play pool of frozen prior builds from Phase 4 on |
| Submission queue is the bottleneck for ladder convergence | Submit from end of Phase 1, daily thereafter |
| One clever change breaks everything two days before the deadline | Freeze a known-good build 48h out; regression gate on every merge |

---

## 7. Division of labour

You are building this through me, so I own all of it — code, simulation, tuning, analysis.
There are exactly three things the sandbox physically prevents me from doing:

| Only you can do | Why | Effort |
|---|---|---|
| Run `bash bootstrap.sh` once | My VM has no PyPI or GitHub egress, so `kaggle-environments` can only be installed on your Mac. The script installs it, dumps the real engine's constants and a validation trace to `calibration/`, and I read those files straight out of this folder. | One command |
| Accept the competition rules in the browser | Kaggle gates submission behind a click-through. | One click |
| Run `bash submit.sh "<message>"` | Needs your Kaggle credentials. | One command per submission |

Everything else — including all calibration reasoning once the dump exists — is mine.
Where work fans out across independent pieces I'll run it as parallel subagents rather
than serially; the shipped policy stays fast deterministic Python, because the Kaggle
sandbox has no network and enforces one second per turn.

## 8. Scope change: Kaggle *is* the hackathon

Confirmed 5 Sep. There is no separate judged event, so ladder rank is the only thing that
scores. That removes the judge-facing deliverables from Phase 6 — no pitch, no slides, no
narrative polish. The replay viewer survives, but demoted to what it always really was: a
debugging tool for watching where hands waste turns and where the market book gets away
from us. The ~2 days that frees goes into Phases 4 and 5, which are where bank comes from.


