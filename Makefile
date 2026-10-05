# The single command surface for this repo.
# Do not invent ad-hoc invocations — add a target here instead (docs/architecture.md §4).
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
#
# The other half of that hazard is the *shape* of the guard, fixed 2026-09-21: the old
# `command -v X && X ... || echo "SKIPPED"` also printed "SKIPPED — not installed" when the
# tool was present and FAILED, and exited 0. A live ruff error in fetch_corpus_v1.py had
# been invisible that way. Presence and outcome are now separate: if/else, never `||`.
export PATH := $(PATH):$(shell $(PY) -m site --user-base)/bin

# The frozen generation envelope (ADR-003). One block: env-check verifies all three against the
# LIVE runner, and every recipe inherits them.
#
# OLLAMA_NUM_PARALLEL is the slot count the runner ACTUALLY SERVES, not a request to Ollama.
# Ollama 0.33.2 runs the qwen35 architecture at one slot whatever is requested (finding F1), and
# the launchd pin that requested 4 was removed (ADR-003, A2). The consumer of this export is the
# gateway, which reads it as its admission permit count when launched through make
# (gateway/cmd/gateway/main.go). The pool it sizes bounds queueing delay, not memory.
export OLLAMA_NUM_PARALLEL := 1
# The server build and the weights are part of the envelope too: the one-slot rule is a
# version-specific scheduler rule (Ollama.app auto-updated 0.32.13 -> 0.33.2 unattended on
# 2026-09-01; auto-update is now off), and `ollama pull` can re-point a tag at new weights.
OLLAMA_VERSION := 0.33.2
LLM_BLOB := sha256-7a3a8d55382135a773916fd7c35044b2a2a3a7b8dee788095d70f122e6d8f520

.DEFAULT_GOAL := help
.PHONY: help setup spike ingest dev measure ask demo-reset demo proto test lint verify figures check env-check redis-check gate-corpus load-smoke mu-hit ui seam-check

help: ## Show targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Report the tooling /verify needs but cannot find (W5 setup task)
	@command -v redis-server  >/dev/null || echo "  brew install redis"
	@command -v protoc        >/dev/null || echo "  brew install protobuf"
	@command -v ruff          >/dev/null || echo "  pip3 install ruff pytest"
	@echo "  cd $(RAG) && pip3 install -e '.[dev]'"

spike: ## Feasibility spike — measure the memory envelope. SPENT: already frozen
	@echo "Envelope frozen at num_ctx=8192, one generation slot (ADR-003). Re-run only on a"
	@echo "hardware change, and re-freeze deliberately if the numbers move."
	@echo "Baseline:"; vm_stat | head -4; sysctl hw.memsize; sysctl vm.swapusage

ingest: ## Build the index from the current corpus
	cd $(RAG) && $(PY) -m rag.ingest

env-check: ## Verify the frozen envelope against the LIVE runner (ADR-003) -- loads both models, ~2.1 GB
	@$(PY) experiments/scripts/env_check.py --frozen-np $(OLLAMA_NUM_PARALLEL) \
	  --ollama-version $(OLLAMA_VERSION) --llm-blob $(LLM_BLOB)

redis-check: ## Verify the cache/dependency eviction split is safe (interfaces.md D)
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
	   echo "  FAIL — maxmemory is set. Cache capacity is round(0.25 * K) entries,"; \
	   echo "         a COUNT, and K is not derived until W8. A byte budget here would evict"; \
	   echo "         by size instead, which is not the bounded cache the study specifies."; \
	   exit 1; }
	@echo "  OK — nothing evictable; capacity stays unset until K is derived (the eviction split Open, W8)"

# There are TWO kinds of run and they need different gates. Conflating them is what makes a
# strict gate get quietly weakened, because it blocks work it was never meant to govern.
#
#   `dev`     — FUNCTIONAL. Demo, MVP, debugging. Proves behaviour. Produces NO citable number:
#               every headline figure is pre-computed and the load clip is pre-recorded
#              . It needs exactly one thing from memory: enough room to load
#               the models without swapping. No app-closing ritual, no pressure zone.
#   `measure` — MEASURED. Anything whose number reaches the thesis. Full discipline; proposal 7's
#               validity rule applies and a failed gate means the run is discarded.
#
# The rule that keeps this honest: a latency printed by `dev` is NOT citable, and the banner says
# so on every run. The hazard was never the relaxed run — it is a demo number drifting onto a slide.

