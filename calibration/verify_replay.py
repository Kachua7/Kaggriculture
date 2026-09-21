"""Golden check: does the vendored engine source reproduce a recorded episode, step for step?

Re-simulates a replay JSON (Kaggle episode format: `steps[t][player] = {action, observation,
reward, status}`) by feeding each recorded action into the interpreter of THIS repo's vendored
engine source, then diffs the engine's own state against the recorded observations at every
step. This is the gate A3 panels sit behind: a comparison table between the mirror and a real
engine is only evidence if that engine provably replays a real episode exactly.

The mined tutorial replay (calibration/real_engine/tutorial_episode.json) was recorded on
kaggle-environments 1.32.2 — its runtime config says townCenterSellInterval=12 and its shop
sequence is a permutation, both of which match 1.32.2 and contradict the 1.32.7 defaults.
So the default engine dir here is calibration/engine-1.32.2 (kept for exactly this purpose).
Point --engine-dir at calibration/engine to replay a 1.32.7-era ladder replay, or to watch
this tutorial replay diverge (expected, from the first re-drawn shop on day 6).

Runs under .venv/bin/python — the vendored module imports kaggle_environments.utils for
resolve_episode_seed, and .venv holds the pinned install.

Usage:
  .venv/bin/python calibration/verify_replay.py
  .venv/bin/python calibration/verify_replay.py --engine-dir calibration/engine <replay.json>

Exit 0 iff every step of every compared field matches exactly (floats to 1e-6).
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys

DEFAULT_REPLAY = os.path.join(os.path.dirname(__file__), "real_engine", "tutorial_episode.json")
DEFAULT_ENGINE_DIR = os.path.join(os.path.dirname(__file__), "engine-1.32.2")
# Canonical names used by fingerprint.py: the replay-matched 1.32.2 copy and the pinned
# 1.32.7 wheel extraction.
ENGINE_DIR_1322 = DEFAULT_ENGINE_DIR
ENGINE_DIR = os.path.join(os.path.dirname(__file__), "engine")

# The fields the interpreter owns, per player. `step` and `remainingOverageTime` are
# framework-managed (the interpreter never writes them), so they are not compared.
COMPARE_KEYS = ("day", "hour", "player", "market", "town", "farms", "private")


class Struct:
    """Attribute wrapper: the engine writes obs.farms etc. as attributes, and reads
    configuration both by attribute (`cfg.episodeSteps`) and via its dict-or-obj `get`."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def load_engine_module(engine_dir: str):
    py = os.path.join(engine_dir, "kaggriculture.py")
    name = "kaggriculture_vendored"
    spec = importlib.util.spec_from_file_location(name, py)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm(x):
    """Normalize for exact comparison: ints/floats to rounded floats, dicts key-sorted."""
    if x is None or isinstance(x, (str, bool)):
        return x
    if isinstance(x, (int, float)):
        return round(float(x), 6)
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [norm(v) for v in x]
    return str(x)


def diff_paths(a, b, path="$", out=None):
    """Collect JSON paths where two normalized structures disagree (bounded output)."""
    if out is None:
        out = []
    if len(out) >= 12:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((f"{path}.{k}", "<missing>", a.get(k, b.get(k))))
            else:
                diff_paths(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}[]", f"len {len(a)} vs {len(b)}", (a[:3], b[:3])))
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))
    return out


def resimulate(replay: dict, engine_dir: str, max_reports: int = 0):
    """Re-simulate a replay dict on one vendored engine dir.

    Returns (exact, failed, first_bad) where first_bad is a list of
    (step, player, [(json_path, recorded, live), ...]) detail reports. This is the
    authoritative version discriminator: an episode replays exactly under exactly one
    mechanics set, so fingerprint.py runs it against every vendored candidate.
    """
    steps = replay["steps"]
    n_steps = len(steps)
    players = len(steps[0])
    eng = load_engine_module(engine_dir)

    env = Struct(configuration=Struct(**replay["configuration"]),
                 done=False,
                 info=dict(replay.get("info") or {}))
    state = []
    for p in range(players):
        # DEEP-COPY the seeded observation: the interpreter mutates the nested farms/market/
        # town/private dicts in place, and they would otherwise be the replay's own step-0
        # objects — silently corrupting the recording for every caller that reuses it
        # afterwards (fingerprint.py runs resimulate, then reads heuristic rows off the
        # same steps list).
        obs = Struct(**copy.deepcopy(steps[0][p]["observation"]))
        state.append(Struct(action=None, observation=obs, status="ACTIVE", reward=0, info={}))

    # Replay alignment (verified empirically): steps[t][p].action is the action that
    # PRODUCED steps[t][p].observation from steps[t-1]'s state — steps[0] is the initial
    # observation with a placeholder action. So: seed state from steps[0], then for each t
    # feed action@t and compare the interpreter's output against steps[t].
    exact = 0
    mismatched = 0
    first_bad = []
    for t in range(1, n_steps):
        # The interpreter reads obs0.step but never writes it (framework-managed). The
        # engine processes step N and emits the observation for N+1, and action@t produced
        # obs@t — so it must process t-1 here.
        state[0].observation.step = t - 1
        for p in range(players):
            act = steps[t][p].get("action")
            state[p].action = act if act is not None else {}
        eng.interpreter(state, env)
        ok = True
        for p in range(players):
            live = {k: norm(getattr(state[p].observation, k)) for k in COMPARE_KEYS}
            rec = {k: norm(steps[t][p]["observation"].get(k)) for k in COMPARE_KEYS}
            if live != rec:
                ok = False
                if len(first_bad) < max_reports:
                    first_bad.append((t, p, diff_paths(rec, live)[:12]))
        if ok:
            exact += 1
        else:
            mismatched += 1
    return exact, mismatched, first_bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay", nargs="?", default=DEFAULT_REPLAY)
    ap.add_argument("--engine-dir", default=DEFAULT_ENGINE_DIR)
    ap.add_argument("--max-reports", type=int, default=3, help="steps to print in detail")
    args = ap.parse_args()

    with open(args.replay) as f:
        replay = json.load(f)
    n_steps = len(replay["steps"])

    exact, mismatched, first_bad = resimulate(replay, args.engine_dir, args.max_reports)

    print(f"replay : {args.replay}")
    print(f"engine : {args.engine_dir}")
    print(f"steps  : {n_steps - 1} transitions compared across {len(replay['steps'][0])} players")
    print(f"exact  : {exact}/{n_steps - 1}")
    print(f"failed : {mismatched}/{n_steps - 1}")
    for t, p, ds in first_bad:
        print(f"\nfirst divergence at step {t}, player {p}:")
        for path, rec_v, live_v in ds:
            print(f"  {path}\n    recorded: {rec_v}\n    live    : {live_v}")

    if mismatched == 0:
        print("\nGOLDEN PASS — the vendored engine reproduces this episode exactly.")
        return 0
    print("\nGOLDEN FAIL — engine source does not reproduce the recording (see paths above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
