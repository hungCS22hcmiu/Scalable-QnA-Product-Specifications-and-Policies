#!/usr/bin/env bash
# Shared helpers for thesis repo hooks.
# Sourced, never executed directly. Hooks block by exiting 2 with a message on stderr.

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DOCS_AI="$REPO_ROOT/.docs/ai"
WORK_DIR="$REPO_ROOT/.docs/work"
STATE_DIR="$REPO_ROOT/.claude/state"

# W1 Monday. Weeks are computed from the calendar so there is no state to drift.
# Overridable so the boundary can move if the schedule does (it already has once — ADR-020)
# and so the W8+ path is testable without waiting for the calendar.
WEEK1_START="${THESIS_WEEK1_START:-2026-07-13}"
RUNWAY_LAST_WEEK="${THESIS_RUNWAY_LAST_WEEK:-7}"   # lightweight ≤7; full rigor from W8 (ADR-020)

# --- stdin -------------------------------------------------------------------
# Read the payload ONCE, at source time, into a plain variable.
# It cannot be read lazily inside a function: jqf uses command substitution, which
# runs in a subshell, so any caching done there is discarded and the second read
# gets an already-consumed stdin (silently returning empty — i.e. failing open).
HOOK_JSON=""
if [[ ! -t 0 ]]; then HOOK_JSON="$(cat)"; fi

# A payload that arrived but will not parse is an anomaly, not a no-op. Failing open
# silently would let a guarded edit through on malformed input, so say so loudly.
hook_json_ok() {
  [[ -z "$HOOK_JSON" ]] && return 1
  printf '%s' "$HOOK_JSON" | jq -e . >/dev/null 2>&1
}

hook_stdin() { printf '%s' "$HOOK_JSON"; }

jqf() { # jqf <filter> [default]
  local out
  out="$(printf '%s' "$HOOK_JSON" | jq -r "$1 // empty" 2>/dev/null)" || out=""
  printf '%s' "${out:-${2:-}}"
}

tool_name()  { jqf '.tool_name'; }
tool_path()  { jqf '.tool_input.file_path'; }
# Proposed content: Write uses .content, Edit uses .new_string, MultiEdit uses a list.
tool_content() {
  local c
  c="$(jqf '.tool_input.content')"
  [[ -n "$c" ]] && { printf '%s' "$c"; return; }
  c="$(jqf '.tool_input.new_string')"
  [[ -n "$c" ]] && { printf '%s' "$c"; return; }
  printf '%s' "$HOOK_JSON" | jq -r '[.tool_input.edits[]?.new_string] | join("\n")' 2>/dev/null || true
}

# --- week --------------------------------------------------------------------
current_week() {
  local now w1 days
  now=$(date +%s)
  w1=$(date -j -f "%Y-%m-%d" "$WEEK1_START" +%s 2>/dev/null) || { echo 0; return; }
  days=$(( (now - w1) / 86400 ))
  (( days < 0 )) && { echo 0; return; }
  echo $(( days / 7 + 1 ))
}

in_runway() { local w; w=$(current_week); (( w >= 1 && w <= RUNWAY_LAST_WEEK )); }

week_row() { # the time_line.md row for a week, trimmed
  local w="${1:-$(current_week)}"
  grep -E "^\| \*\*$w\*\*" "$REPO_ROOT/docs/time_line.md" 2>/dev/null | head -1
}

# --- active task -------------------------------------------------------------
active_task() { cat "$STATE_DIR/active-task" 2>/dev/null | tr -d '[:space:]'; }

task_dir() { local t; t="$(active_task)"; [[ -n "$t" ]] && printf '%s/%s' "$WORK_DIR" "$t"; }

implementation_unlocked() {
  local d; d="$(task_dir)"
  [[ -n "$d" && -f "$d/READY_TO_IMPLEMENT" ]]
}

# An ADR is cited for a frozen change when approvals.md references ADR-NNN.
adr_cited() {
  local d; d="$(task_dir)"
  [[ -n "$d" && -f "$d/approvals.md" ]] && grep -qE 'ADR-[0-9]{3}' "$d/approvals.md"
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

is_frozen_doc() {
  case "$(rel_path "${1:-}")" in
    docs/decisions.md|docs/interfaces.md|docs/experiment-protocol.md) return 0 ;;
    *) return 1 ;;
  esac
}

is_raw_results() {
  case "$(rel_path "${1:-}")" in
    experiments/results/*/raw/*|experiments/results/*/manifest.yaml) return 0 ;;
    *) return 1 ;;
  esac
}

# --- output ------------------------------------------------------------------
block() { printf '%s\n' "$*" >&2; exit 2; }   # exit 2 = block the tool call
allow() { exit 0; }
note()  { printf '%s\n' "$*"; exit 0; }        # stdout is surfaced to the session

# Files where a frozen value can actually TAKE EFFECT — code and config only.
# Prose that merely names a frozen value (docs, rules, command files) is not a risk and
# must not trip the guard: false positives cost real interruptions and train you to
# ignore it. The three frozen documents are guarded separately by is_frozen_doc().
# NOTE: .claude/* and .docs/* are exempt FIRST, so the guard can never lock its own
# source — a self-referential guard needs a bootstrap exemption or it wedges the repo.
is_value_bearing() {
  local p; p="$(rel_path "${1:-}")"
  case "$p" in
    .claude/*|.docs/*) return 1 ;;
    *.proto)           return 1 ;;  # authority is interfaces.md §B, gated separately
    docs/*)            return 1 ;;
    *.md)              return 1 ;;
    gateway/*|rag/*|contracts/*|experiments/*) return 0 ;;
    Makefile|*.mk)     return 1 ;;  # command surface, not experiment config
    *.conf|*.yaml|*.yml|*.toml|*.json|*.env|*.sh|.env*) return 0 ;;
    *) return 1 ;;
  esac
}
