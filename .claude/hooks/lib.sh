#!/usr/bin/env bash
# Shared helpers for thesis repo hooks.
# Sourced, never executed directly. Hooks block by exiting 2 with a message on stderr.

set -uo pipefail

REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DOCS_AI="$REPO_ROOT/.docs/ai"
WORK_DIR="$REPO_ROOT/.docs/work"
STATE_DIR="$REPO_ROOT/.claude/state"

# Weeks were removed 2026-09-21 (Pre-thesis_Sweeping.md #4). The schedule is now phases
# with binary exit criteria, and rigor is set by the SCOPE of a change rather than by the
# calendar: a one-line fix in week 20 does not need the ceremony a seam change needs, and a
# seam change in week 2 always did. `current_week()`, `in_runway()`, `week_row()`,
# WEEK1_START and RUNWAY_LAST_WEEK are gone; `current_phase()`, `phase_row()` and
# `task_scope()` replace them.
PHASE_FILE="${THESIS_PHASE_FILE:-}"

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

# --- phase -------------------------------------------------------------------
# Explicit state, not derived from the calendar: a phase ends when its exit criterion
# passes, which is a binary test and not a date (time_line.md "Ground Rules" 5).
# Unset is a legitimate state and is reported as such rather than guessed at.
current_phase() {
  local f="${PHASE_FILE:-$STATE_DIR/phase}"
  [[ -f "$f" ]] || { printf ''; return; }
  tr -cd '0-9' < "$f"
}

# The phase's row from the phase plan. time_line.md owns it TODAY; super-plan.md takes
# it over once #3 is filled (super-plan.md "What this document owns"). Reads whichever
# is authoritative, preferring the super plan once it carries real rows, so the handover
# needs no edit here.
phase_row() {
  local n="${1:-$(current_phase)}"
  [[ -z "$n" ]] && return 1
  local sp="$REPO_ROOT/docs/super-plan.md" tl="$REPO_ROOT/docs/time_line.md"
  if [[ -f "$sp" ]] && grep -qE "^### Phase $n — " "$sp" 2>/dev/null \
     && ! grep -A2 -E "^### Phase $n — " "$sp" 2>/dev/null | grep -q 'TODO(after sign-off)'; then
    grep -E "^### Phase $n — " "$sp" | head -1
    return 0
  fi
  grep -E "^\| \*\*$n — " "$tl" 2>/dev/null | head -1
}

phase_exit_criterion() { # the binary test that closes the current phase
  local row; row="$(phase_row "${1:-}")" || return 1
  [[ -z "$row" ]] && return 1
  case "$row" in
    '### '*) printf '%s' "${row#\#\#\# }" ;;
    *)       printf '%s' "$row" | awk -F'|' '{print $4}' | sed 's/^ *//;s/ *$//' ;;
  esac
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
# cheapest path, which is the failure mode three tiers invite (see gate-check.sh).
task_scope() {
  local d; d="$(task_dir)"
  [[ -n "$d" && -f "$d/SCOPE" ]] || { printf ''; return; }
  tr -cd 'LMS' < "$d/SCOPE" | head -c 1
}

# Design documents each scope must have before /approve implementation can run.
# frozen-guard.sh is armed at EVERY scope and is not listed here — it is not a phase.
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
