"""Play an agent tree and print its banks as JSON. The comparison tool `pack.sh` runs twice.

The question this answers is narrow and it is the one that actually goes wrong on submission day:
*does the tree that came out of the tarball behave like the tree I measured?* A missing
`kagfarm/__init__.py`, a stale file, a module left out of the archive -- all of those produce an
importable submission that either crashes on turn one or, worse, quietly falls back to
`_safe_pass` and banks a few hundred dollars while the log stays clean.

So this script takes a directory, plays episodes with `main.agent` resolved *from that
directory*, and writes nothing to stdout except a canonical JSON map of seed -> bank. Run it once
on the unpacked tarball and once on the repo, `cmp` the two outputs, and byte equality is proof
that the archive contains the agent that was measured. Diagnostics go to stderr precisely so they
stay out of that comparison -- wall-clock timings differ between runs and would break it.

    python3 verify_pack.py /tmp/unpacked --seeds 4 --opps starter,heuristic

Exits non-zero if the tree fails to import, raises inside `Policy.act`, breaches the turn budget,
or banks nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", help="directory holding main.py and kagfarm/")
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--opps", default="starter,heuristic")
    a = ap.parse_args()

    tree = os.path.abspath(a.tree)

    # The tree goes first so `main` and `kagfarm` resolve there; the repo goes second for
    # `engine` and `agents`, which are test scaffolding and never ship. Order is the whole
    # mechanism -- with the repo first, this script would cheerfully verify the repo twice.
    for path in (_HERE, tree):
        while path in sys.path:
            sys.path.remove(path)
    sys.path.insert(0, _HERE)
    sys.path.insert(0, tree)

    import main
    import kagfarm

    # `main.py` puts its own directory on `sys.path` at import time, so a tree that is missing
    # `kagfarm/` will not fail -- it will silently pick up the repo's copy and report a clean
    # run for an archive that cannot work. Assert the resolution instead of assuming it.
    got = os.path.dirname(os.path.abspath(kagfarm.__file__))
    if os.path.dirname(got) != tree:
        sys.exit("verify_pack: kagfarm resolved to %s, not %s -- the tree is incomplete"
                 % (got, tree))
    if main._BROKEN:
        sys.exit("verify_pack: %s/main.py could not import its policy: %s" % (tree, main._BROKEN))
    if not callable(getattr(main, "agent", None)):
        sys.exit("verify_pack: %s/main.py exposes no callable `agent`" % tree)

    from engine import KaggricultureEnv
    from agents import BUILTIN_AGENTS

    banks = {}
    worst_ms = 0.0
    for opp_name in a.opps.split(","):
        opp = BUILTIN_AGENTS[opp_name]
        for seed in range(a.seeds):
            main._POLICIES.clear()
            env = KaggricultureEnv(episode_steps=720, seed=seed)
            obs = env._obs()
            while not env.done:
                t0 = time.monotonic()
                act = main.agent(obs[0])
                ms = (time.monotonic() - t0) * 1000.0
                worst_ms = max(worst_ms, ms)
                if ms > 1000.0:
                    sys.exit("verify_pack: seed %d vs %s breached actTimeout at %.0fms"
                             % (seed, opp_name, ms))
                obs, _ = env.step([act, opp(obs[1])])
            pol = main._POLICIES.get(0)
            err = getattr(pol, "last_error", None) if pol else None
            if err:
                sys.exit("verify_pack: seed %d vs %s raised %s" % (seed, opp_name, err))
            bank = env.farms[0].money
            if bank <= 0:
                sys.exit("verify_pack: seed %d vs %s banked $%.0f" % (seed, opp_name, bank))
            banks["%d/%s" % (seed, opp_name)] = round(bank, 4)

    print(json.dumps(banks, sort_keys=True, indent=1))
    mean = sum(banks.values()) / len(banks)
    sys.stderr.write("verify_pack: %s -- %d episodes, mean $%.0f, worst turn %.1fms\n"
                     % (tree, len(banks), mean, worst_ms))


if __name__ == "__main__":
    main_cli()
