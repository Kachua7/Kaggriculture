"""Replay-opponent sparring partners for the local panel.

Type A — REPLAY_EXACT (default, per the frozen plan's fidelity hierarchy: recorded
actions are AVAILABLE in the replay JSON, so they are used, not reconstructed):
- The recorded seat's full action dict (farmer + hands + market) is replayed VERBATIM
  each turn. The farm board is private, so the recorded physical trajectory largely
  self-reproduces even though our seat plays differently: only prices, weed spawns and
  shed-fill races diverge, all second-order. This reproduces the recorded economy —
  including the income flow the recorded opponents lived on — not just its order list.

Type B — REPLAY_MARKET_PRESSURE (make_replay_agent(..., mode="pressure")):
- Market orders verbatim at their exact turns; physical actions from a deterministic
  greedy body. NOT a faithful replay: calibration showed a greedy body cannot sustain
  the recorded cost structure (a fib wage bill of $2-14k/day needs the recorded income
  flow, which a hand-rolled body does not generate), so the judge goes bankrupt and
  applies no pressure. Kept for experiments that want pure order-tape pressure.

Determinism and safety:
- PARAMS-immune by construction: this module never reads kagfarm.policy, so a sweep
  mutating PARAMS for seat 0 cannot alter the judge.
- Deterministic: no RNG, no wall-clock; the tape is fixed data.
- Spawn-safe: the manifest is built at import from files that exist on THIS machine
  (macOS spawns pool workers fresh, so parent-side dynamic registration would not
  propagate into eval's process pool).
"""
import json
import os

from engine import BOARD_SIZE, OBJECT_TABLE
from kagfarm.constants import SHED_TILES

REPLAY_DIRS = (os.path.expanduser("~/Downloads"), "analysis/replays")

# episode-id -> (label, our_final_money, recorded_seed). `our_final_money` resolves
# the recorded seat bank-first (name labels were seat-inverted on the 111xxx batch;
# bank-matching is the only reliable attribution). The recorded seed (replay info.seed)
# lets the panel re-run each judge ON ITS OWN RECORDED WORLD: the only difference from
# the recorded episode is then our seat's play — a true counterfactual.
MANIFEST_IDS = {
    "111103455": ("air", 58352.0, 85913572),
    "111148725": ("aditya", 61206.0, 1860128738),
    "111201497": ("sathish", 57823.0, 1079297752),
    "111229714": ("kovkin", 63413.0, 953635407),
    "111264433": ("madhur", 66396.0, 2118364291),
    # 2026-09-21 batch: 111365643 is the Phase-0 evidence game (kill-chain first-
    # divergence: opponent leads DROP by d2, FEED/CARE d4, COLLECT d5, HERD d10).
    # S. Mujtaba Hussain $84,979 = the $75-85k class this build must clear first.
    "111365643": ("mujtaba", 57978.0, 183303730),
}