measure: env-check redis-check ## Gate a MEASURED run (proposal 7 validity rule)
	@zone=$$(sysctl -n kern.memorystatus_vm_pressure_level); \
	 if [ "$$zone" != "0" ]; then \
	   echo "FAIL — memory pressure level $$zone (0=green, 1=yellow, 2=urgent)."; \
	   echo "       A yellow/red run is invalid and must be discarded and repeated at lower"; \
	   echo "       load. NOTE: this sensor's behaviour is under review — run the reboot"; \
	   echo "       test before trusting a reading."; \
	   ps aux -m | awk '{sum+=$$6} END {printf "       currently %.1f GB total RSS\n", sum/1024/1024}'; \
	   exit 1; \
	 fi; \
	 echo "  OK — green. Record swap delta across the run; a run that swapped is invalid."

# rag-server-reuseport (docs/work/2026-10-05-rag-server-reuseport/): three guards keep the gateway on
# the rag.server started HERE. `exec` makes $$! the server's own PID (under /bin/bash 3.2 it was the
# subshell, so the trap orphaned the server on :50051). The port pre-check refuses to start beside a
# listener already there, since the gateway dials localhost:50051 and would reach that one instead.
# And the gateway starts only once THIS PID listens on the port (`lsof -a -p` sees our own process
# even where it cannot see another user's), replacing a fixed `sleep 2` that a server failing to
# bind after 2 s slipped past.
dev: redis-check ## Run redis + rag service + gateway locally (FUNCTIONAL — numbers not citable)
	@command -v redis-stack-server >/dev/null || command -v redis-server >/dev/null \
	  || { echo "redis missing — make setup"; exit 1; }
	@pgrep -q ollama || { echo "FAIL — ollama not running; start it first"; exit 1; }
	@avail=$$(sysctl -n kern.memorystatus_level); \
	 if [ "$$avail" -lt 25 ]; then \
	   echo "FAIL — only $${avail}% memory available; the models need ~2.1 GB resident"; \
	   echo "       (qwen3.5:2b 1.70 + nomic-embed 0.37) and would swap. Close ONE heavy app"; \
	   echo "       or run: sudo purge"; \
	   exit 1; \
	 fi; \
	 echo "  ┌─────────────────────────────────────────────────────────────┐"; \
	 echo "  │  FUNCTIONAL RUN — latencies printed here are NOT citable.    │"; \
	 echo "  │  For a number that reaches the thesis, use: make measure     │"; \
	 echo "  └─────────────────────────────────────────────────────────────┘"; \
	 echo "  memory available: $${avail}% (floor 25%; models need ~2.1 GB of 16 GB)"; \
	 rag_port=$${RAG_GRPC_ADDR:-0.0.0.0:50051}; rag_port=$${rag_port##*:}; \
	 case "$$rag_port" in ''|*[!0-9]*) \
	   echo "FAIL — RAG_GRPC_ADDR must end in :<port> (got '$${RAG_GRPC_ADDR}')"; exit 1;; esac; \
	 held=$$(lsof -t -nP -iTCP:$$rag_port -sTCP:LISTEN 2>/dev/null | sort -u | tr '\n' ' '); \
	 if [ -n "$$held" ]; then \
	   echo "FAIL — :$$rag_port is already held by PID $$held(a stale rag.server?). The gateway would"; \
	   echo "       dial it instead of the server started here. Stop it first."; \
	   exit 1; \
	 fi; \
	 ( cd $(RAG) && exec $(PY) -m rag.server ) & \
	 rag_pid=$$!; \
	 trap 'kill $$rag_pid 2>/dev/null' EXIT INT TERM; \
	 for i in $$(seq 60); do \
	   kill -0 $$rag_pid 2>/dev/null || { echo "FAIL — rag.server exited on startup (if it could not bind, see"; \
	     echo "       lsof -nP -iTCP:$$rag_port -sTCP:LISTEN)"; exit 1; }; \
	   if lsof -a -p $$rag_pid -nP -iTCP:$$rag_port -sTCP:LISTEN >/dev/null 2>&1; then break; fi; \
	   [ $$i -lt 60 ] || { echo "FAIL — rag.server not listening on :$$rag_port after 30 s"; exit 1; }; \
	   sleep 0.5; \
	 done; \
	 echo "  rag.server pid $$rag_pid listening on :$$rag_port"; \
	 cd $(GATEWAY) && RESULTS_DIR=$${RESULTS_DIR:-$(PWD)/experiments/results} \
	   UI_DIR=$${UI_DIR:-$(PWD)/ui/dist} go run ./cmd/gateway

