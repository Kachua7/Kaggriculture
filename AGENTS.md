# AGENTS.md — Kaggriculture

Session learnings that cannot be recovered by reading the code.

## Workspace

- The tool's default workspace root is an UNRELATED project (Virasat/BitKosh). Every
  Kaggriculture command must `cd "/Users/pranjalmorwal/Desktop/kaggriculture 2"` first —
  the checkout was renamed 2026-09-20 and the path has a SPACE, so always quote it
  (a typo'd root like "kaggressive 2" fails silently when the command ends in `2>/dev/null`);
  read/list tools accept that absolute path directly.
- This is the user's shared local checkout. Build artifacts `submission.tar.gz` and
  `submission/` are gitignored; `analysis/*.json` probe outputs are NOT ignored (only
  untracked), so a `git add -A` / `snapshot.sh` will sweep them in — regenerate them but
  don't commit them unless intended.

## Calibration & ladder state (operational facts, not in code)

- Bootstrap has NOW run (12 Sep): `.venv` is python3.13 (the 1.32.7 wheel needs >=3.11;
  system python3 is 3.9), pinned `kaggle-environments==1.32.7`, engine vendored+hashed at
  `calibration/engine/MANIFEST.sha256`. Ground truth is the GOLDEN CHECK
  (`calibration/verify_replay.py`: vendored interpreter replays the tutorial episode
  719/719 steps exact), not `calibrate.sh` traces. `calibration/engine-1.32.2/` exists only
  to re-simulate that replay — it was recorded on 1.32.2.
- Zero ladder submissions still. Submission is user-only: accept rules in the browser, then
  `bash submit.sh "msg"`. Submit early and daily — the pairwise rating needs episode volume.
- FIELD INTEL (public leaderboard CSV, 16 Sep): 9,258 teams; the official baseline agent
  sits at 2795.7 / rank 169; top 3188.5, median 786.5; 8,339 teams have exactly 2
  submissions (baseline + one edit, most likely) and 1,543 last submitted on the 16th.
  Score is a SKILL RATING (not bank dollars). ~168 teams already beat the baseline. Every
  day unsubmitted is lost rating volume against the 23 Sep entry deadline.
- REAL-TIER commands: `.venv/bin/python eval.py --engine real`, `sweep.py --engine real`,
  `calibration/a3_compare.py` (the 32-seed gate), `calibration/diff_source.py` (mechanical
  mirror-vs-wheel table; final verdict DIVERGE=0/NEW=0 — run under .venv), `calibration/fingerprint.py <replay.json>`
  (dates any replay). Real tier is in-process, ~8 eps/s, no pool.
- Livestock probes (2026-09-20): `analysis/animal_funnel.py [seed]` traces the BUY->PLACE->
  FEED->escape funnel by monkey-patching `env._refresh_animal`; `ANIMAL_ARM=shepherd8|shepherd20|b|c`
  injects that arm's params. Real-tier arm A/B: `analysis/ab_shepherd.py --arm a|s8|s20`.

## Execution paths that differ from how the code reads

- At hour 0 of every day `farms[i]["hands"]` is EMPTY: hands are hired during hours 0-4
  (`PARAMS hire_hours=4`) and vanish at midnight. A dawn-sampling trace showing hands=0 means
  "not hired yet", not "no hands hired".
- In eval.py metrics, `thirst` counts only plants killed by two dry nights; plants that finished
  their schedule and decayed are `spent`. Summing the two once falsely read as a labour bug.
- Every PLANT job carries a next-turn WATER (`then=["WATER"]`, `acts=2`), and zero plants died
  on their planting day across ~1,600 measured plantings. That is empirical, not structural:
  a wasted turn (seedless-PLANT/PICKUP waits and empty-queue PASSes exist in `_unit_ops`) can
  slide a run's tail PLANT to hour 23, whose WATER then lands after midnight refresh
  (consecutive_unwatered 1 -> 2 = weed). No explicit guard; routing changes must respect it.
- `route.capacity()` returns TILE-VISITS (op + its walk ≈ 2 turns each); chore-loop budgets in
  policy.py count RAW TURNS. Comparing a loop budget against `share * capacity()` is a silent 2x
  error — any co-feasibility gate must multiply capacity by 2 (the live=4 herd-freeze bug).
- The executor runs a unit's queue until the day runs out, so overflow cuts the TAIL. In
  nearest-chain order the tail held the farthest animals' feeds — queues whose jobs have unequal
  consequence must be ordered by consequence first (feeds-first), never by geography alone.
- `endgame_days` opens at d25 but a live herd eats through d29: `_sell_orders`' endgame branch and
  the herd's feed hold interact through the shed WHEAT pool. While mouths stand, the buffer must
  ride through endgame (the `herd_endgame` override) or the herd starves at d27-28 with grain
  visibly in the shed — working capital, not inventory.

## Engine-version ledger (12 Sep) — read before touching constants

- The tutorial replay is **1.32.2 mechanics** (fingerprint re-simulation proves it). The
  mirror's old `[real]` tags were true *for 1.32.2*: tau=12 (2/day town centre), staged
  centre schedule [(20,4),(10,2),(0,1)], shops WITHOUT replacement, log/linear below-curves
  for CARROT/TOMATO/EGG. **1.32.7 changed all four** (tau 24, schedule removed, WITH
  replacement, hinge below-curves) and also enforces shedCapacity on BUY. Constants are now
  tagged `[real:1.32.7]` and follow the pin; the FIRST ladder replay must be fingerprinted
  and, if it dates 1.32.2, constants re-tagged back (mechanical, ~30 min, then re-run the
  A3 gate). `max_yield_unfert` exists in NEITHER engine — it was a pure mirror invention,
  now dead data (`yield_cap` ignores it).
- A3 gate (32 seeds self, mirror vs real-1.32.7): mean +8.7%, p10 +$5,375, but **p10-set
  Jaccard 0.200** (lockout seeds reshuffle); win-rate vs starter 100% both. Verdict GO A5.
- A5 scoped sweep (real tier, holdout-gated): **no adoption** — tuning-panel win 70.8% was
  overfit; holdout shows every axis regressing or noise; two with-replacement `mix`
  candidates also rejected. v1 structure survives the pinned engine unchanged.

## Contested-market findings (measured)

- Self-vs-self (mutual adoption) is bimodal: mean ~$50k, but p10 ~$10-14k vs best ~$70k.
  `corr(mine, total) = +0.86` -> mostly a SEED (shop-draw) effect, not lost races.
- Bad-seed signature: ~105 strawberries sold at 2.15x base vs ~265 at 1.97x on good seeds —
  a VOLUME loss at a HIGHER price. The drain-floor fix for this (raise the lookahead's
  projected strawberry drain to the horizon-averaged expected drain) was implemented and
  MEASURED REJECTED 2026-09-08: p10 never moves at weights 0.25/0.5, weight 1.0 collapses the
  mean ($50.6k -> $36.7k, thirst 50 -> 72). The tail is NOT strawberry under-planting; it is a
  season-quality effect (early draw starves the cash crops -> smaller farm all season). The
  rejected machinery sits in policy.py with `drain_floor=0.0` and a full measured table; do
  not reopen without a mechanism that targets bad seeds specifically.
- The melon opening (24/25 tiles) is load-bearing: capping it costs ~$56k, and flooding
  dominates restraint in the 2x2. Axis closed — do not re-open.
- **Windfall cap ADOPTED 16 Sep** (`windfall_pct=0.45`, `windfall_reserve=0` in PARAMS):
  the day-11 melon windfall used to plant the whole 96-tile board against ~$0 cash; the
  wage bill then starved the roster, 70+ tiles died of thirst, and the farm stayed dead
  from day 17 (see `analysis/autopsy.py`). The dawn seed budget may now spend only 45% of
  the bank on any multi-quadrant dawn. Mutual meta (`--opps self_live`), both seed halves:
  mirror +$14-19k mean / +$22-27k p10 / +$16-19k min; REAL tier 48 seeds +$8.4k mean /
  +$26.3k p10 / +$18.4k min. Byte-identical vs the built-ins (their weak market never
  depresses our cash, so the cap never binds there — it is liquidity-proportional and
  self-targets contested seasons). Head-to-head cells over these axes ARE chaotic
  (0.45/0 beats the old cell 51/96 while 0.55/2 ties it 54/96); the mutual meta is the
  selector that held. `windfall_pct=1.0,windfall_reserve=0` reproduces the old behaviour.
- `_spawn_guess` now mirrors the engine's `_spawn_hand` exactly: hands spawn ON the four
  shed-access tiles (4,4),(5,4),(4,5),(5,5) by least-occupancy NWSE, not on an N/W/S/E
  ring around the shed. Regression-tested in `tests/test_policy.py`.
- SEED MAP WARNING: the spawn fix + windfall cap re-shuffled the per-seed outcome map
  (seed 9 went $8.7k -> $62k; mirror_tail's WORST/BEST quartile labels no longer name the
  same seeds). Re-derive bad-seed lists from a fresh tail run before autopsying.
- **Market monitor BUILT, gated OFF (16 Sep)** (`monitor=0`, `opp_credit=0.0`,
  `sell_infer=0.0` in PARAMS): a runtime estimator reading the public book every turn —
  per-good price slope (`tau`), town-drain scale (`d`), and opponent net supply from the
  inventory identity `opp = dInv - my_sells + drain + my_buys`. Measured INCONCLUSIVE
  in-mirror (aggregate −$21 across 4 blocks): the opponent's real volume (engine truth:
  ~11 wheat / 7 strawberry / 4.6 melon per day) moves book prices only ~1-4%, below
  allocator decision noise. Kept for LADDER INSURANCE, and it works: a doubled shop
  interval reads d=0.61 (caught), baseline reads d=0.84-0.87 (band 0.72-1.30).
  DOCUMENTED BLIND SPOT: a town-centre-interval-only override reads d≈1.02 — every
  untraded good is shop-dominated, and the opponent's own milk/egg/tomato sales
  contaminate all four drain goods downward. If a ladder replay ever shows a town-centre
  discrepancy, fit `d` offline from the replay JSON instead of trusting the monitor.
  The `opp` magnitudes over-read engine truth 2–4× on shop-drained goods (book zero-clamp
  truncation + wave-day clamping) and under-read melon; trust the SIGN (a trading peer
  reads positive) and the override detection, never the magnitudes.
  `analysis/monitor_truth.py` reproduces the engine-truth table on any seed.
  Build scars, all in the code: (1) sell bookkeeping must be CAPPED at shed stock at
  order time — raw order sizes overcount ~4x because sells re-fire every turn against
  self-liquidating over-orders; (2) BUY_SEED is fixed-price off-book — counting it
  poisons the identity; (3) the day-fit window must use the closed day's dawn shop list
  (shops unlocked on day N drain on N, not N−1); (4) each opp sample is clamped ±50
  units/day because units landing in the shed mid-turn are sellable same-turn and
  undercount our own executed sells; (5) with `monitor=1` and zero knobs the policy is
  byte-identical (regression-tested). Ground-truth hooks: `env._exec_hook` counts
  executed SELL/BUY_PRODUCT units per seat in the mirror engine.