# -- spectator judges (2026-09-21): elite-vs-elite games that do NOT contain us. Both
# seats' tapes are judge candidates. TeamNames order IS seat order (verified against
# bank-matching on our own games), so an explicit seat index is REQUIRED here -- the
# `_resolve_seat` heuristic keys on our d0 melon cohort and would misresolve these.
SPECTATOR_IDS = {
    # ep_id -> {name: seat}. 111328923 = Majkel1337 $139,851 (seat 0) vs
    # THIRD FARM CLUB $127,781 (seat 1): the top-two convergence game.
    "111328923": {"majkel": 0, "thirdfarm": 1},
    # 110964284 = THIRD FARM CLUB $98,814 (seat 0) vs Majkel1337 $100,281 (seat 1):
    # the second Majkel judge the promotion gate requires, and a CLOSE elite game.
    "110964284": {"tfc2": 0, "majkel2": 1},
    # 111369668 = SpaTaro $115,292 (seat 0) vs Majkel1337 $119,975 (seat 1), seed
    # 1430410553: the only elite tape that survived the Downloads cleanup — now the
    # PRIMARY elite judge (Majkel's third registered game).
    "111369668": {"sparo": 0, "majkel3": 1},
    # 112127332 = Pranjal Morwal $65,585 (seat 0) vs Luan He $97,554 (seat 1), seed
    # 1907357912. Luan He's plant cadence is the winner-profile the s12 autopsies
    # named: 1-3 seeds/day d5-d10 (staggered cohorts) vs our two tsunamis.
    "112127332": {"luanhe": 1},
    # 112129810 = juicyorange $88,022 (seat 0) vs Pranjal Morwal $40,425 (seat 1),
    # seed 211331135: the $47.6k loss. Second field judge on the fresh build.
    "112129810": {"juicy": 0},
    # -- the MIDFIELD tier (2026-09-25, ELO package): the 2400-2900 coin-flip band where
    # Bradley-Terry rating actually moves (elite losses are nearly free; these decide the
    # record). Seat maps from TeamNames order, verified against the reward banks.
    # 113122185 = Pranjal $90,413 (seat 0) vs Tâm La Thành $67,342 (seat 1), seed
    # 969596258: the endgame-conversion WIN specimen (d26 gap -$11k -> +$23.1k).
    "113122185": {"midfield_tam": 1},
    # 112957999 = Dean Johnson $41,669 (seat 0) vs Pranjal $51,162 (seat 1), seed
    # 970394715: the +$9.5k win (980u strawberry @ $200 realized).
    "112957999": {"midfield_dean": 0},
    # 112959216 = Pranjal $47,641 (seat 0) vs Jiahan Cao $57,066 (seat 1), seed
    # 309707973: the -$9.4k near-miss (892u @ $269 -- premium prices, volume short).
    "112959216": {"midfield_jiahan": 1},
    # 112952973 = Pranjal $66,148 (seat 0) vs susutem $76,805 (seat 1), seed
    # 1465775700: the -$10.7k near-miss (1279u @ $215 -- ~50 units short).
    "112952973": {"midfield_susutem": 1},
    # -- the RESTORED dossier (2026-09-21, analysis/restore_replays.py): the 12 wiped
    # Majkel games re-pulled from kaggle/kaggriculture-episodes-2026-09-1{9,20} into
    # analysis/replays/. Majkel wins all 13 restored games; margins +$326 to +$21.6k.
    # Only the MAJKEL seat is listed per game (build_manifest builds one judge per dict
    # entry; the losing seats are added on demand to keep import memory bounded).
    "110886706": {"majkel886": 0},   # +$326  vs Otter Vibe        $73,656  (closest)
    "110900752": {"majkel900": 0},   # +$21,592 vs THIRD FARM CLUB $134,619 (widest)
    "110907373": {"majkel907": 1},   # +$1,527 vs Yannik Schiffner $154,751
    "110913896": {"majkel913": 0},   # +$16,245 vs THIRD FARM CLUB $76,211
    "110920455": {"majkel920": 0},   # +$5,042 vs THIRD FARM CLUB  $97,982
    "110926948": {"majkel926": 0},   # +$5,376 vs Yannik Schiffner $87,010
    "110932461": {"majkel932": 0},   # +$7,439 vs Orbital Terraformer $80,088
    "110938064": {"majkel938": 1},   # +$11,894 vs ymg_aq          $80,582
    "110943566": {"majkel943": 1},   # +$12,129 vs THIRD FARM CLUB $107,623
    "110948948": {"majkel948": 1},   # +$1,193 vs DSM              $99,852
    "110954233": {"majkel954": 0},   # +$3,239 vs Planned Economy  $99,674
    "111016701": {"majkel016": 1},   # +$523  vs Sida Zuo          $95,033
    # Also on disk, available for registration when needed (one dict line each):
    # 110959567 ymg_aq/Majkel $121k/$134k; 110141835, 110129805 Majkel/SpaTaro;
    # 110141832, 110123361 Majkel/Unknown Mother-Goose; 110135201 DSM/Majkel.
}


def _replay_seed(path):
    """The recorded world's seed: info['seed'] (engine-persisted), then configuration.

    111103455's info.seed matches the manifest's hardcoded 85913572, which validates
    the reader against a known value."""
    d = json.load(open(path))
    s = (d.get("info") or {}).get("seed")
    if s is None:
        s = (d.get("configuration") or {}).get("seed")
    return s