ask: ## One query end to end.  make ask Q="can I return this laptop?"
	@test -n "$(Q)" || { echo 'usage: make ask Q="your question"'; exit 1; }
	curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
	  -d '{"question":"$(Q)"}' | jq .

# Restore a known-cold state so a rehearsal starts where the demo script assumes it does
#. A warm cache turns step 1 into TIER1_HIT and collapses all four steps
# at once, live -- so this runs BEFORE every rehearsal, not once.
#
# FLUSHALL, never FT.DROPINDEX. Dropping the index leaves the t2:* hashes behind; the gateway
# re-creates idx:cache at startup (EnsureCacheIndex) and RediSearch re-indexes those orphans,
# giving a warm cache that PRESENTS as cold -- the exact failure this target exists to prevent.
demo-reset: ## Restore corpus, flush both tiers, pre-warm nothing
	@redis-cli PING >/dev/null 2>&1 || { echo "FAIL -- redis not reachable (see CLAUDE.md)"; exit 1; }
	@lsof -ti tcp:8080 >/dev/null 2>&1 && { \
	   echo "FAIL -- the gateway is still listening on :8080. Stop it first, THEN reset."; \
	   echo "       FLUSHALL drops idx:cache along with the keys (verified 2026-09-05), and the"; \
	   echo "       gateway only calls EnsureCacheIndex at startup. Resetting under a live gateway"; \
	   echo "       leaves it writing t2:* records into an index that no longer exists: step 3"; \
	   echo "       never reaches TIER2_HIT and NOTHING reports an error."; \
	   echo "       Order is: stop dev -> make demo-reset -> make dev."; \
	   exit 1; } || true
	@pgrep -q ollama || { echo "FAIL -- ollama not running; the re-ingest needs nomic-embed-text"; exit 1; }
	@foreign=$$(redis-cli --scan | grep -cvE '^(corpus:|t1:|t2:|dep:|entry:|lru:)' || true); \
	 if [ "$$foreign" != "0" ]; then \
	   echo "FAIL -- $$foreign key(s) here do not belong to the thesis."; \
	   echo "       FLUSHALL wipes EVERY database on the server, so this refuses rather than"; \
	   echo "       destroying an unrelated project's data (CLAUDE.md: this machine is shared)."; \
	   echo "       Inspect: redis-cli --scan | grep -vE '^(corpus:|t1:|t2:|dep:|entry:|lru:)'"; \
	   exit 1; \
	 fi
	@dirty=$$(git status --porcelain -- data/ | grep -v '^??' || true); \
	 if [ -n "$$dirty" ]; then \
	   echo "  restoring corpus files edited since the last commit (step 5 undoes itself here):"; \
	   printf '%s\n' "$$dirty" | sed 's/^/    /'; \
	   git checkout -- data/; \
	 else echo "  corpus clean -- nothing to restore"; fi
	@untracked=$$(git status --porcelain -- data/ | grep '^??' || true); \
	 if [ -n "$$untracked" ]; then \
	   echo "  NOTE -- untracked files left in place (not deleted); they WILL be ingested:"; \
	   printf '%s\n' "$$untracked" | sed 's/^/    /'; \
	 fi
	@echo "  flushing both tiers and the corpus index (FLUSHALL)"
	@redis-cli FLUSHALL >/dev/null
	@$(MAKE) --no-print-directory ingest
	@t1=$$(redis-cli --scan --pattern 't1:*' | wc -l | tr -d ' '); \
	 t2=$$(redis-cli --scan --pattern 't2:*' | wc -l | tr -d ' '); \
	 c=$$(redis-cli --scan --pattern 'corpus:*' | wc -l | tr -d ' '); \
	 printf '  corpus:%s  t1:%s  t2:%s\n' "$$c" "$$t1" "$$t2"; \
	 if [ "$$t1" != "0" ] || [ "$$t2" != "0" ]; then \
	   echo "  FAIL -- cache is not cold; step 1 would answer TIER1_HIT and the script collapses."; \
	   exit 1; \
	 fi; \
	 if [ "$$c" = "0" ]; then \
	   echo "  FAIL -- corpus is empty; every question would MISS with no sources listed."; \
	   exit 1; \
	 fi; \
	 echo "  OK -- cold cache, corpus indexed. Ready to rehearse the four steps."

