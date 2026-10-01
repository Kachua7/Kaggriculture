"""One-off: v2 (strict-only) matching baseline, PINNED hash seed, on the 5 desync worlds.

Forces every tier-3 call in the current comparator back to strict, which reproduces
the sub24 (v2) pick exactly: _pick(2) then _pick(3)->always None -> halt. Run per
world in its own process (the 12-games-one-process sequence leaks cross-episode
state; every ledger number is one-world-per-process, PYTHONHASHSEED=0).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kagfarm.policy as P  # noqa: E402

_SRC = P._variant_sig_eq


def _strict_only(sig, donor_sig, tol=2):      # noqa: ARG001 - tier arg forced to 2
    return _SRC(sig, donor_sig, 2)


P._variant_sig_eq = _strict_only

from analysis.elite_counterfactual import main  # noqa: E402,E501  (patched before use)

main()
