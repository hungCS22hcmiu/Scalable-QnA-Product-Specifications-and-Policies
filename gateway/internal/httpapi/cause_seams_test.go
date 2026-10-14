package httpapi

// Test scaffolding for item 2.3 (docs/work/2026-10-14-refusal-cause-code/plan.md, step 6).
//
// harness_test.go says new seams may be added with a note in the task, and may not loosen a strict
// check. These three are WRAPPERS built from the harness's own fields, in a new file, so the harness
// itself is not edited and every check it makes still runs: the wrapped fakeRAG still enforces
// top_k == 0 and records every call, and the wrapped fakeStore is the same store.
//
//   - anyNamespaceStore ignores the namespace in the search. The real search never returns a
//     wrong-namespace candidate, so the NAMESPACE cause is unreachable with the harness's own store;
//     this is the "Redis filter and Go's check disagree" case the cause exists to flag (review F4).
//   - textlessRAG is a pre-1.4 server: chunk IDs, no evidence text.
//   - zeroChunkRAG answers Retrieve with no chunks at all.

import (
	"context"
	"net"
	"testing"

	"google.golang.org/grpc"

	"github.com/hung/thesis/gateway/internal/cache"
	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/ragpb"
)

// anyNamespaceStore is the harness store with a search that does not filter by namespace.
type anyNamespaceStore struct{ *fakeStore }

func (s anyNamespaceStore) NearestTier2InNamespace(_ context.Context, vec []float32, namespace string, k int) ([]cache.Candidate, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.namespaces = append(s.namespaces, namespace)
	s.calls["NearestTier2InNamespace"]++
	return s.nearest(vec, k, func(cache.Tier2Entry) bool { return true }), nil
}

// textlessRAG is the harness's fake service whose Retrieve drops the evidence text.
type textlessRAG struct{ *fakeRAG }

func (r textlessRAG) Retrieve(ctx context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	resp, err := r.fakeRAG.Retrieve(ctx, req) // keeps the call log and the strict checks
	if err != nil {
		return nil, err
	}
	resp.Texts = nil
	return resp, nil
}

// zeroChunkRAG is the harness's fake service whose Retrieve finds nothing for a known product.
type zeroChunkRAG struct{ *fakeRAG }

func (r zeroChunkRAG) Retrieve(ctx context.Context, req *ragpb.RetrieveRequest) (*ragpb.RetrieveResponse, error) {
	resp, err := r.fakeRAG.Retrieve(ctx, req)
	if err != nil {
		return nil, err
	}
	return &ragpb.RetrieveResponse{DatasetEpoch: resp.GetDatasetEpoch()}, nil
}

// useRAG points the handler at svc, served on its own listener, and stops it when the test ends.
// Call it between asks, never during one: the handler reads RAG without a lock.
func (hs *harness) useRAG(t *testing.T, svc ragpb.RagServiceServer) {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	srv := grpc.NewServer()
	ragpb.RegisterRagServiceServer(srv, svc)
	go func() { _ = srv.Serve(lis) }()
	client, err := ragclient.New(lis.Addr().String())
	if err != nil {
		srv.Stop()
		t.Fatalf("ragclient: %v", err)
	}
	hs.h.RAG = client
	t.Cleanup(func() {
		_ = client.Close()
		srv.Stop()
	})
}
