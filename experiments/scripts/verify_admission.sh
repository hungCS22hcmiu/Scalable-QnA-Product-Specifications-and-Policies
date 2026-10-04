#!/usr/bin/env bash
# Quick, self-verification-only check of the admission-control claims on slide 5 of
# the advisor review: permit pool bound + 503 shed, and singleflight
# coalescing. Not a rehearsed live-demo script and not a measurement run -- it fires real
# generations against a real running gateway, so it costs real memory/time. Numbers here are
# NOT citable; they only exist so you can eyeball "does the mechanism actually behave as
# described" before the meeting.
#
# CLAUDE.md's standing rule still applies: check memory pressure before running.
#   sysctl kern.memorystatus_vm_pressure_level   # want 0
#
# Usage:
#   GATEWAY_URL=http://localhost:8080 ./experiments/scripts/verify_admission.sh
#
# Since ADR-003 the gateway grants ONE permit (the one slot Ollama serves), so with
# GEN_QUEUE_BUDGET=0 the N_DISTINCT=8 burst splits 1x200 / 7x503. The "4x200 / 4x503" split
# on slide 5 was taken with 4 permits, before ADR-003. main.go defaults the queue to
# 2x permits, which QUEUES instead of shedding, so set it to 0 to see pure shedding:
#   cd gateway && GEN_QUEUE_BUDGET=0 go run ./cmd/gateway

set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8080}"
N_DISTINCT="${N_DISTINCT:-8}"
N_IDENTICAL="${N_IDENTICAL:-5}"
NONCE="$(date +%s)"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

PRODUCTS=(product-headphones-01 product-headphones-02 product-furniture-01 product-furniture-02
          product-kitchen-01 product-kitchen-02 product-laptops-01 product-laptops-02)

echo "== admission-control self-check (NOT citable, NOT the rehearsed demo) =="
echo "gateway: $GATEWAY_URL"
if ! curl -s -o /dev/null -w '' --max-time 2 "$GATEWAY_URL/products"; then
  echo "gateway not reachable at $GATEWAY_URL -- start it first (make dev)" >&2
  exit 1
fi
echo

fire() {
  local idx="$1" question="$2" product_id="$3" outfile="$TMPDIR/resp_$idx.json"
  local status
  status=$(curl -s -o "$outfile" -w '%{http_code}' --max-time 60 \
    -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg q "$question" --arg p "$product_id" '{question:$q, product_id:$p}')" \
    "$GATEWAY_URL/ask")
  echo "$idx $status" >> "$TMPDIR/status.log"
}

echo "-- test 1: $N_DISTINCT concurrent DISTINCT questions (permit pool + shed) --"
: > "$TMPDIR/status.log"
t0=$(date +%s.%N)
for i in $(seq 1 "$N_DISTINCT"); do
  p="${PRODUCTS[$((i % ${#PRODUCTS[@]}))]}"
  fire "d$i" "Admission check $NONCE variant $i: what is the return window for this item?" "$p" &
done
wait
t1=$(date +%s.%N)
ok=$(awk '$2==200' "$TMPDIR/status.log" | wc -l | tr -d ' ')
shed=$(awk '$2==503' "$TMPDIR/status.log" | wc -l | tr -d ' ')
other=$(awk '$2!=200 && $2!=503' "$TMPDIR/status.log" | wc -l | tr -d ' ')
printf 'wall: %.2fs  200=%s  503=%s  other=%s\n' "$(echo "$t1 - $t0" | bc)" "$ok" "$shed" "$other"
if [ "$other" != "0" ]; then
  echo "  (non-200/503 statuses -- check status.log / response bodies in $TMPDIR)"
fi
echo

echo "-- test 2: $N_IDENTICAL concurrent IDENTICAL questions (singleflight coalescing) --"
: > "$TMPDIR/status.log"
same_q="Admission check $NONCE coalescing probe: how long is the warranty?"
t0=$(date +%s.%N)
for i in $(seq 1 "$N_IDENTICAL"); do
  fire "s$i" "$same_q" "product-headphones-01" &
done
wait
t1=$(date +%s.%N)
printf 'wall: %.2fs for %s identical requests\n' "$(echo "$t1 - $t0" | bc)" "$N_IDENTICAL"
echo "per-request cache/answer-hash (all should match if coalesced onto one generation):"
for i in $(seq 1 "$N_IDENTICAL"); do
  f="$TMPDIR/resp_s$i.json"
  if [ -s "$f" ]; then
    cache=$(jq -r '.cache // "?"' "$f")
    ans_sha=$(jq -r '.answer // ""' "$f" | shasum -a 256 | cut -c1-12)
    lat=$(jq -r '.latency_ms // "?"' "$f")
    echo "  s$i  cache=$cache  latency_ms=$lat  answer_sha=$ans_sha"
  else
    echo "  s$i  (no response body -- shed or error, see status.log)"
  fi
done
echo
echo "If coalesced correctly: all $N_IDENTICAL show cache=MISS (they race in together before"
echo "any Tier-1 write lands), matching answer_sha, near-identical latency_ms, and wall time"
echo "close to ONE generation -- not $N_IDENTICAL times one."
echo "Raw response bodies kept at: $TMPDIR (until this shell exits)"
