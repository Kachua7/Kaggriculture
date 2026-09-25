# Two-slot ladder A/B protocol

Written 25 Sep 2026 (ledger 0925j). Governs the final submission window: today is
D-5; the **final deadline is Wed 30 Sep 2026**; Kaggle tracks **only the latest 2
submissions**, and every submission plays ladder games overnight. The two latest
submissions are therefore a two-slot A/B rig by construction — this protocol makes
it deliberate.

## Why two slots, and why they should differ

Two identical submissions self-pair (measured: 110081520 — twin play, guaranteed
W+L, zero opponent information, zero rating EV). Two *different* builds halve that
waste: each game either one plays is evidence about *a* build, and the pair covers
2× the opponent diversity per day. Slot A never changes, so overnight Slot-B games
can never cost the pair its floor.

## The slots

| | Slot A — conservative | Slot B — experimental |
|---|---|---|
| Build | Current shipped artifact, `~/Downloads/submission14.tar.gz` sha256 `ecc00dc7…` (hf build, midfield judge bar 3W–1L, elite guard byte-exact −$37,243; payload byte-identical to the 0925i `7b2c238c…` archive — the sha changed only from tar-header nondeterminism on the 0925k repack) | One experimental arm per day, from the slot-B candidate list |
| Changes | **Never**, except one ordered migration below | Re-chosen once daily after reading results |
| Role | Floor + regression guard + rating accrual | Information: measures one idea against the real field |
| Risk | None (already proven on the bar) | Bounded: worst case it loses some games and dies that evening |

The only permitted Slot-A migration is at the final-week freeze (see stop rule): if
and only if a Slot-B build has met the promotion bar, Slot A is overwritten with the
winner **once**, ordered, then both slots hold it. One migration, not churn.

## Slot-B candidate list (what to try, in order)

Every candidate must first be **measured on the judge bar before it consumes a
slot-day** (`analysis/judge_bar.py --tier both --params '{"knob": v}'`): no dormant
knob carries a pre-registered positive expectation — all 0925a–0925i arms were
measured-rejected. Therefore Slot B's job is to measure the *unmeasured* gaps, in
this priority order (from the field autopsies, not from the falsified families):

1. **Day 1 (Fri 26 Sep) — the hf build itself.** Slot B = the promoted hf build
   (`sha 7b2c238c…`, the currently-live artifact). This is not redundant with
   Slot A-as-of-last-night: the ladder has only pre-hf games; tonight's pair is
   the **first real-field evidence of the hire-floor fix** (d2–9 one-hand trough,
   idle_steps ~40–43%). Read: does the trough disappear on the field?
2. **Day 2 — one pre-registered arm from the falsification ledger's "near-miss"
   arithmetic, at the smallest measured margin of safety.** The 0925g arithmetic
   says each midfield near-miss was ~40–50 strawberry units short. The live lever
   named there and never measured is **cohort sizing of the d13–19 strawberry
   cohort** (NOT sell timing — three families killed that). Concretely: one judge-
   bar pass on a modest acreage/seed-budget expansion for that cohort; if the bar
   shows ≥+$1k mean midfield W/L with no elite material regression, it becomes the
   Day-2 Slot-B arm; if the bar kills it, the day measures the runner-up below.
3. **Day 3+ — remaining structural candidates**, each judged the same morning:
   the `dawn_pace` mechanism re-test at a small pace (2–3/dawn) is the one dormant
   mechanism whose 0920 reject was measure-first honest but never re-tested at the
   current hire-floor cell; after it, the mid-game idle-recut family.
   Each candidate gets exactly one slot-day; a failed candidate is never retried
   unchanged.
4. **If no candidate survives the morning bar, Slot B repeats the previous best
   (hf build) rather than running a judged-rejected arm.** A known build on the
   field is worth more than a knowingly-worse arm: it widens the hf sample and
   risks nothing.

Rules: one candidate per slot-day; no compound arms (two knobs at once cannot be
attributed); any arm the morning bar kills is recorded as such in the ledger and
never re-armed without a new mechanism.

## The daily loop (run every morning through D-1)

1. **Collect.** Pull last night's replays from Kaggle for both submissions.
2. **Autopsy + fingerprint every tape** (`analysis/replay_autopsy.py`, then
   `calibration/fingerprint.py <replay.json>` — the runbook's step 4, now a daily
   gate, not a first-week ritual). Record per tape: opponent, W/L, build
   fingerprint, and the trough metric (d2–9 hires, idle_steps).
3. **Read the pair.** Slot A's games are the control series; Slot B's are the
   treatment series. Same-day same-field, seeds aside.