- **Runtime engine fingerprint ADOPTED 16 Sep** (`force_engine="auto"` in PARAMS): the
  real harness calls callable agents as `agent(observation, configuration)`
  (kaggle_environments/agent.py), so on the ladder the version is READ off the handed
  config — `townCenterSellInterval` 24→1.32.7 / 12→1.32.2, certain, on turn 0. The
  config-less mirror tier falls back to a melon-cadence probe (MELON is in no shop
  basket, so the day-gap between its inventory declines IS tau). `apply_engine_profile`
  in constants.py swaps all five differing rows (tau, staged town-centre multiplier,
  unlock replacement, three below-curves) into every by-value importer; mirror engine.py
  reads the swappable rows through `kagfarm.constants` module attributes for exactly this
  reason. Measured: on 1.32.7 auto is byte-identical to pin (mirror seeds + the real-tier
  dir); on a 1.32.2 engine it is worth +$13.5k on seed 9 ($57,685 vs $44,201). A
  non-default config override reads None and falls back to the pin. Tests:
  `TestEngineFingerprint` (config dict+struct, probe gaps, profile tick/multiplier
  assertions, mirror byte-identity, config-path flip). `engine_verdict()` reports the
  active profile. The first replay's offline fingerprint now CONFIRMS what auto chose
  instead of being the only signal (runbook step 4 unchanged).
