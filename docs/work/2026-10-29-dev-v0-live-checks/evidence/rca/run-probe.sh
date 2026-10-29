#!/usr/bin/env bash
# Re-derive the RCA probe numbers. Run from the repo root with v1 in Redis. Loads nomic-embed-text only.
# Same server start as `make seam-check`, on a private port (50054). Usage: bash <this> [single-chunk ids...]
set -euo pipefail
export DATASET_EPOCH_FILE="${DATASET_EPOCH_FILE:-$PWD/data/dataset-epoch}"   # as the Makefile exports it (read-only use)
E="$(cd "$(dirname "$0")" && pwd)"
echo "pressure: $(sysctl -n kern.memorystatus_vm_pressure_level)"
if lsof -t -nP -iTCP:50054 -sTCP:LISTEN >/dev/null 2>&1; then echo "port 50054 busy"; exit 1; fi
( cd rag && RAG_GRPC_ADDR=127.0.0.1:50054 REDIS_URL=redis://localhost:6379/0 exec python3 -m rag.server ) &
pid=$!; trap 'kill $pid 2>/dev/null || true' EXIT INT TERM
for i in $(seq 60); do nc -z 127.0.0.1 50054 2>/dev/null && break; sleep 0.5; done
( cd gateway && RAG_SEAM_ADDR=127.0.0.1:50054 RCA_SINGLE="$*" \
  go test -count=1 -v -overlay "$E/overlay-probe.json" -run '^TestRCAProbe$' ./internal/ragclient/ )