# The four demo questions, pinned. They are NOT interchangeable with paraphrases of
# themselves: the trap (Q4) clears tau=0.85 by only 0.019 and fails theta=0.60, and an
# off-hand rewording drops it below tau -- at which point a fixed threshold refuses it too
# and step 4 proves nothing. Re-derived and verified 2026-09-05.
DEMO_Q1 := Am I entitled to a full refund on my headphones 30 days after delivery?
DEMO_Q3 := Is a full refund possible for my headphones 30 days after delivery?
DEMO_Q4 := Am I entitled to a full refund on my sofa 30 days after delivery?
DEMO_PAUSE ?= 2

demo: ## Rehearse the four demo steps against a cold cache
	@command -v jq >/dev/null || { echo "FAIL -- jq not installed"; exit 1; }
	@lsof -ti tcp:8080 >/dev/null 2>&1 || { echo "FAIL -- gateway not listening on :8080. Run: make dev"; exit 1; }
	@warm=$$(( $$(redis-cli --scan --pattern 't1:*' | wc -l) + $$(redis-cli --scan --pattern 't2:*' | wc -l) )); \
	 if [ "$$warm" -ne 0 ]; then \
	   echo "FAIL -- cache is warm ($$warm entries). Step 1 would answer TIER1_HIT and all four"; \
	   echo "       steps collapse at once. Stop the gateway, run 'make demo-reset', 'make dev'."; \
	   exit 1; \
	 fi
	@tmp=$$(mktemp -d); trap 'rm -rf $$tmp' EXIT; \
	 tau=$${REUSE_TAU:-0.85}; theta=$${REUSE_THETA:-0.60}; \
	 ask() { curl -sS -X POST localhost:8080/ask -H 'content-type: application/json' \
	           -d "$$(jq -nc --arg q "$$1" '{question:$$q}')" > "$$2"; }; \
	 num() { case "$$1" in null) printf '%s' "—";; *) printf "$$2" "$$1";; esac; }; \
	 line() { printf '    %s  ·  %s ms  ·  similarity %s  ·  source_overlap %s\n' \
	   "$$(jq -r .cache "$$1")" "$$(jq -r .latency_ms "$$1")" \
	   "$$(num "$$(jq -r .similarity "$$1")" '%.4f')" \
	   "$$(num "$$(jq -r .source_overlap "$$1")" '%.2f')"; }; \
	 hdr() { printf '\n\033[1m── Step %s · %s\033[0m\n    Q: %s\n' "$$1" "$$2" "$$3"; }; \
	 printf '  cold cache verified (t1:0 t2:0)  ·  tau=%s theta=%s — DEMO values, swept later\n' "$$tau" "$$theta"; \
	 printf '  latencies here are NOT citable (dev-v0, make dev)\n'; \
	 \
	 hdr 1 "fresh question — the cost every uncached system pays" "$(DEMO_Q1)"; \
	 ask "$(DEMO_Q1)" "$$tmp/1.json"; line "$$tmp/1.json"; sleep $(DEMO_PAUSE); \
	 \
	 hdr 2 "exact repeat — Tier 1" "$(DEMO_Q1)"; \
	 ask "$(DEMO_Q1)" "$$tmp/2.json"; line "$$tmp/2.json"; sleep $(DEMO_PAUSE); \
	 \
	 hdr 3 "paraphrase — Tier 2, different words, same evidence" "$(DEMO_Q3)"; \
	 ask "$(DEMO_Q3)" "$$tmp/3.json"; line "$$tmp/3.json"; sleep $(DEMO_PAUSE); \
	 \
	 hdr 4 "the trap — high similarity, different evidence" "$(DEMO_Q4)"; \
	 ask "$(DEMO_Q4)" "$$tmp/4.json"; line "$$tmp/4.json"; \
	 printf '\n    The refusal is arithmetic, not a model score — check it by eye:\n\n'; \
	 jq -r --slurpfile e "$$tmp/1.json" '\
	   ($$e[0].sources) as $$src | (.sources) as $$got | \
	   ["    cached entry grounded in (headphones):"] \
	   + ($$src | map("      " + (if (. as $$c | $$got | index($$c)) then "\u2713 " else "  " end) + .)) \
	   + ["", "    retrieved now (sofa):"] \
	   + ($$got | map("      " + (if (. as $$c | $$src | index($$c)) then "\u2713 " else "  " end) + .)) \
	   | .[]' "$$tmp/4.json"; \
	 shared=$$(jq -r --slurpfile e "$$tmp/1.json" '[.sources[] | select(. as $$c | $$e[0].sources | index($$c))] | length' "$$tmp/4.json"); \
	 total=$$(jq -r '.sources | length' "$$tmp/1.json"); \
	 printf '\n    overlap = %s shared / %s entry sources = %.2f  <  theta %s   →  REFUSE, generate instead\n' \
	   "$$shared" "$$total" "$$(jq -r .source_overlap "$$tmp/4.json")" "$$theta"; \
	 \
	 hits=$$(cat $$tmp/[1-4].json | jq -r 'select(.cache|test("HIT")) | .cache' | wc -l | tr -d ' '); \
	 printf '\n\033[1m── Counters\033[0m\n    requests 4  ·  hits %s  ·  hit rate %s%%  ·  generations avoided %s\n\n' \
	   "$$hits" "$$(( hits * 25 ))" "$$hits"

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
	@if command -v pytest >/dev/null; then (cd $(RAG) && pytest); \
	else echo "pytest SKIPPED — not installed"; fi
	@# experiments/ has its own suite and is NOT covered by rag/pyproject.toml's testpaths.
	@# Invoked separately rather than by widening testpaths, because rag/ is an installed package
	@# and experiments/scripts/ is a directory of runnable scripts -- different import stories.
	@if command -v pytest >/dev/null; then pytest experiments/tests -q; \
	else echo "pytest SKIPPED — not installed"; fi

