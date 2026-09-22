package ragclient

import (
	"context"
	"testing"

	"github.com/hung/thesis/gateway/internal/ragpb"
	"google.golang.org/grpc"
)

// fakeRagServiceClient captures the outgoing request so tests can assert on it without a real
// RAG service. Only Retrieve/Answer are exercised by this package's callers, so the other
// RagServiceClient methods are unused here.
type fakeRagServiceClient struct {
	ragpb.RagServiceClient
	lastRetrieveReq *ragpb.RetrieveRequest
}

func (f *fakeRagServiceClient) Retrieve(_ context.Context, in *ragpb.RetrieveRequest, _ ...grpc.CallOption) (*ragpb.RetrieveResponse, error) {
	f.lastRetrieveReq = in
	return &ragpb.RetrieveResponse{}, nil
}

// TestRetrievePassesProductID pins product-scoped retrieval: product_id must reach the wire request unchanged,
// so the RAG service can scope its search to that product.
func TestRetrievePassesProductID(t *testing.T) {
	fake := &fakeRagServiceClient{}
	c := &Client{rpc: fake}

	if _, err := c.Retrieve(context.Background(), "what is the power rating?", 5, "product-laptops-02"); err != nil {
		t.Fatalf("Retrieve returned error: %v", err)
	}
	if got := fake.lastRetrieveReq.GetProductId(); got != "product-laptops-02" {
		t.Fatalf("RetrieveRequest.ProductId = %q, want %q", got, "product-laptops-02")
	}
}

// TestRetrieveEmptyProductIDIsZeroValue pins the backward-compatible case: a caller that
// supplies no product_id must produce the same empty-string request field as before this
// change, so unscoped retrieval keeps behaving exactly as it did pre.
func TestRetrieveEmptyProductIDIsZeroValue(t *testing.T) {
	fake := &fakeRagServiceClient{}
	c := &Client{rpc: fake}

	if _, err := c.Retrieve(context.Background(), "what is the power rating?", 5, ""); err != nil {
		t.Fatalf("Retrieve returned error: %v", err)
	}
	if got := fake.lastRetrieveReq.GetProductId(); got != "" {
		t.Fatalf("RetrieveRequest.ProductId = %q, want empty", got)
	}
}
