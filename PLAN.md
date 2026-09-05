# Kaggriculture — build plan

Written 5 Sep 2026. Entry deadline **23 Sep 2026** — 18 days.
Target: top of the Kaggle ladder, with a presentable demo layer that doubles as debugging tooling.

---

## 1. Where we actually stand

| Thing | Status |
|---|---|
| Knowledge transfer doc | Complete and trustworthy (`Kaggriculture_FINAL_KT.md`) |
| `kagfarm/` v1 agent (17 tests passing) | **Gone.** Lived in a sandbox that reset. Rebuild from the doc. |
| Local mirror simulator (`engine.py`, 801 lines) | **Survives, works, and is now partly calibrated** (§5.1). Runs a full 720-turn episode in a few seconds. |
| Economics | **Measured**, not assumed — `analysis/econ_probe.py`, `analysis/portfolio.py`, `calibration/mirror_truth.py`. See §2. |
| Sample agents (`agents.py`) | Toy level. `heuristic` ends the season on **$5,825** from a $3,000 start. |
| Real `kaggle-environments` engine | Not installed anywhere. Cannot be reached from my sandbox (PyPI and GitHub are both egress-blocked). |
| Git | Initialised, one commit (`ae2a211`). Commits go through `bash snapshot.sh "<msg>"` — see §7. |

Two consequences that shape everything below:

1. **The mirror sim is the iteration loop, not the real engine.** I can run thousands of
   episodes against `engine.py` at high speed. That is how knobs get tuned — you cannot
   tune 15 parameters through a Kaggle submission queue. The real engine's role is
   *periodic validation*, and it has to run on your machine, not mine.
2. **The mirror is uncalibrated in exactly the places that matter most.** Its market
   curve reproduces the official 4-point price table exactly, but each good's curve shape
   was *solved* from those four points, and its crop yield rules were inferred from prose.
   §5 splits this into what is now settled and what is still open. The two open items carry
   $67k of an $85k modelled revenue between them — so calibration is Phase 0, not an
   afterthought.

---

## 2. What the numbers say the strategy has to be

Everything in this section is *measured* by driving `engine.py`, not derived on paper
(`analysis/econ_probe.py` for the market and per-crop yields, `analysis/portfolio.py` for
the season model). Three of the conclusions in the first draft of this plan were wrong,
and they were wrong in the same way — they treated the market as a fixed pool of demand.
The corrected picture is in §2.1, and it inverts the sell timing.

### 2.1 The town is a price *pump*, not a sink

The shops buy their basket every 4 turns whether or not anyone sells, and shops unlock one
per 3 days up to 8. That drain is ~134 units/day across all goods at full ramp, and one
farm can supply only 14–28% of it. So inventory sits **below** the $I_0 = 10{,}000$
baseline all season and prices sit **above** base — the opposite of a glut. Confirmed on
the mirror by `idle_market_trace` (both agents pass for a whole episode): eight of nine
goods slope down and their prices slope up. Only fertilizer stays flat, because no shop
buys it.

`drain/d` is units removed per day at 8 shops; `idle $` is the price on the final day if
*nobody* ever sells that good; `cap solo` is how many units we can sell across the season
while holding marginal price ≥75% of base; `cap dual` is the same if the opponent matches
us unit for unit:

| Good | base | drain/d | idle $ | cap solo | rev solo | avg $ | cap dual |
|---|---|---|---|---|---|---|---|
| Wheat | 25 | 31.0 | $48 | 2,940 | $56,903 | 19.4 | 1,470 |
| Egg | 50 | 13.0 | $64 | 1,647 | $64,385 | 39.1 | 824 |
| **Strawberry** | 120 | 25.0 | **$293** | 437 | $40,838 | 93.5 | 219 |
| Carrot | 35 | 19.0 | $60 | 378 | $10,338 | 27.3 | 189 |
| Milk | 160 | 19.0 | $317 | 343 | $42,154 | 122.9 | 172 |
| Tomato | 60 | 13.0 | $91 | 263 | $12,017 | 45.7 | 132 |
| Wool | 200 | 13.0 | $247 | 255 | $39,813 | 156.1 | 128 |
| **Melon** | 250 | **1.0** | $280 | 109 | $23,781 | 218.2 | 55 |

