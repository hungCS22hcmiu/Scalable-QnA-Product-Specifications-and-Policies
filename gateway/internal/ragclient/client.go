package ragclient

import (
	"github.com/hung/thesis/gateway/internal/ragpb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

// Client owns the pooled gRPC channel to the Python RAG service (interfaces.md §B).
// "Pooled" means constructed once at startup, not per request -- gRPC multiplexes many
// concurrent calls over one HTTP/2 connection internally, so no custom connection pool is
// needed (architecture-guardrails.md: ragclient/ must not be constructed per request).
type Client struct {
	conn *grpc.ClientConn
	rpc  ragpb.RagServiceClient
}

// New dials target (host:port) once. No TLS in scope -- single-machine envelope (ADR-009).
func New(target string) (*Client, error) {
	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, err
	}
	return &Client{conn: conn, rpc: ragpb.NewRagServiceClient(conn)}, nil
}

func (c *Client) Close() error {
	return c.conn.Close()
}