lint: ## Format check + vet + python lint
	@out=$$(gofmt -l $(GATEWAY)); test -z "$$out" || { echo "gofmt needed:"; echo "$$out"; exit 1; }
	cd $(GATEWAY) && go vet ./...
	@if command -v ruff >/dev/null; then ruff check $(RAG) experiments; \
	else echo "ruff SKIPPED — not installed"; fi

verify: lint ## Full verification: lint + build + test (see /verify)
	cd $(GATEWAY) && go build ./...
	@$(MAKE) --no-print-directory test

# Item 1.4: texts flows Python -> Go, positionally aligned, checked against Redis as the oracle
# (docs/work/2026-10-05-carry-chunk-text/design.md 3d). Two guards make it a check that cannot pass
# while proving nothing:
#  - It OWNS its rag.server: started from the working tree on a private port and killed on exit,
#    never whatever answers on :50051, which can be stale (rag-server-reuseport). `exec` makes
#    $$! the server's own PID, so the trap kills the server, not just a subshell.
#  - It fails unless the log shows every subtest PASS. `go test -run` with no match exits 0 and
#    prints PASS, and so does a skip; -count=1 alone does not stop a cached result being read.
# Loads nomic-embed-text (the query is embedded), not the LLM. Not a measurement: the pressure
# level is recorded, not gated on. Pass SEAM_LOG=<path> to keep the log as evidence.
SEAM_PORT ?= 50052
SEAM_REDIS_URL ?= redis://localhost:6379/0
SEAM_LOG ?=

