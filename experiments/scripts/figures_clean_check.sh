#!/usr/bin/env bash
# Item 5.4, done condition 6: the figures come out the same from a clean checkout plus the raw archive.
#
#   make figures-clean-check
#
# 1. `make figures` in the working tree; the sha256 of every file under each run's figures/ is recorded.
# 2. The repository's tracked files plus its untracked, not-ignored files (`git ls-files --cached --others
#    --exclude-standard`) are copied into an empty temp folder, removed on exit. It must hold no raw/, judge/ or
#    figures/ folder of a run: those are gitignored, which is the point of the test.
# 3. In the copy, with RESULTS_DIR unset, `make figures` must exit non-zero, and its output must name raw/.
# 4. For each run that has an archive.sha256: `make raw-restore RUN_ID=<id>`, then `make raw-check RUN_ID=<id>`;
#    both must exit 0.
# 5. `make figures` in the copy must exit 0, and every figure file must have the sha256 of step 1.
#
# Prints one line per step, then `IDENTICAL <n> files`, or each differing file. Exit 0 only when all five hold.
# Reads the archive (RAW_ARCHIVE_DIR, default ~/thesis-raw-archive); writes only the working tree's figures/ and
# the temp copy. Loads no model; citable: no.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
unset RESULTS_DIR
export RAW_ARCHIVE_DIR="${RAW_ARCHIVE_DIR:-$HOME/thesis-raw-archive}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
COPY="$WORK/copy"
mkdir "$COPY"

fail() { echo "FAIL: $*" >&2; exit 1; }

# sums <tree>: "<sha256>  <path>" for every file under a run's figures/, paths relative to the tree, sorted.
sums() {
  (cd "$1" && find experiments/results -path '*/figures/*' -type f -print0 | sort -z | xargs -0 shasum -a 256) || true
}

# quiet <log> <command...>: run it, keep its output in <log>, and return its exit code.
quiet() {
  local log="$1"; shift
  "$@" >"$log" 2>&1
}

# --- 1. the working tree --------------------------------------------------------------------------------------
quiet "$WORK/step1.log" make figures || { cat "$WORK/step1.log"; fail "step 1: make figures failed in the working tree"; }
sums "$ROOT" > "$WORK/before.sha"
N="$(wc -l < "$WORK/before.sha" | tr -d ' ')"
[ "$N" -gt 0 ] || fail "step 1: make figures wrote no figure file"
echo "step 1: make figures in the working tree, $N figure files hashed"

# --- 2. the clean copy ----------------------------------------------------------------------------------------
git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' f; do
  if [ -e "$f" ] || [ -L "$f" ]; then printf '%s\0' "$f"; fi
done > "$WORK/files.list"
tar --null -T "$WORK/files.list" -cf - | tar -xf - -C "$COPY"
for folder in raw judge figures; do
  if compgen -G "$COPY/experiments/results/*/$folder" > /dev/null; then
    fail "step 2: the copy holds a results/*/$folder/ before the restore, so the test would prove nothing"
  fi
done
echo "step 2: clean copy of $(tr -cd '\0' < "$WORK/files.list" | wc -c | tr -d ' ') files, with no raw/, judge/ or figures/"

# --- 3. make figures must refuse ------------------------------------------------------------------------------
if (cd "$COPY" && env -u RESULTS_DIR make figures) > "$WORK/step3.log" 2>&1; then
  cat "$WORK/step3.log"
  fail "step 3: make figures exited 0 in the clean copy, which has no raw/"
fi
grep -q 'raw/' "$WORK/step3.log" || { cat "$WORK/step3.log"; fail "step 3: make figures failed, but its output does not name raw/"; }
echo "step 3: make figures exits non-zero in the copy and names the missing raw/"

# --- 4. restore and check -------------------------------------------------------------------------------------
RUNS=0
for list in "$COPY"/experiments/results/*/archive.sha256; do
  [ -e "$list" ] || continue
  RUN_ID="$(basename "$(dirname "$list")")"
  (cd "$COPY" && env -u RESULTS_DIR make raw-restore RUN_ID="$RUN_ID") > "$WORK/step4-$RUN_ID.log" 2>&1 \
    || { cat "$WORK/step4-$RUN_ID.log"; fail "step 4: make raw-restore failed for $RUN_ID"; }
  (cd "$COPY" && env -u RESULTS_DIR make raw-check RUN_ID="$RUN_ID") >> "$WORK/step4-$RUN_ID.log" 2>&1 \
    || { cat "$WORK/step4-$RUN_ID.log"; fail "step 4: make raw-check failed for $RUN_ID after the restore"; }
  RUNS=$((RUNS + 1))
done
[ "$RUNS" -gt 0 ] || fail "step 4: no run has an archive.sha256, so there was nothing to restore"
echo "step 4: restored and checked $RUNS run(s) from $RAW_ARCHIVE_DIR"

# --- 5. the same figures --------------------------------------------------------------------------------------
(cd "$COPY" && env -u RESULTS_DIR make figures) > "$WORK/step5.log" 2>&1 \
  || { cat "$WORK/step5.log"; fail "step 5: make figures failed in the copy after the restore"; }
sums "$COPY" > "$WORK/after.sha"
if diff "$WORK/before.sha" "$WORK/after.sha" > "$WORK/step5.diff"; then
  echo "step 5: IDENTICAL $N files"
else
  cat "$WORK/step5.diff"
  fail "step 5: the figures differ between the working tree and the clean copy"
fi
