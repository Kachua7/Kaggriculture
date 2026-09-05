# Kaggriculture local simulator

An independent, runnable reimplementation of the Kaggriculture rules, built
from your knowledge-transfer doc. **This is not the official
`kaggle-environments` package** — that's a live, gated Kaggle competition
environment I can't install/verify from this sandbox. This is a model of the
*documented rules* so you can play with the problem, test strategies, and
build intuition before (or alongside) working against the real engine.

## Files

- `engine.py` — the game engine: board/shed/labor, crop & animal biology,
  the dynamic market price curve, and town demand. `KaggricultureEnv`.
- `agents.py` — sample agents: `pass`, `random`, `starter` (a direct port of
  the official wheat-loop sketch in your doc), and `heuristic` (a slightly
  smarter wheat farmer that hires hands and manages a sell buffer).
- `run_demo.py` — CLI to run one episode between two agents, print progress,
  and optionally plot bank balance over time or dump a full replay to JSON.

## Quick start

```bash
pip install matplotlib   # only needed for --plot
python run_demo.py --p0 heuristic --p1 starter --steps 720 --seed 1 --plot money.png
```

Use your own agent by writing a Python file with an `agent(obs)` function and
passing `--p0 mymodule:agent` (the module must be importable, i.e. on your
`PYTHONPATH` / in the same folder).

Programmatic use:

```python
from engine import KaggricultureEnv
from agents import agent_heuristic, agent_starter

env = KaggricultureEnv(episode_steps=720, seed=42)
env.run([agent_heuristic, agent_starter])
print(env.farms[0].money, env.farms[1].money)
```

`env.history` after `.run()` holds the observation dict for both players at
every turn if you want to inspect state or build your own charts.

## What's verified against the doc

- **Market price curve** — `price_for()` reproduces every value in the
  official price-curve table (Section 11.2) exactly: `P(I0−T)`, `P(I0+T)`,
  `P(I0+2T)` for all 9 resources, using the stated `sqrt / sq / log / log10 /
  hinge / linear` curves and the `amp = target·base / f(T)` formula.
- **Fibonacci hire cost**, resetting each dawn: 1,1,2,3,5,8,13,21,34,55,…
- **Watering/feeding death rules**: a plant with `consecutive_unwatered ≥ 2`
  becomes a weed; a planted-but-unwatered-same-day crop dies with no grace
  period; an animal unfed two days running escapes.
- **Shed cap (100 non-seed items, uncapped seeds)**, overflow discarded on
  `DROP`/`PLACE`/end-of-day dump.
- **Town demand**: town center drains 1 of every non-fertilizer product every
  24 turns; shops unlock every 3 days (capped at 8, drawn with replacement)
  and drain their basket every 4 turns, single-product shops at 2×.
- **Order clearing**: `SELL`/`BUY_PRODUCT` on the same resource are settled
  unit-by-unit, alternating between players, with price recomputed after each
  unit — matching the doc's "both players get the same price for their first
  unit" example, and the $1-floor units still get bought but don't add to
  market inventory.

## Where I had to make a judgment call

The doc is precise about *rules* but doesn't give the exact internal formula
for day-by-day crop/animal yield growth (it gives the *shape* of the rule in
prose plus a few numeric checkpoints: bonus window start, max yield, etc.).
My implementation:

- **One-time crops** (wheat/carrot/melon): gain +1 yield unit (or +2 if
  fertilized) on every watered day from `first_yield_day` through
  `max_yield_day` inclusive, capped at the unfertilized/fertilized max. After
  `max_yield_day`, an unharvested crop decays 1 unit every other day and
  turns to weed shortly after hitting zero.
- **Ongoing crops** (tomato/strawberry): gain +1 (or +2 fertilized) on each of
  the doc's explicit scheduled days (e.g. tomato: 8, 9, 10, 11), capped at
  `max_yield`; after the 4th scheduled day the plant decays the same way.
- **Animals**: `CARE`/fertilizer/production-bank logic follows the doc's
  4-step description in Section 9.5 literally.

If you can pull real episode replays (the doc points at community datasets —
`kaggriculture-episodes`, `kaggriculture-engine-reference-tables`,
`500+-match-replay-corpus`), the highest-value next step is diffing this
engine's per-turn `yield_units` against real replays and tightening these
growth formulas — everything else (market, town, shed, hiring, movement) is
either exact from the spec or mechanically unambiguous.

## Extending it

- Swap in your own agent and run it against `heuristic` to sanity-check
  strategy ideas (land-expansion timing, when to switch off wheat into
  premium goods, hand-count vs. Fibonacci cost tradeoffs, etc.) before
  burning a real Kaggle submission slot.
- `run_demo.py --dump-replay replay.json` gives you the full turn-by-turn
  state to build your own analysis notebook.
- The market, shop, and object tables are plain dicts at the top of
  `engine.py` — easy to tweak for "what if" experiments (e.g. testing how
  sensitive a strategy is to the melon glut curve).