seam-check: ## Item 1.4: texts flow Python -> Go aligned, oracle = Redis (NOT a measurement)
	@set -euo pipefail; \
	 log="$(SEAM_LOG)"; [ -n "$$log" ] || log=$$(mktemp -t seam-check); \
	 echo "  memory pressure level: $$(sysctl -n kern.memorystatus_vm_pressure_level) (0 = green; recorded, not gated)"; \
	 redis-cli -u $(SEAM_REDIS_URL) PING >/dev/null 2>&1 || { echo "FAIL — redis unreachable at $(SEAM_REDIS_URL)"; exit 1; }; \
	 n=$$( (lsof -t -nP -iTCP:50051 -sTCP:LISTEN 2>/dev/null || true) | sort -u | wc -l | tr -d ' '); \
	 echo "  info: $$n process(es) listening on :50051 (rag-server-reuseport; not used by this check)"; \
	 if lsof -t -nP -iTCP:$(SEAM_PORT) -sTCP:LISTEN >/dev/null 2>&1; then \
	   echo "FAIL — port $(SEAM_PORT) already has a listener; SO_REUSEPORT would share it"; exit 1; \
	 fi; \
	 ( cd $(RAG) && RAG_GRPC_ADDR=127.0.0.1:$(SEAM_PORT) REDIS_URL=$(SEAM_REDIS_URL) exec $(PY) -m rag.server ) & \
	 rag_pid=$$!; \
	 trap 'kill $$rag_pid 2>/dev/null || true' EXIT INT TERM; \
	 for i in $$(seq 60); do \
	   kill -0 $$rag_pid 2>/dev/null || { echo "FAIL — rag.server exited on startup"; exit 1; }; \
	   if nc -z 127.0.0.1 $(SEAM_PORT) 2>/dev/null; then break; fi; \
	   [ $$i -lt 60 ] || { echo "FAIL — rag.server not listening on $(SEAM_PORT) after 30 s"; exit 1; }; \
	   sleep 0.5; \
	 done; \
	 echo "  rag.server pid $$rag_pid on 127.0.0.1:$(SEAM_PORT), started from the working tree"; \
	 ( cd $(GATEWAY) && RAG_SEAM_ADDR=127.0.0.1:$(SEAM_PORT) REDIS_URL=$(SEAM_REDIS_URL) \
	   go test -count=1 -v -run '^TestSeam$$' ./internal/ragclient/ ) 2>&1 | tee "$$log"; \
	 for want in TestSeam TestSeam/L1 TestSeam/L2 TestSeam/L3 TestSeam/shift; do \
	   grep -q -- "--- PASS: $$want (" "$$log" || { echo "FAIL — no '--- PASS: $$want' in $$log"; exit 1; }; \
	 done; \
	 if grep -qE -- '--- SKIP|no tests to run|\(cached\)' "$$log"; then \
	   echo "FAIL — the test did not genuinely run (a skip, no matching test, or a cached result)"; exit 1; \
	 fi; \
	 echo "  PASS — texts aligned with chunk_ids on L1-L3, splice fired, shift rejected. Log: $$log"

load-smoke: ## k6 harness shakedown against a LOCAL gateway (NOT a measurement)
	@command -v k6 >/dev/null || { echo "SKIPPED -- k6 not installed"; exit 0; }
	@lsof -ti tcp:8080 >/dev/null 2>&1 || { echo "FAIL -- no gateway on :8080 (make dev)"; exit 1; }
	@echo "  ┌─────────────────────────────────────────────────────────────┐"
	@echo "  │  SHAKEDOWN ONLY. The load generator is CO-HOSTED with the    │"
	@echo "  │  system under test, so these numbers are NOT citable.        │"
	@echo "  │  A real run drives :8080 from a second machine:    │"
	@echo "  │    see experiments/k6/README.md                              │"
	@echo "  └─────────────────────────────────────────────────────────────┘"
	k6 run -e RATE_RPS=2 -e VUS=4 -e DURATION=20s experiments/k6/ask.js

