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
# Names the retrieval a run or a reference set was made with. Every ADR that changes retrieval
# bumps it. First value: ADR-020's category swap plus ADR-021's own-product refill.
RETRIEVAL_VERSION = "adr-021"

# --- dataset version, bump for v1, never re-chunk in place ---
# The default is v1, the frozen corpus (item 4.4, 2026-10-29: the author retired dev-v0). Set
# DATASET_VERSION=dev-v0 to use the old development corpus; `make demo-reset` still does.
# An empty value counts as unset: "" would make ingest read data/.
DATASET_VERSION = os.environ.get("DATASET_VERSION") or "v1"

# --- Connections ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# --- Corpus vector index (this RAG service's own retrieval index) ---
# NOT the gateway's Tier-2 answer cache (interfaces.md §D: idx:cache, t2:*) — that is a
# separate index the gateway owns starting W6/W7. Keep these prefixes visibly distinct.
CORPUS_INDEX_NAME = "idx:corpus"
CORPUS_KEY_PREFIX = "corpus:"

# The dataset epoch is a file, read at call time: see rag/epoch.py (interfaces.md E, ADR-008).

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
# How long a SIGTERM (or SIGINT) waits for the Answer calls in flight before gRPC cancels them.
# 60 s, like the gateway's shutdownGrace. Not a frozen value. A bad value fails at import, so the
# server does not start.
SHUTDOWN_GRACE_S = float(os.environ.get("RAG_SHUTDOWN_GRACE_S", "60"))