Note what `idle $` does to the old story: strawberry ends the season at **$293 against a
$120 base** if left alone, milk at $317 against $160, wheat at $48 against $25. Scarcity,
not glut, is the equilibrium.

### 2.1a But the `drain/d` column above is an average of a lottery

Shops are drawn **with replacement** from the eight types, one every three days. So which
goods get demand is a per-episode dice roll, and the mean basket that produced `drain/d`
above never actually occurs. Counting baskets:

| Good | baskets buying it | P(zero shops all season) | season units absorbed (p10 / median / p90) |
|---|---|---|---|
| Wheat | 5/8 | 0.0% | 318 / 534 / 714 |
| **Strawberry** | 4/8 | 0.4% | 228 / **426** / 624 |
| Milk | 3/8 | 2.3% | 138 / 318 / 534 |
| Carrot | 2/8 | 10.0% | 66 / 318 / 624 |
| Tomato | 2/8 | 10.0% | 66 / 210 / 408 |
| Egg | 2/8 | 10.0% | 66 / 210 / 408 |
| **Wool** | 1/8 | **34.4%** | 30 / 210 / 498 |
| **Melon** | 0/8 | 100% | **30 / 30 / 30** |

Three consequences, each of which changed a decision:

1. **Wheat and strawberry are the only reliable demand.** Wool has a 34% chance of draining
   30 units for the entire season, which makes sheep dead weight in a third of episodes.
   Carrot, tomato and egg are 10% each. So livestock and the minor crops are
   *draw-conditional* lines, and the agent must read the unlocked-shop list from day 3
   before committing tiles or barn money to them.
2. **Melon's price-neutral demand is exactly 30 units a season, every episode, shared with
   the opponent.** Roughly four tiles fill it. Everything past that is deliberate flooding
   — which still pays, at $218/unit average down to 75% of base, but it is the contested
   line and the opponent's melon is subtracted from ours (§2.3).
3. **At the sustainable rate the market is not the binding constraint at all — production
   is.** Median absorbable flow across all goods is worth about **$199k** at base prices,
   against a modelled bank of $73k. Strawberry alone would need **106 tiles** of its own to
   fill its price-neutral demand, i.e. more than the whole board. So the portfolio is
   limited by tiles, labour-actions and the 100-item shed, not by market depth, and any
   argument of the form "we cannot sell that much" is wrong for every good except melon.

Mechanically this had been wrong in three places at once — `kagfarm/constants.py`,
`analysis/econ_probe.py` and `analysis/portfolio.py` each carried their own copy of the
mean-basket approximation. There is now one exact function,
`drain_per_day_from_shops(good, shops)`, plus `unlocked_shops_from_obs(obs)` to read the
list out of an observation; `expected_drain_per_day` survives only as the prior to use
before day 3, with a docstring saying so.

### 2.2 So "sell early" was backwards — for every drained good, later is dearer

The first draft said the book only degrades, so front-load. That is false for the eight
goods above except melon: every hour we wait, the town has removed more inventory and
raised the price. What actually caps hoarding is not price risk, it is the **100-item
shed**, which silently discards overflow at midnight. That gives the real rule:

- Sell down to empty every day, because tomorrow's harvest needs the space, and an item
  we refuse to sell is an item we are about to destroy.
- Do *not* set a reserve price as a fraction of base (§2.4).
- The endgame liquidation ramp survives, but for a different reason: unsold stock scores
  zero, not because prices are about to collapse.
- The one thing that inverts this is an opponent who is also selling. The town's pump is
  slow (a few dozen units a day); a determined opponent can add hundreds. Against that,
  waiting is how you get front-run. See §2.3 and the Phase 5 estimator.


### 2.3 Melon is the one exception, and it is the whole competitive story

Melon appears in **no shop basket** — its only drain is 1/day from the town centre. So
nothing regenerates a melon price once it is pushed down, and its `sq` above-curve reaches
the $1 floor about 158 units above $I_0$. The entire melon market is worth roughly **$26k
for the whole game, shared between both players, and it goes to whoever sells first.**

Measured against an opponent dumping melon into the same book (fixed 100-tile mix):

