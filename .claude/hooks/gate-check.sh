#!/usr/bin/env bash
# PreToolUse: Edit|Write|MultiEdit
#
# The phase gate. Blocks source edits until the active task has passed its design
# phases and a human ran `/approve implementation` (which writes READY_TO_IMPLEMENT).
#
# Calibration (ADR-020): W5-W7 runway = LIGHTWEIGHT (this gate allows; frozen-guard.sh
# still runs). W8+ = FULL RIGOR. The switch is computed from the calendar, not stored.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

command -v jq >/dev/null 2>&1 || allow

path="$(tool_path)"
[[ -z "$path" ]] && allow
is_source "$path" || allow          # docs, .docs/, config: never phase-gated

week="$(current_week)"

# --- runway: lightweight -----------------------------------------------------
if in_runway; then
  # Allow, but leave a trail marker so /task-status can show unguarded source work.
  if [[ -z "$(active_task)" ]]; then
    printf 'W%s runway — lightweight gate: source edit allowed with no active task.\n' "$week"
    printf 'Consider `/task <slug>` if this is more than a few lines; full rigor resumes W8.\n'
  fi
  allow
fi

# --- W8+: full rigor ---------------------------------------------------------
task="$(active_task)"

if [[ -z "$task" ]]; then
  block "BLOCKED — no active task (W$week: full rigor is in force).

  file: $(rel_path "$path")

Source edits under gateway/, rag/, contracts/, experiments/ require an open task with a
design trail.

  /task <slug>     open the trail (spec → impact → design → approvals)

Governing: .docs/README.md · ADR-020 (rigor switches on at W8)"
fi

if ! implementation_unlocked; then
  d="$(task_dir)"
  have=""
  for f in spec impact plan; do
    [[ -f "$d/$f.md" ]] && have+="  ✓ $f.md"$'\n' || have+="  ✗ $f.md  (missing)"$'\n'
  done

  block "BLOCKED — task '$task' has not been approved for implementation.

  file: $(rel_path "$path")

Design trail at .docs/work/$task/:
$have
Implementation unlocks only when a human runs:

  /approve impact            after reviewing impact.md
  /approve contract          if the change touches interfaces.md surfaces
  /approve experiment        if the change touches what/how anything is measured
  /approve implementation    writes READY_TO_IMPLEMENT and unlocks source edits

Run \`/task-status\` to see which phase is outstanding.
Governing: .docs/README.md · .docs/ai/architecture-guardrails.md"
fi

allow
