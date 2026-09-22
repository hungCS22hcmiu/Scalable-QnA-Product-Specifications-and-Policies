#!/usr/bin/env bash
# Stop: fires when the assistant finishes a turn.
# Reminds about the open task. Never blocks (exit 0 always).
#
# The journal reminder was removed 2026-09-22 together with /log and /gate: nagging for a
# daily entry would ask for a file nothing writes. What remains here is task state.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

msgs=()

[[ -z "$(current_phase)" ]] && msgs+=("· Phase is UNSET — \`/phase <n>\` so the banner knows which exit criterion to print.")

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
