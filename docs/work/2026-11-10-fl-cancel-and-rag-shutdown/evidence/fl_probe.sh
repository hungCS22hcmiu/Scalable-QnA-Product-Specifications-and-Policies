#!/usr/bin/env bash
# DC 5 of docs/work/2026-11-10-fl-cancel-and-rag-shutdown/design.md: does a client that drops during
# generation free Ollama's one slot? citable: no. `make dev` must be running (run_fl_probe.sh does it).
#
#   pilot   : three candidate questions A, each sent straight to rag.server's Answer (no gateway).
#             The first that takes at least 4 s to generate is kept. None does: NO PILOT, exit 3.
#   B alone : ROUNDS times, a one-word request straight to Ollama (the one of probe_ollama_stops.sh).
#   rounds  : ROUNDS times: POST /ask with A, client drops at DROP_S (default 1) s (curl --max-time
#             $DROP_S), then B at once.
#             A round is valid only if the gateway log gained exactly one "abandoned while generating".
#   result  : gap = median(B after a drop) - median(B alone).  PASS if gap <= 0.5 s, GAP otherwise.
#
# Needs GATEWAY_LOG (the file `make dev` writes to). Optional: PRODUCT (3 chunks in v1), ROUNDS,
# DROP_S (seconds until the client drops, default 1), GATEWAY_URL, OLLAMA_BASE_URL.
# Exit: 0 PASS, 10 GAP, 3 NO PILOT, 4 no valid round.
set -u

: "${GATEWAY_LOG:?GATEWAY_LOG is required: the file that make dev writes its output to}"
PRODUCT=${PRODUCT:-product-laptops-b07qvm5x8w}
ROUNDS=${ROUNDS:-5}
DROP_S=${DROP_S:-1}
GATEWAY=${GATEWAY_URL:-http://localhost:8080}
OLLAMA=${OLLAMA_BASE_URL:-http://localhost:11434}/api/generate
MODEL=qwen3.5:2b-q4_K_M
LIMIT=0.5
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)

# B exactly as in probe_ollama_stops.sh: the served model, think false, num_ctx 8192.
B=$(printf '{"model":"%s","prompt":"%s","stream":false,"think":false,"options":{"num_ctx":8192}}' \
  "$MODEL" "Reply with exactly one word: OK.")

pressure() { sysctl -n kern.memorystatus_vm_pressure_level; }
timeB() { curl -s -o /dev/null -w '%{time_total}' -X POST "$OLLAMA" -d "$B"; }
abandoned() { grep -c 'abandoned while generating' "$GATEWAY_LOG" || true; }
median() {
  sort -g | awk '{a[NR]=$1} END {
    if (NR == 0) print "nan";
    else if (NR % 2) print a[(NR + 1) / 2];
    else printf "%.6f\n", (a[NR / 2] + a[NR / 2 + 1]) / 2 }'
}

echo "pressure at start: $(pressure) (1 = green, 2 = yellow, 4 = red)"
echo "drop at: $DROP_S s"

# 1. Pilot: a question whose answer takes at least 4 s, asked once straight to rag.server.
CANDIDATES=(
  "Explain in full detail every specification of this laptop, one by one, and what each means for a buyer, then its return and warranty policy."
  "Write a long, detailed buyer's guide for this product. Cover every feature in the context, one by one, with at least two sentences each, and finish with a summary."
  "List every fact in the context as a numbered list, and after each fact write three sentences that explain what it means for a buyer."
)
A=""
PILOT_S=""
for q in "${CANDIDATES[@]}"; do
  t=$(PYTHONPATH="$ROOT/rag/src" python3 - "$q" "$PRODUCT" <<'EOF'
import sys
import time

import grpc

from rag.pb.rag.v1 import rag_pb2, rag_pb2_grpc

query, product = sys.argv[1], sys.argv[2]
stub = rag_pb2_grpc.RagServiceStub(grpc.insecure_channel("localhost:50051"))
start = time.monotonic()
list(stub.Answer(rag_pb2.AnswerRequest(query=query, product_id=product), timeout=150))
print(f"{time.monotonic() - start:.3f}")
EOF
  )
  echo "pilot candidate: ${t:-error} s for: $q"
  if [ -n "$t" ] && awk -v t="$t" 'BEGIN { exit !(t >= 4) }'; then
    A=$q
    PILOT_S=$t
    break
  fi
done
if [ -z "$A" ]; then
  echo "NO PILOT: no candidate took 4 s or more"
  exit 3
fi
A_BODY=$(printf '{"question": "%s", "product_id": "%s"}' "$A" "$PRODUCT")

# 2. B alone.
alone=()
for i in $(seq "$ROUNDS"); do
  t=$(timeB)
  alone+=("$t")
  echo "B alone #$i: $t s"
done

# 3. Rounds: A through /ask, the client drops at DROP_S (default 1) s, B at once.
after=()
valid=0
for i in $(seq "$ROUNDS"); do
  before_n=$(abandoned)
  curl -s -o /dev/null --max-time "$DROP_S" -X POST -H 'Content-Type: application/json' \
    -d "$A_BODY" "$GATEWAY/ask"
  t=$(timeB)
  after_n=$(abandoned)
  if [ $((after_n - before_n)) -eq 1 ]; then
    after+=("$t")
    valid=$((valid + 1))
    echo "round $i: B after a drop $t s (valid: log +1)"
  else
    echo "round $i: B after a drop $t s (NOT valid: log +$((after_n - before_n)))"
  fi
done

# 4. Result. These seven lines are the last of the output (tail -8 shows them).
if [ "$valid" -eq 0 ]; then
  echo "NO VALID ROUND: the gateway log never gained an 'abandoned while generating' line"
  echo "pressure at end: $(pressure)"
  exit 4
fi
m_alone=$(printf '%s\n' "${alone[@]}" | median)
m_after=$(printf '%s\n' "${after[@]}" | median)
gap=$(awk -v a="$m_after" -v b="$m_alone" 'BEGIN { printf "%.3f", a - b }')
if awk -v g="$gap" -v l="$LIMIT" 'BEGIN { exit !(g <= l) }'; then verdict=PASS; code=0; else verdict=GAP; code=10; fi
echo "pilot A: ${PILOT_S} s straight to rag.server, for: $A"
echo "B alone, median of ${#alone[@]}: $m_alone s"
echo "B after a drop, median of $valid valid rounds: $m_after s"
echo "gap = $gap s (limit $LIMIT s)"
echo "valid rounds: $valid of $ROUNDS"
echo "RESULT: $verdict"
echo "pressure at end: $(pressure)"
exit $code
