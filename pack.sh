#!/usr/bin/env bash
# Build submission.tar.gz and prove the archive plays the agent that was measured.
#   bash pack.sh            # -> submission.tar.gz, verified on 8 episodes
#   SEEDS=8 bash pack.sh    # verify harder
#
# `submit.sh` calls this and will not upload without it. The reason it is a separate step with
# its own verification is that a tarball is a second copy of the agent, and a second copy is a
# chance to ship something other than what the panel measured. A missing kagfarm/__init__.py, a
# module left out of the file list, a stale build -- each of those unpacks into a tree that
# imports, falls back to `_safe_pass` on turn one, and banks a few hundred dollars on the ladder
# while every log here stays clean. So this script stages an explicit file list, unpacks its own
# output, plays it, and requires the banks to match the repo bank-for-bank before it declares
# success. Anything less is submitting on faith.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
SEEDS="${SEEDS:-4}"
OPPS="${OPPS:-starter,heuristic}"
OUT="submission.tar.gz"

# macOS `tar` writes AppleDouble `._` entries for any file carrying extended attributes, and
# files that have been through a Finder folder generally do. Harmless locally, unexplained junk
# in a submission archive.
export COPYFILE_DISABLE=1

SHIP_ROOT=(main.py)
SHIP_PKG=(kagfarm/__init__.py kagfarm/constants.py kagfarm/route.py kagfarm/policy.py)
# Data file for the opening book (opening_book=1 reads it). Optional by design: the
# loader tolerates absence (planner fallback), so bundle.py's single-file variant
# ships without it and still plays.
SHIP_DATA=(kagfarm/opening_book.json)

for f in "${SHIP_ROOT[@]}" "${SHIP_PKG[@]}"; do
  [ -f "$f" ] || { echo "!! $f is missing — nothing to pack."; exit 1; }
done
for f in "${SHIP_DATA[@]}"; do
  [ -f "$f" ] || { echo "   (note: $f absent — shipping without the opening book)"; SHIP_DATA=(); break; }
done

# Every .py under kagfarm/ has to be in SHIP_PKG. Listing the files explicitly is what keeps
# __pycache__ and stray probes out of the archive; this check is what stops that explicitness
# from silently dropping a module someone adds later.
for f in kagfarm/*.py; do
  case " ${SHIP_PKG[*]} " in
    *" $f "*) ;;
    *) echo "!! $f exists but is not in SHIP_PKG — add it to pack.sh before submitting."; exit 1;;
  esac
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/stage"
UNPACKED="$TMP/unpacked"
mkdir -p "$STAGE/kagfarm" "$UNPACKED"

cp "${SHIP_ROOT[@]}" "$STAGE/"
cp "${SHIP_PKG[@]}" "$STAGE/kagfarm/"
if [ "${#SHIP_DATA[@]}" -gt 0 ]; then cp "${SHIP_DATA[@]}" "$STAGE/kagfarm/"; fi

# `-C "$STAGE"` puts main.py at the archive root. The harness looks for it there; a leading
# directory is the difference between a ranked submission and a validation error.
tar -czf "$OUT" -C "$STAGE" main.py kagfarm

echo "==> $OUT ($(wc -c <"$OUT" | tr -d ' ') bytes)"
tar -tzf "$OUT" | sed 's/^/    /'

if tar -tzf "$OUT" | grep -Eq '__pycache__|\.pyc$|\.DS_Store|/\._'; then
  echo "!! build junk in the archive — fix pack.sh before submitting."; exit 1
fi

# The single-file fallback, for a harness that wants one file and nothing else. Regenerated here
# so it can never lag the tarball, but not fatal: the tarball is the artifact being submitted and
# it is verified below on its own terms. A failure here means the flattening broke, which is worth
# looking at and not worth blocking a submission on.
if [ -f bundle.py ]; then
  "$PY" bundle.py --seeds 2 >"$TMP/bundle.log" 2>&1 \
    && echo "==> single-file fallback: submission/main.py (verified)" \
    || { echo "!! bundle.py failed — single-file fallback is stale. Tail:";
         tail -4 "$TMP/bundle.log" | sed 's/^/    /'; }
fi

tar -xzf "$OUT" -C "$UNPACKED"

echo "==> verifying the unpacked archive on $SEEDS seeds x $OPPS"
"$PY" verify_pack.py "$UNPACKED" --seeds "$SEEDS" --opps "$OPPS" >"$TMP/packed.json"
"$PY" verify_pack.py .          --seeds "$SEEDS" --opps "$OPPS" >"$TMP/repo.json"

if ! cmp -s "$TMP/packed.json" "$TMP/repo.json"; then
  echo "!! the unpacked archive does not play like the repo:"
  diff "$TMP/repo.json" "$TMP/packed.json" | sed 's/^/    /' || true
  exit 1
fi

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
DIRTY=""
git diff --quiet 2>/dev/null || DIRTY=" +uncommitted"
echo "==> PACK OK — archive plays the repo build bank-for-bank (commit ${SHA}${DIRTY})"
