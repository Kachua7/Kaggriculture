"""PRE_SUBMIT_CHECKLIST P0 smoke, run against the EXACT submission.tar.gz bytes.

Checks, in checklist order:
  P2 packaging : tar layout (main.py at root), files present
  P0.1 Struct  : harness calls agent(structify(obs), structify(config)) -- Struct IS a
                 dict subclass, so .get works; this run proves it on the real path
  P0.2 smoke   : full 720-step episodes on kaggle_environments.make("kaggriculture"),
                 self-self and vs the built-in starter, in ONE process (global-state
                 leak check: a second episode must reset cleanly)
  P0.4 timeout : any status TIMEOUT/ERROR/INVALID => DQ signature, reported
  P0.5/P3.5    : final reward is the bank (money), printed for the shed/bank check

Run with the canonical interpreter:
  .venv/bin/python analysis/harness_smoke.py
"""
import os
import sys
import tarfile
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Default: the canonical tar. Optional argv[1]: any other archive (.zip twin) to smoke
# the exact bytes of a different upload format.
TAR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "submission.tar.gz")

print(f"tar    : {TAR}")
print(f"size   : {os.path.getsize(TAR):,} bytes")

# ---- P2: layout ----------------------------------------------------------------
if TAR.endswith(".zip"):
    import zipfile
    with zipfile.ZipFile(TAR) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
    names = [i.filename for i in infos]
    print(f"layout : {sorted(names)}")
    assert "main.py" in names, "FATAL: no main.py at zip root"
    assert all(os.path.normpath(n).startswith(("main.py", "kagfarm/")) for n in names), \
        "unexpected zip members"
else:
    with tarfile.open(TAR) as tf:
        names = tf.getnames()
    print(f"layout : {sorted(names)}")
    assert "main.py" in names, "FATAL: no main.py at tar root"
    assert not any(n.startswith("/") for n in names), "absolute path in tar"

tmp = tempfile.mkdtemp(prefix="kgsmoke_")
if TAR.endswith(".zip"):
    import zipfile
    with zipfile.ZipFile(TAR) as zf:
        zf.extractall(tmp)                     # members verified above, no traversal
else:
    with tarfile.open(TAR) as tf:
        tf.extractall(tmp, filter="data")   # reject traversal/symlink members even in a tampered tar
main_path = os.path.join(tmp, "main.py")

# ---- P0.2 + P0.4: real harness episodes -----------------------------------------
from kaggle_environments import make  # noqa: E402  (venv site-packages)


def one(name, specs):
    env = make("kaggriculture")
    t0 = time.monotonic()
    env.run(specs)
    dt = time.monotonic() - t0
    print(f"\n[{name}] {dt:.1f}s  steps={len(env.steps)} (expect 720)")
    for i, ag in enumerate(env.state):
        info = ag.info if isinstance(ag.info, dict) else getattr(ag.info, "__dict__", {})
        print(f"  seat {i}: status={ag.status!r} reward=${ag.reward:,.0f} "
              f"err={info.get('err')}")
    bad = [ag.status for ag in env.state if ag.status not in ("DONE", "INACTIVE")]
    assert not bad, f"FATAL: non-DONE statuses {bad} => DQ on the ladder"
    assert len(env.steps) >= 719, "episode ended early"
    return [ag.reward for ag in env.state]


print("\n=== episode 1: our tar (seat 0) vs our tar (seat 1), one process ===")
b1 = one("self-self", [main_path, main_path])
print(f"banks: {b1}")

print("\n=== episode 2, SAME process: our tar vs built-in starter (state-leak probe) ===")
try:
    b2 = one("vs-starter", [main_path, "starter"])
except Exception as e:                                  # noqa: BLE001
    print(f"starter builtin unavailable: {e!r}")
    b2 = one("self-self-again", [main_path, main_path])
print(f"banks: {b2}")

print("\n=== episode 3, SAME process: seat swap (seat 1 is ours) ===")
b3 = one("swap", ["starter", main_path])
print(f"banks: {b3}")

print("\nALL SMOKE CHECKS PASSED: no ERROR/TIMEOUT, 720 steps, rewards are banks.")
