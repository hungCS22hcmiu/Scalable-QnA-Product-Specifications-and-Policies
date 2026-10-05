"""gRPC server exposing RagService (interfaces.md §B). Two RPCs, deliberately: Retrieve lets
the C1 cascade (W12+) get source overlap without paying for generation; Answer is the full
miss path. Neither is hand-edited generated code -- both wrap rag/{retrieve,generate}.py.
"""

from concurrent import futures

import grpc

from rag import config, generate, retrieve
from rag.pb.rag.v1 import rag_pb2, rag_pb2_grpc


class RagServicer(rag_pb2_grpc.RagServiceServicer):
    def Retrieve(self, request, context):
        top_k = request.top_k or config.TOP_K
        chunks, epoch = retrieve.retrieve(request.query, top_k=top_k, product_id=request.product_id)
        # texts[i] must be the text of chunk_ids[i] (interfaces.md B v0.9). All three arrays come
        # from this one list; a shifted texts would score a cached answer against the wrong chunk
        # with no error anywhere. Proved against Redis by `make seam-check`.
        return rag_pb2.RetrieveResponse(
            chunk_ids=[c.chunk_id for c in chunks],
            scores=[c.score for c in chunks],
            dataset_epoch=epoch,
            texts=[c.text for c in chunks],
        )

    def Answer(self, request, context):
        top_k = request.top_k or config.TOP_K
        # Single retrieval: when the caller has already retrieved for this query,
        # ground on exactly its
        # chunks instead of retrieving again. The gateway runs its retrieval concurrently with the
        # embedding, so a banded miss would otherwise retrieve twice -- and the second one re-embeds
        # the query, which is the expensive half.
        if request.retrieved_chunk_ids:
            chunks, epoch = retrieve.fetch_by_ids(list(request.retrieved_chunk_ids))
        else:
            chunks, epoch = retrieve.retrieve(
                request.query, top_k=top_k, product_id=request.product_id
            )
        text = generate.generate(request.query, chunks)
        # stream=false is the only path in scope (SSE dropped) -- exactly one
        # terminal chunk, never per-token emission.
        yield rag_pb2.AnswerChunk(
            text=text,
            done=True,
            source_chunk_ids=[c.chunk_id for c in chunks],
            model_used=config.LLM_MODEL_ID,
            dataset_epoch=epoch,
        )


def build_server(addr: str) -> tuple[grpc.Server, int]:
    """The server serve() runs, bound to addr but not started. Returns it with its bound port.
    Separate from serve() so tests can bind exactly what production binds.

    SO_REUSEPORT is OFF. grpcio turns it on by default, which let a second rag.server bind the
    address a stale one held, with the gateway's connections split between them silently. Off, the
    second bind raises RuntimeError. SO_REUSEADDR is untouched, so a restart right after a kill
    still binds."""
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4), options=[("grpc.so_reuseport", 0)]
    )
    rag_pb2_grpc.add_RagServiceServicer_to_server(RagServicer(), server)
    port = server.add_insecure_port(addr)
    return server, port


def serve() -> None:
    server, _ = build_server(config.GRPC_ADDR)
    server.start()
    print(f"rag.server listening on {config.GRPC_ADDR}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
