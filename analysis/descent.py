"""Resumable coordinate descent, because this sandbox cannot run a long job.

Every shell call here is its own PID namespace under `bwrap --die-with-parent --unshare-pid`, so a
backgrounded `sweep.py` dies the moment the call that launched it returns. Measured twice: a
`nohup`'d run logged 80 lines and froze mid-round-1, a `setsid`'d relaunch logged 8. There is no
detach, and each call is capped near two minutes. A 70-evaluation self-play descent takes ~96s of
compute, three rounds take five minutes, and that simply does not fit in one call.

So this is `sweep.py`'s descent with a wall clock and a state file. Each invocation evaluates as
many cells as fit in `--budget` seconds, then exits 0 printing either RESUME or DONE; call it again
until it says DONE. **State is written after every single evaluation**, so a kill costs one cell
rather than a round -- which is the whole reason this exists as a separate tool instead of a flag
on `sweep.py`.

The scoring, the axis lists, and the veto on errors and budget breaches all come from `sweep.py`
unchanged, so a descent run here is the same descent, only interruptible. The holdout is not
optional and is a separate mode below: this walks one axis at a time over a 48-episode panel, which
is exactly enough resolution to fit the panel.

    python3 analysis/descent.py --init --seeds 48 --opps self --objective wins --rounds 3
    python3 analysis/descent.py --budget 100          # repeat until DONE
    python3 analysis/descent.py --holdout 96          # then this, on seeds it never saw
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sweep import AXES, score, _fmt, holdout as sweep_holdout   # noqa: E402
from kagfarm.policy import PARAMS                               # noqa: E402


def load(path):
    with open(path) as fh:
        return json.load(fh)


def save(path, st):
    """Atomic, because a kill mid-write would lose the whole descent rather than one cell."""
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh, indent=1)
    os.replace(tmp, path)


def init(path, a):
    axes = [x for x in a.axes.split(",") if x in AXES]
    for ax in axes:                       # the bug that silently regressed `endgame_days`
        assert PARAMS[ax] in AXES[ax], "%s: incumbent %r not in candidate list" % (ax, PARAMS[ax])
    st = {"cfg": {"seeds": a.seeds, "start": a.start, "opps": a.opps.split(","),
                  "objective": a.objective, "rounds": a.rounds, "workers": a.workers},
          "axes": axes, "cell": {k: PARAMS[k] for k in axes}, "score": None,
          "round": 0, "ai": 0, "vi": 0, "changed": False, "evals": 0, "log": [], "done": False}
    save(path, st)
    print("init %d axes, %d seeds x %s, objective=%s, %d rounds"
          % (len(axes), a.seeds, ",".join(st["cfg"]["opps"]), a.objective, a.rounds))
    return st


def _score(st, cell):
    c = st["cfg"]
    return list(score(cell, range(c["start"], c["start"] + c["seeds"]),
                      c["opps"], c["workers"] or None, c["objective"]))


def _emit(st, line):
    st["log"].append(line)
    print(line)


def step(path, budget):
    """Evaluate cells until `budget` seconds are up, saving after each one."""
    st = load(path)
    obj = st["cfg"]["objective"]
    if st["done"]:
        print("DONE  %s  %s" % (_fmt(tuple(st["score"]), obj), json.dumps(st["cell"])))
        return st
    t0 = time.monotonic()
    if st["score"] is None:
        st["score"] = _score(st, st["cell"])
        st["evals"] += 1
        _emit(st, "start %s" % _fmt(tuple(st["score"]), obj))
        save(path, st)
    while time.monotonic() - t0 < budget:
        if st["round"] >= st["cfg"]["rounds"]:
            st["done"] = True
            break
        axis = st["axes"][st["ai"]]
        if st["vi"] >= len(AXES[axis]):
            st["ai"] += 1
            st["vi"] = 0
            if st["ai"] >= len(st["axes"]):
                _emit(st, "round %d done: %s  (%d evals)"
                          % (st["round"], _fmt(tuple(st["score"]), obj), st["evals"]))
                if not st["changed"]:
                    st["done"] = True
                    break
                st["round"] += 1
                st["ai"] = 0
                st["changed"] = False
            save(path, st)
            continue
        val = AXES[axis][st["vi"]]
        st["vi"] += 1
        if val == st["cell"][axis]:
            save(path, st)
            continue
        s = _score(st, dict(st["cell"], **{axis: val}))
        st["evals"] += 1
        flag = ""
        if tuple(s) > tuple(st["score"]):
            st["cell"] = dict(st["cell"], **{axis: val})
            st["score"], st["changed"], flag = s, True, "  <-- best"
        _emit(st, "  %-12s = %-6s  %s%s" % (axis, val, _fmt(tuple(s), obj), flag))
        save(path, st)
    save(path, st)
    tag = "DONE " if st["done"] else "RESUME"
    print("%s round %d/%d axis %d/%d  %s  %d evals, %.0fs this call"
          % (tag, st["round"], st["cfg"]["rounds"], st["ai"] + 1, len(st["axes"]),
             _fmt(tuple(st["score"]), obj), st["evals"], time.monotonic() - t0))
    if st["done"]:
        moved = {k: v for k, v in st["cell"].items() if v != PARAMS[k]}
        print("moved off incumbent: %s" % json.dumps(moved, indent=2))
    return st


def run_holdout(path, n):
    """Re-score the winner, and each of its moves alone, on seeds the descent never touched.

    Delegates to `sweep.holdout`, so the per-axis attribution is the same table a `sweep.py` run
    prints. The seeds start where the tuning panel ended, which is the only property that matters.
    """
    st = load(path)
    c = st["cfg"]
    first = c["start"] + c["seeds"]
    rows = sweep_holdout(st["cell"], range(first, first + n), c["opps"],
                         c["workers"] or None, c["objective"])
    st["holdout"] = [[t, list(v)] for t, v in rows]
    st["holdout_seeds"] = [first, first + n]
    save(path, st)
    return rows


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="analysis/descent.json")
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--budget", type=float, default=95.0,
                    help="wall-clock seconds to spend this call; the harness caps a call near 120")
    ap.add_argument("--holdout", type=int, default=0,
                    help="run the holdout on this many unseen seeds instead of descending")
    ap.add_argument("--log", action="store_true", help="dump the accumulated log and exit")
    ap.add_argument("--seeds", type=int, default=48)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--opps", default="self")
    ap.add_argument("--axes", default=",".join(AXES))
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--objective", default="wins", choices=("mean", "wins"))
    ap.add_argument("--workers", type=int, default=0)
    a = ap.parse_args()
    path = a.state if os.path.isabs(a.state) else os.path.join(_ROOT, a.state)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if a.init:
        init(path, a)
        return
    if a.log:
        st = load(path)
        print("\n".join(st["log"]))
        return
    if a.holdout:
        run_holdout(path, a.holdout)
        return
    step(path, a.budget)


if __name__ == "__main__":
    main_cli()
