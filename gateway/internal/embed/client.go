package embed

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// queryPrefix is mandatory and exact. nomic-embed-text is trained with asymmetric prefixes --
// "search_query: " for queries, "search_document: " for indexed text -- and omitting it does not
// error, it just quietly produces worse similarities (rag/src/rag/embedding.py). Since
// the corpus was indexed WITH the document prefix by the Python side, a query embedded without
// this prefix lands in a different region of the space and every Tier-2 lookup degrades with no
// signal that anything is wrong.
const queryPrefix = "search_query: "

// Dim is the ONLY Go-side definition of the frozen embedding width. cache/ receives it
// through main.go rather than importing embed/, so interfaces.md F's "dims must equal the Tier-2
// index DIM" holds by construction instead of by two constants agreeing.
const Dim = 768

// Model is frozen by the frozen embedding model alongside Dim; the two must move together or not at all.
const Model = "nomic-embed-text"

// Client calls Ollama's embedding endpoint. It deliberately mirrors rag/src/rag/embedding.py
// rather than re-deriving the contract: the two must agree exactly or query vectors and corpus
// vectors are not comparable.
//
// Only queries are embedded here. Documents are embedded by the Python ingest path, which owns
// the corpus index; the gateway never writes corpus vectors.
type Client struct {
	baseURL string
	model   string
	http    *http.Client
}

func New(baseURL, model string) *Client {
	return &Client{
		baseURL: baseURL,
		model:   model,
		// Matches embedding.py's 60s. This call sits on the hit path and bounds mu_hit
		// (interfaces.md F), so a hang here is a stall, not a slow success.
		http: &http.Client{Timeout: 60 * time.Second},
	}
}

// Query returns the embedding for a search query, with the nomic prefix applied.
func (c *Client) Query(ctx context.Context, text string) ([]float32, error) {
	// `input` is a LIST even for one string, and the response field is `embeddings` (plural,
	// list-of-lists). This is the /api/embed endpoint, not the legacy /api/embeddings which
	// takes `prompt` and returns a singular `embedding`.
	payload, err := json.Marshal(map[string]any{
		"model": c.model,
		"input": []string{queryPrefix + text},
	})
	if err != nil {
		return nil, fmt.Errorf("embed: marshalling request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/api/embed", bytes.NewReader(payload))
	if err != nil {
		return nil, fmt.Errorf("embed: building request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("embed: calling ollama: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("embed: ollama returned %s", resp.Status)
	}

	var out struct {
		Embeddings [][]float64 `json:"embeddings"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, fmt.Errorf("embed: decoding response: %w", err)
	}
	if len(out.Embeddings) == 0 {
		return nil, fmt.Errorf("embed: ollama returned no embeddings")
	}

	// Pulling a different Ollama embed model returns 384 or 1024 dims. Nothing downstream would
	// error -- the write would be rejected by the index and every Tier-2 lookup would simply
	// miss forever. Fail loudly here instead.
	if got := len(out.Embeddings[0]); got != Dim {
		return nil, fmt.Errorf("embed: model %q returned %d dims, expected %d", c.model, got, Dim)
	}

	// Redis stores FLOAT32 (interfaces.md D). Narrowing here rather than at the Redis boundary
	// keeps the conversion in one place, next to the reason for it.
	vec := make([]float32, len(out.Embeddings[0]))
	for i, v := range out.Embeddings[0] {
		vec[i] = float32(v)
	}
	return vec, nil
}
