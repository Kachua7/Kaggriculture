"""Kaggle submission entry point. `agent(obs)` is the only thing the harness calls.

Everything of substance lives in `kagfarm/`. This file does three jobs and no more:

  Make the import work wherever the harness unpacks the tarball. The sandbox does not put
  the submission root on `sys.path` reliably, so the package directory is added explicitly
  relative to this file rather than to the process CWD.

  Hold one `Policy` per player index. The harness may run both seats in one process during
  its own validation episode, and a `Policy` carries a day's routing plan as mutable state
  -- sharing one instance between seats would hand player 1 player 0's queues.

  Never raise. A raise, or a turn over `actTimeout` (1s), forfeits the episode outright, so
  a bug on day 3 costs the whole 30 days instead of one turn. `Policy.act` already wraps
  itself; this is the outer belt that also covers a failed import or a malformed `obs`.
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_POLICIES = {}
_BROKEN = None

try:
    from kagfarm.policy import Policy
except Exception as _e:                        # pragma: no cover - sandbox import failure
    Policy = None
    _BROKEN = repr(_e)


def _safe_pass(obs):
    """The least-bad legal action: do nothing, but with the right number of hands.

    `hands` has to match the roster length or the engine may reject or mis-apply the whole
    action, so even the give-up path has to read the observation.
    """
    n = 0
    try:
        me = (obs.get("farms") or [])[obs.get("player", 0)]
        n = len(me.get("hands") or [])
    except Exception:
        pass
    return {"farmer": ["PASS"], "hands": [["PASS"]] * n, "market": []}


def agent(obs, config=None):
    if Policy is None:
        return _safe_pass(obs)
    try:
        seat = obs.get("player", 0)
        # A fresh episode restarts the clock; `plan_day` running backwards is the signal.
        pol = _POLICIES.get(seat)
        if pol is None or obs.get("day", 0) < pol.plan_day:
            pol = _POLICIES[seat] = Policy()
        return pol.act(obs)
    except Exception:
        return _safe_pass(obs)


# Some Kaggle simulation harnesses look for a callable named after the file, others for a
# module-level `agent`. Exposing both costs nothing.
kagfarm_agent = agent
