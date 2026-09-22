#!/usr/bin/env bash
# Shared helpers for thesis repo hooks.
# Sourced, never executed directly. Hooks block by exiting 2 with a message on stderr.

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WORK_DIR="$REPO_ROOT/docs/work"
STATE_DIR="$REPO_ROOT/.claude/state"

# Weeks were removed 2026-09-21. The schedule is phases with binary exit criteria, and
# rigor is set by the SCOPE of a change rather than by the calendar.
#
# The docs tree was consolidated 2026-09-22 and task trails live in `docs/work/`. The
# frozen-value guard and the scope gate were removed in the same pass, because both read
# files that no longer exist — a guard that silently fails open is worse than no guard,
# since it still reads as protection. Rigor is now a convention the commands describe,
# not a mechanism the hooks enforce.
PHASE_FILE="${THESIS_PHASE_FILE:-}"

# --- stdin -------------------------------------------------------------------
# Read the payload ONCE, at source time, into a plain variable.
# It cannot be read lazily inside a function: jqf uses command substitution, which
# runs in a subshell, so any caching done there is discarded and the second read
# gets an already-consumed stdin (silently returning empty — i.e. failing open).
HOOK_JSON=""
if [[ ! -t 0 ]]; then HOOK_JSON="$(cat)"; fi

hook_stdin() { printf '%s' "$HOOK_JSON"; }

jqf() { # jqf <filter> [default]
  local out
  out="$(printf '%s' "$HOOK_JSON" | jq -r "$1 // empty" 2>/dev/null)" || out=""
  printf '%s' "${out:-${2:-}}"
}

tool_name()  { jqf '.tool_name'; }
tool_path()  { jqf '.tool_input.file_path'; }

# --- phase -------------------------------------------------------------------
# Explicit state, not derived from the calendar: a phase ends when its exit criterion
# passes, which is a binary test and not a date. Unset is a legitimate state and is
# reported as such rather than guessed at.
current_phase() {
  local f="${PHASE_FILE:-$STATE_DIR/phase}"
  [[ -f "$f" ]] || { printf ''; return; }
  tr -cd '0-9' < "$f"
}

phase_row() {
  local n="${1:-$(current_phase)}"
  [[ -z "$n" ]] && return 1
  grep -E "^### Phase $n — " "$REPO_ROOT/docs/super-plan.md" 2>/dev/null | head -1
}

# The binary test that closes the phase: the `**Exit:**` line under the heading -- NOT
# the heading itself, which names the phase rather than the test.
phase_exit_criterion() {
  local n="${1:-$(current_phase)}"
  [[ -z "$n" ]] && return 1
  awk -v n="$n" '
    $0 ~ "^### Phase " n " \xe2\x80\x94 " { f = 1; next }
    f && /^\*\*Exit:\*\*/ { sub(/^\*\*Exit:\*\*[[:space:]]*/, ""); print; exit }
    f && /^### / { exit }
  ' "$REPO_ROOT/docs/super-plan.md" 2>/dev/null
}

# --- active task -------------------------------------------------------------
active_task() { cat "$STATE_DIR/active-task" 2>/dev/null | tr -d '[:space:]'; }

task_dir() { local t; t="$(active_task)"; [[ -n "$t" ]] && printf '%s/%s' "$WORK_DIR" "$t"; }

implementation_unlocked() {
  local d; d="$(task_dir)"
  [[ -n "$d" && -f "$d/READY_TO_IMPLEMENT" ]]
}

# --- scope -------------------------------------------------------------------
# L / M / S, written by /task into the trail. Rigor is a property of the CHANGE, not of
# the date. Unset is NOT defaulted to S: an unlabelled task would otherwise take the
# cheapest path, which is the failure mode three tiers invite.
task_scope() {
  local d; d="$(task_dir)"
  [[ -n "$d" && -f "$d/SCOPE" ]] || { printf ''; return; }
  tr -cd 'LMS' < "$d/SCOPE" | head -c 1
}

scope_requires() { # scope -> space-separated list of required trail files
  case "${1:-}" in
    L) printf 'spec.md impact.md design.md review.md plan.md' ;;
    M) printf 'spec.md impact.md plan.md' ;;
    S) printf 'spec.md' ;;
    *) return 1 ;;
  esac
}

scope_label() {
  case "${1:-}" in
    L) printf 'LARGE — spec → impact → design → opus design-review → plan' ;;
    M) printf 'MEDIUM — spec → impact → plan' ;;
    S) printf 'SMALL — spec only (one paragraph)' ;;
    *) printf 'UNSET' ;;
  esac
}

# --- path classification -----------------------------------------------------
rel_path() { # absolute -> repo-relative
  local p="${1:-}"
  printf '%s' "${p#"$REPO_ROOT"/}"
}

is_source() {
  case "$(rel_path "${1:-}")" in
    gateway/*|rag/*|contracts/*|experiments/scripts/*|experiments/k6/*) return 0 ;;
    *) return 1 ;;
  esac
}

# --- output ------------------------------------------------------------------
block() { printf '%s\n' "$*" >&2; exit 2; }   # exit 2 = block the tool call
allow() { exit 0; }
note()  { printf '%s\n' "$*"; exit 0; }        # stdout is surfaced to the session