| Opponent melon/day | Our bank | vs solo |
|---|---|---|
| 0 | $71,829 | — |
| 2 | $62,204 | **−$9,625** |
| 5 | $53,955 | −$17,874 |
| 10 | $21,851 | −$49,978 |
| 20 | $11,393 | −$60,436 |

An opponent selling **two melons a day** costs us ten thousand dollars. This is the only
good where being second is catastrophic, and the only place opponent modelling pays.
Operationally: melon goes on the book the instant it is harvested, never held.

### 2.4 Never hold a reserve price — the shed couples every good together

The shed is *one* 100-item pool, so refusing to sell a crashed good starves every other
good of space, and the overflow destroys incoming harvests. That converts a price
disagreement into a production collapse. Reserve price × opponent pressure, allocation held
fixed at the §2.8 optimum, panel mean over six shop draws. The opponent rate is units/day
of *each* of the five crops, so 5 means 25 units/day:

| Opponent units/day/crop | reserve 0.00 | 0.25 | 0.50 | 0.75 | 0.90 | 1.00 |
|---|---|---|---|---|---|---|
| 0 | **$74,701** | $74,701 | $74,157 | $73,082 | $71,087 | $62,796 |
| 2 | **$60,594** | $50,897 | $50,124 | $47,680 | $44,394 | $40,076 |
| 5 | **$44,665** | $29,714 | $28,258 | $21,250 | $19,393 | $20,199 |
| 10 | $6,520 | $9,297 | $5,708 | $9,115 | **$9,350** | $9,009 |
| 25 | **$1,485** | $1,416 | $856 | $732 | $353 | $353 |

Reserve 0 — sell everything, every tick, highest marginal price first — wins or ties at
every pressure level except one, and is up to **$23k better** under attack. The single
exception is 10 units/day/crop, where reserve 0.90 is $2,830 ahead inside a market that has
already collapsed 87% from solo; at that point every policy has lost and the ranking is
noise. The simplest policy is also the strongest one.

Worth noting what this table says beyond the reserve question: **an opponent selling two
units a day of each crop costs us $14k, and five costs us $30k.** The pump in §2.1 is a few
dozen units a day; an opponent is not rate-limited that way. Any plan that banks on
scarcity pricing is implicitly assuming the opponent leaves it alone.

### 2.5 Labour is nearly free, so routing quality sets farm size

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
routing drives farm size. Instrumenting an episode (`analysis/verify_claims.py`) confirms
the headroom rather than assuming it: the current `heuristic` agent keeps a **mean of 11.4
tiles planted, peak 16, out of 100 reachable**, never buys land, and lets weeds accumulate
to 13 tiles by day 21 without ever digging them. That is **8.8× on tile count alone**.

One measured constraint the router has to respect: `PLANT` creates a tile with
`consecutive_unwatered = 1`, so **a plant that is not watered on the day it goes in dies at
that midnight**. Planting and watering are one atomic job, not two independent ones.

### 2.6 Logistics are free if you exploit the midnight dump

Seeds live in an uncapped slot that `PLANT` draws from directly, and every unit's carried
inventory auto-dumps into the shed at midnight. So a unit never needs to walk to the shed
to plant or to deliver a harvest — only to collect fertilizer or wheat for feeding.

The binding logistics constraint is instead the **100-item shed cap**, since midnight
overflow is silently discarded. Sell the shed down to empty each day and you can absorb
~100 harvested items per night. Selling itself is nearly free: 10 orders per turn × 24
turns, and each order carries any quantity.

### 2.7 Per-crop yields, measured off the engine rather than from the formula

`calibration/mirror_truth.py` scripts a single tile through `engine.py` — buy seed, plant,
water every turn, `HARVEST` at hour 23 of day D — and reads the shed. So these are units
*banked*, not units on the tile. `slack_d` is how many extra days you can be late to the
harvest before losing a unit; `0` means the harvest turn is a hard deadline.

| Crop | seed | base | best day | units | cycle | $/tile-day | $/action | slack_d |
|---|---|---|---|---|---|---|---|---|
| **Melon** | 80 | 250 | 12 | 4 | 13 | **70.8** | **61.3** | 1 |
| Strawberry | 100 | 120 | 16 | 4 | 17 | 22.4 | 20.0 | **0** |
| Carrot | 20 | 35 | 3 | 3 | 4 | 21.2 | 14.2 | **0** |
| Wheat | 10 | 25 | 4 | 4 | 5 | 18.0 | 12.9 | 1 |
| Tomato | 50 | 60 | 11 | 4 | 12 | 15.8 | 13.6 | 2 |

