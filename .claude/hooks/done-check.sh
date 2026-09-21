#!/usr/bin/env bash
# Stop: fires when the assistant finishes a turn.
# Reminds about the worklog and the weekly exit test. Never blocks (exit 0 always).

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

week="$(current_week)"
(( week < 1 || week > 22 )) && exit 0

log="$REPO_ROOT/docs/worklog/W$(printf '%02d' "$week").md"
today="$(date +%Y-%m-%d)"
msgs=()

if [[ ! -f "$log" ]]; then
  msgs+=("· No worklog for W$week yet — run \`/week\` to open it.")
elif ! grep -q "$today" "$log" 2>/dev/null; then
  msgs+=("· No W$week worklog entry for $today — run \`/log\` before you stop.")
fi

task="$(active_task)"
if [[ -n "$task" ]] && ! implementation_unlocked; then
  msgs+=("· Task '$task' is still LOCKED — outstanding design phase. \`/task-status\`")
fi

if [[ -n "$task" ]] && implementation_unlocked; then
  msgs+=("· Task '$task' is open. When the work is done: \`/verify\` → \`/ai-review\` → \`/done\`.")
fi

if (( ${#msgs[@]} )); then
  printf 'W%s checklist:\n' "$week"
  printf '%s\n' "${msgs[@]}"
fi
exit 0
