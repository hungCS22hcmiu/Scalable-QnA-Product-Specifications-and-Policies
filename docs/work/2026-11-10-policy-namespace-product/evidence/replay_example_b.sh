#!/usr/bin/env bash
# Replays Tier 2.md Example B, questions 2 to 4, on a stack this script starts and stops. citable: no.
#   bash replay_example_b.sh LABEL      LABEL is "before" or "after" (the change); it names two files here:
#   dev_LABEL.log (make dev's output, which is also the gateway log) and replay_LABEL.jsonl (one line per request).
#
# The three requests, in order (the lines of the .jsonl follow this order):
#   Q2  "How long is the warranty on these headphones?"          H1  product-electronics-b07zj7qg33
#   Q3  "What warranty period do these headphones come with?"    H1  (a paraphrase: same-product reuse)
#   Q4  Q2's words, from H2  product-electronics-b079jfb616      (the cross-product case)
# The MIXED arm is set off explicitly (LANE_SIGMA_HI=0.20), the support gate and tau are the gateway's
# defaults (gate on, tau 0.85). A line keeps only the fields of the response that are not text: the reply
# text can carry corpus text, so it is never read and never saved.
# Exit: 2 at memory pressure 4; 1 if :8080 or :50051 already has a listener, the cache reset fails, the
# stack does not come up in 120 s, or a request fails; otherwise 0.
set -u

LABEL=${1:?usage: replay_example_b.sh LABEL}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
DEV_LOG="$HERE/dev_$LABEL.log"
OUT="$HERE/replay_$LABEL.jsonl"

H1=product-electronics-b07zj7qg33
H2=product-electronics-b079jfb616
Q2="How long is the warranty on these headphones?"
Q3="What warranty period do these headphones come with?"

pressure() { sysctl -n kern.memorystatus_vm_pressure_level; }

level=$(pressure)
if [ "$level" = 4 ]; then
  echo "memory pressure is 4 (red): close apps and check again. Not started."
  exit 2
fi
echo "memory pressure at start: $level"

for port in 8080 50051; do
  held=$(lsof -t -nP -iTCP:$port -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ')
  if [ -n "$held" ]; then
    echo "FAIL: :$port is already held by PID $held. Stop it first."
    exit 1
  fi
done
for f in "$DEV_LOG" "$OUT"; do
  if [ -e "$f" ]; then
    echo "FAIL: $f already exists. Evidence is not overwritten: move it, or use another LABEL."
    exit 1
  fi
done

MAKE_PID=""
cleanup() {
  # The gateway is the listener on :8080. TERM makes it drain and exit; go run then ends, and make
  # dev's EXIT trap stops rag.server. If rag.server still holds :50051 after make is gone, TERM it.
  local gw rag i
  gw=$(lsof -t -nP -iTCP:8080 -sTCP:LISTEN 2>/dev/null | head -1)
  if [ -n "$gw" ]; then
    kill -TERM "$gw" 2>/dev/null
  elif [ -n "$MAKE_PID" ]; then
    kill -TERM "$MAKE_PID" 2>/dev/null
  fi
  if [ -n "$MAKE_PID" ]; then
    for i in $(seq 90); do
      kill -0 "$MAKE_PID" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$MAKE_PID" 2>/dev/null; then echo "make dev still running after 90 s: PID $MAKE_PID"; fi
  fi
  rag=$(lsof -t -nP -iTCP:50051 -sTCP:LISTEN 2>/dev/null | head -1)
  if [ -n "$rag" ]; then
    kill -TERM "$rag" 2>/dev/null
    for i in $(seq 30); do
      lsof -t -nP -iTCP:50051 -sTCP:LISTEN >/dev/null 2>&1 || break
      sleep 1
    done
  fi
  MAKE_PID=""
}
trap cleanup EXIT

cd "$ROOT" || exit 1
if ! make cache-reset; then
  echo "FAIL: make cache-reset failed."
  exit 1
fi

LANE_SIGMA_HI=0.20 make dev > "$DEV_LOG" 2>&1 &
MAKE_PID=$!

up=0
for i in $(seq 120); do
  if curl -s -o /dev/null -m 2 localhost:8080/stats; then up=1; break; fi
  kill -0 "$MAKE_PID" 2>/dev/null || break
  sleep 1
done
if [ "$up" -ne 1 ]; then
  echo "FAIL: the gateway did not respond on :8080 within 120 s. Last 30 lines of $DEV_LOG:"
  tail -30 "$DEV_LOG"
  exit 1
fi

# ask QUESTION PRODUCT_ID: one /ask, one line appended to $OUT. Only the response's fields that are not
# text are kept.
ask() {
  local q=$1 pid=$2 p body resp
  p=$(pressure)
  echo "pressure before the request ($pid): $p"
  body=$(jq -nc --arg q "$q" --arg p "$pid" '{question:$q, product_id:$p}')
  if ! resp=$(curl -sS -m 300 -X POST localhost:8080/ask -H 'content-type: application/json' -d "$body"); then
    echo "FAIL: the request for $pid did not complete."
    return 1
  fi
  if ! printf '%s' "$resp" | jq -c --arg label "$LABEL" --arg pid "$pid" --arg p "$p" \
    '{label:$label, product_id:$pid, pressure:($p|tonumber), cache, similarity, lane, namespace, sources, latency_ms}' >> "$OUT"; then
    echo "FAIL: the response for $pid is not JSON."
    return 1
  fi
  tail -1 "$OUT"
  sleep 2 # the write-back lands
}

ask "$Q2" "$H1" || exit 1
ask "$Q3" "$H1" || exit 1
ask "$Q2" "$H2" || exit 1

echo "arm in the gateway log: $(grep -o 'mixed_lane=[a-z]*' "$DEV_LOG" | head -1)"
echo "memory pressure at end: $(pressure)"
exit 0
