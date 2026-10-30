# `gateway/internal/embed/` — the query embedding

**Describes:** commit `29b24a6` (30 Oct 2026). **Files:** `client.go` (103 lines), `doc.go`. Governing
contract: `interfaces.md` §F.

## 1. Purpose

It turns the incoming question into a 768-number vector, so Tier 2 can search for a similar cached question.
It runs on every Tier-1 miss, in parallel with retrieval. It serves **C1** (Tier 2) and bounds the Tier-2
μ_hit.

## 2. Boundaries

- It imports nothing from this repository.
- It embeds **queries only**. Document vectors are written by the Python ingest; the gateway never writes a
  corpus vector.
- It must mirror `rag/src/rag/embedding.py` exactly, or query vectors and corpus vectors are not comparable.

## 3. `client.go`

**Constants:**
- `Model = "nomic-embed-text"` and `Dim = 768`, both frozen. `Dim` is the only Go definition of the width;
  `cmd/gateway` passes it to `cache`, so the index width and the query width cannot drift apart.
- `queryPrefix = "search_query: "`. nomic-embed-text is trained with two prefixes, one for queries and one for
  documents (`search_document: `, used by the Python ingest). Leaving the prefix out raises **no error**: it
  just makes every similarity worse.

**`New(baseURL, model)`** builds a client with a **60 s timeout**, the same as `embedding.py`. The call sits on
the hit path, so a hang is a stall, not a slow success.

**`Query(ctx, text)`**:
1. Builds `{"model": …, "input": ["search_query: " + text]}` for Ollama's `/api/embed`. `input` is a list,
   and the reply field is `embeddings` (a list of lists). This is not the old `/api/embeddings` endpoint.
2. Returns an error on a non-200 status, a bad body, or an empty list.
3. **Checks the width.** Another Ollama model returns 384 or 1,024 numbers; nothing later would fail, and
   every Tier-2 lookup would just miss. So any width other than 768 is an error here.
4. Converts the numbers from float64 to **float32**, the type Redis stores (`interfaces.md` §D), in this one
   place.

## 4. Callers and callees

- **Built by** `cmd/gateway/main.go`: `embed.New(ollamaURL, embed.Model)`.
- **Called by** `httpapi`'s Tier-2 cascade, at the same time as `ragclient.Retrieve`. A failed embedding
  degrades the request to a miss; the write-back then writes Tier 1 only (no vector), which is why
  `entry:{entry_id}` exists (`Redis-Data Structure.md` §8).
- **Calls** Ollama over HTTP.

## 5. Tests that pin it

The package has **no test file**. `httpapi`'s tests use a fake embedder, and the live path is exercised by
`make seam-check` and the demo. The width check and the prefix are pinned only by code review.

## 6. Silent failures to watch

- **A missing or different prefix** on either side (here or in `embedding.py`) degrades every similarity with
  no error.
- **A different embedding model** with the same width (768) would pass the check and still make old and new
  vectors incomparable. The model is frozen; `make env-check` pins the LLM blob, not this one.
- **The embedding runner serves one slot.** Under heavy Tier-2 load, these calls queue inside Ollama, out of
  the gateway's sight; admission does not govern them (item 7.2).

## 7. Commit

`29b24a6`. The package last changed in `21aaaec` (the docs consolidation, comments only).
