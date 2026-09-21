"""Restore lost replay tapes from the official kaggriculture-episodes-* datasets.

The Downloads cleanup wiped the 24-32MB judge tapes; the competition publishes every
episode JSON in daily datasets (index: kaggle/kaggriculture-episodes-index). This
script pages each day's file listing, notes which dataset holds each wanted episode,
and downloads just those files (~30MB each) into analysis/replays/ -- which
replay_opp.REPLAY_DIRS already scans, so restored tapes auto-register as judges.

Usage:
    python3 analysis/restore_replays.py --scan            # locate only
    python3 analysis/restore_replays.py --scan --download # locate + fetch
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys

INDEX = "kaggle/kaggriculture-episodes-index"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEST = os.path.join(ROOT, "analysis", "replays")

# Wanted episode ids. Groups: our judge tapes (MANIFEST_IDS), the s8/s9/sub10
# analysis batch, and elite-vs-elite spectators beyond the surviving 111369668.
WANTED = [
    # our-game judges (bank-first attribution)
    "111365643", "111264433", "111229714", "111201497", "111148725", "111103455",
    # s8-era autopsies
    "110928677", "110922997", "110918559", "110897820",
    # Majkel dossier batch
    "110954233", "110948948", "110943566", "110938064", "110932461",
    "110926948", "110920455", "110913896", "110907373", "110900752",
    "110894053", "110886706",
    # earlier autopsies referenced by the ledger
    "110850828", "110874286", "110873165",
    # the s10 games (sub10games folder, also wiped)
    "111016701",
    # second close elite game named by the promotion gate
    "110964284",
]

DAYS = ["2026-09-12", "2026-09-13", "2026-09-14", "2026-09-15",
        "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20"]


def day_slug(day):
    return f"kaggle/kaggriculture-episodes-{day}"


def list_files(slug):
    """All (name, size) for a dataset, following page tokens."""
    out, token = [], None
    while True:
        cmd = ["kaggle", "datasets", "files", slug, "-v", "--page-size", "100"]
        if token:
            cmd += ["--page-token", token]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            sys.stderr.write(r.stderr[-300:])
            return out, token
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        if not lines:
            break
        if lines[0].startswith("Next Page Token"):
            token = lines[0].split("=", 1)[1].strip()
            lines = lines[1:]
        else:
            token = None
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        rows = list(reader)
        if not rows:
            break
        out.extend((row["name"], row.get("size", "")) for row in rows)
        if token is None:
            break
    return out, token


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--download", action="store_true")
    a = ap.parse_args()
    wanted = set(WANTED)
    found = {}
    for day in DAYS:
        slug = day_slug(day)
        files, _tok = list_files(slug)
        hits = [(n, s) for n, s in files if n[:-5] in wanted]
        print(f"{day}: {len(files)} files, {len(hits)} wanted", flush=True)
        for n, s in hits:
            found[n[:-5]] = (slug, n, s)
        if wanted <= found.keys():
            break
    missing = sorted(wanted - found.keys())
    print(f"\nlocated {len(found)}/{len(WANTED)}")
    if missing:
        print("missing (not in scanned days):", missing)
    map_path = os.path.join(HERE, "replay_location_map.json")
    json.dump(found, open(map_path, "w"), indent=1)
    print(f"location map -> {map_path}")
    if not a.download:
        return
    os.makedirs(DEST, exist_ok=True)
    for ep in sorted(found):
        dest_file = os.path.join(DEST, f"{ep}.json")
        if os.path.exists(dest_file) and os.path.getsize(dest_file) > 1_000_000:
            print(f"{ep}: already restored")
            continue
        slug, fname, size = found[ep]
        print(f"{ep}: downloading from {slug} ({size}) ...", flush=True)
        r = subprocess.run(["kaggle", "datasets", "download", slug, "-f", fname,
                            "-p", DEST, "-o"], capture_output=True, text=True,
                           timeout=600)
        if r.returncode != 0:
            sys.stderr.write(r.stderr[-300:])
            continue
        # CLI writes <fname>.zip for single-file pulls? Accept either; normalize.
        zip_path = os.path.join(DEST, fname + ".zip")
        raw_path = os.path.join(DEST, fname)
        src = zip_path if os.path.exists(zip_path) else raw_path
        if src.endswith(".zip"):
            subprocess.run([sys.executable, "-c",
                            f"import zipfile; zipfile.ZipFile({src!r}).extractall({DEST!r})"],
                           check=True, timeout=300)
            os.remove(zip_path)
        got = os.path.join(DEST, fname)
        if os.path.exists(got):
            json.load(open(got))          # validate before declaring victory
            print(f"{ep}: ok ({os.path.getsize(got)} bytes)")
        else:
            sys.stderr.write(f"{ep}: download vanished\n")


if __name__ == "__main__":
    main()