Units banked by harvest day, which is what the planner actually needs:

```
WHEAT        d2=2  d3=3  d4=4  d5=4  d8=2  d10=1
CARROT       d2=2  d3=3  d4=2  d5=2  d8=0
MELON        d10=2 d11=3 d12=4 d13=4 d14=3 d16=2
TOMATO       d8=1  d10=3 d11=4 d12=4 d13=4 d14=3 d16=2
STRAWBERRY   d10=1 d11=1 d12=2 d13=2 d14=3 d16=4
```

Two rules fall straight out of this. **Carrot and strawberry have zero slack** — miss the
day and a unit is gone, so those tiles must be first in the dawn route, not last. And
**every crop decays after its peak**: a wheat tile left standing to day 10 banks 1 unit
instead of 4, so an unharvested ripe tile is an actively depreciating asset.

### 2.8 The season portfolio model

`analysis/portfolio.py` runs a day-by-day season under a target tile allocation and
enforces the five things that actually decide the score: cash flow from a $3,000 start
with land that must be *earned*, the 100-item shed with silent overflow, market flow with
shops ramping in, Fibonacci wages, and the 720-turn horizon. Allocation is searched by
random restarts plus unit-step local ascent. Every season is now run against a **fixed
panel of six shop draws** and the objective is the panel mean, because §2.1a showed the
mean basket is not a draw that ever happens; `worst` is the weakest of the six, so a mix
that only wins on lucky carrot demand is visible rather than hidden in an average.

| Tile budget | Bank | Worst draw | Revenue | Seeds | Land | Wages | Hands | Best mix |
|---|---|---|---|---|---|---|---|---|
| 25 | $31,314 | $29,934 | $31,365 | $3,020 | $0 | $31 | 2 | mel 10, str 7, whe 4, car 2, tom 2 |
| 50 | $46,844 | $44,997 | $50,353 | $5,428 | $1,000 | $81 | 4 | mel 19, str 13, whe 8, tom 5, car 5 |
| 75 | $61,821 | $56,817 | $68,709 | $6,720 | $3,000 | $168 | 6 | str 26, mel 16, tom 15, whe 13, car 5 |
| **100** | **$73,082** | $66,891 | $86,377 | $8,838 | $7,000 | $457 | 8 | str 35, whe 25, mel 19, tom 11, car 10 |

Making the drain exact moved the 100-tile optimum by 14 tiles: **tomato fell 25 → 11 and
wheat rose 14 → 25.** That is the mean-basket error unwinding in exactly the direction
§2.1a predicts — tomato is 2 baskets in 8 and was being credited with demand it usually
does not get, wheat is 5 in 8 and is the one line that never fails to clear.

Where the money comes from at 100 tiles — note the realized price column, which is the
§2.1 pump showing up as revenue:

| Good | sold | revenue | avg $ | base | % of base |
|---|---|---|---|---|---|
| **Strawberry** | 140 | **$36,310** | 259.4 | 120 | **216%** |
| Melon | 152 | $31,240 | 205.5 | 250 | 82% |
| Wheat | 260 | $9,540 | 36.7 | 25 | 147% |
| Carrot | 126 | $5,026 | 40.0 | 35 | 114% |
| Tomato | 52 | $4,262 | 82.0 | 60 | 137% |

**Strawberry is the largest revenue line in the game, and the first draft of this plan
dismissed it as "thin."** The reason is §2.1: the town eats ~25 strawberries a day while
one tile produces 4 units in the *entire season* (17-day cycle, one cycle fits). It is
structurally under-supplied, so it clears at more than double base. §2.1a sharpens this —
it would take 106 tiles of strawberry to saturate its own demand, so strawberry is never
the thing to cut.

