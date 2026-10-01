# Ladder submission runbook

Everything before step 1 is already done and gated (tests, pack, bundle, A3, real-tier
replication). This file exists because the ONLY remaining calibration question —
which engine version the ladder actually runs — is answered by a replay, and the
replay only exists after a submission. Do the steps in order; do not skip 4.

**Final window (25–30 Sep 2026):** which builds ride the two tracked submission slots,
the daily collect/autopsy/judge loop, and the freeze rule are governed by
`LADDER_AB_PROTOCOL.md` (ledger 0925j). This file keeps the mechanics: upload commands,
replay retrieval, fingerprint decision rule (step 4 — now run on EVERY tape daily, not
just the first).

## The exec-context rule (learned 2026-09-17, non-negotiable)

The harness does NOT import `main.py` as a module. `kaggle_environments.agent
.get_last_callable` **exec's the source** with a bare globals dict, where `__file__` is
undefined — referencing `__file__` anywhere at module level raises NameError at exec time,
which surfaces as `InvalidArgument` and **ERRORs every episode** (both seats, reward None,
empty logs). All import-context gates (verify_pack, bundle, tests) import `main` as a real
module, where `__file__` exists, so they cannot catch this. `main.py`'s `_locate_root()` is
`__file__`-independent (NameError-tolerant, sys.path scan — the harness appends the
submission dir to sys.path before exec) and `analysis/harness_smoke.py` runs the exact tar
bytes through `kaggle_environments.make` to pin it. Never reintroduce a bare `__file__`
outside `_locate_root`'s try block, in any file that ships. Related: obs/config arrive as
`utils.Struct`, which subclasses `dict` — `.get`/`[]` work unchanged (proved by the same
smoke, P0.1 of PRE_SUBMIT_CHECKLIST).

## 0. Pre-flight (all four must be green)

```
python3 -m unittest discover -s tests -q        # 36 tests, OK
bash pack.sh                                    # PACK OK, bank-for-bank vs repo
python3 bundle.py                               # BUNDLE OK (single-file fallback)
/Users/pranjalmorwal/Desktop/kaggriculture/.venv/bin/python calibration/a3_compare.py
# The only gate that replays the submission path the ladder actually uses:
/Users/pranjalmorwal/Desktop/kaggriculture/.venv/bin/python analysis/harness_smoke.py
```

`harness_smoke.py` is non-optional since 2026-09-17: it runs the exact tar bytes through
`kaggle_environments.make` (exec context, Struct obs) and is the only check that catches
exec-context failures — see "The exec-context rule" above.

`submit.sh` refuses to run without `bootstrap.sh` having created `.venv` (that is where
the kaggle CLI lives) and re-runs `pack.sh` itself.

## 1. Submit

From the ORIGINAL checkout (`~/Desktop/kaggriculture`, where `.venv` exists) or here after
`bash bootstrap.sh`:

```
bash submit.sh "windfall cap + spawn fix, monitor off"
```

That uploads `submission.tar.gz` (the verified package build). If Kaggle rejects the
tarball layout, `bash submit.sh "..." single` uploads the flattened file — do not start
debugging, the two are byte-verified to play identically.

## 2. Get the replay

When the submission finishes scoring (Kaggle shows the episode link on the submission
page), download the replay JSON:

```
kaggle competitions submissions kaggriculture      # find the submission id
kaggle competitions episodes -h                    # or grab the replay link from the page
```

Save it as `calibration/replays/first.json` (create the directory if needed).

## 3. Read the scoreboard before anything else

- If the episode banked ≈ the sanity-panel numbers for its opponent mix, the submission
  pipeline itself is healthy.
- If it banked a few hundred dollars, `main.agent` fell back to `_safe_pass` in the
  sandbox — that is an import failure INSIDE Kaggle, and the fix is in packaging, not
  policy. Compare the archive against `pack.sh`'s stage list first.

## 4. Fingerprint the replay (the reason for steps 1–3)

```
/Users/pranjalmorwal/Desktop/kaggriculture/.venv/bin/python \
    calibration/fingerprint.py calibration/replays/first.json
```

Decision rule, pre-committed:

- **EXACT under 1.32.7** → constants stay as tagged. The calibration programme is
  complete; freeze and let rating accrue.
- **EXACT under 1.32.2** → re-tag from `calibration/engine-1.32.2`, re-run the A3/A5
  gates on the re-tagged build (the shop-draw lottery and three price curves change),
  and re-submit. Until then the current constants are tuned for the wrong game.
- **EXACT under neither** → the ladder config overrides something (the fingerprints
  print which rows matched). The monitor's `d` diagnostic and
  `analysis/monitor_truth.py` are the offline tools for separating a config override
  from a mechanics difference. Known weak spot: a town-centre-interval-only override
  is invisible to `d` (measured d≈1.02); fit tau and the intervals from the replay JSON
  directly in that case.

## 5. Record it

Append the verdict to `calibration/live.md` (one line: replay, verdict, action taken),
and the version ledger in `AGENTS.md` if it contradicts the 1.32.7 tag.

## Post-submit (added 2026-09-19): fingerprint the ladder engine

1. `kaggle competitions submit kaggriculture -f submission.tar.gz -m "<tag>"`
2. Wait for the first episode to process, then pull a replay JSON:
   `kaggle competitions episodes <submission-id>` (or download from the episode viewer).
3. Fingerprint the engine from the replay (engine version, townCenterSellInterval,
   per-good lockstep quoting) against calibration/engine-1.32.2 vs -1.32.7.
4. If it is NOT 1.32.7: re-open calibration/live.md "re-baseline the mirror" before
   trusting any local gate. If it is: freeze; do not reopen closed axes.
