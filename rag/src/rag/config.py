"""Frozen constants for the RAG service. One place for the values.

Changing any of these mid-study invalidates cross-configuration comparisons
(the decision record) and requires a new ADR + a new dataset_version.
"""

import os

# --- embedding model ---
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768

# --- chunking + retrieval ---
CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
TOP_K = 5

# --- dataset version, bump for v1, never re-chunk in place ---
DATASET_VERSION = "dev-v0"

# --- Connections ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# --- Corpus vector index (this RAG service's own retrieval index) ---
# NOT the gateway's Tier-2 answer cache (interfaces.md §D: idx:cache, t2:*) — that is a
# separate index the gateway owns starting W6/W7. Keep these prefixes visibly distinct.
CORPUS_INDEX_NAME = "idx:corpus"
CORPUS_KEY_PREFIX = "corpus:"

# --- Dataset epoch stub ---
# Real epoch tracking (interfaces.md §E) is dependency-map/invalidation scope, W9-W11.
# retrieve() returns this constant until then.
DATASET_EPOCH_STUB = 0

# --- generation LLM ---
LLM_MODEL = "qwen3.5:2b-q4_K_M"    # Ollama tag actually invoked
LLM_MODEL_ID = "qwen3.5-2b"        # wire `model_used` id (interfaces.md §A's frozen example
                                    # string) -- do not conflate with the Ollama tag above
LLM_THINK = False                  # mandatory on every call -- hidden CoT mode inflates
                                    # latency ~5x with no observed quality benefit

# --- envelope ---
LLM_NUM_CTX = 8192

# --- gRPC server (this service) ---
GRPC_ADDR = os.environ.get("RAG_GRPC_ADDR", "0.0.0.0:50051")
