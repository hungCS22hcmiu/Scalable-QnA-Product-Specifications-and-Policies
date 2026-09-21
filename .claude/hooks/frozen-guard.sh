#!/usr/bin/env bash
# PreToolUse: Edit|Write|MultiEdit
#
# ALWAYS ARMED — including the W5-W7 runway, where phase gating is otherwise off.
# W5 is precisely when ADR-003/014/017 freeze their values, so this is the week the
# tripwire matters most. See .docs/ai/rules.md #1.
#
# Blocks an edit that appears to change a frozen experimental value unless the active
# task's approvals.md cites an ADR.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

command -v jq >/dev/null 2>&1 || allow   # fail open if jq is missing; never wedge the session

# Payload present but unparseable: surface it rather than silently allowing a guarded edit.
if [[ -n "$HOOK_JSON" ]] && ! hook_json_ok; then
  block "BLOCKED — frozen-guard received a malformed hook payload and cannot verify this edit.

Refusing to fail open on a guarded path. If this recurs, check .claude/hooks/lib.sh
or disable the hook deliberately in .claude/settings.json — do not ignore it."
fi

path="$(tool_path)"
[[ -z "$path" ]] && allow

# --- write-once raw results (rules.md #3) ------------------------------------
if is_raw_results "$path"; then
  block "BLOCKED — experiments/results/*/raw/ and manifest.yaml are WRITE-ONCE.

  $(rel_path "$path")

Raw output and run manifests are immutable once written (experiment-protocol.md §3,
.docs/ai/rules.md #3). Figures regenerate FROM raw via \`make figures\` — never the reverse.

If a run is wrong, record a new run_id. Do not edit history."
fi

# --- direct edits to the frozen documents ------------------------------------
if is_frozen_doc "$path" && ! adr_cited; then
  block "BLOCKED — $(rel_path "$path") is a frozen document.

Changes to decisions.md / interfaces.md / experiment-protocol.md require a decision record.

  1. Run \`/adr\` to draft the ADR for this change, or
  2. Cite an existing ADR-NNN in .docs/work/$(active_task)/approvals.md

Governing: interfaces.md 'Versioning' · .docs/ai/rules.md #1"
fi

# --- frozen values inside code/config ----------------------------------------
# Only files where a value can take effect. Documentation that names a frozen value is
# not a risk; scanning it produces false positives that teach you to ignore the guard.
is_value_bearing "$path" || allow

content="$(tool_content)"
[[ -z "$content" ]] && allow
[[ -f "$DOCS_AI/frozen-values.txt" ]] || allow
adr_cited && allow   # human already signed off with an ADR

hits=""
while IFS= read -r pat; do
  [[ -z "$pat" || "$pat" == \#* ]] && continue
  if printf '%s' "$content" | grep -qE "$pat"; then
    hits+="  · $pat"$'\n'
  fi
done < "$DOCS_AI/frozen-values.txt"

[[ -z "$hits" ]] && allow

block "BLOCKED — this edit touches a FROZEN experimental value.

  file:    $(rel_path "$path")
  matched:
$hits
Frozen values (num_ctx, OLLAMA_NUM_PARALLEL, embedding model, DIM, top_k, chunking,
FLAT index, eviction policy, cache capacity, δ, dataset_version) are frozen study-wide.

Why this is blocked rather than warned: changing one produces NO error and NO visible bug.
It silently invalidates every measurement taken before the change, and you find out in W20.

To proceed:
  1. \`/adr\` — record the change, its rationale, and WHICH PRIOR RUNS IT INVALIDATES
  2. Cite that ADR-NNN in .docs/work/<task>/approvals.md
  3. Retry the edit

If you are only READING or reporting these values, no edit is needed.
Governing: interfaces.md 'Frozen study-wide' · experiment-protocol.md §1 · .docs/ai/rules.md #1"
