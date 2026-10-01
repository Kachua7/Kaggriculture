"""Dossier-grade profiler for top-10 corpus games (0925n).

Per game, per seat: final bank, d0 order script (first 5 order turns verbatim),
first BUY_ANIMAL turn, ordered animal units <= d10, herd mix, seed mix (WHEAT/MELON),
executed milk/wool, sell-day count, hires, d20 money lead.

Usage: python3 analysis/top10_profile.py [file.json ...]   # default: analysis/replays/top10/
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.profile_replay import profile, executed_flow

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "analysis", "replays", "top10")


def first_animal_turn(orders):
    for turn, mkt in orders:
        for mo in mkt:
            if mo[0] == "BUY_ANIMAL":
                return turn
    return None


def animal_units_by_day(orders, day_max):
    n = 0
    for turn, mkt in orders:
        if turn // 24 > day_max:
            break
        for mo in mkt:
            if mo[0] == "BUY_ANIMAL":
                q = mo[2] if len(mo) > 2 and isinstance(mo[2], int) else 1
                n += q
    return n


def money_at(pr, day):
    for d, m in pr["money_curve"]:
        if d == day:
            return m
    return None


def card(path):
    d = json.load(open(path))
    teams = d.get("info", {}).get("TeamNames", ["?", "?"])
    prof = profile(path)
    out = {"file": os.path.basename(path), "teams": teams, "seats": {}}
    for p in sorted(prof):
        pr = prof[p]
        flow = executed_flow(pr)
        d0_script = [mkt for turn, mkt in pr["orders"] if turn <= 4]
        out["seats"][p] = dict(
            team=teams[p] if p < len(teams) else "?",
            final=pr["final_money"],
            hires=pr["hires"],
            land=pr["land_buys"],
            d0_script=d0_script,
            first_animal=first_animal_turn(pr["orders"]),
            animal_u_d10=animal_units_by_day(pr["orders"], 10),
            herd=dict(pr["anim_buys"]),
            wheat_seeds=pr["seeds"].get("WHEAT", 0),
            melon_seeds=pr["seeds"].get("MELON", 0),
            milk=flow.get("MILK", 0),
            wool=flow.get("WOOL", 0),
            sell_days=len(pr["sell_days"]),
            d20=money_at(pr, 20),
        )
    a, b = out["seats"][0], out["seats"][1]
    out["margin"] = (a["final"] or 0) - (b["final"] or 0)
    out["winner"] = teams[0] if (a["final"] or 0) > (b["final"] or 0) else teams[1]
    return out


def print_card(c):
    print("=" * 78)
    print("%s  margin %+d  winner %s" % (c["file"], c["margin"], c["winner"]))
    for p in sorted(c["seats"]):
        s = c["seats"][p]
        print(" seat%d %-22s final $%s  d20 $%s  hires %d land %d" %
              (p, s["team"], format(s["final"] or 0, ","),
               format(s["d20"] or 0, ","), s["hires"], s["land"]))
        print("    d0 script (t<=4): %s" % (s["d0_script"],))
        print("    1stAnimal t%s  animal_u_d10 %d  herd %s" %
              (s["first_animal"], s["animal_u_d10"], s["herd"]))
        print("    seeds W%d/M%d  milk~%d wool~%d  sell_days %d" %
              (s["wheat_seeds"], s["melon_seeds"], s["milk"], s["wool"], s["sell_days"]))


if __name__ == "__main__":
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(DEFAULT_DIR, "*.json")))
    if not paths:
        print("no games yet in", DEFAULT_DIR)
    for pth in paths:
        print_card(card(pth))
