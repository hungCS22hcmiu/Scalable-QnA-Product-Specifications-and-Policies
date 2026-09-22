package ragclient

import (
	"context"
	"io"
	"testing"

	"github.com/hung/thesis/gateway/internal/ragpb"
	"google.golang.org/grpc"
)

// fakeAnswerStream yields exactly one terminal AnswerChunk, matching what the real server sends
// (stream=false only, ADR-016). Embeds grpc.ClientStream (nil) since Answer() only calls Recv().
type fakeAnswerStream struct {
	grpc.ClientStream
	sent bool
}

func (f *fakeAnswerStream) Recv() (*ragpb.AnswerChunk, error) {
	if f.sent {
		return nil, io.EOF
	}
	f.sent = true
	return &ragpb.AnswerChunk{Text: "900W", Done: true, SourceChunkIds: []string{"product-laptops-02#chunk-0"}}, nil
}

type fakeAnswerClient struct {
	ragpb.RagServiceClient
	lastAnswerReq *ragpb.AnswerRequest
}

func (f *fakeAnswerClient) Answer(_ context.Context, in *ragpb.AnswerRequest, _ ...grpc.CallOption) (grpc.ServerStreamingClient[ragpb.AnswerChunk], error) {
	f.lastAnswerReq = in
	return &fakeAnswerStream{}, nil
}

// TestAnswerPassesProductID pins ADR-034: product_id must reach the wire request unchanged, so
// the RAG service's own fallback retrieval (used when retrievedChunkIDs is empty) can scope its
// search the same way Retrieve's does.
func TestAnswerPassesProductID(t *testing.T) {
	fake := &fakeAnswerClient{}
	c := &Client{rpc: fake}

	if _, err := c.Answer(context.Background(), "what is the power rating?", 5, nil, "product-laptops-02"); err != nil {
		t.Fatalf("Answer returned error: %v", err)
	}
	if got := fake.lastAnswerReq.GetProductId(); got != "product-laptops-02" {
		t.Fatalf("AnswerRequest.ProductId = %q, want %q", got, "product-laptops-02")
	}
}

// TestAnswerEmptyProductIDIsZeroValue pins the backward-compatible case.
func TestAnswerEmptyProductIDIsZeroValue(t *testing.T) {
	fake := &fakeAnswerClient{}
	c := &Client{rpc: fake}

	if _, err := c.Answer(context.Background(), "what is the power rating?", 5, nil, ""); err != nil {
		t.Fatalf("Answer returned error: %v", err)
	}
	if got := fake.lastAnswerReq.GetProductId(); got != "" {
		t.Fatalf("AnswerRequest.ProductId = %q, want empty", got)
	}
}