# The corpus sensitivity gate (data-card.md 7). Nothing is frozen until all four criteria pass,
# and the script refuses to print a snapshot digest until they do.
#
#   make gate-corpus                       # G1..G4 against data/v1 -- needs redis + ollama + ingest
#   make gate-corpus STRUCTURAL=1          # G3/G4 only -- the loop to run while authoring
#   make gate-corpus VERSION=dev-v0 ...    # shakedown; dev-v0 is NOT gated
VERSION ?= v1
WORKLOAD ?= data/workload-$(VERSION).json
gate-corpus: ## Run the corpus sensitivity gate and, if it passes, print the snapshot hash
	@test -d data/$(VERSION) || { echo "FAIL -- no corpus at data/$(VERSION)"; exit 1; }
	@test -f "$(WORKLOAD)" || { \
	   echo "FAIL -- no workload at $(WORKLOAD)"; \
	   echo "        It must live OUTSIDE data/$(VERSION)/: rag.ingest globs that directory and"; \
	   echo "        asserts doc_id == filename, so a workload file dropped in it breaks ingestion."; \
	   exit 1; }
	$(PY) experiments/scripts/corpus_gate.py --version $(VERSION) --workload $(WORKLOAD) \
	  $(if $(STRUCTURAL),--structural-only,) $(if $(REPORT),--report $(REPORT),)

mu-hit: ## mu_hit probe shakedown against a LOCAL gateway (NOT a measurement)
	@command -v k6 >/dev/null || { echo "SKIPPED -- k6 not installed"; exit 0; }
	@lsof -ti tcp:8080 >/dev/null 2>&1 || { echo "FAIL -- no gateway on :8080 (make dev)"; exit 1; }
	@echo "  ┌─────────────────────────────────────────────────────────────┐"
	@echo "  │  SHAKEDOWN ONLY -- CO-HOSTED generator, numbers NOT citable. │"
	@echo "  │  mu_hit decides whether S1's wording stands, so    │"
	@echo "  │  the RECORDED probe must run from a second machine:          │"
	@echo "  │    k6 run -e GATEWAY_URL=http://<sut-ip>:8080 \\              │"
	@echo "  │           experiments/k6/mu_hit.js                           │"
	@echo "  └─────────────────────────────────────────────────────────────┘"
	k6 run -e MODE=$${MODE:-tier1} -e RATE_RPS=$${RATE_RPS:-60} -e VUS=$${VUS:-20} \
	  -e DURATION=$${DURATION:-20s} -e PROBE_SIZE=$${PROBE_SIZE:-5} experiments/k6/mu_hit.js

ui: ## Build the demo UI bundle. Node is BUILD-time only.
	@command -v npm >/dev/null || { echo "SKIPPED -- npm not installed"; exit 0; }
	@echo "  Building to ui/dist. The gateway serves it; no dev server runs at demo time,"
	@echo "  so nothing competes with the model for the memory envelope."
	cd ui && npm install --no-audit --no-fund && npm run build
	@echo "  OK -- restart 'make dev' to pick it up, then open http://localhost:8080"

figures: ## Regenerate every figure from raw/ (raw is write-once)
	$(PY) experiments/scripts/make_figures.py

# NOTE: uses grep, not rg. `rg` is a zsh alias here, not a binary on PATH, so under
# make's /bin/bash it silently vanished and every check reported "clean" — a vacuous
# pass, which is the exact failure mode this repo's verification discipline forbids.
DOCSRC := $(shell find docs -name '*.md' -not -path 'docs/archive/*') README.md CLAUDE.md

check: ## Documentation consistency sweep
	@echo "--- dropped scope appearing as a live commitment ---"
	@grep -n -E 'learned predictor|predictor-gated|semantic routing' $(DOCSRC) || echo "  clean"
	@echo "--- approximate index must always say never mid-study ---"
	@grep -n 'HNSW' $(DOCSRC) || echo "  clean"
	@echo "--- stale schedule references ---"
	@grep -n -E 'Sep 13|W5.W9|W10.W22|W9 report' $(DOCSRC) || echo "  clean"
	@echo "--- untracked files ---"
	@git status --short