Melon is the mirror image: 152 units sold against 30 units of price-neutral demand, which
is why it is the only line clearing *below* base (82%). It is still worth 19 tiles because
$205/unit on a $80 seed beats everything else per tile-day — but every one of those units
is contested, and re-optimising against an opponent dumping 10 melons/day moves 11 tiles
out of melon into strawberry and carrot. Melon allocation is **opponent-dependent**, which
is the Phase 5 hook.

Two reasons to treat $73k as a floor rather than a ceiling: the model leaves tiles idle
late in the season instead of backfilling a finished strawberry tile with a 4-day carrot,
and it ignores livestock entirely (milk idles at $317 against a $160 base). One reason to
treat it as optimistic: it faces no opponent at all, and §2.3's pressure table is steep.

### 2.9 The number to beat

| Scenario | Terminal bank |
|---|---|
| Current `heuristic` in the mirror | $5,825 |
| Portfolio model, 100 tiles, opponent selling 5/day of each crop | ~$45k |
| Portfolio model, 100 tiles, opponent selling 2/day of each crop | ~$61k |
| Portfolio model, 100 tiles, solo seller, no reserve | ~$75k |

That is more than an order of magnitude of headroom, and it is bounded by *routing* — the
model assumes we can service every planted tile every day, which is exactly the §2.5
claim. Treat **$35k in the mirror as the Phase 4 gate** and the ladder as the referee.


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
because of §2.5.

---

## 4. Schedule

Eighteen days. Each phase ends in something submittable, because a phase that cannot be
submitted cannot be measured.

### Phase 0 — Ground truth (5–6 Sep)

The only phase that requires your machine rather than mine. Mirror side is done; the
real-engine diff is what remains.

- ~~`git init`, commit what exists, add `.gitignore`.~~ Done (`ae2a211`). Note: I cannot
  delete `.git/index.lock`, so commits go through `bash snapshot.sh "<msg>"` on your side.
- ~~Build a mirror-side probe emitting the same JSON shape as the real-engine dump, so
  calibration is a mechanical diff.~~ Done — `calibration/mirror_truth.py` → `mirror.json`.
- ~~Resolve the yield-growth divergences.~~ Three fixes applied to `engine.py` and verified:
  one_time crops are planted with `yield_units = 1` (wheat *and* carrot *and* melon — with
  start=0 both wheat and carrot land exactly one short of their documented caps, and the
  same off-by-one on two crops is a start value, not a coincidence); melon
  `max_yield_day = 12`; and `HARVEST` is a **no-op before `first_yield_day`**, without which
  `start_yield=1` would let a melon be planted and harvested the same day for $250 against
  an $80 seed, on every tile, every day. Five of six documented caps now land exactly.
- Fix `calibration/dump_truth.py` to water **every turn**, not just at hour 1. Its current
  schedule leaves the plant unwatered on its planting day, which kills every probe plant at
  the first midnight — it did exactly that on the mirror and produced an all-zeros trace.
  Also port the `rule_checks` probes across. **Do this before you run `calibrate.sh`.**
- `pip install -U kaggle-environments` on the Mac (`bash bootstrap.sh`), then
  `bash calibrate.sh` → `calibration/truth.json`; then `diff_truth.py`.
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

Rewritten around §2.2–2.4. The old design here — a reserve price as a fraction of base,
decaying over the season — is **measurably worse than selling everything** and is dropped.

- Default policy: every tick, sell the good with the highest *marginal* price, repeat until
  the shed is empty. No reserve. §2.4 has the numbers; the shed being one shared pool is
  why a per-good reserve backfires.
- Melon is special-cased in the other direction: sell on harvest, same turn, always. Its
  book does not regenerate, so held melon is melon the opponent gets to sell instead (§2.3).
- The only case for *holding* is shed pressure being low and tomorrow's harvest being
  small, which is rare enough that it is a knob to sweep, not a design centre.
- Endgame liquidation ramp over the last 24–48 turns — still needed, but because unsold
  stock scores zero, not because prices are about to fall.
- Buy back wheat for feed when it is cheap; the `log` curve makes this viable.

**Exit:** zero items lost to shed overflow across the seed set, and realized price ≥100% of
base on strawberry/wheat/carrot/tomato (§2.1 says the pump makes that the *floor*, so
missing it means the seller is broken, not the market).

### Phase 4 — Crop portfolio and livestock (13–17 Sep)

