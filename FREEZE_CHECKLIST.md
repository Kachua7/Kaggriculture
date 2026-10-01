# FREEZE CHECKLIST — submission17 → both slots (Tue Sep 29, morning)

Ship artifact: `submission17.tar.gz` — sha256 `3e1c0b38…` (verified 0927, do NOT repack).
Slot B candidates (owner picks; strongest harness numbers win):
- `submission20.tar.gz` — sha256 `34d4de74…` — **the census clone + melon₀ fix**
  (ship block: `majkel_skeleton()` + `seed_opening_cap=900`). Strongest measured
  build of the cycle: wall mean −$23,378 (new best ever), midfield 4W-0L
  +$19,980, paired vs shipping sub19 **20W-4L (0.833)**. Ladder-verified shape:
  hires 284, land 2.6 spread, herd peak 14, wheat ~820/game.
- `submission18.tar.gz` — sha256 `fd9c15ac…` (v2 surge: `replant_idle=1,
  hire_surge_day=10, hire_surge_n=12`; paired 72W-0L vs the v1 incumbent; wall mean
  −$31,568, midfield 3W-1L flat).
Superseded: `rpidle_candidate.tar.gz` `d2cffa65…` (v1, was resident at 466.6);
`rw1_candidate.tar.gz` `8a0d857d…` (paired wash — do not use).
BOTH conditional artifacts upload ONLY per the branch below.

## Step 0 — CONFIRMED (Sep 27, screenshot of discussion 739410)
Addison Howard (Kaggle staff): "The team score is based on the better of its
two submissions (a team can't occupy two ranks). The second slot can be viewed
as a hedge with no downside." Ties = half wins. Play rate post-deadline:
hoped to increase, no commitments. => **Execute Step 3B.**

## Step 1 — Monday morning: field pull (automated)
```
.venv/bin/python analysis/morning_pull.py
```
Expected healthy state: sub17 mean ≈ +$631, 540-600 weak (0W-10L is KNOWN —
do not panic on this line), last-10 ≥ 3W. Any NEW flag (≥-$60k margin in the
last 6, 500-540 turning red, last-10 ≤ 2W) → investigate before freezing:
pull the tape, run `analysis/telemetry_dump.py` on it, compare to the known
signature (d14-24 deficit, BUY_SEED 5-10x). A NEW signature is the only thing
on earth that reopens the freeze.

## Step 2 — Monday: verify the artifacts one last time
```
shasum -a 256 submission17.tar.gz          # must start 3e1c0b38
shasum -a 256 submission18.tar.gz          # must start fd9c15ac
shasum -a 256 rw1_candidate.tar.gz         # must start 8a0d857d (only if used)
```
Hash moved = DO NOT UPLOAD; re-verify against the repo or rebuild from git.

## Step 3A — FALLBACK ONLY (rule were "both count" — it is NOT)
If ever needed: two sub17 uploads, B first then A re-up. CURRENTLY INACTIVE:
the rule is confirmed better-of-two, so Step 3B applies.

## Step 3B — DONE through sub20; sub21 is the pending Slot B upgrade
1. sub20 IS SEATED in Slot B (ref 56617155). Ladder read (39 tapes, 0929,
   see calibration/live.md): melon₀ = 8.0 every game ✓, hires 280 ✓,
   herd peak 13 ✓, land 2.9 ✓ — the census signature landed. Wall NOT
   narrowed (600-800 0W-7L −$60.4k). NEW finding: 2 of 39 games (5%) died
   of roster desertion at the d4 dawn (d3 $0 → wages unpaid) — the famine
   failure mode, −$75k mean.
2. **`submission22.tar.gz` (sha256 `bd45fd3b…`, 145,327 B) is the strongest
   measured Slot B candidate** = sub21 + turn_allocator=1 (the 0929 wall
   graft). Wall mean −$22,619 → −$18,514, worst tail −$47.6k, 5/7 tapes
   improve; midfield 4W-0L +$19,838; famine tapes 1W-1L +$14,445; paired
   12 seeds 15W-9L. Supersedes `submission21.tar.gz` (sha256 `56fecee8…`,
   the famine guard alone). Upload the best available over sub20 in Slot B
   (Slot A sub17 never touched); famine_wage_frac=0 reverts byte-identical.
3. Slot A stays sub17 (the proven build is the team score; never touched).

## Step 4 — Tuesday: verify residency, then hands off
- `.venv/bin/python analysis/morning_pull.py` one last time.
- Episodes attribute to the CURRENT slots: after the re-up, new games are
  sub17-vs-field in both seats. Seat-0 bias is known (65% vs 41%) — expected.
- No further uploads after the freeze unless a catastrophe is measured AND a
  fix exists that passes the paired harness + wall tier + elite guard.

## Standing facts (do not re-litigate)
- 540-600 wall: class-wide disease, 0W-10L on sub17, 500-540 is 5W-2L (fine).
- Elite games: sub17 2W-0L at 800+ — the build scales UP, not down.
- Every measured candidate (alloc1, wheel_fallback, dawn_pace, pace+floor,
  rw1) is either rejected or a wash. sub17 is the best-measured cell, n=35,
  mean +$631. The freeze is a positive decision, not a default.
