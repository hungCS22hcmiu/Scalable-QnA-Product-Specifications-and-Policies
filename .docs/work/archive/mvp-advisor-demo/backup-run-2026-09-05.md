# Backup run — captured 2026-09-05

**What this is:** a verbatim transcript of a clean, provably-cold run of all four demo steps,
captured immediately after `make demo-reset` reported `t1:0 t2:0`. It exists so the meeting can
proceed if Ollama or Redis dies, or if the room has no time for a live run.

**What it is not:** a screen recording. The transcript below is the *content*; a recording of
`make demo` running is still worth capturing on the day (one command, one take — see plan.md
Day 4 §2).

All numbers non-citable: `dev-v0`, demo θ/τ, `make dev` (functional run).

## Rehearsed Q&A — "what about τ = 0.86?"

Verified 2026-09-05, don't guess at it live. Restart with `REUSE_TAU=0.86 make dev`:

```
gateway: tau=0.860 theta=0.60 dim=768 index=idx:cache
cascade similarity=0.8689 overlap=0.40 reuse=false similarity_only=true entered_band=true
```

The trap still enters the band and the rule still refuses — **the demo survives τ = 0.86**. It
does not survive τ = 0.87 (0.8689 falls below the threshold, so a fixed rule refuses it too and
step 4 stops proving anything). Say that before being asked: τ is a demo setting, the real result
is the swept frontier.

## Transcript

```
$ make demo-reset
  corpus clean -- nothing to restore
  flushing both tiers and the corpus index (FLUSHALL)
cd rag && python3 -m rag.ingest
loaded 44 records from /Users/hung/Desktop/thesis/data/dev-v0
split into 44 chunks
indexed 44 docs, 44 chunks -> idx:corpus
  corpus:44  t1:0  t2:0
  OK -- cold cache, corpus indexed. Ready to rehearse the four steps.

$ make dev        # (banner)
    │  FUNCTIONAL RUN — latencies printed here are NOT citable.    │
    memory available: 41% (floor 25%; models need ~2.1 GB of 16 GB)
  2026/09/05 22:47:06 gateway: tau=0.850 theta=0.60 dim=768 index=idx:cache  (tau/theta are DEMO values, swept later)
  2026/09/05 22:47:06 gateway listening on :8080 (redis=localhost:6379 rag=localhost:50051)

$ make demo
  cold cache verified (t1:0 t2:0)  ·  tau=0.85 theta=0.60 — DEMO values, swept later
  latencies here are NOT citable (dev-v0, make dev)

── Step 1 · fresh question — the cost every uncached system pays
    Q: Am I entitled to a full refund on my headphones 30 days after delivery?
    MISS  ·  2951 ms  ·  similarity —  ·  source_overlap —

── Step 2 · exact repeat — Tier 1
    Q: Am I entitled to a full refund on my headphones 30 days after delivery?
    TIER1_HIT  ·  0 ms  ·  similarity —  ·  source_overlap —

── Step 3 · paraphrase — Tier 2, different words, same evidence
    Q: Is a full refund possible for my headphones 30 days after delivery?
    TIER2_HIT  ·  32 ms  ·  similarity 0.9750  ·  source_overlap 1.00

── Step 4 · the trap — high similarity, different evidence
    Q: Am I entitled to a full refund on my sofa 30 days after delivery?
    MISS  ·  1976 ms  ·  similarity 0.8689  ·  source_overlap 0.40

    The refusal is arithmetic, not a model score — check it by eye:

    cached entry grounded in (headphones):
      ✓ policy-returns-electronics#chunk-0
      ✓ policy-returns-furniture#chunk-0
        policy-warranty#chunk-0
        product-headphones-03#chunk-0
        product-headphones-04#chunk-0

    retrieved now (sofa):
      ✓ policy-returns-furniture#chunk-0
      ✓ policy-returns-electronics#chunk-0
        policy-shipping#chunk-0
        product-furniture-04#chunk-0
        product-furniture-08#chunk-0

    overlap = 2 shared / 5 entry sources = 0.40  <  theta 0.60   →  REFUSE, generate instead

── Counters
    requests 4  ·  hits 2  ·  hit rate 50%  ·  generations avoided 2


gateway cascade log (steps 3 and 4):
2026/09/05 22:47:19 gateway: cascade similarity=0.9750 overlap=1.00 reuse=true similarity_only=true entered_band=true
          retrieved=[policy-returns-electronics#chunk-0 policy-returns-furniture#chunk-0 policy-warranty#chunk-0 product-headphones-03#chunk-0 product-headphones-04#chunk-0]
          entry_sources=[policy-returns-electronics#chunk-0 policy-returns-furniture#chunk-0 policy-warranty#chunk-0 product-headphones-03#chunk-0 product-headphones-04#chunk-0]
--
2026/09/05 22:47:19 gateway: cascade similarity=0.8689 overlap=0.40 reuse=false similarity_only=true entered_band=true
          retrieved=[policy-returns-furniture#chunk-0 policy-returns-electronics#chunk-0 policy-shipping#chunk-0 product-furniture-04#chunk-0 product-furniture-08#chunk-0]
          entry_sources=[policy-returns-electronics#chunk-0 policy-returns-furniture#chunk-0 policy-warranty#chunk-0 product-headphones-03#chunk-0 product-headphones-04#chunk-0]
```
