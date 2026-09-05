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

echo "==> creating virtualenv at $VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> installing kaggle-environments + kaggle CLI (inside the venv only)"
python -m pip install --upgrade pip -q
python -m pip install --upgrade kaggle-environments kaggle -q

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
  echo "     source $VENV/bin/activate && pip install -U 'kaggle-environments>=1.32.7'"
  exit 1
fi

echo "==> copying engine source -> $OUT/real_engine/"
cp -R "$ENVDIR"/. "$OUT/real_engine/"
rm -rf "$OUT/real_engine/__pycache__"

echo "==> writing version + file manifest"
python - <<PY > "$OUT/versions.txt"
import kaggle_environments as ke, sys, os
print("kaggle_environments", getattr(ke, "version", "?"))
print("python", sys.version.replace("\n", " "))
PY

find "$OUT/real_engine" -type f | sort >> "$OUT/versions.txt"

echo
echo "Done. Engine source is now in $OUT/real_engine/ — that is all I need."
echo "Next: run  bash calibrate.sh  to generate the ground-truth episode traces."