SHED_SET = set(SHED_TILES.values())
_ANIMAL_STRUCT = {"GOOSE": "COOP", "COW": "PASTURE", "SHEEP": "PASTURE"}
_BUILD_FOR = {"GOOSE": "BUILD_COOP", "COW": "BUILD_PASTURE", "SHEEP": "BUILD_PASTURE"}
_PLANT_PREF = ("MELON", "STRAWBERRY", "TOMATO", "WHEAT", "CARROT")

# Working-capital floor, applied by the RUNNER (eval.run_one / ab_panel), never by the
# agent: the engine does not let an agent mint money. Calibration showed the recorded
# opponents survive their d0-14 trough on a windfall that the mirror world halves (our
# seat is stronger than our recorded seat was), so the tape goes bankrupt at d15 and a
# bankrupt judge applies zero market pressure — a bystander, not a sparring partner.
# The floor must clear the fib WAGE BAND for the recorded roster (~$2-3k/day for 10-12
# hands at fib pricing), not just bare solvency, or the d0 order list (seeds before
# hires) exhausts cash, HIREs fail forever, and a 1-hand judge cannot work a 60-tile
# farm. $2,000 lets the tape's roster form; the subsidy total is reported in the
# calibration card (ab_panel) and a judge needing a large subsidy relative to its
# recorded bank is flagged rather than silently trusted.
SUBSIDY_FLOOR = 2000.0


def _find_replay(ep_id):
    for d in REPLAY_DIRS:
        p = os.path.join(d, f"{ep_id}.json")
        if os.path.exists(p):
            return p
    return None


def _resolve_seat(path, ep_id):
    from analysis.profile_replay import profile
    prof = profile(path)
    if ep_id in MANIFEST_IDS:
        our_money = MANIFEST_IDS[ep_id][1]
        for p, pr in prof.items():
            if pr["final_money"] is not None and abs(pr["final_money"] - our_money) <= 2.0:
                return 1 - p
    for p, pr in prof.items():
        if pr.get("d0_seeds", {}).get("MELON", 0) >= 8:
            return 1 - p
    return 0


def _ripe(t, day):
    """PLANT initializes yield_units=1 for EVERY crop and HARVEST before
    first_yield_day is an engine no-op (engine.py carries the KT note). A naive
    `yield_units > 0` test makes a body hammer HARVEST on an immature melon all day
    -- the planting-pace killer this panel shipped with. WHEAT's first_yield_day is 0
    (its day-0 unit is genuinely harvestable)."""
    if t.get("yield_units", 0) <= 0:
        return False
    crop = t.get("crop")
    spec = OBJECT_TABLE.get(crop) or {}
    first = spec.get("first_yield_day", spec.get("sched_days", [0])[0])
    return (day - t.get("planted_day", 0)) >= first


def _recorded_actions(path, seat):
    """{turn: action_dict} verbatim from the replay. Kaggle replays carry the full
    action each seat emitted every step (dict form: farmer/hands/market — the same
    contract as the mirror); None or missing turns degrade to PASS."""
    d = json.load(open(path))
    steps = d["steps"]
    out = {}
    for i, st in enumerate(steps):
        a = st[seat].get("action")
        if isinstance(a, dict) and a:
            out[i] = a
    return out


