# Evidence for ADR-019 — containment overlap within a product (θ)

Not a task trail: the measurement behind ADR-019, taken in chat on 2026-10-30.

- **What:** the containment overlap of product-scoped retrievals, `|retrieved(q) ∩ retrieved(e)| / |retrieved(e)|`,
  as `gateway/internal/reuse/rule.go` `Overlap` computes it. The entry's retrieval stands in for its recorded
  sources. Each query is retrieved with its own `product_id`, as `rag.server` does.
- **Pairs:** the `v1` validation split only (the test split is untouched):
  - each paraphrase with its cluster's seed, which should be reused;
  - each probe with its `pair_of`, split into B-within and B-cross, which should be refused.
- **Conditions:** `v1` in Redis (539 chunks), memory pressure 2 (yellow), embedding model only. **citable: no.**
- **Files:**
  - `fk_overlap_probe.py`: the probe;
  - `overlap-pairs.jsonl`: one line per pair, with IDs and numbers only and no question text;
  - `overlap-summary.txt`: the summary.
- **Re-run:** `python3 docs/work/2026-10-30-adr-019-theta-overlap/fk_overlap_probe.py <out.jsonl>`, from the repo
  root, with `v1` in Redis.
