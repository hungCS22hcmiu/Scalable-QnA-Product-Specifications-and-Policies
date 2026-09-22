#!/usr/bin/env bash
# Stop: fires when the assistant finishes a turn.
# Reminds about the journal and the open task. Never blocks (exit 0 always).
#
# Weeks were removed 2026-09-21 (Pre-thesis_Sweeping.md #4). The worklog was one file per
# week; it is now one append-only journal, because dropping weeks would otherwise drop the
# chronology and the hours, and the write-up needs both (docs/worklog/README.md).

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

journal="$REPO_ROOT/docs/worklog/journal.md"
today="$(date +%Y-%m-%d)"
msgs=()

if [[ ! -f "$journal" ]]; then
  msgs+=("· No docs/worklog/journal.md — run \`/log\` to start it.")
elif ! grep -q "$today" "$journal" 2>/dev/null; then
  msgs+=("· No journal entry for $today — run \`/log\` before you stop.")
fi

[[ -z "$(current_phase)" ]] && msgs+=("· Phase is UNSET — \`/phase <n>\` so the banner and \`/gate\` know what to test.")

task="$(active_task)"
if [[ -n "$task" ]]; then
  scope="$(task_scope)"
  if [[ -z "$scope" ]]; then
    msgs+=("· Task '$task' has no SCOPE — the gate will refuse source edits. \`/task-status\`")
  elif ! implementation_unlocked; then
    msgs+=("· Task '$task' (scope $scope) is LOCKED — a design phase is outstanding. \`/task-status\`")
  else
    msgs+=("· Task '$task' is open. When the work is done: \`/verify\` → \`/ai-review\` → \`/done\`.")
  fi
fi

if (( ${#msgs[@]} )); then
  printf 'Checklist:\n'
  printf '%s\n' "${msgs[@]}"
fi
exit 0
