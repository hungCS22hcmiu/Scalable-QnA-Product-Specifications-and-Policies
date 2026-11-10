"""The subprocess entry point of test_server_shutdown.py: the real server.serve(), with no Redis.

The shutdown tests must prove the handlers in serve() itself (the signals, server.stop(grace), the
exit code), because a handler that is missing from the served path only shows when SIGTERM kills an
Answer in flight (F-L design.md, failure mode 6). So this script patches the two retrieval
functions to return one fixed chunk, then calls the real serve(). Everything else comes from the
environment: RAG_GRPC_ADDR, OLLAMA_BASE_URL, DATASET_EPOCH_FILE and RAG_SHUTDOWN_GRACE_S.

Run as a script, never collected: its name does not start with test_.
"""

from rag import retrieve, server
from rag.retrieve import RetrievedChunk

_CHUNK = RetrievedChunk(
    chunk_id="product-laptops-02#chunk-0",
    score=0.9,
    text="UltraBook Air 13: 13-inch display, 1.2 kg.",
    doc_id="product-laptops-02",
    ordinal=0,
)

if __name__ == "__main__":
    retrieve.fetch_by_ids = lambda *args, **kwargs: ([_CHUNK], 41)
    retrieve.retrieve = lambda *args, **kwargs: ([_CHUNK], 41)
    server.serve()
