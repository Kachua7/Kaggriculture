#!/usr/bin/env bash
# Checkpoint the repo:   bash snapshot.sh "melon wave working"
#
# Exists because my sandbox can create git's lock files but not delete them, so
# git run from my side works exactly once and then jams. Running this from your
# shell clears the locks and commits. If you'd rather I just handle commits
# myself, grant file-delete permission when I ask and this script becomes
# unnecessary.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-checkpoint}"

rm -f .git/*.lock .git/objects/maintenance.lock .writetest 2>/dev/null || true
rmdir .gittest 2>/dev/null || true

if [ ! -d ".git" ]; then
  git init -q
fi

git add -A
if git diff --cached --quiet; then
  echo "nothing to commit."
else
  git commit -q -m "$MSG"
  echo "committed: $MSG"
fi

echo
git log --oneline | head -10
