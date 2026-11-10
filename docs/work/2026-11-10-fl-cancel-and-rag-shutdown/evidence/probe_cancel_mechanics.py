"""Design-stage probe (2026-11-10): settles two library facts §3 rests on. No model, no Redis.

P1  grpcio: a unary-stream handler blocked BEFORE its first yield gets its add_callback callback when
    the client cancels, and how fast.
P2  httpx AsyncClient: cancelling the asyncio task of a POST whose server has not sent any header yet
    closes the TCP connection, and how fast the server sees it (recv returns b"").
P3  the same with the planned shape: a threading.Event polled every 50 ms from inside asyncio.run.

Run: cd rag && python3 -I ../docs/work/2026-11-10-fl-cancel-and-rag-shutdown/evidence/probe_cancel_mechanics.py
"""

import asyncio
import socket
import threading
import time
from concurrent import futures

import grpc
import httpx


# ---------- a fake HTTP server that never answers and records when the client closes ----------
def fake_silent_server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    closed_at = {}

    def run():
        conn, _ = srv.accept()
        conn.recv(65536)  # the request; never answered
        while True:
            data = conn.recv(65536)
            if not data:
                closed_at["t"] = time.monotonic()
                return

    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1], closed_at


# ---------- P1 ----------
def p1():
    fired = {}
    entered = threading.Event()

    def handler(req, context):
        context.add_callback(lambda: fired.setdefault("t", time.monotonic()))
        entered.set()
        time.sleep(2.0)  # blocked, no yield yet
        yield b"late"

    h = grpc.method_handlers_generic_handler(
        "probe.P", {"Answer": grpc.unary_stream_rpc_method_handler(handler)}
    )
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    server.add_generic_rpc_handlers((h,))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    ch = grpc.insecure_channel(f"127.0.0.1:{port}")
    call = ch.unary_stream("/probe.P/Answer")(b"q")
    entered.wait(2)
    time.sleep(0.2)
    t0 = time.monotonic()
    call.cancel()
    time.sleep(0.5)
    server.stop(None)
    if "t" in fired:
        print(
            f"P1 add_callback fired {1000 * (fired['t'] - t0):.1f} ms after client cancel"
        )
    else:
        print("P1 add_callback did NOT fire within 0.5 s")


# ---------- P2 ----------
def p2():
    port, closed_at = fake_silent_server()

    async def main():
        async with httpx.AsyncClient(timeout=120.0) as c:
            task = asyncio.create_task(
                c.post(f"http://127.0.0.1:{port}/api/generate", json={"stream": False})
            )
            await asyncio.sleep(0.3)
            t0 = time.monotonic()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return t0

    t0 = asyncio.run(main())
    time.sleep(0.3)
    if "t" in closed_at:
        print(
            f"P2 server saw close {1000 * (closed_at['t'] - t0):.1f} ms after task.cancel()"
        )
    else:
        print("P2 server did NOT see a close")


# ---------- P3 ----------
def p3():
    port, closed_at = fake_silent_server()
    stop = threading.Event()

    async def post_until_stop():
        async with httpx.AsyncClient(timeout=120.0) as c:
            req = asyncio.create_task(
                c.post(f"http://127.0.0.1:{port}/api/generate", json={"stream": False})
            )
            while not req.done():
                if stop.is_set():
                    req.cancel()
                    try:
                        await req
                    except asyncio.CancelledError:
                        pass
                    return "stopped"
                await asyncio.sleep(0.05)
            return "done"

    out = {}
    th = threading.Thread(
        target=lambda: out.setdefault("r", asyncio.run(post_until_stop()))
    )
    th.start()
    time.sleep(0.3)
    t0 = time.monotonic()
    stop.set()
    th.join(2)
    time.sleep(0.2)
    seen = f"{1000 * (closed_at['t'] - t0):.1f} ms" if "t" in closed_at else "NOT seen"
    print(
        f"P3 result={out.get('r')} thread_alive={th.is_alive()} server saw close: {seen}"
    )


if __name__ == "__main__":
    print(f"grpcio {grpc.__version__}, httpx {httpx.__version__}")
    p1()
    p2()
    p3()
