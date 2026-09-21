// Command gateway is the resource-governing HTTP gateway (Final_Proposal.md §6.1).
// It wires packages together and holds no logic of its own.
package main

import (
	"context"
	"log"
	"math"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/hung/thesis/gateway/internal/admission"
	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/catalog"
	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/httpapi"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
	"github.com/hung/thesis/gateway/internal/telemetry"
	"github.com/redis/go-redis/v9"
)

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getenvFloat(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
		log.Fatalf("gateway: %s=%q is not a number", key, v)
	}
	return def
}

func getenvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
		log.Fatalf("gateway: %s=%q is not an integer", key, v)
	}
	return def
}

// spaHandler serves the built single-page app: real files where they exist, index.html
// everywhere else. The fallback is what lets the client-side router own /p/{doc_id} -- without
// it, opening a product page directly (or reloading one, which the demo does constantly when
// driving several tabs) would 404 on a path the server has never heard of.
func spaHandler(dir string) http.Handler {
	files := http.FileServer(http.Dir(dir))
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		clean := filepath.Clean(r.URL.Path)
		if clean != "/" {
			if _, err := os.Stat(filepath.Join(dir, clean)); err == nil {
				files.ServeHTTP(w, r)
				return
			}
		}
		http.ServeFile(w, r, filepath.Join(dir, "index.html"))
	})
}

