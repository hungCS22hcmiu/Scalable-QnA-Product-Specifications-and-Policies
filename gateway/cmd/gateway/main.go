// Command gateway is the resource-governing HTTP gateway (Final_Proposal.md §6.1).
// It wires packages together and holds no logic of its own.
package main

import (
	"log"
	"net/http"
	"os"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/httpapi"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/redis/go-redis/v9"
)

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func main() {
	redisAddr := getenv("REDIS_URL", "localhost:6379")
	ragGRPCAddr := getenv("RAG_GRPC_ADDR", "localhost:50051")
	httpAddr := getenv("HTTP_ADDR", ":8080")

	rdb := redis.NewClient(&redis.Options{Addr: redisAddr})

	rag, err := ragclient.New(ragGRPCAddr)
	if err != nil {
		log.Fatalf("gateway: connecting to RAG service at %s: %v", ragGRPCAddr, err)
	}
	defer rag.Close()

	store := cache.NewStore(rdb)
	handler := httpapi.NewHandler(store, rag)

	mux := http.NewServeMux()
	mux.HandleFunc("/ask", handler.Ask)

	log.Printf("gateway listening on %s (redis=%s rag=%s)", httpAddr, redisAddr, ragGRPCAddr)
	log.Fatal(http.ListenAndServe(httpAddr, mux))
}
