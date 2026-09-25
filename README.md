# Kaggriculture

A Bradley-Terry-optimized agent for the Kaggle **Kaggriculture** simulation competition
(Sep 2026). Engine-exact against the pinned kaggle-environments 1.32.7 wheel; measured
on a replay-judge panel built from real ladder tapes.

**Current artifact: `submission17`** — sha256 `3e1c0b38968686d58892a805868591069422ed53e95b66fedf467de1df0d7093`.

## Measured state (25 Sep 2026)

| tier | shipped (sub14-class) | submission17 |
|---|---|---|
| midfield judges (W/L-first) | 3-1, mean +$8,336 | **3-1, mean +$11,055** |
| elite judges (guard) | 0-5, mean -$37,243 | **0-5, mean -$37,057 (best ever)** |

Field: 8-12 in the first 20 ladder games (submission15 build) — clean sweep of the
sub-535 band, losses concentrated in the 541-650 band, decided by a d8-15 income stall.

## The three levers shipped in 17 (all judge-bar cleared)

1. **windfall_pct 0.50** — funds the d13-19 strawberry cohort (the near-miss arithmetic:
   each midfield loss was ~40-50 units short). Tâm judge +$38,240, best single margin
   ever measured.
2. **mix MELON 24→17** — frees ~$350 of the day-0 round for the elite opening script's
   t2 sheep (dossier: Majkel orders sheep at t2; wool is his only W/L-separating line).
3. **wheat_drip 6** — the winners' heartbeat: they sell 14-71 wheat units EVERY day
   (per-day curve autopsies of 426 top-10 games); ours pooled 12 days/mouth of feed
   bridge in the shed. Drip=6 shrinks the bridge; surplus flows through the $27.5
   reserve floor (crater-proof); BUY_PRODUCT fallback re-buys.

## What got falsified along the way (all two-tier judge bar, all REJECTED)

Herd scale (16/22-head cells: catastrophic without a service loop), elite wage cadence
(8 hires/day unfunded: elite -$86k), sell-side timing/metering x3, opponent
conditioning, post-crash holding, opponent-aware planting, early milk window. Full
falsification ledger: `calibration/live.md` (0925a-0925n), including the top-10 corpus
decomposition (426 games profiled: within-tier outcomes decided by d20 bank presence,
not labor quantity; wool separates only 3/7 teams).

## Repo map

- `main.py` + `kagfarm/` — the agent (constants/route/policy; opening_book optional)
- `engine.py` — local mirror engine (source-exact semantics, H1-H3 audits)
- `calibration/` — `live.md` (the ledger of record), `fingerprint.py` (daily engine
  verdict from any replay), `verify_replay.py` (719/719 golden check), `majkel_dossier.md`
- `analysis/` — `judge_bar.py` (two-tier W/L bar), `top10_scan/profile/curves` (daily
  episode-dataset pipeline), `ab_panel.py` + `replay_opp.py` (replay-judge panel),
  `harness_smoke.py` (the exec-context gate that catches import deaths), ~50 measured
  probes
- `LADDER_AB_PROTOCOL.md` — the two-slot ladder A/B protocol + post-deadline principle
- `LADDER_RUNBOOK.md` — submission mechanics + fingerprint decision rule
- `OPEN_QUESTIONS.md` — 41 open questions ranked by expected value
- `pack.sh` / `bundle.py` / `verify_pack.py` / `submit.sh` — artifact build + verification

## Build & verify

    bash pack.sh                     # builds + bank-for-bank-verifies submission.tar.gz
    python3 -m unittest discover -s tests -q    # 141 tests
    .venv/bin/python analysis/harness_smoke.py submission.tar.gz   # exec-context gate
    .venv/bin/python analysis/judge_bar.py --tier both              # the W/L bar

The policy is deterministic given a seed; the pack gate compares the unpacked archive
against the repo build bank-for-bank ($91,400 packaging panel for 17).
