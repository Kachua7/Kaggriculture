"""Top-10 corpus pipeline (0925n): bulk-download a daily episode dataset, keep only
games involving top-10 teams, profile them dossier-style.

Modes (run from project root):
  python3 analysis/top10_scan.py download   # detached kaggle download (survives exit)
  python3 analysis/top10_scan.py status     # download progress
  python3 analysis/top10_scan.py scan       # stream-scan zip, keep top-10 games
  python3 analysis/top10_scan.py scan --validate <file.json>
  python3 analysis/top10_scan.py profile    # dossier-grade summary of kept games

Kept games land in analysis/replays/top10/ and auto-register as replay_opp judges.
"""
import argparse, json, os, subprocess, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DL_DIR = "/tmp/ep24full"
KEEP_DIR = os.path.join(ROOT, "analysis", "replays", "top10")
SLUG = "kaggle/kaggriculture-episodes-2026-09-24"
LOG = "/tmp/ep24_download.log"

TOP10 = [
    "DSM", "Boey", "Unknown Mother-Goose", "M & M & P & Q", "DECEM",
    "Fourth Quadrant", "Majkel1337", "mtmr_s1", "Vadim Vasilenko",
    "\u5403\u767d\u996d\u7684\u5927\u80a5\u9c7c",
    "Pranjal Morwal",  # slot-A control series
]


def download():
    os.makedirs(DL_DIR, exist_ok=True)
    log = open(LOG, "w")
    proc = subprocess.Popen(
        ["kaggle", "datasets", "download", SLUG, "-p", DL_DIR, "-o"],
        stdout=log, stderr=log, start_new_session=True)
    print("detached download PID", proc.pid)
    time.sleep(8)
    if os.path.exists(LOG):
        print("log tail:", open(LOG).read()[-200:])


def status():
    if os.path.exists(LOG):
        tail = open(LOG).read()[-200:].replace("\r", "\n").strip().splitlines()
        print("log:", tail[-1] if tail else "(empty)")
    if os.path.isdir(DL_DIR):
        for f in sorted(os.listdir(DL_DIR)):
            p = os.path.join(DL_DIR, f)
            if os.path.isfile(p):
                print("  %s: %.2f GB" % (f, os.path.getsize(p) / 1e9))
    else:
        print("no download dir yet")


def team_names_from_member(zf, name):
    with zf.open(name) as fh:
        chunk = fh.read(4096).decode("utf-8", "ignore")
    i = chunk.find('"TeamNames"')
    if i < 0:
        return None
    j = chunk.find("]", i)
    seg = chunk[i:j + 1]
    return [s.strip(' "') for s in seg.split("[")[-1].split(",")]


def scan(validate=None):
    if validate:
        ep = json.load(open(validate))
        names = ep.get("info", {}).get("TeamNames", [])
        print("validate:", os.path.basename(validate), "teams=", names,
              "match=", [t for t in names if t in TOP10])
        return
    os.makedirs(KEEP_DIR, exist_ok=True)
    zips = sorted(f for f in os.listdir(DL_DIR) if f.endswith(".zip"))
    if not zips:
        print("no complete zip yet; run status"); return
    zp = os.path.join(DL_DIR, zips[0])
    kept = seen = 0
    with zipfile.ZipFile(zp) as zf:
        members = [m for m in zf.namelist() if m.endswith(".json")]
        total = len(members)
        for m in members:
            seen += 1
            try:
                names = team_names_from_member(zf, m)
            except Exception as e:
                print("  skip", m, e); continue
            if names and any(t in names for t in TOP10):
                data = zf.read(m)
                json.loads(data)
                out = os.path.join(KEEP_DIR, os.path.basename(m))
                with open(out, "wb") as fh:
                    fh.write(data)
                kept += 1
                print("  KEEP", os.path.basename(m), names, flush=True)
            if seen % 50 == 0:
                print("  scanned %d/%d, kept %d" % (seen, total, kept), flush=True)
    print("DONE: scanned %d, kept %d -> %s" % (seen, kept, KEEP_DIR))


def profile():
    files = sorted(os.path.join(KEEP_DIR, f) for f in os.listdir(KEEP_DIR)
                   if f.endswith(".json"))
    print("kept games:", len(files))
    for f in files:
        ep = json.load(open(f))
        names = ep.get("info", {}).get("TeamNames", [])
        steps = ep.get("steps", [])
        banks = []
        if steps:
            last = steps[-1]
            for seat in range(2):
                r = last[seat].get("reward", 0) if isinstance(last[seat], dict) else 0
                banks.append(r)
        if len(banks) == 2:
            print("  %s: %s $%.0f vs %s $%.0f" % (os.path.basename(f),
                  names[0], banks[0], names[1], banks[1]))
        else:
            print("  %s: %s" % (os.path.basename(f), names))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["download", "status", "scan", "profile"])
    ap.add_argument("--validate", default=None)
    a = ap.parse_args()
    if a.mode == "scan":
        scan(a.validate)
    elif a.mode == "download":
        download()
    elif a.mode == "status":
        status()
    else:
        profile()
