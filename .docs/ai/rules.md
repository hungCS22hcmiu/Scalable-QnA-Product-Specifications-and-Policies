# Rules AI trips over in this repo

Ten trip-wires, derived from this repo's actual failure modes — not generic engineering advice. Each
rule is short **on purpose** and cites the governing section rather than restating it. **Read the cited
section before acting; this file is the trigger, `docs/` is the authority.**

Review subagents Read this file at review time. When a governing doc changes, only the citation here
may need updating — never the content.

---

### 1. Never change a frozen value
`num_ctx` · `OLLAMA_NUM_PARALLEL` · embedding model + `DIM` · `top_k` · chunking config · FLAT index ·
cache capacity · the two-region eviction policy · dataset snapshot.
→ `interfaces.md` "Frozen study-wide" · `experiment-protocol.md` §1 · `decisions.md` ADR-002/003/005/014/017

**Why it bites:** no error, no bug. It silently invalidates every measurement taken before the change,
and you find out in W20 when the numbers won't reconcile. A change requires a **new ADR** and an explicit
statement of which prior runs are void.

### 2. Never reinstate dropped scope
Learned predictor · predictor-gated invalidation · GPTCache/vCache *integration* · semantic routing ·
SSE streaming · evaluated bypass classifier · mid-study HNSW.
→ `Final_Proposal.md` §12 "Already dropped, do not reinstate" · §14 · ADR-016/018

If a task appears to need one of these, **flag it — do not build it.**

### 3. `experiments/results/*/raw/` is write-once
Never edit, never re-run in place, never regenerate. Figures are produced *from* raw by script.
→ `experiment-protocol.md` §3

### 4. The proto is generated
Edit `contracts/rag/v1/rag.proto`, then `make proto`. Never hand-edit generated stubs on either side;
never let the Go and Python shapes diverge.
→ `interfaces.md` §B

### 5. Two Redis eviction regions
Cache entries under LRU; dependency state (`dep:*`, `entry:*`) under **`noeviction`**. An evicted
dependency record makes its entries permanently unpurgeable and breaks C2's completeness **silently**.
→ `interfaces.md` §D · ADR-005

### 6. Provenance fields are load-bearing
`source_chunk_ids` (C1 overlap + C2 dependency map) · `t1_key` (makes Tier-1 purgeable) ·
`dataset_epoch` (guards the write-back race). Renaming or dropping any one breaks a contribution with
**no error at all**.
→ `interfaces.md` §A, §D, §E

### 7. No ML runtime on the hit path
No torch, no sentence-transformers, no in-process model. Embeddings come from the Ollama endpoint. The
reuse decision is set intersection over chunk-ID strings, in Go.
→ `Final_Proposal.md` §7 · ADR-017

**Why it bites:** ~2 GB resident for a ~400 MB model, in a 16 GB envelope where that is roughly one
concurrent generation slot.

### 8. Read the governing doc before editing at a seam
Wire shapes → `interfaces.md`. Metrics and counting rules → `experiment-protocol.md`. Corpus →
`data-card.md`. Structure → `docs/design/architecture.md`. Guessing at a seam is how silent drift starts.

### 9. No new dependency without sign-off
Every resident megabyte competes with KV cache. **The memory envelope is the thesis.**
→ `Final_Proposal.md` §3, §7 · ADR-017

### 10. Never tune to make a headline work
The null result is **pre-registered** and reportable. Do not adjust thresholds, filter the workload,
drop an inconvenient stratum, or re-run until a figure looks better.
→ `Final_Proposal.md` §5 C1 "Fallback, pre-registered" · `experiment-protocol.md` §6

This is the research-integrity analogue of immutable tests: a measurement is evidence, not a target. If
a result looks wrong, the honest paths are (a) find a defect in the *instrument* and document it, or
(b) report the result. There is no third path.
