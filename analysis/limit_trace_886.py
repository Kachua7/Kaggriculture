"""F4 probe: WHY do 8-40 tiles sit empty d18-29 on judge 886?

Reads `policy.limit` (the allocator's own per-pass veto labels) at each dawn,
plus tile_limited / live counts / seed bank. Read-only diagnosis for the
replant-wave fix. Same judge plumbing as analysis/kill_chain.py.
"""
import importlib
import sys

sys.path.insert(0, ".")
from analysis.ab_panel import _judge_meta
from bridge.real_env import RealEnv, ENGINE_DIR


def main():
    _ep, _path, _seat, seed = _judge_meta("replay_majkel886")
    from kagfarm import policy as _policy
    pol = _policy.Policy
    mod = importlib.import_module("main")
    importlib.reload(mod)
    from agents import BUILTIN_AGENTS
    opp = BUILTIN_AGENTS["replay_majkel886"]

    env = RealEnv(seed, ENGINE_DIR)
    obs0 = env._obs_view(0)
    obs1 = env._obs_view(1)
    t = 0
    inst = None
    print("day  limit                     tiles live empty seed$")
    while not env.done:
        a0 = mod.agent(obs0, env.config)
        a1 = opp(obs1)
        if inst is None:
            inst = mod._POLICIES.get(0)      # built lazily on the first agent() call
        env.step([a0, a1])
        day = t // 24
        if inst is not None and t % 24 == 0 and day >= 12:
            me = obs0["farms"][obs0["player"]]
            live, empty = inst._board_state(me.get("tiles") or [],
                                            me.get("unlocked_quadrants") or set())
            weeds = sum(1 for row in (me.get("tiles") or []) for tl in (row or [])
                        if isinstance(tl, dict) and tl.get("kind") == "WEED")
            from kagfarm.policy import collect_jobs
            jobs = collect_jobs(me.get("tiles") or [],
                                me.get("unlocked_quadrants") or set(), day,
                                obs0.get("prices") or {}, inst.want,
                                getattr(inst, "seed_plan", {}), inst.p,
                                animals=inst.animals)
            from collections import Counter as _C
            jmix = _C(j["op"][0] for j in jobs)
            print(f"d{day:2d} tl={int(inst.tile_limited)} live={sum(live.values()):3d} "
                  f"empty={empty:2d} weeds={weeds:2d} want={dict(inst.want or {})} "
                  f"jobs={dict(jmix)}")
        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)
        t += 1


if __name__ == "__main__":
    main()