func main() {
	redisAddr := getenv("REDIS_URL", "localhost:6379")
	ollamaURL := getenv("OLLAMA_BASE_URL", "http://localhost:11434")
	ragGRPCAddr := getenv("RAG_GRPC_ADDR", "localhost:50051")
	httpAddr := getenv("HTTP_ADDR", ":8080")

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})

	rag, err := ragclient.New(ragGRPCAddr)
	if err != nil {
		log.Fatalf("gateway: connecting to RAG service at %s: %v", ragGRPCAddr, err)
	}
	defer rag.Close()

	store := cache.NewStore(rdb, embed.Dim)

	// Idempotent: creates idx:cache on first run, no-ops afterwards. Done at startup rather than
	// lazily so a schema problem surfaces here, not on the first user request.
	if err := store.EnsureCacheIndex(context.Background()); err != nil {
		log.Fatalf("gateway: creating %s: %v", cache.CacheIndexName, err)
	}

	// nomic-embed-text, 768-dim (ADR-003) -- frozen, and must match the dim idx:cache declares.
	embedder := embed.New(ollamaURL, embed.Model)

	// tau and theta are DEMO VALUES, not frozen. Read from env so "what about tau = 0.86?" is a
	// five-second restart rather than an argument. Both are swept for anything reported
	// (proposal 9.4, rules.md #10).
	thresholds := reuse.Thresholds{
		Tau:   getenvFloat("REUSE_TAU", 0.85),
		Theta: getenvFloat("REUSE_THETA", 0.60),
		// +Inf DISABLES the short-circuit. This used to default to 1.0 on the assumption that
		// cosine similarity reaches it "only on an identical vector" and that case was
		// unreachable in practice -- WRONG, discovered live 2026-09-09: asking the byte-identical
		// question about two different products embeds to the same vector both times, so
		// similarity is exactly 1.0 and the short-circuit fired, serving one product's cached
		// answer for another's question with no provenance/namespace check at all (it runs before
		// Classify/Namespace). +Inf is unreachable by construction, not just "unreachable in
		// practice" -- cosine similarity is capped at 1.0. Measured on dev-v0, no lower value is
		// safe either -- traps and correct reuses interleave, the worst trap scoring 0.9685
		// against only one correct reuse above it.
		TauHigh: getenvFloat("REUSE_TAU_HIGH", math.Inf(1)),
	}
	// The lane band is the two-lane experiment's selector, same DEMO-value status as tau/theta
	// (.docs/work/two-lane-cache). LANE_SIGMA = 0.2 sits in the gap measured on dev-v0
	// 2026-09-06: spec questions scored 0.00 and policy questions 0.40-0.80, nothing in between.
	//
	// LANE_SIGMA_HI defaults to LANE_SIGMA, which COLLAPSES the band and disables the MIXED lane
	// entirely -- the original two-lane rule, bit for bit. That default is deliberate, not
	// laziness:
	//
	//  1. Turning it on is a RULE CHANGE and must be pre-registered before any reported run
	//     (approvals.md). A rule that enables itself by default cannot be pre-registered.
	//  2. Stratum D is "impossible in dev-v0" per data-card.md 2 -- it needs the product<->policy
	//     join key of ADR-024 requirement 1, which lands with v1. The operating point belongs to
	//     the sweep on that corpus, not to a demo default chosen from this one.
	//
	// [0.20, 0.60) is the MEASURED candidate, not a guess: on dev-v0 2026-09-06, policy_frac was
	// 0.00 for all 10 spec questions, 0.20-0.40 for 5 of 6 mixed ones and 0.60-0.80 for all 10
	// policy ones. An earlier comment here claimed dev-v0 "cannot calibrate the band"; that was
	// reasoning ahead of measurement and it was WRONG -- MIXED and POLICY separate cleanly. The
	// real boundary problem is at Lo: the sixth mixed question retrieved zero policy chunks and
	// so classifies SPEC, with its policy half ungrounded. See approvals.md.
	band := reuse.LaneBand{Lo: getenvFloat("LANE_SIGMA", 0.20)}
	band.Hi = getenvFloat("LANE_SIGMA_HI", band.Lo)
	mixedLane := "DISABLED (collapsed band)"
	if band.Hi > band.Lo {
		mixedLane = "ENABLED -- must be pre-registered before any reported run"
	}
	// > 1.0, not >= 1.0: cosine similarity's ceiling IS 1.0, reachable on an identical vector
	// (e.g. the same question text asked about two different products) -- see the TauHigh
	// comment above. A threshold of exactly 1.0 is NOT disabled.
	shortCircuit := "DISABLED"
	if thresholds.TauHigh <= 1.0 {
		shortCircuit = "ENABLED -- hits at or above tau_high are served on SIMILARITY ALONE, with no provenance check"
	}
	log.Printf("gateway: tau=%.3f theta=%.2f tau_high=%.3f lane_band=[%.2f,%.2f) dim=%d index=%s  (all DEMO values, swept later)\n"+
		"         MIXED lane: %s\n"+
		"         short-circuit: %s",
		thresholds.Tau, thresholds.Theta, thresholds.TauHigh, band.Lo, band.Hi, embed.Dim,
		cache.CacheIndexName, mixedLane, shortCircuit)

	// Admission control. The permit count comes from OLLAMA_NUM_PARALLEL, frozen at 4 by ADR-017
	// and pinned in the environment that `make env-check` verifies -- read here rather than
	// re-declared, so the gateway can never bound concurrency to a different number than the one
	// Ollama was started with and the run reports.
	//
	// ⚠️ env-check records finding F1: for qwen3.5 this variable currently has NO effect, because
	// ollama overrides it to -np 1. The permit pool is therefore bounding the gateway to a
	// concurrency the model server does not actually offer, and surplus permits queue INSIDE
	// ollama where this gateway cannot shed them. Resolve that ADR before reading any shed rate
	// as a property of the gateway.
	permits := getenvInt("OLLAMA_NUM_PARALLEL", 4)
	// Queue budget: how many callers may WAIT rather than be shed. Zero means shed immediately
	// once the permits are gone. A DEMO value, swept like the rest.
	queueBudget := getenvInt("GEN_QUEUE_BUDGET", 2*permits)
	pool := admission.New(permits, queueBudget)
	log.Printf("gateway: admission permits=%d queue_budget=%d  (permits from OLLAMA_NUM_PARALLEL, ADR-017;\n"+
		"         see env-check F1 -- ollama may serve -np 1 regardless, in which case surplus\n"+
		"         permits queue inside ollama and this gateway cannot shed them)",
		permits, queueBudget)

	// Bounded cache. ADR-027 fixes capacity at round(0.25 * K) ENTRIES, where K is the frozen
	// workload's distinct-query count -- so the absolute number is not knowable until the corpus
	// is frozen, and 0 (unbounded) is the honest default until then. It is logged either way:
	// an unbounded run is a valid thing to measure and never a thing to measure by accident,
	// because every hit rate it produces is an upper bound no deployment reaches.
	capacity := getenvInt("CACHE_CAPACITY", 0)
	capacityNote := "UNBOUNDED -- hit rates are an upper bound; set CACHE_CAPACITY=round(0.25*K) once K is frozen (ADR-027)"
	if capacity > 0 {
		capacityNote = "entries, LRU, enforced by the gateway (see cache/capacity.go)"
	}
	log.Printf("gateway: cache_capacity=%d  %s", capacity, capacityNote)

	// Per-request evaluation log (interfaces.md H, ADR-029). RUN_ID empty disables it, which is
	// what `make dev` runs with: a functional run must not leave a file that looks like a
	// measurement. raw/ is write-once, so a reused RUN_ID refuses to start rather than appending
	// to a finished run.
	evalLog, err := telemetry.Open(getenv("RESULTS_DIR", "experiments/results"), getenv("RUN_ID", ""))
	if err != nil {
		log.Fatalf("gateway: opening evaluation log: %v", err)
	}
	if evalLog == nil {
		log.Printf("gateway: evaluation log DISABLED (RUN_ID unset) -- functional run, produces no measurement")
	} else {
		log.Printf("gateway: evaluation log -> %s/%s/raw/requests.jsonl",
			getenv("RESULTS_DIR", "experiments/results"), getenv("RUN_ID", ""))
	}

	handler := httpapi.NewHandler(store, rag, embedder, thresholds, band, pool)
	handler.Catalog = catalog.New(rdb)
	handler.Capacity = capacity
	handler.Eval = evalLog
	handler.RunID = getenv("RUN_ID", "")
	handler.ConfigID = getenvInt("CONFIG_ID", 0)
	handler.Mutation = getenv("MUTATION", "off")

	mux := http.NewServeMux()
	mux.HandleFunc("/ask", handler.Ask)

	// Demo UI support (docs/defense_demo.md §3). Neither endpoint is on a measured path, and
	// /stats is explicitly not the measurement channel -- that is the evaluation log.
	mux.HandleFunc("/products", handler.Products)
	mux.HandleFunc("/stats", handler.Stats)

	// The built UI is served BY THE GATEWAY, not by a dev server. That is deliberate: at demo
	// time there is no Node process competing for the memory envelope the thesis is about, and
	// the page is same-origin with /ask so there is no CORS layer to explain on stage. Node is a
	// BUILD-time dependency only (`make ui`).
	if uiDir := getenv("UI_DIR", ""); uiDir != "" {
		if _, err := os.Stat(filepath.Join(uiDir, "index.html")); err == nil {
			mux.Handle("/", spaHandler(uiDir))
			log.Printf("gateway: serving demo UI from %s", uiDir)
		} else {
			log.Printf("gateway: UI_DIR=%s has no index.html -- run `make ui` (API still served)", uiDir)
		}
	}

	// Graceful shutdown exists for ONE reason: the evaluation log is buffered, and a hard exit
	// would discard whatever had not been written -- silently shortening the run's own record of
	// itself. Flush before leaving.
	srv := &http.Server{Addr: httpAddr, Handler: mux}
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-stop
		log.Printf("gateway: shutting down, flushing the evaluation log")
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdownCtx)
	}()

	log.Printf("gateway listening on %s (redis=%s rag=%s)", httpAddr, redisAddr, ragGRPCAddr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Printf("gateway: %v", err)
	}
	if err := evalLog.Close(); err != nil {
		log.Printf("gateway: closing evaluation log: %v", err)
	}
	if n := evalLog.Dropped(); n > 0 {
		log.Fatalf("gateway: THIS RUN IS INCOMPLETE -- %d evaluation record(s) were dropped", n)
	}
}
