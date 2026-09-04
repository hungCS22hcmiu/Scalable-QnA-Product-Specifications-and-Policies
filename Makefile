# The single command surface for this repo.
# Do not invent ad-hoc invocations — add a target here instead (docs/design/architecture.md §4).
# Targets report "SKIPPED — <tool> not installed" rather than passing vacuously.

SHELL := /bin/bash
GATEWAY := gateway
RAG := rag
PY := python3

# ruff/pytest install into the pip *user base* (~/Library/Python/<ver>/bin), which a
# non-login /bin/bash does not have on PATH. Without this they are installed but invisible,
# `command -v` fails, and lint/test report "SKIPPED — not installed" — a vacuous pass, the
# exact failure this file's header forbids. Derived, not hardcoded, so a Python upgrade
# does not silently reintroduce the skip.
export PATH := $(PATH):$(shell $(PY) -m site --user-base)/bin

# Frozen by ADR-017; mu_gen = 28.2 tok/s was measured at this value, and
# experiment-protocol.md 1 requires it pinned and reported per run. Exported here so a
# terminal-launched Ollama is pinned even if the shell predates the launchctl setenv
# (~/Library/LaunchAgents/com.thesis.ollama-env.plist covers GUI/login launches).
export OLLAMA_NUM_PARALLEL := 4

.DEFAULT_GOAL := help
.PHONY: help setup spike ingest dev ask demo-reset proto test lint verify figures check env-check redis-check

help: ## Show targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Report the tooling /verify needs but cannot find (W5 setup task)
	@command -v redis-server  >/dev/null || echo "  brew install redis"
	@command -v protoc        >/dev/null || echo "  brew install protobuf"
	@command -v ruff          >/dev/null || echo "  pip3 install ruff pytest"
	@echo "  cd $(RAG) && pip3 install -e '.[dev]'"

spike: ## W5 feasibility spike — measure the memory envelope (ADR-017)
	@echo "Run /spike in Claude Code: fills experiment-protocol.md 1.1 and freezes ADR-017."
	@echo "Baseline:"; vm_stat | head -4; sysctl hw.memsize; sysctl vm.swapusage

ingest: ## Build the index from the current corpus
	cd $(RAG) && $(PY) -m rag.ingest

env-check: ## Verify the frozen envelope is actually pinned in the running environment (ADR-017)
	@printf 'OLLAMA_NUM_PARALLEL  make=%s  launchd=%s  (frozen: 4, ADR-017)\n' \
	  "$(OLLAMA_NUM_PARALLEL)" "$$(launchctl getenv OLLAMA_NUM_PARALLEL || echo unset)"
	@test "$$(launchctl getenv OLLAMA_NUM_PARALLEL)" = "4" || { \
	  echo "  FAIL — launchd value is not 4. Ollama reads this at START, so a mismatch means"; \
	  echo "         measurements describe a different configuration than the one reported."; \
	  echo "         Fix: launchctl load -w ~/Library/LaunchAgents/com.thesis.ollama-env.plist"; \
	  echo "         then RESTART Ollama (it does not re-read the value while running)."; \
	  exit 1; }
	@pgrep -q ollama && { \
	  echo "  FAIL — ollama is already running, so the value it is SERVING is unknown."; \
	  echo "         It reads OLLAMA_NUM_PARALLEL at process start only, and macOS does not let"; \
	  echo "         us read it back: 'ps eww' on an owned process returns zero environment"; \
	  echo "         tokens. Unverifiable must not read as verified — this used to be a NOTE"; \
	  echo "         that exited 0, which let a run report ADR-017's value while serving another."; \
	  echo "         Fix: pkill -f 'ollama serve', then start it again (2 seconds)."; \
	  echo "         See also review.md F1: for qwen3.5 this variable currently has NO effect at"; \
	  echo "         all — ollama overrides it to -np 1. Resolve that ADR before trusting a 4."; \
	  exit 1; } || true
	@echo "  OK"

redis-check: ## Verify the cache/dependency eviction split is safe (interfaces.md D, ADR-005)
	@redis-cli PING >/dev/null 2>&1 || { echo "redis not reachable — start it (see CLAUDE.md)"; exit 1; }
	@pol=$$(redis-cli CONFIG GET maxmemory-policy | tail -1); \
	 mem=$$(redis-cli CONFIG GET maxmemory | tail -1); \
	 printf 'maxmemory-policy=%s  maxmemory=%s\n' "$$pol" "$$mem"; \
	 test "$$pol" = "noeviction" || { \
	   echo "  FAIL — policy is '$$pol', not noeviction."; \
	   echo "         maxmemory-policy is SERVER-GLOBAL, not per logical DB, so any allkeys-*"; \
	   echo "         setting can evict corpus:* vectors and (from W9) dep:* records. An evicted"; \
	   echo "         dependency record makes its entries permanently unpurgeable and breaks C2"; \
	   echo "         completeness with NO error (interfaces.md D, architecture.md 6 invariant 2)."; \
	   echo "         Fix: redis-cli CONFIG SET maxmemory-policy noeviction"; \
	   exit 1; }
	@test "$$(redis-cli CONFIG GET maxmemory | tail -1)" = "0" || { \
	   echo "  FAIL — maxmemory is set. Cache capacity is round(0.25 * K) entries (ADR-027),"; \
	   echo "         a COUNT, and K is not derived until W8. A byte budget here would evict"; \
	   echo "         by size instead, which is not the bounded cache the study specifies."; \
	   exit 1; }
	@echo "  OK — nothing evictable; capacity stays unset until K is derived (ADR-005 Open, W8)"

