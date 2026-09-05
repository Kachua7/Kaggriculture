#!/usr/bin/env bash
# Pack + submit to the ladder:   bash submit.sh "melon wave v3"
#                               bash submit.sh "melon wave v3" single   # one-file fallback
# Requires: bootstrap.sh has run, and you've accepted the rules at
# https://www.kaggle.com/competitions/kaggriculture/rules
#
# Two artifacts, because the harness's preference is not documented anywhere I can read and
# submission day is the wrong time to find out. The default is the tarball (main.py at the
# archive root plus the kagfarm package, which is the layout every Kaggle simulation competition
# has used); pass `single` to upload `submission/main.py` instead, which is the same agent
# flattened into one file and verified against the package build. If one is rejected, try the
# other -- do not start debugging.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-kagfarm}"
MODE="${2:-tar}"

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

case "$MODE" in
  single) FILE="submission/main.py" ;;
  *)      FILE="submission.tar.gz" ;;
esac
[ -f "$FILE" ] || { echo "!! $FILE not built — see the pack.sh output above."; exit 1; }

echo "==> submitting $FILE: $MSG"
kaggle competitions submit kaggriculture -f "$FILE" -m "$MSG"

echo
echo "==> recent submissions"
kaggle competitions submissions kaggriculture | head -12
