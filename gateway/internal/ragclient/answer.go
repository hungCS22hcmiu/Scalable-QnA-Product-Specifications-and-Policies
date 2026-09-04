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
func (c *Client) Answer(ctx context.Context, query string, topK uint32) (*AnswerResult, error) {
	stream, err := c.rpc.Answer(ctx, &ragpb.AnswerRequest{
		Query: query,
		TopK:  topK,
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