4. **Judge tomorrow's Slot-B candidate** on the two-tier bar (`analysis/judge_bar.py
   --tier both`). If it fails the promotion bar below, promote the next list item
   or repeat the current best.
5. **Submit** the chosen Slot-B build (and re-submit Slot A unchanged if the
   two-latest rule forces a re-up to keep it resident — see "The two-latest trap").
6. **Append one ledger line** to `calibration/live.md`: date, both slot builds
   (sha prefixes), per-tape W/L and fingerprint verdicts, the bar result for the
   new candidate, and tomorrow's Slot-B pick with its rationale.

**The two-latest trap:** submitting Slot B *replaces the older of the two
residents*. To keep Slot A resident and unaffected, **Slot A must be re-uploaded
after every Slot-B upload** (same bytes each time — that is what makes its series
a control). Order matters: B first, then A. If a day's upload quota or timing
forces a choice, Slot A's re-up wins — never let the conservative slot roll off.

## Promotion bar (evidence that promotes a Slot-B build over the shipped build)

Three conditions, ALL required. Evidence is cumulative across days; nothing is
decided on one night.

1. **Judge bar (pre-ladder gate), two tiers:** MIDFIELD tier W/L ≥ 3–1 with mean
   margin ≥ +$1k (i.e., no regression vs the 3W–1L / +$8,336 baseline), AND ELITE
   tier mean margin no worse than −$41k (≤ ~$4k material regression vs the
   −$37,243 guard). Elite W/L itself is not gating (BT prices elite losses ~0).
2. **Ladder evidence vs the field, same-opponent-class W/L:** across all
   accumulated Slot-B ladder games (its own games plus, where opponents overlap,
   head-to-head tape comparison), the Slot-B build's W/L record must be **no
   worse than Slot A's** against the same opponent bands (mid-field band
   −$9k–+$25k margins; structural band worse than −$38k), with **≥ 8 total
   field games** for the candidate build. If games are too few by freeze eve,
   the tie-break goes to the judge bar, not to vibes.
3. **No red-flag tape findings:** no `_safe_pass` signature (flat ~0.1 ms agent
   durations, no dawn spikes — the import-failure tell), no fingerprint verdict
   other than 1.32.7 EXACT on its tapes, no bank-collapse episodes (bank <$5k
   absent a catastrophic seed draw the p10 panel already covers).

On all three met at the freeze point: perform the one ordered Slot-A migration
(repack from the winning cell, full pre-flight: tests, `pack.sh` bank-for-bank,
`harness_smoke.py`, fingerprint of its first tape), copy to
`~/Downloads/submission14.tar.gz` (new sha, recorded), and upload to both slots.
Otherwise **Ship A unchanged** — after 0925a–0925i, "known 3W–1L midfield build"
beats any unmeasured change.

## Stop rule for the final week

- **D-2 (Mon 28 Sep) — candidate cutoff.** Last day a *new* candidate may enter
  Slot B. After this day, Slot B repeats the best-measured build only.
- **D-1 (Tue 29 Sep) — freeze.** If the promotion bar is met, perform the single
  ordered migration **this morning**, not the evening (each build needs one night
  of field evidence before the deadline; a migration uploaded D-1 evening has no
  tape evidence and is a blind bet). If the bar is not met, re-up the shipped
  build to both slots and stop.
- **Deadline day (Wed 30 Sep):** no new builds. Only re-uploads of the frozen
  best to both slots if the two-latest rule requires it. Any build that has not
  played at least one ladder game before the deadline is not eligible to be the
  frozen pick — which is exactly why the freeze decision happens D-1 morning.

## Pre-submission gate (every upload, unchanged)

`bash pack.sh` (bank-for-bank, $91,776 packaging panel) · tests green ·
`analysis/harness_smoke.py` (the exec-context gate) · fingerprint the first tape
of every uploaded build the next morning. Slot A is byte-stable, so its gate is
once — re-ups must carry the same *payload* (the recorded sha is `ecc00dc7…`; a
repack can move the archive sha via tar headers even with an identical payload,
so verify by payload diff, not by archive sha alone).

## Post-deadline principle (user directive, 25 Sep — REMEMBER THIS)

**Games keep being played after the submission window closes.** Rating does not stop at
the deadline: the two resident builds keep racking ladder games, so the terminal state
is whatever build sits resident with the best WIN RATIO in its neighborhood. Therefore:

- The freeze decision optimizes LONG-RUN resident win-rate, not last-moment rating.
  A build that wins its band forever outranks a slightly-higher-rated build that
  plateaus — 3000, if it comes, accrues AFTER the deadline via sustained W/L.
- The final shipped build should be the best-measured W/L build at deadline, and any
  v2 continuous-economy work that matures later can replace it ONLY if it passes the
  same promotion bar on the two-tier bar first.
- 3000 by Sep 30 is not the goal; 3000 EVER is. The two-slot rig's job is to leave the
  highest-win-ratio agent resident when uploads close, then keep feeding it games.

## Relationship to existing docs

- `LADDER_RUNBOOK.md` keeps the submission mechanics (step 1–4) and the original
  fingerprint decision rule; this file governs *which builds* ride the two slots
  and when to stop.
- `calibration/live.md` (0925a…0925j) holds the falsification ledger; every Slot-B
  candidate must cite its ledger entry or its morning-bar result before arming.
