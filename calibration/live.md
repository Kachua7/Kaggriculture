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
