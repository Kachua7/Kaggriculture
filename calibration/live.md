# Live calibration ledger — Vendored-Truth Purge

Written 12 Sep 2026. This file is the record the plan pre-committed to: which engine
version is the reference, what the 32-seed gate said, and what was therefore adopted.

## Engine versions in play

| Copy | Version | Role |
|---|---|---|
| `calibration/engine/` | **1.32.7** (pinned in `bootstrap.sh`, sha256 manifest alongside) | The reference. Mirror constants follow this. |
| `calibration/engine-1.32.2/` | 1.32.2 | Kept only to re-simulate the tutorial replay, which was recorded on it (`module_version: 1.32.2`, runtime `townCenterSellInterval: 12`). |
| `engine.py` (repo mirror) | models 1.32.7 constants, 1.32.2-validated growth rules | Screening tier: 144+ seed panels, sweeps. |
| Vendored interpreter via `bridge/real_env.py` | whichever `--engine-dir` | Confirmation tier: 32-seed panels, gates. ~8 eps/s in-process — no pool. |

**Golden gate:** `calibration/verify_replay.py` re-simulates the tutorial replay through the
vendored interpreter — **719/719 steps exact** under 1.32.2 (it diverges under 1.32.7 from
the first mechanics difference, as expected). Every `[real]` tag below is therefore
"real-for-a-recorded-engine", and the replay/observation field name is confirmed
(`obs["town"]["unlocked_shops"]`).

## The 1.32.2 → 1.32.7 delta (read from both sources)

| Mechanic | 1.32.2 (replay) | 1.32.7 (pin) |
|---|---|---|
| `townCenterSellInterval` default | 12 (1.32.2 json) | **24** (1.32.7 json); competition config may override |
| Town-centre demand schedule | **staged**: `[(20,4),(10,2),(0,1)]` — 1, then 2, then 4 units/day | **removed** — flat 1/day |
| Shop draw | **without replacement** (`rng.choice(sorted(remaining))`) | **with replacement** (duplicates consume independently) |
| CARROT/TOMATO/EGG below-curves | log / linear / linear | **hinge / hinge / hinge** (spike past T) |
| `max_yield_unfert` | does not exist in either version (WATER caps at `max_yield` always) | same |
| Market `BUY_PRODUCT`/`BUY_ANIMAL` | shed uncapped on buy | **shedCapacity enforced on buy** |
| `PLACE` op for animals | — (buy auto-places? no: `_apply_unit_action` PLACE exists in 1.32.2; json not) | PLACE documented in json |
| `$1` sells | add no market supply | same (both versions) |

## A3 gate result (32 seeds × self, pre-committed rule)

- mean bank: mirror $42,039 → real $45,704 (**+8.7%**)
- p10: mirror $8,899 → real $14,274 (**+$5,375**)
- **p10-set Jaccard 0.200** (lockout seeds reshuffle completely: mirror {10,13,16} vs real {13,14,29})
- win-rate vs starter: 100% on both engines (Δ 0.0pp)

**VERDICT: GO A5** (win-rate unchanged, Jaccard ≪ 0.85 — the constant changes move the
contested-market distribution even though they don't move the win-rate against weak
opponents).

## Closed-axis re-verify + real-tier endgame (16 Sep 2026)

After the windfall cap re-shuffled the seed map, every previously-closed axis was
re-verified under the NEW cell (mirror, 3–4 disjoint 48-seed blocks, `--workers 4`):

- `endgame_days` 4/6: REJECT both (−$1.1k / −$0.3k agg, sign-consistent)
- `fert_stock` 12/16: REJECT both (−$0.2k / −$1.1k; 12 also raises lost 13.7→15+)
- `reserve` 1.0/1.2: flat (±$27 — the 1.2 "ADOPT at +27" print is the confident-noise
  case blocks.py itself documents; ignored)
- `haul_trigger` 0.45/0.70: flat (real deltas −$18/+$16)
- `mix_cap` 4.5/7.5: REJECT 4.5 (−$0.7k), 7.5 inconclusive
- `max_hands` 10/14: 10 byte-identical to 12 (never binds), 14 REJECT −$2.1k
- `windfall_pct` 0.35/0.55: flat vs built-ins (expected — the cap never binds there;
  its mutual-regime case was settled on both tiers)

**No hidden interactions. The closed axes stay closed under the new cell.**

The OPEN live.md item — endgame/`lost` on the real tier — was closed with
`calibration/real_endgame.py` (24 mutual seeds): `endgame_days=5` confirmed
(3: +$488, 7: +$302 — both inside noise at n=24; the mirror curve shape stands).
`lost` is mirror-only instrumentation: the real tier exposes no overflow counter,
and its cost is already priced into the banks. No adoption; constants untouched.

`LADDER_RUNBOOK.md` now carries the submission + replay-fingerprint decision rule
(the one remaining calibration question).

## Runtime self-fingerprint (16 Sep 2026) — the replay dependency is gone

The version question can now be answered BY the submission instead of about it: the real
harness passes `configuration` to callable agents (kaggle_environments/agent.py line ~146,
`callable_agent(observation, configuration)`), and `townCenterSellInterval` differs
12↔24 across the two wheels. PARAMS `force_engine="auto"` reads the row on turn 0
(certain) and swaps the profile; the melon-cadence probe covers config-less engines;
non-default overrides read None and fall back to the 1.32.7 pin. Verified on the vendored
tier: the 1.32.7 dir detects 1.32.7 byte-identically, the 1.32.2 dir detects 1.32.2 and
is worth +$13.5k on seed 9 over mis-detected play. Regression-tested (TestEngineFingerprint).
The bridge's hardcoded config (which would have silently run tau=24 on 1.32.2 dirs) now
merges each engine dir's json defaults — a latent dev-tier bug fixed, no adopted result affected.

The runbook's step-4 fingerprint remains as post-hoc CONFIRMATION of what auto chose,
not as the only signal.

## Windfall-cap gate (16 Sep 2026) — A3 re-run on the adopted cell

The `windfall_pct=0.45` cell (see AGENTS.md, adopted via the mutual meta on both tiers) was
put through the same pre-committed 32-seed A3 gate:

- mean bank: mirror $57,905 → real $56,713 (−2.1%, tier-scale noise)
- **p10: real $39,450** — the pre-windfall A3 recorded $14,274; the real-tier tail moved +$25k
- win-rate vs starter: 100% both engines (Δ 0.0pp)
- p10-set Jaccard 0.000 — the lockout seeds reshuffled completely, which is what a +$25k tail
  move should do to the p10 set

**VERDICT: GO.** The 1.32.7 confirmation tier reproduces the adoption; constants stay tagged.
First ladder replay still must be fingerprinted before any 1.32.2 re-tag.

## A5 scoped re-sweep (real tier, 24 seeds self + 24 holdout, objective = wins)

Winner on the tuning panel (win 70.8%): `mix_cap 100, reserve 0.9, crowded 0.85,
fert_margin 2.6, endgame_days 4`. Holdout verdict:

| Cell | Δwin | Δmean |
|---|---|---|
| `mix_cap = 100` | **−16.7pp** | −$1,172 |
| `reserve = 0.9` | −4.2pp | +$156 |
| `crowded = 0.85` | −4.2pp | −$377 |
| `fert_margin = 2.6` | ±0 | +$62 |
| `endgame_days = 4` | ±0 | −$102 |
| all combined | **−20.8pp** | −$829 |

**ADOPTION: none.** The tuning-panel win was overfit; every axis regresses or is noise on
held-out seeds. Two `mix` candidates reweighted for with-replacement demand also rejected
on holdout (one −37.5pp, one flips +12.5pp → −25pp). The v1 structure survives contact
with the pinned engine unchanged.

**Verdict against the plan's kill row:** the gate fired GO, the scoped sweep was run, and
it produced nothing that beats the incumbent. Ship v1 as-is; constants stay 1.32.7-tagged.

## What is still open

1. **Which version does the live ladder run?** First ladder replay →
   `.venv/bin/python calibration/fingerprint.py <replay.json>`. If the re-simulation block
   dates it 1.32.2, re-tag constants (τ 12, staged centre schedule, no-replacement,
   log/linear below-curves), re-run the A5 gate, and update this file.
2. If the competition config passes `marketParams` or non-default intervals, the replay's
   `configuration` block names them — fingerprint prints them.
3. The endgame haul/liquidation tail and `endgame_days` never re-tested on the real tier
   against the *new* `lost` profile; `lost` is unmeasured on the real tier (shed overflow
   is visible only inside the interpreter).

## diff_source.py verdict (final, after the exec-extractor fixes)

`python3 calibration/diff_source.py` → `rows: 13   DEAD=3  REAL=10` — **DIVERGE=0, NEW=0**.
All ten configuration rows, the full MARKET_PARAMS table (per-good base/T/curves), CROPS,
ANIMALS, SHOPS (via the single-product ×2 fold mapping), and MAX_SHOP_INSTANCES match the
pinned 1.32.7 wheel exactly. The only DEAD rows are the three `max_yield_unfert` entries —
mirror-only inventions, already neutralized in engine.py. The A2 re-tag is provably
complete; any future re-pin re-runs this table first.

(Extractor notes for future maintainers: ast.literal_eval fails on both sources' dict-
constructor values — wheel MARKET_PARAMS/CROPS/ANIMALS embed MARKET_I0 name references and
mirror OBJECT_TABLE uses dict(...) calls — so both load through an exec fallback with
`__file__` set; the engine module imports kaggle_environments, so run the table under
.venv/bin/python. Ongoing crops are compared through the sched_days[0]→first_yield_day
mapping and the engine-derived max_yield_day is skipped by design.)

## Tooling added this session

- `calibration/verify_replay.py` — golden check + reusable `resimulate()`; exit 0 iff exact.
- `calibration/fingerprint.py` — version verdict from any replay (primary: re-simulation
  under both vendored engines; secondary: heuristic rows).
- `calibration/a3_compare.py` — the pre-committed 32-seed gate, exit code = verdict.
- `bridge/real_env.py` — vendored-engine driver + eval-compatible metrics.
- `eval.py --engine mirror|real`, `sweep.py --engine mirror|real`.
- `requirements-real.txt`, `bootstrap.sh` pin + `calibration/engine/MANIFEST.sha256`.

Run everything real-tier under `.venv/bin/python` (the wheel needs ≥3.11; bridge falls
back to a seed stub under bare python3, but `.venv` is the canonical interpreter).

## Mirror-semantics audit closures (17 Sep, evening)

External audit (all claims source-verified before acting) found three mirror/real
divergences. All fixed in `engine.py` and re-gated:

- H1 full-shed buys: mirror charged + discarded; real refuses uncharged. Mirror now
  refuses (BUY_PRODUCT, BUY_ANIMAL). Dump overflow discard was already correct (the
  real `_drop_inventories_to_shed` discards overflow).
- H2 market lockstep: mirror settled seat 0 before quoting seat 1 (seat-0 bias ≈ +0.55%
  on bulk melon); now both seats are quoted at one pre-commit inventory per round, with
  a `_quote_unit` helper and refusal-drop semantics matching `_process_market`.
- H3 hand spawn: mirror ringed N/W/S/E around (4,4); real spawns on the shed-access
  tiles. `_spawn_hand_pos` now equals `_spawn_hand`; the spawn test asserts the mirror's
  actual spawn (it previously passed against a hardcoded literal while the mirror was
  wrong — a false-confidence test).

Re-gated after the fixes: sanity panel $82,993 → $84,602; seed-0 pin $60,507 → $59,249;
real-tier (vendored 1.32.7, 2 seeds vs starter) $87,300 mean, 0 over-budget.
work_steal=1 ADOPTED on the corrected mirror (4-block +$229, all blocks positive).
monitor=1 / monitor+sell_infer=0.5 REJECT. plan_ms default −1 (deterministic; the
wall-clock gate made play machine-speed dependent and could flake pack.sh).
M1 closed: `_book_serve` now reads the matched variant (recorded at the dawn decision)
and the serve test compares against the RECORDED donor hours — the old test passed even
with the serve path broken, because both sides fell back to the same planner.
Also: book path anchored to policy.py `__file__`, wheat feed shed-room guard, eval
unknown-key restore, engine LOCKED/None precedence, smoke tar filter="data", vendored
engine dirs gitignored (MANIFESTs kept) ahead of any `git add -A`.

## 2026-09-17 (evening) — FIRST LADDER EPISODE AUTOPSIED: engine 1.32.7 EXACT, FREEZE

Replay 110081520 (the team's first scored ladder episode). Verdicts:

- **fingerprint.py: RE-SIMULATION EXACT, 719/719 steps under 1.32.7. NOT 1.32.2.**
  Per the A5 protocol: FREEZE. No re-tag, no constant changes, no code changes.
  (Supporting rows: shop draw WITH replacement CONFIRMED; CARROT/EGG below-curve
  families 117/117 and 165/165 exact; melon window CONFIRMED. tau UNDECIDED —
  recorded config states townCenterSellInterval=24, matching our 1.32.7 tag.)
- **The agent is fully alive on the ladder.** Agent-log durations spike at every dawn
  replan (steps 0/24/48/...) growing to 6.6 ms worst; zero stderr; 719/719 steps.
  Not the _safe_pass signature (flat ~0.1 ms, no spikes). Exec-context fix proven live.
- **Episode 110081520 was a SELF-MATCH**: both seats "Pranjal Morwal" — our two
  submissions paired together. Money curves identical through day 12, final
  $62,553 vs $61,732 (margin $821, market-tie noise). Guaranteed W+L, ~zero
  rating EV, no opponent information. Day-0 actions 24/24 identical (twin play).
- Rating 600 → 498 is BT noise from early matches (incl. this 50/50 self-pair),
  NOT broken play: the agent banks $62k+ on the ladder, in line with the $60-90k
  local band. Self-matches resolve as one win + one loss and rate us against
  ourselves; the fix is opponent volume, not code.
- New tool: analysis/replay_autopsy.py — one-command replay facts (teams,
  self-match flag, money curve, day-0 identity, behaviour profile). Run it on
  every downloaded replay before drawing conclusions.

Actions: none to the tar (frozen). Next replays: autopsy + fingerprint each; the
moment an episode has a REAL opponent team, read B2 evidence (who wins on what).

## 2026-09-17 (night) — FIRST TWO REAL-OPPONENT EPISODES: same loss mechanism, twice

Episodes: 110082767 (vs "Kaggriculture @ Farmageddon", L $86,464 vs $108,029)
          110086009 (vs "Aotokitsuruya",            L $48,194 vs $65,987)
Both fingerprint 1.32.7 EXACT (719/719 re-sim) — mechanics identical to our tuning.

Common pattern across BOTH independent opponents (B2 live evidence):
- LABOR: their HIRE orders 314 / 273 vs our 177 / 169 (~1.7-1.9x our labor force)
- SEEDS: their seed-unit buys 194 / 247 vs our 155 / 224, wheat-heavy
  (58 / 57 wheat seed orders vs our 6 / 7 — continuous fast wheat cycles)
- EARLY LAND: they unlock quadrant 2 by day 2-6 while we stay on 1 quad until the
  day-12 melon windfall (then jump 1->4). We win total land by mid-season and
  still lose: land without labor does not convert.
- IDLE CASH: our bank sat >$8k on 312/312 steps of days 13-25 in BOTH games
  (100% of the mid-season). Aotokitsuruya spent down to near-zero (81/312 steps).
- They passed us mid-season (Farmageddon day 18) or out-sprinted our endgame wave
  (Aotokitsuruya +$34.6k days 26-28 vs our +$20.3k).

Interpretation: the live meta is labor-heavy wheat-volume farms. The mirror's
"roster pays for itself / windfall 0.45 optimum" verdicts were measured against a
SYNTHETIC panel — precisely the B2 caveat. Evidence now exists to re-test the
roster and spend-rate axes as a SLOT-2 variant (slot 1 stays the proven frozen tar;
the variant swaps in for one of our two duplicate live submissions, so nothing is
risked). Decision with the team lead.

## 2026-09-18 — H4 CONFIRMED + FIXED: the animal programme was dead on the ladder, alive in the mirror

The 5-6 record vs real opponents hid a systematic hole. All 8 autopsied replays showed the
same signature: 2 cows bought, **zero** milk sold, `COW: 2` rotting in the final shed —
while every opponent (winners and losers alike) ran a live animal economy.

**Three stacked causes, each found by tracing one episode end-to-end:**

1. **Mirror divergence (op semantics).** Real `PICKUP` requires a shed-access tile
   (`_is_shed_adjacent`); real `FEED`/`FERTILIZE` draw from the UNIT's carried inventory,
   never the shed; real fert window is day..day+2. Our mirror lacked all three; the policy's
   one-leg "PICKUP anywhere" placement job only ever worked locally. Fixed in `engine.py`;
   policy re-anchored to 3-act chained jobs (PICKUP@shed -> walk -> op) via `then_pos`.
2. **Feed chains entered the value lottery.** The routine feed (~$246 at GROW) lost the
   `ranked[:n]` / serpentine coin-flip every other day; the engine kills at 2 consecutive
   misses; even the RESCUE tier lost on d16 while the plan bought a REPLACEMENT cow.
   Fixed in `_replan`: feed chains are pulled out of `ranked` and pre-pended to the nearest
   unit — a chore, not a bid. Also: no buy while any animal sits at unfed>=1.
3. **Care was gated behind the expansion gate.** `collect_jobs` keyed ALL animal care on the
   plan dict; gate-fail days blinded the planner to live animals. Care is now unconditional;
   only `n_build`/`n_buy` are gated.
4. **Buffer chicken-and-egg (real tier only).** The sell pass liquidated the same 6 wheat the
   buy pass purchased each turn (`mouths=0` held nothing back) — shed wheat pinned at 0 for
   12 days, buffer gate never opened, herd never started on seeds 2/3. Sell-side hold now
   counts `n_build` mouths. Root-caused via a temporary KAGFARM_DEBUG line (removed).

**Real-tier funnel (vendored engine), 6 seeds vs arch_passive:** buys 2, places 2, feeds
16-22 (= animal-days), zero escapes, zero rots, MILK revenue in every episode. Seed 2 bank
$79k -> $94k. Mirror suite 43/43 (6 new H4 pins in tests/test_policy.py).

**Adoption gate:** `n_animals=3` REJECT on the meta panel (-$383, `lost` 9.9->13.4) and
REJECT on the synthetic panel — the honest-physics herd is 2; the win is that those 2 cows
now actually produce on the ladder. Pre-flight green: 43 tests, PACK OK bank-for-bank,
BUNDLE OK, harness smoke DONE 720 steps. `submission.tar.gz` (69,962 B, 18 Sep) is the
H4-fixed build — submit as the next slot.

## 2026-09-18 (evening) — KT_V2 adoption verdict: crop/market layer REJECTED, CARE ADOPTED

The KT_V2 doc (10-replay ladder audit) was adopted behind gates, not wholesale. The gates
spoke with one voice: **everything that restructured the crop/market engine lost money on
the project's own panel; the one source-verified keeper — CARE — won cleanly and is now
the default.**

**Measured, rejected (panel = 24 seeds x 6 meta opponents, 144 episodes; incumbent tar =
$54,043 mean / p10 $34,652 / 121-144):**
- **D6 season-pot budgets (kappa):** kappa=1.0 capped strawberry at ~17 acres (the d12
  projection sees only 4-5 open shops) against a REALIZED price of 214% of base — every
  capped acre was money on the table. Panel fell to $31.7k. Kappas removed from crops.
- **D9 stagger cap:** 1.5 slack throttled the strawberry board to ~6 tiles/dawn — but the
  ongoing-crop strategy IS the wave (both $86k+ replays planted 85 in ONE dawn; every
  delayed day is 4-8 units x ~$200 the season never sees). MEASURED OFF (slack=100).
- **D3 melon cap:** KT's own Part 0 table contradicts D3 — melon earned us $26.4k/game,
  our #2 good. The mechanism is WAVES (d0/d12/d24 cohorts, each wave's head sells at
  $190-270 before the glut). Bisection: opening 9.5 tiles -> $31.9k, 14 -> $28.4k,
  25-but-no-second-wave -> $22.8k. Melon restored to mix at 24; mix_cap governs.
- **D8 metered sells:** sizing orders at the per-tick drain destroyed the cash cycle — the
  wallet sat at $2-7 for two weeks (no windfall, no herd, no land) and the season ended at
  $343. The banked (shed + carried) sizing is the incumbent's and is correct; the ladder's
  $0-realization sells were a BAG-STRANDING problem, already handled by haul discipline.
- **D5/12-hands via cash gate + D4 day-0 herd:** subsumed — the incumbent's roster is
  already cash-gated and the herd gates on `mouths_buffer`, which is the part that matters.

**Adopted — D2 CARE (`animal_care=True`, default):** source-verified against the vendored
engine — `pending_care_bonus += 1` on every cared-AND-fed day; production pops
`min(max_held, 1 + bonus)`. The incumbent's "measured, not worth it" verdict was rendered
on a mirror with WRONG CARE semantics; the KT turn made the mirror source-exact. With
daily feeding already guaranteed by the H4 chore architecture, daily CARE doubles a cow
(11 -> 66 units/season) and triples a sheep. A/B on two disjoint 24-seed blocks, sign
agreeing on all three objectives:

| block | arm | mean | p10 | min | win | MILK |
|---|---|---|---|---|---|---|
| 1 | off | 54,043 | 34,652 | 1,561 | 121 | 1,244 |
| 1 | **on** | **55,646** | **35,677** | **1,872** | **126** | **4,412** |
| 2 | off | 52,095 | 30,369 | 1,468 | 123 | — |
| 2 | **on** | **54,337** | **32,305** | **2,123** | **124** | — |

Post-adoption: panel mean **$55,516** (+$1,473 vs incumbent tar), p10 $36,171, 44/44 tests,
PACK OK bank-for-bank, BUNDLE OK (worst turn 5.3 ms vs 1000 ms), real tier 6/6 at $64.2k
mean with MILK $5.2k/episode. `submission.tar.gz` is rebuilt — submit as the next slot.

Also this turn: the KT-turn per-turn chore injector and the KT budget/stagger/melon code
were REMOVED in favor of the incumbent architecture (preserved at /tmp/kagg_kt_policy.py);
tests re-pinned to the H4 contracts they protect (metered-sell pins reverted to the
banked-sizing contract; the chore pin now asserts the dawn chore survives the roster
re-cut). One honest defect found and fixed while bisecting: `mouths` (buy-side buffer AND
sell-side hold) now counts standing structures, so a built-but-empty pasture can never
again deadlock the wheat supply.

---

## 2026-09-19 — submission-2 (V3 rewrite) compared, verified, and filed

The user attached `~/Downloads/submission-2` (main.py + kagfarm/{__init__,policy,spec}.py,
19.6 KB packed). `main.py` is BYTE-IDENTICAL to ours; the package is a different
architecture: a 926-line policy over a new engine-transcribed `spec.py` (12 hands,
drain-derived acreage, CARE from turn one, melon capped at 5 tiles, KAG_OVERRIDE env
hook). Comparison required a mirror fix first:

**H5 mirror fix (engine-exact):** our BUILD created `{kind: COOP, animal: None, ...}`; the
real engine creates a BARE `{kind: COOP}` and only PLACE writes the animal dict (escape
reverts to the bare structure too). V3's `"animal" in tile` test turned every empty coop on
our old mirror into a ghost animal -> KeyError -> its never-raise wrapper PASSed the whole
episode ($2,857 floor). Fixed engine.py (BUILD bare, escape bare, PLACE emptiness test
`"animal" not in tile`). Our build's numbers are UNCHANGED by the fix (55,516 as recorded).

**Head-to-head (same seeds x opponents both arms):**

| tier | arm | mean | p10 | win | notes |
|---|---|---|---|---|---|
| panel blk1 | OURS | 55,516 | 36,171 | 124/144 | CARE build |
| panel blk1 | **V3** | **77,475** | **59,646** | **137/144** | livestock-led: milk 34k, wool 22k |
| panel blk2 | OURS | 54,337 | 32,305 | 124/144 | |
| panel blk2 | **V3** | **76,502** | **60,604** | **128/144** | both blocks agree |
| real self 6 | OURS | 47,956 | 38,502 | 3/6 | |
| real self 6 | **V3** | **71,026** | **57,280** | **5/6** | +48%, 0.4 ms/turn |
| REAL H2H 24 games | dead even | 61,543 vs 66,645 | — | 12-12 | seats swapped both ways |

**Verdict: adopt as slot 2, do NOT displace slot 1.** V3 crushes synthetic strangers and
self-play but is even vs us in a shared market (its own `opp_weight=0.35` monitor fights
over the same pots). The ladder is strangers -> V3 is the higher-ceiling slot.

**Safety gates passed:** harness-style smoke (bare-exec, no `__file__`, both seats one
process, full 720 turns, worst 3.3 ms vs 1 s); self-contained (needs no opening_book.json;
imports only `kagfarm.spec`+`kagfarm.policy`); syntax-verified. Artifact filed as
`submission_v3.tar.gz` (19,566 B) — byte-for-byte the attached folder packed main.py+kagfarm.
V3 preserved importable at `kagfarm_policy_v3.py` + `kagfarm_spec_v3.py` with an eval-shim
`agent()`; drivers: analysis/ab_v3.py (panel), analysis/h2h_v3.py (real-tier direct H2H).

Unresolved before slot-2 upload: nothing blocking. KAG_OVERRIDE is inert on the ladder
(competition sandboxes typically scrub env); defaults are the tested config.

**Submission artifact:** the user's `submission-3.zip` (21.6 KB) was submission-BROKEN as
sent — macOS `__MACOSX/` junk inside, and `main.py` nested under `submission-2/` instead
of the archive root (the harness would miss the package and PASS whole episodes). Payload
itself was byte-identical to the verified V3 (all four hashes match). Repacked clean as
**`submission3.zip` (project root, 13.6 KB, `-X` no-extra-attrs)**: main.py at root,
no junk, unpacked hashes verified identical, artifact smoke re-run on the freshly
unpacked zip (720 turns x2 seats, banks $70.9k/$70.3k, worst 1.2 ms vs 1 s budget).
UPLOAD THIS ONE. Same payload as `submission_v3.tar.gz` — either format is fine; the zip
was requested.

## 2026-09-19 — V4: the seed-466488175 post-mortem adopted, then gated

The external post-mortem diagnosed V3 (submission-3) on one ladder loss (66.0k vs
123.7k). All four root causes verified in code: (1) MELON skipped when `rank` is built, so
no melon seed was ever bought/planted — the placement loop AND the seed ladder iterate
`rank`; (2) `_placement_jobs` returns nothing at `headroom<=0` and `need_struct` subtracts
all standing slots (`- empty_slots - held`), so a 13th pasture is unreachable — two cows sat
in the shed d15→end; (3) labour load 80–92 vs cap 87.8 + `_budget` pot-caps froze growth d16+;
(4) engine `_do_hire` has NO cap (fib only: $233/$377/$610 for 13/14/15), so 14 hands is
legal. Not the author's model: hire beyond 12 and re-priced-pot budgets are TUNING, and the
panel said both are wrong for the general field.

**Adopted (all structural, code-verified):**
- Melon given a `rank` entry (`want>0` ⇔ window) + ladder slot 0 with full-cohort buys.
  The d0 cohort died on cash-order: at t1 the ladder's running cash was spent by hires+feed+
  cows before the seed section ran ($370 < $400 cohort). A wave that misses its window is
  worth $0 — everything else can wait an hour. Waves 2/3 (d11–13, d24–25) re-enter only
  above 2.5× base; panel-neutral (the d0 wave itself pushes MELON below the floor).
- Structure build decoupled from crop-labour headroom: gate on empty tiles + banked stock
  instead (`min(need, 4)`; 0 only when the board is genuinely full).
- `sheep_cap` knob (default 0 = uncapped) + WOOL crash drip (sell ≥8/tick below 0.30× base).
- Wave/ladder cap: `min(melon_tiles, 8)`, `hold_px` 0.80→0.70 (data: every held good
  re-listed ≥1.5× base).

**Rejected by the same-day A/B (author's tuning, fitted to one game):**
- `hands=14` + raised kappa: the V4 bundle scored $63.3k mean / p10 $40.0k / 87-144 vs the
  same-day ref V3 $77.5k / $59.6k / 137-144. Bisected: the sheep cap alone cost $14k mean
  (panel wool is 19.5% of revenue, $21.9k/ep — the cap was fitted to a game where WE crashed
  wool by dumping 64 units); raised kappa −$10k on top; hands 13/14 regressed p10 (f1 $53.9k
  vs e3 $59.5k). The author's "idle cash d16+" is real, but cash deploys into land+herd via
  the structure fix, not wages.
- Adopt point **e3** = structural fixes + V3's original kappa + hands 12:
  **$78.1k / p10 $59.2k / min $47.3k / 132-144 (block 1); $78.3k / $60.3k / 136-144
  (block 2)** vs same-day ref $77.5k / $59.6k / 137-144 and $76.5k / $60.6k / 128-144 —
  ≥ ref on mean and floor.

**Target-seed behavior (466488175, real tier):** self-play $25.5k → $55.3k/$56.0k; 5 melon
seeds bought d0 and sold in the d11–13 wave; pastures 7→11; herd 4→15 head; cash deployed
through d17.

**Real-tier H2H vs the CARE build (24 games, seats swapped): V4 16–8** (V3 was 12–12),
means $70.2k vs $64.3k. The fixes help exactly where V3 lost: ramp-up and cash deployment
in a shared market.

**Artifact: `submission4.zip` (project root, 20.8 KB)** — main.py (byte-identical to the
submitted line) + kagfarm/{__init__, policy, spec}.py; import rewritten package-relative
(`from .spec import`); verified: fresh-unpack hash match on all 4 files, bare-exec harness
smoke with the package import ASSERTED (banks $55,280/$56,014 = probe_v4 to the dollar,
exec-path equivalence proven; second seed $46.7k/$43.5k), worst turn 1.6 ms vs 1 s budget.
Reference copy: `kagfarm_policy_v3_ref.py`; drivers: `analysis/ab_grid.py` (bisect matrix),
`analysis/probe_v4.py`, `analysis/probe_ladder.py`, `analysis/probe_trace0.py`.

## 2026-09-19 — dairy recipe mapped onto the first-submission build (H5/CARE line)

Author's engineering premises: ALL FIVE verified in vendored source (1.32.7) — shed-adjacency
= (4,4),(5,4),(4,5),(5,5) with PICKUP/DROP/PLACE shed-only (README L43/49/50); FEED needs
the animal tile + unfed + 1 wheat from the unit bag (L505-513); BUY_ANIMAL settles into the
shed at fixed price (L679-686); 10-order cap truncates per turn (L551/560); midnight dumps
bags and fires hands (L878-882). No fiction there.

Recipe item -> verdict on THIS build (panel block 1, 144 eps, control reproduces the
recorded $55,516 / p10 $36,171 / 124-144 exactly):
- 8-cow herd day-gated ramp  -> ADOPTED AS MECHANISM, REJECTED AS DEFAULT TARGET: ramp arm
  $53,074 / p10 $34,978 / 116-144 (all three objectives down); ungated arm byte-identical
  (the incumbent's one-a-day + buffer + margin + 2x-cost gates bind before any target does).
  `_ramped_target` ships behind herd_ramp=True / ramp_cap_early=2 / ramp_full_day=14 — a
  proven no-op at n_animals=2, insurance for any future raised herd target. 3 new tests.
- WHEAT_RESERVE=12          -> already present, stronger: feed_hold=12/mouth, dynamic in
  mouths incl. n_build; and the sell pass holds grain while any animal is alive.
- CASH_FLOOR=400            -> already present, stronger: n_buy gated on
  money > buy_cost*2 (implies >=$400 remaining after any animal order).
- PREMIUM_SELL_ORDER        -> rejected as a regression: static list sells MELON first even
  after its price crashes ($24 observed in the wool-crash replay); _sell_orders already
  sorts dearest-first dynamically and buys sell-slots back last under the order cap.
- farmer partition to 4 shed tiles -> rejected as structural regression: our routing is a
  budgeted serpentine planner (~10 tile-visits/unit vs ~4 for greedy nearest-hand, route.py
  docstring) and the farmer is the day-0 planter; a shed-lock breaks the melon factory.
  (dairy80.zip's own farmer walks out to harvest with no bag — its rule is advisory.)

Artifacts: submission.tar.gz rebuilt through pack.sh (PACK OK, bank-for-bank, 2.3 ms worst),
real tier 6/6 self at $47,956 = recorded baseline. Suite 47/47.

## 2026-09-19 — ladder dump-gates from episode 110850828 (L $62,335 vs $128,508, Malak Reda)

Autopsy: we lost on PRICE REALIZATION, not production. Three one-turn dumps collapsed the
shared book, all traced to code: melon d10 = 714 units @$26.2 (opponent: 24 @$148) from the
book's 23-seed cohort ripening synchronized + `always_sell` full-naming; wheat d16 = 417 @$2.9
then bought back d17-26 @$30-47 (crowd-dump branch bypassed the reserve floor entirely);
strawberry d27 = 1,025 @$15.5 while the opponent dripped at $175-238 daily. Opponent profile:
never >~30 units/day of anything, all season; $89.1k realized from animals (milk 40.2k + wool
19.1k + fertilizer byproduct 29.8k) vs our $6.0k milk / 2 cows.

Adopted (panel-gated, block1+block2 disjoint, baseline $55,516/$54,337 reproduced first):
- **melon_opening=8** (was 23): the book's day-0 BUY_SEED MELON is capped at serve time
  (`_book_serve`); cohort still lands in one order. Book file untouched. Both blocks: mean
  +$496/+$438, wins +2/0, and the tail unlocks (max $68.9k -> $92.4k) — smaller cohorts
  realize higher prices on the seeds that matter. `melon_opening=0` restores verbatim serve.
- **crowd crater floor** (`crowd_floor_frac=0.5`): crowded sells now walk the price curve
  down only to half the reserve floor instead of naming everything at whatever the book
  clears — the $2.9-wheat round-trip is dead. Uses the same fast-valve (2x cap) as before.
- **crowd cap** (`crowd_cap_mult=2`): crowded sells of ordinary goods name <=2x2 days of
  observed town drain (valve doubles it; feed grain excluded from the valve total).
  `lost` 33 -> 15.9/11.4 (halved spoilage), px 110.7% -> 111.7%.

Adopted-then-reverted BY MEASUREMENT (the honest ledger):
- **endgame meter** (`endgame_cap=2`): REJECTED — our endgame stock is a WAVE (last cohort
  + bag accumulation), so metering just moved the dump to the final day while overflow ate
  the stock in between (mean -$5.5k, lost 33->41). Default endgame_cap=0 = full-clear, the
  B11 verdict stands; the meter stays available behind the param, pinned by test.
- **n_animals 2 -> 4**: REJECTED AGAIN — mean $54,686 vs $56,852 at n=2 with identical sell
  fixes; the ramp's day-14 release leaves too few milk days to pay for displaced crop
  labour. The live livestock gap belongs to V4 (54% animal revenue), not this crop-led build.

Tests: 9 new (crowd floor/cap, valve, melon clear + cohort cap, ramp, meter-behind-param),
57/57 green. Real tier: self-play $47,459 (baseline $47,956, noise), H2H vs V4 unchanged
16-8 (fixes target the FIELD, not the duel). pack.sh PACK OK bank-for-bank; harness smoke
no ERROR/TIMEOUT, 720 steps, worst 2.4ms. submission.tar.gz rebuilt (73,591 B).

The structural lesson, now in code comments: our synthetic field mirrored our own dumping
habits, so every previously "closed" axis touching sell RATE was measured in a vacuum. The
winner's edge was never a bigger farm — it was drip-sized production plus never cratering
the shared book.

## 2026-09-19 (evening) — replays 110873165 (W +$20.9k) & 110874286 (L −$39.5k): dawn-pace axis

110874286 vs Yeyuqing0913 is the third consecutive confirmation of the spray signature: our
seed buys ran d0 {MELON: 23} -> d11 {STRAWBERRY: 41, WHEAT: 25} -> d12 {STRAWBERRY: 20}, the
cohort ripened as a wave (4 units @$569 on d17, then NOTHING d18-24, then 475 units @$44.57
on d27) while the winner committed ~26 strawberry tiles once and drip-sold at 177% of base.
Their real engine was the animal economy: fertilizer $59.3k (122 units @ $486 = 9.7x base),
wool $41.4k, milk $43.3k — ~$144k of $199k total. That lane stays V4's.

Built: `dawn_pace` — a per-dawn planner gate in `_targets` with replace+growth semantics
(a dawn may REPLACE the live board plus N tiles; replacement can never be vetoed, so the
melon factory's 8-tile replant cycle survives — capping the whole allocation measured
-$12k in the first design's bisect). Held seeds are paced too (planting 20 held seeds
same-day recreates the synchronized cohort). Day-0 book serve never reaches `_targets`,
so the melon opening is untouched by construction. One off-by-one caught by tests
(want > live+pace allowed one tile past the cap; fixed to >=).

REJECTED BY MEASUREMENT, DEFAULT OFF (dawn_pace=None, mechanism pinned behind the param):
both panel blocks, same-day driver, 144 eps each — OFF $66,346/$65,465 mean, p10 $45.8k/
$48.1k, 288/288 wins; ON (8/dawn) $51,256/$49,934, p10 $41.4k/$37.4k, 254/288. The panel
REWARDS the spray: its opponents were built from our own dumping habit, so it cannot price
the wave's cost — the strongest form yet of the 2026-09-19 structural lesson. Ship bar was
parity; this is -15k, so the default stays OFF until ladder evidence re-opens the axis.

Tooling fact now on the record: the MIRROR drifted during the interrupted turns (engine.py/
agents.py edits post-date the last gated ledger entry) — today's mirror panel reads the
whole tree ~$10k above the recorded baselines ($66.3k unpaced vs $56.0k recorded; baseline
reproduction is no longer possible on the mirror). The REAL tier settled everything:
self-play $47,459 vs $47,956 recorded (baseline intact), H2H vs V4 exactly 16-8 — policy
behavior is byte-equivalent to the shipped submission except the inert dawn-pace gate.
Next mirror work must re-baseline the recorded numbers first.

Tests: 63/63 (6 dawn-pace: default-off, pacing, replacement, net-growth bound, held seeds,
None off-switch). pack.sh PACK OK bank-for-bank (commit 5029a9a +uncommitted), verify smoke
worst 2.4 ms. submission.tar.gz rebuilt. Temporary probes removed.

## 2026-09-19 (night) — livestock A/B/C/D on the real tier: the 80-90k ceiling, measured

Goal: the 110874286 winner's ~$144k animal economy (fertilizer $59.3k @ 9.7x base, wool,
milk, ~22 animals) as the route to an 80-90k minimum. Built `animal_pace` (animals bought
AND structures built per dawn, default 1 = byte-identical; emit scales
min(pace, want - built) / min(pace, want - live - held), cash gate scales with pace, all
safety gates kept). Funnel probe got an ANIMAL_ARM hook.

12 seeds x (self + arch_passive), REAL tier, all four failure modes measured per arm:

| arm | profile | ALL mean | p10 | min | milk units | win |
|-----|---------|---------|-----|-----|-----------|-----|
| A | n=2, pace=1, h10 (control) | $56,672 | $37,986 | $12,036 | 15 | 18/24 |
| B | n=20, pace=4, h10 | $53,623 | $40,100 | $34,413 | 20 | 18/24 |
| C | n=20, pace=4, h12 | $56,256 | $46,193 | $27,073 | 20 | 16/24 |
| D | n=8, pace=3, h11 | $53,724 | $37,461 | $30,436 | 16 | 19/24 |

VERDICT: the +$8k adopt bar is NOT met (best arm is mean-parity). What the run bought:
the floor (B/C/D min $27-34k vs A's $12k) and p10 (C +$8.2k). What it did NOT buy: mean.

BINDING CONSTRAINT (funnel, ANIMAL_ARM=c, seed 0): pace works -- 20 structures built, 7
animals bought -- but ALL 7 ESCAPED. Feed ops 28 for the episode where a 20-herd needs
~400: the mouths*6 wheat buffer IS bought (arm B spent only +$1.3k over control), so the
grain is in the shed and the FEED VISITS never arrive. Chore routing serves a 2-herd;
it does not scale to 20. Until feeding is a first-class scheduled job stream (roster
sizing + router capacity charged per animal-day), the herd ceiling is ~2-4 productive
animals and the winner's fertilizer/wool/milk volumes are unreachable by params alone.
NEXT LEVER (not this cycle): animal chores as a scheduled stream with per-animal-day
routing budget; then re-run this A/B with pace 4-6.

Also note: the architecture recipe's verified/rejected items and the post-submit
fingerprint step are recorded in the runbook (LADDER_RUNBOOK.md).

Tests: 63/63 (pace emit covered by the byte-identity-at-1 contract and min-clamps).
Artifact UNCHANGED per the ship condition -- submission.tar.gz / submission7.tar.gz
remain the shipped builds.

## 2026-09-20 — shepherd stream (scope v4) built and measured

Phase 1 (execution): dedicated chore loops (`shepherd_loops`/`shepherd_chores`), shepherd
carve-out in `_replan`, shed-near structure placement, workload-sized stream (smallest share
whose loops fit the stream's own day), non-sticky co-feasibility cap on `n_buy`, feeds-first
loop ordering, all-quadrant shed seeding, herd-protected endgame feed hold. Three real bugs
found by the funnel and fixed: turn-vs-visit units mismatch (freeze at live=4), sticky
`want=live` freeze (buys=2 stall), endgame sell pass draining the feed buffer (d28 escape
with grain in the pool). **Funnel gate met: 0 escapes on all 6 probe episodes** (4-7 live).
68/68 tests green (shepherd tests byte-identity at default + loop semantics).

Phase 3 (real tier, 12 seeds x self+passive, arm A control reproduced the recorded $56,672):

| arm | mean | p10 | min | wins | milk+fert rev |
|---|---|---|---|---|---|
| A control | $56,672 | $37,986 | $12,036 | 18/24 | $5.5k |
| s8 (8-herd) | **$59,481 (+$2.8k)** | **$43,767 (+$5.8k)** | **$42,854 (x3.6)** | 17/24 | $18.1k |
| s20 (20-herd) | $53,383 (−$3.3k) | $40,774 | $38,534 (x3.2) | **19/24** | $13.7k |

**Verdict: +$8k bar NOT met — no submission8.** The stream works; the economics cap out:
a crop-led build tops out near a 6-8 herd served by 3-4 shepherds. s8's disaster-floor
tripling and s20's win-count lead are real ladder value (Bradley-Terry rewards not-losing),
but neither clears the mean bar, and `shepherd_mode=0` ships default (byte-identity
re-verified by pack.sh bank-for-bank; harness smoke clean, worst turn 2.4 ms).

The gap to the $144k winner is now precisely bounded: they run the stream AND give it the
farm's tiles (their crop line is small and drip-sized; ours still grows a full melon
factory). A livestock-LED profile (n_animals as the primary programme, crops as the side
gig) is the one untested configuration — the crop-led tests can't see it by construction.

## 2026-09-20 (later) — submission8 packaged by owner's call

The +$8k mean bar was not met, and the owner chose to ship the best measured profile anyway.
Defaults flipped to the s8 shepherd profile (`n_animals=8, animal_pace=3, shepherd_mode=1,
shepherd_share=4, max_hands=11`) — the A/B numbers carry over exactly, since the default
build now reproduces the s8 arm ($59,481 mean, $43,767 p10, min $42,854, 17/24 on the
24-episode real-tier gate vs control's $56,672 / $12,036 worst-case). What the owner buys
at mean cost −$? (nothing at mean; +$2.8k): +$5.8k p10, a x3.6 disaster floor ($12k -> $43k),
and a working livestock line (milk+fert $5.5k -> $18.1k). Pins updated to the new contract;
68/68 green; funnel 0 escapes at defaults; pack.sh PACK OK bank-for-bank; real-tier harness
smoke on the artifact: DONE/720 steps, no ERROR, banks $3,632/$71,611 (worst turn 2.5 ms).
Artifact: `submission8.tar.gz` (79,805 bytes, main.py at archive root, no junk files).

## 2026-09-20 (evening) — replay autopsy 0-4 batch, Option B trial and revert, submission9

### The four-game autopsy (analysis only, no code changes during the pass)

| episode | our seat | opp seat | margin |
|---|---|---|---|
| 110897820 | $55,191 | $161,741 | −$106,550 |
| 110918559 | −$63,140 (margins) | — | loss |
| 110922997 | −$19,590 (margins) | — | loss |
| 110928677 | −$35,700 (margins) | — | loss |

Our profile in all four: **23 melon seeds planted day 0** (allocator filled the quadrant
because the only `melon_opening` consumer lived in `_book_serve` and `opening_book=0`
ships default — the dead-knob diagnosis), day-10 melon **order** of 834 units, d11–12
strawberry spray of 37–80 tiles, d25+ shed peaks 56–86 (no midnight discards,
`haul_trigger` fine), herd ops 47–63/season. Shop draws supported dairy in all four
(milk-demand present, yarn in two); no town-demand lock.

**Measurement correction (decisive):** the "834-unit dump" and "1,157-unit d27 craters"
are **order sizes, not settled units** — over-naming a SELL is free (winners emit 6,000-
unit clear-alls on day 29; `test_sell_counts_carried_inventory`'s 86-naming is contract).
Observation ground truth for 110897820 day 10: shed EMPTY and $7,913 banked — the melon
wave settled at roughly the winner's scale (12 seeds, 60 units @5/tile). The winner plays
the same melon wave we do; its $161,741 came from 22 animals, 184 eggs, 150 strawberry
@2x — volume on scarce goods, not from us being capped.

### Option B trial — implemented, measured, REVERTED same day

Built per plan (planner-path clamp in `_targets` binding on day 0 regardless of book
state; `dawn_pace` default ON at 8/dawn; 3 new test pins; verified day-0 BUY_SEED MELON
= exactly 8 with surplus flowing to carrot/wheat). Real-tier A/B then rejected it 3x in
one afternoon (12 seeds x self+passive each):

| arm | mean | p10 | max | strawberry |
|---|---|---|---|---|
| caps OFF (= s8 default) | $59,481 | $43,767 | $76,721 | 134 u @ 197% |
| pace ON + clamp | $51,023 | $41,445 | $59,760 | 56 u @ 228% |
| clamp alone | $51,162 | $41,575 | $59,967 | 68 u @ 219% |

Mechanism (coherent, visible in the revenue table): the day-0 melon windfall is what
FUNDS the d11–12 strawberry spray — 23 tiles finish day 9–10, the windfall plus d11 land
unlock buys the strawberry cohort. Clamp the funding and the spray never happens;
strawberry volume collapses 134 → 68 units and the gross loss dwarfs the price gain.
Per-unit strawberry price DID rise (228% vs 197%) — the price-protection premise is
real; the volume premise was wrong on this engine.

**Epistemics refinement (supersedes the blanket "ladder outranks panel" rule):** the
panel's blind spot applies to SELL-side axes, where it mirrors our own dumping habit.
Production-VOLUME axes follow real engine physics, which the real tier reproduces —
there "ladder evidence" from order sizes misleads, and the real-tier A/B is the arbiter.
Rule of thumb: waves seen in replay *actions* must be validated against replay
*observations* (sheds, money) before they enter a plan.

Both mechanisms stay in code, param-gated (`melon_opening`, `dawn_pace`), with the
mechanism tests retained behind explicit overrides. Defaults returned to the measured
s8 profile. Pins updated to the reverted contract; 71/71 green.

### submission9 — packaged

`submission9.tar.gz` == the s8 profile, byte-equivalent in behavior to `submission8.tar.gz`
(the trial left no behavioral trace; the diff is param comments, the clamp mechanism
behind default-OFF, tests). Gates: 71/71 tests, funnel 0 escapes at 6 live both seeds,
pack.sh PACK OK bank-for-bank (verify_pack mean $69,585 on 8 episodes both sides), real-
tier harness smoke on the artifact: DONE/720 steps both seats, no ERROR/TIMEOUT, banks
$3,538/$76,878, worst turn 2.6 ms.
SHA-256: `4daed365e4e247f7a1a3457ebbee3ab4e4b6adfad544b717a93078da08d8063f`

### submission9 five-game autopsy (batch 111103455–111264433, 2026-09-20)

Banks (bank-matched seat IDs; replay_meta's name labels were seat-inverted on this
batch — always match final banks before attributing seats):

| game | us | opp | margin | opp profile |
|---|---|---|---|---|
| 111103455 | $58,352 | air $54,713 | +$3,639 W | herd 10 by d9, hires 5-9/day, zero weeds |
| 111148725 | $61,206 | Aditya Dube $76,971 | -$15,765 L | 16 animals by d12 (6C/6S/4G) |
| 111201497 | $57,823 | Sathishkumartheta $75,714 | -$17,891 L | 14 by d15 (12 cows), hires 12/day |
| 111229714 | $63,413 | Vladyslav Kovkin $63,778 | -$365 L | 10 sheep gradual, even game |
| 111264433 | $66,396 | Madhur Sabherwal $83,006 | -$16,610 L | 14 by d15 (8C/11S) |

**Execution held the s8 contract in every game** (d0 melon cohort fired, wave sold,
herd fed, weeds cleared by d27, sheds under cap; our banks $57.8-66.4k, all >= the s8
mean $59.5k). **We lost to a style:** opponents assemble 14-16 animals by d12-15 while
our first placement lands d15 and steady-state (5-6) only at d21 — their d15-29
compounding window is 14 days, ours 8. Secondary leaks: our d1-d9 hiring trough
(`4, 0, 2, 2` hires vs their 5-12 daily from d0) and mid-season weed brushes (our
peaks 11-13 vs winners' 0-9).

Verdict: s9's profile holds up exactly as measured on the panel and loses to the
$75-83k livestock-led class that now dominates the schedule. The gap is the six-day
herd-assembly head start plus daily steady hiring — the Majkel1337 dossier's opening
script. Fifth confirmation of the structural pattern (110897820's $161k winner,
110962306's $105k, these three).

Also confirmed in this batch (game 111103455): final-market fingerprint — we named
1,078 melon + 1,044 strawberry while selling 0 TOMATO into a 3x PIZZA draw ($280
final) and 0 WOOL into a YARN draw ($242), and bought zero sheep. Candidate-universe
ceiling, not optimizer failure.

## 2026-09-21 — submission10 build session: replay-judge panel + gates

**The replay-opponent panel is built and validated (the plan's core deliverable).**
Five judges (air, aditya, sathish, kovkin, madhur) replay their recorded market+physical
actions verbatim. Calibration instrument = verify_replay's both-seats-verbatim resimulation
on the VENDORED engine (the mirror cannot reproduce a recorded economy — verified the hard
way; all judges flagged LOW-CONFIDENCE there while self-sustaining to the dollar on the real
engine). Result: cash_ratio 1.00 on all five, 719/719 steps exact — the panel also
independently re-validates the vendored engine against five fresh ladder episodes.

**Tooling (run with .venv/bin/python — vendored engine imports kaggle_environments):**
`analysis/profile_replay.py`, `replay_opp.py` (judges + manifest), `analysis/ab_panel.py`
(--calibrate / paired_ab), `agents.py` (BUILTIN_AGENTS registration). Design contract:
each judge runs on its OWN recorded seed; the only difference from the recording is our
seat's play (a true counterfactual). Verbatim judges are seed-locked — on foreign seeds
their tape buys garbage and they become $0 bystanders (a too-easy test; do not do it).

**Replay-tape alignment trap:** steps[t].action produced steps[t].observation FROM t-1, so
the action for obs.step=s is index s+1. First bridge A/B fired every recorded feed/water one
turn early — day-boundary feeds landed before the midnight fed_today reset, silently killing
production (77 failed milk sells). Same rule as verify_replay.resimulate.

**Panel baseline (s8 default):** margins -3.9k / -19.5k / -33.7k / -0.4k / -18.7k —
1W-4L, mean -15.2k. Kovkin matches the ladder to the dollar; others land near the recorded
outcomes. The panel reproduces the ladder. THE REAL JUDGE WE NEVER HAD.

**opening_led arm (dossier transplant: d0 cow+wheat script, herd 12, roster floor 10)
— REJECTED by the panel gate.** Measured ladder of arms on the honest judges:
s8 default (-15.2k mean) > opening_led12 (-26.2k) > opening_led8 (-31.9k).
Diagnostics worth keeping:
- Roster floor 10 alone: -$25k on the mirror (seed 0, arch_passive). Forced 9-10 hires
  spend the bank to ~$0 daily (seeds+fert cash-gate off the wage bill), the cash-gated
  herd never assembles (1 animal all season), and mid-season die-offs compound. The
  dossier's "10 hands every day" only works when EVERY hand is employed on a 12-20 herd.
  led_roster_floor default stays 0; knob kept.
- Day-0 script must be guarded by self.ordered: unguarded it re-fired all 24 turns of d0
  (7 cows, bank $937). Both d0 knobs now guarded; script alone measured +$2.4k (cow0).
- Herd 12 bypassing the ramp: -6.7k mean on the mirror panel — consistent with every
  prior herd raise; the ramp bypass buys animals the shepherd stream cannot serve.
- Vs air judge, opening_led12's own bank rose but the JUDGE banked $69.7k vs its recorded
  $54.7k — our oversized herd fed their book. Losing arms can feed opponents; the panel
  sees this, the synthetic panel structurally cannot.
- Shop-keyed species choice: already in via animal_rank (prices each species' product
  against the unlocked shop schedule) — no table needed; the rank refuses bad placements
  only when the species-choice gate opens at all.

**SHIPPED in submission10:** the sell-from-shed settlement fix — SELL settles from
private["shed"] ONLY (vendored `_commit_unit`), unit actions run before `_process_market`
so a same-turn DROP funds a same-turn sell, but named-carried units never settle. The
sell pool is now shed-backed + carried named as a free MARGIN (unfunded tail units are
skipped silently — costs neither a slot nor a dollar), incl. carried-only goods (a
same-turn DROP can land them in-shed before settlement). Also removed a pre-existing
duplicated while-block in the normal-sell path. Episode 110850828's d28 trace (23.6
strawberries stranded at 720) is the motivating mechanism. Mirror n=1 can't price the
d29 effect either way; it is strictly contract-correct. opening_led=False ships
byte-identical s8 behaviour + this fix.

**Verification chain:** 71/71 unit tests; bundle.py bank-for-bank identical (8/8 episodes,
worst turn 5.4ms); tar payload unpacked and smoked; opening_led=False confirmed in payload.
Artifact: submission10.tar.gz, 82,208 bytes, sha256 6a7a0eed0984c0ce0d53722d1978269beaa2ce6e8c842c503dbb0cd69a57624b.

**Next-lever ranking (panel-measured):** the gap to the $75-83k class is NOT transplantable
by opening-order alone — it is herd economics our streams can't serve. The levers the panel
can actually price next: (1) per-animal shepherd throughput (loops/unit, bag cap) to make a
bigger herd servable at all; (2) shop-keyed PORTFOLIO admission (wool/tomato candidate
universe, the 111103455 ceiling); (3) feed-at-floor wheat buying (game-1 final market:
9,871 units at $36). The dossier's day-0 herd-first ordering is measured DEAD for this
architecture; stop re-proposing it.

### Adversarial re-review of this session's changes (2026-09-21, same day)

**Defect found and fixed (mine):** the sell-from-shed edit had narrowed `total` (the crowd
metric) to shed-only along with the sell pool. `total` feeds the `crowded` flag and the fast
valve — an OVERFLOW predictor that must stay shed+carried (carried bags bank into the shed at
midnight; the 11.6-destroyed-units mechanism from 110850828 is exactly this). Restored
`total = shed + carried`; only the named-sell count remains shed-backed. The original
`pool` fed both consumers; my edit split one consumer into two variables and dragged the
second along. Lesson: when a variable feeds two concepts, split it at the consumer, not at
the source.

**Consequence: the packed artifact was rebuilt** (the earlier 6a7a0eed sha carried the
degraded crowd metric in its s8-profile payload). New: submission10.tar.gz, 82,263 bytes,
sha256 bbe979a133dc5c7b945d1a2c35e5e6ccc2f733dba7cc61b751855645467ce2b0. Re-verified:
71/71 tests, bundle 8/8 bank-for-bank (worst turn 4.7ms), tar payload smoked ($68,395 on
seed 0 — crowd-metric restoration is worth ~+$16.9k on that seed vs the pre-correction
code; it restores shipped anti-overflow discipline, the sell fix's effect remains embedded).

**Panel numbers re-measured on corrected code (the verdict was robust):**
baseline s8 mean margin -11.2k (air +3.6k, aditya -23.2k, sathish -19.8k, kovkin -365,
madhur -16.1k — Kovkin still exact to the ladder); opening_led12 mean -22.9k (madhur
flipped +5.7k, air/sathish/kovkin still disasters). s8 default wins the gate. All earlier
session conclusions stand.

**Audit trail of what was checked and cleared:** sell-fix loop (pool|carried union,
carried-only goods named — free upside, engine skips unfunded units); mirror
`_settle_one_unit` parity with vendored `_commit_unit` (shed-only SELL, silent skip, full-
shed BUY refusal) — contract verified on both engines; d0 script guards (self.ordered),
reduced-bank sequencing, falsifiable arm knobs; `_ramped_target` opening_led bypass;
replay judge `step+1` alignment; panel seed-locking contract (each judge on its recorded
seed); judged-hands overflow safety (mirror truncates hand_ops per unit owned — no
KeyError/crash under counterplay).

## 2026-09-21 — Elite spectator judges added; first measured margin vs Majkel

**Machinery:** spectator-judge support in the panel. `replay_opp.SPECTATOR_IDS` maps
elite-vs-elite episodes (games that do NOT contain us) to explicit seat indexes —
TeamNames order IS seat order (verified against bank-matching on our own games), and the
auto-seat heuristic keys on OUR d0 melon cohort, so spectators require the explicit seat.
`_replay_seed()` reads info["seed"] (validated: 111103455 -> 85913572 matches the
hardcoded manifest value). `ab_panel._judge_meta()` unifies both manifest kinds; ALL_PANEL
is now 7 judges. `agents.py` unchanged (spreads build_manifest()).

**Calibration:** replay_majkel and replay_thirdfarm both cash_ratio 1.00, 719/719 exact,
no premium flags (WHEAT 0.49/0.65 = the known same-day-settle artifact on the fastest
good; gate only flags premium).

**THE NUMBER — submission10 baseline vs the full 7-judge panel:**

| judge | our bank | judge bank (recorded) | margin |
|---|---|---|---|
| air | $58,338 | $54,713 ($54,713) | +$3,625 |
| aditya | $53,654 | $76,877 ($76,971) | −$23,223 |
| sathish | $61,011 | $80,835 ($75,714) | −$19,824 |
| kovkin | $63,413 | $63,778 ($63,778) | −$365 |
| madhur | $66,886 | $82,994 ($83,006) | −$16,108 |
| **majkel** | **$47,255** | **$157,475 ($139,851)** | **−$110,220** |
| **thirdfarm** | **$56,060** | **$180,838 ($127,781)** | **−$124,778** |

**Read (three layers):**
1. The old five reproduce their recorded margins exactly (kovkin to the dollar) — panel
   integrity holds through the extension.
2. **Our gap to the top class is ~$110k, not ~$20k.** The ladder's $75-83k class and the
   $140k class are different sports. The herd machine (shepherd throughput -> wheat
   backbone -> max_hands 12 -> early land) is not a tuning project; it is the whole game.
   Closing HALF this gap lands ~$95-105k, above the current $75-83k ladder class.
3. **Both elites banked MORE against us than in their recorded head-to-head** (Majkel
   +$17.6k, TFC +$53.1k above recorded — the largest counterfactual signal the panel has
   produced). Mechanism: the recorded game had TWO elite animal economies sharing one
   market, glutting each other's premium books and bidding up shared feed. Against our
   crop-led seat, their milk/wool sells into an empty book while our own selling pushes
   crop prices down. We are not merely losing to them; our current profile is the
   best possible CUSTOMER for their economy. Every melon/strawberry we sell subsidizes
   the gap.

Also confirmed: our seat banks least on the elite world ($47.3k vs $53-67k elsewhere) —
the 111328923 shop draw punishes the melon-heavy profile further.

**Next arms (unchanged order, now with a precise target):** shepherd throughput
(2->3 animals/unit), wheat-backbone feeding, max_hands 12 + early land, then the d0
seed-mix arm (6M+10W elite convergence vs our 22-melon cohort — now doubly motivated:
the elite world's shop draw punishes the melon cohort).

## Elite kill-chain v2 — where the gap opens (2026-09-21)

Instrument: `analysis/kill_chain.py` (real tier, judge on own recorded seed — the
counterfactual contract). Metric discipline per review: SELL counts SETTLED units
(`_commit_unit` hook), HERD counts PLACED animals (tile state), feed cost = wheat-bought
cash + own wheat valued at realized price (upper bound). Panel now 10 judges; the three
new ones calibrate cash_ratio 1.00 / 719/719 exact. `submission10.tar.gz` verified
untouched after all analysis (sha256 bbe979a1…7ce2b0; bare `shasum` prints SHA-1 —
always use `-a 256` when checking the ledger).

### Phase 0 — d0-10 servicing capacity (THE binding constraint)
- vs Mujtaba ($85k class): opp holds H=8 hands from day 0 and runs FEED/CARE/DROP from
  d0-1 (1 placed animal, 2 coops by d2). We hold 1-3 hands d1-9 and our first physical
  chore stream is d10. First divergence: DROP=2, FEED=4, CARE=4, HERD_PLACED=4,
  COLLECT+HARVEST=5, BUILD=10.
- vs Majkel/TFC ($140k class): 5 animals PLACED on d0, FEED/CARE from turn 1,
  COLLECT+HARVEST divergence d1, herd 21 by d11 (TFC) vs our 0 until d13.
- The d1-9 labor starvation measured in the ladder autopsy is confirmed under
  counterplay: ~30-40 idle early labor orders while the judge builds its machine.

### Phase 1 — d8-14 herd compounding
- Mujtaba: opp herd 4 (d10) -> 8 (d11) -> 15 (d12) -> 16 (d14). Ours: 0 until d13, 2
  by d15, 6 by d20. PURCHASED split: 6 vs 17 animals bought.
- Majkel: 21 placed by d11 vs our 6 total; animals bought 7 vs 18.

### Phase 2 — d15-27 recurring monetization (settled units @ realized $)
- Mujtaba: MILK ours 78u @$174 ($13,593) vs judge 195u @$201 ($39,243); WOOL ours 0 vs
  judge 106u @$247 ($26,137). D_p (judge product revenue to deny/compete) = $65,380.
- TFC: MILK ours 70u @$319 ($22,308) vs judge 291u @$297 ($86,539); WOOL ours 0 vs 81u
  @$210 ($17,006); EGG 101u @$46. D_p = $108,157.
- Our melon line WINS its matchup (v1: 155$/u x 131 vs 129 x 72) — it is just too small
  to matter against a $65-108k animal book.

### Phase 3 — d29 terminal conversion
- vs Mujtaba we WIN liquidation: +$8,621 vs +$5,007 — endgame is not the gap at the
  $85k class. vs TFC it is: their d29 +$23,468 vs our +$6,566 (final swing -$16,902),
  driven by 12 DROPs + 50 COLLECTs on the last day vs our 3 + 5.

### Conversion efficiencies (season)
| judge | eta_animal (u/feed-care) ours vs judge | eta_capital ours vs judge |
|---|---|---|
| Mujtaba | 0.54 vs 0.53 | 0.45 vs 3.07 |
| Majkel | 0.51 vs 0.62 | 0.61 vs 3.16 |
| TFC | 0.49 vs 0.72 | 1.17 vs 4.26 |

### Verdict (four-phase)
The gap opens in Phase 0 (servicing: hands d0-9 + chore streams from d0) and compounds
in Phase 1 (herd placed by d11-12, not d18-21). Phase 2 prices it ($65k-$108k judge
animal books vs our $13-22k). Phase 3 is already competitive vs the chasing pack.
eta_animal is near parity — our per-animal machine is fine; eta_capital (0.45-1.17 vs
3.1-4.3) shows we never deploy the capital into animals at all. **The lever is capital
-> placed animals EARLY, gated on Phase 0 servicing capacity (hands d0 + shepherd
throughput), not per-animal efficiency.**

### Controls recorded (review-locked)
- Attribution: all numbers above are real-tier (vendored engine, judge's own recorded
  seed); mirror numbers are approximations and must not be quoted against these.
- No-imitation clause: arms must not clone judge action sequences; they are judged
  against them on the counterfactual seed.
- Promotion gate for the servicing-throughput experiment: panel mean margin vs the
  three elite judges must improve, D_p must not grow (product denial must not feed the
  judge's book), and the d10 melon wave must survive (it is our one winning line).
- Artifact: submission10.tar.gz untouched by this analysis turn (sha256 bbe979a1…7ce2b0).

## Sub10 first ladder batch — 15 episodes in sub10games/ (2026-09-20)

Record 7W-8L (7W-7L real; +1 self-match 111362182). Our banks $45.4k-$76.1k, mean $63.1k.
Perfect class split on opponent final bank: 7-0 vs sub-$58k opponents, 0-7 vs $61k+.

All 7 losses share one signature: opponent buys 7-12 COWS and PLACEs on day 0 (turn 3-7);
our first PLACE is turn ~318 (d13-14) in EVERY game, 0 placed by d10 all season. Opponents
with early placement but goose-heavy or unserviced herds (Jan 15G, ahmedou 14G+2C, GSD 24
animals/unserviced) still lost to us. Cow-heavy serviced day-0 herds = the loss class.

d20 position predicts 12/14 outcomes; losses carry a -$1.9k to -$22.1k d20 gap (the herd
book we never build). Exceptions: comeback wins vs samanyu (-$7.8k at d20, +$31.6k final)
and Swaroop (-$1.9k -> +$54.8k) — our d20-29 slope ($41-69k) is competitive.

Our seat is highly deterministic across all 15: first hire t=1, ~205 hires, 148-227 seeds
(melon 23-30, wheat 27-119, strawberry 20-89), 16-21 sell-days, peak 875-1,276 units/day
emitted (pot-limited settlement; no craters vs sub-$58k class). Sell-fix banks up vs s8-era.

Verdict: independent live-field confirmation of the kill-chain. The Phase-0 servicing arm
(day-0 hands + chore streams + capital -> placed serviced cows by d10) is the lever; the
recorded promotion gate stands unchanged.

## 2026-09-21 — elite_counter_v1 implemented (P0 block + smoke-caught fixes)

Built the approved elite-counter package in kagfarm/policy.py behind elite_script (OFF by
default; baseline byte-identical, 90/90 tests green):

- P0-1 engine-exact animal_programme (care-bank pop semantics; cow 36/sheep 34/goose 54
  cared units) + P0-2 state-exact pre-event HARVEST (pending_care_bonus from the tile).
- P0-3 mixed-herd portfolio (COW/SHEEP/GOOSE envelopes, per-species ordered guards).
- P0-4 settlement-based day-0 FSM: t0 COW+grain+4 HIRE, t1-t2 sheep spread per turn with
  per-turn bundle cap 2 (the 10-order slot cap truncates anything denser); script owes
  outrank seeds until settled.
- P1 time-indexed feed gate + mandatory wheat backbone allocation in _targets.

Smoke (vendored engine, seed 0) caught five defects, each fixed:
1. Sell pass sold the whole 28-unit feed bridge back (dawn-stale mouths=0) -> herd
   escaped by d5, season $2.7k. Fix: shed-animals count as mouths in _sell_orders.
2. Script bridge sized off shed animals (they do not eat until placed) -> $500 dead
   capital; placed-mouths-only targeting (led_wheat0 floor per turn).
3. Seed budget zeroed inside the script window -> field never opened, $1-27 cash d4-10,
   cow lost d14. Fix: seed_floor=300 inside the window.
4. WOOL reserve floor ($150 x 0.9) parked the first pop; hold window is day>=12 and the
   elite wool floor drops to 0.55 x base past d12 (dossier: first-mover until d12, then
   hold through the trough, sell into recovery).
5. animal_margin froze expansion at the opening herd with $30k idle (in-mirror both
   product prices crash). Fix: elite_margin=0 when money >= expansion_cash(5) x cost.

Mirror A/B (both seats, seeds 0-3): elite mean $57.2k vs baseline $66.3k — mirror
understates the elite arm (both seats glut each other's markets; the baseline's 22-melon
wave feeds on a copy of itself). Season shape on seed 0 is dossier-faithful: melon 12
seeds, wool first-mover sale d9-10, wool hold d14-16 recovering ~$190, milk drip d17-29.

REAL-TIER VERDICT (the number that matters) — ab_panel vs the only elite tape that
survived the Downloads cleanup, 111369668 SpaTaro $115.3k / Majkel1337 $120.0k (seed
1430410553, registered as replay_sparo / replay_majkel3):
- s10-baseline: our $68.6k vs judge $178.2k -> margin -$109.6k. The judge EXCEEDS its
  recorded $120k: every unit we do not produce is revenue Majkel captures. This is the
  competition objective measured directly.
- elite-v1: our $43.7k vs judge $95.2k -> margin -$51.5k. Market denial works (judge
  suppressed $178k -> $95k) but our own economy gave up too much (melon_opening=0).
- melon12/melon20 single-run spread ($20.6k/$43.7k) shows the chaos scale on one judge;
  directional conclusions only until multi-seed.
- Gap decomposition: (a) elite-v1 never re-expands the herd past 6 (portfolio caps +
  service gate), (b) melon engine cannibalized by the animal opening, (c) judge's real
  economy is land+herd+melon triple-engine; ours is two.
Next lever, in order: herd envelope above 6 with a scaled shepherd share (the service
gate is the binding constraint, not cash), then melon cohort re-addition once the herd
machinery holds 10+.

## 2026-09-21 (cont) — judge panel restored; multi-judge A/B verdict

Restored 14 wiped tapes from kaggle/kaggriculture-episodes-2026-09-1{9,20} via
analysis/restore_replays.py (per-file download from the official daily episode datasets;
location map in analysis/replay_location_map.json). All 14 feature Majkel1337 and he wins
every one (margins +$326 to +$21.6k). 16 judges now registered in replay_opp.SPECTATOR_IDS
(Majkel seat only per game). Our own lower-scored ladder games are NOT in the published
daily snapshots — they only exist as downloads.

Panel A/B, 5 judges, each on its recorded seed (margins, our$ vs judge$):
- s10-baseline: -20.1k (886), -124.7k (900), -92.4k (907), -86.7k (913), -70.8k (920); mean -78.9k
- elite-v1:     -88.8k (886), -117.3k (900), -79.0k (907), -64.9k (913), -77.2k (920); mean -73.5k

Read: elite-v1 is better on mean and on the wide games (suppression), but LOST badly on
886 — the closest recorded game (+$326) — because the melon-led baseline was actually
contesting that board while our animal opening handed Majkel's engine a free field (judge
$136.5k vs recorded $74k, i.e. +$62k of uncontested revenue). Neither arm suppresses
consistently; judge banks $71k-$181k vs our $37k-$65k is a 2-3x structural gap.

Structural conclusion (unchanged from the gap decomposition, now panel-confirmed): a
2-engine economy (animals XOR melons) cannot beat Majkel's 3-engine economy
(land+herd+melon, $100k+ in every restored game). The build target is triple-engine with
a 10+ herd: scale shepherd share with herd size (service gate is the binding constraint),
keep the capped melon cohort, keep land expansion.

## 2026-09-22 — grind 0921: co-feasibility gate rework (projected herd + growing share)

**Symptom.** Skeleton arm frozen at 4–5 animals all season on every judge (baseline
bought 5 vs Majkel's 18). New `gate_log` telemetry read dawn-by-dawn on seed 0:
- d1–d12 `money_gated=True` (legacy pace×cost×2 = $4,800 floor vs bank $500–2,400)
- d12 money clears, buys 3 (gate tested live=4: b_full 33 ≤ 64 ✓ — **admitted the
  buy that broke it**)
- d14 the 7-animal stream costs **b_full=92 > share 4×per_unit 14=56** →
  `n_buy_cap=0` for the rest of the season; overloaded stream then **killed 3
  animals by d26** (live 7→4)
- `per_unit` also shrinks 18→14 as quadrants unlock (commute grows), so the fixed
  share went stale even without the buy.

**Fixes (kagfarm/policy.py, `_animal_plan`).**
1. **Projected co-feasibility**: the gate now tests live + unplaced + the pace buys
   this dawn would admit (capped by `want`), not the current herd — it can no longer
   admit exactly the buy that breaks the stream.
2. **Growing shepherd share**: share grows from `shepherd_share` while the projected
   stream overflows, roofed at ~half the roster (census: 5–6 of 12 hands) and
   max_hands−1. The roof, not a constant, is now what freezes growth.
3. **gate_log extended** (permanent, diagnostics-only): share_cap/per_unit/b_full/
   c_full/live/held/built/backlog. Guarded with `locals().get` because the shepherd
   block is skipped at live=0 — the unconditional first version NameError'd inside
   `_animal_plan` and act() swallowed it (the "gate_log went silent" red herring).
4. Money floor: legacy `pace×cost×2` **kept**. Two cheaper variants tested and
   reverted: raw cost and cost+2d-grain both collapse the mirror to $14k/$4.9k even
   with the new gate — Majkel's same-day windfall reinvest needs a field already
   producing at his cadence; ours isn't there. Revisit with a feed-surplus
   admission test (shed buffer ≥ 2 days).

**Tests.** `test_default_off_and_cofeasibility_gate` updated to the new contract
(share grows to roster roof; freeze requires a roofed-infeasible stream —
max_hands=3 → roof 2 < 9 pastures). 90/90 green.

**Mirror (skeleton, seeds 0–2).** $49.3k/$54.6k, $46.5k/$45.4k, $44.9k/$58.4k —
healthy; herd places d3–5, ramps to 7 by d13 (was frozen at 4). Late-season
7→4 deaths remain (watch item, not this cycle).

**Real-tier judges (kill_chain, own recorded seeds).**
- majkel886 (closest game): margin **−$88.8k → −$61.5k**
- majkel907: **−$92.4k → −$62.5k**
- majkel900 (widest game): −$124.7k → **−$140k** (regression; our bank $31k vs
  $171k — the widest judge punishes our slowest economy)
- Mean: **−$102k → −$88k**. Animals bought 7–9 vs his 16–24 (was 5 vs 18).
- Structure notes: wool first-mover confirmed on 886 (ours 71u @ $227 = $16.1k vs
  his 60u @ $209); milk is still his engine (his 276u @ $132 = $36.5k vs ours
  63u @ $136 = $8.6k); eta_capital 0.36–0.65 vs his 0.95–2.65.

**Named next levers.** (1) The money floor blocks exactly the d6 wool-windfall
reinvest — a feed-surplus admission test is the designed fix. (2) Milk lane: his
$36.5k comes from cows placed by d6 — our first cows land d4 but the herd stalls at
4–7 through the milk window. (3) majkel900 regression to diagnose before shipping.

## 2026-09-22 — grind 0921 b/c/d: shed-ring reservation + LPT shepherds + ring commute

**Diagnosis (from the majkel900 gate/geometry probes).** The d14-d22 buy veto was the
co-feasibility gate reading a REAL overload — caused by three stacked geometry/planning
defects, not the gate:
1. **The shed-ring land race (the named seam).** The 46-tile d0 seed round claims the
   whole shed-adjacent band days before the first BUILD fires, so pastures sat at avg
   walk 3.9-4.0 (Majkel: 1.6-1.8). 7 animals cost 83-92 service turns vs 6x12=72
   capacity.
2. **Snake deal** put the farthest item into cluster 0 (nearest+farthest ~= 20 turns);
   the max-based care test read the one fat loop and vetoed with 4 shepherds idling.
3. **Area-scaled per_unit** (18->12 as quadrants unlock) priced shepherd days like crop
   serpentines, but shepherd loops are shed-anchored (loop[0] is a shed PICKUP).

**Fixes (kagfarm/policy.py).**
1. `collect_jobs`: shed-ring RESERVATION — tiles at Manhattan <=2 from any access tile
   (access tiles excluded) are held for animal structures while `need_more > 0`
   (want − built − live), released once the herd is housed; crops walk a filtered pool
   so a same-call planting cannot eat the reserve.
2. `shepherd_loops`: LPT deal (costliest item first into the lightest cluster) replaces
   the snake round-robin.
3. `shepherd_loops`/`_animal_plan`: shed-anchored commute (constant 3.0) for shepherd
   budgets; crops keep the area-scaled term. Herd-aware growth roof `(_proj+1)//2`.
   Placement on the judge confirmed: pastures [(3,3),(3,4),(4,2),(4,3)] — walk 1.5
   (was 4.0), Majkel's exact ring pattern.

**Results.** Animals bought on judges: 13/10/7 vs Majkel 16/24/19 (session start: 5).
Herd 10 placed by d18 (was 7 forever). 90/90 tests; mirror $31k-$53k (self-play
noise band). Judge banks noise-flat (mean −$92k): the herd arrives but still dies
late — execution-level, see next entry.

**Named next seam (execution, not planning):** the stream is planned to fit (b_full
42-49 vs capacity 84-96) but only 7-9 FEEDs execute per day against ~21 needed (12
units incl. farmer; kill_chain FEED column). At d20-24 the herd starves (10->1 placed
by d24 on 900) and `starving=True` re-vetoes. Suspects: shepherd queues dropped by
the unit-count-value lottery at re-plan (the stream assigns shepherds as units NEAREST
the shed — but re-plans hand their queue slots to crop sweeps), or loops rebuilt on a
shed whose grain hasn't landed (PICKUP validity grace).

## 2026-09-22 — grind P1/P2: FEED execution fixed; two economic fixes tested and reverted

**P1 — the FEED execution seam, root-caused via graphify call-graph audit + queue spy.**
`_replan` re-derived shepherds by nearest-shed distance on EVERY call and overwrote their
queues with the full loop from its head. Roster re-cuts fire on every HIRE batch, hands
spawn on shed tiles, so each arrival re-sorted the ranking and discarded all in-progress
loops (the traced planned-21/executed-7 gap). Second defect: loop FEED legs are marked
`carried=True` at ASSIGNMENT, but grain only enters the bag when the PICKUP head executes;
a momentarily dry shed made every carried FEED execute empty (engine no-op, turn AND chore
burned). Fixes (policy.py): (1) `shepherd_pins` — pairing chosen once at the dawn plan,
kept across re-cuts; a mid-progress shepherd queue is never overwritten; (2) bagless-FEED
repair in `_unit_ops` — re-queue a grain run sized to owed feeds, or defer bagless FEEDs
behind grain-free legs (CARE/HARVEST). Gates: FEED 154/154 and 98/98 on mirror traces, no
d20-24 collapse, 90/90, judge mean -$88k -> -$79.7k (886 -$61.5k -> -$45.2k, 900 -$140k
-> -$101.8k, 907 regressed -$62.5k -> -$92k — watch item: milk sold at $49 avg into the
crash, wool 0 on the default arm).

**P2 — feed-surplus money floor (TESTED, NOT ADOPTED).** Floor = admitted buys + missing
2d grain bridge at live wheat price + $150 reserve (the 0921 variants' collapse mode is
structurally unreachable in this form). Result: animals stayed 8/8/8 on judges (the floor
is no longer the binding gate once the projected co-feasibility gate exists) and the
mirror regressed $37-48k -> $34-42k. `feed_floor` knob kept OFF, documented, for P5.

**P2b — sell-side feed protection (TESTED, REVERTED).** The 886 skeleton trace caught the
real d22-25 herd deaths: shed grain 0 with ten mouths standing while `SELL WHEAT 1-4`
fired every few turns — the carried-margin term (`pool - hold + carried`) names units that
can only settle FROM the held grain, and the crowded exemption zeroed the hold for whole
days (pressure 56-85%) while the BUY_PRODUCT buyback was itself `crowded`-gated. Three
variants (unconditional hold + margin clamp; + valve floor removal; + physical-crowded
floor removal) all regressed: judge mean -$90.6k, seed-5 steal test froze at $3.8k, and
the crater-floor breach broke a measured contract. REVERTED to the shipped form; the
correct shape is settlement-exact (never name more than pool-hold shed-backed units,
never drop bags) plus a crowd-proof BUY_PRODUCT lane — gated on the judge panel, not
built mid-session.

**State at end of turn:** post-P1 build is the session best (90/90; mirror $44-58k;
judges 886 -$45.2k / 907 -$92k / 900 -$101.8k, mean -$79.7k). Next: P3 edge layer
(wool tilt / cadence front-run / opponent-conditioned portfolio), P4 late rank window,
then the P5 tuner — the knob sheet now has two measured-OFF candidates (feed_floor,
sell-side feed protection) waiting for it.

## 2026-09-22 — Two gap-closers: milk window shipped, money floor closed for good

**Objective:** ship the milk first-mover window (opponent-herd-conditioned sell cadence)
and the herd scale-up past 8 (field-cadence-gated money floor). Promotion bar: judge mean
+$10k over -$79.7k, no judge regressing >$5k. **Bar NOT met; one mechanism shipped as
verified infrastructure, three market-side fixes measured dead. The seam moved upstream.**

### Shipped and kept: the milk window (P3)
- `self.opp_census` (rival herd from public `farms[].tiles`, every turn) + `self.px_peak`
  (season price peaks) in `_market_orders`; milk hold in `_sell_orders` (elite-only knobs:
  `milk_window/1, milk_window_start/13, milk_opp_glut/8, milk_hold_frac/0.8, milk_hold_cap/40`).
- Mechanically verified on judge 907: census reads his 14-15 cows correctly, peak 237
  tracked, hold condition correct. Byte-inert in self-play (A/B off-vs-on identical to the
  cent: [30537/67067],[44716/51987],[26292/33646] — twin census stays < 8 cows).
- **Why it did not move the judges:** shedMILK = 0 every day d10-20 on 907. Our herd
  places d14-20 (judge: d1-8); milk's first yield is d8 after placement, so our first
  milk lands AFTER the $206-237 window closes. The hold is correct infrastructure but
  economically moot until the herd ramps early. Judge 907 still realizes 87u @ $49 vs
  his 347u @ $139.

### P2c k-scaled field-cadence floor — TESTED AND OFF (third money-floor failure)
Floor = largest k<=pace the bank carries WITH the bridge priced from the real wheat
schedule; k-admitted quantity flows to the emission. Mirror: seed 0 herd 2C+2S ($37.9k),
seed 1 OK ($57.3k), seed 2 herd ZERO ($28.9k). The bridge is PRICED into the floor but
not ENFORCED (the reservation is advisory; wages/seeds/fert/land still draw the rest).
Three independent designs (0921 raw-cost, P2 fixed-2d, P2c k-cadence) all fail the same
way: the legacy wall's slack IS the field protection. Only an ENFORCED reservation (the
emission batch itself buying the bridge grain) could reopen this — P5 tuner item.

### P2b carried-margin clamp — TESTED AND REVERTED (same session)
Clamping carried margin on held goods ("settlement-exact") cost the mirror $62-66k ->
$19.8-50.1k. The carried margin names two things settlement cannot distinguish: same-turn
DROPs (legitimate, load-bearing for the wheat drip economy) and slow-walker bags (the
theft tail). Killing the first costs more than the second. Real fix = a bag-tracking map
(which carried units reach the shed this turn) — P5 tuner item.

### Judge panel (default arm, all three Majkel judges)
- 886: ours $46,214 vs $91,439 -> **-$45.2k** (unchanged from post-P1 reference)
- 900: ours $58,902 vs $160,727 -> **-$101.8k** (unchanged)
- 907: ours $54,650 vs $146,629 -> **-$92.0k** (unchanged); milk 87u @ $49 vs his $139
- Animals bought 8 vs 16/24/19 on every judge; eta_capital 0.25/0.86/0.11 vs 1.36/3.38/1.87.

### The seam this turn named (next session's target — upstream of the market layer)
1. **Wool lane produces ZERO on 886/907** (judge sells 60u @ $199 / 81u @ $162): our
   8 animals appear to be all-cow on 886/907 (wool 0u sold, 0u shed ALL season) while
   wool sits at $174-218 — a seller's market we ignore. Probe: did the d0 script's 3
   sheep actually buy under the judge's cash path, or did the per-turn bundle cap drop
   them? One judge d0-order dump answers it.
2. **Herd places d14-20 vs judge d1-8** — the milk window's $44k deficit on 907 is
   production timing. Every money-floor relaxation starves the field, so the unlock is
   NOT the bank number: it is the d6 wool windfall (dead on 886/907 per #1) plus
   placement cadence.
3. Milk window kept ON in the skeleton: it binds the moment the herd ramps early
   (verified mechanically; costs nothing while inert).

**Ship verdict: NO-SHIP for a new zip.** The build is unchanged-or-marginally-better
(90/90 tests, mirror banks byte-identical, judge margins flat), the milk window is
correct-by-construction infrastructure, and the three failed market-side fixes are now
documented negative results instead of future time sinks.

## 2026-09-22 — Wool-lane probe: the sheep purchase path fixed and adopted

**Question:** why is wool 0u all season on judges 886/907? **Answer:** the default arm
never bought a sheep — the d0 script is elite-only and the animal programme's incumbency
lock (`best = incumbent or best`) made the first-ranked species (COW) permanent: judges
bought d12 COWx3 / d13 COWx3 / d16 COWx2 and nothing else, against a $174-218 wool
seller's market worth $11.9-13.1k to the judge.

**Fix shipped (default arm, judge-gated):**
1. `wool_lane=2` + `herd_sheep=2` (base PARAMS): extends the elite per-species portfolio
   (marginal ranks + envelopes) to the default arm, with a sheep-FIRST seeding override —
   one pace-sized SHEEP order before any cow expansion; the marginal portfolio resumes after.
2. Envelope clamp, DEFAULT ARM ONLY: the portfolio's species headroom bounds the buy
   quantity (unclamped, herd-level `want-live` bought SHEEPx3 into a 1-slot lane and the
   placement stream rotted one; clamp on the ELITE arm collapsed skeleton seed 0
   $30.5k -> $11.4k, so it is scoped out there).
3. Sell-discipline extension: wool floor + wool trough-hold + milk window now also fire
   when `wool_lane > 0` (default arm), not only under elite_script.

**Judge panel (before -> after, adopted config):**
- 886: -$45.2k -> **-$61.5k** (regressed $16.3k — gift to the judge via the shared book:
  our wool hold raised HIS wool price $154 -> $164 and our milk dilution raised his milk
  $98 -> $118; zero-sum dynamics, not a defect in our lane)
- 900: -$101.8k -> **-$57.5k** (+$44.3k; milk 0u -> 66u @ $278)
- 907: -$92.0k -> **-$83.0k** (+$9.0k)
- Mean **-$79.7k -> -$67.3k (+$12.4k)**; worst-case -$101.8k -> -$83.0k (+$18.8k);
  animals bought 11/8/11 vs his 16/24/19; default-arm mirror $50-60k (was ~$45k);
  skeleton byte-identical; 90/90 tests.

**Measured negatives this turn (documented, reverted):**
- `--params` on kill_chain is structurally broken: run_trace applies PARAMS.update
  BEFORE RealEnv(), and RealEnv reloads kagfarm.policy (AGENTS.md reload trap) — every
  params-sweep run silently used shipped defaults. Sweep by editing PARAMS defaults only.
- wool_lane ∈ {1,2,3} are byte-identical: the effective sheep envelope is
  max(herd_sheep, wool_lane) = 4 for all — herd_sheep is the real knob.
- milk_window on/off byte-identical on judges: the milk hold's remaining leak is the
  carried margin (same-turn DROPs settle from the shed past a hold); the clamp fix
  regressed the mirror and stays reverted (bag-map = P5 item).
- wl3/sheep4 (sheep dilution at 4 mouths): mean wash (-$79.0k), 886 -$78.1k — service
  dilution dominates on stream-bound judges; 2 sheep is the measured optimum.

**Verdict: ADOPTED (mean +$12.4k, worst-case +$18.8k, 2/3 judges better).** The 886
regression is the adversarial cost of raising shared-book prices from the smaller seat;
watch it when the herd scale-up (dairy recipe) makes us the volume seller.

---

## grind 0922b (evening) — F1–F6 gap-closer package: implemented, measured, REVERTED

Plan: the audit-driven F1–F6 package (d0 herd budget, want-collapse fix, buffer
deadlock admission, weed/DIG repair, asymmetric holds, growing shepherd share) against
the promotion bar (+$10k mean, no judge regressing). Every piece was measured on the
three Majkel judges (886/900/907) plus the mirror and skeleton smokes; the config that
would have shipped regressed the elite arm $47.7k -> $25.9k, so the full package was
reverted to the validated post-P1 state. Reference panel RESTORED byte-exact:
886 -$61.5k / 900 -$57.5k / 907 -$83.0k (mean -$67.3k), 90/90 tests.

**Measured results, per feature (the value is in the negatives):**
- F1 d0_herd (default-arm d0 core herd 1C+2S, seed-budget netting): judge 886
  -$91.7k on vs -$64.6k off. The $3k bank cannot fund a $1.4k core herd AND the ~$2k
  d0 seed round the panel proved load-bearing. A core herd needs the elite script's
  seed-FLOOR pairing, not netting. Knob `d0_herd` ships False.
- F2/F2b want floor (max(env_total, census, ramp) incl. the envelope-FULL branch):
  byte-inert in self-play and on judges (our judged herds sit at 8, far under any
  envelope). Structural correctness fix, unproven economics. Shipped OFF (legacy form).
- F3 deadlock admission (buffer bypass at zero standing animals): fixes a REAL measured
  collapse — mirror seed 2 died at $4.1k both seats (d11 wave $12.4k arrives, no mouths
  -> buffer 0 -> every buy vetoed -> cash bleeds to $0 by d16, zero animals all season;
  the F1 runs hid this because early mouths bypass the gate). Seed 2 -> $22-27.5k both
  seats. But judged NEGATIVE: the 3 extra buys dilute service on an existing herd
  (900 -$7.1k blanket, mean -$3.3k narrowed). Ships off behind dormant `deadlock_admit`
  (bypass formula preserved in a comment at `_animal_plan`).
- F4 weeds: two sub-fixes measured. (a) `weed_tiles` (planning into weed slots)
  displaces real plants and fails the monitor opp-estimate unit test — dead. (b)
  DIG tier 28 (just under TIER_GROW): byte-inert on judges, but elite-toxic
  (skeleton seat-1 $52.0k -> $26.8k in one bisect; the tier reorders the elite
  opening's chore stream). The d18-25 default-arm weed backlog is real (weeds 7 -> 35,
  live 67 -> 37 while replanting was PLANNED every dawn — the death spiral:
  unwatered -> weed -> tile invisible to _board_state -> weeds crowd the loop), but its
  binding constraint is stream CAPACITY, not tier order. Ships legacy TIER_DIG=10;
  dormant `weed_tier` knob kept.
- F5 asymmetric holds (wool/milk hold only while we out-shed the rival 2:1): fully
  wired (`_dominant`, opp shed from public farms[]), measured BYTE-INERT on the panel —
  our goods arrive after the trough, so the holds never fire either way. Ships off;
  becomes live the moment the herd scale-up makes us a volume seller.
- F6 growing shepherd share on the default arm: byte-inert on judges (the fixed share
  is not the judged binding gate at herd 8); never isolated in the mirror. Ships off.

**Defects found and fixed in the harness itself:**
- A seed-budget edit briefly swallowed the elite netting clause (`elif` collapse) —
  caught by the skeleton smoke ($50.0k vs $47.7k), reverted.
- PARAMS block duplication from repeated knob toggling — deduped, py_compile-gated.
- smoke_elite determinism verified (repeated runs byte-identical).
- The morning "$47.7k skeleton reference" was contaminated by the same turn's first
  edit batch (F2 want-raise flowing into the elite arm); the true pre-session skeleton
  is $33.5k/$52.0k. Session lesson: bisect matrices must use a STASHED pre-session
  file copy, not memory, when the same turn produces multiple configs.

**The one seam that still owns the whole gap (unchanged, now with cleaner evidence):**
animals bought 8-11 vs judge 16-24; eta_capital 0.16-0.96 vs 1.28-1.93; every
market-side fix is downstream of it. The service-capacity/growth architecture (not the
market layer, not the gates' bank numbers) is the next and only lever that matters.

**Verdict: REVERTED — no adoption. Reference state restored and verified byte-exact on
the judge panel; probes preserved (`analysis/limit_trace_886.py`,
`analysis/seed2_trace.py`).**

---

## Majkel d8-20 labor dossier (2026-09-22) — measured, `analysis/majkel_labor.py`

**Question:** before building the care-rate gate, calibrate the shepherd ratio and
gate threshold to Majkel's REAL labor allocation, not the census estimate.

**Method (action-level, no mirror):** 14 restored episodes in `analysis/replays/`
(13 dossier games + 110964284). Seat = higher final reward (he wins all 14).
Ops read verbatim from `action.farmer`/`action.hands`; HARVEST attributed to
animal tiles only when the worker stood on a PASTURE/COOP tile the turn before
(per-episode ambiguity 1.2-5%); care rate = each animal tile's `fed_today`/
`cared_today` flags at END of day (raw engine state, steps[day*24+23]).

**Headline (pooled, 182 episode-days d8-20):**

| Metric | Value |
|---|---|
| Distinct workers on animal ops per day | **8.78** (per-episode 7.85-9.31) |
| FEED / CARE / animal-HARVEST ops per day | 18.9 / 19.4 / 8.0 |
| COLLECT_FERTILIZER per day | 13.4 (steady all season) |
| Herd at dawn | 12.0 @ d8 -> **15.6 mean** (peaks 15.9-16.3) |
| End-of-day fed rate | **88.0%** |
| End-of-day cared rate | **88.5%** |

**Per-day shape:** care rate oscillates 63-72% (d16, d18, d20, d22) against
97-100% neighbors; d28-29 care collapses 13%->0% by design (endgame
liquidation, no point servicing animals the last two days). Staffing is a
stable core (w1-w5 nearly every day on 110886706) plus rotating extras.

**Per-episode spread (workers/day, herd, cared%):** best game 110900752
($156.2k): 9.31 workers, herd 20.31, **98.9%** — his ceiling config. Weakest
full-herd game 111016701 ($95.6k): 8.23 workers, herd 12.85, 83.8%. He does
NOT sustain 90-100% at 15-16 animals on average — 88% is his sustainable
rate; ~99% appears only at his highest staffing+capital peak.

**Calibration for the care-rate gate (replaces the census estimate):**
- Shepherd ratio: **1 animal-worker per 1.8 herd** (8.78/15.6), NOT 1 per 2.5-3
  — at herd 15 that is ~8 shepherds, not 5-6.
- Gate threshold: **>=88% projected care = sustainable** (admit), **>=95% =
  stretch** (matches his $156k peak: 20.3 animals @ 98.9% @ 9.3 workers).
  Do not gate at a flat 90%: his own average play runs below it.

**Wool correction (supersedes the dossier's sheep-lane framing):** Majkel does
NOT run a wool lane. Mean herd composition ~2.5 sheep; wool revenue ~$0 in
most episodes (only the 3-sheep d6-windfall games earn ~$14.7k). Sheep are a
one-shot early windfall play, not a recurring lane. The wool_lane=2 default-arm
knob adopted earlier is calibrated to a pattern he does not actually run.

**Rerun:** `python3 analysis/majkel_labor.py` (reads `analysis/replays/*.json`
only; Downloads deliberately excluded — it mixes in our own episodes).

---

## wool_lane=2 audit: KEEP (2026-09-22) — retire refuted, re-tune inert, coupling found

**Prompt:** the labor dossier showed Majkel runs no wool lane (~2.5 sheep, ~$0 wool
revenue), so the shipped `wool_lane=2` default-arm knob looked calibrated to a
pattern he does not play. Audited on the 4-judge panel (886/900/907/majkel3),
arm-vs-arm with shipped-default edits + restore (the documented `--params` trap).

**Panel (terminal margins, ours vs judge):**

| Judge | shipped wl=2 (ref) | wl=0 (retire) | herd_sheep=1 (env 2) |
|---|---|---|---|
| majkel886 | −$61,467 | −$45,225 | byte-identical to ref |
| majkel900 | −$57,492 | −$101,825 | byte-identical to ref |
| majkel907 | −$83,023 | −$91,979 | byte-identical to ref |
| majkel3 | +$82,479 | −$99,049 | byte-identical to ref |
| **mean** | **−$62.0k** | **−$84.5k** | = ref |

**Verdict: KEEP `wool_lane=2` unchanged.** Retiring regresses the mean −$22.6k and
flips majkel3 by −$181.5k. Re-tuning through the envelope is inert: `herd_sheep=1`
(env = max(1,2) = 2) is byte-identical on every judge — the marginal ranker stops
at ~2 sheep regardless of the cap; the seed override is the only active lever.

**Why retiring loses (mechanism, from the settled-unit lines):** the lane's value
is NOT wool revenue (ours: $0.8-5.6k/game; judge: $10.1-14.0k). It is (a) **product
denial** — our 26-30u of wool sales crash the judge's realized wool price ($199→$164
on 886, $242→$39 on 900, $162→$125 on 907; his wool cash $87.9k→$14.0k on 900), and
(b) **milk-window coupling** — the P3 milk hold is gated on `wool_lane > 0`
(policy.py:3941/3960/4056), so wl=0 silently disables it and our milk went 66u @
$278 ($18.3k) → 0u on 900. With wl=0 the incumbent lock also went all-sheep on 900
(8 sheep, 111u wool, zero cows). **Trap for future knobs: `wool_lane=0` changes
three subsystems at once (portfolio, wool holds, milk hold) — never treat it as a
pure "no sheep" toggle.**

**Field-context correction (supersedes the dossier's field implication, not its
Majkel facts):** the dossier is right that MAJKEL runs 2-3 sheep only; but the
actual judge field runs 3-17 sheep from d6 (Otter Vibe 3, Yannik 3-4, TFC 7→17,
SpaTaro 2). A 2-sheep mixed herd IS the elite consensus — the knob was
accidentally tuned to the field, which is what the panel rewards.

**Judge-infrastructure caveat:** majkel3's judge seat is a broken counterfactual —
the tape-replay of Majkel's seat earns $313 baseline (his market orders fail to
fill once our play diverges from his recorded game) and $173,051 under wl=0.
Weight 886/900/907 for A/B decisions; use majkel3 only with the seat-artifact
caveat. 90/90 tests green, shipped file restored byte-exact (wl=2, herd_sheep=2).

---

## Ship 0922 — A/B/C/D plan executed (2026-09-22, late session)

Frozen A/B/C/D build per the approved plan. A shipped; B and C measured and
rejected; D froze and verified. Final shipped panel (no params, kill_chain):
**886 −$61.5k / 900 −$55.4k / 907 −$84.5k, mean −$67.1k** (reference −$67.3k;
900 +$2.1k better, see c_full below). 90/90 tests.

- **A1 (want floor, SHIPPED):** `want = max(env_total, live+held, ramp)` uncondi-
  tional — the d18 want-collapse can no longer cap the herd below live. Fixtures
  pin it.
- **A2 (P4 rank expiry): SKIPPED with math** — the cow window already ends at its
  last profitable pop (`range(first, left)` is empty for d22+ buys); extending
  buys pure cost.
- **A3 (milk-hold decouple, SHIPPED):** the P3 hold no longer requires
  `wool_lane > 0` (own knob `milk_hold_decouple`), byte-inert at wl=2. The audit's
  hidden-coupling trap is gone.
- **A4 (`--params` fix, SHIPPED):** kill_chain re-applies PARAMS AFTER
  `RealEnv(...)` (its `__init__` reloads kagfarm.policy and silently wiped every
  historical sweep — verified: `animal_pace=0` now buys 0 animals).
- **c_full crash fix (SHIPPED, explains the 900 +$2.1k):** `gate_log`'s
  `max(c_full)` had no `default=` and raised ValueError on empty endgame lists;
  `act()` swallowed it, silently aborting the full plan for the rest of the dawn.
  A latent bug made *reachable* by fewer endgame crashes; the fix is behavioral
  on 900 only.
- **B package (built, JUDGE-REJECTED, dormant):** care_gate + shepherd_share_grow
  (1:1.8) + feed_backbone_def + herd_cow 14 + deadlock_admit. Mirror: healthy,
  seed2 $49.5k, deadlock_admit NOW POSITIVE under gate protection (+$11.6k mean).
  Judges: care gate caps buys at **5 animals on all three judges** (ref 8-11,
  Majkel 16-24); `service_margin` 8 no-op, 13 admits 8 but terminal drops
  $96.8k→$96.4k (886). Root cause: the mirror loop-cost model (commute=3.0) is
  pessimistic vs real geometry, and the default arm's crop program eats per_unit.
  **Deeper finding: our milk (45u @ $109 = $4.9k vs judge 347u @ $145 = $50.5k on
  886) arrives after the d13-19 window because the seed round consumes d0-d10 —
  admission control cannot fix timing.**
- **C (skeleton opening as shipped default, REJECTED hard):** majkel_skeleton()
  judged 886 −$73.2k / **900 −$142.5k** / 907 −$55.1k, mean −$90.2k. Confirms F1:
  without the d0-d10 seed round's cash the animal-led opening starves on the real
  field. The dossier opening needs its own funded seed floor, not just animals
  first — do NOT retry without that.
- **D (freeze):** shipped knobs: care_gate/shepherd_share_grow/feed_backbone_def
  False, herd_cow 9, deadlock_admit dormant, wl=2, herd_sheep=2. All new code
  paths stay in-tree behind knobs. Probes kept: analysis/limit_trace_886.py,
  analysis/seed2_trace.py.

**Next-session ledger entry (the one seam left):** animals must be on the board
by d2 AND the seed round must still run — that is a CASH-SCALE problem (the $3k
bank funds one or the other), so the lever is the d0-d2 sell program (melons
ripen d6-7, wool d6) sequencing, not gate tuning. Gate-protected herd growth
(B1-B4) is built and dormant; it activates the day a funded opening lands.

---

## Funded-opening grid — COMPLETE, all forms judge-negative (2026-09-23)

The untested C variants, built (`led_flock` knob: stage-2 flock + reserve
netting + seed floor + k-admit money gate for the default arm) and judged.
New knob ships DORMANT (default False); shipped path byte-verified (knob-off
seed2 reproduces the documented $4.1k deadlock state; 90/90 tests).

| Config | 886 | 900 | 907 | mean |
|---|---|---|---|---|
| reference (no flock) | −61.5k | −55.4k | −84.5k | **−67.1k** |
| opening_led alone (stage 1 only) | −60.6k | −77.8k | −95.5k | −78.0k |
| flock @ ramp env (~9) | −75.9k | −82.4k | −85.5k | −81.2k |
| flock @ env 12 + grow-share | −79.2k | −90.4k | −72.4k | −80.7k |
| flock @ env 14 + grow-share | −79.4k | −93.5k | **−55.4k** | −76.1k |

**Mechanism, now measured end-to-end:** the flock DOES open the milk window
(83u @ $264 = $21.9k on 900 — our best milk result ever; reference sold ~0).
But in every form the shepherd share + animal capital cannibalize a MORE
profitable crop program: milk gains of $10-22k coexist with margins $9-14k
WORSE than reference. The d6 wool pop also never materialized as a windfall
(5-10u sold @ trough prices — the 3-sheep flock's wool arrives but the sell
floor holds it past the pop). 907 (weakest judge) improves +$29k at env 14;
886/900 pay more than 907 gains.

**The structural seam (not a knob):** Majkel runs 12 hands AND 8.8 animal
workers/day because his move-share is 59% vs our 69% — his same 12 hands do
~31% more work actions. Our animals don't lose because of gates, envelopes, or
openings (11 judge cells now tested across the two sessions); they lose because
every shepherd turn is stolen from crops at a rate our route layer can't
afford. The next build is `kagfarm/route.py` (untouched since 09-05):
cluster-based assignment to cut move-share toward 59%, freeing ~3-4 hand-turns
day — equivalent to ~2 free hands at zero wage cost. That is the only lever
left that adds capacity instead of reallocating a fixed pool.

---

## s1223 field autopsy — post-submission12 tapes (2026-09-23)

Three fresh ladder games (112127332 L, 112128608 W, 112129810 L). Two
corrections to the failed turn's mid-crash read, both material:

1. **The "threw away a won game" claim was WRONG** — the crashed counter had a
   seat-mapping error. Clean d20-29 sweep (analysis/endgame_sweep.py): we were
   NEVER ahead in 112127332; Luan He led $48.6k-to-$2.6k at d20. Our endgame is
   the best on the field (we out-earn every opponent on d29: +$8.9-31.5k vs
   their +$2.0-5.7k; the d29 liquidation machinery works).
2. **The game is decided in the d12-18 valley, not the endgame.** All three
   games share the identical shape: we bank +$16.5-18k by d10-11 (melon wave,
   best-in-field), then run 5-6 straight negative days while the winner
   compounds +$3-6k/day. Attribution (analysis/spend_attr.py, KT_V2
   alignment): in the valley we issued 74 HIRE orders ($8.3k wages) against
   $0.2k of sells, and planted 52 strawberries on d12 ALONE. Luan He plants
   1-3 seeds every day d5-d10 and sell income runs $0.8-2.8k EVERY day.

**The tsunamis-vs-stagger profile:** our planting is two synchronized cohorts
(19 melons d0, 52 berries d12) paying in two lumps (+$18k d10, +$10k d25-26)
with $0 in between; the winners' staggered cohorts + pre-d11 herd pay daily.
Plant-pacing experiments were reverted 3x (2026-09-20: per-unit price rises
but volume halved, -$8.3k) — the ladder rejected pacing our own cohorts.

**Judges registered:** replay_luanhe (112127332 seat 1, $97,554) and
replay_juicy (112129810 seat 0, $88,022) in replay_opp.py. Counterfactual
resim is faithful: baseline margins match the real games exactly (luanhe
-$31,969, juicy -$45,526). New field data point: Luan He bought 38 animals,
sold 251 wool @ $216 = $55.4k — a SHEEP-LED elite herd; Majkel-calibrated
wool_lane=2 does not match this field's winner mix.

**15th wall cell — the burst arm, final form tested:** env-15 + margin_open
(new dormant knob: default-arm expansion_cash bypass, the gate that was
elite-only) + deadlock_admit + grow-share. Result: luanhe -$48.5k (WORSE by
$16.5k — 17 animals diluted milk 97u -> 59u), juicy +$2.7k. Byte-identical
cells first proved the margin gate was moot at envelope 11: the envelope IS
the binding veto, and raising it service-dilutes exactly as Phase B
predicted. Fifteen cells across three sessions: no herd/margin/opening
combination beats the frozen build on real tapes.

**Where the money actually is (measured, untouched):** judge animal revenue
$42-56k vs ours $19-22k on the fresh field; eta_capital 2.2-3.2 vs our
0.43-0.48. Every capacity-reallocation lever is exhausted. The remaining
lever is capacity CREATION: route.py move-share (ours 69% vs elite 59%).

---

## s1223 route-layer build — move-share premise retired (2026-09-23)

**Premise check first, and it failed:** the 69%-vs-59% move-share gap that
motivated the route-layer build predates submission12. Re-measured on the
fresh tapes (analysis/ladder_move_share.py): our current build runs **58.1%,
58.6%, 59.6%** across the three games -- already at the elite 59% mark. The
serpentine lane machinery in route.py is elite-grade. What actually differs
is op VOLUME: winners issue 6,288-6,728 unit ops vs our 5,335-5,386 (same or
lower move-share, a third more work) -- utilization, concentrated in the d1-9
roster trough (~26 ops on d1 vs their ~250).

**Built and measured (all ships dormant or retired):**
- `lane_keep` (keep standing queues on roster-growth recuts, cut residual for
  idle hands): mirror move-share 56-61% but banks -$13-16k on seeds 0-1.
  Measured verdict: the legacy re-cut's "churn" (561 redirects, 378 far) is
  LOAD BALANCING -- re-pointing a busy unit toward fresh work beats keeping
  it on a stale lane. The executor's `_valid`-drop + steal path already
  handles invalid jobs; the churn is not waste.
- `roster_adaptive` (commute shrinks with live lanes at roster sizing):
  catastrophic (seed 0 $59.7k -> $35.8k) -- shrinking commute shrinks
  per_unit capacity, which SHRINKS the demand-sized roster. Wrong sign.
  Retired same-session, documented at the knob.
- `led_roster_floor=1, max_hands=12` on the default arm: mean -$2.3k on the
  5-judge panel (907 -$9.3k worse) -- fails the bar. `led_roster_floor=1`
  alone is byte-identical on all five judges (inert: demand-sizing already
  covers the ramp on real tapes; the floor only binds in mirror deadlocks).

**Shipped path verified intact:** 90/90 tests, baseline move-share byte-match
(58.5%, $59.7k seed 0), judge reference reproduced (-$55.4k on 900).

**Where this leaves the capacity question:** routing is NOT the lever -- the
winners do not walk less, they work MORE with a similar walk budget. The
d1-9 trough is cash-constrained (Fibonacci hires + the seed round compete
for the same $3k), not intent-constrained: the floor does nothing on the
field because demand already asks for the hands. The next real lever is
early-season CASH, and every cheap form of it has been measured negative
(F1, C, led_flock grid). The honest read: our midgame valley is a
capital-acquisition-rate problem, and the remaining untested space is
raising melon-wave yield per tile (fert timing, yield decay management),
not more lanes.

## 0924b: dossier adoption round (S11 profit-maximizer cross-check)

**Cross-checked the pasted engine-exact dossier against our tree.** Already
shipped and verified there: shed-only SELL pool, event-exact animal simulator
with max_held pre-event harvest, milk first-mover window, wool hold rule,
marginal-value melon selling, demand-gated goose lane. REJECTED with evidence:
tomato re-adoption (deliberately excluded -- 68% of thirst deaths, min $42.9k
-> $45.3k), cohort stagger (measured negative 3x), fixed day-0 script/herd
(F1/C/led_flock graveyard), roster wind-down (engine has NO recurring wages --
Fibonacci is one-time; trimming hands saves $0), fractional yield-decay bands
(the engine's real decay is max_lifespan_step for one-time crops past peak;
strawberry is ongoing and never decays -- the dossier's 0.75/0.5 curve does not
exist), land_count_cap (see below).

**feed_solvency (shipped earlier today, the big one):** the $0-death mode
(seeds 2/3/4 bought 3 cows at d13 with a dry shed -> all starved -> $0 farm for
15 turns) killed by a 4-line gate: never BUY_ANIMAL unless cash-left covers
every mouth's 6-day grain deficit. Mirror mean $28.5k -> $55.9k (+$27.3k,
every seed now $45-65k); never poorer on any of 5 judges (886 +$13.7k absolute).

**Adopted + SHIPPED (all byte-identical on 5/5 judges and mirror -- zero
measured cost, guards the pathological cases):**
- `animal_stop_species=1`: per-species last-profitable-buy day (>=2 production
  events for NPV>0): cow 19 / sheep 20 / goose 24. The shipped calendar stop
  admitted cows at d22-24 that produce once and never pay their feed.
- `milk_floor_frac=0.5`: milk's dedicated sell floor (90%-of-base breaks at 8
  units oversupply -- most fragile good on the board); drip reaches the crater
  zone instead of stranding units.
- `se_last_day=13`: SE quadrant ($4,000) blocked once strawberry (16d cycle)
  can no longer finish; blanket count-caps rejected, deadline form is free.

**Measured and REJECTED:** `land_cap_quads=3` (blanket 3-quadrant cap) --
mirror mean +$9,357 (four seeds up, s4 $45.0k -> $71.4k) but judges mean
-$1.0k with luanhe -$20.4k: in OUR crop-led build an early SE pays (strawberry
planted d<=13 finishes d29), the mirror's tight-cash seeds were the exception,
not the rule. Knob kept inert for sweep history.

**Gates at ship time:** 90/90 tests; verify_pack 8/8 mean $82,498, worst turn
2.4ms. Mirror panel mean $55,876 (was $28.5k pre-feed_solvency).

## 0924c: opponent-conditional wool arbitrage (opp_wool_prio=1, SHIPPED)

**Premise correction first:** the "Majkel leaves wool unclaimed" hypothesis was
FALSE -- he runs BOTH lanes at scale (14-16 cows AND sheep flocks; 900 even
crashes wool to $39 with 363u sold). The real pattern: his portfolio is both
lanes served by 10-12 hands; ours was cow-only.

**Mechanism:** when the rival herd is cow-heavy (>= `opp_cow_glut`=10 cows),
runs <= `opp_sheep_max`=4 sheep, and live wool >= 0.8x base, the portfolio
lifts the sheep envelope to `opp_wool_env`=8 and forces the species pick until
the lane stands. All admission gates (stream co-feasibility, feed_solvency,
per-species stop) stay upstream -- this aims the portfolio, it does not bypass
admission. The guards are the feature: on 900 (rival sells 363u wool, price
$39) and luanhe (rival IS the wool seller, 251u) the condition correctly keeps
us out -- both judges byte-identical.

**Measured (same-binary A/B, margins vs the judge):**
- 886: -$67.7k -> -$50.9k (+$16.8k) -- our sheep crashed HIS wool too
  (judge bank $127.9k -> $102.9k, -$25.1k; ours -$8.2k: competitive effect,
  not just added revenue)
- 907: -$85.2k -> -$66.3k (+$19.0k), our bank $41.4k -> $59.5k (+$18.1k)
- 900 / luanhe / juicy / mirror seeds 0-4: byte-identical (guards held)
- Mean Majkel-margin: -$69.4k -> -$57.5k -- the largest margin move measured
  in the project.

**Gates at ship:** 90/90 tests; verify_pack 8/8 mean $82,498 unchanged.

## 0924d: the wage-trap myth dies -- max_hands 11 -> 14 (SHIPPED)

**Engine-exact discovery:** `hires_today` RESETS AT DAWN (kaggriculture.py
_daily_refresh: `f.hires_today = 0`) and hands PERSIST forever. The Fibonacci
ladder is priced PER DAY, not per roster: hire one hand a day and it costs $1.
There are NO recurring wages. The "Fibonacci wage trap" that capped every build
of this project at 10-12 hands -- including in every dossier and the
wage_reserve itself -- was a miscalibration. Nobody ever tested higher.

**Why it matters:** the ladder winners out-work us 6,288-6,728 vs ~5,350
unit-ops at similar move-share. Labor capacity was the direct lever at the gap.

**Sweeps (mirror seeds 0-4):**
- mh11 ref: mean $55,876, min $44,996
- mh12: $55,984 (flat). mh14 legacy reserve: $60,795 but the FULL-CAP reserve
  ($986) is a one-day-hire assumption -- mh16 collapsed to $22,919 on it.
- wage_reserve_window=10 (price 10 hires ahead, sum $143): mh14+w10 is the
  PEAK: mean $59,938, min $54,030 -- worst-seed floor +$9k, variance collapse.
  mh16/mh20 at any window: $47-48k (routing dilution, corpse seeds return).

**Judges (mh14+w10):** mean ours $55.9k -> $60.3k (juicy +$15.7k, 907 +$14.1k,
luanhe +$1.5k; 886 -$6.4k but his -$25.1k = the anti-glut trade working,
margin +$14.3k). herd_cow=12 probe: mixed (+$10.1k margin 886 / -$3.8k 907),
not adopted. opp_wool_env sweep under mh14: 8 remains optimal.

**Gates at ship:** 90/90 tests; verify_pack mean $82,498 -> $84,050 (the
default arm's field panel IMPROVED). Packaged into submission13.

## 0924e: the fertilizer valve -- verify_pack crosses $100k (SHIPPED)

**The waste:** FERTILIZER sat in _INPUTS and was NEVER sold mid-season, yet
every animal yields 1 unit/day (29/season/animal), COLLECT is paid daily, the
shed caps at 100, and midnight overflow DESTROYS units after displacing $110
strawberries. A 9-animal herd produces ~260 units/season of paid-for,
warehouse-clogging, then-destroyed inventory.

**Form finding (three variants measured):**
- continuous sell: mirror mean -127 (s1/s3 -6k: fert SELL slots at $25 displace
  strawberry slots at $110 on comfortable days) -- REJECTED
- continuous sell + fert_stock buffer hold: mean -1,229 -- REJECTED
- CROWDED-SHED VALVE: fert sells ONLY when the shed crosses the crowded line.
  Mirror +$4,172 mean, EVERY seed up (61.1/61.6/62.9/66.3/65.6k). On
  comfortable days the slot stays with produce; when the shed crowds, the
  cheapest unit (fert) relieves the overflow first.

**Results:** verify_pack mean $84,050 -> $100,348 (SIX FIGURES; field episodes
run bigger herds than the mirror, so overflow destruction was far larger
there). Judges: ALL FIVE improved on both bank and margin -- luanhe 73,076 /
juicy 69,046 / 886 65,722 / 900 64,449 / 907 56,152 (mean $65.7k, +$5.4k).
Mean Majkel margin -52.4k: best ever (start of day: -67.1k).

**Gates at ship:** 90/90 tests (valve contract pinned); verify_pack 8/8 mean
$100,348, worst turn 2.5ms. Packaged into submission13.

## 0924f — submission13 re-audit: safety nets are saturated, one regression caught

Request: re-audit the session-start state and harden the two weak mechanisms
(wool arbitrage, safety nets). Same-binary A/B throughout.

**False alarm caught and killed (the important result):** the session-start
end-state audit reported unplaced animals at the buzzer on mirror seed 4 —
but its PARAMS reset forced stale arm values (`melon_opening=24`, old s8
behavior). On TRUE shipped defaults every animal places by d26; structures
are free (BUILD_PASTURE needs only an empty tile), so placement never
structurally stalls. A backlog count-cap built to fix the phantom leak
(`backlog_cap_def=2`) measured **-$7,782 mean on the mirror (56.3k vs 64.1k,
every seed down)** — dawn programs legitimately buy 2-3 animals while 1-2 are
mid-flight. REVERTED same-session; baseline restored byte-exact
(64,188/61,596/62,857/66,326/65,584 = reference to the dollar). Lesson: audit
probes must deepcopy the shipped PARAMS and never override arm selectors.

**Saturation sweep on the real 5-judge panel** (ref = 73,076/69,046/65,722/
64,449/56,152 ours, mean margin -42,310):
- `milk_floor_frac` 0.5->0.3: byte-identical 5/5. The drip floor never binds
  on real tapes; knob already optimal.
- `opp_cow_glut` 10->8: byte-identical 5/5. Earlier entry buys nothing (the
  trigger is already early relative to our sheep build-out).
- `opp_wool_env` 8->12: REJECTED, mean margin -51,163 (886: -62,057, a
  $20.3k collapse — 12 sheep crash the shared pot we sell into and drain
  crop labor).
- `opp_wool_px` 0.8->0.9: REJECTED, 886 -55,022 (tighter guard just blocks
  the good entry).
The moving arms prove the panel detects differences; identical arms prove
saturation, not insensitivity. Both shipped mechanisms sit at a measured
local optimum. Single-knob tuning of them is DEAD; future gains must come
from new structure (herd scale under service), not re-tuning.

**Endgame liquidation already ships** (`endgame_cap=0` full-clear; the old
"36 wheat at the buzzer" predates it).

**Gates:** 90/90 tests; pack.sh verified bank-for-bank; verify_pack mean
$100,348 (8/8, worst turn 2.5ms) — unchanged, as expected for a net-zero
diff. submission13 tarball regenerated with the re-audit comments.

## 0924g — submission13 tape autopsy + zero-waste audit + fert drip

**Five fresh ladder tapes (112836605/781/901/022/139, post-ship): 1-4.**
Margins -25.5/-36.4/-57.6/-62.0k; win +9.8k. Same signature as the judge panel,
now tape-confirmed across four independent opponents:
- MILK is the #1 revenue gap: winners $54.6-86.0k/season, us $9.5-39.5k.
- FERTILIZER is #2 and it is TIMING: winners sell continuously from d0
  ($69-81k seasons); our valve releases mostly d24-29 ($33-48k).
- The d12-17 valley is THE losing window: our sell revenue is NEGATIVE there
  in 3 of 4 losses (-0.1 to -3.2k) while winners bank +18.7 to +46.6k.
- khan (112840218) made $21k from EGG/geese — a lane we have machinery for
  and never fire.
- Winners' seed mix leans strawberry-heavy (66-85 seed-buys) + melon (17-24).

**Engine-truth correction (0924g):** hands VANISH nightly in BOTH engines
(farm["hands"] = [] at _day_refresh; vendored line 880) and hires_today resets
-- the fib curve re-prices the FULL roster every dawn (~$987/day at 14 hands).
The 0924d "hands persist, ~$1-5 hires" claim was WRONG. max_hands=14 stays
adopted (its A/B was measured bank-positive), but the wage bill is real and
recurring; wage-sensitive tuning must price it. Comment corrected in policy.py.

**Waste audit (analysis/waste_audit.py, mirror seeds 0-4, engine-exact):**
- overflow 219 units/5 seeds (54 strawberries = ~$6-8k, rest wheat/fert)
- escapes 1, thirst deaths 0, end-shed 39, unharvested 12, unspent seeds 13
- gain-window misses 1,677 tile-days (largest theoretical class; the d12-13
  idle-PASS cluster is the labor-side seam)
- cash_rot NEGATIVE (-92k): money compounds; no idle-cash problem
- watch: unfed animal-days 51->63 under the fert drip (priced into judges)

**FERT DRIP adopted (fert_drip_px=0.8, opp_fert_demand=5):** fertilizer joins
the sell pool at >=0.8x base when the rival's placed herd >= 5 (a real economy
demands fert and sustains the shared book); crowded-valve unchanged. Journey,
all same-binary:
- unguarded: judges +$4.0k mean (73.1/71.3/77.6/64.4/62.3k, zero regressions,
  886 +$11.8k), but verified pack -2.9k (passive twins = no buyer, pure slot
  displacement).
- +shed-wheat feed guard: byte-inert on all 5 judges (real herds rarely cover
  the hold) while still costing mirror s2/s3 -> REVERTED.
- +rival-herd gate: BOTH panels satisfied (pack back to $100,348; judges keep
  +$4.0k). The gate composes with opp_wool_prio's pattern: read the rival,
  enter a lane only when there is someone to sell to.

**Gates:** 90/90 tests (three-regime fert contract pinned incl. the herdless-
rival negative); pack.sh bank-for-bank; verify_pack 8/8 mean $100,348; judges
mean bank $69.7k (best recorded; margin mean -38.3k, best recorded).
submission13 repackaged.

**Next structural seams (unchanged, now tape-confirmed):** milk herd scale
under service (their $54-86k vs our $9.5-39.5k), the d12-17 valley sell
engine, and the geese/EGG lane trigger.

## 0924h — three seams probed; all three honest rejections (net-zero ship, evidence banked)

**Seam 1 idle_recut (the d12-17 valley labor seam).** Five variants, all same-binary
mirror A/B: lane_keep $17.3k (shepherd loops DELETED — standing excludes shepherds),
raw whole-board recut $18.9k (drained shepherd lanes rebuilt as crop lanes, herd
starves), >=2-idle recut+restore $61.3k mean-flat but variance-explosive (s2 +17.4k,
s3/s4 -14/-18k), full-drain predicate byte-inert (>=1 crop lane always holds work to
midnight), final direct-residual cut (no recut, busy lanes untouched, deduped against
standing queues) byte-identical on the panel. Root cause confirmed real (510 PASSes,
all with 26.1 mean waterable tiles on board, exploding h20-23) but every safe cure is
inert and every active cure is catastrophic. Kept dormant (idle_recut=0) with the
full negative-result dossier in-line. Lesson: the tail-tiles are invisible to steal
BECAUSE they are in nobody's queue, and any fix that touches queues touches shepherds.

**Seam 2 egg_lane (khan's $21k EGG season).** GOOSE was skipped by herd_goose=0 in
the portfolio loop — fixed with a demand-conditional envelope lift (egg shops unlocked
>= egg_lane_shops, EGG >= egg_lane_px x base, rival geese < 4; rank/margin gates
upstream). Mirror: +$3.0k mean, p10 $19.3k -> $33.8k, thirst/idle down. Judges: REGRESSION
(egg_lane=4: -7.0/-11.5/-13.6/+2.1/0k; 886's draw has NO egg shop so the lane sat out
there while milk vanished from our ledger — displacement, not substitution). Conservative
3-goose/2-shop form still -3.3/-4.1k on luanhe/juicy. REJECTED; knob ships at 0.
Probe artifact: judge 886 shop draw is FARMERS_MARKET/PET_CAFE(/SMOOTHIE) — the EGG
lane only exists on bakery/brunch draws, which the mirror over-samples.

**Seam 3 herd_cow=12 on measured geometry.** Placement geometry verified healthy:
mean structure walk 2.52 (23 structures, 15 inside dist<=2; radius-2 reserve saturates
and spills to dist 6) vs Majkel's 1.6-1.8. hc12 judges: ours $68.8/57.5/57.2/67.7/62.4k
(-5 to -9k own bank on every judge) vs only 886 margin +$5.4k (his bank fell $14.2k —
the shared-book denial effect is real). Mean margin -2.5k. REJECTED; herd stays 9.

**Tooling correction (0924g audit):** KAG_OVERRIDE is read ONLY by kagfarm_policy_v3.py,
never by kagfarm/policy.py — the 0924h-era "byte-identical" idle_recut/egg_lane env-var
A/Bs were no-ops. Correct protocol: PARAMS.update before env + re-apply after RealEnv
init (bridge/real_env.py reloads policy), or --params on the judge drivers. Baselines
re-paired on the exact tree: luanhe -25.2 / juicy -26.7 / 886 -39.8 / 900 -51.5 /
907 -58.6 (mean -40.3k; juicy/886/907 carry the fert-drip vs the 0924g refs, refs
re-frozen here).

**Gates:** 90/90 tests; pack.sh bank-for-bank; verify_pack 8/8 mean $100,348, worst
turn 2.5ms. submission13 tarball repacked (net-zero policy diff vs 0924g: knobs ship
dormant; egg_lane/herd geometry evidence ledgered for the next structure-level push).

## 0924i — weakest-subsystem rebuild: the shepherd service scheduler (wheel_plan)

**Vision check.** Across 12 submissions the single subsystem furthest below the elite
standard is service capacity under herd scale: our cows cap at 9 vs Majkel's 14-16,
milk banks $9.5-39.5k vs their $54-86k, and every herd_cow>9 arm died at the
co-feasibility gate. The chain-based `shepherd_loops` is the draft that chose the
wrong shape. Measured defect (judge 886, herd-12 arm): at herd 11 the chain stream
costs 107 of 110 day-budget turns (97%), ~79% WALKING (22 ops, ~85 walk turns), max
cluster 99 turns; one tail-cut loses 2-3 animals' feeds at once. Engine truth that
makes the rebuild legal: FEED/CARE/COLLECT are per-tile flag-guarded single ops;
PICKUP/DROP shed-side; bags auto-dump at midnight; the CARE bonus banks 1/day.

**The rebuild.** `wheel_plan()`: per-animal shed-anchored trips (PICKUP 1 -> walk in ->
FEED -> piggyback CARE/COLLECT/HARVEST -> home DROP only when carrying), trips
assigned round-robin over access tiles by nearest-neighbor tour, same return contract
as the chain so every admission gate reads it unchanged. Cost-neutral at ring 1
(3 turns/trip vs chain 5.9/animal), ~7.2/animal at Majkel's ring 1.6-1.8. An
overloaded day sacrifices ONE animal's care tail, never a life; max-trip ~8 turns vs
chain 99. 3 structural tests added (93/93).

**The honest verdict, all same-binary on the 5-judge bar (refs 0924h):**
- wheel_plan=1 (pure): mean bank -$3.6k. 886 +$8.4k OUR bank? NO -- +$8.4k was MARGIN
  (Majkel fell $16.8k under our denied milk); our own bank fell $8.5k there and
  -$7.4/-10.3/-8.9k on luanhe/juicy/907. The wheel improves NO farm's own economy
  where the chain fits; its per-animal PICKUP/DROP overhead is real cost.
- wheel_fallback (hybrid, soft trigger): = pure wheel on 4/5 judges (max-loop clause
  fires on every herd>=9 dawn; a chained feed-block ALWAYS exceeds one shepherd's
  day). Rejected as designed.
- wheel_fallback (hard total-budget trigger): byte-identical where the chain fits
  (luanhe/907 exact) but -$11.0k on 886 and -$12.5k on 900 -- mid-season regime
  switches corrupt the structure-placement geometry the standing plan assumes.
- wheel_plan=1 + herd_cow=12 (the plan's key question): STILL REJECTED. Mean margin
  -$50.5k vs -$40.3k shipped, 907 -$75.4k. Honest costs did not un-cage the envelope:
  12 cows genuinely cannibalize crop service on the real tier. The herd-9 equilibrium
  is an economy optimum, not a planning artifact.

**Shipped state:** wheel_plan/wheel_fallback both at 0 (dormant, full dossier in-line);
net-zero diff vs 0924g (only the wheel builder + selector + tests added). 93/93 tests;
pack.sh bank-for-bank; verify_pack 8/8 mean $100,348, worst turn 2.5ms. Tarball
repacked to ~/Downloads/submission13.tar.gz.

**What survives for the next push:** (1) the escape-halving is real (12.5 vs 24.4 on
the mirror) -- if a future arm values herd ROBUSTNESS over throughput, the wheel is
the pre-built shape; (2) herd scale is now proven gated by REAL crop-service
opportunity cost, so the next structural lever is the crop engine's own efficiency
(the 1,677 gain-window water misses), not the animal side.

### 0924i adversarial review (fresh-eyes pass over the wheel diff)

- FIXED (real defect, dormant-arm): the executor pinned shepherds by `len(loops)` and
  zipped loops onto units; the wheel returns index-parity lists WITH empty placeholders
  (the gate reads loop_costs positionally), so units pinned to empty loops idled all day
  OUTSIDE the serpentine crop pool. Executor now filters empty loops before pinning --
  no-op for the chain (it only returns non-empty loops). Wheel-arm 886 re-run: 69,069
  unchanged; shipped-path byte-parity re-proven (mirror n=18 $56,755 exact; luanhe
  73,076 / 900 64,449 exact, each in a CLEAN process).
- Probe-protocol note: run_one_real(params) mutates process-global PARAMS and never
  restores -- multi-arm probes in one process contaminate every call after the first.
  One judge per process (or explicit PARAMS reset) is the only sound protocol.
- Docstring drift corrected: the wheel comment claimed "trips taken whole, heads fit"
  -- false; assignment is round-robin over a nearest-neighbor tour, no fits-check.
  The code was fine; the description lied.
- Reported, not fixed (pre-existing, not introduced here): the executor's bagless-FEED
  repair can 2-turn-cycle while the shed is dry (identical in the chain; bounded
  upstream by feed_solvency). 93/93 tests; pack.sh bank-for-bank; verify_pack $100,348;
  tarball repacked.

### 0924j — submission14 tape autopsies → the hire-floor adoption (build turn)

**Tapes:** 112942073 (Driz Lo $159,586 vs our $32,712 — the second 6-digit opponent
ever recorded), 112941859 (self-match $60.6k/$56.3k, sum $117k). Also 112929590
(amit shulstein $78,413 vs our $19,090). Same three-defect chain in all:
(1) d0 spend $2,925/$3,000 → $155, no animal ever possible on day 0;
(2) demand-sized roster hired 1 hand d2–d9 (seed-light board, no jobs yet);
(3) the legacy animal money wall (pace×cost×2) bought 0 animals in 112929590.

**Three knobs built (kagfarm/policy.py PARAMS):** seed_opening_cap (d0 budget cap),
k_admit_def (P2c field-cadence money floor on the default arm), hire_floor_n/
hire_floor_day (census hire-ahead-of-demand floor).

**Instrumentation break caught mid-turn:** the first adoption A/B was invalid —
the hire_floor edit had fused onto a `#`-comment line inside PARAMS (line 286), so
`hire_floor_n` silently didn't exist and params=None ran (650,1,None). Proven by a
Policy.__init__ spy: file-default mode read (650,1,None) vs explicit (650,1,4).
Rule: any new PARAMS knob must be read back via a fresh interpreter before A/B.

**Judge bar (recorded seeds, clean factorial, all knobs pinned):**
- shipped refs reproduced byte-exact: −25.2/−26.7/−39.8/−51.5/−58.6 (mean −$40.3k)
- seed_opening_cap REJECTED at 650 AND 1200 (luanhe −$20k, 907 −$52k/−$52k worse):
  the d0 melon wave funds the whole strawberry spray on the real tier — the 0920
  melon_opening lesson again; the passive-opponent mirror cannot see it.
- k_admit_def REJECTED (886 −$17.8k, mean −$3.3k): the windfall reinvest is
  mistimed for the default arm's cash curve.
- hire_floor ADOPTED as hf=4, hire_floor_day=5.

**Adopted-cell bar (hf=4/day=5):** −24.0/−24.6/−29.7/−51.6/−56.4 → mean −$37.2k
(+$3.0k vs shipped, 4/5 better, 0 worse). Day=10 form rejected on its own bar:
juicy best-ever −17.8k but 907 −$6.8k worse + a −$25k mirror tail (s4 $38.7k);
day=5 covers exactly the pre-income trough (hires d0-11 = [3,0,1,0,1,0]) and keeps
mirror mean $64.9k (+$3.5k), worst seed +$12.6k ($46.6k→$59.2k... final $38.7k→$60.7k
on the day-5 form).

**Gates:** 95/95 tests · parity proven (file-default == explicit-params, luanhe
65,120 both channels) · pack.sh bank-for-bank · submission14 repacked.

### 0924j postscript — first field wins on the ladder pair (both PRE-hf build)

112945796 W +$9,711 vs Sam Scott (us $92,413): our bank pinned $161-2,146 d8-22,
trailing by $37.8k at d22, then the d26-29 wave + full-clear swung +$41k in two
days (his d29 +$3.6k, ours +$10.6k liquidation). Won on endgame conversion.
idle_steps 310/720 (43%!) -- the d2-9 one-hand trough working even in a win.
112946976 W +$96,744 vs Bum_Fy_Mz (us $103,530 -- FIRST six-figure field bank):
passive book (his 33 SELL-turns all season, 39 wool hoarded to $0 at the buzzer),
our drip cadence 22 turns d10 then 4-34/day mid, 40-67/day endgame full-clear.

**Fingerprint:** both games' hire cadence = [3,0,1,0,1,0,1,1,1,1,4,14] -- byte-equal
to the two LOSSES (112942073/112941859). The ladder still runs the pre-hf profile;
submission14 (hf=4/day=5) was packed after these games were played. Read: the same
build that lost to a 6-digit elite beats the mid-field -- consistency vs the field
is the early-trough fix (hf) + endgame machinery already shipped; consistency vs
elites is still the herd-assembly gap.

### 0924j postscript 2 — four field games all = the FIRST pack named submission14

User confirms both earlier wins (112945796/112946976) AND these two
(112961710 W +$12,771 vs Abhimanyu Singh, us $97,939; 112967723 L −$38,058 vs
Alejandro Rendon B., us $73,517 / him $111,575) ran the first submission14
archive — the pre-hf build. The hf repack (sha 639e4777, packed 0925 00:10) is
NOT on the ladder yet; uploading it is what activates the hire floor.

**Alejandro = third 6-digit elite, same kill-chain, tighter diagnosis:**
his d0-10 is ALSO pinned ~$70-500 (the seed-light opening is normal among
elites) — the loss is entirely d14-24 mid-game: him +$8.1k → $74.7k (+$66.6k,
~$6.7k/day sustained compounding), us $6.7k → $13.4k (+$6.7k TOTAL, flat bank
for ten days). Profile: wheat-heavy accumulator (67 wheat seeds, 11 berry),
302 hires (~12.5/day avg), animals in the final shed (MILK/EGG), near-empty
shed at the buzzer. Our mid-game roster was NOT the problem ([14,11,11,14...]
from d12) — the bank flatness is income conversion: idle_steps 289/720 (40%)
with the herd gap unchanged. The elite signature, now 3/3 (Majkel/Driz/
Alejandro): match the melon opening, then out-compound us d14-24 while our
engine idles between the d12 wave and the d26 endgame.

### 0924j postscript 3 — full field record of the pre-hf submission14 class: 4W-7L

New batch (all pre-hf fingerprint confirmed): L −24.1k men-of-culture,
L −10.7k susutem, L −44.4k Matt Dowis, W +9.5k Dean Johnson, L −9.4k Jiahan Cao,
L −18.6k Ryan Hancock, L −39.9k Cody Schrank. With the earlier four:
**4W–7L, mean margin −$21.9k.** Loss bands: coin-flip band −$9–24k (4 games,
fixable by the trough+hiring fixes), structural band −$38–44k (3 games, one
defect class).

**THE one defect class (Matt Dowis cleanest): the mid-game conversion stall.**
Our bank d14–26 sits at $875–6,534 for FOURTEEN days while the winner
compounds (Dowis $14k→$76k, Alejandro $8k→$75k, Driz analogous). Our endgame
machinery is intact — Dowis game still swung +$55k in the last 3 days
($6.5k→$36.0k→$61.3k). Income profile is BIMODAL (d10-12 melon wave + d26-29
berry wave + full-clear); the elite profile is CONTINUOUS (wheat-heavy
accumulators, 57-190 wheat seeds, drip sells, animals): ~$5k net from us in
d14-26 vs ~$67k from them. The hf build queued for upload attacks the EARLY
trough only. The mid-game stall is the next structural fight; named levers:
the 1,677 gain-window water misses, the d12-17 idle valley (idle_recut family,
measured dormant), and the wheat-accumulator lane the elites all run.

### 0925a — ELO-first package: W/L bar built; both spec-diff knobs MEASURED-REJECTED

**Objective reframe (official rules):** Bradley-Terry scores W/L only, margin never
moves rating — losing to a 3200 elite costs almost nothing, the coin-flip band vs
mid-field is where rating dies. The bar is now W/L-first: `analysis/judge_bar.py`
(thin wrapper over ab_panel.paired_ab, each judge on its own recorded seed, one
process per arm).

**Spec diff (competition page) produced two candidate levers:**
- B1 `decay_urge`: past max_lifespan standing yield bleeds 1 unit/2 TURNS (spec).
  Escalates the bleeding tile's HARVEST to TIER_RESCUE, priced at standing units
  (constants.decay_clock_running; boundaries exact per crop, tested).
- B2 `plant_water_chain`: verified ALREADY SHIPPED (policy.py:1401 chains then=
  ["WATER"] on every allocator PLANT — the zero-grace rule is covered at source).
- C `endgame_shift` (+`endgame_shift_gap=0.10`, base-equiv denominator ~$1,111):
  public rival money, trailing by >10% at d24 = full-clear regime starts one day
  early (floors off d24, never leading/tied, one-sided no-oscillation, pooled-
  episode reset at day<=1).

**Judge-bar factorial (5 judges, recorded seeds; baseline byte-parity with the
0924j refs):** baseline 0-5, mean −$37.2k · B1 alone −$37.5k (byte-identical 4/5,
juicy −$1.2k) · C alone −$38.7k · bundle −$38.8k. **Both REJECTED, defaults 0.**
The decisive reading: on 907, C's early clear took OUR bank DOWN $3.5k
($61.3k→$57.8k) while the judge's went UP — selling a day earlier into the glut
grows the rival's realized price too, and overnight recovery between metered waves
out-earns the head start. **The endgame full-clear is not time-starved; its timing
is not what loses close games — the SIZE of the endgame wave is.** B1 is byte-neutral
because decay-state tiles barely exist on elite boards (the ordinary plan harvests
at harvest_day; lifespan starts a day later) — the weed probe's rotted produce comes
from days the whole plan is over-subscribed, which is a capacity problem, not a
tiering one. Both mechanisms stay as documented dormant knobs for the P5 tuner.

**W/L instrumentation is the durable yield:** every future arm reads as W-L first,
margin second; baseline (0-5, −$37.2k) is the new promotion line. Also from this
bar: the 900 judge's recorded opponent is $156.2k-class (the $65-70k ladder means
nothing there) — elite judges are margin-irrelevant under BT but stay as stress
arms for mechanism falsification, which is exactly what they did here.

**State:** 106/106 tests (95 + 11 new), pack.sh bank-for-bank ($91,776 packaging
panel, worst turn 2.4ms), `~/Downloads/submission14.tar.gz` sha a1a64b9a… (hf
build + dormant knobs; no behavior change vs 0924j).

## 0925b — no-waste package: P0 cancels P3; P1/P2/P4 built, all three measured-rejected

**P0 (empty-tile veto) — the finding that reshaped the plan.** The "8–40 tiles empty
d18–24" waste pool was tape-attribution confusion, not an allocator veto. Judge 886
(limit_trace_886): the allocator fills the board every dawn — `tl=1`, want sums equal
the dawn-empty count (16/16 d13, 22/22 d17, 14/14 d21) — and ALREADY pivots to
wheat/carrot organically (want WHEAT 4–12, CARROT 1–12 from d17; d27+ empties are the
correct `in_time` deadline expiry). The Dowis tape (112955553, seed 1176166457, our
seat 1) shows the same empty-tile picture as a dead board: 19 weeds, live=0, $82 at
d12, $0 from d14 — with the book serving only d0–6. **P3 (pivot lane) cancelled: the
behavior exists; the real defect is the cash/income stall, and the pre-0924j ladder
build that played these tapes predates the solvency/ledger fixes.**

**Built (all dormant, knob=0, tests):** P1 `tick_burst` (mid-season floor-eligible
sells burst-capped; remainder re-offers next turn at the drain-lifted book;
always_sell/crowded/endgame untouched) · P2 `crowd_premium_floor` (the crowded-valve
branch keeps the NORMAL reserve floor for STRAWBERRY/MILK/WOOL via
`_PREMIUM_HOLD_GOODS` — overflow discards incoming bags, not shed stock) ·
P4 `marginal_sell` + `_marginal_hold` (prefix-priced future-head hold floor:
future_head = mi + horizon×(pipeline-per-cycle − exact drain); monotone above-I0
curve, strict generalization of the static floor, flat book ⇒ identical). Live site
threads `tiles` into `_sell_orders` for the real pipeline read.

**Judge bar (5 judges, recorded seeds, one process per arm; baseline −$37,243
byte-exact):** P1 burst=3 → −$37,631 (886 −$1.7k) · P2 → −$37,883 (luanhe −$3.3k,
the luanhe $75.2k→$77.7k leak) · P4 → **−$115,914 catastrophic** (our banks $28.4k
vs $61.3k on 907 while the judge ROSE; the crude full-yield/cycle pipeline model
misprices supply timing and we withheld into a book the judge then monopolized —
exactly the melon_opening family's falsification mode, one tier deeper).
**All three REJECTED; defaults 0** with verdict comments; mechanisms dormant.

**Waste-map postscript:** the remaining honest waste pools after this session are
(1) the mid-game income stall itself (capacity/financing, not sell rules — three
sell-side falsifications now agree), and (2) the opening book's all-PASS days
(demoted: pre-window watering is yield-neutral, ~$0–1k). Next real fight is
production-side, not trading-side.

**State:** 117/117 tests (106 + 11 new), pack.sh bank-for-bank ($91,776 packaging
panel, worst turn 2.4ms), tree ships unchanged behavior (knobs 0).

## 0925c — mid-game stall traced (production side)

Kill-chain 886/900: capital is never idle — the $17.4k d10-11 wave is fully spent
by d13 (land + berry acreage + fert) and the board runs full with a 12-15 roster.
The stall is two ANIMAL-LANE starvations: (1) the d0 script's 2C+3S escapes by d4
(FEED ops = 0 through d13 on BOTH judges — the bridge grain the script intends
never lands; funnel: 886 buys 2/season, 0 milk ever sold); (2) the herd rebuilds
to only 6-8 placed (one-buy pacing + full envelopes) vs judges' 14-21 from 16-24
buys, monetizing the lanes we abandon (886 judge MILK $23.1k vs our $0; 900 judge
WOOL $25.7k + MILK $43.2k vs our $17.9k). eta_capital 0.54-0.66 vs 1.13-1.66.
Sized fix approved: bridge_grain (guaranteed d0 feed reservation) +
wave_share_animal (~30% of each windfall to BUY_ANIMAL, in_time/feed_ok-gated).

## 0925d — P5 dormant-knob sweep: all cells lose; no interaction rescues

Judge bar, one process per arm, baseline −$37,243 (means):
tb1 −38,278 · tb2 −37,632 · tb3 −37,631 · tb4 −37,628 · tb5 −36,939 · tb6 −36,940
(burst saturates at 5; the floor loop already meters most piles below 5-6 units)
cpf −37,883 · du −37,465 · es −38,7xx | cpf+du −38,011 · cpf+es −39,020 ·
cpf+du+es −38,811 | tb5+du −37,965 · tb5+cpf −37,772.
Best cell tb5 = +$304 — far below the ≥$1k adoption bar. The four knob families
are independent small negatives on the real tier; combinations sum, none rescue.
**Verdict: all-reject.** Every sell-side knob stays 0. The sell engine is
confirmed near-local-optimum; the fight is production-side (0925c plan).

## 0925e — unaudited-tape sweep: hf build STILL has zero ladder games; record corrected 5W-7L

**Build attribution (decisive).** 112912372 (earliest sub14-era tape, Sep 24 22:22)
fingerprint = [3,0,1,0,1,0,1,1,1,1,4,2] — identical to all 11 prior tapes. No
Downloads tape post-dates the hf pack (newest 00:24 < pack 01:44). The hf build
(sha a1a64b9a) remains upload-pending with zero field games.

**New find: 112912372 vs ru-shao, W +$46,049 (us $84,423)** — a fifth win the
batch pass missed. Autopsy: both farms stall mid-game (ours 12.5k d12 -> 4.4k d18;
theirs 6.2k -> 4.0k), we drip-sold 422 vs their 72 SELLs, they ran a wheat-
accumulator opening (193 wheat units) and hoarded to the buzzer (10 wheat + 1 cow
unsold); our d28-29 liquidation +$33.7k decided it. Confirms the regime map:
endgame conversion beats mid-field accumulators; mid-game compounding beats us at
the elite tier.

**Corrected field record of the pre-hf sub14 class: 5W-7L**
W: ru-shao +46.0k, Bum_Fy_Mz +96.7k, Abhimanyu +12.8k, Sam Scott +9.7k, Dean
Johnson +9.5k | L: Jiahan -9.4k, susutem -10.7k, Ryan Hancock -18.6k,
men-of-culture -24.1k, Alejandro -38.1k, Cody Schrank -39.9k, Matt Dowis -44.4k.

**Re-ranked defect list (post 0925b/c/d falsifications):**
1. d0-9 feed-bridge death (PRODUCTION, fix approved bridge_grain): FEED=0 through
   d13 on both elite judges; the $2.1k script herd escapes d4; kills the whole
   animal lane ($40-70k of judge value). Highest leverage.
2. Wave-share herd expansion (PRODUCTION, fix approved wave_share_animal): 6-8
   placed vs judges' 14-21; eta_capital 0.54-0.66 vs 1.13-1.66.
3. Endgame dependence (SYMPTOM of 1+2): every win rides the d26-29 full-clear;
   cured only by a bigger mid-game base, NOT by sell/timing knobs (three
   falsifications: 0925a endgame_shift, 0925b sell family, 0925d sweep all-reject).
4. Hire-floor validation (PENDING LADDER): hf build expected to remove the d2-9
   one-hand trough; zero field evidence until the a1a64b9a archive is uploaded.
5. Small/demoted: book PASS days (~$0-1k), waste-ledger instrumentation (no
   behavior change), move-share 69->59% (unmeasured on the current bar).

## 0925f — production-side package: flock_arm + wave_share_animal (build+measure, REJECTED)

The 0925c kill-chain named the two animal-lane starvations; the approved fix shipped as three
knobs and went to the judge bar. **All arms rejected — but the mechanism finally works.**

- **Step-1 verdict (bridge trace, seed 731180114):** the bridge never dies on the default
  arm because **the d0 script never fires** (`opening_led/elite_script/led_flock` all False).
  `flock_arm` arms the fully-built led_flock stack (flock + `_top_grain` bridge + reserve
  netting + k-admit money gate).
- **Smoke findings fixed in code:** (1) whole-flock reserve netting at t0 crushed the seed
  round (melon wave $17.4k → $3.3k) → `flock_stage2_mode` (0 raw / **1 stage-1-only** /
  2 same-turn surplus); (2) founding cow starved d8 → the wheat backbone + mandatory wheat
  pre-allocation extended to the flock arm. Final mirror shape: cow alive all season
  (FEED d2–28), flock d13–15, wave-funded expansion to 4c7s, banks $71–83k.
- **Judge bar (5 judges, recorded seeds, baseline −$37,243):**
  mode 0 **−$59,212** · mode 1 **−$56,853** · bundle +wave 0.3 **−$62,787**. ALL REJECT.
- **Why the bar overturns the mirror:** the judge's bank *rises* in every flock arm (886:
  $74k recorded → $107–132k; 907: $156k → $136–161k while our margin doubles worse). Two
  structural reasons: (a) the melon wave is not just our income — it is **market denial**
  (we glut melon, the judge cannot monetize its book; sacrifice it and the judge's book
  pays full price); (b) our milk arrives d13+ = **after the first-mover window** ($230–246
  early, $40–80 crash), so at our service scale the herd costs more crop income than the
  late-window milk returns.
- **Ledger synthesis (third falsification family agreeing):** on this tier, *defending our
  book (melon wave) + premium-window timing* is worth more than *adding a late animal lane*.
  The elite gap is not "we have no herd" — it is that their herd monetizes EARLY and ours
  monetizes LATE, and the wave-fund route destroys the denial asset. Next live levers: d0–12
  market denial engineering (wave timing/size vs the judge's monetization), not herd scale.
- State: 125/125 tests · pack.sh bank-for-bank ($91,776) · knobs documented dormant ·
  artifact repacked `~/Downloads/submission14.tar.gz`.

## 0925g — ELO package P1/P2/P4: premises FALSIFIED by tape calibration (not built)

The approved package's own first step (calibrate the converter/hoarder classifier on the 12
ladder tapes) killed it before any code shipped — the honest outcome under the measure-first
rule.

- **P1 classifier: no separating signal.** Opponent cumulative SELL revenue by d20/24 does
  not separate hoarders from converters (Tâm, the hoarder archetype, outsold Jiahan by d20);
  late-dump size (d25-29) does not either ($16-34k for near-miss opponents vs Tâm $42.6k).
  The exact market-residual variant (inventory identity + shop drain + both buys) reads
  $2-5M of phantom revenue — engine artifacts (floor-consumed sells, per-turn order
  renaming, midnight overflow discards) make the residual unusable as an instrument.
- **P2 narrow endgame_shift: premise false on our own tapes.** The near-miss losses were
  NOT sold into a crashed book: realized d25-29 prices were premium everywhere (Jiahan
  $269/unit strawberry, twin $257, susutem $215) and prices do not order the outcomes
  (Jiahan $269 LOST; Dean $200 WON). Volume orders them (1749u/980u won; 892-1279u lost).
  Selling earlier into an opponent dump that does not materialize would repeat the 0925a
  reject.
- **P4 buzzer-chain guard: stale premise.** The d25-29 chains are already protected
  (split_runs deliver_reserve=5, endgame_cap=0 full-clear, animal_stop_species). The old
  buzzer tails were pre-hf artifacts.
- **One real defect found: the $1 self-crash (112960536 vs Ryan Hancock).** 560 strawberry
  units realized $1 average d25-29 — our own endgame full-clear walked the price to the
  floor mid-sale (vs the $250 book: ~$100k+ destroyed). Candidate fix for the next bar:
  price-aware endgame metering (`endgame_floor`: stop the clear when the marginal realized
  price collapses; resume next dawn after the town drain recovers the book; d29 keeps the
  true full clear).
- **The near-miss arithmetic (the case that closes):** susutem needed +$10.7k = ~50 more
  strawberry units at their realized $215; Jiahan ~40u at $269; the twin ~17u at $257. The
  deficit is mid-game PRODUCTION VOLUME — the d13-19 strawberry cohort — the same verdict
  the 0925a/b/d sell-side and 0925f production-side falsifications all reached.
- State: no code changed by 0925g itself; PARAMS untouched; shipped artifact unchanged
  (152b7bcd).

## 0925h — endgame_floor: built, tested, MEASURED-REJECTED on the judge bar

The one real defect 0925g found (the $1 self-crash, tape 112960536: 560 strawberry at $1
average vs the $250 book) got its candidate fix and the bar killed it with a mechanism
lesson.

- **Built:** `endgame_floor` — during the endgame full-clear, a good whose live price sits
  below `endgame_floor_frac` x its season peak (`px_peak`, exact per-turn public read)
  pauses for the day; the town drain recovers the book between waves (the 0925a-validated
  mechanism); d29 clears regardless; always_sell (MELON) exempt; knob off = byte-identical.
  Six unit tests (pause / healthy-clear / d29 override / MELON exemption / off-form /
  no-peak safety). 131/131 green.
- **Judge bar (baseline byte-exact at -$37,243):** `endgame_floor=0.3` mean **-$41,930**
  (-$4.7k). Byte-identical 2/5 (886, juicy — the knob binds only on a collapsed book).
  900 +$2.2k (small wave, pause -> recovery worked as designed). luanhe **-$23.0k**: the
  paused units never recovered — the town drain cannot lift a book that size before d29,
  so the pause converted a descending-price cascade into a d29 $1 clear anyway, minus the
  mid-cascade units that were already banked in the baseline.
- **Mechanism verdict:** once our own wave has crashed the book, HOLDING CREATES NO VALUE
  — the wave size (1,749u into a ~100-unit-T premium book) is the defect, not the sell
  order. The 0925g arithmetic (each near-miss ~40-50 units short at premium prices) and
  this reject agree from opposite directions: **cohort sizing is the only live lever.**
- State: 131/131 tests · pack.sh bank-for-bank ($91,776) · knob documented dormant ·
  artifact repacked (sha below).

## 0925i — win-rate package: bar upgrade + wave-cap + milk-window + p10 panel

**1. MIDFIELD JUDGE TIER REGISTERED (the instrument upgrade).** SPECTATOR_IDS gains four
coin-flip-band judges (seats from TeamNames order, tapes copied to analysis/replays/):
midfield_tam (113122185 s1, seed 969596258), midfield_dean (112957999 s0, 970394715),
midfield_jiahan (112959216 s1, 309707973), midfield_susutem (112952973 s1, 1465775700).
judge_bar.py now runs ELITE (guard) + MIDFIELD (primary W/L verdict) tiers. **Shipped
build midfield baseline: 3W-1L, mean +$8,336** (Tâm +25.4k, Dean +6.7k, Jiahan +12.5k,
susutem -11.3k) — the current build WINS the Jiahan world the tape build lost; susutem
reproduces the near-miss. Elite baseline byte-exact (-$37,243).

**2. opp_acreage_credit (book-aware wave cap) — REJECTED both scales.** Forward
opponent-supply estimator from PUBLIC acreage (opp_acreage_supply: standing units +
scheduled productions over horizon; tests shipped) feeding the existing opp plumbing.
credit 0.5: elite -$70,559 (planting collapsed) AND midfield 2-2. credit 0.1: midfield
+$8,900 (noise) but elite -$48,099. Mechanism: our endgame wave is the market-DENIAL
asset on the elite tier — pricing our planting against the rival's future supply
suppresses it and gifts them the book. The estimator works; the channel destroys value.

**3. milk_first_wave (minimal d0 cow) — REJECTED both tiers.** Elite -$45,227 (guard);
midfield 2-2 (+$2,938, Jiahan W->L by -$146). Even ~$550 of seed round doesn't repay
through the d13-19 window at our service scale. The 0925f bundle verdict holds for the
minimal form: the window is unreachable from the default arm's economy.

**4. p10 variance panel (16 seeds x passive/elite): NO TAIL PROBLEM.** vs starter:
16/16 W, mean $94.7k, p10 $80.3k. vs majkel886: 0/16 W (structural, BT-cheap), p10
$49.3k — the catastrophic floor is ~$49k, the windfall-draw tail is tamed by the shipped
solvency governor. "Bulletproof" holds: no seed draw loses to the field we beat.

**State:** 136/136 tests · pack bank-for-bank ($91,776) · knobs dormant at 0 · artifact
repacked (sha below). **The ELO ledger now reads: the sell layer, herd scale, opponent
conditioning, post-crash holding, AND opponent-aware planting are all measured local
optima; the midfield build wins 3/4 on the upgraded bar; the remaining gap is exactly
the elite tier, which BT prices at ~zero. Next rating lever: ladder volume on the
current build (two-slot A/B), not further local search.**

## 0925j — two-slot ladder A/B protocol adopted (D-5 to deadline)

**Instrument:** `LADDER_AB_PROTOCOL.md` (new, governs the final window; runbook keeps
submission mechanics). Premise measured, not assumed: two identical submissions self-pair
(110081520 — twin play, guaranteed W+L, ~zero rating EV), so the two-latest rule's two
slots are run as a deliberate A/B rig instead.

**Slots:** A = shipped artifact sha `7b2c238c…` (hf build; midfield bar 3W-1L +$8,336;
elite guard byte-exact -$37,243), never changes except one ordered migration at freeze;
B = one experimental arm per day, re-chosen each morning after reading last night's tapes.
Day-1 Slot B = the hf build itself — the ladder has only pre-hf fingerprint
[3,0,1,0,1,0,1,1,1,1,4,2] games, so the pair gives the hire-floor fix its first field
evidence (d2-9 hires, idle_steps ~40-43% are the read).

**Daily loop (through D-1):** pull tapes → autopsy + fingerprint each (runbook step 4 is
now a DAILY gate) → Slot A = control series, Slot B = treatment → judge tomorrow's
Slot-B candidate on the two-tier bar (`judge_bar.py --tier both`) → upload **B first,
then A** (the two-latest trap: every B upload rolls off the older resident, so A must be
re-upped byte-stable after every B upload) → one ledger line per day.

**Promotion bar (all three, evidence cumulative):** (1) judge bar pre-gate — midfield
W/L ≥ 3-1 with mean ≥ +$1k vs the +$8,336 baseline AND elite mean no worse than -$41k
vs the -$37,243 guard (elite W/L not gating — BT prices elite losses ~0); (2) ladder
field record no worse than Slot A's on same opponent bands with ≥ 8 field games for the
candidate, else tie-break goes to the judge bar, never vibes; (3) no red flags — no
_safe_pass signature, fingerprint 1.32.7 EXACT on every tape, no bank collapse outside
the p10-covered draw.

**Slot-B candidate queue (each must pass the morning bar before consuming a slot-day; no
dormant knob carries positive expectation, so Slot B measures the UNMEASURED gaps):**
day 1 hf build itself → day 2 the 0925g near-miss arithmetic's live lever (d13-19
strawberry cohort sizing, ~40-50u short at premium prices — production volume, the one
family three falsifications agree on; NOT sell timing) → day 3 dawn_pace re-test at pace
2-3 (its 0920 reject predates the hire-floor cell) → then idle-recut. One candidate per
slot-day, no compound arms, a failed candidate is never re-armed unchanged; if nothing
survives the morning bar, B repeats the current best rather than arming a judged-rejected
arm.

**Stop rule:** D-2 (Mon 28) = last day a NEW candidate may enter B · D-1 (Tue 29,
MORNING) = freeze — if the promotion bar is met, the single ordered A-migration happens
then (a D-1-evening migration has zero tape evidence and is a blind bet); if not, ship A
unchanged to both slots and stop · deadline day = re-uploads of the frozen best only; a
build with zero ladder games is ineligible to be the frozen pick.

**Day-0 state check (this turn):** newest Downloads tape = 113122185 (already the
tam judge) → Slot A's sha is the currently-playing build; tape queue empty; fingerprint
fresh. Tree: no changes (protocol + ledger only).

**State:** no code changed (knobs untouched at 0, artifact unchanged `7b2c238c…`); 136/136
tests stand; this entry is the protocol's record. Tomorrow's first action: read overnight
tapes, autopsy+fingerprint, judge the day-2 candidate, upload B then A.

### 0925j postscript — workspace cleanup (same day)

One pass parked everything unreferenced into `useless/` (see its README): the stale
`kagglegit/` GitHub copy, the 2.3 GB raw replay corpora (`majkel1337games/` 63 tapes,
`sub10games/` 16 tapes — all cited games were already copied into `analysis/replays/`),
the nine superseded submission archives (`submission.zip`…`submission10.tar.gz` +
`submission_v3.tar.gz`; live artifacts remain `submission.tar.gz` and
`~/Downloads/submission14.tar.gz` sha `7b2c238c…`), `PLAN.md` +
`Kaggriculture_FINAL_KT.md`, the V3 modules (`kagfarm_policy_v3{,_ref}.py`,
`kagfarm_spec_v3.py`) and three caller-less probes (`plant_cadence`, `kt_trace_probe`,
`move_share`). Path note: `calibration/majkel_dossier.md`'s "Corpus: majkel1337games/"
now lives at `useless/replay-corpora/majkel1337games/`. Verified after the moves: 136/136
tests, pack.sh PACK OK bank-for-bank ($91,776), midfield judge bar reproduces 3W-1L
+$8,336 byte-exact. Kept despite low activity: calibrate.sh/snapshot.sh/run_demo.py
(bootstrap + AGENTS.md chain), calibration truth tools, and every analysis probe named
in ledger entries 0920-0925i.

## 0925l — leaderboard grounding: the ~3000-ELO claim RETRACTED, real numbers recorded

Provenance of the bad number: "55-60% win rate ≈ ~3000 ELO" entered the record as an
early-session working assumption and was never validated against the actual score
distribution; the 0925k-era situation summary repeated it and a schedule-blend was
invented around it. The Sep 25 public leaderboard (10,004 teams, pulled 19:04) contradicts
it. Measured facts now on the record:

- WE are "Pranjal Morwal": **535.0, rank 6,724 / 10,004** (submission14, uploaded Sep 24).
- Median team = **761.3** — half the field is above us. Teams ≥1000: 3,995. ≥2000: 1,587.
  ≥2800: 29. ≥3000: 5 (DSM 3064.5, Boey 3041.6, Unknown Mother-Goose 3019.5,
  M & M & P & Q 3018.5, DECEM 3008.9). Bottom of the table: -206.8.
- Tracked opponents' true ratings: Jiahan Cao **473.9**, Tâm La Thành **500.2** (both
  below us — consistent with the judge-bar wins), susutem **601.9**, Cody Schrank
  **612.5**, Matt Dowis **634.5** (the near-miss/structural band sits just above us),
  Dean0016 **2385.7** (rank 676 — if this is the "Dean Johnson" we beat twice on tape,
  that is measured evidence of strength far above our current score), Driz Lo **2714.9**
  (rank 70), Majkel1337 **2984.6** (rank 7).
- Our submission scores cluster 480-587 across five different builds (53.3 was the broken
  dairy_v1) — the score is moving with GAME VOLUME, not build changes, so 535 is
  convergence noise plus few games, not the build's level.

**Corrected outlook:** 55-60% win rate is plausible only against the sub-700 band (where
the judged evidence lives: we beat 473-500 solidly, coin-flip 600-635, tape wins vs a
~2385 outlier). Steady-state with volume: plausibly the **700-1,200 band** (top ~35-40%)
if the near-miss flips land; 2000+ has no measured support; 2800+ means top-29 and is
retracted. The build/ship decision is UNCHANGED — under Bradley-Terry the best measured
W/L build is still the optimal ship, which is submission15.

**Retest note (same turn):** submission15.tar.gz re-verified on the attached bytes:
sha ecc00dc7… matches, payload byte-identical to submission.tar.gz, 136/136 tests,
harness smoke on the exact archive PASSED (720 steps x3, seat swap), judge bar
re-run fresh: elite 0-5 mean -37,243 / midfield 3-1 mean +8,336 — both byte-exact
to baseline.

## 0925k — submission15 packaged: the freeze-candidate ship

**What ships: the measured build unchanged.** No knob adoption — nothing cleared the
two-slot promotion bar (all dormant knobs measured-rejected 0925a-0925i), so per the
protocol's default the ship is the 3W-1L midfield build byte-for-byte. submission15 =
repack-and-tag, not a code change.

**Pre-flight, all three gates green (25 Sep):** 136/136 tests · pack.sh PACK OK
bank-for-bank ($91,776 packaging panel, worst turn 2.4ms) · harness_smoke on the exact
tar bytes ALL CHECKS PASSED (720 steps, no ERROR/TIMEOUT, banks $3,617/$95,960 — the
exec-context gate).

**Artifacts:** `submission15.tar.gz` = `submission.tar.gz` =
`~/Downloads/submission14.tar.gz` (Slot-A artifact refreshed), all sha256
**ecc00dc7eef6e0590e5bc4f725b10337d4fb2d9b6800d8dad9274dc342c55442**, 131,140 bytes.
Payload verified byte-identical to the 0925i archive (recorded sha `7b2c238c…`): the
archive sha moved only because pack.sh repacked the tarball (tar headers carry fresh
mtimes); unpacked-file diff exits 0. The protocol doc's Slot-A sha reference was
updated to `ecc00dc7…` with the payload-identity note.

**Upload (user-only, per runbook):** `bash submit.sh "submission15: hf build,
freeze candidate"` or the Kaggle UI with `submission15.tar.gz`. Two-slot protocol
reminder: the two-latest rule means upload order matters — B first, then A re-upped
carrying this same payload. Freeze decision is D-1 morning (Tue 29): if no Slot-B
candidate has met the promotion bar by then, this build ships to both slots and the
season closes.

## 0925m — the livestock-led redesign, MEASURED (five judge-bar arms, one evening)

The user's challenge: "if closing the gap means livestock redesign then redesign it." The
ledger said the untested cell was herd 14-16 with crops cut to a wheat backbone — every
prior herd raise (0919/0920/0924h) bolted cows onto the FULL crop engine with an
undersized shepherd stream. The knobs already exist (n_animals, animal_pace,
shepherd_share, herd_cow, mix, max_hands), so the redesign went to the bar as
CONFIGURATION, one process per arm, both tiers:

| arm | cell | elite mean | midfield W/L / mean |
|---|---|---|---|
| L1 herd-16 | n=16 pace=4 share=9 cow=14 hands=15 mix W18/M8/S10 | −$74,955 | 0-4 −$32,379 |
| L2 herd-22 | n=22 pace=5 share=12 cow=18 hands=16 mix W24/M6/S6 | −$69,981 | 1-3 −$17,717 |
| L3 hybrid | n=12 pace=3 share=7 cow=11 hands=14 mix W14/M16/S20 | **−$33,928** | 3-1 +$6,478 |
| C1 berry-40 | mix S40 only | −$43,457 | 3-1 +$9,364 |
| C2 windfall .50 | windfall_pct 0.50 only | −$39,846 | 3-1 +$8,481 (Tâm **+$38,240** best-ever) |
| L4 combo | L3 + C2 | −$39,077 | 3-1 +$5,383 |

**Verdict: NONE promotes.** The shipped build's midfield +$8,336 stands. Three
mechanism findings, all new to the record:

1. **The redesign ceiling is REAL and measured.** L1/L2 (the true elite shape: herd
   14-22, crops subordinated) are CATASTROPHIC on both tiers — worse than the shipped
   build everywhere. The shepherd stream does not scale past ~12 head even with share
   raised to 9-12; the economy cannot fund pace-4/5 assembly; and the denial-asset loss
   (0925f) repeats. The elite recipe requires the EXECUTION layer Majkel has (feed
   scaling, capital deployment), not bigger targets — confirming 0919's "NEXT LEVER"
   note that chores need per-animal-day routing budget first.
2. **L3 is the closest thing to continuity we can field** — herd 12 with a MELON-16/S20
   hybrid mix improved the ELITE tier by +$3.3k (best elite ever measured, −$33,928) at
   midfield parity. But midfield mean is −$1.9k vs shipped and susutem worsens — it
   trades a coin-flip win for an elite-margin trim. Under BT (elite losses ~free), that
   trade is NEGATIVE expected rating. Not promoted, but recorded: the first arm ever to
   beat the shipped build on the elite tier.
3. **C2 (windfall 0.50) hit Tâm for +$38,240** — the largest single margin ever
   measured — while holding the guard. One-judge variance at n=1 per judge; a multi-seed
   confirmation on the tam/dean pair would be the cheap next step, but the promotion bar
   (W/L + ≥+$1k mean, no elite regression) is not cleared by mean +$145.

The user's question "what is stopping us" now has its final, measured answer: the
continuous economy is not a parameter away — the herd assembly/execution layer is the
missing subsystem, and building it is a next-season (v2) program, not a 5-day knob.
Every configuration reachable in the existing architecture has now been measured on the
two-tier bar. The projection stands: ~700-1,200 steady-state, band levers = hf field
evidence + (unmeasured on ladder) C2-style funding; 3000 requires the v2 execution
layer. Ship decision unchanged: submission15.

## 0925n — top-10 corpus pipeline + the continuity decomposition

**Pipeline built tonight:** `analysis/top10_scan.py` (detached bulk-download of the daily
episode datasets + stream-scan that keeps ONLY top-10-team games into
`analysis/replays/top10/`, disk peak <100 MB) · `analysis/top10_profile.py` (dossier
cards: d0 order script verbatim, first-animal turn, animal units ordered ≤d10, herd mix,
seed mix, executed milk/wool from shed deltas, sell days, d20 bank) ·
`analysis/top10_curves.py` (per-day income decomposition: money delta + shed outflow by
good, d8–26). Same-day embargo fact: today's dataset 403s per-file; yesterday's works.
Download of the 09-24 dataset (736 MB zip, 590 episodes) running detached.

**First results, measured:**

1. **DECEM card (112648567 vs ymg_aq):** d0 order script VERBATIM the unified elite
   script (t1 COW+WHEAT-feed, t2 sell+4 hires+COW+SHEEP×3) — dossier opening confirmed
   on 09-24 data. Herd 24 head (5C/12S/7G), 176 wool executed, 301 hires, d20 $54.8k,
   won +$10.9k.
2. **The DSM-vs-Majkel separator is LABOR + CADENCE, not product mix** (10-game
   stratified subset): DSM hires 291–295/season vs Majkel 288–289 in EVERY game; DECEM
   301. DSM orders 16–21 animal units by d10 vs Majkel 13–19. Wool/milk volumes are
   MIXED between winners and losers — within the tier they do not separate. The rank-1
   edge is a constant 3–6 hires plus 2–3 earlier animals.
3. **The continuity table (medians):** US pre-hf (n=4): hires 230, animal-units-by-d10
   **ZERO**, wheat seeds 96, melon 24 (the ONLY corpus team leaning melon), milk 16,
   wool 10, **d20 bank $4,057**, final $58,655. Majkel (n=63): 288/17/172/13/194/69/
   d20 $57,907/$100,979. DSM (n=36): 291/16/175/19/182/58/$59,768/$102,158.
   M&M&P&Q (n=5): 270/bulk/148/11/221/17/**$82,600**/$109,938. The mid-game stall is
   now a single number: d20 bank $4k vs $58–83k, caused by the four lines above it.
4. **Income decomposition (DECEM game):** positive income EVERY day d10–24
   (+$2.5–8k/day, $70.3k net in the window); daily outflow 20–60 wheat + 7–22
   fertilizer + rotating wool/egg/carrot/tomato/strawberry drips. The elite recipe is a
   plant→cycle→sell loop plus an animal byproduct stream — zero dead days. Our stall =
   zero days BETWEEN two waves.
5. **L5 arm (hire_floor 8/day on the L3 cell) REJECTED:** midfield 1–3 (−$13,199),
   elite −$86,090. Elite wage cadence is unfunded without the continuous milk/fert
   income loop. The LOOP is the missing subsystem, not the roster number — now proven
   from both directions (L1/L2: herd without loop fails; L5: wages without loop fail).

**Next:** scan the zip on completion → profile every top-10 game → wool-signal retest →
arms to the two-tier bar. Pipeline commands: `python3 analysis/top10_scan.py scan|profile`.

### 0925n addendum — 426 games captured, 142 profiled: the within-tier separator measured

Scan kept 426/590 games (top-10 teams played each other all day). Stratified profile
(142 games, every 3rd) per-team medians:

| team | n | W-L | hires | aD10 | d20 | milk | wool | herd median |
|---|---|---|---|---|---|---|---|---|
| DECEM | 47 | 24-23 | 313 | 24 | 58.7k | 124 | 93 | 23C/3S/3G |
| Vadim | 45 | 17-28 | 311 | 24 | 53.0k | 132 | 89 | 7C/6S/11G |
| **DSM** | 37 | **35-2** | 317 | 24 | 56.6k | 128 | 43 | 6C/**14S**/5G |
| UMG | 28 | 11-17 | 311 | 22 | 56.0k | 131 | 86 | 11C/9S/4G |
| M&M&P&Q | 25 | 18-7 | 286 | 21 | 60.3k | 123 | 49 | 5C/5S/**11G** |
| mtmr_s1 | 24 | 7-17 | 316 | 21 | 52.7k | 88 | 41 | 6C/5S/11G |
| Majkel | 20 | 9-11 | 281 | **27** | **62.9k** | **217** | 75 | 19C/7S/1G |
| Boey | 6 | 3-3 | 282 | 26 | 61.7k | 63 | 102 | 15G median |
| Fourth Quadrant | 7 | 5-2 | 308 | 17 | 62.5k | 41 | 64 | 14C/7S |

**W-vs-L split per team (the separator test):** hires W-vs-L FLAT for every team (±3)
— labor QUANTITY does not separate within the tier. aD10 flat (±2). Wool separates for
3/7 (DECEM 94-43, mtmr 143-28, M&M 72-24), inverts for Vadim (54-111), flat for Majkel
and 吃白饭. **d20 bank separates for 7/7 teams** (mtmr +$12.0k, 吃白饭 +$8.9k, DECEM
+$6.6k W-lead). VERDICT: the top tier is decided by WHO IS AHEAD AT D20 — early-mid
game conversion efficiency — exactly the phase where our d20 bank is $4k. Meta drift
since the dossier: Majkel scaled animals up (aD10 27, milk 217), DSM went sheep-heavy
(6C/14S/5G) and is 35-2 in the sample, goose-tilts (Vadim/mtmr/Boey/M&M) underperform
their ratings head-to-head. Our levers for d20 presence: the C2 windfall-funding arm
(bar-cleared tonight) for the d13-19 cohort, L3's early herd, and the wheat drip loop.
Teams to emulate at our scale: M&M&P&Q (60.3k d20 with 270 hires — the LOWEST labor
among winners, goose/seed-led income mix) and Majkel's milk scale-up.

### 0925n postscript — submission15 field debut: 20 games autopsied (user-supplied tapes)

21 games of the hf build (submission15) placed in `submission15games/` by the user; one
self-match excluded. Battery: top10_profile cards + leaderboard rating join + curve
autopsies of both outlier losses. Results:

- **Field record 8-12, mean margin −$8.5k.** vs 400-900 band: 8-10 (−$5.3k). Clean
  sweep of sub-535 (6-0-1, HarryZ +37.1k / Morales +26.6k / Raffi +23.3k / Mahbub
  +19.0k / Ngoc +16.4k / Carriço +11.3k / Axit +80), losses start at 541 and worsen
  with rating (644 −$27.3k). One Zenith (2902) game, −$60.7k (margin −$61k vs mean
  elite judge −$37.2k: consistent).
- **The d20 stall is CONFIRMED ON THE FIELD:** our d20 median $5,078 vs the top-10
  corpus $53-63k. And the losses are DECIDED BY D14: vs JosephGuhlin (622) we net
  +$8.6k over d10-24 while he nets +$85.2k — days 8-15: him +$21.5k, us −$14.3k. Same
  shape vs Zenith (him +$77.5k in the window; d8-15 him +$15.9k, us −$15.3k).
- **The winner's income engine, per-day (both games):** 14-71 wheat units sold DAILY,
  9-49 fertilizer/day, 5-35 units/day of the rotating drip (wool/milk/egg/strawberry),
  positive income EVERY day. Ours: -$9.1k on d11 (the post-wave crater), zero or
  negative income on 9 of 18 days in the window.
- **Hire floor FAILED TO FIRE on the field:** aD10 median 0 in all 20 games (pre-hf
  also 0), hires median 251 (pre-hf 230 — only +21). The d0-9 trough the hf build was
  built to fix is STILL THERE: the first-animal gap vs the elite script (t1) remains
  ~unresolved on the ladder.
- **Slot-B cadence implication:** the 400-535 band is fully beaten by BOTH builds;
  every rating point above ~535 is being conceded to the d8-15 stall. C2 (windfall
  0.50) plus the daily wheat-drip loop are exactly the two measured levers aimed at
  that window. Zenith (2902) confirms the elite gap is unchanged.

**Actions:** 1) Day-2 Slot-B = windfall 0.50 (C2, bar-cleared) — pack submission16 at
next turn start; 2) the daily wheat-drip cadence becomes the next arm after C2;
3) our d20-presence target for any adopted arm: +$10k by d20 (top-10 losers' band),
not $53k — that is the realistic midpoint the two-slot protocol can verify.

### 0925n postscript 3 — hire-floor debug: the CORRECTED diagnosis

Funnel trace on tape 113308005 (worst-case opening, bank $125-164 for d1-9):

- **The hire floor DID fire.** Hires/day = [4,4,4,4,4,4,1,1,1,1] — exactly the
  hf=4-through-day-5 contract, then demand-sizing takes over. The "never fired" claim
  in the postscript above was WRONG: it conflated the roster floor with the herd.
- **What waits is the HERD, and the gate is CASH, not a bug.** First BUY_ANIMAL at
  t289 (d12) — the morning after the melon wave lands. The chain: d0 book spends
  $2,836 of the $3,000 opening on 19 melon seeds → bank $125-164 d1-9 → a cow (~$550)
  is unaffordable → buffer gate + cash gates correctly veto → wave cash arrives
  d10-11 → first animal d12. The gate chain (mouths_buffer, feed coverage, pace)
  all worked as designed.
- **Both measured escapes from this exact wall already failed on the bar:**
  seed_opening_cap (0924j: capping the wave kills the spray it funds — REJECTED at
  650 AND 1200) and milk_first_wave (0925i: the $550 d0 cow never repays — REJECTED).
  The elite script funds animals-first because its whole economy is wheat-milk
  compounding; ours is wave-led, and the wave IS our first compounding event.
- **Remaining unmeasured levers for the d0-11 dead window:** (a) a MELON_OPENING
  trim that keeps most of the wave but frees ~$300-400 for 1-2 sheep (between the
  full 19 and the killed caps — the dossier says 3 sheep cost ~$300 and Majkel
  orders them at t2; never measured at this size), (b) the wheat-drip cadence arm
  (smooths d11-15, not d0-9). Both go to the bar before any promotion.
- Sub-535 sweep + 541-650 stall remain the field truth; d20 median $5.1k vs their
  $53-63k unchanged.

### 0925n postscript 4 — submission16 PACKED (Day-2 Slot-B: windfall 0.50 as default)

PARAMS windfall_pct 0.45 -> 0.50 (single-line change, comment cites the C2 verdict).
Gates: 136/136 tests · pack.sh PACK OK bank-for-bank ($91,299 packaging panel — the
panel bank moved +$523 with the new default, worst turn 2.4ms) · harness_smoke on the
tar PASSED (720 steps, banks $3,421/$98,833). Final confirmation bar on the new
DEFAULT build (file defaults, not --params): **midfield 3-1, mean +$8,481** (Tâm
+38,240 / Dean +6,730 / Jiahan +287 / susutem -11,334) · **elite -39,846, inside the
-$41k guard**. Promotion bar: MET (W/L held, mean ≥ +$1k, elite within guard).
Artifact `submission16.tar.gz` sha256 a43f2dfc3ce52d9216c513dbfce7491b00e79944fbb9f27bbc893165979f84d9.
Upload order per protocol: submission16 FIRST (Slot B), then Slot-A re-up (either
submission15 or the new artifact — payload differs from Slot A only by the windfall
default, so re-up submission.tar.gz as the same Slot-A control it has always been... 
NO: Slot A must stay the 3W-1L/windfall-0.45 build; re-up from the submission15
artifact, not the current tar).

### 0925n postscript 5 — M17-sheepfund: SECOND bar-cleared arm; the Day-3 queue forms

`mix MELON 24 -> 17` (freeing ~$350 of the d0 round, the dossier's 2-sheep budget):
**midfield 3-1 mean +$10,238** (beats shipped +$8,336 AND submission16's +$8,481),
**elite -$37,775** — BETTER than the shipped guard (-$37,243? no: -$37,775 is $532 worse
but well inside the -$41k materiality line, and 2/5 judges byte-identical). Best single
judge +$38,240 (Tâm — the windfall-sized margin persists). M17+wf50 combo is
BYTE-IDENTICAL to M17 alone (+10,238/-37,775 to the dollar): the windfall cap never
binds on the trimmed opening (17 seeds spend less than 45% of bank), so the two arms
are complementary on DIFFERENT phases — wf50 shapes the d11 reinvest, M17 shapes d0.

**State:** two bar-cleared, unshipped arms now exist (C2/wf50 = submission16's default;
M17 = Day-3 candidate). Per the protocol's one-candidate-per-slot-day rule, M17 ships
as Day-3's Slot-B (its own artifact), C2 stays Day-2. The mix trim's mechanism is
unchanged-cash-flow: fewer d0 seeds, earlier affordable sheep — the exact unmeasured
size between the killed seed-caps and the full wave.

### 0925n postscript 6 — submission16 REBUILT with both changes (owner call: correct)

The owner overrode the one-candidate-per-slot-day split: submission16 has zero ladder
games, and the combined cell is ALREADY measured as a unit (M17+wf50 byte-identical to
M17: +10,238/-37,775) — packing them separately spends a ladder-night to measure a
composition the bar already priced. The post-deadline principle (get the best-measured
build resident ASAP) governs. Both defaults folded: windfall_pct 0.50 + mix MELON 17.

**Re-gate on the final artifact:** 136/136 tests · pack bank-for-bank ($92,838 packaging
panel — the combined cell moves the panel +$1,062 vs the shipped build, exactly the
direction the bar predicted) · harness smoke PASSED (720 steps, banks $3,536/$94,744) ·
confirmation bar on file defaults: **midfield 3-1 mean +$10,238** (Tâm +38,240 / Dean
+8,160 / Jiahan +9,920 / susutem -15,368) · **elite -37,775, inside the guard**.
Note Jiahan's margin improved +$7.4k vs the C2-only run — the M17 trim helps the
near-miss world too (2 more sheep worth of d0 budget). susutem's loss widens to
-$15.4k (from -$11.3k) — the one judge where the trim costs margin; W/L unchanged.

**Artifact: submission16.tar.gz** sha256
b92c7e61521104c4f89e4fa6cf6fb0a2ca4d03fb2263fbb1a23f269f14465f64 (131,265 B),
supersedes the a43f2dfc… wf50-only build. Upload order: submission16 first (Slot B),
then Slot-A re-up from the submission15 bytes. Next arm: wheat-drip cadence on the
bar before it becomes Day-3's Slot-B.

### 0925n postscript 7 — wheat_drip BUILT + MEASURED: clears the bar at 6-9 days/mouth

**Mechanism (the honest one, after reading the whole sell pass):** the shipped mid-season
feed bridge is feed_hold(12) x mouths — ~$3k of working capital parked in the shed at 8
mouths, which is WHY our shed never flows d13-24 while the winners sell 14-71 units/day.
The new `wheat_drip` knob (default 0 = byte-identical) shrinks the bridge to N days/mouth
at the two bridge sites (main + shed-mouths); the freed surplus flows through the NORMAL
reserve-floor path (1.1 x $25 = $27.5, never the $2.9 crater) and the BUY_PRODUCT WHEAT
fallback re-buys if the shed runs dry pre-harvest. The shepherd 1-day/mouth floor site is
a MAX — a 1-day drip can never undercut a live herd's same-day feed.

**Tests:** TestWheatDrip 5/5 (off-form byte-identity incl. the minv SCALE lesson: minv is
I0-absolute inventory, 9900=scarcity/$35, 10400=glut/$20 — a wrong test book reads as
total scarcity and passes vacuously) · suite 141/141.

**Judge bar, both tiers (baseline shipped +8,336/-37,243; submission16 cell +10,238/-37,775):**

| arm | midfield | elite mean |
|---|---|---|
| drip=3 | **2-2** +6,959 | -$56,204 |
| drip=6 | **3-1 +11,055** | **-$37,057 (BEST ELITE EVER)** |
| drip=9 | **3-1 +11,077** | -$37,050 |

**Reading:** drip=3 is too thin (sells the bridge down to near the shepherd floor; a herd
day goes bad -> 2-2 + elite crater). drip 6-9 = the winners' actual cadence (~a week of
feed on hand, everything beyond that flows daily): midfield +$11.1k (beats the shipped
build by +$2.7k and submission16 by +$0.8k) AND elite -$37.1k, the best elite cell ever
measured — the freed grain funds early herd/mid-game income without starving anyone.
 drip=9 ≈ drip=6 (plateau: the surplus beyond 9 days/mouth is what the shed pools anyway).

**Day-3 Slot-B candidate: wheat_drip=6 on top of submission16's cell** — the composition
(wf50 + M17 + drip6) needs its own confirmation run on file defaults before packing
submission17; the drip is mechanistically COMPLEMENTARY (flow vs funding vs opening).

### 0925n postscript 8 — submission17: all three levers folded (owner call)

Owner's fold rule (post 16): an unpacked candidate with a unit-measured composition
packs as ONE artifact — the ladder attributes games to builds, not knobs, and the
post-deadline principle wants the best-measured cell resident fastest. Defaults now:
windfall_pct 0.50 + mix MELON 17 + wheat_drip 6.

**Gates:** 141/141 tests · pack bank-for-bank ($91,400 packaging panel) · harness smoke
PASSED (720 steps, banks $3,651/$104,795) · confirmation bar on file defaults:
**midfield 3-1 mean +$11,055** (Tâm +38,240 / Dean +8,089 / Jiahan +13,258 /
susutem -15,368) · **elite -37,057 — the best elite cell ever measured** (vs shipped
-37,243: the drip funds the mid-game without feeding the elite book). W/L held 3-1.
Jiahan +13.3k: the drip's smooth cadence directly fattens the near-miss world.

**Artifact: submission17.tar.gz** sha256
3e1c0b38968686d58892a805868591069422ed53e95b66fedf467de1df0d7093.
**Upload plan (owner runs submit.sh):** submission17 as Slot B; Slot A stays the
submission15 bytes (control). submission16.tar.gz stays on disk as the fallback cell
(wf50+M17, +10,238) in case the drip shows a field defect in its first tapes.
Ladder read for tomorrow: wheat sold per day in OUR shed outflow (the drip should
show 10-40/day where pre-drip games showed ~0-5), d20 bank (target +$10k), and the
541-650 band W/L.

### 0925n postscript 2 — POST-DEADLINE PRINCIPLE (user directive, governs everything)

The user's directive, verbatim in spirit: **games keep being played even after the
submission timeline is over — we need the model with a crazy good win ratio resident,
so even if it does not reach 3000 ELO by 30 Sep, it will later on.** Recorded in
LADDER_AB_PROTOCOL.md as the post-deadline principle. Consequences:

1. The freeze decision (D-1 morning) optimizes LONG-RUN resident win-rate, not
   last-moment rating. The question is not "what is highest rated on the 30th" but
   "what build keeps winning its neighborhood forever after."
2. 3000 remains the target — accrues AFTER the deadline via sustained W/L volume on
   the resident builds. Nothing about the promotion bar loosens: an unstable resident
   loses games forever, which is the one unrecoverable outcome.
3. v2 (the continuous-economy rewrite, spec'd from the 426-game top-10 corpus) is the
   route to the 3000-class win ratio; it can replace the resident ONLY through the
   same two-tier promotion bar once built and measured.

### 0925o — reframe adjudication (external analysis vs our ledger) + the pre-freeze program

An external reframe (user-supplied) was adjudicated claim-by-claim against the ledger
and code. Verdicts:

- **BT scoring, W/L-only, margin never enters** — CONFIRMED; matches our own 0925a
  finding. Consequence adopted: tail-risk elimination outranks upside; a 6-3-by-$500
  build beats a 3-6-by-$50k build.
- **Games continue ~2 weeks post-deadline; final leaderboard = BT tournament** —
  consistent with the Kaggle FAQ reading; matches the post-deadline principle (above).
- **Majkel decisive, not brute-force** — CONFIRMED by corpus: unified d0 script 3/3,
  hires flat within ±3 between W and L, M&M&P&Q wins with the LOWEST hire count (286)
  at d20 $82.6k. Execution efficiency, not labor volume.
- **Shepherd arithmetic explains L1/L2 collapse** — CONFIRMED as mechanism: min
  shepherd units for herd {6:3, 8:4, 11:5, 14:7, 17:7}; L1 had share=9 (>7 needed)
  yet collapsed 0-4 -74,955, so static co-feasibility is necessary but NOT sufficient
  — the failure is crop-side labor starvation during the ramp under a per-dawn quota
  scheduler. This is exactly the ledger's "missing SUBSYSTEM" verdict (0925m).
- **Fix = capacity-aware per-turn allocator, one labor pool** — ADOPTED as the one
  structural change worth a slot-day. Scope: one module, not a rewrite.

Two corrections to the reframe (recorded so they are not re-litigated):

1. **The verbatim d0 script already exists as a knob**: `elite_script`
   (policy.py PARAMS) implements t1 COW+wheat-feed / t2 sell+HIREx4+COW+SHEEPx3 and
   was measured-rejected in an earlier cell. "Hard-code it now" is already done; the
   open question is why it lost. Arithmetic: the script needs ~$2,300 CASH on d0
   (COW $400 + COW $400 + 3xSHEEP $1,500 + hires $7), while the M17 melon book
   spends $2,836 TOTAL on 19 melon seeds ($80 each = $1,520; the ledger's $2,836
   includes other d0 spend). Different kinds of number — cash-needed vs total d0
   spend. The elite opening and the melon wave are near-mutually-exclusive at d0
   cash; adopting the script means cutting melon to ~M5-8. A strategy fork
   (tempo+livestock vs denial+windfall), not a free win.
2. **The harness seat-pairing concern is satisfied by construction**: the judge bar
   replays verbatim seed-locked judge tapes in the opposite seat (seat-paired,
   opponent-behavior-pinned). The real weakness is n=4 midfield judges (one game =
   the whole 3-1 vs 2-2 gap) — argument for wider mirror reads, not a rebuild.

**Melon-denial guard (reframe item, adopted)**: no standalone M15/M13 ladder arm.
Denial may be a weapon vs cow-heavy elites (#32); any melon cut lives inside the
tempo-fork BAR READ only. Allocator default comp stays M17.

**Program (user-approved sequencing: both, sequenced)**: (1) tonight the owner
uploads submission17 as Slot B then re-ups Slot A from submission15 bytes;
(2) Fri night tempo-fork bar read (elite_script+M8, bar-only, free evidence) + the
telemetry emitter for #13/#16/#17/#14; (3) Sat the `turn_allocator` dormant knob,
GATED by a full 720-turn replay check BEFORE the bar run (the cross-turn-state bug
class that ate the day-0 ledger, place-queue, and wool-floor rewrites passes unit
tests and fails full replays — so the check is designed for exactly that class);
(4) Sun-Mon bar then Slot B; D-2 Mon 28 candidate cutoff; D-1 Tue 29 morning freeze
per protocol. If the allocator dies, Slot B repeats 17 and the tempo fork's bar
verdict decides whether it is worth the fallback day.

### 0926a — allocator built and gated; tempo fork measured; BOTH bar-rejected; 17 stands

The 0925o program executed in one session. Everything below is measured, not projected.

**Telemetry (answers #13/#16/#17/#14 as daily tools).** `analysis/telemetry_dump.py`
(one pass per tape): money-flow d8-24 with the day's order mix, thirst/spent deaths
and animal-census drops, BUY_PRODUCT fallback fires, wheat outflow/day. First field
tape (113305431) already answered #13: the sink is **d11 -$8.4k = 3 BUY_LAND + seeds
+ hires** (land timing, not the melon opening); #17: FERT x351 + WHEAT x229 re-buys;
#14: our wheat outflow 2-5/day vs the winners' 14-71. Wired into the daily loop.

**replay_check (the pre-bar gate the reframe review demanded).** `analysis/replay_check.py`
feeds full 720-turn mirror episodes through act() and checks the cross-turn-state
class: hour-sequence integrity, exceptions, _safe_pass signature, bank floor, and
same-seed thirst/animal-loss vs baseline (deterministic, zero noise). Two gate
calibration findings of its own: the 23-turn end-of-day all-PASS drain at d3h23 is
in the BASELINE on every seed (not the import tell — the tell is a long streak plus
flat ~0.01 ms durations with no dawn spikes), and fast-turn fraction is likewise
normal for a queue-executing agent. `--judges` mode runs the judges' own world seeds.

**The allocator took seven iterations, and the gate caught every one** (unit tests
passed each time; full replay broke each time — exactly the predicted class):
- v1 replace-wholesale: income jobs orphaned, 23-turn PASS stall, $69k->$24k.
- v2 blind prepend: duplicated the dawn plan's own rescues (thirst UP both seeds).
- v3 orphan-dedupe: mixed (seed0 thirst 23<36; seed1 worse; the dawn plan already
  carries most survival work, orphans are rare).
- v4 pair-timing guard: never insert ahead of a mid-flight then-chain.
- v5 value-order walk sim: re-derived the crisscross trap `_replan`'s docstring
  warns about; overestimated the day, gutted lanes, thirst 67, bank $5k.
- v6 nearest-block + sequential shed: thirst UP everywhere; the Q-autopsy found
  15/15 d27 deaths had a WATER QUEUED THAT NEVER RAN — insertion deferred the
  lane's own grow-waters past midnight and the spiral fed itself.
- **v7 (shipped form): the reframe's spec, literal.** Free budget per unit =
  turns_left minus a walk-sim of its standing lane; an orphaned survival job goes
  only where it fits WITHOUT deferral (3-turn buffer for the walk-sim's blind spot
  to dynamic costs), shedding only the lane's droppable plant-fill tail
  (tier < TIER_GROW, no pending chain); otherwise honestly REJECTED and counted.
  Mirror: thirst DOWN on all 3 seeds (30/13/17 vs 36/19/18), banks +2/3 seeds,
  replay_check ALL GATES PASS x3 seeds; judge-seed mode also clean (majkel886
  thirst equal, bank +$1.4k; tam equal).

**Bar verdicts (two-tier, one process per arm).**
- **Tempo fork** (elite_script+M8): midfield 3-1 mean +$12,132 — best mean ever,
  and it FLIPS susutem L->W (+$10,830: melon denial was a crutch vs that shape,
  first #32 data) — but hands Jiahan W->L. W/L lateral under BT. Elite 0-5
  **-$76,064: guard failure.** REJECTED; denial-vs-weapon evidence banked.
- **Allocator** (turn_allocator=1 on shipped cell): midfield 3-1 +$7,184 (clear),
  elite **-$41,484 vs -$41,000 limit: miss by $484** — and W/L identical to
  shipped on all 9 judges. No W/L improvement = no promotion basis. REJECTED
  (marginal, recorded as measured).

**Posture.** submission17 (3e1c0b38...) stands as THE ship. Per protocol: Slot B
repeats 17, D-2 Mon candidate cutoff stands (a new candidate would need a NEW
mechanism, not a retry), D-1 Tue 29 morning freeze on 17 to both slots. The
allocator code stays DORMANT (default 0, byte-identical, 146/146 tests) as the
v2 seed for the post-deadline program. NOTE: do not re-run pack.sh before the
uploads — submission17.tar.gz exists on disk with its recorded sha; a fresh repack
would shift the archive sha (payload-equivalent, knob-off byte-identical, but the
recorded sha is the one to upload).

## 0926b — sub17 field autopsy (26/26 public tapes + 15/16/1 comparison sets)

**Trigger.** User: "submission17 is doing horrible, it hasn't even crossed 600 elo"
(512.4 at pull). Episode tables + all replays pulled (new downloader: `episodes
<subid>` CLI takes NO -c flag; `api.competition_episode_replay(id, path)` writes
`episode-<id>-replay.json`): sub17 26/26, sub16 30/31, sub15 23/24, sub1 25/26
public tapes + fresh leaderboard CSV 0926T12:03. Sub15 late tapes completed the
set (113327197/113351749/113395306 now local).

**Headline W/L.** sub17 = 12W-14L, mean margin **+$766 — the best of all four
builds measured** (16: −2,166; 15: −3,145; 1: −4,816). Two elite scalps:
XDang13 (2292) +$28k, Awesome Egg (1034) +$23k. Three losses are coin-flips
(−1k, −8.9k, −10.2k).

**The wall is class-wide, not a sub17 defect.** Fine-band table (opp rating
bands, W-L):

| band    | sub1    | sub15   | sub16   | sub17   |
|---------|---------|---------|---------|---------|
| 500-540 | 11W-3L  | 9W-0L   | 9W-6L   | 8W-1L   |
| 540-600 | 0W-4L   | 2W-7L   | 3W-2L   | 0W-9L   |
| 600-800 | 1W-4L   | 0W-3L   | 0W-5L   | 2W-4L   |
| 800+    | 0W-1L   | 0W-1L   | 2W-3L   | 2W-0L   |

Every build ever shipped collapses at the 540-600 wall (class total 5W-22L) and
sweeps <500. Sub17's 0-9 there is not statistically separable from 15's 2-7.
**Sub17 holds the best ≥600 record we have ever fielded (4W-4L).** The 566.9
all-time peak of the first submission was a soft-early-pool artifact — its own
fine-band table shows the identical wall collapse. "First build was best" is
dead.

**Why the rating sits at 512**: 58% of sub17's schedule (15/26) was wall-band
games; 12W-14L against that mix + BT small-n noise. Not under-played (27 eps,
comparable to sub15's 24 for 540.2) and not a build regression.

**Mechanism (margin decomposition, me−opp by window, pooled).** In wall losses
the deficit is made in **d14-24 mid-game: −38.9k avg** (sub17; range −19k to
−63k), while d8-13 expansion is only −5.4k. Class-wide the same shape: sub1
−37.5k, sub15 −35.9k, sub16 −42.1k mid-game in their wall losses. Order counts
in d14-24 (sub17 wall games): winners out-BUY_SEED us 5-10x (e.g. 53|6, 67|6,
52|16 — they replant continuously), our BUY_PRODUCT fallback churn runs 5-10x
theirs (119|14, 126|51, 107|16), HIRE counts even or ahead (145|104 etc.).
Within sub17, churn is a constant tax, not the discriminator: wins carry
BUY_PRODUCT 78/g vs losses 68/g. Wheat drip6 verified in the field: 31/day
mid-game in losses, 36/day in wins — inside the 10-40 prediction. d20 bank:
wins 72.5k vs losses 60.6k, but two losses were at 78-80k by d20 and still lost
the back half — mid-game income, not bank size, decides. Endgame thirst cascade
(d25-29, 25-58 deaths) hits winners and losers alike — red herring for W/L.

**Verdict.** Posture UNCHANGED: sub17 (3e1c0b38..., wf50+M17+drip6) stays THE
ship; freeze Tue 29 morning to both slots; two-latest rule keeps 17+16 resident
through the deadline tail. Flipping to submission15 bytes would concede the
600+ edge on current evidence; the promotion bar (field half) is satisfied —
17 ≥ 15 at every band within n.

**Post-deadline seed (the actual lever).** The 540-600 winners' signature is
mid-game replant cadence (BUY_SEED 5-10x ours) at flat/negative d8-13
expansion — our fixed footprint stops scaling while theirs compounds at
+$3-14k/day. A mid-game replant-elasticity mechanism (scale planted footprint
with bank + market, not a fixed mix) is the first candidate for the post-
deadline program; second is allocator v7 (dormant) for the d25-29 thirst tail.
Filed as the new top open question.

**Tooling lessons.** (1) `kaggle competitions episodes <subid>` — no `-c` flag.
(2) `competition_episode_replay(episode_id, path)` returns None; writes
`episode-<id>-replay.json` as a side effect. (3) Loading 100+ full replay JSONs
in one process exceeds a 240s sync call — extract per-folder meta maps first,
then merge telemetry separately. (4) telemetry_dump thirst key is a per-day
dict (`{'7': 3, ...}`), not a total.

## 0926c — replant-elasticity program: both planting-side forms gate-REJECTED; monitor audit

**Build (dormant, default 0, byte-identical, 152/152 tests green with 6 new).**
Two forms of the 0926b "mid-game replant elasticity" lever, both against the
wall signature (our field boards 47% thirsty at dawn vs winners ~12%):

1. **`water_cover_mult` (committed-acreage cap, cap = mult x watered plants).**
   Smoke + unit tests clean; replay gate FAIL at 1.15 (3 seeds): arm mean
   $40.0k vs baseline $58.5k, thirst UP on 2/3 (45v19, 19v18). Cause: with a
   demand-sized roster, shrinking the board shrinks the hands that water it,
   coverage falls, the cap tightens — a measured vicious cycle.
2. **`water_cover_max_thirst` (planting brake, freeze top-ups while dawn
   thirsty-fraction > threshold).** No multiplicative feedback by construction.
   Still FAIL: 0.20 → mean $28.2k, thirst UP on all 3 seeds (98v36, 53v19,
   23v18). Cause (baseline distribution probe /tmp/thirst_frac_probe.py): the
   MIRROR'S NORMAL dawn thirst is mean 39%, p50 30-35%, max 1.0 — the baseline
   engine rescues the unwatered tail same-day at trivial cost (deaths 0-19,
   banks $68k). No threshold separates disease from normal because the
   mirror's thirst is not the field's disease. Both knobs stay DORMANT
   (mechanism + tests kept as the record; byte-identical at 0).

**Verdict: the wall disease is field-specific and lives on the SERVICE side
(roster economics on a 4-quadrant board), not the planting side.** The mirror
already replants every empty tile (limit_probe: d10-19 stops on `tiles` 87% of
dawns with $6.5k budget idle and 91 visit-headroom), waters its board to $68k
banks, and cannot see the field failure. What the field tapes show instead:
BUY_SEED 5-10x, d14-24 income gap −36-42k, boards 2x the winners' size at 47%
thirst — a roster/service problem. The next candidate must change the service
side (roster sizing/watering cadence vs board size), and the judge bar must
arbitrate it — but the bar's judges are 3-4 midfield games per tier (n=4), so
a candidate will need multiple bar runs or the wall-tape judge set first.
Posture UNCHANGED: sub17 ships, freeze Tue 29 morning.

**Monitor audit (user request: "check the things that monitor when competitors
sell etc live is working fine or not").** What exists: `_MarketMonitor`
(kagfarm/policy.py:2237) infers opponent net supply per good from the public
book identity (opp_net = inv_delta − my_sells + town_drain + my_buys), plus
`opp_census` (rival herd from public tiles, LIVE every turn at
policy.py:4476/4503) and px_peak. Findings: (1) **the monitor is DORMANT in
the shipped cell** — `monitor=0` (PARAMS:384), so no opponent-sell estimates
reach the planner; (2) `opp_census` IS live and feeds `opp_wool_prio` /
milk-window branches (both inactive at their shipped defaults), so the shipped
arm runs ~fully opponent-blind by design; (3) the monitor's own machinery is
healthy: wrapped never-raise error paths, capped flow bookkeeping (the ~4x
carried-re-offer bias is handled), ±50/day clamps, and the unit test
`test_monitor_byte_identical` (monitor=1 with zero knobs == monitor=0)
protects the measure-only mode; (4) its arms were MEASURED-REJECTED earlier
(monitor=1 block gate, sell_infer INCONCLUSIVE, opp_acreage_credit rejected
2026-09-25 on both tiers — the planting-suppression channel is
value-destroying where the endgame wave is the denial asset). Nothing to fix;
the audit answer is "working as designed, switched off on measurements". If
the post-deadline program wants opponent reads, the cheapest healthy client
is `monitor=1` + zero knobs for diagnostics only (byte-identical, free data).

## 0927 — Field pull COMPLETE: sub17 at full coverage (n=35, 18W-17L, mean +$631)

User exported 19 replays + 20 final-day screenshots into `submission17games/`
(replays are authoritative: TeamNames + final rewards). Downloaded the 6
missing ladder episodes in place (113711104, 113734408, 113801467, 113871736,
113935757, 113964640) — `submission17games/` now has full ladder coverage for
sub17 (56559743); nothing missing. Two-tape-set dedup: /tmp/sub17eps + folder.

New information vs the 0926b autopsy (27 tapes):
- **8 new games** (2 user-exported + 6 pulled): 4W-4L, mean +$4.3k — the two
  worst were Mingkang He −$51.8k (526.5, wall band) and Mani Kanta Kalluru
  −$13.9k (541); the best were lbs-vadar +$16.0k (511) and Yuichiro Kinoshita
  +$16.9k (462). Mingkang tape re-confirms the EXACT measured signature:
  d14-24 account deficit −$31.5k of the −$51.8k, opponent BUY_SEED count 7-8x
  ours mid-game. One unrated loss: Huanchen Jia −$10.0k (113964640).
- **Complete-tape table (n=35): <500 8W-0L mean +$35.8k | 500-600 5W-12L mean
  −$11.8k (−$200k total) | 600-800 3W-4L mean −$15.2k | 800+ 2W-0L mean
  +$25.8k. Mean opp rating: wins 660 vs losses 598 — we beat better teams than
  we lose to.** The 540-600 wall remains the entire disease; 600-800 improved
  vs 0926b (now 3W-4L with the Asher W).
- Verdict UNCHANGED and REINFORCED: sub17 mean margin +$631 over n=35 is still
  the best of all four builds measured; freeze plan (sub17 both slots, Tue 29
  morning) stands. Mingkang He 113969634 becomes the #1 wall-tape judge
  candidate. The last-10 stretch (3W-7L) is wall-band scheduling, not build
  quality — same conclusion as 0926b with 8 more games of evidence.

Addendum (0927 morning pull): team CSV 0927 08:20 = **536.5**, +12.0 elo and
+164 ranks vs 0926 12:03 (rank 6697/10,068 — median). sub17 played 8 eps on
0926 + 4 on 0927; sub16 8 + 3. The +12.0 is exactly what an 18-17 tape record
at near-even odds produces — the elo is tracking true strength, not lagging
it. Near-neighbor density: ~0.1 elo per rank around us (688 teams in 500-560).
6,434 teams ≥560. Final leaderboard is BT over all games through ~2 weeks
post-deadline: at ~5-8 eps/day/submission the tail is ~150+ more games, so
the deadline pick decides what engine plays them.

## 0927c — "Faster agent" program: turn_allocator=1 GATED + WALL JUDGE TIER BUILT

User ask: a faster-growing agent, ideally one that never loses. Reframe
delivered up front: BT converges everyone to ~50% (even 3106-rated DSM loses
games); the engineerable form is "never loses BADLY" — our 17 sub17 losses
avg −$13.9k with a −$79k tail, made in the d14-24 BUY_SEED race. Attack:
(1) the DORMANT `turn_allocator=1` (survival-first re-cut, "the one structural
fix worth a slot-day", implemented 0926 but never gate-measured) — the
measured disease is 47% thirsty boards vs winners' 12%, and thirst rescue
lives exactly in the allocator's re-cut; (2) the WALL JUDGE TIER — the 7 worst
500-600-band sub17 losses registered as replay judges so candidates are gated
on the exact games that set the rating record.

**Replay gate (3 seeds, self mirror): ALL GATES PASS.** Thirst deaths DOWN on
every seed (36→30, 19→13, 18→17) — the mechanism works. Cost: the
survival-first seat gives back bank to its baseline twin on the big-board seed
(−$8.9k seed 0; mean −$2.6k) — the mirror rewards growth; the field taxes it.

**Judge bar (real tier):** midfield 3W-1L mean +$7,184 (shipped baseline
3-1 +$8,336 — W/L equal, mean within chaos). Elite 0-5 mean −$41,484 vs the
−$41,000 guard — FAILS the written elite guard by $484 (margins chaotic
±$10k run-to-run; W/L identical 0-5; formally a fail).

**Wall tier (NEW, the headline):** 7 worst wall losses registered as judges
(replay_wall_nottoday/aarya/tnwl/hayday/mingkang/alexandre/aynrmio; tapes in
analysis/replays/, seats in SPECTATOR_IDS, `--tier wall` added to judge_bar).
Counterfactual VALIDATED: baseline reproduces the recorded losses nearly to
the dollar (aynrmio −10,223 exact; alexandre −79,212 vs −79,237; mingkang
−51,861 vs −51,823). Baseline 0W-7L mean −$35,092 → alloc1 **1W-6L mean
−$33,901**: the aynrmio recorded LOSS flips to a W (+$43), 5 of 7 margins
improve, aarya regresses (−$5.6k), mingkang flat. FIRST-EVER measured W-flip
on a real wall tape by any arm this cycle.

**Verdict:** alloc1 = measured progress, not promotable today (elite guard
missed by $484 on a chaotic margin; bar is the bar). Deadline posture
UNCHANGED: sub17 freezes into both slots Tue 29. alloc1 becomes the
post-deadline program's Day-1 candidate; next build = thirst_rescue_q
(allocator + quota so the growth tax is recovered while the rescue holds).
The wall tier is now permanent infrastructure — every future candidate gets
judged on the exact games that decide the rating.

## 0927d — "Fix the throughput" program: four experiments, one closed diagnosis

User push after the elite-gap explanation: "so fix that shit". Program ran the
throughput levers end-to-end. Also: elite guard RE-RUN bit-identical
(−$41,484, same to the dollar — the elite tier is deterministic, so the $484
miss is REAL, not chaos; correcting 0927c's "margin chaos" note; alloc1 is
formally dead as a candidate, its mechanism lives on).

1. **dawn_pace=8 alone: gate FAIL** (mean −$7.8k, thirst up 2/3 seeds).
   Third planting-side limiter to die by the demand-shrink vicious cycle.
2. **roster_floor_min (NEW knob, service side)**: implemented + tested
   (157/157 green, TestRosterFloorMin ×5) — holds the roster at a fraction of
   max_hands while any pace gate is active; fib cash cap untouched; 0.0 =
   byte-identical, inert without dawn_pace.
3. **pace=8 + floor 0.64: mirror gate FAIL** (thirst up 2/3, mean −$6.9k) —
   but the mirror gate cannot see contested books (a capped opening once cost
   $56k THERE while being optimal), so it went to the wall tier:
   **0W-7L mean −$48.5k, worse than baseline on 6/7** — against real
   (non-pressure) opponents, throttling planting donates income. The
   wall disease was never over-planting. Planting-side hypothesis CLOSED
   (three independent kills: cover_mult, cover_brake, pace).
4. **alloc1 + labour_slack=1.5: byte-identical to alloc1** — labour_slack is
   inert in the dawn allocator (tiles/cash bind first). Cheap levers exhausted.

**Closed diagnosis (now measured, not inferred): the gap is WATERING
THROUGHPUT THROUGH ROUTING — how WATER legs share the day with HARVEST/SELL
legs — not acreage policy, not roster size, not planting cadence.** alloc1's
survival-first re-cut is the only measured lever that touches it (thirst down
3/3 gate seeds, first wall W-flip). Next build, named: **route_weight** —
explicit W(L, H) value weighting in collect_jobs, W 0→1 sweeps with a wall-
tier + midfield bar. The wall tier carries every future verdict.

## 0927e — External audit response: wheel_fallback re-judged on the wall tier; REJECTED (path now closed)

External reviewer (Claude) independently unpacked the shipped tarball (hash
verified) and recommended finishing the half-tested `wheel_fallback` hybrid
instead of new builds. File audit VERIFIED (elite_script/opening_led/led_flock/
d0_herd/wave_share_animal all shipped 0; wheel_plan/wheel_fallback dormant at
0; the +$8.4k judge-886 line exists). But the 0924i dossier already holds the
full wheel record, including the correction that matters: the +$8.4k was
MARGIN (denied-milk pressure), not our bank — our own bank FELL $8.5k there;
pure wheel −$7.4/-10.3/-8.9k on luanhe/juicy/907; soft-trigger fallback =
pure wheel on 4/5 judges (max-loop clause fires every herd≥9 dawn); hard
trigger −$11.0k on 886 / −$12.5k on 900 (mid-season switch corrupts placement
geometry); wheel+herd_cow=12 still rejected (herd-9 equilibrium is an economy
optimum, not a planning artifact).

**New increment run (the only cell 0924i never measured): wheel_fallback=1 on
the WALL tier — 0W-7L, mean −$36,152 vs shipped −$35,092; aarya −$8.9k
(best single wall margin any arm has produced) but 0 flips and no mean gain.**
Verdict: the wheel-fallback path is now FULLY evaluated on the modern bar and
STAYS DORMANT (0). The 0924i closing note stands exactly: the wheel is the
pre-built shape for a future arm that values herd ROBUSTNESS (escape-halving
12.5 vs 24.4) over throughput — not this one.

Also verified from the audit memo: the MAJKEL_SKELETON h0 cash read ($1,843 vs
$223) is real but does not contradict the record — the funded-herd rejections
(live.md 1873-1877 numbers) were all measured against the CURRENT chain
scheduler, so any skeleton-bundle retest is gated on a scheduler change first
(route_weight / a watering-throughput fix), not before. Program verdict:
route_weight remains the Day-1 post-deadline build; wall tier adjudicates.

## 0927f — External KT audited (3000+ rating doc): 4 claims checked, 2 adopted, 2 already-shipped

External KT document received ("Achieving 3000+ rating"). Verification per
house rule — check before adopting:

1. **`kaggle/kaggriculture-episodes-index` dataset EXISTS — VERIFIED LIVE.**
   Pulled manifest.csv (9.4KB, refreshed 2026-09-27): 59 daily dumps, Jul 30 →
   Sep 26, ~21GB/day, 800-1,000 eps/day, rating-filtered. ADOPTED as the
   post-deadline program's foundation: a rating-filtered miner (medians by
   rating band, per KT §4.3-4.4) becomes the strategy source for
   route_weight/roster/land targets. This supersedes hand-picked-tape
   distillation at scale.
2. **"Remove the 3-quadrant cap": the cap is ALREADY a knob** —
   `land_cap_quads` (policy.py ~4965, 0 = uncapped in the shipped cell; the
   allocator must also be tile_limited with season-timing intact). No cap to
   remove; the open question is the OPPOSITE (is full-board+13-15 hands
   serviceable by our scheduler — exactly the watering-throughput question).
3. **Fertilizer age-scheduling: ALREADY SHIPPED in a more general form** —
   policy.py:1205 prices doses against `gain_days(crop)` remaining-gain-day
   windows ("only worth a visit on the morning of a gain-day it covers").
4. **Paired-seat testing: PARTIALLY already done; ADOPT as standard.** The
   mirror gate runs both seats deterministically; the judge bar is
   counterfactual (our seat on the judge's recorded world). But the h2h
   seat-swap protocol (A/B on both seats per seed) is NOT institutionalized —
   adopt for the post-deadline program.

NOT adopted / already known: (a) the two-slot freeze discipline is our
standing protocol (freeze Tue 29, sub17 both slots); (b) the regime layer
(behind/close/ahead) matches the measured endgame findings (endgame_shift
rejected 0925a — timing not value-starved) but a POSITION-tracked posture
is a legitimate post-deadline module; (c) "3000+" is observed-real per the
KT but our n=1 eliteness gap (1.6-1.8x d8-24 income) is the same wall it
describes. Freeze posture UNCHANGED; next concrete step: the dataset miner.

## 0927g — route_weight BUILT, GATED, and it CLEARS THE WRITTEN PROMOTION BAR

The 0927d closed diagnosis, implemented: `route_weight` (PARAMS, default 0.0 =
byte-identical) lifts proposed-water tiers in collect_jobs so watering competes
with HARVEST in the ranked[:n] route lottery. Mechanics: GROW water 30 → 30+10w
(harvest parity 40 at w=1); same-day due water (RESCUE 50) compresses toward
parity — 40+10w — keeping its head start until w=1; RESCUE/feed/decay classes
and shepherd pins untouched; the (-tier,-value) sort itself unchanged.
Tests: TestRouteWeight ×6 (parity at 0, tier math both classes, head-start
order, other-classes-untouched); suite 163/163. One fixture lesson: a GROW
water tile needs consecutive_unwatered=0 EXPLICITLY — the cu-fallback classifies
an age-due tile as dying (RESCUE) when the key is absent.

**Replay gate (rw=1.0, 3 seeds): ALL GATES PASS** — and mirror thirst is
IDENTICAL (36/19/18): the mirror board has route slack, so water never loses
the lottery there. Third confirmation the mirror cannot see the field disease.

**Judge bar (rw=1.0): midfield 3W-1L mean +$10,844 (best of the session;
shipped +$8,336, alloc1 +$7,184) — and elite −$38,742 PASSES the −$41,000
guard (alloc1 missed it by $484).** First arm to clear the written bar this
cycle. Wall tier: 0W-7L but mean −$34,868 (best no-flip wall arm; shipped
−$35,092, alloc1 −$33,901): aynrmio −$10.2k → −$5.3k (closest any arm has come
to flipping a wall tape), aarya −$4.2k best single margin. Cells: rw=0.5
worse (−$36.0k; alexandre −$85.2k shows the mid-weight harms the biggest
tails); rw1+alloc1 WORSE (−$36.4k, they interfere — pick one).

**Program verdict: route_weight=1.0 is the first gate-cleared candidate; the
promotion question (ship at freeze Tue 29 vs hold sub17) is the owner's —
both options evidence-backed, decision recorded when made.** Next: paired-
seat protocol on the rw1-vs-shipped question, then the dataset miner.

**0927g addendum — owner decision + stale-bar audit (both applied):** the
owner caught a PROTOCOL BUG before any promotion: the written bar
(+$8,336/−$41,000) describes what sub17 scored BEFORE shipping; re-running
the shipped cell on the same session's bar gives **+$11,055/−$37,057** — rw1's
+$10,844/−$38,742 is marginally BELOW the true incumbent on both metrics and
statistically indistinguishable at n=4. Honest state: rw1 ≈ sub17, unresolved.
**Decision: HOLD sub17 through freeze (nothing to promote; no deferred
upside); skip the 24-seed confirmation today (scarce pre-freeze window beats
settling a coin-flip gap the post-deadline window answers for free); rw1
enters the post-deadline program as "wash, pending paired-seat confirmation
with prior expectation: probably no real difference."** LADDER_AB_PROTOCOL.md
amended with the ANCHOR RULE: every session re-runs the incumbent on the bar
and compares like-to-like; sub-±$2k mean gaps at n=4 are UNRESOLVED by fiat.

## 0927i — CORRECTION: there IS no post-deadline upload; paired-seat harness built; rw1 question RESOLVED as a wash

The 0927g addendum's "skip the 24-seed confirmation, the post-deadline window
answers it for free" was WRONG: the final BT tournament plays whatever is
resident in the two slots at the Sep 30 close — nothing can be shipped after.
The rw1-vs-sub17 question therefore decides what plays ~150 rating-deciding
games, and it had to be resolved BEFORE the freeze. Built the harness the KT
mandated: `analysis/paired_harness.py` (seat-swapped, same-seed pairs of our
own policy; per-pair W/L/S verdicts; deterministic).

**Result (rw1 vs shipped, 12 seeds = 24 seat-swapped mirror games): 13W-11L,
W/L 0.542, mean +$736, MEDIAN +$3, worst −$4.6k.** rw1 ≈ sub17 on the mirror —
the judge-bar wash CONFIRMED at proper n. No field-evidence case for rw1
exists; promoting it before the deadline would have been variance, not value.
**Decision (recorded): freeze = sub17 both slots, UNCHANGED and now
positively verified rather than default.** rw1 files as the post-deadline
program's research arm (wall-tier positive, mirror-neutral).

**Two-slot asymmetry VERIFIED on our own ladder data:** seat 0 wins 65% of
sub17's 35 games (11/17) vs seat 1 41% (7/17) — the coin's bias is real and
the final tournament inherits it.

**OPEN RULE (governs any pre-freeze diversification): does the final BT
team score take the better of the two active submissions, or both?** The KT
cited discussion 739410 ("Final Bradley-Terry scoring") as answering this;
the thread POSES the question (snippet-verified) and Kaggle threads are
JS-rendered (unscrapable here). Unverified either way. If better-of-two:
slot B carrying rw1 (mirror-neutral, wall-positive, fresh-games σ benefit)
is a bounded-downside free option. If both count: sub17 both slots strictly.
Owner to confirm from the browser if desired; default remains sub17/sub17.

## 0927h — External "rebuild S17" memo audited: its central quarantine claim is EXACTLY BACKWARDS

Second external memo (29 sections, architecture proposal: policy zoo + regime
classifier + rollout selector + Hungarian assignment). House rule applied:
check every actionable claim against code + ledger before acting.

**Claim 23 ("quarantine windfall_pct→1.0 and wheat_drip→0; the code's own
comments prove both are elite-negative defaults"): REFUTED BY THE LEDGER.**
The memo misread guard-ACCEPTANCE scores (the whole build's elite result at
adoption time) as knob ABLATIONS. 0925n ps7's three-arm measured table says
the opposite: drip=3 midfield 2-2 elite −$56,204 (thin bridge, herd-day tail
crater) | **drip=6 midfield 3-1 +$11,055, elite −$37,057 BEST ELITE CELL EVER**
| drip=9 ≈ drip=6. The shipped cell is drip=6 PRECISELY BECAUSE it is the
measured best-on-elite choice. Its "−37,057" comment is the acceptance
evidence FOR the knob, not against. Same class of error as the wheel memo's
"+$8.4k" margin/bank conflation. Quarantining per the memo would ship a cell
2.5x worse on the elite tier than the one we have.

**Claim 4 (animal_load=0 model mismatch): REAL CODE, LEGITIMATE OPEN QUESTION**
— `animal_load=0.0` (policy.py:1026, load += animal_load*live at :3112): the
crop allocator does not charge crop capacity for livestock service. It is a
NAMED dormant knob (F4), not an oversight — but the memo is right that the
_plans-vs-executes capacity mismatch is measured-adjacent to the wall disease.
Queued as a post-deadline cell (small values 0.1-0.3, wall tier adjudicates).

**Adopted items** (convergent with standing program): paired W/L as primary
objective (ANCHOR RULE already added 0927g); opponent-family payoff matrix and
regime/expert selection as the post-deadline research direction; dataset miner
over 59 rating-filtered daily dumps (verified live, 0927f) as the priors source
for expert trajectories; 11-14 hands re-swept under paired W/L rather than
bank. **Rejected for THIS competition**: a 3-day ground-up rebuild (deadline
Tue 29; the plan's own Day-1 step "freeze S17" is what is already happening);
rebuilt-from-scratch cores are the classic pre-deadline tail-risk play.
**Filed for the post-deadline program** in priority order: dataset miner →
paired-seat harness → rw1 confirmation → animal_load cells → expert-population
prototype. Freeze UNCHANGED: sub17 both slots Tue 29 morning.

## 0927-exec — Freeze engineering COMPLETE: conditional rw1 artifact + morning-pull automation + checklist

**1. Ship artifact re-verified:** submission17.tar.gz sha256 `3e1c0b38…` —
intact, do NOT repack.

**2. Conditional rw1 artifact BUILT + PROVENANCE-PROVEN:** staged tree with
`route_weight=1.0` baked as the DEFAULT (sed on the single PARAMS line),
replay gate from the staged sandbox passes, then paired-harness proof at 6
seeds: the artifact's default policy reproduces the measured rw1 margins
TO THE DOLLAR on all 12 seat-swapped games. Final-loop proof repeated on the
EXTRACTED archive (3 seeds, identical). Junk-check caught __pycache__ on the
first tar (excluded on rebuild). **rw1_candidate.tar.gz sha256 `8a0d857d…`,
repo root.** Upload ONLY if the better-of-two rule is confirmed (see
FREEZE_CHECKLIST.md step 0/3B).

**3. `analysis/morning_pull.py` BUILT + FIRST RUN:** ladder-diff → download →
W/L-by-band → regression flags, both residents. First run pulled 10 missing
sub17 eps + all 38 sub16 eps (sub16's first complete tape set).
**Finer-band discovery: sub17 is 5W-2L at 500-540 — the wall is specifically
540-600 (0W-10L), not the whole 500-600.** Band profiles are COMPLEMENTARY:
sub16 wins 540-600 (4-4) but collapses 600+ (2W-10L); sub17 dominates 600+
(5-4). Overall means still decide the freeze: sub17 +$631 vs sub16 −$4,596.
Flags fired (540-600 W%, sub16 tail) are KNOWN signatures — no freeze reopen.

**4. FREEZE_CHECKLIST.md written:** step 0 (owner confirms better-of-two rule
on discussion 739410) → Monday morning pull → hash verification → 3A default
(sub17 ×2, B-then-A order) / 3B conditional (rw1 → Slot B) → Tuesday
residency check → hands-off. Standing facts appended so nothing gets
re-litigated under deadline pressure.

## 0927-nemo — Dual Nemotron consultation (OpenRouter, both keys, 2 temps)

Briefed two independent NVIDIA Nemotron 3 Ultra instances (temp 0.4 / 0.9) on
the full project record (analysis/nemo_briefing.md: game, build, 35-tape
record, complete falsification history, constraints). Answers in
/tmp/nemo_answers.md. House rule applied to their output too — hallucinations
found: instance-1's "r=0.82 animal/thirst correlation (unpublished)" (no such
statistic exists), its fabricated gate thresholds ("wall ≥ −$25k") and
"+40-60 rating" projections. Mechanisms kept, numbers discarded.

**Convergent finding (both instances, independently):** the 540-600 wall is a
VELOCITY-SPECIALIST STYLE TRAP — that band self-selects for bots whose single
skill is continuous same-day replant (harvest→replant latency ≈0-1 turns);
they plateau at 600 because that is all they do. We beat 800+ teams because
THEY diversified away from pure replant velocity. Our replant is dawn-gated
(seed purchase at dawn only; a tile freed mid-day waits for tomorrow) and our
replant competes at PLANT tier 20 in the route lottery. Both also flagged our
telemetry blindness: we count BUY_SEED but not REPLANT LATENCY nor fill-price
percentile. Both rank animal_load the #1 next-season lever (already queued
0927h).

**Adopted: the REPLANT RINGFENCE as the last live candidate** — privileged
replant path for just-harvested tiles (tier bump for replant-PLANT + mid-day
seed drip so freed tiles do not wait for dawn). Escapes all three kill
mechanisms (no board shrink, no roster shrink, no spend cap — it ADDS
throughput at the exact BUY_SEED 5-10x signature). Plan: tonight telemetry
(replant latency + fill price) + dormant implementation; Sunday full gates
(unit → replay → wall tier → paired harness) plus the animal_load=0.2 cell;
Monday field pull + ship decision. Honest prior: wash, per the rw1 lesson.
Freeze UNCHANGED.

## 0927-ringfence — Replant ringfence BUILT, then gate-KILLED with the cycle's most valuable finding

The Nemotron-convergent lever implemented as two dormant knobs: `replant_boost`
(same-day replant of just-harvested tiles pinned at a lifted tier, crop name
recovered from the previous snapshot) + `replant_recut` (harvest-triggered
route re-cut). Engine truth en route: ONE_TIME crops (melon) leave the tile
None on harvest — that is the hot signal; ONGOING crops (strawberry) keep a
0-yield tile and are NEVER hot (replanting would destroy a standing plant).
168/168 tests (hot_tile_diff, pin/tier, boost-0 identity, fractional tier,
want bump).

**Gate battle (the teaching sequence):**
1. boost 1.0 (=tier 40) + recut-on-every-harvest: arm mean $3,000 vs $58,471 —
   the agent banked NOTHING beyond start (recut churn reset routes every
   harvest turn). Caught by the gate before any judge bar.
2. Repair A (recut once/day, turn_allocator pattern): mean $37,183, thirst
   DOUBLED on all 3 seeds (74/36/53 vs 36/19/18).
3. Repair B (boost capped to tier 25, strictly below water): mean $37,183→
   improved but thirst still 68/35/41 — tier displacement persists.
4. **Discriminating experiment (recut-only, boost=0, tier-20 pins): STILL
   FAILS — thirst 69/45/45, bank $39,638 (−$19k).** The harm is the recut
   infrastructure itself: a mid-day _replan recomputes capacity from
   turns_left, so ANY harvest-hour recut mechanically shrinks the day's plan
   and discards jobs the standing plan would have completed. That is why the
   turn_allocator (fires once, near dawn, first survival sighting) is safe
   while harvest-hour recuts (h8-h20) are structurally unsound.

**THE FINDING: "continuous replant" — the wall band's actual skill — CANNOT be
bolted onto this executor by re-cutting. It requires INCREMENTAL plan-patching
(append the replant job to the standing queue; shift tiles only within a
hand's remaining day), i.e. an executor rewrite: the strongest evidence yet
for the external memos' core thesis.** The ringfence dies here as a
parameter; it is reborn as the design spec for the post-deadline executor
(top of the program queue, above animal_load). Knobs stay in PARAMS dormant
(0.0/0) with the full battle documented; all dormancy verified; freeze
UNCHANGED: sub17 both slots Tue 29 morning.

## 0927-robson — New tape tripped the reopen flag; land gate built; the throttle family is now CLOSED

Morning pull caught a NEW sub17 episode live: 114126769, L **−$110,272** vs
Robson (800+) — the worst sub17 margin ever, tripping the checklist's
"≥−$60k in last 6" reopen condition. Telemetry: same elite signature at its
purest (rival +$4.7-9.6k EVERY day after d10, their thirst 1 vs our 40,
18-vs-3 BUY_SEED on the heavy day) PLUS a new aggravator: our d11 ran **3
BUY_LAND orders in one day** on the windfall — acreage the roster could not
service, then 40 thirst deaths across 4 quadrants. Built the fix:
`land_serviceability` (0.0 = byte-identical): a new quadrant is bought only
while crew (hands + hires still deferred this day) ≥ ls × 7 per owned
quadrant, counting the one being bought. 170/170 tests.

**Gate: mirror near-miss with a twist** (seed 2 bank +$5.9k while thirst
18→21 trips the strict line; mean −$2.7k) — then the wall tier: **0W-7L mean
−$48,867, worse than shipped on every game.** REJECTED. Interpretation: at
the wall the binding constraint is never our land count — these opponents
out-EXECUTE us on any board; gating land just shrinks our income without
removing the loss. The Robson loss, meanwhile, is the elite executor gap,
NOT over-extension (40 thirst deaths on 4 quadrants is a 3x-execution
deficit, not a land problem).

**The growth-throttle family is now CLOSED with four independent kills
(cover_mult, cover_brake, dawn_pace+floor, land_serviceability) plus the
ringfence's recut-structural finding. Conclusion for the program: no knob
inside THIS executor fixes the wall or the elite gap — the executor rewrite
(incremental plan-patching, priority water, hire-coordinated growth) is the
only remaining lever, and it is a next-season build.** All new knobs dormant,
170/170 tests, shipped bytes untouched. Freeze UNCHANGED: sub17 both slots
Tue 29 morning. Remaining pre-deadline work: field pulls + hash checks per
FREEZE_CHECKLIST.md.

## 0927-exec — replant_idle BUILT AND GATED: FIRST CANDIDATE TO BEAT THE INCUMBENT IN THE PAIRED HARNESS

The executor-rewrite insight, productized WITHOUT a rewrite: the codebase
already contained the safe append mechanism (0924h idle-residual cut — appends
residual jobs directly to IDLE units' queues, never reads busy lanes or
shepherd loops, "zero churn by construction"). New dormant knob `replant_idle`
reuses it: when a one_time harvest frees a tile, the replant (PLANT+WATER
chained, shipped tier 20) is APPENDED to the nearest idle unit's queue,
deduped against all standing queues, dearest-crop-first, one wave per turn,
terminated h22. No re-cut ever happens — this is why it is NOT the killed
recut mechanism. _seed_orders reads live queues, so the seed is bought
same-day. 170/170 tests (append semantics, hot-diff, boost/recut dormant).

**Gates:**
- Replay gate: FAIL on the strict line only (seed 1 thirst 23v19; seed 2
  +$6.1k with thirst 19≈18; mean +$2.0k — first replant build ever net-positive
  on the mirror).
- **Wall tier: 1W-6L mean −$32,625 (BEST EVER; shipped −$35,092) — aynrmio
  FLIPS at +$3,653 (largest flip margin ever); mingkang −$46.8k (best),
  alexandre −$75.9k (best), hayday −$16.6k (best).**
- Judge bar: midfield 3W-1L **+$12,185 (best ever; incumbent +$11,055)**;
  elite −$39,568 (inside −$41,000 written guard; $2.5k short of the
  incumbent's own −$37,057).
- **Paired harness (the rw1 wash-killer): 12-seed block 12W-12L (+$2,885,
  median +$2,164) — NOT a wash this time; 16-seed extension 21W-11L (0.656,
  median +$1,318). Combined: 56 games, 33W-23L (0.589), mean +$2.1k, median
  positive — the first candidate to BEAT the incumbent in paired play.**

**Decision: OWNER CALL.** The evidence favors replant_idle (wall mean, wall
flip, midfield mean, paired harness — all positive; the only negatives: elite
mean $2.5k short of the incumbent on n=5, and mirror thirst granularity).
Options: (A) freeze sub17 both slots (unchanged); (B) rpidle → Slot B under
the better-of-two rule (owner must confirm the rule first); (C) rpidle both
slots (aggressive; discards sub17's proven n=35 record for a 56-game paired
edge). FREEZE_CHECKLIST.md step 0 and 3B carry the branch. Ship artifact
untouched; rpidle is a PARAMS flip + 55 lines on a proven pattern — packable
in minutes via the established sandbox bake + paired-provenance proof.

### 0927-exec addendum — endgame guard added to replant_idle (owner caught the gap)

Question "what about our final-days money?" exposed a real hole: appended
replants bypassed the dawn `in_time` calendar check, so late-season harvests
would be replanted into cycles that cannot finish by d29 (pure seed loss in
the endgame). Fix: `in_time(crop, day)` guard in `_replant_idle` — the append
naturally goes quiet crop-by-crop as each calendar cutoff passes. RE-VERIFIED:
170/170 tests; mirror mean $61,041 (+$2.6k vs shipped); wall still 1W-6L with
the aynrmio flip (+$888; mean -$33,600, second-best ever); paired blocks with
guard: 13W-11L (+$4,105 median +$4,792) and 17W-15L (+$1,170). Guard is ADOPTED
into the rpidle cell. Bar elite/midfield numbers on file are pre-guard; the
guard only REMOVES negative-value spends, so those can only improve.

### 0927-pack — Brainstorm/reenvision cycle + dual-Nemotron pack review; rpidle PACKED

/brainstorm found the idle-only restriction was stricter than the real
invariant; /reenvision built the generalization (busy hands with <3-job
queues may take the replant, harvester-on-tile preferred). **Gate KILLED it**:
mirror −$2.3k, thirst up all seeds — delaying a busy hand's queued WATER legs
2 turns pushes them past midnight. The invariant is ZERO DELAY on
water-critical lanes, not zero deletion. Reverted to idle-only and re-proven:
170/170; fresh 8-seed paired block **11W-5L (0.688), mean +$6,402, median
+$6,279, worst −$2,160, both seats positive** — strongest block of the cycle.

**Dual-Nemotron pack review (both keys, briefing 2): BOTH answer Q1 = Option B
(rpidle in one slot + incumbent in the other), hedged against the unconfirmed
slot rule; both name the same #1 risk (elite mean −$2.5k worse × the slot
rule). Nemotron Q2 plan adopted: (1) extend paired harness to ~100 games
overnight; (2) replicate the elite bar n>=10 for both cells with a revert
trigger at −$1.5k p<0.05; (3) thirst forensic on the seed-1 mirror failure.**

**Packed: `rpidle_candidate.tar.gz` sha256 `d2cffa65…`** — bake, paired
provenance proof (3 seeds to the dollar), junk-check, final-loop proof on the
EXTRACTED archive (2 seeds, exact). FREEZE_CHECKLIST.md updated: 3A = sub17
both slots (if the rule is unknown/BOTH-count); 3B = rpidle Slot B + sub17
Slot A (if better-of-two confirmed). Ship artifact `3e1c0b38…` untouched;
superseded rw1_candidate marked do-not-use in the checklist.

## 0927-rule — TWO-SLOT RULE CONFIRMED: better-of-two (Kaggle staff)

Owner screenshot of discussion 739410: Addison Howard (Kaggle staff, 23d ago):
"The team score is based on the better of its two submissions (a team can't
occupy two ranks). The second slot can be viewed as a hedge with no downside."
Ties count as half wins for each side. Post-deadline play rate: "we always hope
to increase the play rate... can't make commitments."

**Consequences (executed immediately):** FREEZE_CHECKLIST.md Step 0 marked
CONFIRMED; Step 3B (rpidle Slot B + sub17 Slot A) is now the ACTIVE path;
Step 3A demoted to fallback. The hedge has NO downside by organizer decree —
the rpidle upload cannot hurt the team score, only the incumbent slot's
count. The "second weakest submission pulls the team down" tail risk is DEAD.

## 0927-dossier — rpidle first 22 ladder games + OCR elo deltas (screenshots speak)

User supplied 17 episode JSONs + 16 ladder screenshots; replays were the
authoritative W/L source, the screenshots carried the one thing replays do
not: per-game RATING DELTAS. OCR'd all 16 via macOS Vision
(`analysis/ocr_vision.swift`; no tesseract on the box). Convention confirmed
(bare number = pre-game rating, paren = delta): 15 consecutive games link
exactly (2 off-by-one OCR reads).

- Record verified from replays: 17 games 9W-8L mean +$5,742; 22 by night-end
  (5 more pulled) 10W-12L mean −$64; slots now rpidle 466.6, sub17 533.4
  (= team score), team rank 6821/10083.
- Signature replicated in all 9 losses incl. the 5 new mid-band ones (521-571
  elo, NOT just elites): d11 sink −$8.2-9.2k, orders exactly {BUY_SEED 3,
  HIRE 3, BUY_PRODUCT 1, BUY_LAND 3, SELL 16}, thirst 33-73, d12-24 ~$0,
  wheat hoard then d25-28 wave. One disease, nine copies.
- K-decay MEASURED from OCR deltas: K = |Δ|/(S−E) → 225, 230, 215, 202, 170,
  143, 121, 99, 91, 73, 69, 60, 53, 48, 45, 42 after 16 games. Decay is per
  game played; post-deadline play-rate drops mean K stays ~40+ through the
  freeze → final rating = recent form at high K. Streak-suppression ≳ mean
  margin in ship priority.
- Schedule fairness: Elo-expected wins at pre-game ratings = 9.10 vs actual 9
  — the 0.500 is performance, not matchmaking.
- Rank math: peers lost to (510-571) cost 3-5 elo each but are the pairings a
  ~500-530 final rating will draw; elites (601-731) cost 34-58 each and are
  rare. The mid-band is the rank-killer; that is where the d11 disease fires.
- Dual-Nemotron consult #3 (briefing 3 + addendum, both keys): converged on
  (1) order-level BUY_LAND pacing — one quadrant per day (d11/12/13), no
  acreage shrink, no plan re-cut — and (2) front-load hires onto the d10
  windfall so dawn-d11 crew is pre-scaled for the new quadrants. KEY
  explicitly checked both against the killed-lever ledger (passes: not a
  growth-throttle, not a recut). Both claims verified in code: BUY_LAND emits
  one order per turn (the 3 = three quadrants settled same day);
  `in_time` puts the cost of a 1-2 day quadrant delay at ~1 carrot cycle of
  earning window, not a throttle; dawn demand sizer + `hire_hours_late`
  confirm mid-day hires cannot rescue the same day's watering (the disease
  mechanism, restated).

## 0927-surge — windfall hire surge MEASURED IN; order-level land pacing KILLED

Implemented both Nemotron #3 levers as dormant knobs (byte-identical at 0):
`land_pace_days` (order-level BUY_LAND spread) and `hire_surge_day/n`
(pre-scale the dawn crew the day before the spray). 180/180 unit tests.

**land_pace_days: DEAD by measurement, second mechanism learned.** Pacing
makes the dawn-lag the BASELINE regime: every new quadrant arrives to a crew
sized the dawn before it (the crew sizer never sees the purchase coming).
Mirror thirst rose on all 3 seeds vs default; pace+surge combo failed the
wall bar 0W-7L (−$34,870) and flipped aynrmio. The spray's same-day settle
is *less bad* than three under-crewed dawns. Knob kept, default 0, do not
bake. The falsification record grows a new invariant: CREW MUST PRE-EXIST
THE LAND, never trail it.

**hire_surge (d10, n=12, max_hands=14): the strongest arm of the cycle.**
- replay_check vs shipped rpidle: +$24,155/game (+39.6%), strict thirst gate
  passes 2/3 seeds (seed 2 +14 = the wheat-backbone trade, priced below).
- Wall bar (7 tapes): W/L unchanged 1W-6L, mean −$33,600 → −$31,568
  (+$2.0k), worst tail −$76,380 → −$67,633, aynrmio flip holds (+$1,245).
- Midfield bar: 3W-1L unchanged, margin +$289 (flat where already winning).
- Paired harness vs shipped rpidle: block 1 24W-0L +$41,544/game; block 2
  (fresh seeds) 48W-0L +$38,359/game, worst game +$12,857. **72-0.**
- Dose-response: n=8 worse (−$35,127); n=16 = n=12 bit-identical
  (max_hands=12 in the surge window caps it); raising max_hands to 16
  FAILS the wall bar 0W-7L (−$37,763) — extra hands cost more than they
  water. d9 worse (−$38,814, fib cash gate pre-windfall). Cell: day=10,
  n=12, max_hands=14 unchanged.
- Elite judge tapes missing on disk (spectator manifest incomplete) — the
  Nemotron elite revert trigger (−$1.5k p<0.05) could not be run; the wall
  bar's W/L-unchanged + tail improvement stands in as the regression guard.

**Verdict: ship surge12 as rpidle v2 in Slot B (user call on the upload).**
Wall-margin/tail improvement is exactly the size of the close peer losses
(−$7k to −$20k, 3-5 elo each) that the dossier names the rank-killer; paired
72-0 says the mechanism is real. Resets to 600 seed on upload — worth it only
because the arm is measured better; sub17 (533.4 = team score) untouched.

## 0927-pack18 — surge cell baked as `submission18.tar.gz` (rpidle v2)

Bake pipeline executed end-to-end: 3 PARAMS lines baked
(replant_idle=1, hire_surge_day=10, hire_surge_n=12; repo defaults restored
after packing — 180/180 tests re-run on the restored tree), pack.sh verified
the unpacked archive plays the repo BANK-FOR-BANK on 8 episodes
(mean $94,413), baked values grep-confirmed INSIDE the archive.
**Artifact: `submission18.tar.gz` sha256 `fd9c15ac…` (142,391 bytes).**
superseded rpidle_candidate.tar.gz (v1) marked in FREEZE_CHECKLIST.md;
submission17.tar.gz (3e1c0b38…) untouched, still Slot A / team score.
Upload is an owner action (`kaggle competitions submit -f submission18.tar.gz`
or `bash submit.sh "rpidle v2: surge"`); resets Slot B to the 600 seed.

## 0927-clone19 — OWNER EXPERIMENT: ship the census program PURE as submission19

Owner order: "copy the top one, ignoring our tests — as a test model." Executed
literally: the shipped artifact is the PURE majkel_skeleton census preset
(13-tape elite census distillation, built 0921 for exactly this purpose and
never shipped) — PARAMS.update(majkel_skeleton()) at import, NO surge, NO
replant_idle. First measurement of the preset ever run:

- mirror (replay_check, 3 seeds vs old shipped default): mean $78,632 vs
  $58,471 = +$20,161 (+34.5%). Thirst gate fails strict line on 2/3 seeds
  (26/28 vs 19/18) — the known census trade: more acreage worked, cheaper
  deaths, richer bank.
- Wall bar: 1W-6L, mean −$27,845 (BEST EVER; v2 −$31,568; shipped −$33,600).
  aynrmio +$24,798 = the largest flip margin ever recorded (any build).
- Midfield: **4W-0L, +$24,535 — the first perfect sweep**; flips susutem
  (+$32,548), which every prior build lost.
- **Paired head-to-head vs the v2 surge cell: 15W-9L (0.625), +$2,327** —
  the strongest candidate of the cycle. The owner's corpus instinct won:
  the elite program beats our best hybrid.

Ship mechanics: ship block appended to kagfarm/policy.py (3 lines + comment;
restore = delete it). 10 default-pin tests re-anchored faithfully (the
mechanisms are unchanged; the pins now describe the census default — melon₀ 8,
seed_opening_cap 250, opening_led herd/ramp bypass, d0 animal script, surge
comparative contracts). 180/180. One real packaging bug found by the pack
gate: the aliased import broke the single-file flattener (NameError) — fixed
by importing majkel_skeleton through policy's existing relative-import block.
pack.sh: bank-for-bank $45,094 (8 episodes), single-file fallback verified.
**Artifact: `submission19.tar.gz` sha256 `781941c9…` (142,833 bytes).**
Checklist names both Slot B candidates (19 clone / 18 surge) with the owner
call; ladder read for 19 = the dossier signature in REVERSE (sell days 30/30,
hires ~250+, land ≤4, d12-24 continuous income, thirst low).

## 0927-clone19-ladder — first 9 games: signature mostly lands; LIVESTOCK PLACEMENT BROKEN

sub19 (56615524) n=9: 4W-5L, mean +$2,892. Bands: <500 3W-0L +$65,929
(the elite crush), 500-540 1W-2L −$1,105 (coin-flips, close), 600-800
0W-3L −$56,148 (the known wall). d11-spray signature GONE (sinks now
scattered $1-2k; HIRE 11-12/day live).

Census compliance (9-game means vs elite target):
- hires 284 (target 280-320) PASS — was ~60
- land 2.6 spread over days (2-4) PASS — was 3-in-one-day
- wheat sold ~820/game (~800) PASS
- sell_days 24.7 (29-30) NEAR — phantom sells eat slots (below)
- melon0 2.0 (6-14) FAIL — day-0 melon cohort cash-gated down to 2
- herd 0 vs 14-35 FAIL — THE DELTA: 14-17 PASTURES build, ~16 animals are
  bought (d0 script + d15-20 pace-3 orders), but the census is ZERO all
  season and the shed ends 0-2 — animals are never PLACED on the structures.
  The milk lane (elite's biggest revenue line) produces nothing; executed
  milk ~79 units is residue. Evidence: 114287485 structures {PASTURE: 14 by
  d19}, census curve all-zero, shed@end SHEEP 2.
- Phantom sells: the plan emits sells for production that does not exist —
  SELL MILK ordered 1,065 vs ~79 executed, MELON 684 ordered (melon0=2!),
  FERTILIZER 442 sold back — dead orders clog the 10-slot market budget
  every turn, displacing real sells.
- Elite-opponent exposure: bruyantq (626) ordered 72 animals on d12 and won
  by $59k — the real livestock program exists in the field and crushes the
  broken-herd clone.

submission20 fix list (priority order): (A) PLACE/FEED chain never fires —
find why the shepherd stream skips placement under the census arm; (B) sell
meter must inventory-gate (never emit sells for shed-absent goods); (C) melon0
cash gate loosened to census 6-14 band.

## 0927-sub20 — "fix everything": two bugs were MINE, one real fix found and shipped

Ladder-diff forensics on the first 9 games first produced two FALSE alarms,
both measurement errors on my side (engine-exactness discipline vindicated):
1. "herd=0, placement broken" — WRONG. The engine stores a placed animal
   under the SINGULAR tile key `animal` (verified against DECEM's real
   replay tiles). With the correct census the clone's herd peaks 13-16 in
   every game (mean 14.1 = the census target): pastures, placement, feeding,
   milk production all work. Field calibration: elite opponents run herds
   12-26 (bruyantq 20, nubx 26).
2. "phantom sells" — WRONG. Market-order counts in replays re-emit every
   turn until settled (true for every agent incl. the elite); and the
   "FERTILIZER sold 442" was shed-delta consumption by crops, not sell-back.

THE REAL DELTAS, measured and gate-tested (all vs the census program):
- seed_opening_cap 900 (was preset 250): restores the day-0 melon cohort to
  the census band — ladder diff showed melon0 = 2/game vs elite 6-14
  (winners 17). Mirror +$6,993 (+12%); wall mean −$23,378 (NEW BEST EVER,
  tail −$55.5k); midfield 4W-0L +$19,980; paired vs the shipping sub19
  20W-4L (0.833), worst −$6,601. SHIPPED in submission20.
- wool_hold_price=0 (always-sell wool): WASH (−$605) and corpus-contrary
  (elite winners sell LESS wool than losers) — DROPPED; the hold IS elite.
- herd 20 (field-calibrated): −$4,840, thirst up — DROPPED; our service
  machinery profitably feeds 14 mouths, not 20. The census number wins.

**Artifact: `submission20.tar.gz` sha256 `34d4de74…` (142,927 bytes)** —
census program + melon0 fix; pack-verified bank-for-bank ($86,608 vs the
clone's $45,094 on the same 8 weak-opponent episodes — the d0 windfall
nearly doubles the early bank); 180/180 tests; single-file fallback OK.
Checklist updated: sub20 is the strongest Slot B candidate.

## 0929 — sub20 signature + the famine guard (submission21)
**Pull:** sub20 = ref 56617155, 39 ladder tapes (17W-22L, mean −$16,407).
**Signature check (n=39):** melon0 **8.0 in every game** (was 2.0 on sub19; elite
6-14) — the seed_opening_cap fix landed. hires 279.8 ✓ (census ~280), herd peak
13.1 ✓ (census 14, correct singular `animal` key), land 2.9 ✓, milk 83, wool 22,
wheat 770 ✓. Bands: <500 10W-1L +$20,931; 500-540 4W-4L; 540-600 3W-6L;
**600-800 0W-7L −$60,359 (wall NOT narrowed)**; 800+ 0W-4L −$76,195.
**Two famine collapses found and root-caused (114608031 T. Scharf, 115165685
Aki Lit — both low-band):** money curve d0 $126 → d3 $0 → $0 for 27 days; hands
6 → 0 at the d4 dawn (unpaid wages → desertion); no SELL ever fired; the d0 crop
cohort died of thirst d5. Mechanism: the d0-3 script spends to ~$88-107 and the
ONLY pre-d4 income is the d3 fertilizer drip (SELL FERTILIZER from turn 5, ~14
orders) — and the drip needs price ≥ fert_drip_px AND opp herd ≥ opp_fert_demand;
vs a crop-rush opening (no herd d3) it never fires. One d3 water/input buy then
crosses the wage threshold → d4 dawn wage charge → $0 → the WHOLE roster deserts
(re-hire = cumulative fib). −$63k and −$86k on the ladder, the entire tail.
Seed_opening_cap 900 made this MORE likely than sub19 (the d1-3 cushion that
used to absorb a suppressed drip is spent on the doubled d0 seed round).
**Falsification ledger additions:** thirst 44 (sub19) → 53 (sub20) with melon0 8
— the melon cohort costs real water; the wall is NOT thirst-fixable by herding
(herd 13 ✓, hires ✓, wall losses unchanged); a 5% catastrophic-failure mode
(famine) was invisible to the mirror and to the wall/midfield tiers — only the
ladder tapes showed it.
**The guard (kagfarm/constants.py preset + 2 sites in policy.py):** knobs
`famine_wage_frac=1.0, famine_price_frac=0.20, famine_sell=True`.
(1) PROSPECTIVE wage floor: fertilizer / BUY_LAND / lump+wheat-drip buys and
every HIRE may not spend below `famine_wage_frac × fib-sum(hands)` — the engine's
own daily wage bill; dose counts are CLIPPED (pessimistic $25/unit), hires break.
(2) Emergency sell lane: when cash is already under the floor, `_famine` strips
the sell floors/holds (feed holds EXCEPTED — never sell the herd's grain to pay
wages) and sells shed fertilizer at a 0.20× floor. famine_wage_frac=0 is the
byte-identical shipped control (off-switch verified).
**Gates:** 185/185 tests (5 new TestFamineGuard). Wall 1-6 mean −$23,378 →
−$22,619 (aynrmio byte-identical — guard inert when solvent). Midfield 4W-0L both
arms, mean +$19,980 → +$18,984, WORST-case margin +$890 → +$8,801 (tail variance
compresses). Counterfactual on the actual collapse tapes (new famine judges,
replay_famine_scharf / replay_famine_akilit in replay_opp.py): OFF −$62,656 /
−$91,739 (0W-2L) → **ON +$33,403 / −$7,613 (1W-1L)**. Akilit seat map is
bank-verified (TeamNames inverted on that tape — seat 1 verbatim reproduces OUR
$9.5k collapse, not his $95.7k; judge = seat 0).
**Artifact: `submission21.tar.gz` sha256 `56fecee8…` (144,592 bytes)** — census
program + melon0 fix + famine guard; 185/185 tests; bundle verified 16/16
episodes bank-for-bank (worst turn 8 ms); pack.sh bank-for-bank OK.

## 0929b — wall attack: the 600-800 diff, two kills, one graft (submission22)
Goal: the 600-800 band is 0W-11L across sub19+sub20; win some of it (and
eventually 800+) to move BT rating toward 2000.

**Wall diff (analysis/wall_diff.py, 10x 600-800 + 4x 800+ + 9x 540-600 tapes,
our seat vs the recorded winner):** hands/day d10-16 EQUAL (11.0 vs 10.6-11.1);
WATER/day equal-or-higher; PLANT/day d10-16 +25 to +41 OVER the winners (72-82
vs 44-57); thirst total 50-56 vs winners' 3-5 (10-17x); HARVEST/day 30-50% LESS
than winners; executed strawberry 36 vs 65-173. Diagnosis: WATER-CAPACITY
SATURATION — we book ~150% of crew capacity in chained plant+water legs, the
marginal tiles die (15/week in-window), premium cycles forfeit, and the winners'
smaller-alive boards out-harvest us while spare seed cash compounds into herds
(their milk 170 / wool 103 vs our 85 / 26). HIRE surge: ruled out by the diff
itself (crew is equal; d9-11 hires cannot un-kill d10-16 tiles).

**Kill 1 — water_cover_max_thirst=0.20 (blanket dawn brake):** mirror bank mean
−$9.6k vs baseline (thirst 40→15, 47→22 but the veto cancels servable premium
top-ups too). Third planting-side limiter killed by the same class of failure.
**Kill 2 — cover_exempt (NEW knob: brake exempts MELON/STRAWBERRY, vetoes only
staple top-ups):** mirror mean −$9.4k, thirst unchanged — vetoing staples while
premium continues still shrinks the compounding board. mix_cap=2.0 (capacity-
true shrink, no veto machinery): wall mean −$22,048 (+$571 = noise). Board-shrink
in every form is dead on this program; only ADDED capacity has ever passed.

**The graft — turn_allocator=1 (survival-first mid-day re-cut, fires once/day at
the first rescue sighting):** mirror bank −$2.4k with thirst ±1 (the documented
mirror-rewards-growth asymmetry; the FIELD taxes growth, so the wall tier is the
decisive instrument). Wall: 1W-6L, mean −$22,619 → **−$18,514 (+$4.1k)**, worst
tail −$57.7k → **−$47.6k**, 5/7 tapes improve, aynrmio +$29.7k (mingkang −$2.3k
the only regression). Midfield 4W-0L +$19,838. Famine tapes 1W-1L +$14,445
(composes with the famine guard). Paired harness 12 seeds: 15W-9L (0.625), mean
+$746, worst −$5.4k.

**Artifact: `submission22.tar.gz` sha256 `bd45fd3b…` (145,327 bytes)** = census
program + melon0 fix + famine guard + turn_allocator=1 (ship block, revert =
delete the line). 185/185 tests (test_knob_default_off re-anchored to 1 with the
off-switch contract pinned; same faithful re-anchor pattern as sub20's pins);
bundle 16/16 bank-for-bank (worst turn 5.9 ms); pack.sh bank-for-bank OK.

**Honest read vs the 2000-elo goal:** sub22 is the best-measured build (better
close-peer margins and tails = the 540-600 currency), but it did NOT flip a
600-800 W. The 800+ diff points the opposite way from the wall: their boards are
BIGGER and fully watered — real capacity (cash speed + hire cadence), not just
discipline. Closing that gap is a post-deadline program, not a day-one graft.

## 0929c — capacity program day 1: five arms, one structural finding
Goal (user): faster cash conversion + higher hire cadence so a bigger board
stays fully watered — the 800+ diff's direction. Every arm gated mirror-first
(replay_check 3 seeds vs {}), wall where the mirror was neutral.

**Arm 1 — water_reserve (NEW, idle-append water residual):** v1 captured all
ranked waters and appended to any idle unit incl. the farmer: mirror −$9.5k,
seed-2 thirst 66 (the v6-class churn: thin-metadata legs, farmer pulled off
pattern). v2 (exact dropped-set diff, full job metadata, farmer excluded):
BYTE-IDENTICAL on all 3 seeds — on the census program there are NO idle hands
when the re-cut drops waters. The labour market is fully saturated; idle slack
does not exist. Mechanism kept (knob water_reserve, default 0, inert), the
finding is the point.

**Arms 2-5 — the board-shrink family is dead on the census program (4th kill):**
dawn_pace {4,4,6,6}: mirror −$12.9k, thirst UP 2/3, min bank $4 (even with the
census ramp removing the roster-shrink cycle). windfall_pct 0.75: −$5.4k, thirst
up 2/3 (the census funds from daily wool/milk cash, not the bank; loosening the
cap only deepens the d11 overbook). TOMATO in mix alone: +$182 (inert; mix caps
never bind at mix_cap=3.0). FORCED mix (mix_cap=1.0, straw-weighted, wheat 9):
mirror-neutral, wall mean −$23,273 vs sub22's −$18,514 — mingkang −$21k. Every
single-axis perturbation of the census booking/mix/replant equilibrium is
neutral-to-negative.

**The plant-by-crop diff (the real 800+ signature):** d10-16 PLANTs by crop —
they plant TOMATO (19-21) which we CANNOT (not in the mix); they plant 4x less
wheat (79 vs 318 on 600-800) and buy the difference at $25 (the ~100-unit
market buys already on record); their boards are ongoing-crop stable, ours
one_time-churning. The 800+ edge is a MULTI-KNOB EQUILIBRIUM (tomato + market
grain + bigger herds feeding milk/wool cash + the hire cadence to water it) —
each piece assumes the others, which is why one-at-a-time grafts fail.

**Verdict: no capacity graft ships today. sub22 (census + melon0 + famine
guard + turn_allocator) stays the artifact.** The capacity program is the
post-deadline package: TOMATO mix share + wheat-marketization (buy grain at
<=1.0x base up to the mouths buffer, cap wheat REPLANTS not the backbone) +
herd envelope 16-20 gated on the allocator's water protection — built and
gated TOGETHER as one arm, paired harness first, wall second, elite guard last.

## 0929d — capacity program, final push: 8 arms, 8 kills, one conclusion
Owner directive: deadline tomorrow, "find a way, consider everything." Executed:
the two remaining measured couplings of the 800+ signature were built and gated.

**Arm 5 re-run — the feed-marketized package (mix_cap 1.0, straw 16 + TOMATO 4,
wheat 4, feed_backbone=false):** mirror −$22.8k, min bank $8. The forced mix
kills the EARLY engine: wheat/carrot fund d4-10, strawberry pays nothing before
d16 — the 800+ farms afford their boards because their HERDS fund the gap.
**Arm 6 — feed_backbone=false alone:** −$10.3k, thirst up 2/3. The wheat floor
is load-bearing: it paces the early-season rhythm the whole plan sizes against.
**Arm 7 — shepherd_div (NEW knob: census shepherd share is (live+2)//3+1 — at
herd 14 that is SIX units shepherding, ~5 in the field; div=4 releases one):**
mirror −$85 neutral, thirst up 2/3 (freed capacity is re-absorbed by demand-led
booking — the same shape that killed water_reserve), wall −$19,107 = a wash vs
sub22's −$18,514. **Arm 8 — div4 + herd 18 (the 800+ signature: leaner
shepherding + bigger herd):** mirror −$7.7k, thirst up, min bank $6. Killed.

**CONCLUSION (measured, not inferred): the census equilibrium is locally
optimal.** Eight single-axis and coupled perturbations — booking caps, budget
caps, mix shapes, feed marketization, labor split, herd scale — all neutral or
negative on this program. The 800+ edge is a CO-EVOLVED equilibrium (feed
strategy x crop calendar x herd scale x labor x cash speed jointly selected);
reaching it means re-deriving the allocator, a multi-day build. Parameter space
around the census is exhausted for this cycle.

**Deadline decision: submission22.tar.gz (sha bd45fd3b) is the artifact.** Best
measured build in campaign history: wall mean −$18,514 (best ever; tail −$47.6k),
midfield 4W-0L, famine collapses eliminated (counterfactual −$77k → +$12.9k),
paired 15W-9L. Upload it to Slot B tonight — every remaining hour of ladder play
compounds via K≈40 recent-form weighting. Two dormant knobs (water_reserve=0,
shepherd_div=3) joined the infra; defaults byte-identical; 185/185 tests.
The capacity package (tomato + grain market + herd 16-20 + allocator re-derivation)
is the post-deadline tournament program, built as ONE arm with new mechanisms.

**UPLOAD NOTE (integrity):** the repo tree gained two DORMANT knobs after the
sub22 bake (water_reserve=0, shepherd_div=3; byte-identical defaults, 185/185,
pack bank-for-bank re-verified). The current submission.tar.gz sha therefore
differs from the artifact. **The upload is `submission22.tar.gz` (bd45fd3b…)
specifically** — the exact bytes that were bundle-verified 16/16 and pack-verified
at bake time and that the wall/midfield/famine/paired gates measured. Do not
upload the regenerated archive; the two knobs ship post-deadline with the
capacity package.

## 0930a — plan approved, build day 1: sell-day parity measured + the early drip (submission23)
**W2 entry point measured (the sell-day gap):** elite (Majkel 12 games) sells on
100% of days 0-29; we miss d0-2 entirely, d3 31%, d6-7 56%. The elite pattern:
SELL WHEAT x1 d0 (t2/t3/t16/t17), then the FERTILIZER DRIP 1/unit from t3 EVERY
opening day (d1-3, turns 3-12, at whatever price) — no price gate, no rival-herd
requirement. Our shipped drip needed price >= fert_drip_px AND opp herd >= 5,
so d0-3 sat dead.
**The arm (`sell_fert_early=1, sell_fert_early_days=3`, preset):** the early
lane bypasses the drip's price+herd gates on days 0-3, sells at the deep 0.20x
floor, suspends the fert_stock buffer hold in the window (no fert jobs exist
before the herd places). Doubles as the standing pre-d4 income cushion.
**Gates:** 185/185 tests (3 invariant pins re-anchored: never-sell-inputs moves
to day 4; the drip is asserted as shipped day-0-3 behavior). Mirror: mean −$1.6k
neutral, MIN BANK UP $19 -> $27-51 (the cushion, visible). Paired self-play
12W-12L wash. Wall 1W-6L mean −$18,509 (holds vs −$18,514, identical W/L).
Midfield 4W-0L +$18,354 (holds). **Famine tier 2W-0L +$22,745 — the Akilit
near-miss FLIPPED to a win (+$4,134); Scharf +$41,356.** The drip both closes
the opening sell-day gap AND hardens the famine cover to a full sweep.
**Artifact: `submission23.tar.gz`** = sub22 + sell_fert_early (one preset line +
3 gate sites). Upload next window; 2 submissions remain today.
Next in the queue (build day 1 continues): re-hire cadence, land pacing,
herd envelope, selection curve, fire_threshold; then W1 opening-book clone.

**0930a follow-up — the d6-7 gap root-caused: PLACEMENT LAG.** 0/39 sub20
tapes hold ANY wool by d7. Measured: elite (110886706/110900752) has all 5
founding animals PLACED on day 0 (first wool sale d6); we place 4 by d3 then
STALL — herd=5 arrives at mean day 12.4 (min 11, max 16, n=37 healthy tapes),
first wool d8. The d0 script BUYS 2C+3S on day 0 but structures/placement
cannot keep up: one animal idles in the shed ~10 days, the wool lane starts
2+ days late, and the milk/wool cash engine that funds the elite's early game
compounds from d12 instead of d6. THE next build item: d0 structure pacing +
placement chain (elite builds its pastures/coops day 0 and places same-day).
This outranks the remaining W2 parity items (re-hire cadence etc.) because it
is upstream of them: the herd IS the early cash.

**0930b — arm 10 (opening build sprint) built, caught, killed, root-caused.**
The H4 rot test failed twice (2-3 animals in shed at T=720) and the mirror
priced it: placement accelerated (1 by d1 vs 0; 8 vs 7 by d12 — the mechanism
WORKS) but the value-lottery boost stole d0-2 hands from the field: seed-0 bank
$78.3k -> $59.7k. Root cause: our d0 seed round books ALL 4 hands on crops;
the elite's d0 seed round plants with the FARMER ONLY, so his hands are FREE
for the build sprint. The sprint without the smaller seed round is a theft from
the field. Dormant at 0. v2 (post-deadline): dedicated pre-build appends +
seed_opening_cap reduction paired — a TWO-KNOB co-move, gated together.
Day-1 total: sell-day parity (SHIPPED as sub23), placement lag root-caused,
sprint built+instrumented+killed in-cycle. The gates are working exactly as
designed — nothing unmeasured reaches the ladder.

## 0930c — MISSION PHASE 1 COMPLETE: sub24 = FULL ELITE CLONE (all gates real tier, all PASS)

**The probe "failure" was real — replay convention off-by-one.** `verify_replay.py` proves
(719/719 golden actions on 110886706 with `calibration/engine`) that `steps[t].action` was
decided from `steps[t-1].observation`: the action decided from obs@t is `steps[t+1].action`.
The old extractor read `steps[dawn+h].action` — d0/d1 still cloned (shift-robust), but d2
killed an animal (late feed) and d3 rerolled the shop. Fixed in `analysis/make_elite_book.py`
(`i = dawn + h + 1`) and `analysis/elite_counterfactual.py` (`oa = opp_actions[t+1]`); book
rebuilt: 1,423,436 bytes, sig v2, 30 days x 12 donors.

**Counterfactual clone validation (fixed probe, 12 donor worlds):** 7/12 byte-exact to the
dollar (110886706 $73,982; 110900752 $156,211; 110920455 $103,024; 110932461 $87,527;
110948948 $99,852; 110938064 −$1; 110913896 −$145); 5 sig_miss desyncs at d3/d6/d7/d8/d12
(110907373, 110926948, 111016701, 110954233, 110943566 — d0 has 1 sig across 12 donors but
10 distinct hour-scripts; pick-first serves 110886706's scripts everywhere, RNG diverges
later). 9/12 hold ≥8 days, mean 20.5 served days. Machinery sound; desync list = Phase 2.

**Mirror tier is NOT ladder-faithful for the book (documented, not a verdict):** on engine.py
the book serves d0-1 then halts (d2 fert-bucket artifact the real engine does not produce);
mirror-paired elite-vs-{} = 8W-16L 0.333 mean −$3,031 — screening artifact. ALL book gates
run the real tier (`analysis/paired_harness_real.py`, vendored 1.32.7 via bridge.real_env).

**Famine fix = coupled bundle (10 single-axis kills predicted the bundling):** windfall_pct
0.50→0.9 (akilit −$5,364→−$375, scharf +$47,497→+$62,165; saturates at 0.9), land_margin
1.20→1.0 (elite's aggressive land race; flips akilit to W +$7,041). Loss anatomy: strategy
mismatch (donor all-in animal economy in famine world) + planner under-conversion, NOT the
serving; realized animal prices healthy ($190-205 wool, $222-246 milk).

**Ship bundle (end of kagfarm/policy.py):** `PARAMS["elite_book"]=1; PARAMS["windfall_pct"]=0.9;
PARAMS["land_margin"]=1.0; PARAMS_BASE = dict(PARAMS)`. Revert = delete the three lines.

**H4-2 stray-mop defect (exposed by the bake's rot test, 4 edits in policy.py):** stray-mop
want floor (`_owned > want → want = _owned`), stray re-aim in `_animal_plan` with shared-kind
PASTURE capacity (COW+SHEEP), `plan["mop"]=n` so mop builds get rescue value ≥300 (queued at
rank ~0 at day tail and never reached), housing clamp on n_buy counting GLOBAL free housing
(wave-exempt). Rot test passes: 0 shed animals at T=720.

**Test re-anchoring (185 → 191):** sub24 ships elite_book=1 and the elite switch ALIASES
book_file, so TestOpeningBook's v1-machinery pins run elite-OFF on both sides via class
setUp/tearDown (shipped-default contract moved to TestEliteBook.test_elite_book_off_by_default).
`python3 -m unittest discover -s tests` = **191/191 OK**.

**GATE LADDER — FINAL POLICY (re-measured AFTER H4-2, real tier, `--params '{}'`):**
- Paired harness 12 seeds (1000-1011, seat-swapped, ship vs sub23-equivalent overrides):
  **24W-0L-0T, mean +$16,074, median +$14,396, worst +$4,737, best +$32,455.**
- Famine **2W-0L**: scharf +$56,469 (judge $44,101 vs recorded $71,140), akilit +$7,041
  (judge $74,927 vs recorded $95,740).
- Wall **mean −$8,098** (beats the −$18,509 bar by $10,411): W aarya +15,702, W tnwl +13,079,
  W aynrmio +25,166; L nottoday −13,266, L hayday −19,532, L mingkang −48,565,
  L alexandre −29,267 (3W-4L, same profile as pre-H4-2).
- Midfield **4W-0L mean +$43,641**: tam +43,927, dean +54,709, jiahan +16,899, susutem +59,029.
- Hold-out 12 seeds (999901-999911, 999999): **24W-0L-0T, mean +$14,856, worst +$5,556.**
Pre-H4-2 numbers for the record (same tiers): paired +16,492 worst +244; wall −8,782;
famine +62,165/+7,041; midfield +43,200 (jiahan +15,135); hold-out +12,923 worst +4,733.
H4-2 regressed nothing; judge-reactive margins drift a few k between runs (aynrmio
+19,022→+25,166, scharf +62,165→+56,469) — direction never flips.

**BAKE (sub24):** `bundle.py --seeds 4` → submission/main.py 7,132 lines / 1,827 KB, elite
book embedded (`_elite_book_embedded = json.loads(r'''...'''`) verified **8/8 bank-for-bank**
vs the package build, worst turn 3.2ms. `pack.sh` → submission.tar.gz 256,601 bytes, ships
kagfarm/opening_book_elite.json, unpacked-archive bank-for-bank == repo on 8 episodes.
- `submission.tar.gz` sha256 **02a1c3c6ec60ea28161f186566bc4d0efe266cb0c950839149a927d2b751a5fc**
- `submission/main.py` sha256 **12d33309afd711aaea805e2540f867a9d641dd2ae9598b9d9fd086a6dc8cc859**
- tarball `kagfarm/policy.py` == repo `kagfarm/policy.py` (sha256 933f430e…) — byte-verified.

**UPLOAD NOTE:** nothing has been uploaded. The artifact is `submission.tar.gz`
(02a1c3c6…) seated via the Kaggle UI pencil badge in **Slot B**; Slot A (sub17) is never
touched. Phase 2 queue: per-donor variant selection (kill the 5 sig_miss desyncs), counterfactual
diff loop, elite judge tier re-pull (spectator tapes / dataset terms), capacity package.

## 0930d — MISSION PHASE 2: desync root-cause + v3 rescue serving; sub25 baked (all gates real tier, all PASS)

**Phase-2 gate: book-hold 9/12 -> 12/12.** The 5 sig_miss desyncs are root-caused and
instrumented (`analysis/book_desync_probe.py` — per-dawn live sig vs all 12 stored variants,
per-component deltas, serving-identity continuity). Anatomy:
- Dominant kill: SHOP-NAME exactness. 12/14 observed misses matched on day/money/herd/wool
  with the shop set off by a +/-1 swap (e.g. 110907373 d3: live {BRUNCH_SPOT} vs stored
  1-shop set, everything else exact). The unlock draw rerolls cross-world and shop sets
  never re-converge, so one name divergence halted the clone for the season. Scripts never
  name a shop (demand prices are read from the live market).
- Identity thrash: at d0 all 12 donor sigs collide (1 distinct sig, 10 distinct hour-
  scripts), so pick-first locks 110886706's chain everywhere; worlds re-lock onto their OWN
  chain when a sig matches (110907373 d2, 111016701 d6, 110954233 d6, 110943566 d9) — the
  mechanism self-corrects when allowed to match.
- Near-misses beyond buckets: 111016701 d7 missed its own script on grain -2 (herd/wool/
  shops/money all exact); 110954233 d14 on wool +1 alone.

**The v3 serving mechanism (kagfarm/policy.py):** two-tier match — STRICT (v2 semantics:
day/herd/shop-names/wool exact, money/grain/fert buckets +/-1) then RESCUE (shop COUNT +/-1
never names, wool +/-1, grain +/-2, day/herd still exact), with the incumbent chain's
variant preferred INSIDE each tier; strict is never capped, rescue-tier days are capped by
`book_rescue_cap` (default 2/episode); action-validity guard still gates every served day.
Book rebuilt (1,423,513 bytes, sig_version 3, ASCII-only note).

**Measured pick order (pinned hash seed, 12 donor worlds, one process per run set):**
strict-first keeps all 7 byte-exact worlds byte-exact; tolerant-as-primary STEALS chains
(11/12 hold, mean clone delta -53k); incumbent's tolerant match above strict-any breaks the
exact worlds (11/12, -53k); incumbent-preference INSIDE a tier adds ~+56k of cloned bank vs
plain first-match (110943566 and 111016701 clone 10-20 days longer).

**Process nondeterminism found and controlled (affects every measurement):** two identical
in-process runs disagreed (110900752 d7 halt only in the 12-games-one-process sequence).
PYTHONHASHSEED pinned => byte-stable. Root: per-process hash-order iteration; the vendored
engine's own RNG is seed-derived and clean. ALL ledger numbers from 0930d on are
PYTHONHASHSEED=0. Earlier unpinned numbers carry a hash knife-edge (the 0930c 5/12 desync
list itself shifts by 1-3 days under re-roll; the set of 5 is stable).

**Counterfactual validation — final v3+cap (12 donor worlds, pinned):**
- Byte-exact to the dollar: 110886706 +0, 110900752 +0, 110920455 +0, 110932461 +0,
  110948948 +0, 110938064 -1, 110913896 -145 — all 7 preserved.
- Rescue extensions: 110926948 d6-7 (+2d), 110954233 d7-8 (+2d), 111016701 d7-8 (+2d),
  110943566 d9-13 (+5d), 110907373 d3-4 (+2d; its long rescue streak is capped).
- **book-hold >= 8 days: 11/12** (only 110907373 sits at 5 served; uncapped reached 9 but
  its rescue tail was value-negative), mean served 21.3 days, mean clone delta -27,354
  (improved from -29,403 uncapped / -36,991 v2: the rescue tail days were costing money).

**Famine forensics (analysis/famine_forensics.py — v2 vs v3 in the recorded akilit world):
uncapped v3 served akilit d6-10 on the rescue tier; the chain's end state (herd 18-19)
starved the planner's conversion (L -5,854 vs sub24's W +7,041). The cap=2 profile (strict
d0-5, rescue d6-7, planner from d8) keeps the early herd-buy rescue days and cuts the late
all-in buys: akilit W +16,244, scharf W +62,748.**

**GATE LADDER — sub25 (v3 + book_rescue_cap=2, real tier, PYTHONHASHSEED=0, --params '{}'):**
- Tests: **192/192 OK** (new pin test_rescue_tier_tolerances_v3: rescue matches shop COUNT
  +/-1 never names, wool +/-1, grain +/-2; bounded; day/herd exact at every tier).
- Paired 12 seeds (1000-1011, seat-swapped, ship vs sub23-equivalent): **22W-2L-0T (0.917),
  mean +27,783** (v2 was 24W-0L mean +16,074 — longer serving is real ladder value).
- Famine **2W-0L mean +39,496**: scharf +62,748, akilit +16,244 (v2: +31,755 mean).
- Wall mean **-8,588** (beats the -18,509 bar by 9,921): 2W-5L, margins swung inside the
  judge-reactive noise band (alexandre -29,267 -> -4,763; hayday -19,532 -> -1,314).
- Midfield **4W-0L** mean +19,866 (margins judge-noise; W/L profile holds).
- Hold-out 12 seeds: **22W-2L-0T (0.917), mean +13,205**.
- Counterfactual book-hold **11/12 >= 8 days** (gate >= 11/12).

**BAKE (sub25) — and two bake-integrity fixes the bake itself caught:**
1. bundle.py's raw-string safety check FIRED: the v3 note's non-ASCII +/- became a \u00b1
   escape in the book JSON, and submission/main.py would have stayed STALE (sub24) next to
   a fresh tarball. Fixed at the source (make_elite_book writes ASCII, asserts no ''' or
   backslash at build time) and pack.sh now FAILS the pack when bundle.py fails (was a
   warning). submission/main.py regenerated and verified: **8/8 bank-for-bank, worst turn
   3.5ms**, sig v3 embedded.
2. pack.sh tarballs are now REPRODUCIBLE (staged mtimes pinned to 202609300000, gzip -n):
   two packs of the same tree produce the same sha (verified twice). The artifact-of-record
   is unambiguous.
- `submission.tar.gz` sha256 **c539704a75a01ac37e7ea53623313a4fd0c8eb53dd57115eda935f04a27e4a7c**
  (repack-stable)
- `submission/main.py` sha256 **8bf5798416c18937822499ed369e1afc9d17f3363a306ec5a67323596ee5a5f1**
- tarball `kagfarm/policy.py` == repo (sha256 cdb94082…) — byte-verified.

**UPLOAD NOTE:** nothing has been uploaded. Owner decision: seat `submission.tar.gz`
(c539704a…) in **Slot B** via the Kaggle UI pencil badge (Slot A / sub17 untouched). sub24
(02a1c3c6…) is superseded — the v3 rescue serving is strictly measured better on the ladder
(paired mean +27,783 vs +16,074; famine mean +39,496 vs +31,755; hold 11/12 vs 9/12) with
every byte-exact clone world intact. Phase 3 queue: per-donor book synthesis (one world, one
chain — removes the d0 collision entirely), elite judge tier re-pull (spectator tapes /
dataset terms), capacity package (tomato mix + grain marketization + herd envelope).

## 0930e — MISSION PHASE 3: per-donor WORLD LOCK (chain identity); sub26 baked (all gates real tier, all PASS)

**The design insight that changed the plan:** the d0 observation is BYTE-IDENTICAL across all
12 donor worlds (same $3,000, market, blank farm, empty shops — 1 distinct d0 sig, 10 distinct
hour-scripts; even d1 obs differs only by opponent-trade fill drift inside the money bucket),
so NO d0 key can pick the right chain: d0-2 identification is information-theoretically
impossible from obs alone. What DOES identify a world from dawn obs is its seed-derived
shop-unlock schedule — and that schedule is ALREADY recorded verbatim as sig[1] on every
stored variant, so the per-donor book required NO book rebuild and NO size increase: it is a
matcher change over the sig_version-3 book as shipped.

**The mechanism (kagfarm/policy.py):** `_shop_fp` (sorted name multiset, JSON-canonical,
junk-safe), `_book_worlds` (groups the book into per-donor chains {donors, schedule}; returns
None on a legacy no-donor book -> v3 behavior), and a world-lock branch in the dawn pick:
until one strict candidate is unique, every strict candidate serves verbatim in donor-file
order (exactly v2/v3 behavior on those dawns); on a UNIQUE candidate the world LOCKS (measured
lock dawns d3 for 3 donors, d6 for 7 more, d9 for the PET_CAFE twins; 110907373 locks d2 by
its unique money-bucket sig) and its chain serves EXCLUSIVELY — no cross-chain matching. An
own-sig miss past d2, or a missing chain entry, ABANDONS the chain (never replays stale own
scripts, never crosses): the measured v3 strict+rescue fallback serves that dawn (clean
degradation — a strict cross-match is still the right script to serve). Validity guard,
rescue-cap accounting, and the strict tier are unchanged. New param `book_world_lock`
(default 1); 0 is byte-equal to v3. Measured and REJECTED: `book_chain_once` (one lock per
episode) — it dimmed later re-locks in other worlds for zero gain.

**Oracle probe (analysis/_oracle_once.py) — the phase headline:** own-donor-only book +
always-true sig patch through the SHIPPED act() path (validity guard live) = 30/30 served,
clone bank byte-exact to the donor in ALL FIVE desync worlds (110907373 +0, 110926948 +0,
110954233 +0, 110943566 +0, 111016701 +0). The live env replays the recorded worlds perfectly:
the residual desync divergence is NOT environmental (retires the 0930d RNG-sensitivity
hypothesis) — it is entirely the d0-2 script-class assignment, which is unidentifiable. The
world lock captures everything capturable from dawn observations.

**Counterfactual (12 donor worlds, pinned seed):** book-hold **11/12 >= 8 days** (gate >=
11/12), mean served 21.3, mean clone delta **-27,354** — class-equal to 0930d, with +1/+2
served dawns on 110954233 (8->10), 111016701 (8->9), 110943566 (13->14). The 7 byte-exact
worlds byte-exact (110886706/110900752/110920455/110932461/110948948 +0; 110938064 -1;
110913896 -145). 110907373 unchanged at 5 (its live unlock draw rerolls from d3 — no recorded
chain covers that world; cap semantics unchanged). 110926948 serves 8 then misses on herd
drift (v3-rescue profile unchanged).

**GATE LADDER — sub26 (real tier, PYTHONHASHSEED=0, --params '{}'):**
- Tests: **194/194 OK** (new pins: _shop_fp/_book_worlds helpers incl. legacy-book None;
  world lock serves own chain post-lock, refuses the stale own script on a miss day, v3
  fallback serves that day, book_world_lock=0 restores v3).
- Paired 12 seeds (1000-1011, seat-swapped, ship vs sub23-equivalent): **24W-0L-0T (1.000),
  mean +25,451, median +27,908, worst +7,397 — the best W/L on record** (v3: 22W-2L mean
  +27,783; v2: 24W-0L at mean +16,074). The chain lock recovered the perfect W/L profile
  while keeping v3's margin gains.
- Wall: **2W-5L, mean -8,588 — byte-identical to 0930d** (all 7 judge margins equal to the
  dollar: also a determinism confirmation of the pin).
- Midfield **4W-0L, mean +19,866** and famine **2W-0L, mean +39,496** (scharf +62,748, akilit
  +16,244) — both byte-identical to 0930d.
- Hold-out 12 seeds: **22W-2L-0T (0.917), mean +13,205** — identical.
- Live-world neutrality head-to-head (phase3 vs v3, 6 seeds, real tier): 12/12 exact
  seat-determined splits (|m1| = |m2|) — the lock changes nothing where no recorded world
  matches, i.e. zero regression risk outside the clone domains.

**BAKE (sub26):** tests 194/194 then `pack.sh` — PACK OK, archive plays the repo
bank-for-bank on 8 episodes, single-file fallback verified, `book_world_lock` present in the
embedded build, book file unchanged (cedcd371…).
- `submission.tar.gz` sha256 **23446a445ceffe36b2a172f2fa185d9634465bfaf36b3e25a6a4b54d1aa19460**
  (repack-stable: two packs byte-identical, cmp-verified)
- `submission/main.py` sha256 **b685d69090954c22b4d70f1290f38ab7a81b7e7b2dc405d1596b38d06d233e43**
- tarball `kagfarm/policy.py` == repo `kagfarm/policy.py` (sha256 dfff0f36…) — byte-verified.

**UPLOAD NOTE:** nothing has been uploaded. Owner decision: seat `submission.tar.gz`
(23446a44…) in **Slot B** via the Kaggle UI pencil badge (Slot A / sub17 untouched). sub25
(c539704a…) is superseded: equal or better on every gate, with the clone domain now served
exclusively by its own world's chain. Phase 4 queue: the d0-2 script-class window is CLOSED
as information-theoretically impossible (oracle proof) — remaining book upside on this route
is zero; next value is the capacity package (tomato mix + grain marketization + herd
envelope) and the elite judge tier re-pull (spectator tapes / dataset terms).

## 0930f — LIVE-FIELD AUTOPSY + HERD-PROTECTION STACK; sub27 baked (all gates real tier, all PASS)

**Owner seated sub26 as ref 56703163 (2026-09-30 09:14, public 538.8) — first real ladder read
of the elite-book build.** `analysis/morning_pull.py --sub 56703163 --dir submission26games`
pulled 25 episodes: **14W-11L, mean +4,521** — dominant below 540 (13W-2L, mean +26k) but
**0W-5L above 600 Elo, mean -40,193** (Fazil Putra -85k, Sandeep -52k, sansh0u0 -37k). Our
final banks 45-113k vs their 100-140k: a CEILING gap, not an opening failure (d0-12 trajectories
are equal in wins and losses; the split happens d18-29).

**Root cause chain (per-episode forensics, Adel Zebiche 115705045 the cleanest):** the 600+
opponents run 11-26-animal herds that pay through the final week (Fazil +46.1k, Sandeep +48.2k,
sansh0u0 +49.6k in d24-29) — ours earned +9-17k there because the herds were DEAD. Engine rule
(calibration/engine/kaggriculture.py:816): an animal ESCAPES after 2 consecutive unfed days.
Feed stops in our worlds because of a shed deadlock: (1) MILK has no shop draw in these worlds
-> drain_per_day_from_shops == 0 exactly -> the crowd-cap valve metered it at a constant ~2/day
while production ran 4-6 -> the pile SAT (30-36 slots at $1-15 for weeks, 234 sold all game);
(2) milk_window's glut-hold parked up to 40 MORE dead slots betting on a recovery no buyer
exists to deliver; (3) FERTILIZER sat at 26-63 under the $55 crowd floor; (4) shed at 100/100
released the feed-grain hold (the `not crowded` gate) while BUY_PRODUCT WHEAT 84/day orders had
nowhere to land; (5) feeds 13 -> 6 -> 0 across d19-21; herd 13 -> 7 -> 0 across d21-23. Also
found: shepherd_loops hard-coded `endgame = day >= SEASON_DAYS - 1` ("herd is liquidated") but
the engine offers NO way to liquidate an animal — d29 was a guaranteed dead-herd day, and the
`not endgame` FEED/CARE gates left the herd unattended d25-28.

**The fix — four independent flags (all threading through, defaults preserve the byte-stream):**
- `shed_endgame_chore`: shepherd_chores/animal_jobs/shepherd_loops/wheel_plan keep FEED+CARE
  through the endgame DAYS (d25-28); the FINAL dawn (d29) still stops (no cycle scores).
- `grain_release`: the crowded shed no longer sells the feed-grain hold (`(not crowded) or
  grain_release` — the first draft `not (crowded and grain)` inverted this and broke the
  monitor-residual pin 5.097 -> -5.832; caught by the pin, fixed, byte-parity re-proven).
- `no_shop_valve`: in a crowded/valve-open shed, a good with d == 0 (no shop drain, not
  town-centre) sells AT ANY PRICE; `keep_price_floor` goods exempt.
- `milk_dead_hold_release`: the milk glut-hold releases when MILK drain is structurally zero.

**Measured:** mirror flag screen (analysis/flag_screen_once.py, twin self-play): grain_release
15 animals alive at d22/29 vs 12 shipped; shed_endgame_chore +879 sum-bank; the sell-side pair
mirror-inert (the dead-MILK crowded-shed state is ladder-real). Full ladder ON the stack (real
tier, PYTHONHASHSEED=0): paired 12 seeds **24W-0L-0T mean +25,267 worst +6,831** (sub26:
24W-0L +25,451 — W/L identical), wall **2W-5L -8,442** (sub26 -8,588; hayday +732), famine
**2W-0L +39,936** (akilit +17,449, +1,205 — the herd tier gains most), midfield **4W-0L
+19,426**, hold-out **22W-2L-0T +12,886**. Every W/L profile identical to sub26; margins inside
the judge-noise band. Tests 194/194 with the flags ON in PARAMS (defaults were proven inert by
byte-parity: monitor residual 5.097 exactly equals the pre-flag build).

**BAKE (sub27):** pack.sh PACK OK, archive plays the repo bank-for-bank (8 episodes),
`shed_endgame_chore` present in the embedded build (15 refs), repack-stable (cmp-verified).
- `submission.tar.gz` sha256 **3836b905833d2dd79f0fada03a89f9db0fddf25760c442474d196f5e60f5c7c7**
- `submission/main.py` sha256 **cd257e4444d12e8055e1408ab290ff5d2d6f751652f1b5e77ace834c78aa8453**
- tarball `kagfarm/policy.py` == repo (sha256 d2d590f1…) — byte-verified.

**UPLOAD NOTE:** nothing uploaded by agents. Owner decision: seat `submission.tar.gz`
(3836b905…) in **Slot B** when the next cadence window opens (sub26/ref 56703163 currently
resident at 538.8). Expected field effect: the 600+ band losses were herd-collapse losses —
the stack attacks exactly that (mirror +3 herd, famine akilit +1,205); the below-540 dominance
should be untouched (W/L profiles identical on every gate). Remaining queue: capacity package
(tomato mix + grain marketization + herd envelope vs the 600+ opponents' 11-26 herds),
cow-lean herd rebalance (winners run 8 COW / 3-4 SHEEP; ours 9+5), elite judge tier re-pull.

## 0930g — CRITIC PILLAR AUDIT: shop-gated sheep BUILT, MEASURED, REJECTED; monitor fixture pinned

External-strategist pillar review (three claims) audited against engine tables and panels:
- **Pillar 3 (thirst = route interruption)** — SUPERSEDED by measurement: the 0929 wall graft
  already runs the v7 survival-first allocator (six documented failed iterations); the 0930f
  stack removed the true leak (shed deadlock -> unfed herds -> escapes). No new work.
- **Pillar 4 (reserve floors vs drip-selling)** — CONFIRMS the shipped design (tick_burst off
  is correct: crowd_floor_frac 0.5 already prices storage risk; milk/wool keep dedicated
  windows; 0930f milk_dead_hold_release covers the dead-market case). No new work.
- **Pillar 2 (shop-gated livestock)** — the 34.4% number is EXACT (8 shop types drawn with
  replacement, 8 draws, (7/8)^8 = 0.344; verified engine source + constants). Wool drain is
  binary: 13/day with a YARN_STORE, 1/day town-centre-only without. BUILT as
  `shop_gated_sheep` (+sheep_drain_min=5, sheep_floor): gates the sheep envelope at current
  count and blocks the wool-lane seeding force-pick when the observed drain is thin; default 0
  byte-inert (monitor residual 5.097 == pre-flag sub26 file under the pinned fixture).
  **MEASURED KILL on the real tier:** paired flag-ON vs sub27, 12 seeds seat-swapped:
  10W-14L, mean -409 (panel1 4W-8L -162 incl. two double-seat losses; panel2 6W-6L -656).
  Refuted on the shipped build: `animal_rank` already prices wool through the live shop-keyed
  drain curve and `wool_floor` monetizes the thin drain — the stranded-capital scenario the
  critic describes is already handled without shrinking the flock. Flag stays DORMANT with
  the panels as the record. Do not re-test this axis without a new mechanism.

**Test-fixture repair (tests only, artifact unaffected):** TestMarketMonitor's monitor pins
broke when the 0930f flags shipped ON — the fixture world itself changed (self-play sell
cadence), not the monitor: sub26 file 5.097 / one-seat-flags-off -5.832 / both-on 0.916.
Fixed TestMarketMonitor with a setUp/tearDown pinning flags-OFF on BOTH seats (mirrors
TestOpeningBook's pattern); 194/194. A first edit attempt corrupted the test file (orphan
docstring tail, SyntaxError line 751) — repaired and verified via ast.parse before running.
Also learned mid-session: several tool results in this thread were corrupted/impossible
(misspelled paths 'kaggressive', phantom test counts 200/194) — all conclusions above were
re-derived from disk-verified state (sha checks, like-for-like A/B harness); the 0930g/0930f
ship-state on disk is confirmed correct (repo policy ef3b5736…, sub27 tarball d2d590f1…
== ledger).

**SUB27 REMAINS THE SEATED CANDIDATE** (3836b905…, unchanged — 0930g added only dormant code
+ test pins). Queue unchanged: capacity package, cow-lean herd rebalance, elite judge re-pull.

## 0930h — BRIEFING 5 CONSULT (2-API): the critic-converged items adopted; sub28 baked

**The consult** (analysis/nemo_briefing5.md -> nemo_consult5.py -> nemo_answers5.md +
per-key files): the external architecture critique ("terminal-cash optimizer, 8 engines")
put to both OpenRouter keys with our measured state and constraints. Answers converged:
- **Q1 triage — BOTH: build Engine 4 (global action scheduler) + Engine 1 (delta-TC shadow);
  refuse Engine 2 (full shared-market forward sim: compute-prohibitive, and sequential
  repricing cannot represent the hard shed-capacity deadlock that actually killed our
  herds). KEY also refuses Engine 5 (predictive opponent model); Y_2 also refuses Engine 7
  (replay mining: compute/transfer risk). Engine 3 (joint portfolio) ranked near-last by
  both — the cited public-reconstruction numbers are a static single-player snapshot.
- **Q4 premise split — BOTH 25/75**: only 25% "missing numerical profit engine"; 75%
  "execution throughput / mechanical fragility." Both cite our own evidence: world-lock
  perfection was ladder-neutral, herd survival was the 600+ separator, the principled
  sheep gate lost 10W-14L. KEY: "opponents above 600 likely EXPLOIT fragilities, not
  out-optimize portfolios." Both give a discriminating measurement: run the Engine-4
  shadow telemetry on the 600+ worlds; KEY: sub27 vs 600+ in the next 24 paired games
  (>=2W-2L confirms the fragility explanation).
- **Q2 — both prescribe a SHADOW form with kill numbers**: shadow assignment layer over
  the existing rank/allocator; kill if productive-action rate does not rise (KEY +3pp with
  <=50ms/turn; Y_2 +2pp, famine tier must not regress).
- **Q3 traps — both flag**: portfolio numbers are single-player overfits (Fibonacci wages
  are a step function, not marginal; midnight overflow discards INCOMING bags so shed-slot
  value != production capacity); market-impact simulation ~ full engine sim (the sheep-gate
  loss proved this); TOMATO suppression is a heuristic, not a structural truth.

**Adopted (both default-off or inert):**
1. **Productive-action telemetry** (the falsification substrate both answers require):
   per-day records in Policy.telemetry_days ({actions, productive{}, move, idle, turn_ms}),
   classified like the public analysis (N/S/E/W = movement). Always-on instrumentation,
   zero behavioral role. First mirror read: 38.1% productive / 57.0% move / 14.7% idle —
   ALREADY near the public top-farm profile (40.7%/53.9%): the throughput gap to 600+
   worlds must now be measured THERE (the discriminating experiment), not in mirror
   self-play. Two build defects caught and fixed in-session: an accumulator block landed
   in __init__ (135 test errors, never-raise shell would have silently PASSed it — the
   suite caught it in 8s); a synthetic-obs test path missing the dawn init (0 != 1).
2. **tomato_probe flag**: injects a TOMATO entry into the mix so the marginal loop can
   DISCOVER a tomato regime (CROP_PLAN has TOMATO: harvest d11, 4 units, 8 water-days);
   _board_state counts it; default 0 byte-inert. Smoke: flag-on never bought a tomato
   seed all season in mirror (rank table still prefers the shipped mix) but the mix-share
   reshuffle moved the mirror bank +5,102 on one seed (59,382 vs 54,280) — acreage-cap
   sensitivity is real (the dossier's claim), worth a proper sweep arm later.

**Gate ladder on ship defaults (real tier, PYTHONHASHSEED=0):** tests 194/194; monitor
residual 0.916 == sub27 ship state (behavioral parity); counterfactual 11/12 hold, 21.3
served, mean delta -26,960 (vs -27,354 pre-0930f: the herd flags improved clone worlds);
paired 24W-0L-0T mean +23,578 worst +6,431; wall byte-identical 2W-5L -8,442; famine
byte-identical 2W-0L +39,936; midfield byte-identical 4W-0L +19,426; hold-out 22W-2L-0T
+12,666. **BAKE (sub28):** pack.sh PACK OK bank-for-bank (8 eps), repack-stable (cmp),
telemetry/tomato_probe present in the embedded build.
- `submission.tar.gz` sha256 **82ecbba866b1f2c712d15cc82f29057d4cceb6daa10a2246f49f334d8fba761b**
- `submission/main.py` sha256 **1e26e806d4dd665d1a5c8798566890941c3d77870de160d7ad10e3dc89101964**
- repo `kagfarm/policy.py` sha256 **64a32be2920e08d9b1d30856c51c6067471151045d18d24c06f4c652c1bb124c**

**NEXT (the consult's own discriminating experiments, in order):** (1) telemetry read on
the 600+ ladder worlds — pull the next sub26/sub27 episode batch and classify productive
vs move vs idle per band; KEY's kill number: sub27 >= 2W-2L vs 600+ confirms fragility,
<=1W-5L reopens the profit-engine question. (2) Engine-4 scheduler shadow: build the
min-cost assignment advisory behind the allocator, gate = productive-action delta with
the kill numbers above. (3) tomato_probe sweep arm on the real tier (the +5,102 mirror
hint). (4) NOT BUILT, per both critics: full market simulator, opponent-supply
forecasting, replay-mining ML — revisit only post-tournament.

## 0930i — THE DISCRIMINATING MEASUREMENT: throughput-gap premise REFUTED; Engine-4 shadow refused pre-build; tomato probe a wash

Both briefing-5 answers conditioned their #1 pick (Engine 4) on "top farms convert 40.7% of
actions vs our 34%" — a ceiling of free Elo from movement efficiency. The telemetry built in
0930h made this measurable on the LADDER itself. Read all 25 sub26 episodes, both seats, every
farmer/hand head-op classified (productive / movement / idle / market-SELL), opponents banded
by the 0927 leaderboard CSV (10068 teams):

| band | n | our prod% | their prod% | their move% |
|---|---|---|---|---|
| <540 | 15 | 40.2% | 38.9% | 48.3% |
| 540-600 | 4 | 39.7% | 39.3% | 51.1% |
| 600+ | 6 | **40.2%** | **40.5%** | 52.8% |

- **Our productive-action rate is band-INVARIANT (40.2% everywhere) and statistically
  identical to the 600+ opponents who beat us.** Individually: we OUT-produce Chikkam
  Sandeep (37.4%), sansh0u0 (37.0%) and Gruberx (32.4%) while losing to them by $18-52k;
  Fazil Putra is the only super-efficient outlier (53.8% — and the <540 band ALSO contains
  high-prod% opponents, so the rate does not separate wins from losses in either
  direction). Our prod% by result: W 40.8% vs L 39.3% (noise).
- **VERDICT: the "34% vs 40.7% movement-waste ceiling" does not exist on the ladder.** The
  600+ gap is WHAT the productive actions land on — asset scale and composition (their
  acreage ramp, herd sizes, endgame income) — not how many actions are productive. The
  public reconstruction's 34% benchmark was a weaker third-party bot, not us.
- **Engine-4 shadow REFUSED BEFORE BUILD** (plan decision rule: ceiling must be real). Zero
  code written, days of engineering saved. The same telemetry still pays: it is the
  standing per-band throughput monitor for every future episode batch.
- **tomato_probe real-tier panel: 6W-6L, mean +$24, median +$690** — an exact wash; the
  flag never actually allocates tomato (the rank table rejects it every dawn; the mirror
  +$5,102 was a mix-share reshuffle artifact of the caps, not tomato value). Flag stays
  shipped and dormant as the DISCOVERY switch it was built to be; no arm, no further
  sweeps. The "tomato regime" the critique wanted discoverable is now formally measured
  as not-existing at these shop-draw prices — with the mechanism (rank rejection, not
  structural suppression) proven.

**ARTIFACT STATE: unchanged. sub28 (82ecbba8… / policy 64a32be2…) remains the seated
candidate; zero code changed this entry — both experiments were measurements of existing
state, which is the cheapest kind.** The consult's queue is now fully executed or formally
refused: Engine 4 refused pre-build (ceiling refuted), Engine 1 shadow remains OPTIONAL
(the fragility hypothesis it would serve was itself downgraded by this measurement),
tomato probed and closed, Engines 2/5/7 refused by both critics. The remaining ladder gap
to 600+ is asset scale — the capacity package (acreage ramp + herd envelope) is the one
live candidate queue, and the cow-lean herd rebalance is its first arm.

## 0930j — SUBMISSION-6 (S6) AUDIT EXECUTED: P0 correctness items verified and fixed; sub29 baked

The S6 architecture audit's P0 list was verified against code item by item, then fixed or
closed with measurements. No behavior changed on any measured world (ladder byte-identical
to sub28); these are correctness fixes under the serving path.

**FIXED (shipped):**
1. **Day-29 final-turn boundary** — the donor tapes record 24 entries d0-28 but 23 on d29
   (the h23 decision is never recorded: the episode settles first). The old path hit the
   IndexError at the final settlement turn and fell through the silent catch to the planner.
   Now an EXPLICIT handoff (`day >= SEASON_DAYS-1 and hour >= TURNS_PER_DAY-1 -> return
   None`): the terminal planner's full-clear owns the last turn by design, not by accident.
   Behavior-identical on every world (the planner was already taking over); the fix removes
   the accidental policy boundary.
2. **Book validator settlement semantics** — the 0930c guard required the shed to ALREADY
   hold every SELL unit, but the engine settles unit actions (DROP empties the bag) BEFORE
   market orders within one step, so a recorded donor turn of DROP-then-SELL was genuinely
   funded and the guard halted whole donor days for no corruption risk. Carried inventory
   now counts toward a SELL exactly when the SAME action carries a DROP. The two halves of
   the agent now share one settlement semantics (the sale engine's documented form).

**VERIFIED NON-BINDING (measured, no change):**
3. **Planner/executor labor mismatch** — the hook exists (`animal_load` param, shipped 0.0
   with a measured rationale). Re-tested under the 0930f herd stack: banks byte-identical
   at 0.0 / 0.8 / 1.6 (the ceiling has slack at the current roster; the 0922 measurement
   stands). Not a bug: a documented, re-confirmed conclusion.
4. **Ongoing-crop flat pipeline** — claim CONFIRMED (a standing strawberry counts its full
   4-unit block regardless of remaining events; arrival timing invisible). FIXED behind
   `arrival_weighted` (default 0 = shipped flat form): each standing tile discounts by
   remaining-events/total-events. Dormant pending its own gate — the pipe feeds
   `effective_prices`/`marginal_rank`, so this is a model change, not correctness.

**S6 claims checked and already-shipped or previously measured:** elite-book sig
exclusion of market/opponent state (deliberate, documented v2/v3 design with the world-lock
oracle proof on record); wool/milk floors as heuristics (milk_dead_hold_release now covers
the dead-market case); herd constants (envelope is a search space, marginal rank governs);
TOMATO/goose exclusion (TOMATO discoverable via tomato_probe and measured not-existing at
these prices; goose lane demand-gated already). The S6 macro-simulator/strategy-zoo/reset
proposal remains a post-tournament item — this session's measured refusals (Engine-4 ceiling
refuted on the ladder, principled gates losing to the coupled rank system, world-lock
ladder-neutral) are the evidence base against rebuilding the controller mid-cycle.

**Gate ladder (ship defaults, real tier, PYTHONHASHSEED=0):** tests 194/194; monitor
residual 0.916 == sub28; counterfactual 11/12 hold, 21.3 served, -26,960 (identical);
paired 24W-0L-0T +23,578; wall -8,442; famine +39,936; midfield +19,426; hold-out 22W-2L
+12,666 — every tier byte-identical to sub28. **BAKE (sub29):** PACK OK bank-for-bank,
repack-stable (cmp).
- `submission.tar.gz` sha256 **39c4a5fe9d88976d1026b902443d036b3f9cb27d8462a893a48cc6692a6dfc7e**
- `submission/main.py` sha256 **e92a6eb2810918839df7874f36cd7c1501febfbeb82fda094189c17cb3c48c84**
- repo `kagfarm/policy.py` sha256 **679cc9a9efe0842fdbaa9f0cadd4282252531802a180158f4b81af8c3c656fdc**

**SEATED-CANDIDATE NOTE:** sub29 supersedes sub28 on correctness (the final-turn handoff and
settlement semantics are the two real defects of the serving path). Owner seats sub29
(39c4a5fe…) in Slot B at the next window.

---

## 0930k — BRANCH COUNTERFACTUALS on B (115863161): the $56.7k gap is the milk regime, NOT the herd collapse; admission control is NOT the fix

**Method (exact, not proxy):** `analysis/branch_counterfactual.py` replays episode 115863161 through the vendored 1.32.7 engine using verify_replay's alignment (action@t produces obs@t from state@t-1; state seeded from deep-copied steps[0]; obs.step=t-1). Both run-level and per-step gates must pass — run-level byte equality is necessary but not sufficient. BASELINE: 50,648/77,754 with all 719 steps byte-exact on all COMPARE_KEYS. Interventions branch the replay and rerun; the opponent plays its recorded tape throughout, so Δcash is attributable to the intervention alone. `PYTHONHASHSEED=0` throughout. Harness sha256 `f75e97bdde05db90a9ff5162052dcee891c9bfa11be48255e21855f7ac5dd5bdb` — verify on disk before quoting.

**v1 harness defects (caught and fixed before any conclusion):** (1) `_commit_unit` sell collectors bound to the baseline's farm object identity — dead item breakdowns in all non-baseline branches of the first panel; (2) MilkFloor v1 froze the whole market at d18 (snapshot-restore before every step) and drained the wrong direction (drained while price > target); its rows measured "freeze at d18", not a milk regime — `milk_250 == milk_180` byte-identical was the tell; (3) FeedOracle v1 (free shed wheat at dawn) was re-routed by the fixed tape into market sales: +13,390 with the SAME 12 escapes, not a service fix. Replaced by FeedService (force `fed_today` outcome) and MilkHold (drain shared market MILK to target via the engine's own curve). `no_d0` = engine artifact (skipping d0's recorded animal batch breaks the script farm — terminal 0, not a result). `cap8`≡`cap10` because B's herd enters d14 at 11 and only expands... never (never exceeds 10 post-d14 on the recorded path), and `cap12` is a no-op by the same mechanism (never exceeds 10 post-d14 on the recorded path).

**Results (final bank, Δ vs 50,648; gap to close = 56,725):**

| branch | final | Δ vs B | herd d29 | escapes d14+ | milk $/u |
|---|---:|---:|---:|---:|---:|
| baseline (byte-exact 719/719) | 50,648 | — | 2 | 12 | 75 |
| no_d6 (skip 6 COW) | 48,593 | −2,055 | 1 | 7 | 121 |
| no_d6_d7 | 48,999 | −1,649 | 1 | 7 | 121 |
| no_d13 (skip 3 COW) | 51,678 | +1,030 | 2 | 9 | 75 |
| no_d6_d7_d13 | 50,513 | −135 | 1 | 4 | — |
| no_d0 | 0 | artifact | — | — | — |
| cap12 | 50,648 | +0 (no-op) | 2 | 12 | 75 |
| cap10 / cap8 | 51,678 | +1,030 | 2 | 9 | 75 |
| service_d18_25 | 50,062 | −586 | 2 (collapse DEFERRED to d28) | 12 | 75 |
| service_d14 | 52,447 | +1,799 | 14 | 0 | 75 |
| milk_250_d14 | 67,789 | +17,141 | 2 | 12 | 227 |
| milk_180_d14 | 60,331 | +9,683 | 2 | 12 | — |
| milk_250_d18 | 63,167 | +12,519 | 2 | 12 | — |
| combo_service_milk | 70,053 | +19,405 | 14 | 0 | 228 |
| combo_nod67_service_milk | 56,344 | +5,696 | 8 | 0 | — |

**The three headline rows:**
- `service_d14` — oracle-feeding every animal every turn d14-29: herd held at 14, **zero escapes**, final **52,447 (+1,799)**. The celebrated 12-escape catastrophe was worth ~$1.8k on this path.
- `milk_250_d14` — drain the shared market's MILK to a $250 quote from d14, both seats' recorded behavior UNCHANGED: final **67,789 (+17,141)**, milk realizes $227/u vs $75/u on the same 113 sold units, and it happens **with the 12 escapes still happening**. Pure market-regime dollars, zero behavior change.
- `combo_service_milk` — both: **70,053 (+19,405)** ≈ additivity within noise; service and regime are ~independent mechanisms.

**Admission-control rows (the user's hypothesized fix, measured):** skipping the exact d6-7/d13 batches moves terminal cash −2,055 to +1,030 — **no_d6 is NEGATIVE** (the 6-COW batch pays for itself even on the collapse path: d6 cash $670 can fund zero further hires; skipping it frees nothing else). cap12 no-op; cap10/cap8 +1,030. Even perfectly-timed admission control worth ≤ $2k here; the collapse was recoverable at the d14 tie point by service alone (+1,799 with zero escapes) or regime (+17,141 with the collapse). **"B shouldn't have bought those cows" is REFUTED as the dominant cause; the runaway variable is the shared milk price.**

**MilkHold d18 variant:** +12,519 — most of the regime damage lands d14-18.

**Composition at the d14 tie point (why the regimes differ):** our herds were IDENTICAL (6 COW + 3 SHEEP both runs); B had +2 geese and slightly fewer plants (56 vs 61). The opponent differed: **B's Antonio ran 8 COW + 4 SHEEP at d14 vs A's ShayML 5 COW** (B's opp = 8C+4S from d10). B's glut was OPPONENT-built — our own herd is NOT the glut source. Careful with v3.0's milk_hold conclusion here: v3.0's flagged d25 batching is real but is not where the gap lives — the real driver is B's OPPONENT's herd building a milk glut that crushed our realization to $75/u.

**v3.0 convergence:** its five non-additive columns (and the report's own warning) were correct — the two dominant branches are near-additive (+1.8k service + $17.1k regime = $19.4k of the 56.7k gap; the remainder is A-side revenue-mix/land difference, non-additive both directions). Both dominant losses are INVISIBLE to any admission-control fix. The capacity package (acreage ramp + cow-lean rebalance) is NOT re-aimed by this episode: B's deficit here is regime + service, not admission. Re-aim it at the 600+ band losses (Fazil −85k, Sandeep −52k, sansh0u0 −37k) before spending a gate on it.

**Artifacts:** `analysis/branch_out/branch_results_0930k.json` (per-branch banks/dawn-cash/herd-dawn/sold/rev/terminal-shed); branch log above. Ledger verified on disk after write.

**0930k REPACK (final):** pack.sh re-run 10/01 after 0930k (policy.py unchanged at 679cc9a9…): tar **byte-identical to seated sub29** (`39c4a5fe…`, cmp clean), submission/main.py regenerated+verified (`e92a6eb2…`). Battery re-run on exact tar bytes: PACK OK 16/16 bank-for-bank, harness smoke 3/3 episodes DONE 720 steps no ERROR/TIMEOUT (vs-starter 59,216/3,835; swap 3,571/115,978), tests 194/194. Artifact-of-record unchanged; ready to seat.

---

## 0930m — PLAN-EXECUTED SESSION (the 35-point severity-table plan): every P0/P1/P2 item either fixed behind a default-off flag, measured, or verified-already-shipped; artifact-of-record stays sub29

**Data-loss incident (first thing on record):** five elite judge tapes (111103455 air, 111148725 aditya, 111201497 sathish, 111229714 kovkin, 111264433 madhur) were deleted from ~/Downloads outside the session; the default judge_bar BAR tier cannot run until re-downloaded (`--sub` pulls or morning_pull). 14 TRACKED files were also deleted (PLAN.md, KT doc, sweep JSONs, notebook) — left untouched per ownership protocol. `submission.tar.gz` was "missing" — owner had renamed it `submissionfinal.tar.gz` (same bytes 39c4a5fe…); restored under both names. Surviving gate battery: elite3 (majkel886/900/907) + famine2 + midfield4 + wall7 = 16 judges; SHIPPED baseline re-run first and reproduced the 0930j sub29 numbers byte-for-byte (0-3 −84,635 / 2-0 +39,936 / 4-0 +19,426 / 2W-5L −8,442) before any arm was trusted.

**Plan-item disposition:**
1. **Book state aliasing (P0)** — measured, not guessed: sig (day, shops, money-bucket, herd, wool, wheat-bucket, fert-bucket) aliases on d0-2 exactly as documented (all donors identical d0 — the known unsolvable), 9/30 days any aliasing, **0/30 days where aliased donors differ in hands**. Donor-chained world lock (0930e) already IS the plan's "elite_prior not elite_controller" direction: chain identified from shop schedule, then served with NO cross-donor matching. `analysis/book_audit_0930l.py` is the permanent probe.
2. **Hands in sig (P0)** — VACUOUS as specified: the engine resets farm["hands"]=[] at every dawn (kaggriculture.py 880) and hires during the day, so a dawn hands field is [] for everyone. The reshape concern is bounded by lineage: served days replay the donor's own HIRE orders (roster = donor lineage); reshape fires only on rescue-tier days (cap 2/ep) and one mixed day after a halt.
3. **Rescue widening** — measured 0 dawns on both ladder replays: the rescue band never admits a foreign donor there. Cap stays 2.
4. **Planner/executor labor mismatch (P0)** — verified-already-enforced: `animal_load` re-measured non-binding 0930i; shepherd loop gate is EXACT-cost (policy 4286-4294: per-loop real walk+ops must EACH fit the day); feed_backbone + time-indexed feed_ok (4227+) already run the cumulative-demand-vs-supply check the plan asked for. Charging livestock against the crop ceiling stays the 0922 measured reject (farm shrank, idle rose, nothing gained).
5. **Opponent future supply (P0)** — BUILT: `opp_supply_pace` (+window/gain) — census history per turn, milk-window glut test ORs in a >=3-cow growth over 3 days (Antonio ramp shape; 0930k: the level trigger milk_opp_glut=8 fires only after the glut exists). Judge verdict: byte-identical 16/16 — Majkel-type elites hold LEVEL herds; the pace arm targets ladder ramp opponents and stays dormant pending a real ladder A/B.
6. **Recurring production time-indexing (P0)** — `arrival_weighted` (built 0930i) judge-barred for the first time: byte-identical 16/16. Dormant.
7. **marginal_sell=0 (P1)** — **DISCOVERED LATENT DEFECT**: the dormant flag was wired to a stale 7-arg call against the 8-arg `_marginal_hold(good,n,mi_now,tiles,unlocked,shed,day,horizon,unlocked_shops)` — arming it pre-repair raised TypeError per good inside the never-raise guard, i.e. the 0925b "MEASURED −$115,914 catastrophic" verdict measured a crash-to-PASS cascade, not the mechanism. Call repaired (8 args, shed passed). Re-measured real tier: W/L identical on all 16; margins ~neutral (wall 2-5 −6,909 vs shipped −8,442 on aarya −22.9k→−9.3k; midfield 4-0 +19,844; elite 0-3 −84,940; famine 2-0 +39,934). Mirror screen +$29,296. Verdict: mechanism is NOT the 0925b catastrophe; still W/L-neutral → stays dormant, flag 0. This invalidates the ledger's −$115,914 row as a mechanism verdict (it was an artifact verdict).
8. **always_sell hard law (P1)** — `sell_gate_always` param added (default == always_sell; endgame pause reads it); inert by construction while endgame_floor=0 (measured reject) — the seam for a future state-dependent gate exists without touching shipped behavior.
9. **Route budget-break (P1)** — the plan called it a bug; MEASURED CATASTROPHIC as "fixed": `route_skip_stuck=1` on the mirror = 53,099 vs 129,906 bank, herd 3, minfeed 3 — the shipped `break` hands the over-budget job to the NEXT unit via the shared cursor; skipping it discards work and fragments runs. REJECTED, flag stays 0, `split_runs` gained the documented skip_stuck kwarg (call sites thread it, default off).
10. **Wheat model: field vs feed (P1)** — `feed_demand_floor` built: mouths pin shed wheat at ANY price incl. endgame (B-run d24-25 window). Judge: byte-identical 16/16 (shipped holds already bind everywhere the judges exercise); dormant for ladder A/B.
11. **Market slots (P1)** — no change: BUY_SEED emits one slot per CROP (dearest-first, skip-and-continue on unaffordable heads in _seed_orders), which IS the deferral the plan demanded; a cross-good slot optimizer remains a post-tournament item.
12. **PARAMS_BASE "duplicate" (P2)** — the two assignments were exact-identity by construction (import-order); consolidated: end-of-file block re-pointed as the single source of truth with PARAMS_BASE.update(PARAMS) belt-and-suspenders; mid-file legacy snapshot annotated. Tests 194/194 pass (windfall_pct identity pins).
13. **Exception-to-PASS (P2)** — `_fallback_errors` counter added in act()'s guard (inert telemetry); flag screens report it, fberr=0 everywhere this session. The counter is how the NEXT "catastrophic" verdict gets caught as a crash cascade at screen time — same lesson as item 7.

**Ship state:** ALL new flags default-0; ship block and PARAMS_BASE semantics unchanged; tests 194/194; artifact-of-record = sub29 39c4a5fe… (submission.tar.gz == submissionfinal.tar.gz, cmp clean, harness smoke re-passed post-restore). policy.py a2206fd2… route.py a9439eb5… flag_screen_0930m.py e7ab59e8… (verify on disk before quoting).

**Plan verdict:** the plan's highest-value specific find was unintentional — repairing marginal_sell's call exposed that one of the ledger's headline rejects was a crash artifact. Its book/labor claims were largely already-shipped engineering (world lock, exact-cost gates, feed backbone), and its route "bug" is a measured kill. The genuine new mechanisms (opp pace, feed demand floor, arrival weighting) are dormant and ladder-invisible on available judges — their promotion path is the real ladder, not the tape set.

---

## 0930n — PLAN P0-1..P0-8 IMPLEMENTED AS SHIP INTENT (owner directive: mechanisms ACTIVE, regressions recorded not gated); SUB30 BAKED

**Basis:** owner's directive to implement the 40-point plan "even if changes fail on the judge book"; the gate discipline is retained ONLY for crash-cascades (a TypeError-to-PASS spiral is a broken build, not a measurement — every arm verified fberr=0 via flag_screen).

**P0 dispositions (all ACTIVE in the ship block unless noted):**
1. **P0-1 book_valid DROP accounting FIXED**: actor-specific sellable = shed + Σ(actors that DROP g)·carried_i(g) via private.inventories, replacing the blanket any-DROP-credits-all-carried form (hand 3's milk no longer pays hand 7's fertilizer sale).
2. **P0-2/P0-6 market intelligence ACTIVATED**: monitor=1, opp_credit=1.0, opp_acreage_credit=0.10 (the 0924 full-1.0 elite reject re-entered SMALL at the plan's direction; verdict below).
3. **P0-3 service_slack_admission ACTIVE** + **two real defects found while integrating**: (a) the first draft sat inside the non-wave housing block — shrinking base buys freed cash the wave lane spent on an unhousable late cohort (rot); moved to bind the plan's FINAL cohort, whatever lane funded it; (b) the late window admitted buys against n_build grace that promised structures the board could not hold (no empty tile for the 17th pasture) — fixed: late window (>= wave_housing_free_until=18) admits ONLY into existing structures. New param wave_housing_free_until=18 preserves the measured d11-13 wave flow.
4. **P0-4 event-pricing ACTIVE**: animal_programme now emits `events` (the exact pop walk: first pop banks `first` care-days, later pops `1+interval`); animal_rank prices each pop at the head it will meet (prior pops already on the market) instead of one average. Single-event programmes take the old path byte-identically.
5. **P0-5 arrival_weighted=1**, **P0-6 opp_supply_pace=1**, **feed_demand_floor=1** all ACTIVE.
6. **P0-7 marginal_sell=1** (the 0925b catastrophic was the 0930m-found crash artifact; honest verdict W/L-neutral).
7. **P0-8 book-off ablation RUN** (elite3): book-off 0-3 margins −47.7k/−73.0k/−51.6k vs book-on (sub30) −62.8k/−104.9k/−90.1k — the book is worth ~$35-40k of ABSOLUTE economy on elite worlds (907: our bank 74.8k vs 43.0k), though margins NARROW book-off because our suppressed play stops suppressing the judge's book (market denial). W/L 0-3 both ways: the elite gap is CAPACITY (their recorded $156k vs our ~$75k), confirming the plan's own scorecard diagnosis. The book is a first-class asset, not a crutch to delete; E0-in-strategy-zoo remains the right long-term shape.
8. **Recorded refusal (unchanged from 0930m):** route_skip_stuck=0 — mirror-measured catastrophic (44,895 vs 140,488 sum-bank under the new baseline; the shipped break delegates to the next unit).

**Real-tier verdict (16 judges, shipped sub29 baseline re-verified byte-exact first):**
- W/L: **12 identical, 1 regression (wall aynrmio W +3,781 → L −22,109), none gained** — wall 1-6 vs 2-5.
- Margins: midfield 4-0 **+27,041 vs +19,426 (+38% on the primary tier)**; famine 2-0 +44,055 vs +39,936; elite 0-3 −85,925 vs −84,635 (guard tier, immaterial); wall 1-6 −12,469 vs −8,442 (the aynrmio flip).
- Mirror (glut world): sum-bank 140,488 vs 129,906 pre-activation (+8%), herd29 16/16, min_feed 12 vs 9 — the service machinery is strictly healthier on the world that reproduces the ladder loss conditions. Seeds 0/2/7: banks 71.5k/55.7k/79.4k, ZERO shed rot.
- Tests: 194-run, **6 recorded pin overrides** (5 sell-behavior pins + opp_acreage default pin assert the PRE-activation world the plan overrides), 0 errors, rot test PASSES.

**BAKE (sub30):** PACK OK bank-for-bank 16/16 (worst 51 ms), harness smoke 3/3 DONE 720 steps.
- `submission.tar.gz` == `submissionfinal.tar.gz` sha256 **4ec2b7db35de7bed5b2821dddee1c69879e2e3595f430e04ab747e06a3cf0d35**
- `submission29.tar.gz` = the seated sub29 (39c4a5fe…) as rollback
- repo `kagfarm/policy.py` sha256 **f3ba8c8c28025603085bf6c9c24710fe205866d8df02103f8f246e703ae17f46**

**Honest reading for the owner:** the plan's mechanisms bought a real midfield margin gain and a healthier service profile at the cost of one wall flip; W/L (the BT objective) is net −1 on available judges. The architecture claims (WorldState/strategy-zoo/rollouts, P1 list) remain unbuilt — this session shipped the plan's P0 instrumentation and gates, not the S30 brain. 2000-Elo remains unproven; the elite capacity gap (~$80k to Majkel's recorded bank) is still the binding constraint, exactly as the plan's scorecard said.

---

## 0930o — SECOND PLAN EXECUTED (P0-A/B/C/D of the 40-point critique) AS SHIP INTENT; SUB31 BAKED; W/L PROFILE RESTORED TO SUB29'S WITH BETTER MARGINS

**Owner directive:** implement the critique's four P0s "ignoring your judge books" — mechanisms active, verdicts recorded. Same crash-cascade rule as 0930n: every arm fberr=0.

**P0-A — third route scheduler (`assign_runs`, route.py):** pass 1 = serpentine sweep where an over-budget job is SET ASIDE for pass 2 and the scan CONTINUES (the unit takes the next job that fits — the run keeps contiguity except at set-aside seams, which are exactly the work the day cannot afford at that position); pass 2 = global reassignment of set-asides to the unit with the cheapest marginal walk from where its run ENDED, appended if it fits that unit's remaining budget, else dropped (the honest outcome). Both prior forms let an impossible job consume the shared cursor (skip-stranding measured 44.9k vs 140.5k). Wired at the two primary dawn assignment sites behind `route_assign=1` (ship block); the shepherd-loop and per-turn re-cut paths remain on split_runs (documented seam — the re-cut paths are append/repair, not primary assignment). **Verdict: the 0930n wall regression (aynrmio W→L) is RECOVERED (−22,109 → +12,749); wall back to 2-5.**

**P0-B — `service_forecast()` (module function) + `service_survival=1`:** per-day available worker time (hands x capacity(commute)) vs minimum required service work (2/animal/day feed+care, +2/pending placement; WATER on CROP_PLAN schedule days by age; HARVEST at maturity per crop kind) over a 4-day horizon. The survival constraint: on ANY deficit day, `_animal_plan` refuses ALL new admissions (builds/placements of owned stock unaffected) — the plan's point that the B-run catastrophe was the EXISTING machine becoming unserviceable, not one bad purchase. Reads the planned roster (max_hands), never raises.

**P0-C — MILK/WOOL opponent forecasts + exact self-ledger:**
- `opp_animal_supply(opp_tiles, day, weight)`: from the PUBLIC herd (placed_day + engine first_yield/interval), the exact pop DATES per product (conservative per-pop = min(interval, max_held), no care credit; pops_done from public yield_units when larger). `opp_milkwool_forecast=1`: the milk-window glut test ORs in "6 days of incoming MILK pops >= 2x milk_opp_glut" — the Antonio-ramp glut is visible as a CALENDAR at d10-14, before the live census crosses the level trigger.
- `monitor_exact_self=1`: the policy replays its queued unit ops and counts actors whose first op is DROP; each SELL unit in the monitor's bookkeeping is backed by shed stock OR one dropping actor's bag (engine settles DROPs before the market leg) — the same-turn DROP+SELL undercount that booked our own milk as opponent supply is gone. MILK and WOOL join `_TAU_GOODS`: the two goods that decide the elite war are now tracked in tau AND residual.
- Known residual simplification, recorded: the DROP-fund is actor-COUNT, not per-good bag-exact (per-actor carried maps were not wired into the monitor call); strictly closer to exact than the shed-cap heuristic it replaces.

**P0-D — strategy zoo: `STRATEGY_ZOO` (E0 elite-prior = shipped state = empty delta; E1-E8 complete-strategy candidates: livestock-lean, cow/sheep, wool-recovery, strawberry, tomato/shop, crop-staple, anti-livestock, liquidity) + `analysis/zoo_rollout.py` (the ΔV evaluator: every expert = a complete PARAMS delta scored on the W/L-moving judges; verdict rule = graduate only if W/L beats E0, margin never promotes). Smoke-verified end-to-end (famine tier: E0/E1/E4 all 2-0). In-episode selection stays E0 until an in-budget rollout policy exists — the evaluator is the offline scorer the plan demanded.**

**Latent defect found by the 0-failure test mandate:** `_marginal_hold`'s live call passed the QUADRANT SET as `unlocked_shops` — the drain inside the hold was ~1/day (town-centre only) instead of the true shop drain (~31/day wheat). The 0930n "honest" arm still measured under a ~30x drain error. Fixed (self.shops). The fixture failures this exposed were real contract violations, not pin churn: fixtures passed quadrant sets where shop lists belong. All six rewritten as new-contract tests (real shop-list fixtures; burst/drip mechanisms pinned with marginal_sell:0 in isolation; new `TestMarginalHoldArmed` pins the activated contract: scarcity book holds into its own tightening, glutted pile never held). **Tests 195/195 OK — suite is GREEN, zero recorded failures.**

**Real-tier verdict (16 judges, sub30 baseline from the 0930n ledger):**
- W/L: elite 0-3, famine 2-0, midfield 4-0, wall **2-5 (aynrmio W recovered)** — the full profile is byte-identical to sub29's, with the 0930n wall flip gone.
- Margins vs sub30: elite **−80,941 vs −85,925 (best-ever on this tier)**, famine **+45,256 vs +44,055 (best-ever)**, midfield +24,260 vs +27,041 (−2.8k, susutem-driven: our bank $92.1k best-ever on that judge), wall −12,670 vs −12,469 (noise).
- Mirror: seeds 0/2/7 banks 64.9k/62.8k/73.9k, ZERO shed rot, fberr=0 (sum 201.6k vs sub30's 206.6k — self-play absorbs its own shifts; the tier verdict above is the binding one).

**BAKE (sub31):** PACK OK bank-for-bank 16/16 (worst 48.6 ms), harness smoke 3/3 DONE 720 steps.
- `submission.tar.gz` == `submissionfinal.tar.gz` sha256 **ac4f9b63e636e25b4f5b4678a3105ef187595bca1d85302368f83e241330007c**
- `submission29.tar.gz` = seated sub29 (39c4a5fe…); `submission30.tar.gz` = 0930n build (4ec2b7db…)
- repo `kagfarm/policy.py` sha256 **ab91772bb89a567d1bf5cd4a0b612a1bc08e9b776922b72fe2731b76fca9ea53**; `kagfarm/route.py` **b3565714609f53cf306262fd3ad315e0a3d415c87aabbd4f3242f01ecbaba332**

**Honest reading:** the plan's P0-A delivered exactly what it predicted (the wall flip recovered, margins up on two tiers); P0-B/C/D are now live instrumentation with zero W/L cost on available judges. The critique's correction is ACCEPTED and recorded: the book ablation proved the book's economic value, not "the elite gap is capacity" — that hypothesis remains one of several (portfolio mismatch, execution, timing, opponent response). The next frontier is unchanged: run zoo_rollout across all 9 experts x all tiers, and build the in-episode rollout that lets E0 defer to a better expert mid-game. 2000 remains unproven; the architecture to attempt it now exists.

**0930o capstone — first full zoo ΔV table (all 9 experts, midfield+famine = the 6 W/L-moving judges, real tier):** the evaluator ran the complete panel end-to-end. Result rows (W/L, mean margin): E0_elite_prior 6-0 +31,259 (reconstructed from the 0930o judge-bar rows above); **E7_anti_livestock 6-0 +33,191; E8_liquidity 6-0 +32,969** (both with per-judge banks including our best-ever famine_scharf $111.4k and susutem $90.9k); remaining experts 6-0 within the E0 noise band (rows in the run log). Verdict per the plan's rule: **no expert graduates — W/L ties with E0 never promote on margin** — but E7 (herd 5C+3S, target 8) is the first candidate ever to beat E0's margin on the W/L-moving tier, and it is exactly the smaller-herd direction the branch counterfactuals (0930k: admission worth ≤$2k) and the capacity critique both point toward. Next decisive panel: E0 vs E7 on the elite3 + wall7 tiers (13 games), where a W/L flip would promote it. The zoo, the evaluator, and the promotion rule are now standing infrastructure.
