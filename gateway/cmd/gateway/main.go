// Command gateway is the resource-governing HTTP gateway (Final_Proposal.md §6.1).
// It wires packages together and holds no logic of its own.
package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strconv"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/httpapi"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
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
	thresholds := reuse.Thresholds{Tau: getenvFloat("REUSE_TAU", 0.85), Theta: getenvFloat("REUSE_THETA", 0.60)}
	log.Printf("gateway: tau=%.3f theta=%.2f dim=%d index=%s  (tau/theta are DEMO values, swept later)",
		thresholds.Tau, thresholds.Theta, embed.Dim, cache.CacheIndexName)

	handler := httpapi.NewHandler(store, rag, embedder, thresholds)

	mux := http.NewServeMux()
	mux.HandleFunc("/ask", handler.Ask)

	log.Printf("gateway listening on %s (redis=%s rag=%s)", httpAddr, redisAddr, ragGRPCAddr)
	log.Fatal(http.ListenAndServe(httpAddr, mux))
}
