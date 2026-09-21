#!/usr/bin/env bash
# UserPromptSubmit: stdout is injected into the session context.
# Keeps every prompt oriented: which week, what is due, what is unlocked.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

week="$(current_week)"
task="$(active_task)"

printf '<thesis-context>\n'
printf 'Week: W%s' "$week"

if (( week >= 1 && week <= RUNWAY_LAST_WEEK )); then
  printf '  |  phase: pre-thesis runway (submit Aug 31)  |  gate: LIGHTWEIGHT'
  printf '  |  frozen-value tripwire: ARMED\n'
elif (( week >= 8 && week <= 22 )); then
  printf '  |  phase: thesis (complete Dec 13)  |  gate: FULL RIGOR\n'
else
  printf '  |  phase: outside the planned schedule\n'
fi

row="$(week_row "$week")"
if [[ -n "$row" ]]; then
  # column 5 of the time_line row is "Done when" (the Dates column was dropped 2026-09-02)
  done_when="$(printf '%s' "$row" | awk -F'|' '{print $5}' | sed 's/^ *//;s/ *$//')"
  [[ -n "$done_when" ]] && printf 'Done when: %s\n' "$done_when"
fi

if [[ -n "$task" ]]; then
  printf 'Active task: %s' "$task"
  implementation_unlocked && printf '  (implementation UNLOCKED)\n' || printf '  (implementation LOCKED)\n'
else
  printf 'Active task: none\n'
fi

printf 'Authority: docs/ is frozen source-of-truth · .docs/ai/rules.md is the trip-wire list\n'
printf '</thesis-context>\n'
exit 0
