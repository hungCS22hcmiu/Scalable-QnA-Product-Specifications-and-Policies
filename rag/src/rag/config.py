"""Frozen constants for the RAG service. One place for ADR-003/ADR-014's values.

Changing any of these mid-study invalidates cross-configuration comparisons
(decisions.md ADR-003, ADR-014) and requires a new ADR + a new dataset_version.
"""

import os

# --- ADR-003: embedding model ---
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768

# --- ADR-014: chunking + retrieval ---
CHUNK_SIZE = 256
CHUNK_OVERLAP = 40
TOP_K = 5

# --- ADR-020/ADR-008: dataset version, bump for v1, never re-chunk in place ---
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
