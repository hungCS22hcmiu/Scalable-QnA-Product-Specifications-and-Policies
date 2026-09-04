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
        chunks, epoch = retrieve.retrieve(request.query, top_k=top_k)
        return rag_pb2.RetrieveResponse(
            chunk_ids=[c.chunk_id for c in chunks],
            scores=[c.score for c in chunks],
            dataset_epoch=epoch,
        )

    def Answer(self, request, context):
        top_k = request.top_k or config.TOP_K
        chunks, epoch = retrieve.retrieve(request.query, top_k=top_k)
        text = generate.generate(request.query, chunks)
        # stream=false is the only path in scope (SSE dropped, ADR-016) -- exactly one
        # terminal chunk, never per-token emission.
        yield rag_pb2.AnswerChunk(
            text=text,
            done=True,
            source_chunk_ids=[c.chunk_id for c in chunks],
            model_used=config.LLM_MODEL_ID,
            dataset_epoch=epoch,
        )


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    rag_pb2_grpc.add_RagServiceServicer_to_server(RagServicer(), server)
    server.add_insecure_port(config.GRPC_ADDR)
    server.start()
    print(f"rag.server listening on {config.GRPC_ADDR}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
