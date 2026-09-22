#!/usr/bin/env bash
# UserPromptSubmit: stdout is injected into the session context.
# Keeps every prompt oriented: which phase, what closes it, what is unlocked.
#
# Weeks were removed 2026-09-21. A week number told you the date; it did not tell you what
# you were trying to finish. Phase + exit criterion does.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

phase="$(current_phase)"
task="$(active_task)"
scope="$(task_scope)"

printf '<thesis-context>\n'

if [[ -n "$phase" ]]; then
  printf 'Phase: %s' "$phase"
else
  printf 'Phase: UNSET — run `/phase <n>` to set it'
fi
printf '  |  thesis, complete Dec 13\n'

crit="$(phase_exit_criterion 2>/dev/null)"
[[ -n "$crit" ]] && printf 'Exit criterion: %s\n' "$crit"

if [[ -n "$task" ]]; then
  printf 'Active task: %s  (scope %s)' "$task" "${scope:-UNSET}"
  implementation_unlocked && printf '  — implementation UNLOCKED\n' || printf '  — implementation LOCKED\n'
else
  printf 'Active task: none\n'
fi

printf 'Authority: docs/super-plan.md is the plan · docs/contracts/ is the seam\n'
printf '</thesis-context>\n'
exit 0