Seed the search from the §2.8 optimum rather than from nothing: `str 35, tom 25, mel 19,
whe 14, car 7` at 100 tiles, and `str 42, tom 20, whe 16, car 14, mel 8` under melon
pressure. Melon allocation is opponent-dependent, so it is a Phase 5 input, not a constant.

- Land on the schedule the model says pays: buy a quadrant only when the tile target
  exceeds what is unlocked **and** the bank still covers seeding it. Buying greedily on day
  0 spends the entire $3,000 stake on dirt and the season never starts.
- Backfill finished long-cycle tiles with short-cycle crops (carrot 4d, wheat 5d) instead of
  leaving them idle — the model does not do this, which is why $71.7k is a floor.
- Then livestock, sized to town drain: milk idles at $317 against a $160 base, wool $247
  against $200, and eggs are effectively bottomless filler.
- Sweep: coordinate descent over the knobs first, then CMA-ES over the survivors, against
  an opponent pool that includes frozen earlier versions of ourselves.

**Exit:** ≥$35k in the mirror; ladder rank trending up across submissions.

### Phase 5 — Opponent awareness (16–20 Sep)

- Estimate the opponent's per-good sell rate from market inventory deltas, which are
  public. Inventory falls on its own from the town drain, so the estimator has to subtract
  the expected drain (which depends on the shop-unlock count) before attributing the rest.
- Melon is the only good where this pays, and it pays enormously: two opponent melons a day
  costs us ~$10k (§2.3). Detect it early, dump our melon book ahead of theirs, and shift
  tiles into strawberry.
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

Ranked by how much of the §2.8 modelled bank rides on the answer.

### 5.1 Resolved on the mirror side

| Question | Answer | Evidence |
|---|---|---|
| Melon `max_yield_day` | **12**, not 10 | KT doc states it as engine truth; mirror contradicted it. Was worth 3× on melon. |
| Do one_time crops start at `yield_units = 1`? | **Yes — wheat, carrot and melon** | With start=0, wheat tops out at 3 against a documented cap of 4 and carrot at 2 against 3. The same off-by-one on two different crops is a start value. With start=1, five of six documented caps land exactly. |
| Is `HARVEST` a no-op before `first_yield_day`? | **Must be** | Otherwise `start_yield=1` makes plant-then-harvest turn an $80 melon seed into $250 on the same tile-day, repeatable everywhere. Probe: `early_harvest_exploit`. |
| Does a plant left unwatered on its planting day survive? | **No** | `PLANT` sets `consecutive_unwatered = 1`. Hard routing constraint (§2.5). |

### 5.2 Still open, and what they cost

| # | Question | Mirror says | Money at stake |
|---|---|---|---|
| 1 | Melon's **above**-curve params (`sq`, target 3.60, `T`=300) | fitted to 4 checkpoints | Sets the size of the melon pot (~$26k) and where the $1 floor lands. $31k of modelled revenue. |
| 2 | Strawberry's **below**-curve params (`sqrt`, target 0.70, `T`=100) | fitted to 4 checkpoints | Sets the 217%-of-base premium that makes strawberry the top revenue line. $36k of modelled revenue. |
| 3 | Melon `max_yield_unfert` | 6 (copied from `max_yield`; the growth rule actually gives 4) | ±50% on the melon programme. The doc lists no separate unfertilised value for melon, so this is the one cap of six that does not land — most likely a mirror artefact. |
| 4 | Every other good's `T` and target | fitted, not read | Sell sizing across the board. Right at the checkpoints, unknown between them. |
| 5 | Shop unlock cadence and basket draw | 1 per 3 days, cap 8, **uniform draw with replacement** | Sets which goods have demand at all. Under the mirror's rule, wool gets no shop in 34% of episodes and carrot/tomato/egg in 10% (§2.1a). If the real engine instead draws *without* replacement, or unlocks a fixed sequence, then every good gets demand every episode and the draw-conditional logic below is dead weight. Confirmed on the mirror by `idle_market_trace`; needs the real engine to confirm the *rule*, not just the shape. |
| 5a | Does the observation expose the unlocked-shop list? | mirror puts it at `obs["town"]["unlocked_shops"]` | If the real obs hides it, the agent cannot compute exact per-good drain and must infer it from inventory deltas instead — which pulls the Phase 5 estimator forward into Phase 3. `unlocked_shops_from_obs` already tries the plausible field names and degrades to town-centre-only, so this fails safe rather than crashing. |
| 6 | Do animals eat wheat, 1/day? | assumed yes | Livestock viability, which is all of Phase 4's second half. Note §2.1a: sheep are also hostage to the yarn-store draw, so this is not the only thing that decides them. |
| 7 | Post-peak decay of unharvested crops | 1 unit every other day, then weed | Harvest deadlines and route priority (§2.7). |
| 8 | Watering bonus window | folded into growth | `[(max+1)//2, max]` applied at WATER time per the doc. Up to +2/tile. |

