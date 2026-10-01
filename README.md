<div align="center">

# 🌾 kagfarm

### A competitive autonomous agent for Kaggle's Kaggriculture simulation

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Kaggle](https://img.shields.io/badge/Kaggle-Kaggriculture-20BEFF?style=flat-square)](https://www.kaggle.com/competitions/kaggriculture)
[![Tests](https://img.shields.io/badge/Tests-226%20passing-2ea44f?style=flat-square)](#-testing)
[![Engine](https://img.shields.io/badge/Real--engine-1.32.7%20vendored-6f42c1?style=flat-square)](#-measurement-and-experimentation)

**Observe → Model → Decide → Schedule → Execute → Measure → Improve**

</div>

---

## What is this?

Kaggriculture is a two-player farming simulation on Kaggle: over a 30-day season
(720 turns) each agent manages crops, livestock, hired farm hands, land expansion
and market orders under a **dynamic shared market** — and the winner is whoever
holds more coins at terminal. Every action costs time and movement, the opponent's
production moves the same prices you sell into, and animals you can't service
escape and die.

This repository is my agent for it — `kagfarm` — plus everything built around it:
a local reimplementation of the rules, an evaluation bridge into the vendored
competition engine, ~78 experiment harnesses, a 226-test suite, and a measurement
ledger ([calibration/live.md](calibration/live.md)) where every experiment —
including the regressions — is recorded.

> The interesting part isn't the farm. It's the control problem:
> **short-term survival vs. long-horizon economic value, against an adaptive
> rival in a shared market.**

<p align="center">
  <img src="docs/architecture.svg" alt="kagfarm decision pipeline" width="720"/>
</p>

---

## Architecture

The agent is organized around one canonical state representation and a layered
decision pipeline:

```text
Observation
    ↓
WorldState ──────────── one snapshot: cash, roster, positions, shed,
    │                  market, FutureSupply[g][t], ServiceLoad[t], slack
    ↓
Opponent inference ──── behavioral phenotype posterior from public state
    ↓                  (MILK/WOOL p10 / p50 / p90 arrival waves)
Strategy zoo ────────── E0–E8, each a parameter overlay on one executor
    ↓
Runtime selector ────── commits one expert per macro window
    │                  (d0/3/6/9/12/16/20/24) + danger-trigger overrides
    ↓
Task planner ────────── portfolio: plant, buy, feed, expand, sell
    ↓
Worker scheduler ────── serpentine allocation → deferred jobs →
    ↓                  global reassignment (cheapest marginal walk)
Market-slot optimizer ─ max Σ ΔV·x  s.t.  Σ slots ≤ 10, sells floored
    ↓
Deterministic executor
```

### Core ideas

**1. Canonical world state.** Subsystems don't each reinterpret the raw
observation. Crops, animals, the opponent's acreage, service capacity and market
pressure are projected into one shared forecast object — because the failure mode
I kept hitting was *two planners quietly disagreeing about the same state*. The
clearest example: the market's supply model and the allocator's supply model used
the same pipeline function with different arrival-weighting, and the inconsistency
survived two submission cycles before the shared-state rewrite exposed it.

**2. Runtime strategy selection.** The agent doesn't commit to one strategy.
A zoo of nine parameter overlays (E0 elite prior … E7 anti-livestock, E8
liquidity) is scored at macro decision points, and the winner is committed for a
window — unless a danger trigger (service deficit, herd-collapse risk, price
shock) fires mid-window.

**3. Opponent modelling as market externality.** The rival isn't controlled, but
their herd moves the shared market. The agent maintains a behavioral-phenotype
posterior and prices own-livestock decisions partly on *their* expected milk/wool
arrival waves — because in a shared market, sometimes the best move changes what
the opponent's production is worth.

**4. Worker scheduling as a real optimization.** Every turn spent walking is a
turn not producing. The scheduler runs serpentine allocation with set-aside and
continue, then a global reassignment pass that hands deferred jobs to the unit
with the cheapest marginal walk. This one mechanism recovered a lost matchup
(−$22,109 → +$12,749) without touching strategy.

**5. Market slots as constrained optimization.** Ten order slots per turn,
shared between buys and sells, under cash and inventory feasibility. The agent
re-packs discretionary orders by marginal value per slot rather than walking a
fixed priority ladder — survival orders (hire, land) stay constitutional.

---

## Measurement and experimentation

The evaluation infrastructure is the project. Every mechanism lives behind a
flag in `PARAMS`, ships dormant until a real-engine battery promotes it, and
every verdict lands in the ledger — **W/L is the promotion metric; margin is a
tiebreaker**. Two findings that justify the discipline:

- **A "catastrophic −$115,914" regression was a measurement artifact.** The flag
  under test hit a stale 7-argument call, crashed inside a never-raise guard, and
  cascaded to PASS-everything. After repairing the call, the true mechanism
  measured W/L-neutral. The ledger row was invalidated, not hidden.
- **A +38% margin improvement shipped zero W/L change** — and one tier took a
  real W→L regression in the same build. Margin lies; W/L is the objective.

### Battery of record (sub31 ship state, real engine 1.32.7, `PYTHONHASHSEED=0`)

| Tier | W/L | Mean margin (coins) | Notes |
| --- | :-: | ---: | --- |
| Elite (3 judges) | 0–3 | −80,941 | best-ever on this tier |
| Famine (2) | 2–0 | +45,256 | best-ever |
| Midfield (4) | 4–0 | +24,260 | |
| Wall (7) | 2–5 | −12,670 | recovered from 1–6 by the scheduler fix |

### First full strategy-zoo table (six W/L-moving judges)

| Expert | W/L | Mean Δ margin |
| --- | :-: | ---: |
| E0 elite prior | 6–0 | +31,259 |
| E7 anti-livestock | 6–0 | **+33,191** |
| E8 liquidity | 6–0 | **+32,969** |

E7 beating E0 on margin does **not** promote it — the promotion rule is W/L.
What it proved is that the state space contains regimes where the elite prior
leaves value on the table, which is exactly why the runtime selector exists.

### Real-ladder read (sub26, 25 public episodes)

14W–11L, mean +4,521; dominant below 540 Elo (13W–2L, mean +26k), winless above
600 (0W–5L, mean −40,193) — a ceiling gap traced per-episode to herd service
collapse, which is what the service-slack machinery now models.

> These are repository-recorded internal evaluations against identified judge
> seatings, not claims about the official competition leaderboard.

---

## Testing

```bash
PYTHONHASHSEED=0 .venv/bin/python -m unittest discover -s tests -q
# Ran 226 tests ... OK
```

226 unit tests cover the policy contracts: scheduler invariants, service
survival gating, opponent-supply calendars (including the day-0 placement edge
case), market-slot feasibility, sell floors under every crowding path, and the
flag-gated subsystems. The hash seed is pinned because a tiny behavioral change
can reroute a 720-turn trajectory — reproducibility is part of the measurement.

---

## Submission pipeline

```bash
PYTHONHASHSEED=0 PYTHON="$PWD/.venv/bin/python" SEEDS=8 bash pack.sh
# PACK OK 16/16 bank-for-bank  →  submission.tar.gz + regenerated submission/main.py
```

`bundle.py` produces the single-file build (a pure function of `main.py` +
`kagfarm/`, re-verified in under a second); `pack.sh` builds the archive and
validates it bank-for-bank against a 16-episode harness before anything ships.
Every seated artifact is hashed in the ledger, with a rollback chain kept on disk.

---

## Repository structure

```text
.
├── main.py                  competition entrypoint
├── kagfarm/
│   ├── policy.py            the agent: WorldState, zoo, selector, market/service planners
│   ├── route.py             worker scheduling (serpentine + deferred + reassignment)
│   ├── constants.py         object/crop/market tables, promotion-flag defaults
│   └── opening_book*.json   precomputed opening chains (shipped prior)
├── engine.py                local reimplementation of the competition rules
├── eval.py / sweep.py       local evaluation and parameter sweeps
├── bridge/real_env.py       evaluation through the vendored real engine (1.32.7)
├── analysis/                ~78 experiment harnesses (A/B panels, forensics, rollouts)
├── calibration/live.md      the measurement ledger: every sub, every gate, every number
├── tests/                   226 unit tests
├── docs/architecture.svg    the pipeline diagram
├── bundle.py                single-file submission bundling
└── pack.sh                  archive build + bank-for-bank validation
```

## Quick start

```bash
bash bootstrap.sh                                                    # venv + pinned deps
PYTHONHASHSEED=0 .venv/bin/python -m unittest discover -s tests -q  # 226 tests
PYTHONHASHSEED=0 PYTHON="$PWD/.venv/bin/python" SEEDS=8 bash pack.sh # build + validate
```

Local evaluation runs the agent against the vendored competition engine via
`bridge/real_env.py`; `analysis/` contains the battery harnesses
(`judge_bar.py`, `paired_harness_real.py`, `zoo_rollout.py`, …).

---

## What I learned

- **Good heuristics need adversarial measurement.** Strategies that looked obviously
  better lost when the opponent pool widened; the only defense is a battery you trust.
- **State representation is the leverage point.** The shared-forecast rewrite found
  real bugs (a silently inert mechanism shipped for two cycles; a day-0 falsy-value
  bug in the opponent calendar) that local reasoning had missed for weeks.
- **Optimization is always constrained.** The real question is never "what's the best
  action" but "best action subject to time, labor, cash, shed capacity and the
  opponent's next ten production waves."
- **Tooling is the deliverable.** Deterministic seeds, bank-for-bank pack checks,
  a written ledger with regression rows — that's what makes 30+ submission cycles
  iterable without re-learning the same lessons.
- **Robustness beats a fragile trick.** A mechanism that wins one matchup and loses
  another is worth less than a W/L-neutral one that removes a failure mode.

## Future work

- Runtime promotion of the zoo: the selector machinery is shipped flag-dormant;
  the E0-vs-E7 conditional panel on the elite/wall tiers decides whether it arms.
- 24/48/96-turn terminal-value rollouts over the shared WorldState.
- Richer opponent phenotype posteriors (revenue-by-product telemetry is already wired).
- Self-play opponent pools for automated strategy discovery.

## Notes

Some competition assets are intentionally not committed (they originate from
Kaggle's engine or are multi-GB replay datasets); `bootstrap.sh` re-vendors the
engine, and `analysis/restore_replays.py` re-fetches replays. See
[FREEZE_CHECKLIST.md](FREEZE_CHECKLIST.md) and `calibration/` for the details.

## Competition

[Kaggriculture on Kaggle](https://www.kaggle.com/competitions/kaggriculture) —
build an autonomous agent that manages a farm and out-earns a rival agent in a
dynamic simulated economy.

---

<div align="center">

**Observe. Model. Decide. Execute. Measure. Improve.**

</div>
