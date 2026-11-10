"""Design-stage probe P4 (2026-11-10): when server.stop(grace) ends its grace with an RPC still
running, does that RPC's add_callback fire, and when? And does a NEW RPC sent during the grace get
UNAVAILABLE? No model, no Redis."""
import threading, time
from concurrent import futures
import grpc

fired, entered = {}, threading.Event()

def handler(req, context):
    context.add_callback(lambda: fired.setdefault("t", time.monotonic()))
    entered.set()
    time.sleep(3.0)  # still running when the grace ends
    yield b"late"

h = grpc.method_handlers_generic_handler("probe.P", {"Answer": grpc.unary_stream_rpc_method_handler(handler)})
server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
server.add_generic_rpc_handlers((h,))
port = server.add_insecure_port("127.0.0.1:0")
server.start()
ch = grpc.insecure_channel(f"127.0.0.1:{port}")
call = ch.unary_stream("/probe.P/Answer")(b"q")
entered.wait(2)
t0 = time.monotonic()
done = server.stop(0.5)
time.sleep(0.1)
try:
    list(grpc.insecure_channel(f"127.0.0.1:{port}").unary_stream("/probe.P/Answer")(b"q2", timeout=1))
    print("P4 new RPC during grace: ACCEPTED")
except grpc.RpcError as e:
    print(f"P4 new RPC during grace: {e.code().name}")
done.wait(3)
print(f"P4 grace 0.5 s: callback fired at +{1000*(fired['t']-t0):.0f} ms" if "t" in fired else "P4 callback did NOT fire")
try:
    list(call)
except grpc.RpcError as e:
    print(f"P4 running RPC ended with {e.code().name}")
