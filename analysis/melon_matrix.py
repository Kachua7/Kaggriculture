"""The melon 2x2: is restraining the opening a Pareto improvement, or a dominated strategy?

Melon is in no shop basket, so the whole season's demand for it is the town centre's two units a
day -- 60 units, *shared between both players*. The shipped agent plants 24 of its 25 opening tiles
as melon anyway, because melon is the fastest cash-per-tile-day route to buying quadrants two and
three before day 12. Against the built-in opponents that works: they never touch the sink.

Against a peer it looks catastrophic. Both farms flood the same 60 units, melon realizes 45% of
base instead of 76%, neither farm can afford its land, the strawberry engine never scales, and the
mirror match pays **$20k instead of $86k**. Capping the opening at `mix_cap=2.0` more than doubles
that, to $46k, replicated on three disjoint blocks. It reads like the largest win available.

**It is not, and this script is why.** Terminal bank decides who wins an episode, but a ladder
rating is won and lost per episode, so the question is not "which cell banks more" -- it is "which
cell takes the episode". Restraint raises *both* banks, and it raises the flooder's by more,
because the flooder is the one still selling into the sink you just vacated. Fill in all four
cells and flooding turns out to beat restraint against either opponent: it is a dominant strategy,
and the mutual-flood outcome both players are driven to is the $20k one. A textbook prisoners'
dilemma, in a game with no way to cooperate.

So the melon opening stays. What this measurement is really worth is the warning: **every headline
number in this project is measured against opponents that do not compete for the sink.** A peer
takes the agent from $86k to $20k. That is the exposure, and capping melon is not the fix for it.

    python3 analysis/melon_matrix.py                 # the 2x2, three disjoint blocks
    python3 analysis/melon_matrix.py --blocks 1      # quick look
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from eval import evaluate                      # noqa: E402
from kagfarm.policy import PARAMS              # noqa: E402

# (label, my mix_cap, opponent name). `self` is pinned to the committed 3.0 flood; `self_mix2` is
# the same policy restrained to 2.0. Four cells, one 2x2.
CELLS = [
    ("flood   vs flood  ", 3.0, "self"),
    ("restrain vs flood ", 2.0, "self"),
    ("flood   vs restrain", 3.0, "self_mix2"),
    ("restrain vs restrain", 2.0, "self_mix2"),
]


def cell(mix_cap, opp, blocks, size, opps_extra=None):
    mine, oppb, wins, ties, n = [], [], 0, 0, 0
    for i in range(blocks):
        seeds = range(i * size, (i + 1) * size)
        rows = evaluate(seeds, [opp], workers=None, quiet=True,
                        params=dict(PARAMS, mix_cap=mix_cap))
        mine.append(sum(r["bank"] for r in rows) / len(rows))
        oppb.append(sum(r.get("opp_bank", 0) for r in rows) / len(rows))
        wins += sum(1 for r in rows if r["bank"] > r.get("opp_bank", 0))
        ties += sum(1 for r in rows if r["bank"] == r.get("opp_bank", 0))
        n += len(rows)
    return {"mine": sum(mine) / blocks, "opp": sum(oppb) / blocks,
            "mine_blocks": mine, "wins": wins, "ties": ties, "n": n,
            "winpct": 100.0 * wins / n}


def main_cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=3)
    ap.add_argument("--block-size", type=int, default=48)
    ap.add_argument("--out", default="analysis/melon_matrix.json")
    a = ap.parse_args()

    print("%d blocks x %d seeds = %d episodes per cell\n" %
          (a.blocks, a.block_size, a.blocks * a.block_size))
    print("  %-21s %9s %9s %9s   %7s %7s" %
          ("cell", "my bank", "opp bank", "total", "my win%", "ties"))
    out = {}
    for label, mc, opp in CELLS:
        r = cell(mc, opp, a.blocks, a.block_size)
        out[label.strip()] = r
        print("  %-21s %9.0f %9.0f %9.0f   %6.1f%% %7d" %
              (label, r["mine"], r["opp"], r["mine"] + r["opp"], r["winpct"], r["ties"]))

    ff = out["flood   vs flood"]
    rf = out["restrain vs flood"]
    fr = out["flood   vs restrain"]
    rr = out["restrain vs restrain"]
    print("\nread the columns, not the rows:")
    print("  against a FLOODING opponent    flood wins %5.1f%%   restrain wins %5.1f%%   -> %s"
          % (ff["winpct"], rf["winpct"], "flood" if ff["winpct"] > rf["winpct"] else "restrain"))
    print("  against a RESTRAINED opponent  flood wins %5.1f%%   restrain wins %5.1f%%   -> %s"
          % (fr["winpct"], rr["winpct"], "flood" if fr["winpct"] > rr["winpct"] else "restrain"))
    dom = ff["winpct"] > rf["winpct"] and fr["winpct"] > rr["winpct"]
    print("\n  flooding is %s" % ("DOMINANT -- it wins the episode against either opponent, so it "
                                  "stays,\n  even though mutual restraint would pay both players "
                                  "%.1fx more bank." % (rr["mine"] / max(1.0, ff["mine"]))
                                  if dom else "NOT dominant -- re-open the axis."))
    print("  bank, for the record: mutual flood $%.0f each, mutual restraint $%.0f each."
          % (ff["mine"], rr["mine"]))

    if a.out:
        path = os.path.join(_ROOT, a.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(out, fh, indent=2)
        print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main_cli()
