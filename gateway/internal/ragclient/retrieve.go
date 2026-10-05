package ragclient

import (
	"context"
	"errors"
	"fmt"

	"github.com/hung/thesis/gateway/internal/ragpb"
)

// ErrTextsMisaligned means the service sent texts that cannot be aligned with chunk_ids: present,
// but not exactly as long (interfaces.md B: "there is no partial population"). There is no safe way
// to guess which element is missing, so the whole response is refused.
var ErrTextsMisaligned = errors.New("ragclient: texts not aligned with chunk_ids")

// RetrieveResult is retrieval WITHOUT generation. Its whole reason for existing is the C1
// cascade: the rule needs the incoming query's chunk IDs to intersect against a candidate's
// provenance, and paying for a generation to get them would defeat the cache it is guarding
// (interfaces.md B).
type RetrieveResult struct {
	ChunkIDs     []string
	Scores       []float32
	DatasetEpoch uint64
	// Texts[i] is the text of ChunkIDs[i] (interfaces.md B v0.9), or nil when the service sent none.
	// Alignment cannot be checked here -- only length can -- so it rests on server.py building both
	// arrays from one list, and on seam_live_test.go comparing them against Redis.
	//
	// Texts == nil with len(ChunkIDs) > 0 means the service returned chunks WITHOUT evidence text,
	// e.g. a server that predates texts. A reader (the support gate) must not score such a request,
	// must not refuse it as SUPPORT, and must not log it as the gate-off arm (support_lex: null):
	// each would misattribute a stale server to the gate. Key on len(ChunkIDs) > 0, because an
	// empty retrieval is nil too.
	Texts []string
}

// Retrieve runs the retrieval-only RPC. Pass topK = 0 so the RAG service resolves it from
// rag/src/rag/config.py's TOP_K -- the same single-source-of-truth reasoning as
// httpapi.topKServerDefault. A literal here would drift the day the frozen chunking changes.
//
// productID is optional (interfaces.md B v0.8): when non-empty, the RAG service scopes
// its search to that product's own chunk plus every policy chunk, instead of searching the whole
// corpus unscoped. This never changes the reuse decision -- reuse/lane.go and reuse/rule.go still
// decide purely from the chunks that come back, exactly as before.
func (c *Client) Retrieve(ctx context.Context, query string, topK uint32, productID string) (*RetrieveResult, error) {
	resp, err := c.rpc.Retrieve(ctx, &ragpb.RetrieveRequest{Query: query, TopK: topK, ProductId: productID})
	if err != nil {
		return nil, err
	}
	texts := resp.GetTexts()
	switch {
	case len(texts) == 0:
		texts = nil // absent entirely: legal, and the only shape a pre-v0.9 server sends
	case len(texts) != len(resp.GetChunkIds()):
		return nil, fmt.Errorf("%w: %d texts for %d chunk_ids", ErrTextsMisaligned, len(texts), len(resp.GetChunkIds()))
	}
	return &RetrieveResult{
		ChunkIDs:     resp.GetChunkIds(),
		Scores:       resp.GetScores(),
		DatasetEpoch: resp.GetDatasetEpoch(),
		Texts:        texts,
	}, nil
}
