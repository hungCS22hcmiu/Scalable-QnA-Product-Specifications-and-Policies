// Package catalog is a read-only view of the ingested corpus, and it exists for ONE reason:
// the demo UI needs a product list to render (docs/defense_demo.md §3).
//
// ⚠️ Nothing here is on a measured path. It is never called by POST /ask, it holds no cache, and
// it makes no reuse decision. If that ever stops being true, this package is in the wrong place:
// the corpus index belongs to the Python service (rag/src/rag/store.py owns its schema), and this
// is a deliberate read across that boundary, justified only by being demo-only and read-only.
//
// It is NOT in cache/ on purpose. cache/ owns the answer cache -- idx:cache, t1:, t2: -- and
// mixing a corpus reader into it would make "which index does this touch?" a question you have to
// read the function body to answer (docs/design/architecture.md §2).
package catalog

import (
	"context"
	"sort"

	"github.com/redis/go-redis/v9"
)

// corpusIndex and the kind tag mirror rag/src/rag/store.py's build_schema(). They are duplicated
// rather than shared because the two services have no common config; if the Python schema changes
// its index name or drops the `kind` tag, this returns an empty list rather than an error, so the
// UI shows an empty catalogue and the cause is not obvious. The startup check in main.go exists to
// surface that at boot instead.
const (
	corpusIndex = "idx:corpus"
	kindProduct = "product"
)

// maxProducts bounds the scan. The frozen corpus is ~150 documents (data-card.md §1) and each may
// yield several chunks, so this is generous headroom rather than a paging strategy -- a demo UI
// listing more than this would be unusable anyway.
const maxProducts = 2000

// Catalog reads product documents out of the corpus index.
type Catalog struct {
	rdb *redis.Client
}

func New(rdb *redis.Client) *Catalog {
	return &Catalog{rdb: rdb}
}

// Product is one corpus document, not one chunk. The distinction matters: a document is chunked
// into several vectors and each carries the same doc_id, so the search below returns one row per
// CHUNK and this collapses them.
type Product struct {
	DocID    string `json:"doc_id"`
	Title    string `json:"title"`
	Category string `json:"category"`
}

// Products lists every product document in the corpus, sorted by category then title so the UI
// renders in a stable order across reloads.
func (c *Catalog) Products(ctx context.Context) ([]Product, error) {
	res, err := c.rdb.FTSearchWithArgs(ctx, corpusIndex, "@kind:{"+kindProduct+"}",
		&redis.FTSearchOptions{
			DialectVersion: 2,
			LimitOffset:    0,
			Limit:          maxProducts,
			// Deliberately NOT returning `text` or `vector`: text is the full chunk body and the
			// vector is a multi-kilobyte blob, neither of which a product list renders.
			Return: []redis.FTSearchReturn{
				{FieldName: "doc_id"},
				{FieldName: "title"},
				{FieldName: "category"},
			},
		}).Result()
	if err != nil {
		return nil, err
	}

	seen := make(map[string]Product, len(res.Docs))
	for _, d := range res.Docs {
		docID := d.Fields["doc_id"]
		if docID == "" {
			continue
		}
		// First chunk wins. Every chunk of a document carries identical doc_id/title/category
		// metadata (rag/src/rag/ingest.py), so this is a de-duplication rather than a choice.
		if _, ok := seen[docID]; !ok {
			seen[docID] = Product{
				DocID:    docID,
				Title:    d.Fields["title"],
				Category: d.Fields["category"],
			}
		}
	}

	out := make([]Product, 0, len(seen))
	for _, p := range seen {
		out = append(out, p)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Category != out[j].Category {
			return out[i].Category < out[j].Category
		}
		return out[i].Title < out[j].Title
	})
	return out, nil
}
