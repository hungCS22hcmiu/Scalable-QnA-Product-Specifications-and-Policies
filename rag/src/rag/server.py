"""gRPC server exposing RagService (interfaces.md §B). Two RPCs, deliberately: Retrieve lets
the C1 cascade (W12+) get source overlap without paying for generation; Answer is the full
miss path. Neither is hand-edited generated code -- both wrap rag/{retrieve,generate}.py.
"""

import signal
import threading
import time
from concurrent import futures

import grpc

from rag import config, epoch, generate, retrieve
from rag.pb.rag.v1 import rag_pb2, rag_pb2_grpc


def _stop_on_rpc_end(context) -> threading.Event:
    """An event that gRPC sets when this RPC ends. generate.stop_when hands it to generate(), which
    closes its Ollama request when it is set (F-L).

    add_callback fires on every way an RPC can end: the client cancels (the gateway does that when
    its own client leaves), the deadline passes, the server's shutdown grace runs out, or the call
    finishes normally (then nobody reads the event). If it returns False the RPC had already ended
    and the callback will never run, so the event is set at once. With no context (a direct call in
    a test) the event is never set."""
    stop = threading.Event()
    if context is not None and not context.add_callback(stop.set):
        stop.set()
    return stop


class RagServicer(rag_pb2_grpc.RagServiceServicer):
    def Retrieve(self, request, context):
        # The epoch is read BEFORE the chunk texts (interfaces.md E order rule) and is the value
        # stamped on the response, never the one retrieve.* returns. Read after the texts, a
        # retrieval that straddled an edit would carry the new epoch over pre-edit text, pass the
        # gateway's write-back guard and cache stale text with no trace.
        ep = epoch.read()
        top_k = request.top_k or config.TOP_K
        chunks, _ = retrieve.retrieve(request.query, top_k=top_k, product_id=request.product_id)
        # texts[i] must be the text of chunk_ids[i] (interfaces.md B v0.9). All three arrays come
        # from this one list; a shifted texts would score a cached answer against the wrong chunk
        # with no error anywhere. Proved against Redis by `make seam-check`.
        return rag_pb2.RetrieveResponse(
            chunk_ids=[c.chunk_id for c in chunks],
            scores=[c.score for c in chunks],
            dataset_epoch=ep,
            texts=[c.text for c in chunks],
        )

    def Answer(self, request, context):
        started = time.monotonic()
        stop = _stop_on_rpc_end(context)
        ep = epoch.read()  # first, before any chunk text is read: same rule as Retrieve above
        top_k = request.top_k or config.TOP_K
        # Single retrieval: when the caller has already retrieved for this query,
        # ground on exactly its
        # chunks instead of retrieving again. The gateway runs its retrieval concurrently with the
        # embedding, so a banded miss would otherwise retrieve twice -- and the second one re-embeds
        # the query, which is the expensive half.
        if request.retrieved_chunk_ids:
            chunks, _ = retrieve.fetch_by_ids(list(request.retrieved_chunk_ids))
        else:
            chunks, _ = retrieve.retrieve(
                request.query, top_k=top_k, product_id=request.product_id
            )
        try:
            with generate.stop_when(stop):
                text = generate.generate(request.query, chunks)
        except generate.Cancelled:
            # The RPC ended before the answer. There is no answer, not even a partial one, so no
            # chunk is sent: the gateway (ragclient/answer.go) refuses a stream with no terminal
            # chunk.
            print(
                f"rag.server: Answer stopped after {time.monotonic() - started:.2f} s: "
                "the RPC ended, the Ollama request was closed",
                flush=True,
            )
            return
        # stream=false is the only path in scope (SSE dropped) -- exactly one
        # terminal chunk, never per-token emission.
        yield rag_pb2.AnswerChunk(
            text=text,
            done=True,
            source_chunk_ids=[c.chunk_id for c in chunks],
            model_used=config.LLM_MODEL_ID,
            dataset_epoch=ep,
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


def _install_shutdown(server: grpc.Server, grace: float) -> None:
    """On the first SIGTERM (or SIGINT), stop taking new RPCs and give the ones in flight `grace`
    seconds. server.stop(grace) makes a new RPC fail with UNAVAILABLE and lets a running Answer
    finish; one still running when the grace ends is cancelled by gRPC, which fires its callback
    (_stop_on_rpc_end), so its Ollama request is closed too (P4 in the F-L task's design.md).

    SIGTERM always: `make dev` stops this server with it. SIGINT only if it is not ignored:
    `make dev` starts the server in the background, where SIGINT is ignored, and taking it over
    would turn Ctrl-C plus the trap's SIGTERM into a "second signal" that kills an Answer in
    flight. The first signal resets every handled signal to its default, so a second one ends the
    process at once."""
    signals = [signal.SIGTERM]
    if signal.getsignal(signal.SIGINT) is not signal.SIG_IGN:
        signals.append(signal.SIGINT)

    def handler(signum, frame):
        print(
            f"rag.server: {signal.Signals(signum).name}: refusing new RPCs, "
            f"waiting up to {grace:g} s for the ones in flight",
            flush=True,
        )
        for sig in signals:
            signal.signal(sig, signal.SIG_DFL)
        server.stop(grace)

    for sig in signals:
        signal.signal(sig, handler)


def serve() -> None:
    # No epoch file, no start (interfaces.md E): every response would be stamped 0 and the
    # gateway would discard every write-back. Checked before the port is bound.
    epoch_path, epoch_now = epoch.check()
    server, _ = build_server(config.GRPC_ADDR)
    server.start()
    # The handlers go in after start(), so stop() is only ever called on a started server. A signal
    # before this line takes the default action, and nothing is in flight yet.
    _install_shutdown(server, config.SHUTDOWN_GRACE_S)
    print(
        f"rag.server listening on {config.GRPC_ADDR} "
        f"dataset_epoch_file={epoch_path} epoch={epoch_now}",
        flush=True,
    )
    server.wait_for_termination()
    print("rag.server: stopped", flush=True)


if __name__ == "__main__":
    serve()