Items 1 and 2 are the priority because $67k of an $85k modelled revenue rests on two curve
shapes that were solved from four data points each. Everything downstream — the tile mix,
the melon urgency, the strawberry weighting — is conditional on them.

Item 5 was promoted after the drain was made exact: it does not move a price, it decides
which goods have a market at all in a given episode, and it turned out to be worth 14 tiles
of the 100-tile optimum (§2.8).


---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| **1s act timeout** — a single slow turn forfeits the episode | Hard wall-clock budget in `agent.py`, cached-plan fallback, and a harness metric that counts turns over budget |
| Mirror diverges from the real engine, so we tune for the wrong game | Phase 0 calibration; re-diff after any real-engine run; never let a knob be tuned on an uncalibrated rule |
| **Two curve shapes carry $67k of modelled revenue** (§5.2 items 1–2) and were each solved from four points | Highest-priority items in the real-engine diff. Until they are confirmed, treat the tile mix as provisional and keep the sell policy shape-independent — "sell everything, dearest first" needs no curve knowledge, which is a second reason to prefer it |
| **An opponent who dumps melon erases ~$50k** | Detect from public inventory deltas (Phase 5), sell melon on harvest with no holding (Phase 3), and keep a strawberry-weighted fallback allocation ready |
| **The shop draw is a lottery, so a mix tuned on the average basket is tuned on a draw that never happens** (§2.1a) — the mean basket gives wool 13 units/day where 34% of episodes give it 1, and carrot 2.4× its median | `portfolio.py` optimises the mean over a fixed 6-draw panel and reports the worst draw alongside it, so a mix that only wins on lucky carrot demand loses the search. At runtime the agent reads `unlocked_shops_from_obs` from day 3 and sizes the draw-conditional lines then, instead of committing tiles at dawn. Wheat/strawberry/melon are draw-independent enough to commit early; wool and the minor crops are not |
| `hands` list length must exactly equal `len(hands)` | Enforced in `actions.emit_all`, asserted in tests |
| Shed overflow silently destroys harvested value | Explicit metric with a zero-tolerance Phase 3 exit gate; sell to empty every tick |
| Overfitting to `heuristic` as the only opponent | Self-play pool of frozen prior builds from Phase 4 on |
| Submission queue is the bottleneck for ladder convergence | Submit from end of Phase 1, daily thereafter |
| One clever change breaks everything two days before the deadline | Freeze a known-good build 48h out; regression gate on every merge |

---

## 7. Division of labour

You are building this through me, so I own all of it — code, simulation, tuning, analysis.
These are the only things the sandbox physically prevents me from doing:

| Only you can do | Why | Effort |
|---|---|---|
| Run `bash bootstrap.sh` once | My VM has no PyPI or GitHub egress, so `kaggle-environments` can only be installed on your Mac. The script installs it, dumps the real engine's constants and a validation trace to `calibration/`, and I read those files straight out of this folder. | One command |
| Run `bash calibrate.sh` after that | Produces `calibration/truth.json`, the other half of the §5 diff. | One command |
| Accept the competition rules in the browser | Kaggle gates submission behind a click-through. | One click |
| Run `bash submit.sh "<message>"` | Needs your Kaggle credentials. | One command per submission |
| Run `bash snapshot.sh "<msg>"` to commit | Git leaves a `.git/index.lock` behind and my sandbox is not permitted to delete files in this folder, so git jams after one operation on my side. Granting delete permission for this folder would fix it permanently and remove this row. | One command per checkpoint |

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


