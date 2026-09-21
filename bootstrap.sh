#!/usr/bin/env bash
# One-time setup — run this once, from the repo root:   bash bootstrap.sh
#
# Creates a self-contained virtualenv inside the repo (.venv), installs the real
# Kaggle engine into it, then copies the engine's source and a constants dump into
# calibration/ so the agent can be checked against ground truth.
#
# Your system Python is not touched. Nothing outside this folder is modified.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
OUT="calibration"

# Pinned engine version — the reference this repo calibrates against. Bump only together
# with calibration/engine/MANIFEST.sha256 and calibration/live.md.
ENGINE_PIN="1.32.7"
# The wheel requires >=3.11; macOS system python3 is often 3.9. Use the newest interpreter
# present, preferring the framework 3.13.
PYBIN="$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)"

# Clear any stale git lock files while we're running with your permissions. Harmless
# if there are none.
rm -f .git/*.lock .git/refs/heads/*.lock .git/objects/maintenance.lock 2>/dev/null || true

echo "==> creating virtualenv at $VENV ($("$PYBIN" --version))"
"$PYBIN" -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> installing kaggle-environments==$ENGINE_PIN + kaggle CLI (inside the venv only)"
python -m pip install --upgrade pip -q
python -m pip install "kaggle-environments==$ENGINE_PIN" kaggle -q
# Assert the pin actually landed; the whole calibration story depends on this exact source.
python - <<PY
import kaggle_environments as ke
v = getattr(ke, "__version__", None)
if v is None:
    fv = getattr(ke, "version", None)
    v = fv() if callable(fv) else fv
v = str(v or "")
assert v.startswith("$ENGINE_PIN"), f"pinned $ENGINE_PIN not installed, got {v}"
print("kaggle-environments", v, "OK")
PY

mkdir -p "$OUT/real_engine"

echo "==> locating the installed kaggriculture environment"
ENVDIR="$(python - <<'PY'
import os, kaggle_environments
print(os.path.join(os.path.dirname(kaggle_environments.__file__), "envs", "kaggriculture"))
PY
)"

if [ ! -d "$ENVDIR" ]; then
  echo "!! kaggriculture env not found at: $ENVDIR"
  echo "   The installed kaggle-environments may be too old. Try:"
  echo "     source $VENV/bin/activate && pip install -U 'kaggle-environments>=$ENGINE_PIN'"
  exit 1
fi

echo "==> copying engine source -> $OUT/real_engine/"
cp -R "$ENVDIR"/. "$OUT/real_engine/"
rm -rf "$OUT/real_engine/__pycache__"

# Content-pin the vendored files: a hash manifest committed to git is what makes
# "calibrated against <pin>" a checkable claim rather than a memory.
mkdir -p "$OUT/engine"
for f in kaggriculture.py kaggriculture.json; do
  cp "$ENVDIR/$f" "$OUT/engine/$f"
done
( cd "$OUT/engine" && shasum -a 256 kaggriculture.py kaggriculture.json > MANIFEST.sha256 )
echo "==> manifest: $OUT/engine/MANIFEST.sha256"
cat "$OUT/engine/MANIFEST.sha256"

echo "==> writing version + file manifest"
python - <<PY > "$OUT/versions.txt"
import kaggle_environments as ke, sys, os
print("kaggle_environments", getattr(ke, "version", "?"))
print("python", sys.version.replace("\n", " "))
PY

find "$OUT/real_engine" -type f | sort >> "$OUT/versions.txt"

echo
echo "Done. Engine source is now in $OUT/real_engine/ and content-pinned in $OUT/engine/ —"
echo "with the real rules readable in this folder, open calibration items are settled by"
echo "reading code instead of inferring them from traces."
echo
echo "==> running calibrate.sh for you (ground-truth episode traces)"
echo "    This scripts ~60 short episodes and takes a few minutes. Safe to Ctrl-C:"
echo "    the engine source above is already saved, and you can re-run"
echo "    'bash calibrate.sh' any time."
echo
exec bash calibrate.sh
