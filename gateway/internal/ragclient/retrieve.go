package ragclient

import (
	"context"

	"github.com/hung/thesis/gateway/internal/ragpb"
)

// RetrieveResult is retrieval WITHOUT generation. Its whole reason for existing is the C1
// cascade: the rule needs the incoming query's chunk IDs to intersect against a candidate's
// provenance, and paying for a generation to get them would defeat the cache it is guarding
// (ADR-007, interfaces.md B).
type RetrieveResult struct {
	ChunkIDs     []string
	Scores       []float32
	DatasetEpoch uint64
}

// Retrieve runs the retrieval-only RPC. Pass topK = 0 so the RAG service resolves it from
// rag/src/rag/config.py's TOP_K -- the same single-source-of-truth reasoning as
// httpapi.topKServerDefault. A literal here would drift the day ADR-014 changes.
func (c *Client) Retrieve(ctx context.Context, query string, topK uint32) (*RetrieveResult, error) {
	resp, err := c.rpc.Retrieve(ctx, &ragpb.RetrieveRequest{Query: query, TopK: topK})
	if err != nil {
		return nil, err
	}
	return &RetrieveResult{
		ChunkIDs:     resp.GetChunkIds(),
		Scores:       resp.GetScores(),
		DatasetEpoch: resp.GetDatasetEpoch(),
	}, nil
}
