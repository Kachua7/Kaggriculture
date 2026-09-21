"""Kaggle submission entry point. `agent(obs)` is the only thing the harness calls.

Everything of substance lives in `kagfarm/`. This file does three jobs and no more:

  Make the import work wherever the harness unpacks the tarball. The harness does NOT
  import this file as a module -- `kaggle_environments.agent.get_last_callable` exec's the
  SOURCE with a bare globals dict, so `__file__` is undefined here and referencing it
  anywhere at module level DQs every episode with a NameError (found by the pre-submit
  harness smoke, 2026-09-17). The locator below is __file__-independent: in exec context
  the harness appends the submission directory to sys.path before exec, so scanning
  sys.path for the kagfarm package finds it; the __file__ branch is kept for real module
  imports (verify_pack, tests); CWD is the last resort.

  Hold one `Policy` per player index. The harness may run both seats in one process during
  its own validation episode, and a `Policy` carries a day's routing plan as mutable state
  -- sharing one instance between seats would hand player 1 player 0's queues. A fresh
  episode is detected by the clock running backwards and rebuilds both policies.

  Never raise. A raise, or a turn over `actTimeout` (1s), forfeits the episode outright, so
  a bug on day 3 costs the whole 30 days instead of one turn. `Policy.act` already wraps
  itself; this is the outer belt that also covers a failed import or a malformed `obs`.
"""

from __future__ import annotations

import os
import sys


def _locate_root():
    """Directory containing the kagfarm package, without ever touching __file__ blindly."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))    # real module import context
        if os.path.isfile(os.path.join(here, "kagfarm", "policy.py")):
            return here
    except NameError:
        pass                                                  # exec'd source: no __file__
    for cand in sys.path:                                     # harness exec context
        try:
            if cand and os.path.isfile(os.path.join(cand, "kagfarm", "policy.py")):
                return cand
        except Exception:
            pass
    return os.getcwd()


_HERE = _locate_root()
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_POLICIES = {}
_BROKEN = None


def _import_policy():
    """Import OUR kagfarm package, not a same-named one an earlier agent cached.

    The harness can run both seats in one process. If the opponent also ships a top-level
    package named `kagfarm` and their agent is built first, `sys.modules` caches theirs and
    a plain `from kagfarm.policy import Policy` would silently bind their code -- this seat
    would then PASS all episode (or worse, play their policy). So: import, check the loaded
    package actually lives in _HERE, purge and re-import if it does not (re-import only
    affects new lookups; the opponent's already-bound references are untouched).
    """
    import kagfarm
    pkg_dir = os.path.dirname(os.path.abspath(kagfarm.__file__))
    if os.path.realpath(pkg_dir) != os.path.realpath(os.path.join(_HERE, "kagfarm")):
        for name in [m for m in list(sys.modules)
                     if m == "kagfarm" or m.startswith("kagfarm.")]:
            del sys.modules[name]
        import kagfarm
    from kagfarm.policy import Policy
    return Policy


try:
    Policy = _import_policy()
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
        return pol.act(obs, config)
    except Exception:
        return _safe_pass(obs)


# Some Kaggle simulation harnesses look for a callable named after the file, others for a
# module-level `agent`. `get_last_callable` picks the LAST callable in the exec globals,
# so both names must reference the same object -- they do.
kagfarm_agent = agent
