"""Seed-2 mirror collapse locator: per-day banks, animals, land, hands."""
import importlib
import sys

sys.path.insert(0, ".")
from bridge.real_env import RealEnv, ENGINE_DIR


def main():
    mod = importlib.import_module("main")
    importlib.reload(mod)
    env = RealEnv(2, ENGINE_DIR)
    obs0 = env._obs_view(0)
    obs1 = env._obs_view(1)
    t = 0
    prev = [None, None]
    while not env.done:
        a0 = mod.agent(obs0, env.config)
        a1 = mod.agent(obs1, env.config)
        env.step([a0, a1])
        day = t // 24
        if t % 24 == 0:
            b = [obs0["farms"][0]["money"], obs1["farms"][1]["money"]]
            h = [1 + len(obs0["farms"][0].get("hands") or []),
                 1 + len(obs1["farms"][1].get("hands") or [])]
            l = [obs0["farms"][0].get("land", {}).get("unlocked", None),
                 obs1["farms"][1].get("land", {}).get("unlocked", None)]
            print(f"d{day:2d} banks=[{b[0]:9.0f},{b[1]:9.0f}] d_bank=[{'' if prev[0] is None else f'{b[0]-prev[0]:+8.0f}'},{'' if prev[1] is None else f'{b[1]-prev[1]:+8.0f}'}] hands={h}")
            prev = b
        obs0 = env._obs_view(0)
        obs1 = env._obs_view(1)
        t += 1


if __name__ == "__main__":
    main()