- **Bridge 1.32.2 config bug FIXED 16 Sep** (bridge/real_env.py): DEFAULT_CONFIG
  hardcoded tau=24 and shadowed the engine json, so every pre-existing 1.32.2-dir bridge
  episode silently ran the 1.32.7 town-centre rate. The bridge now merges each engine
  dir's json defaults over DEFAULT_CONFIG and hands the merged config to agents as the
  framework would. Nothing adopted depends on the old panels (all gates ran on 1.32.7
  dirs, where the merge is a no-op).
- **Opponent archetype panel (16 Sep, analysis/archetype_panel.py)**: the incumbent cell
  is field-robust — vs synthetic passive/hoarder/flooder/snapper opponents it wins
  48/48, 48/48, 42/48, 46/48 with the per-opponent max or near-max mean, and windfall
  stress cells fail in BOTH directions (0.55 reintroduces the death spiral against
  cash-retaining opponents: p10 ~$10k; 0.30 loses land races to a snapper 17/48). The
  0.45 cell is a genuine interior optimum against a field, not just a mirror.
- **External audit triage (16 Sep):** every historical trap claim in the outside audit
  (windfall spiral, A5 overfit, reserve failure, drain-floor, shed-100 discard, spawn
  tiles, zero terminal value) checked out as already-fixed or already-documented —
  closed. Two real finds, both fixed: (1) `eval.run_one` mutated module-global PARAMS
  with no restore, so in-process sequential runs (`evaluate(workers=1)`) evaluated the
  incumbent with the previous candidate's constants — now snapshotted and restored
  before return (bridge tier was already clean via per-episode Policy copy). (2) The
  engine's `[:MAX_MARKET_ORDERS]` truncation is silent and our sell orders can only
  survive it by construction — verified the cap arithmetic in `_market_orders` keeps
  total ≤ 10 in every branch and pinned it with two tests (unit + full-episode).
  Claims verified FALSE for our build: `_reorder_market` premium-first ordering (the
  vendored engine's market price is strictly per-resource — no cross-good coupling,
  so order position cannot change realized prices; only truncation survival matters,
  which we already defend), PLANT-during-day weed risk (already hour-23 guarded),
  seedless-PLANT loss (already `stock`-guarded), replay dict mutation (already
  deep-copied), `(5,4)` spawn wrongness (spawn guess already mirrors `_spawn_hand`).
  `max_yield_unfert` is dead data but documented as such — left in place.
