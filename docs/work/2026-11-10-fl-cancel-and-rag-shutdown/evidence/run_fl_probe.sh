#!/usr/bin/env bash
# Runs fl_probe.sh against a stack this script starts and stops. citable: no.
#   bash run_fl_probe.sh LABEL      LABEL is "before" or "after" (the fix); it names the two output files:
#   dev_LABEL.log (make dev's output, which is also the gateway log) and fl_probe_LABEL.out (the probe).
# Exit: 2 at memory pressure 4; 1 if :8080 or :50051 already has a listener, or the stack does not
# come up in 120 s; otherwise fl_probe.sh's own status (0 PASS, 10 GAP, 3 NO PILOT, 4 no valid round).
set -u

LABEL=${1:?usage: run_fl_probe.sh LABEL}
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
DEV_LOG="$HERE/dev_$LABEL.log"
OUT="$HERE/fl_probe_$LABEL.out"

level=$(sysctl -n kern.memorystatus_vm_pressure_level)
if [ "$level" = 4 ]; then
  echo "memory pressure is 4 (red): close apps and check again. Not started."
  exit 2
fi
echo "memory pressure before start: $level"

for port in 8080 50051; do
  held=$(lsof -t -nP -iTCP:$port -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' ')
  if [ -n "$held" ]; then
    echo "FAIL: :$port is already held by PID $held. Stop it first."
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
make dev > "$DEV_LOG" 2>&1 &
MAKE_PID=$!

up=0
for i in $(seq 120); do
  if curl -s -o /dev/null -m 2 localhost:8080/stats; then up=1; break; fi
  kill -0 "$MAKE_PID" 2>/dev/null || break
  sleep 1
done
if [ "$up" -ne 1 ]; then
  echo "FAIL: the gateway did not answer on :8080 within 120 s. Last 30 lines of $DEV_LOG:"
  tail -30 "$DEV_LOG"
  exit 1
fi

GATEWAY_LOG="$DEV_LOG" bash "$HERE/fl_probe.sh" | tee "$OUT"
status=${PIPESTATUS[0]}
exit "$status"
