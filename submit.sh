#!/usr/bin/env bash
# Pack + submit to the ladder:   bash submit.sh "melon wave v3"
# Requires: bootstrap.sh has run, and you've accepted the rules at
# https://www.kaggle.com/competitions/kaggriculture/rules
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-kagfarm}"

if [ ! -d ".venv" ]; then
  echo "!! .venv missing — run 'bash bootstrap.sh' first."
  exit 1
fi
if [ ! -f "pack.sh" ]; then
  echo "!! pack.sh missing — the agent package isn't built yet."
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

bash pack.sh
echo "==> submitting: $MSG"
kaggle competitions submit kaggriculture -f submission.tar.gz -m "$MSG"

echo
echo "==> recent submissions"
kaggle competitions submissions kaggriculture | head -12
