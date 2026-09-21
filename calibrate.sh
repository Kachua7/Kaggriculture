#!/usr/bin/env bash
# Generate ground-truth traces from the real engine. Run after bootstrap.sh:
#     bash calibrate.sh
# Writes calibration/truth.json, which I read directly out of this folder.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "!! .venv missing — run 'bash bootstrap.sh' first."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python calibration/dump_truth.py
echo
echo "Done. Tell me it finished and I'll take it from there."
