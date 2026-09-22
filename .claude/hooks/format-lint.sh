#!/usr/bin/env bash
# PostToolUse: Edit|Write|MultiEdit
# Formats the file just written. Reports SKIPPED when a tool is absent — never fails the edit.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

command -v jq >/dev/null 2>&1 || exit 0

path="$(tool_path)"
[[ -z "$path" || ! -f "$path" ]] && exit 0

case "$path" in
  *.go)
    if command -v gofmt >/dev/null 2>&1; then
      gofmt -w "$path" 2>/dev/null && echo "gofmt: $(rel_path "$path")"
    else
      echo "gofmt SKIPPED — not installed"
    fi
    ;;
  *.py)
    if command -v ruff >/dev/null 2>&1; then
      ruff format --quiet "$path" 2>/dev/null && echo "ruff format: $(rel_path "$path")"
      ruff check --quiet "$path" 2>/dev/null || echo "ruff check: findings in $(rel_path "$path") — run \`make lint\`"
    else
      echo "ruff SKIPPED — not installed (pip3 install ruff; W5 setup task)"
    fi
    ;;
  *.proto)
    echo "reminder: .proto changed — run \`make proto\` so both sides regenerate (.docs/ai/rules.md #4)"
    ;;
esac
exit 0
