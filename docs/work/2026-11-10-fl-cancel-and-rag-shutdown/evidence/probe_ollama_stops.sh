#!/usr/bin/env bash
# Design-stage probe (2026-11-10), citable: no. Settles unknown U1 of design.md §3:
# does Ollama stop generating when the client of a `stream: false` /api/generate request closes?
# No gateway, no rag.server: curl straight to Ollama, with the served model and options.
#   B alone      : a short request, timed, 3 times (the baseline).
#   A cut, then B: a long request A whose client gives up after 1 s (curl --max-time 1), then B at once.
# If Ollama kept generating A, B would wait for the rest of A (many seconds). If it stopped, B ≈ baseline.
set -u
URL=${OLLAMA_BASE_URL:-http://localhost:11434}/api/generate
MODEL=qwen3.5:2b-q4_K_M
body() { printf '{"model":"%s","prompt":"%s","stream":false,"think":false,"options":{"num_ctx":8192}}' "$MODEL" "$1"; }
A=$(body "Write a long and detailed story, about 800 words, about a lighthouse keeper and a storm.")
B=$(body "Reply with exactly one word: OK.")

timeB() { curl -s -o /dev/null -w '%{time_total}' -X POST "$URL" -d "$B"; }

echo "pressure before: $(sysctl -n kern.memorystatus_vm_pressure_level) (1 = green)"
echo "warm-up B: $(timeB) s"
echo "pressure with the model loaded: $(sysctl -n kern.memorystatus_vm_pressure_level)"
for i in 1 2 3; do echo "B alone #$i: $(timeB) s"; done
for i in 1 2 3; do
  curl -s -o /dev/null --max-time 1 -X POST "$URL" -d "$A"
  echo "A cut at 1 s, then B #$i: $(timeB) s"
done
echo "control: A run to the end takes $(curl -s -o /dev/null -w '%{time_total}' -X POST "$URL" -d "$A") s"
echo "pressure after: $(sysctl -n kern.memorystatus_vm_pressure_level)"
