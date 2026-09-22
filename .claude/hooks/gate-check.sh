#!/usr/bin/env bash
# PreToolUse: Edit|Write|MultiEdit
#
# The phase gate. Blocks source edits until the active task has produced the design
# documents ITS SCOPE requires and a human ran `/approve implementation` (which writes
# READY_TO_IMPLEMENT).
#
# Calibration by SCOPE, not by date (Pre-thesis_Sweeping.md #4, 2026-09-21). It used to
# switch from lightweight to full rigor at W8 on the calendar (ADR-020). Two things were
# wrong with that: a one-line fix late in the schedule paid ceremony it never needed, and
# a seam change early in the schedule paid none when it always did. Rigor now tracks what
# the change touches.
#
#   L  spec → impact → design → opus design-review → plan   (frozen artifacts, seams, reuse/)
#   M  spec → impact → plan                                  (ordinary code)
#   S  spec (one paragraph)                                  (tests, docs, comments, one-liners)
#
# Every scope still ends at a human `/approve implementation`. S is cheap because it needs
# ONE document before that approval, not because it skips the human — an unapproved path
# is a bypass route, and three tiers with a free one is how a gate stops meaning anything.
#
# frozen-guard.sh is ARMED AT EVERY SCOPE and is a separate hook. Nothing here relaxes it.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

command -v jq >/dev/null 2>&1 || allow

path="$(tool_path)"
[[ -z "$path" ]] && allow
is_source "$path" || allow          # docs, .docs/, config: never phase-gated

task="$(active_task)"

if [[ -z "$task" ]]; then
  block "BLOCKED — no active task.

  file: $(rel_path "$path")

Source edits under gateway/, rag/, contracts/, experiments/ require an open task with a
design trail. Pick the opener that matches the work:

  /feature <slug>      new behaviour            (defaults to scope M)
  /bugfix <slug>       something is wrong       (defaults to scope S)
  /refactor <slug>     same behaviour, better   (defaults to scope M)
  /investigate <slug>  find out, do not build   (no source edits at all)
  /task <slug> <L|M|S> when none of those fit

Governing: .docs/README.md · .claude/README.md"
fi

scope="$(task_scope)"

if [[ -z "$scope" ]]; then
  block "BLOCKED — task '$task' has no SCOPE.

  file: $(rel_path "$path")

The gate calibrates on scope and will not guess one: an unlabelled task would take the
cheapest path by default, which is exactly the hole three tiers invite. Write one letter
to .docs/work/$task/SCOPE:

  L   touches a frozen document, interfaces.md, the .proto, or reuse/ — the reuse
      decision and the measured seam are where a silent error costs a whole study
  M   ordinary code: a package, a handler, a script
  S   tests, docs, comments, a one-line fix

If you are unsure between two, take the larger. Governing: .claude/README.md"
fi

d="$(task_dir)"
required="$(scope_requires "$scope")"

missing=""
have=""
for f in $required; do
  if [[ -f "$d/$f" ]]; then have+="  ✓ $f"$'\n'; else have+="  ✗ $f  (missing)"$'\n'; missing+=" $f"; fi
done

if [[ -n "$missing" ]]; then
  block "BLOCKED — task '$task' (scope $scope) is missing design documents.

  file: $(rel_path "$path")

$(scope_label "$scope")

Trail at .docs/work/$task/:
$have
Produce the missing ones, then \`/approve implementation\`. If this change turned out to be
smaller than it looked, lower the scope deliberately in SCOPE and say why in spec.md —
do not leave a document unwritten under a scope that asks for it.

Governing: .docs/README.md · .docs/ai/architecture-guardrails.md"
fi

if ! implementation_unlocked; then
  block "BLOCKED — task '$task' (scope $scope) has its documents but no human approval.

  file: $(rel_path "$path")

Every scope ends here, including S. Implementation unlocks only when a human runs:

  /approve impact            after reviewing impact.md        (L, M)
  /approve contract          if the change touches interfaces.md surfaces
  /approve experiment        if the change touches what or how anything is measured
  /approve implementation    writes READY_TO_IMPLEMENT and unlocks source edits

Run \`/task-status\` to see which phase is outstanding.
Governing: .docs/README.md"
fi

allow
