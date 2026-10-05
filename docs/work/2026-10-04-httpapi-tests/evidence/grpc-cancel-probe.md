# Probe for U1 / F-A — 2026-10-04, grpc-go v1.83.0 (the version gateway/go.mod pins), go 1.26.1
# A standalone module: Go forbids importing gateway/internal/ragpb from outside the gateway module,
# so the probe uses grpc's own health service, whose Watch is server-streaming like Answer.

## Output of: go test -v -count=1 ./...
```
=== RUN   TestCancelledStreamIsNotContextCanceled
    probe_test.go:39: err=rpc error: code = Canceled desc = context canceled  type=*status.Error  errors.Is(context.Canceled)=false
    probe_test.go:43: unary err=rpc error: code = Canceled desc = context canceled  errors.Is(context.Canceled)=false
--- PASS: TestCancelledStreamIsNotContextCanceled (0.07s)
PASS
ok  	probe	0.549s
```

## probe_test.go
```go
package probe

import (
	"context"
	"errors"
	"net"
	"testing"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	hpb "google.golang.org/grpc/health/grpc_health_v1"
)

// Mirrors ragclient.Answer: a server-streaming Recv loop whose client ctx is cancelled mid-stream.
func TestCancelledStreamIsNotContextCanceled(t *testing.T) {
	lis, _ := net.Listen("tcp", "127.0.0.1:0")
	g := grpc.NewServer()
	hs := health.NewServer()
	hpb.RegisterHealthServer(g, hs)
	go g.Serve(lis)
	defer g.Stop()

	conn, err := grpc.NewClient(lis.Addr().String(), grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	st, err := hpb.NewHealthClient(conn).Watch(ctx, &hpb.HealthCheckRequest{})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := st.Recv(); err != nil { // first status message
		t.Fatal(err)
	}
	go func() { time.Sleep(50 * time.Millisecond); cancel() }()
	_, err = st.Recv()
	t.Logf("err=%v  type=%T  errors.Is(context.Canceled)=%v", err, err, errors.Is(err, context.Canceled))

	// Unary path (like Retrieve) with an already-cancelled ctx.
	_, err = hpb.NewHealthClient(conn).Check(ctx, &hpb.HealthCheckRequest{})
	t.Logf("unary err=%v  errors.Is(context.Canceled)=%v", err, errors.Is(err, context.Canceled))
}
```