- **Endgame leftovers audit (16 Sep, analysis/endgame_leftovers.py)**: shed leftovers at
  turn 720 are EXACTLY $0 on all 48 seeds (both opponents); standing crops mean $87-120,
  max $963 (~0.2% of the mean bank). The endgame_days=5 liquidation leaves nothing
  recoverable — the endgame-shaping axis is closed with direct measurement, not inferred
  from banks.
- **Closed axes re-verified under the windfall cell (16 Sep):** endgame_days 4/6,
  fert_stock 12/16, reserve 1.0/1.2, haul_trigger 0.45/0.70, mix_cap 4.5/7.5 and
  max_hands 10/14 all REJECT or flat on disjoint mirror blocks — no hidden interaction
  with the cap. `endgame_days=5` additionally confirmed on the REAL tier (24 mutual
  seeds, `calibration/real_endgame.py`); `lost` is mirror-only instrumentation.
  `LADDER_RUNBOOK.md` holds the submission + fingerprint decision rule.
- **Work stealing (16 Sep, `work_steal` param, default 0):** when a unit's queue drains
  it takes the nearest feasible TAIL job (never the head, never a `then`-chained PLANT,
  seed-checked) off another run instead of PASSing. Mechanism verified directly:
  idle 11.32% -> 8.66% of unit-turns on seeds 0-7. Banks flat: 4x48-seed block gate
  aggregate +$12, INCONCLUSIVE (block deltas −54/−12/−2/+114) — the allocator already
  fits work to labour in the incumbent cell, so freed turns have nothing they'd rather
  do. Off by default per the gate; in the sweep table, worth probing only paired with
  a leaner roster (max_hands) where labour might actually bind. Implementation note:
  `_valid` is re-checked before stealing, so a stale (already-served) tail is dropped
  and the next idle unit re-steals — self-healing, no replan involved.
- **Labour-bound regime probed and CLOSED (16 Sep):** `max_hands=8` alone REJECTS
  (−$3,244 aggregate, every block negative); `max_hands=6` REJECTS harder (−$11,353);
  `work_steal=1,max_hands=8` REJECTS (−$3,027). The interaction is real but small —
  stealing recovers ~$217 (~7%) of the lean-roster loss. The incumbent roster more
  than pays its wages; do not re-open roster shrinkage without a mechanism that
  makes hands cheaper, not fewer.