dev: env-check redis-check ## Run redis + rag service + gateway locally
	@command -v redis-stack-server >/dev/null || command -v redis-server >/dev/null \
	  || { echo "redis missing — make setup"; exit 1; }
	@pgrep -q ollama || { echo "FAIL — ollama not running; start it first (ADR-021)"; exit 1; }
	@zone=$$(sysctl -n kern.memorystatus_vm_pressure_level); \
	 if [ "$$zone" != "0" ]; then \
	   echo "FAIL — memory pressure level $$zone (0=green, 1=yellow, 2=urgent)."; \
	   echo "       Green is required before any local-AI run; a yellow/red run is invalid"; \
	   echo "       and must be discarded and repeated (proposal 7, CLAUDE.md)."; \
	   ps aux -m | awk '{sum+=$$6} END {printf "       currently %.1f GB total RSS; target is under ~10 GB\n", sum/1024/1024}'; \
	   exit 1; \
	 fi; \
	 echo "memory pressure: green"; \
	 ( cd $(RAG) && $(PY) -m rag.server ) & \
	 rag_pid=$$!; \
	 trap 'kill $$rag_pid 2>/dev/null' EXIT INT TERM; \
	 sleep 2; \
	 kill -0 $$rag_pid 2>/dev/null || { echo "FAIL — rag.server exited on startup"; exit 1; }; \
	 cd $(GATEWAY) && go run ./cmd/gateway

ask: ## One query end to end.  make ask Q="can I return this laptop?"
	@test -n "$(Q)" || { echo 'usage: make ask Q="your question"'; exit 1; }
	curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
	  -d '{"question":"$(Q)"}' | jq .

demo-reset: ## Restore corpus, flush cache, pre-warm nothing (defense_demo.md section 4)
	@echo "TODO(W7): restore corpus from data/, redis-cli FLUSHALL, no pre-warm"

proto: ## Regenerate gRPC stubs from contracts/ (never hand-edit stubs)
	@command -v protoc >/dev/null || { echo "SKIPPED — protoc not installed (make setup)"; exit 0; }
	protoc -I contracts \
	  --go_out=$(GATEWAY) --go_opt=module=github.com/hung/thesis/gateway \
	  --go-grpc_out=$(GATEWAY) --go-grpc_opt=module=github.com/hung/thesis/gateway \
	  contracts/rag/v1/rag.proto
	mkdir -p $(RAG)/src/rag/pb
	cd $(RAG) && $(PY) -m grpc_tools.protoc -I ../contracts \
	  --python_out=src/rag/pb --grpc_python_out=src/rag/pb ../contracts/rag/v1/rag.proto

test: ## Run all tests
	cd $(GATEWAY) && go test ./...
	@command -v pytest >/dev/null && (cd $(RAG) && pytest) || echo "pytest SKIPPED — not installed"

lint: ## Format check + vet + python lint
	@out=$$(gofmt -l $(GATEWAY)); test -z "$$out" || { echo "gofmt needed:"; echo "$$out"; exit 1; }
	cd $(GATEWAY) && go vet ./...
	@command -v ruff >/dev/null && ruff check $(RAG) experiments || echo "ruff SKIPPED — not installed"

verify: lint ## Full verification: lint + build + test (see /verify)
	cd $(GATEWAY) && go build ./...
	@$(MAKE) --no-print-directory test

figures: ## Regenerate every figure from raw/ (raw is write-once)
	$(PY) experiments/scripts/make_figures.py

# NOTE: uses grep, not rg. `rg` is a zsh alias here, not a binary on PATH, so under
# make's /bin/bash it silently vanished and every check reported "clean" — a vacuous
# pass, which is the exact failure mode this repo's verification discipline forbids.
DOCSRC := $(shell find docs -name '*.md' -not -path 'docs/archive/*') README.md CLAUDE.md

check: ## Documentation consistency sweep (see /consistency)
	@echo "--- dropped scope appearing as a live commitment ---"
	@grep -n -E 'learned predictor|predictor-gated|semantic routing' $(DOCSRC) || echo "  clean"
	@echo "--- approximate index must always say never mid-study ---"
	@grep -n 'HNSW' $(DOCSRC) || echo "  clean"
	@echo "--- stale schedule references ---"
	@grep -n -E 'Sep 13|W5.W9|W10.W22|W9 report' $(DOCSRC) || echo "  clean"
	@echo "--- frozen-value lists must agree across the three sources ---"
	@grep -c . .docs/ai/frozen-values.txt >/dev/null || { echo "  MISSING frozen-values.txt"; exit 1; }
	@echo "--- untracked files ---"
	@git status --short
