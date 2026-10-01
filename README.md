# Kaggriculture — competitive agent (`kagfarm`)

A bot for the Kaggle **Kaggriculture** competition: farm a shared board over a 30-day
season against one opponent, monetize crops and livestock through a dynamic shared
market, and finish with more terminal cash than the rival. This repo contains the
agent that reached the **sub31** ship state (~$100k+ typical finals against the
embedded judge panel) plus the Sub32 decision layer (runtime strategy selector,
canonical world state, shared forecasts, market-slot optimizer).

## What's here

```
main.py                  competition entrypoint (tar this with kagfarm/ to submit)
kagfarm/
  policy.py              ~7,400 lines: the agent — opening book prior, economy model,
                         strategy zoo, runtime selector, market/service planners
  route.py               worker scheduling (serpentine + deferred + global reassignment)
  constants.py           OBJECT_TABLE / CROP_PLAN / MARKET_PARAMS / MAX_MARKET_ORDERS
  opening_book.json      per-donor opening chains (20K, shipped in the tar)
  opening_book_elite.json  1.4M elite-tape book (dev-time matching substrate)
engine.py                local reimplementation of the competition rules
eval.py / sweep.py       local evaluation + parameter sweeps
bridge/real_env.py       runs the vendored real engine (kaggle-environments 1.32.7)
pack.sh                  builds submission.tar.gz (bank-for-bank 16/16 pack check)
bundle.py                regenerates the single-file submission/main.py build
tests/                   226 unit tests (PYTHONHASHSEED=0)
analysis/                every measured experiment this season (~90 harnesses)
calibration/live.md      the measurement ledger: every sub, every gate, every number
```

## Quick start

```bash
bash bootstrap.sh                     # venv + pinned deps (kaggle-environments 1.32.7)
PYTHONHASHSEED=0 .venv/bin/python -m unittest discover -s tests -q   # 226/226
PYTHONHASHSEED=0 PYTHON="$PWD/.venv/bin/python" SEEDS=8 bash pack.sh # build + 16/16 pack check
```

Run a local mirror game (`analysis/` has the battery harnesses; every battery is run
against the vendored real engine via `bridge/real_env.py`).

## Architecture in one paragraph

Public episode state → **WorldState** (one canonical snapshot: cash, roster,
positions, shed, market, own/opponent future supply, service load and slack) →
**opponent phenotype** posterior → **strategy zoo** (E0 elite prior … E8 liquidity,
each a parameter overlay on the shared executor) → **runtime selector** (commits one
expert per macro window at d0/3/6/9/12/16/20/24, or mid-window on danger triggers:
service deficit, herd collapse, price shock) → task planner → serpentine +
global-reassignment scheduler → market-slot optimizer (max Σ ΔV·x s.t. ≤10 orders,
sells floored) → deterministic executor. Everything measurable is flag-gated in
`PARAMS` with shipped defaults recorded in `calibration/live.md`; dormant
mechanisms ride along inert until a real-tier battery promotes them.

## Measurement discipline

- All gates run on the **real engine** (vendored 1.32.7 via `bridge/real_env.py`),
  `PYTHONHASHSEED=0`, mirror seeds 0/2/7 checked for escapes and zero fallback errors.
- Judge tiers: elite / famine / midfield / wall — identified opponent seatings
  (`analysis/judge_bar.py --tier … --opps …`).
- W/L is the promotion metric; margin is a tiebreaker. The ledger records regressions
  instead of hiding them.

## Notes

- `calibration/engine*/` content is pinned by `MANIFEST.sha256` and intentionally not
  committed (Kaggle's code, not ours) — `bootstrap.sh` re-vendors it.
- Replay datasets (`*games/`) are Kaggle's and multi-GB; `analysis/restore_replays.py`
  re-fetches them. They are gitignored.