- **`sell_infer` tau-floor selling gated (16 Sep):** the wiring already existed
  (`_sell_orders` blends `mkt.tau_floor` into the reserve floor when monitor=1 AND
  sell_infer>0) but the pair had never been its own gate. `sell_infer=0.5`:
  INCONCLUSIVE (−$27); `sell_infer=1.0`: INCONCLUSIVE (−$100). Consistent with the
  monitor's physics: in-mirror the live curve ≈ the shipped curve, so the floor
  reproduces the static one. Stays off; the wiring is ladder-side machinery like the
  monitor itself.
- **Opening book BUILT, gated OFF (16 Sep)** (`opening_book=0`, `book_until_day=6`,
  `book_file=kagfarm/opening_book.json`): per-day donor scripts recorded by
  `analysis/capture_book.py`, keyed on the dawn SIGNATURE — public shop unlocks plus
  our own money/shed/seed totals, market inventory deliberately excluded (it is
  opponent-contaminated and must not disengage an opening). At runtime a matching
  dawn serves the donor's moves verbatim; a miss halts the book for that day and the
  planner takes over mid-day at zero cost. Book built from 32 donor episodes
  (16 seeds x starter/heuristic): days 0-2 are a single shared opening (1 variant
  each), days 3-5 branch into 8 shop-draw state paths; round-trip validation EXACT on
  all donor episodes re-served. Gate on unseen seeds (192-287): byte-identical (+0)
  — on donor paths serving IS our own play; unseen seeds serve only day 0 (its
  signature is seed-independent) and halt days 1-5 on novel shop draws. Day 0 is
  therefore a deterministic opening immune to whatever the opponent does to the
  market — the value case is ladder-side, and the book deepens by re-running the
  capture tool on real replays once they exist (no code change needed; the JSON
  ships in the tarball, and `bundle.py`'s single-file variant tolerates its absence).
  Tests: serve-exactness, halt-fallback, missing-file safety, dawn-signature
  reproducibility (36 total).

## Measurement epistemics (2026-09-20)

- The mirror drifts whenever engine.py/agents.py are edited between gated runs (interrupted
  turns shifted panel baselines ~$10k with a byte-identical policy). The REAL tier is the
  arbiter — it reproduced every recorded baseline ($47.5k self-play, 16-8 H2H) when the mirror
  did not. Re-run a control arm before trusting any mirror delta.
- The synthetic panel CANNOT price ladder-only phenomena: it was built from our own dumping
  habits, so it rewards the spray (dawn_pace ON measured −$15k vs the panel yet the ladder kept
  showing wave costs; sell-metering also mispriced twice). For sell/production-shaping axes,
  ladder replay autopsies outrank panel verdicts.
- Livestock ceiling (measured): a CROP-led build tops out at a 6-8 herd even with a working
  shepherd stream (s8 +$2.8k mean / x3.6 floor; s20 −$3.3k but most wins). The $144k-class
  winners give the herd the TILES — chore execution is solved; crop-vs-herd tile allocation is
  the untested lever.
- `shepherd_share` caps BOTH the stream's unit count AND the reachable herd (~2 animals per
  unit: one unit's day is ~20 turns). Profiles must carry share ≈ target/2 + 1 or the ramp
  stalls via the non-sticky n_buy cap (growth gates must stay memoryless — a sticky
  `want=live` freeze made one bad dawn permanent).

## Verification & determinism

- The policy is deterministic to the dollar given a seed; `pack.sh`'s bank-for-bank gate
  (unpacked tarball vs repo via `verify_pack.py`) depends on it. Break determinism and the
  pack gate fails loudly — that is a feature.
- Wall clock is a non-issue: worst turn ~2-6 ms across all opponents vs the 1000 ms `actTimeout`.
- Behavior-check the SHIPPED entry point (`main.agent`) through `engine.KaggricultureEnv` for
  720 steps, instrumenting `_settle_one_unit` / `_add_shed` / `_refresh_plant` / `_dispatch_unit_op`
  to count sells, overflow, deaths and harvests; replay identical seeds to assert determinism.
- Adding a module to `kagfarm/` requires updating BOTH `pack.sh`'s `SHIP_PKG` and
  `bundle.py`'s `MODULES`; each fails loudly (pack.sh asserts, bundle.py NameErrors) — use
  that instead of editing them speculatively.
- **PARAMS isolation on the in-process real tier:** there is no pool worker to re-import
  `kagfarm.policy`, so module-level PARAMS mutations LEAK across episodes. `PARAMS_BASE`
  (frozen at import) + reset in `sweep.score` is the fix — without it the holdout scores the
  incumbent with the winner's values (fingerprint: three identical holdout rows). Same
  class of bug bit `verify_replay.resimulate`: the interpreter mutates the seeded obs
  dicts in place, so replay seeding must DEEP-copy step 0.
- Replay alignment (Kaggle episode JSON): `steps[t].action` is the action that PRODUCED
  `steps[t].observation` from `steps[t-1]` state; `step` is framework-managed and never
  written by the interpreter — external drivers must advance it manually.
- **Mirror-vs-real semantics audit (17 Sep, external):** three mirror bugs fixed — (H1)
  mirror charged full-shed BUY_PRODUCT/BUY_ANIMAL and discarded; real REFUSES uncharged
  (engine.py now mirrors `_commit_unit`); (H2) mirror settled seat 0 before quoting seat 1
  — every eval gave the evaluated seat a systematic quote edge (~0.55% on bulk melon);
  mirror now quotes both seats at one pre-commit inventory per lockstep round; (H3) mirror
  spawned hands on an N/W/S/E ring around (4,4); real spawns on the shed-access tiles —
  `_spawn_hand_pos` now matches `_spawn_hand`, and the spawn test asserts the mirror's
  actual spawn. Effects: sanity panel $82,993 → $84,602 mean (phantom charges outweighed
  the removed seat edge), seed-0 pin $60,507 → **$59,249**, real-tier smoke $87,300 mean.
  **work_steal=1 ADOPTED** on the corrected mirror (4-block +$229, every block positive;
  the old INCONCLUSIVE was partly the H2 edge). monitor=1 and monitor+sell_infer=0.5 stay
  REJECT. `plan_ms` is now deterministic (default −1 = no wall-clock gate; a positive
  value makes behaviour machine-speed dependent and can flake pack.sh). Also fixed:
  `_book_serve` variant indexing (dead code that silently no-opped, with a vacuous test
  now asserting the RECORDED donor moves), off-by-one hands padding, opening-book path
  anchored to policy.py's `__file__`, wheat feed-of-last-resort shed-room guard,
  `eval.run_one` unknown-key restore, `engine.py` LOCKED/None precedence clause,
  `harness_smoke` tar `filter="data"`, and `.gitignore` now excludes the vendored engine
  dirs (keeping MANIFEST.sha256) before `snapshot.sh`'s `git add -A` commits Kaggle's
  source. 36/36 tests, PACK OK, BUNDLE OK, real-harness smoke clean.
- **The harness exec's `main.py`, it does not import it (2026-09-17):**
  `kaggle_environments.agent.get_last_callable` runs the submission source via `exec` with a
  bare globals dict — `__file__` is undefined there, so referencing it at module level DQs
  every episode (NameError → `InvalidArgument` → both seats ERROR, reward None, empty logs).
  All import-based gates pass on code that dies this way, so the only guard is the real
  harness: `analysis/harness_smoke.py` (exact tar bytes through `kaggle_environments.make`,
  three 720-step episodes, one process). `main.py::_locate_root` is the `__file__`-safe
  locator; obs/config arrive as `utils.Struct`, a dict subclass — `.get` works. Found by
  re-running PRE_SUBMIT_CHECKLIST against our own artifact: the smoke went 16-0-0 / mean
  margin $82,326 vs starter+random after the fix, and would have been 0 valid episodes
  before it.
- Run `analysis/harness_smoke.py` under `.venv/bin/python` (its tar `filter=` kwarg needs
  ≥3.12; system python3 3.9 dies before the checks). Artifact flow: `bash pack.sh` writes and
  bank-verifies `submission.tar.gz`, then `cp` to the named version — never touch the tar by hand.
- Ad-hoc probe gotchas (each cost a debugging round): (1) `importlib.reload(main)` re-imports
  kagfarm.policy fresh and wipes any `PARAMS.update` made BEFORE the reload — apply overrides
  after it; (2) `main.agent`'s never-raise contract silently swallows a crashing probe patch —
  zero output from a patched run means the patch raised, not that the code path never ran.