def make_replay_agent(replay_path, seat=None, mode="exact"):
    """Factory: (replay_path, seat) -> agent(obs). seat None = auto-resolve."""
    ep_id = os.path.basename(replay_path).split(".")[0]
    if seat is None:
        seat = _resolve_seat(replay_path, ep_id)
    from analysis.profile_replay import profile
    prof = profile(replay_path)
    orders = {t: [list(mo) for mo in mkt] for t, mkt in prof[seat]["orders"]}
    actions = _recorded_actions(replay_path, seat) if mode == "exact" else None

    def _manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def _step_toward(origin, tgt):
        dx = tgt[0] - origin[0]
        dy = tgt[1] - origin[1]
        if abs(dx) >= abs(dy) and dx:
            return ["EAST" if dx > 0 else "WEST"]
        if dy:
            return ["SOUTH" if dy > 0 else "NORTH"]
        return ["EAST" if dx > 0 else "WEST"]

    def agent(obs):
        step = obs["step"]
        if actions is not None:
            # TYPE A: verbatim. The recorded dict is already in engine contract form.
            # ALIGNMENT (same rule as verify_replay.resimulate): steps[t].action is the
            # action that PRODUCED steps[t].observation from the state at t-1, so the
            # action to apply when the current observation has step=s is index s+1.
            # Getting this wrong fires every feed/water one turn early — a feed at
            # d0 h24 is wiped by the midnight fed_today reset, and the animal is unfed
            # on d1 (77 failed milk sells in the first bridge A/B traced here).
            a = actions.get(step + 1)
            if a is None:
                return {"farmer": ["PASS"], "hands": [], "market": []}
            return {"farmer": list(a.get("farmer") or ["PASS"]),
                    "hands": [list(h) for h in (a.get("hands") or [])],
                    "market": [list(mo) for mo in (a.get("market") or [])]}

        # TYPE B: market tape verbatim + greedy body (see module docstring).
        me = obs["farms"][obs["player"]]
        market = orders.get(step, [])

        tiles = me["tiles"]
        feed_jobs, water_jobs, harvest_jobs, care_jobs, collect_jobs = [], [], [], [], []
        empty_structs, empty_tiles = [], []
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                t = tiles[y][x]
                pos = (x, y)
                if t is None:
                    # Shed-access tiles read as None in the grid but are the spawn/handling
                    # zone: a unit standing there treats "nearest empty tile" as itself and
                    # PASSes forever (the d0 deadlock this panel shipped with). Never target
                    # them for planting or walking — step OFF is handled by job targeting.
                    if pos not in SHED_SET:
                        empty_tiles.append(pos)
                elif t == "LOCKED":
                    continue
                elif isinstance(t, dict):
                    k = t.get("kind")
                    if k in ("COOP", "PASTURE"):
                        if t.get("animal"):
                            if not t.get("fed_today") or t.get("consecutive_unfed", 0) >= 1:
                                feed_jobs.append(pos)
                            if not t.get("cared_today"):
                                care_jobs.append(pos)
                            if t.get("yield_units", 0) > 0:
                                harvest_jobs.append(pos)
                            if t.get("fertilizer_available"):
                                collect_jobs.append(pos)
                        else:
                            empty_structs.append(pos)
                    elif k == "PLANT":
                        if _ripe(t, obs["day"]):
                            harvest_jobs.append(pos)
                        elif not t.get("watered_today"):
                            water_jobs.append(pos)

        priv = obs.get("private") or {}
        invs = list(priv.get("inventories") or [])
        units = [me["farmer"]] + list(me["hands"])
        while len(invs) < len(units):
            invs.append({})
        shed = priv.get("shed") or {}
        seeds = priv.get("seeds") or {}

        acts = []
        for i, raw_origin in enumerate(units):
            origin = (raw_origin[0], raw_origin[1])  # obs carries lists; SHED_TILES are tuples
            inv = invs[i]
            op = None

            # 1) FEED — wheat must be carried (engine: FEED takes from unit inventory).
            tgt = min(feed_jobs, key=lambda p: _manhattan(p, origin)) if feed_jobs else None
            if tgt is not None:
                if inv.get("WHEAT", 0) > 0:
                    if _manhattan(tgt, origin) <= 1:
                        op = ["FEED"]
                        feed_jobs.remove(tgt)
                    else:
                        op = _step_toward(origin, tgt)
                elif origin in SHED_SET:
                    if shed.get("WHEAT", 0) > 0:
                        op = ["PICKUP", "WHEAT", max(1, len(feed_jobs))]
                    # else: no wheat anywhere — nothing to feed with; fall through
                else:
                    op = _step_toward(origin, SHED_TILES["NW"])
            if op is not None:
                acts.append(op)
                continue

            # 2) PLACE held animals / BUILD their structure (market BUY_ANIMAL only
            #    fills the shed; without this the tape's herd never produces).
            held_animal = next((a for a in ("COW", "SHEEP", "GOOSE") if inv.get(a)), None)
            if held_animal:
                here = tiles[origin[1]][origin[0]]
                if isinstance(here, dict) and here.get("kind") == _ANIMAL_STRUCT[held_animal] \
                        and "animal" not in here:
                    op = ["PLACE", held_animal]
                else:
                    spot = min(empty_structs, key=lambda p: _manhattan(p, origin)) \
                        if empty_structs else None
                    want = _ANIMAL_STRUCT[held_animal]
                    spot = next((p for p in empty_structs
                                 if tiles[p[1]][p[0]].get("kind") == want), spot)
                    if spot is None:
                        if here is None and origin not in SHED_SET:
                            op = [_BUILD_FOR[held_animal]]
                        else:
                            op = _step_toward(origin, min(empty_tiles, key=lambda p: _manhattan(p, origin))) \
                                if empty_tiles else ["PASS"]
                    elif spot == origin:
                        op = ["PASS"]
                    else:
                        op = _step_toward(origin, spot)
                acts.append(op)
                continue

            # 3) on-tile chores: harvest > water > care > collect
            x, y = origin
            here = tiles[y][x] if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE else None
            if isinstance(here, dict):
                k = here.get("kind")
                if k == "PLANT":
                    if _ripe(here, obs["day"]):
                        op = ["HARVEST"]
                    elif not here.get("watered_today"):
                        op = ["WATER"]
                elif k in ("COOP", "PASTURE") and here.get("animal"):
                    if here.get("yield_units", 0) > 0:
                        op = ["HARVEST"]  # animal products need no ripening
                    elif not here.get("cared_today"):
                        op = ["CARE"]
                    elif here.get("fertilizer_available"):
                        op = ["COLLECT_FERTILIZER"]
            if op is not None:
                acts.append(op)
                continue

            # 4) PLANT held seeds on empty ground (BUY_SEED only fills the bag).
            crop = next((c for c in _PLANT_PREF if seeds.get(c)), None)
            if crop and here is None and origin not in SHED_SET:
                acts.append(["PLANT", crop])
                continue

            # 5) walk to the nearest remaining job, else haul to shed and DROP.
            pool = water_jobs + harvest_jobs + care_jobs + collect_jobs + empty_structs
            if crop:
                pool = pool + empty_tiles
            tgt = min(pool, key=lambda p: _manhattan(p, origin)) if pool else None
            if tgt is None:
                if inv:
                    if origin in SHED_SET:
                        op = ["DROP"]
                    else:
                        op = _step_toward(origin, SHED_TILES["NW"])
                else:
                    op = ["PASS"]
            elif tgt == origin:
                op = ["PASS"]
            else:
                op = _step_toward(origin, tgt)
            acts.append(op)

        return {"farmer": acts[0] if acts else ["PASS"],
                "hands": acts[1:] or [["PASS"]],
                "market": market}

    agent.__name__ = f"replay_{ep_id}"
    agent.replay_meta = {"episode": ep_id, "seat": seat,
                         "type": "REPLAY_EXACT" if mode == "exact" else "REPLAY_MARKET_PRESSURE",
                         "subsidy_floor": SUBSIDY_FLOOR}
    return agent


def build_manifest():
    """{name: agent} for every replay file that resolves. Called at import in
    agents.py (spawn-safe) and re-callable for interactive use."""
    out = {}
    seen = set()
    for d in REPLAY_DIRS:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not (fn.endswith(".json") and fn[:-5].isdigit()):
                continue
            ep_id = fn[:-5]
            if ep_id in seen:
                continue
            path = _find_replay(ep_id)
            if not path:
                continue
            try:
                if ep_id in MANIFEST_IDS:
                    out[f"replay_{MANIFEST_IDS[ep_id][0]}"] = make_replay_agent(path)
                    seen.add(ep_id)
                elif ep_id in SPECTATOR_IDS:
                    # Elite-vs-elite game: one judge per listed seat.
                    for name, seat in SPECTATOR_IDS[ep_id].items():
                        out[f"replay_{name}"] = make_replay_agent(path, seat=seat)
                    seen.add(ep_id)
            except Exception:
                continue  # a malformed replay never breaks agent import
    return out


if __name__ == "__main__":
    m = build_manifest()
    print(f"{len(m)} replay opponents: {sorted(m)}")
