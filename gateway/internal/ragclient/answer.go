package ragclient

import (
	"context"
	"errors"
	"io"

	"github.com/hung/thesis/gateway/internal/ragpb"
)

// AnswerResult is the terminal AnswerChunk's payload, accumulated from the stream.
type AnswerResult struct {
	Text           string
	SourceChunkIDs []string
	ModelUsed      string
	DatasetEpoch   uint64
}

// Answer calls the full miss path: retrieve + generate. Loops Recv() until io.EOF, keeping
// the chunk with Done == true as the result -- defensive against the interface allowing
// multiple chunks, even though this week's server sends exactly one (stream=false path only,
// SSE dropped by ADR-016).
// retrievedChunkIDs, when non-empty, tells the service to ground generation on exactly these
// chunks instead of retrieving again (ADR-033, interfaces.md B v0.7). The caller has already
// retrieved for this query -- concurrently with its embedding -- so passing them turns a banded
// miss's two retrievals into one, and the one it removes is the one that re-embeds the query.
//
// Pass nil to let the service retrieve for itself; that path is unchanged.
//
// productID is optional (ADR-034, interfaces.md B v0.8): scopes the service's OWN fallback
// retrieval (used when retrievedChunkIDs is empty) the same way Retrieve's does. Has no effect
// when retrievedChunkIDs is non-empty, since the service does not search in that case at all.
func (c *Client) Answer(ctx context.Context, query string, topK uint32, retrievedChunkIDs []string, productID string) (*AnswerResult, error) {
	stream, err := c.rpc.Answer(ctx, &ragpb.AnswerRequest{
		Query:             query,
		TopK:              topK,
		RetrievedChunkIds: retrievedChunkIDs,
		ProductId:         productID,
	})
	if err != nil {
		return nil, err
	}

	var result *AnswerResult
	for {
		chunk, err := stream.Recv()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		if chunk.GetDone() {
			result = &AnswerResult{
				Text:           chunk.GetText(),
				SourceChunkIDs: chunk.GetSourceChunkIds(),
				ModelUsed:      chunk.GetModelUsed(),
				DatasetEpoch:   chunk.GetDatasetEpoch(),
			}
		}
	}
	if result == nil {
		return nil, errors.New("ragclient: Answer stream ended without a terminal chunk")
	}
	return result, nil
}
