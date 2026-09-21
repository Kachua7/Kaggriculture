#!/usr/bin/env bash
# Checkpoint the repo:   bash snapshot.sh "melon wave working"
#
# Originally existed because my sandbox could create git's lock files but not
# delete them, so git run from my side worked exactly once and then jammed. That
# permission has since been granted, so I commit directly now and you should not
# need this -- it is kept because it also clears the stale locks and supplies a
# git identity the sandbox user does not have.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-checkpoint}"

rm -f .git/*.lock .git/refs/heads/*.lock .git/objects/maintenance.lock 2>/dev/null || true
find .git/objects -name 'tmp_obj_*' -delete 2>/dev/null || true

if [ ! -d ".git" ]; then
  git init -q
fi

# The sandbox user has no git identity of its own. Fall back to the repo's own
# history rather than writing anything into git config.
if ! git config user.email >/dev/null 2>&1; then
  export GIT_AUTHOR_NAME="$(git log -1 --format=%an 2>/dev/null || echo kagfarm)"
  export GIT_AUTHOR_EMAIL="$(git log -1 --format=%ae 2>/dev/null || echo kagfarm@localhost)"
  export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
  export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
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
