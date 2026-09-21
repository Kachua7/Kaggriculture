# Kaggriculture agent — "kagfarm"

A deterministic rule-based agent for [Kaggriculture](https://www.kaggle.com/competitions/kaggriculture),
Kaggle's 1v1 economic farming simulation (30 days × 24 turns; terminal bank wins).

The bot plays a three-engine economy — a serviced livestock herd (cows/sheep), a
capped premium crop cohort (melons/strawberries), and a wheat feed backbone — with
every decision priced off a calibrated model of the engine's market and biology.

## Layout

```
main.py                  entry point: kaggle_environment agent (per-seat Policy instances)
kagfarm/
  policy.py              the agent: planning, livestock, market, routing (the whole brain)
  constants.py           engine tables + strategy tunables (PARAMS)
  route.py               deterministic unit routing (serpentine + shepherd loops)
tests/test_policy.py     90 unit tests: engine fingerprints, gates, regressions
engine.py                independent mirror simulator (documented-rules reimplementation)
agents.py                baseline agents + replay-judge manifest
replay_opp.py            replay-opponent sparring partners (verbatim market tapes)
analysis/                probes, funnels, A/B panels, autopsies (one script per question)
calibration/             real-engine calibration: verifiers, dossier, decision ledger
bridge/real_env.py       runs the agent against the real kaggle-environments engine
bundle.py / pack.sh      build the single-file competition submission, verified
submit.sh                pack + submit to the ladder
```

## Quick start

```bash
bash bootstrap.sh        # optional: create .venv + vendor the real engine for calibration
python3 -m unittest discover -s tests            # 90-test regression gate
python3 run_demo.py --p0 main --p1 heuristic --steps 720 --seed 1   # mirror episode
```

Run the agent against a real recorded opponent (judge on its recorded seed):

```bash
python3 analysis/restore_replays.py --scan --download   # fetch judge tapes (multi-GB)
.venv/bin/python analysis/ab_panel.py --opps replay_majkel3
```

Build a submission: `bash pack.sh` (builds `submission.tar.gz` and proves the archive
plays the agent that was measured).

## Design notes

- **Engine-exact modeling.** Animal yields, care-bank pops, `max_held` clipping, spawn
  tiles, and market settlement are mirrored from the vendored engine source, not
  assumed. Where the mirror and the real engine disagreed, the real engine won.
- **Settlement-based state.** Purchase plans track what the engine *settled*, not what
  was ordered — failed or slot-truncated orders retry automatically.
- **Everything is a tunable.** Strategy parameters live in `PARAMS` (constants.py),
  overridable per-run via `KAG_OVERRIDE` for sweeps and A/B panels.
- **Decisions are logged.** `calibration/live.md` is the ledger: every change records
  the evidence that motivated it and the measured verdict that accepted or rejected it.

## License

MIT — see [LICENSE](LICENSE).
