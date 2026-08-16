# The single command surface for this repo.
# Do not invent ad-hoc invocations — add a target here instead (docs/design/architecture.md §4).
# Targets report "SKIPPED — <tool> not installed" rather than passing vacuously.

SHELL := /bin/bash
GATEWAY := gateway
RAG := rag
PY := python3

.DEFAULT_GOAL := help
.PHONY: help setup spike ingest dev ask demo-reset proto test lint verify figures check

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

dev: ## Run redis + rag service + gateway locally
	@command -v redis-server >/dev/null || { echo "redis-server missing — make setup"; exit 1; }
	@echo "TODO(W6): redis-server & ; python -m rag.server & ; go run ./cmd/gateway"

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
