# Tier 2 — the semantic cache, from the idea to the mechanism

**For:** a reader who is new to this project · **Describes:** the code at commit `d642c45` (1 Nov 2026).
Part 2 was checked against `ff1c6ff` on 30 Oct 2026. Since then only retrieval has changed (ADR-020 and
ADR-021, Step 1). The worked examples were re-run on 7 Nov 2026.
**About the numbers:**
- **The worked examples §9, §10, §11a and §11b are live runs on `v1`** (7 Nov 2026, cold cache, `make dev`).
  It was a functional run under yellow memory pressure, so the latencies are not measurements and
  **none of it is citable**. The raw output is in `docs/work/2026-11-07-tier2-doc-examples/`.
- **`dev-v0` numbers remain** in §3, in §10's unit-test case and in Example C (§11). `dev-v0` is the
  small development corpus (44 documents: 4 store policies and 40 products), retired on 29 Oct 2026.
  These numbers show how the mechanism behaves, and they are **not** results of the thesis.
- **Some numbers come from `v1`**, the final corpus (frozen on 23 Oct 2026): the lane counts in Step 3
  (ADR-015 and ADR-016), the overlap measurement in §8 (ADR-019) and the trap measurements in §12a. They come
  from the validation split, and they are **not citable** either.
- **The thesis results are measured in Phase 6**, on the held-out test split.

**Contents.** Part 1, the idea (§1–4) · Part 2, the mechanism (§5–8) · Part 3, five worked
examples (§9–11b) · Part 4, measuring, traps and limits (§12–13) · Code map and further reading (§14)

---

# Part 1 — The idea

## 1. The problem Tier 2 solves

This project is a question-answering assistant for an online shop. It answers questions about
**product specifications** ("How much does the SoundMax ANC Pro weigh?") and **store policies**
("Can I return headphones after 30 days?").

It runs on **one laptop**: a MacBook M1 with 16 GB of memory. The answers come from a small language
model (Qwen 3.5 2B) that runs locally and writes **one answer at a time**. Writing one answer takes
seconds (1.3 to 8.1 seconds in the runs of Part 3). Reading a stored answer from a cache takes
milliseconds.

So every question the cache answers **safely** is a question the model does not have to answer. This
is how the system serves more users on the same machine: it turns slow generation work into fast
memory lookups.

The cache has two tiers:

- **Tier 1 — same words.** It matches a question that was already asked with the same text (after
  lower-casing and removing punctuation), about the same product. One hash lookup, under a millisecond.
- **Tier 2 — same meaning.** It matches a question that was asked before **in other words**.
  "Am I entitled to a full refund on my headphones 30 days after delivery?" and "Is a full refund
  possible for my headphones 30 days after delivery?" use different words and need the same answer.

Tier 1 is simple, and its safety is checked on the corpus before any run. Tier 2 is where the hard
part is. This document is about Tier 2.

## 2. What a semantic cache is

A semantic cache compares **meanings**, not strings. To do that it uses an **embedding**: a model
turns a sentence into a list of numbers, here 768 numbers from the model `nomic-embed-text`.
Sentences with similar meanings get lists of numbers that point in a similar direction.

How close two such lists are is measured by **cosine similarity**. It is a number up to 1.0, and 1.0
means "the same direction". In the examples below, paraphrases of a question score between 0.91 and
0.99.

A basic semantic cache works in three steps:

1. When it answers a question, it stores the question's vector together with the answer.
2. For a new question, it finds the stored question with the highest similarity.
3. If that similarity is at least a threshold **τ** ("tau"), it serves the stored answer.

```
new question ──embed──►  [0.012, -0.044, …, 0.031]      (768 numbers)
                                  │
                                  │  find the nearest stored vector
                                  ▼
stored: "Can I get a full refund on these headphones …"
        similarity 0.9932  ≥  τ = 0.85   →   serve the stored answer?
```

## 3. Why similarity alone is not safe

The danger is a **false hit**: the cache serves a stored answer to a question that needs a different
answer. The user gets a wrong answer, quickly, and nothing in the system notices.

Similarity measures how two questions are **worded**. It does not measure what **evidence** each
question needs. Two examples from this project show the gap:

- **Return or warranty.** On 6 Sep 2026 a cached answer about returning the EarBuds Pop 3 was compared
  with two new questions about the same product. A paraphrase of the return question scored
  **0.9382**. A question about the warranty scored **0.9208**. Both are above τ = 0.85. The first may
  reuse the answer. The second must not: headphones can be returned within 30 days, but their
  warranty is 1 year.
- **Headphones or sofa.** "Am I entitled to a full refund on my headphones 30 days after delivery?"
  and the same sentence with "sofa" differ in one word, so a cache that compares wording sees two
  near-identical questions. The answers differ: electronics may be returned within 30 days,
  furniture within 14 days and with a 15 % restocking fee.

Moving τ does not fix this. A lower τ catches more paraphrases and lets in more false hits. A higher τ
does the reverse. On 17 labelled test questions in this corpus, the most similar **wrong** match
scored 0.9685, and only one of the seven **right** matches scored higher (0.9899). A τ high enough to
refuse every wrong match would also refuse six of the seven right ones.

## 4. This project's idea: ask the retriever first

The assistant is a **RAG** system (retrieval-augmented generation). Before the model writes an
answer, a **retriever** searches the shop's documents and returns the five most relevant pieces,
called **chunks**. The model then writes its answer from those chunks.

Every chunk has a stable ID that names its document, for example
`policy-return-electronics#chunk-0` or `product-electronics-b07zj7qg33#chunk-1`. Every document ID starts
with `policy-` or `product-`, so the ID alone says what kind of document a chunk comes from.

**The retrieval tells us which evidence a question needs, whatever its wording.** The return question
retrieves the return policy. The warranty question retrieves the warranty policy. Tier 2 uses the
retrieval of the new question twice:

1. **To choose where to look.** The cache is split into groups called **namespaces**. A question may
   only reuse an answer from its own namespace. For a policy question, the namespace is built from
   what retrieval returned: the warranty question looks among warranty answers, so it never sees the
   return answer. For a product question that carries a `product_id`, the namespace is that product,
   taken from the request and not from retrieval (Step 4, Example D).
2. **To check the old answer.** Before an answer is served, a **support gate** checks that the cached
   answer's words and numbers appear in the evidence retrieved **now**, for the new question.

Both checks are plain rules written in Go: string comparisons, set counts and a word count. **No
model runs to make the decision**, so the decision is the same every time, and it takes about 30
microseconds in a benchmark.

**What is new here, and what is borrowed.**
- **Borrowed.** Using retrieval evidence to decide reuse is not new: two systems published in 2026,
  GroundedCache and FinCacheServe, also do it. The support gate is taken from GroundedCache, with its
  published threshold of 0.6.
- **Measured and set aside.** GroundedCache also compares the two chunk lists directly. This project
  measured that check on `v1` and does not use it, because inside one product it cannot tell a safe
  paraphrase from a trap (§8, ADR-019).
- **What it adds.** The **namespace** split, and a way of measuring. The thesis asks a narrow question: does
  this design allow more safe reuse than the best similarity-only threshold, at a fixed budget of false hits
  (provisionally at most 5 %)?

**The served rule, in one line:** similarity ≥ τ **and** the same namespace **and** the support gate
passes.

---

# Part 2 — The mechanism

## 5. Where Tier 2 sits in a request

The system has three parts. The **gateway**, written in Go, receives every question and runs both
cache tiers. The **RAG service**, written in Python, does the retrieval and calls the model. **Redis**
stores both tiers and the vector index. The gateway and the RAG service talk over gRPC.

```mermaid
flowchart LR
    Q["POST /ask<br/>question, optional product_id"] --> T1{"Tier 1<br/>same words, same product?"}
    T1 -- yes --> A1(["answer from Tier 1<br/>under 1 ms"])
    T1 -- no --> T2{"Tier 2<br/>same meaning, same namespace,<br/>answer supported?"}
    T2 -- yes --> A2(["answer from Tier 2<br/>under 100 ms"])
    T2 -- no --> G["generate with the model<br/>1 to 8 s"]
    G --> W["store the answer<br/>in Tier 1 and Tier 2"]
    W --> A3(["answer from the model"])

    classDef hit fill:#d1fae5,stroke:#047857,color:#064e3b
    classDef slow fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    class A1,A2 hit
    class G slow
```

The times are from the run of Part 3 (7 Nov 2026, not measurements): a Tier-1 hit took 1 ms, a Tier-2
hit 69 to 86 ms, and a generation 1.3 to 8.1 seconds. (If the model is busy and too many questions are waiting, the
gateway answers `503 busy, retry` instead of queueing without limit. That is a separate part of the
system and is not covered here.)

## 6. Tier 2 step by step

This is what happens after Tier 1 misses. The steps are numbered as in the text below.

```mermaid
flowchart TD
    S1["1. Embed the question and retrieve 5 chunks, at the same time"] --> S2{"2. Anything to judge?<br/>vector, retrieval, at least one chunk"}
    S2 -- no --> M0(["MISS, nothing judged"])
    S2 -- yes --> S3["3. Lane from the chunk IDs:<br/>SPEC or POLICY"]
    S3 --> S4["4. Namespace from the lane:<br/>a product or a policy document"]
    S4 --> S5{"5. Nearest entry inside<br/>that namespace?"}
    S5 -- none --> M1(["MISS, nothing judged"])
    S5 -- found --> S6{"6. Judge: namespace equal<br/>and similarity ≥ τ?"}
    S6 -- no --> M2(["MISS, cause SIMILARITY<br/>or NAMESPACE"])
    S6 -- yes --> S7{"7. Support gate:<br/>words and numbers in the new evidence?"}
    S7 -- no --> M3(["MISS, cause SUPPORT"])
    S7 -- yes --> H(["8. TIER2_HIT, cause NONE"])
    M0 & M1 & M2 & M3 --> GEN["8. Generate, then store a new entry"]

    classDef hit fill:#d1fae5,stroke:#047857,color:#064e3b
    classDef miss fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    class H hit
    class M0,M1,M2,M3 miss
```

### Step 1 — Embed and retrieve, at the same time

The gateway needs two things about the new question: its **vector**, for the similarity, and its
**retrieval**, for the namespace and the gate. Neither depends on the other, so the gateway asks for
both at once:

- **The vector**, from the embedding model. The text is sent as `search_query: <question>`. The model
  was trained with this prefix (the documents were stored with `search_document: `), and without it
  every similarity would be quietly worse.
- **The top five chunks**, from the RAG service, each with its ID and its text. If the request names
  the product the user is looking at (`product_id`), the retriever changes the top five in three ways
  (`rag/src/rag/retrieve.py`):
  - **Other products' chunks are dropped.** When no policy chunk ranked, their places are filled with
    this product's own best chunks (ADR-021).
  - **This product's own chunk is always included.** If it did not rank, it is put at the top of the
    list. If the list is already full, the last chunk falls off.
  - **A policy chunk of another category is swapped** for the best unused policy chunk of this product's
    category (ADR-020). The number of policy chunks stays the same, so the lane cannot move.

  So it may return fewer than five. Examples A, B, D and E (Part 3) show each case.

This step costs the **slower** of the two calls, not their sum. If either call fails, Tier 2 is skipped
and the request continues as a normal miss. A Tier-2 problem costs speed. It never becomes an error
for the user.

### Step 2 — Stop when there is nothing to judge

Three cases end Tier 2 at once, as a plain MISS with no candidate judged:

- the embedding failed (no vector),
- the retrieval failed,
- the retrieval returned **zero chunks**.

The third case matters most. An answer may only be reused when there is evidence behind the
decision. With zero chunks there is none, so nothing is reused.

### Step 3 — Read the lane from the chunk IDs

A **lane** is the kind of question: about a product (SPEC) or about a policy (POLICY). The lane is
read from one number, the **policy fraction**: the share of retrieved chunks whose ID starts with
`policy-`.

The rule is: a fraction of 0 is SPEC, a fraction of at least 0.20 is POLICY. With at most five chunks,
that means **no policy chunk → SPEC, at least one policy chunk → POLICY**. In a check on the
development corpus (6 Sep 2026) this separated the two kinds completely: ten spec questions all had
fraction 0.00, and ten policy questions all had 0.40 to 0.80. That corpus had 4 policy chunks; `v1` has 48.
The same count on the `v1` validation split (ADR-015) reads 428 of 431 product-only questions as SPEC,
so the split holds for them. It does not hold for mixed questions (stratum D): of 33, 27 are read as
POLICY, 6 as SPEC and none as MIXED, because the band is closed.

**Why read it from the retrieval, and not from the question?** A classifier that reads the question
can be wrong, and its mistakes would look like mistakes of the reuse rule. Counting the prefixes of
what retrieval actually returned cannot be wrong about what was retrieved.

There is also a third lane, **MIXED**, for questions that need both a product and a policy ("How long
is the warranty on the EarBuds Pop 3, and what is its battery life?").
- **ADR-016 (27 Oct 2026)** pins it as **one band, [0.20, 0.60)**, run as an **on/off arm** and never
  swept. Any other band stops the gateway at start.
- **Off is the default:** `LANE_SIGMA` = `LANE_SIGMA_HI` = 0.20, an empty band. The counts above are the
  off arm.
- **`make dev` turns it on for demos** (since 7 Nov 2026). With no `RUN_ID` and neither variable set, it
  starts the gateway with `LANE_SIGMA_HI=0.60`. A measured run, which has a `RUN_ID`, keeps the
  gateway's default: off.
- **On** (`LANE_SIGMA_HI=0.60`), the `v1` validation split reads 12 of its 33 stratum-D questions as MIXED.
  Example E (§11b) shows both arms live.

Every log record names the arm in the field `mixed_lane`. `v1` has 69 stratum-D questions in all.

### Step 4 — Build the namespace

The namespace is the group of the cache that this question may reuse from. It depends on the lane:

| Lane | When | Namespace | Example from the corpus |
| :--- | :--- | :--- | :--- |
| SPEC | no policy chunk retrieved | the product the user is looking at (`product_id`); if none, the document of the **top-ranked** product chunk | "Which graphics card does this laptop have?" on a laptop's page → `product-laptops-b07qvm5x8w` (Example D) |
| POLICY | at least one policy chunk | the document of the **top-ranked** policy chunk | "How long is the warranty on these headphones?" → `policy-warranty-electronics` (Example B) |
| MIXED (on arm only) | both kinds, inside a set band | the pair `{product}\|{policy}`; both halves are required | `product-electronics-b07zj7qg33\|policy-warranty-electronics` (Example E) |

Four details make this work:

- **A namespace is a document, not a chunk.** `policy-return-electronics#chunk-2` belongs to
  `policy-return-electronics`.
- **The top rank decides, not the list of documents.** The return and the warranty questions of
  Example B both retrieve **both** electronics policies. But the retriever ranks the return policy
  first for one and the warranty first for the other. The rank separates them. The list alone would
  not.
- **The product the user is viewing beats the top-ranked product.** Asked with no `product_id`,
  Example D's graphics-card question ranks three other laptops above the one the user is looking at.
  Paraphrases can rank similar products in a different order. The page the user is on does not change.
- **An empty namespace matches nothing.** It is never treated as "match everything".

**Why are policy answers not split by product?** A policy answer is the same for every product the
policy covers. One entry per policy uses less cache space than one entry per product. The cost is shown
in Example B (e): an answer that names one product's brand can reach another product.

### Step 5 — Search inside the namespace only

The gateway sends **one** query to Redis: "the nearest stored question whose namespace is this one".
It asks for one result only (`k = 1`), because inside one namespace the most similar entry is the best
candidate.

```
FT.SEARCH idx:cache "(@namespace:{policy\-return\-electronics})=>[KNN 1 @embedding $vec AS dist]"
```

- The vector index is **exact** (`FLAT`), not approximate. An approximate index could return a
  different neighbour from one run to the next, and that noise would mix with the effect being
  measured. The choice is frozen for the whole study.
- Redis returns the cosine **distance**. The gateway converts it: similarity = 1 − distance.
- If the namespace holds no entry yet, Tier 2 ends as a MISS with nothing judged. This is the normal
  case on a cold cache.

**Why not search the whole cache and filter afterwards?** The nearest few entries overall can all
belong to other namespaces. A good entry in the right namespace would then sit just below the cut and
never be seen, and this gets worse as the cache fills. Searching inside the namespace has no such
limit.

### Step 6 — Judge, in a fixed order, and give one reason

The candidate goes through the checks in a fixed order. The first check that fails gives the
**refusal cause**, and every judged candidate gets exactly one cause in the log:

| Order | Check | Cause if it fails |
| :---: | :--- | :--- |
| 1 | The candidate's namespace equals the question's (for MIXED, the candidate must be MIXED too) | `NAMESPACE` |
| 2 | Similarity ≥ τ (0.85, a demo value) | `SIMILARITY` |
| 3 | The RAG service sent the chunk texts, so the gate can run | `NOT_SCORED` |
| 4 | The support gate passes (Step 7) | `SUPPORT` |
| — | Every check passed: the answer is served | `NONE` |

- **With the gate switched off** (§12), checks 3 and 4 are skipped: a candidate that passes checks 1
  and 2 is served.
- **`NAMESPACE` should never happen**, because the search already filtered by namespace. The check is
  repeated in Go on purpose. If Redis and Go ever disagreed, Go refuses, and the cause shows it.
- **`NOT_SCORED`** means an old version of the RAG service sent chunk IDs without their text. The gate
  cannot check anything, so the answer is not served, and a measured run with any such record is
  invalid.
- **One rule decides serving: the cause is `NONE`.** A request where nothing was judged (Steps 2
  and 5) has no cause at all, which is different from a refusal.
- **τ is not set by hand for results.** It is swept over a range, chosen on a validation set and
  reported on a separate test set. 0.85 is the value the demo uses.

### Step 7 — The support gate

The gate asks one question: **is the cached answer supported by the evidence retrieved for this new
question?** It reads the cached answer and the new chunks. It **never reads either question**. It has
two arms, and both must pass.

**The lexical arm** counts words:

```
S_lex  =  (content words of the cached answer that also appear in the new evidence)
          ─────────────────────────────────────────────────────────────────────────
                          (content words of the cached answer)
```

- **Content words:** lower-case, split on anything that is not a letter or a digit, remove 33 common
  words ("the", "of", "with", …, the standard Lucene list), remove words shorter than three
  characters, and count each word once. There is no stemming, so "return" and "returns" are different
  words.
- **Evidence:** every word of the retrieved chunks.
- **Pass when `S_lex ≥ τ_s = 0.6`.** This value is GroundedCache's published threshold. It is fixed
  and never tuned.

**The numeric arm** checks numbers:

- Every number in the cached answer, with its unit, must appear in **one** retrieved chunk. The number
  and its unit must be in the same chunk, never one in each.
- It reads common forms: "30-day", "30 days" and "thirty days" all become *30 day*; "250g" becomes
  *250 g*; "$49.99" becomes *49.99 $*; "IPX4" is read as a code.
- A number with no unit is checked by its value only.
- A number it cannot read ("½", "1,5 days", "5.3.1") **blocks reuse**. When unsure, it refuses.

**Why two arms?** Words catch the wrong **topic**. Numbers catch the wrong **fact**. An answer that
says "40 hours" where the evidence says "30 hours" shares almost all its words with the evidence
(Example C, §11).

The gate costs about 30 microseconds for both arms in a benchmark on the M1. That is an estimated
0.2 % of a Tier-2 hit.

### Step 8 — Serve, or fall through to generation

**When the cause is `NONE`,** the stored answer is returned with `cache: TIER2_HIT`. Two small writes
then run in the background, so they never slow the answer: the entry's hit counter goes up by one, and
a **Tier-1 copy** is written for the exact words of this question. The next identical question then
stops at Tier 1 and skips the embedding and the search. The copy is written **only while the Tier-2 entry
still exists**, and its key is recorded with the entry (item 4.3). So a later eviction or purge removes
it too.

**Otherwise** the request continues as a normal miss. The model writes a new answer **from the chunks
already retrieved in Step 1**, so the system never retrieves twice. The new answer is stored in both
tiers under one entry ID. Its lane and namespace are computed from **the chunks its own answer was
built from**. A refused candidate is not deleted. The new entry is stored beside it.

## 7. What one Tier-2 entry holds

Each entry is one Redis hash. This is the entry that the first question of Example A (§9) creates.
`<entry_id>` and `<sha256>` stand for long generated IDs.

```
t2:<entry_id>                                     a Redis hash, indexed by idx:cache
├── embedding          768 × float32              the vector of the question that caused the miss
├── query_text         "Can I get a full refund on these headphones 30 days after delivery?"
├── answer             "Yes, you can get a full refund …"   the answer the model wrote
├── source_chunk_ids   product-electronics-b07zj7qg33#chunk-1
│                      policy-return-electronics#chunk-0
│                      policy-return-electronics#chunk-1
│                      policy-return-electronics#chunk-2
│                      policy-warranty-electronics#chunk-2   (the evidence behind the answer)
├── lane               POLICY                     4 of 5 chunks are policy chunks
├── namespace          policy-return-electronics  the top-ranked policy document
├── t1_key             t1:<sha256>                the Tier-1 copy written by the same miss
├── dataset_epoch      2                          corpus version: the epoch file's value, ≥ 1 (item 4.2)
└── hit_count, created_at, source_overlap
```

In the index, `namespace` and `lane` are **tags**: they are compared for exact equality and never
split into words. `embedding` is the vector field (exact `FLAT` index, cosine, 768 dimensions).

The link to the Tier-1 copy (`t1_key`) exists because the Tier-1 key is a hash of the question text and
the `product_id` (ADR-018), and it cannot be computed back from the entry. Without the link, removing an entry would leave its
Tier-1 copy still serving the old answer.

## 8. The overlap score: computed, but it does not decide

The project's proposal planned a third check that compares the chunk lists directly. It is called
**containment**:

```
containment  =  |chunks retrieved now  ∩  chunks behind the cached answer|
                ─────────────────────────────────────────────────────────
                           |chunks behind the cached answer|
```

The rule would reuse when containment ≥ θ ("theta"; the demo value is 0.60).

The code **computes containment for every candidate that clears τ and logs it**, as `source_overlap` in
the evaluation log. It does **not** use it to decide, and θ is **not swept**. ADR-019 (30 Oct 2026)
records this decision. It settles what the plan called finding F-K.

**The reason.** When a request carries a `product_id`, retrieval is limited to that product. A product
has about 3.2 chunks in `v1` (491 product chunks over 152 products), and the retriever returns up to
five. So two questions about the same product mostly retrieve the same chunks, and their containment is
close to 1 whatever they ask. (A long product, with more than five chunks, is an exception. The laptop
in Example D has three, so every question about it retrieves all three.)

**The measurement** (`v1` validation split, 416 pairs, not citable;
`docs/work/2026-10-30-adr-019-theta-overlap/`). Each question was retrieved with its own `product_id`,
and the containment was computed as `rule.go` computes it:

| Pairs | n | mean containment | = 1.0 | ≥ 0.6 |
| :--- | ---: | ---: | ---: | ---: |
| a paraphrase and its seed question (**should** reuse) | 281 | 0.876 | 75 % | 86 % |
| a B-within trap and its pair, same product (should **not** reuse) | 124 | 0.784 | 47 % | 85 % |
| a B-cross trap and its pair, different product (should **not** reuse) | 11 | 0.000 | 0 % | 0 % |

**No θ separates the first two rows.** At θ = 0.6, containment would reuse 86 % of the paraphrases and
85 % of the same-product traps. At θ = 1.0, it would reuse 75 % and 47 %. The third row is already
separated by the namespace, because the two questions are about different products. Example D (§11a)
shows the same thing live: a GPU paraphrase and a RAM question about one laptop both have containment
1.00, and only one of them may reuse the GPU answer. With five chunks, the score can also only take six
values (0, 0.2, …, 1.0).

**What this means for the thesis.** On traps across products, the namespace does the work. On traps
inside one product, only the support gate can refuse. The claim is restated around this served rule
(ADR-019). Logging the containment on every candidate still matters: it is the evidence for the
decision, and the write-up reports its distribution.

---

# Part 3 — Worked examples

Examples A, B and D come from one live run, and Example E from a second run the same day. Example C and
the unit-test case in §10 are older and use `dev-v0`.

**Setting of the live run.** 7 Nov 2026, corpus `v1`, code at `d642c45`, gate on, τ = 0.85, MIXED off.
The cache was emptied first (`make cache-reset`), then `make dev` was started, and the questions were
sent in the order of this part. **Every request carried a `product_id`**, as the `v1` workload does.
Memory pressure was yellow, so the latencies are not measurements. The questions are written for this
document. Four products are used:

| Short name | `product_id` | What it is |
| :--- | :--- | :--- |
| H1 | `product-electronics-b07zj7qg33` | headphones (Anker Soundcore) |
| H2 | `product-electronics-b079jfb616` | headphones (Mpow) |
| Sofa | `product-furniture-b019x98zxm` | a recliner sofa chair |
| Laptop | `product-laptops-b07qvm5x8w` | a gaming laptop, 3 chunks |

The raw log, the answers and the scripts are in `docs/work/2026-11-07-tier2-doc-examples/`.

## 9. Example A — a policy question, end to end

**Question 1:** "Can I get a full refund on these headphones 30 days after delivery?" (H1)

1. Tier 1 misses: nothing is stored yet.
2. Retrieval. The `product_id` changes the top five (Step 1):

   ```
   without product_id                        with product_id = H1 (what the gateway got)
     1. policy-return-electronics#chunk-0      1. product-electronics-b07zj7qg33#chunk-1  ◄ H1's own chunk, put first
     2. policy-return-electronics#chunk-1      2. policy-return-electronics#chunk-0
     3. policy-return-electronics#chunk-2      3. policy-return-electronics#chunk-1
     4. policy-return-laptops-new#chunk-0      4. policy-return-electronics#chunk-2
     5. policy-return-phones-opened#chunk-0    5. policy-warranty-electronics#chunk-2     ◄ swapped in: same category
   ```

   H1's own chunk did not rank, so it is put first, and the phone policy falls off the end. The laptop
   policy is another category, so it is swapped for the best unused electronics policy chunk (ADR-020).
3. Four of five chunks are policy chunks, so the lane is **POLICY**.
4. The top-ranked **policy** document is `policy-return-electronics`. That is the namespace. H1's chunk
   is first in the list, but it is a product chunk, so it does not decide a POLICY namespace.
5. The namespace is empty, so nothing is judged: **MISS**.
6. The model writes an answer (8,095 ms, the first request after start), and a new entry is stored in
   `policy-return-electronics`, with the five chunks above as its sources (§7):

   > "Yes, you can get a full refund on these headphones within 30 days of receiving them. According to
   > the policy, TVs and headphones bought from the store are coverable within 30 days of receipt for a
   > full refund or an exchange. The items also require specific packaging (like charging cases for
   > headphones) when returned via mail."

**Question 2:** the same words, from the same product page. **Tier-1 hit** in 1 ms. Tier 2 does not run.

**Question 3:** "Is a full refund possible for these headphones 30 days after delivery?" (H1)

1. Tier 1 misses: the words are different.
2. Retrieval returns **the same five chunks** as Question 1.
3. Lane POLICY, namespace `policy-return-electronics`: the same as the entry.
4. The search finds Question 1's entry at similarity **0.9932**.
5. Namespace equal, and 0.9932 ≥ 0.85, so the gate runs. (Containment is 5/5 = 1.00, logged only.)
6. The gate refuses: **MISS**, cause `SUPPORT`. The model answers again (4,639 ms).

| Gate arm | Result |
| :--- | :--- |
| Lexical | 32 content words in the cached answer, 18 of them in the new evidence: 18/32 = **0.5625**, below 0.6 |
| Numeric | pass: *30 days* is in the return policy chunk |

The 14 words not found are the model's own wording: *according, cases, coverable, get, like, mail,
packaging, receipt, receiving, require, returned, specific, via, yes.* The policy says "received", and
the gate does no stemming, so "receiving" and "receipt" do not count.

**What this shows.** A safe paraphrase, with the same evidence and a similarity of 0.9932, was refused
because the cached answer used words that the policy does not use. The refusal is safe, but it costs a
generation (false miss 4 in §12a).

**Question 4:** "Can I get a full refund on this sofa 30 days after delivery?" (Sofa)

```
cached entry (Question 1, headphones)                retrieved now (Question 4, sofa)
  1. product-electronics-b07zj7qg33#chunk-1            1. product-furniture-b019x98zxm#chunk-0
  2. policy-return-electronics#chunk-0   ◄ top policy  2. policy-return-furniture-opened#chunk-0    ◄ top policy
  3. policy-return-electronics#chunk-1                 3. policy-return-furniture-unopened#chunk-0
  4. policy-return-electronics#chunk-2                 4. policy-return-furniture-opened#chunk-2
  5. policy-warranty-electronics#chunk-2               5. policy-return-furniture-unopened#chunk-2
```

The two lists share no chunk. The namespace is `policy-return-furniture-opened`. It is empty, so the
headphones answer is **never a candidate**: MISS, nothing judged. (The two questions differ in one word.
Their similarity is 0.8469, just below τ.)

Two things in this result are not the cache's work:
- **The condition was chosen by a small margin.** The question does not say whether the sofa was
  opened. The opened policy scored 0.7448 and the unopened one 0.7325, so the namespace is "opened" by
  0.012. This is the routing limit of §12a, rows 5 and 9.
- **The model's answer is wrong.** It says that a full refund is not possible, but both policies allow
  30 days (180 days opened, 365 days unopened). That is a generation error. The cache stores it like
  any other answer, and a later paraphrase could reuse it.

**Question 5:** Question 1's words again, but from H2's page.

1. Tier 1 misses: the Tier-1 key includes the `product_id` (ADR-018).
2. Retrieval returns H2's own chunk and the same four policy chunks as Question 1.
3. Lane POLICY, namespace `policy-return-electronics`. A policy namespace is shared by every product the
   policy covers (Step 4).
4. The search finds Question 1's entry at similarity **1.0000**, because the text is the same.
   Containment is 4/5 = 0.80, because the product chunk differs.
5. The gate gives 18/32 = 0.5625 again, because the cached answer has no word that only H1's chunk
   contains. **MISS**, cause `SUPPORT`. A second entry with the same question text is stored beside the
   first.

**What Questions 4 and 5 show.** The namespace follows the policy, not the product. A sofa question goes
to a furniture policy and never meets a headphones answer. A question from another pair of headphones
goes to the same electronics policy and does meet it. There, only the gate decides.

## 10. Example B — return or warranty, on the same headphones

The same run continues. Questions 1 to 3 are asked from H1's page, and Question 4 from H2's.

| | Question | Retrieved, in rank order | Namespace | Result |
| :---: | :--- | :--- | :--- | :--- |
| 1 | "How long do I have to return these headphones?" | H1 #1 · return-electronics #0, #1, #2 · warranty-electronics #2 | `policy-return-electronics` | MISS, `SIMILARITY` (0.8240) |
| 2 | "How long is the warranty on these headphones?" | H1 #1 · warranty-electronics #0 · return-electronics #0 · warranty-electronics #1 | `policy-warranty-electronics` | MISS, nothing judged |
| 3 | "What warranty period do these headphones come with?" | the same four as Question 2, in another order | `policy-warranty-electronics` | **TIER2_HIT**, 86 ms |
| 4 | Question 2's words, from H2 | H2 #1 · the same three policy chunks | `policy-warranty-electronics` | **TIER2_HIT**, 85 ms |

In the table, `#1` stands for `chunk-1`, and the `policy-` prefix is left out.

**(a) The namespace separates return from warranty.** Both questions retrieve the electronics return
policy and the electronics warranty. The rank decides: the return question ranks the return policy
first, and the warranty question ranks the warranty first. So the warranty question searches a
namespace that holds only warranty answers, and it never sees a return answer.

Question 2 has four chunks, not five. Without the `product_id`, its top five would also hold two other
headphones' chunks and the phone and laptop warranties. The retriever dropped the two other products,
put H1's chunk first, and swapped the two warranties for electronics policy chunks (Step 1).

**(b) Similarity separates this pair, but only just.** The return and warranty questions score 0.8043,
below τ = 0.85. But Question 1 was refused too. Its nearest stored answer says 30 days, which is right,
and it scored only 0.8240. The safe reuse and the trap are 0.02 apart. This is the problem of §3: a
similarity-only cache would need its τ inside that gap.

**(c) Containment would separate this pair too.** Against the entry of Example A, Question 1, it is 1.00
for the return question (the same five chunks) and 2/5 = 0.40 for the warranty question. It is still
not used, because on the `v1` validation pairs it does not separate paraphrases from same-product traps
(§8).

**(d) A paraphrase is served when the answer stays close to the policy.** Question 3 found Question 2's
entry at similarity 0.9256, with containment 4/4 = 1.00. The gate found 33 of the answer's 38 content
words (0.8684). The five missing words are *automatically, failing, like, specifically, though*. The
numeric arm found *1 year* in the warranty chunk. Result: TIER2_HIT in 86 ms.

**(e) A shared policy answer can carry another product's name.** Question 2's answer, written on H1's
page, says: "…whether the item was bought online or in person at the Soundcore store." Soundcore is
H1's brand.
- Question 4, from H2's page, found that entry at similarity 1.0000 (containment 3/4 = 0.75).
- The word *soundcore* is only in H1's chunk, so the gate found one word fewer: 32/38 = 0.8421, still a
  pass.
- H2's customer was served an answer that names another brand, in 85 ms. The 1-year term is right for
  H2, so the error is one phrase.

This is trap 13 of §12a, and no part of the rule can see it. Note also that the HTTP response of a
Tier-2 hit lists the **entry's** sources, so Question 4's response shows H1's chunk, not H2's.

**The same case in the unit tests (`dev-v0`).** The namespace was designed for a pair measured on
6 Sep 2026 on `dev-v0`, and the unit tests still pin it. There, a return paraphrase and a warranty
question about the EarBuds Pop 3 scored 0.9382 and 0.9208 against a cached return answer, both above τ.
Both also had containment 4/5 = 0.80. Only the namespace told them apart. The tests also check the gate
as a second line of defence, with an authored cached answer of 16 content words:
- it scores 14/16 = 0.875 against the paraphrase's evidence, and 5/16 = 0.3125 against the warranty
  evidence;
- the numeric arm refuses the warranty case, because no chunk contains 30.

(The numeric arm has one looseness, kept on purpose: a unit must appear with *some* number in the same
chunk, not necessarily with this one.) The tests are listed in §14.

## 11. Example C — the gate on answers the model really wrote

**Setting.** On 14 Oct 2026, on `dev-v0`, 27 answers that the model really generated were collected,
and the gate was run on pairs of (cached answer, evidence). The gate was called **directly**, not
through the full request path, so these pairs test the gate on its own.

**It catches a wrong number that the words miss.** The cached answer: *"The battery life of the
SoundMax ANC Pro is 40 hours."* The evidence: the chunk of a **different** product, the SoundMax ANC
Lite, whose battery is 30 hours.

- Lexical arm: 6 content words (*battery, life, soundmax, anc, pro, hours*), 4 found (*soundmax, anc,
  battery, hours*): 4/6 = **0.667**. **Pass.**
- Numeric arm: *40 hours* is not in the chunk, which says 30 hours. **Refuse.**

In the full request path the namespace would already separate these two products. This pair shows why
the numeric arm exists.

**It refuses a correct answer.** The question: "what is the battery life of the EarBuds Pop 3". The
answer: *"The battery life of the EarBuds Pop 3 is 6 hours, with an additional 24 hours when using the
case."* The evidence: that product's own chunk, the evidence the answer was written from.

- 9 content words (*battery, life, earbuds, pop, hours, additional, when, using, case*), 5 found:
  5/9 = **0.556**. **Refuse.**

The answer is right. The gate refuses it because the model used words the spec sheet does not use
(*life, additional, when, using*).

**What the whole sample showed:**

- **0 of 5** real paraphrases were refused. With so few, the 95 % upper bound is still 43 %.
- **2 of 21** answers (9.5 %) scored below 0.6 against the very evidence they were written from.
- Answers that mention "the context" ("as listed in the context") score lower: mean 0.60 with that
  word, 0.85 without.

Nothing was tuned after the sample. A strict gate costs hit rate, not safety, and whether to change the
lexical score is a decision for the final study, made before its data is seen.

**The live run of 7 Nov 2026 adds five gate decisions on `v1`.** Two were refusals of a correct
answer at 0.5625 (Example A, Questions 3 and 5, the same cached answer). Three were passes at 0.8421 to
0.9091 (Example B, Questions 3 and 4; Example D, Question 2). The numeric arm passed all five.

## 11a. Example D — a product question that carries a `product_id`

The same run continues, on the laptop's page. The laptop's record is cut into three chunks.

**Question 1:** "Which graphics card does this laptop have?"

1. Tier 1 misses: nothing is stored for this product yet.
2. Retrieval. Without the `product_id`, four of the top five chunks belong to other laptops, and this
   laptop's chunk ranks fourth. With it, the four are dropped. No policy chunk ranked, so their places
   are filled with this laptop's other chunks (ADR-021). The laptop has only three, so three are
   returned: the whole record.

   ```
   without product_id                               with product_id (what the gateway got)
     1. product-laptops-b01ld4mgoy#chunk-0  0.7710    1. product-laptops-b07qvm5x8w#chunk-0  0.7504
     2. product-laptops-b00ep09b4m#chunk-0  0.7659    2. product-laptops-b07qvm5x8w#chunk-1  0.6400
     3. product-laptops-b01bm8g3uy#chunk-0  0.7617    3. product-laptops-b07qvm5x8w#chunk-2  0.6377
     4. product-laptops-b07qvm5x8w#chunk-0  0.7504
     5. product-laptops-b07bp9b1nt#chunk-0  0.7473
   ```
3. No policy chunk, so the lane is **SPEC**.
4. The namespace is `product-laptops-b07qvm5x8w`. It comes from the `product_id` in the request, **not**
   from the retrieved chunks.
5. The namespace is empty, so nothing is judged: **MISS**. The model answers in 1,791 ms: "The graphics
   card in this laptop is an NVIDIA GeForce GTX 1660 Ti with 6GB of dedicated GDDR6 VRAM."

**Question 2:** "What GPU is in this laptop?"

1. Tier 1 misses. Retrieval returns the same three chunks in another order, and the lane and the
   namespace are the same as for Question 1.
2. The search finds Question 1's entry at similarity **0.9105**. Containment is 3/3 = 1.00.
3. The gate finds 10 of the answer's 11 content words in the evidence (only *card* is missing):
   **0.9091**. The numeric arm passes. (The log reports one number read without a unit, which is checked
   by its value only.)
4. **TIER2_HIT** in 69 ms.

**Question 3:** "How much RAM does this laptop have?"

1. The same namespace, and the same three chunks again.
2. The search finds Question 1's entry at similarity **0.7821**, below τ: **MISS**, cause `SIMILARITY`.
   The model answers in 1,258 ms: "The laptop has 16GB of RAM."

**What this shows.**

- **The namespace is the product named in the request.** Another laptop with almost the same wording can
  never be a candidate, whatever retrieval returns.
- **Containment adds nothing here.** Question 3 retrieves exactly Question 1's three chunks, so its
  containment would be 1.00, the same as for the true paraphrase. (The gateway computes containment
  only for a candidate that clears τ, so this value is computed by hand.)
- **Only similarity stopped Question 3.** If a RAM question had cleared τ, the gate would have checked
  the GPU answer against the same three chunks as in Question 2. It would have given the same 0.9091
  and passed, because the laptop's record contains the GPU. This is trap 4 of §12a: the product's chunks
  contain both facts.

## 11b. Example E — one question about a product and a policy (the MIXED lane)

**Setting.** 7 Nov 2026, a second run that started from an empty cache. The gateway first ran with
**MIXED on**: `make dev` with nothing set, which logs `lane_band=[0.20,0.60) mixed_lane=on` (Step 3).
Then it ran with MIXED off, for comparison. Memory pressure was green at the start and yellow after, so
the latencies are not measurements.

**Question 1:** "How long does the battery of these headphones last, and how long is the warranty?" (H1)

1. Retrieval returns only **two** chunks: H1's own chunk and `policy-warranty-electronics#chunk-0`. The
   other chunks of the top five belonged to other products, and they were dropped. A policy chunk
   ranked, so their places are not refilled (Step 1).
2. One of the two chunks is a policy chunk, so the fraction is 0.50. That is inside the band
   [0.20, 0.60), so the lane is **MIXED**.
3. The namespace is the pair `product-electronics-b07zj7qg33|policy-warranty-electronics`: the product
   from the request, and the top-ranked policy document.
4. The namespace is empty: **MISS**, nothing judged. The model answers (7,674 ms) with the battery hours
   from H1's chunk (40, 60 and 4 hours) and the 1-year warranty.

Four more questions followed:

| | Question (page) | Lane, namespace | Candidate | Result |
| :---: | :--- | :--- | :--- | :--- |
| 2 | "What is the battery life of these headphones, and what warranty do they come with?" (H1) | MIXED, H1 \| warranty | Question 1, similarity 0.9308 | **TIER2_HIT**, 588 ms |
| 3 | Question 1's words (H2) | MIXED, H2 \| warranty | none: the namespace is empty | MISS, nothing judged |
| 4 | "Do these headphones have noise cancelling, and how long is the warranty?" (H1) | MIXED, H1 \| warranty | Question 1, similarity 0.8660 | **TIER2_HIT**, 41 ms |
| 5 | "What colours do these headphones come in, and what does the warranty cover?" (H1) | **POLICY**, `policy-warranty-electronics` | none | MISS, nothing judged |

**Question 2, a safe hit.** It retrieves the same two chunks, so containment is 1.00. The first check of
the judge is the composite rule: the candidate must be MIXED too, and both halves of the pair must be
equal (the log says `rule=composite lane_match=true`). The gate found 30 of the answer's 43 content words
(0.6977) and every number in it. The answer was served. (Of the 588 ms, the embedding call alone took
542 ms, against 25 to 40 ms in the other requests.)

**Question 3, the reason MIXED exists.** The words are Question 1's, so the similarity is 1.0000. But the
product half of the namespace is H2, so Question 1's entry is never a candidate. This matters: H1's answer
says 40 and 60 hours, and H2's chunk says 30 hours. H2 gets its own answer.

**Question 4, a hit that answers the wrong half.** It retrieves the same two chunks, at similarity
0.8660. The gate gives the same 0.6977, because the answer and the evidence are the same. The answer was
served in 41 ms. It gets the warranty right and mentions "active noise cancellation mode" only in
passing, but most of it is about the battery, which this question did not ask. This is trap 4 of §12a
inside the MIXED lane: the evidence holds both facts, so the gate cannot tell them apart, and only τ was
in the way.

**Question 5, MIXED does not catch every mixed question.** This question retrieved H1's other chunk and
three warranty chunks. The fraction is 3/4 = 0.75, above the band, so the lane is POLICY and the colour
half drops out of the key. ADR-016 counts this case: 15 of 33 stratum-D questions stay POLICY with the
band on. A read-only probe found the other two cases as well:
- a GPU and return question on the laptop retrieves 4 policy chunks of 5 (POLICY);
- "How long is the warranty on these headphones, and do they support Bluetooth 5.0?" retrieves no policy
  chunk (SPEC), so its warranty half has no evidence.

**The same pair with MIXED off.** The gateway was restarted with `LANE_SIGMA_HI=0.20` on an empty cache,
and Questions 1 and 3 were sent again. The model wrote new answers.

| | MIXED on | MIXED off |
| :--- | :--- | :--- |
| Question 1 (H1): lane, namespace | MIXED, `…b07zj7qg33\|policy-warranty-electronics` | POLICY, `policy-warranty-electronics` |
| Question 3 (H2): lane, namespace | MIXED, `…b079jfb616\|policy-warranty-electronics` | POLICY, `policy-warranty-electronics` |
| Does Question 3 meet H1's answer? | no | yes, at similarity 1.0000 (containment 0.50) |
| The gate on H1's answer | not run | lexical 10/15 = 0.6667, **pass**; numeric **fail** |
| Result for Question 3 | MISS, nothing judged | MISS, cause `SUPPORT` |

With MIXED off, the product drops out of the key, so H2's question meets H1's answer. The words pass the
gate, and only the numbers stop it: H1's answer said "4 hours" and "60 hours", and neither is in H2's
chunk. If the answer had held no number, or only numbers that both products share, it would have been
served to H2.

**What this shows.**
- **MIXED keeps the product in the key** for a question that needs both a product and a policy. A second
  product never meets the first product's answer (Question 3).
- **With MIXED off, the numeric arm is the only defence** in this case. ADR-016 expected that it "may
  already refuse part of these false hits", and here it did, because the answer held battery numbers.
- **MIXED does not help inside one product** (Question 4), and **it does not reach every mixed
  question** (Question 5).

---

# Part 4 — Measuring and limits

## 12. What each decision leaves in the log

Every request writes **one JSON line** to an evaluation log. These fields describe the Tier-2
decision:

| Field | Meaning |
| :--- | :--- |
| `cache` | `TIER1_HIT`, `TIER2_HIT`, `MISS`, … |
| `similarity` | the candidate's similarity, or `null` when no candidate was found |
| `entered_band` | the candidate cleared τ |
| `source_overlap` | the containment score of §8, logged only |
| `refusal_cause` | `NONE`, `SIMILARITY`, `NAMESPACE`, `SUPPORT`, `NOT_SCORED`, or `null` when nothing was judged |
| `support_lex`, `support_numeric_ok` | the two arms' results, or `null` when the gate did not run |
| `retrieved_chunk_ids`, `candidate_entry_id`, `candidate_sources` | the evidence of this request, and the entry that was judged |
| `support_gate` | `on` or `off`: which version of the rule this process ran |
| `mixed_lane` | `on` or `off`: which MIXED arm this process ran (ADR-016) |

For example, the refusal of Question 3 in Example A would be written like this. (The evaluation log was
switched off during that run, so this record is built from the gateway's log line for that request,
and only the Tier-2 fields are shown.)

```json
{
  "cache": "MISS",
  "support_gate": "on",
  "similarity": 0.9932,
  "entered_band": true,
  "source_overlap": 1.0,
  "refusal_cause": "SUPPORT",
  "support_lex": 0.5625,
  "support_numeric_ok": true,
  "retrieved_chunk_ids": ["product-electronics-b07zj7qg33#chunk-1", "policy-return-electronics#chunk-0",
                          "policy-return-electronics#chunk-1", "policy-return-electronics#chunk-2",
                          "policy-warranty-electronics#chunk-2"],
  "candidate_entry_id": "<Question 1's entry>",
  "candidate_sources": ["…the same five chunks…"]
}
```

The HTTP response to the user shows the similarity and the overlap, but it has **no field for the
reason**. The reason is only in the log.

**The gate can be switched off, to measure it.** `SUPPORT_GATE=on` (the default) or `off` is set for
each run. With the gate off, Tier 2 serves on namespace and similarity alone, and both support fields
are `null`. Every record names the setting, so a run with the gate and a run without it can be
compared, and the gate's own effect, in false hits prevented and in hits lost, can be measured.

## 12a. Traps: every way a reuse decision can go wrong

A cache can be wrong in two directions:
- A **false hit** serves a stored answer that is wrong for the new question. It costs **correctness**.
- A **false miss** calls the model although a right answer was already stored. It costs **capacity**: the
  hit rate falls, and the machine serves fewer questions.

The frontier of Phase 6 measures the trade between the two. Here is every trap known so far, sorted by the
part of the system it gets past.

**False hits — a wrong answer is served.** The numbers in the last column are queries in the `v1`
validation and test splits.

| # | Trap | Example | What stops it | It still gets through when | In the `v1` workload? |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1 | Same words, **different product** (Tier 1) | "Is it waterproof?" asked on two product pages | `product_id` is in the Tier-1 key (ADR-018) | the request carries no `product_id` | no: the corpus gate (G3) excludes it |
| 2 | **Normalisation collision** (Tier 1) | "1.5 m" and "15 m"; "-10 °C" and "10 °C"; "15 %" and "$15" | **nothing**: Tier 1 runs no rule | always | no: G3 excludes it |
| 3 | **B-cross**: similar words, another product | "full refund on my headphones…" against "…on my sofa…" | the namespace | there is no `product_id` and the top-ranked document is wrong | yes: 11 + 11 |
| 4 | **B-within, spec attribute**: same product, another attribute | "Does it work with Windows 10?" against "…Windows 7?" | only the support gate; its numeric arm when the answer holds a number | the product's chunks contain both facts, so the answer is "supported" | yes: 52 + 47 |
| 5 | **B-within, policy condition** | opened against unopened; new against renewed | separate documents give separate namespaces | retrieval ranks the wrong condition first (see below) | yes: 40 + 80 |
| 6 | **B-within, policy region** | domestic against international warranty | as row 5 | as row 5 | yes: 6 + 12 |
| 7 | **B-within, policy kind** | return against warranty, same product | the namespace, and the numeric arm (30 days against 1 year) | retrieval ranks the wrong document first | yes: 6 + 3 |
| 8 | **B-within, condition by department** | opened phone against opened chair | the namespace | as row 7 | yes: 16 (validation) |
| 9 | **The condition said in other words** | "still sealed" for unopened, "used" for opened | only retrieval | retrieval is right only 56 % of the time (see below) | almost none: 13 of 134 |
| 10 | **Same evidence, opposite condition or negation** | "Is the battery removable?" against "…**not** removable?" | **no check can see it** | always | yes; reported as RQ2a (item 6.4) |
| 11 | **Product and policy in one question** (stratum D) | "If this laptop is new, how many days do I have to return it, and how much does it weigh?" | the MIXED lane, on its on arm (ADR-016) | the arm is off: the product half is ignored; or the policy fraction falls outside the band (Example E, Question 5) | yes: 33 + 36. Both arms live in Example E |
| 12 | **A stale answer after a source edit** | a return window changed from 30 to 14 days | dependency purge and the epoch guard (Phase 4) | a purge misses an entry (completeness below 1) | in `mutation: on` runs (item 6.5) |
| 13 | **A shared policy answer names another product** (found 7 Nov 2026) | asked about a Nokia Lumia 830, served "…no restocking fee for returning an unopened iPhone 8 Plus Gold" | **nothing** in the rule; the judge marks it `INCORRECT` | the model writes the product name into a POLICY answer, and the gate passes on the policy words | yes: 3 of 94 Tier-2 hits in the 1 Nov cost run (not citable); super-plan item 5.6. Seen live in Example B (e) |

When retrieval picks the wrong document, the answer is wrong **even with no cache**: the model writes
from the wrong evidence. The cache inherits that error, and so does the reference answer the judge
compares against. Item 5.2's labelling ablation exists to measure this.

**False misses — the model runs although a right answer was stored.**

| # | Cause | Example | Where it shows |
| :---: | :--- | :--- | :--- |
| 1 | **Similarity below τ** (stratum C, very different words) | "How do I send back X?" against "What is the return process for X?" (Example B, Question 1: 0.8240) | refusal cause `SIMILARITY` |
| 2 | **The namespace differs on a safe reuse** | one paraphrase is routed to the other condition's document; no `product_id` | `NAMESPACE`, or the search finds no candidate at all |
| 3 | **The MIXED arm moves a question to another namespace** | 9 policy and 3 product-only questions lose their reuse (ADR-016) | per arm, `mixed_lane` |
| 4 | **The support gate refuses a right answer** | the model used its own words, not the evidence's (Example A, Question 3: `S_lex` 0.5625; Example C: 0.556) | `SUPPORT`; GroundedCache reports that this gate cut its speed-up from 1.48× to 1.04× |
| 5 | **Only the nearest entry is judged** (k = 1) | the nearest entry is wrong, and a right one sits second | ADR-009: the same `candidate_entry_id` refused again and again |
| 6 | **Same question, another `product_id`** | one policy question asked on many product pages gets one entry per page | ADR-018; zero on `v1`, where no question is shared across products |
| 7 | **Evicted by the LRU limit** | the cache holds only 0.25 × K entries | tier mix, item 7.1 |
| 8 | **Purged by a cosmetic edit** | blind purge removes answers the edit did not change | precision, item 6.5 (0.695 in item 4.4, not citable) |
| 9 | **Nothing was written** | the epoch moved during generation; `NOT_SCORED`; the embedding failed | `writeback_discarded`, `NOT_SCORED` |
| 10 | **Paraphrases in flight at the same time** | coalescing joins only identical questions | item 7.1 |

**Two measurements behind rows 5 and 9** (`v1` validation split, not citable;
`docs/work/2026-10-30-condition-routing-probe/`). The question is whether retrieval ranks the **right
condition document** first. That document is the POLICY namespace, so it is what keeps an "opened" answer
away from an "unopened" question.

- **The workload's own questions:**
  - with the condition word in the question, 98 of 121 are right (81 %);
  - without it ("the US version" for domestic), 9 of 13 are right (69 %);
  - when wrong, retrieval often picks **the opposite condition**: new → renewed, unopened → opened,
    domestic → international.
- **Synonyms**, 43 rewrites written for the probe: only **24 of 43** are right (56 %), and the errors
  point one way:
  - "still sealed", "never opened" and "brand-new in its sealed box" (all meaning unopened) go to the
    **opened** document;
  - "used", "unboxed" and "already taken out of the box" (meaning opened) go to the **unopened** document;
  - "brand-new" and "factory-sealed" (meaning new) go to the **renewed** document.

  The embedding follows the **letters** ("never opened" contains "opened"), not the condition they
  describe.

**What follows from this.**
- **These are retrieval limits, not cache-rule limits.** They are reported, not fixed: the corpus, the
  workload and the retriever are frozen.
- **Phase 6 will understate the risk of rows 2 and 9.** The workload almost always uses the literal
  condition word (121 of 134), and G3 keeps normalisation collisions out of it.
- **Possible fixes, all for future work:**
  - a normaliser that keeps signs and decimal points next to digits;
  - hybrid retrieval, with keyword search beside the embedding, for condition words;
  - a query-side condition check. That last one is ruled out in this thesis: the reuse decision may
    never read the question text as a signal.

## 13. Limits and open points

**Decided since the first version of this document:**

- **The overlap score is logged but does not decide** (§8). ADR-019 records this, and the thesis claim is
  restated around the served rule. The proposal and `CLAUDE.md` still describe four checks; those files
  are the author's to update.
- **The MIXED lane** is one pinned band, run as an on/off arm (ADR-016; Step 3).
- **Removing answers when a source changes is built** (Phase 4): dependency purge, the epoch guard, and
  tracking of every Tier-1 key.
- **`product_id` will join the POLICY namespace** (ADR-024, 7 Nov 2026, **not built yet**). It closes trap 13.
  Example A, Question 5, and Example B (e) show the rule as it runs today, before the change.

**Open in the design:**

- **Traps the frozen workload hardly contains** (§12a): conditions said in other words (rows 5 and 9), and
  Tier-1 normalisation collisions (row 2). They are limits to report.
- **Same evidence, opposite condition.** Two questions can retrieve the same chunks and ask about
  opposite conditions, for example an opened and an unopened item. The namespace and the gate both look
  at the evidence, and the evidence is the same, so neither can tell them apart. The planned defence is
  in the corpus: opposite conditions are written into **separate documents**, so they get separate
  namespaces. The thesis reports this residual as part of its claim.
- **Only the nearest entry is judged** (`k = 1`). A refused entry is not removed, so it can stay the
  nearest one and be refused again for each new paraphrase.

**Weak points of the gate, measured:**

- **It is strict.** About one correct answer in ten is refused against its own evidence, mostly because
  of the model's wording (§11).
- **It can be fooled by wording.** An answer that mostly repeats product specs passes even against the
  wrong policy, because spec words appear in every product chunk. A test keeps this case visible.
- **The evidence is small.** The gate's numbers in §11 are from the 44-document development corpus, not
  from `v1`. The thesis measures it on `v1` in Phase 6.

## 14. Code map and further reading

| File | What it does |
| :--- | :--- |
| `gateway/internal/httpapi/handler.go` | One request: Tier 1, embedding and retrieval in parallel, serving, the miss and the write-back |
| `gateway/internal/httpapi/cascade.go` | Tier 2 itself: Steps 2 to 6, in order |
| `gateway/internal/reuse/lane.go` | Lanes, namespaces and the namespace rule |
| `gateway/internal/reuse/cause.go` | The fixed order of checks and the refusal cause (`Thresholds.Judge`) |
| `gateway/internal/reuse/support.go`, `support_numeric.go` | The lexical and the numeric arm of the gate |
| `gateway/internal/reuse/gate.go` | The gate's on/off switch |
| `gateway/internal/reuse/rule.go` | Containment, computed and logged only (ADR-019) |
| `gateway/internal/cache/tier2.go` | The Tier-2 record, the index and the namespace-scoped search |
| `gateway/internal/cache/key.go`, `normalize.go` | The Tier-1 key: the normalised question and the `product_id` (ADR-018) |
| `gateway/internal/deps/` | The dependency map, the blind purge and the epoch check (Phase 4) |
| `gateway/internal/embed/client.go` | The query embedding, with its prefix |
| `gateway/cmd/gateway/main.go` | The defaults: `REUSE_TAU=0.85`, `REUSE_THETA=0.60` (sets the logged containment verdict only), `LANE_SIGMA` = `LANE_SIGMA_HI` = 0.20 (MIXED off), `SUPPORT_GATE=on` |

The `reuse/` package uses only Go's standard library and does no input or output. That is deliberate:
the reuse decision can be tested on its own, with no Redis, no network and no model.

**Tests that pin the examples** (all in `gateway/internal/reuse/`):

- `TestNoThetaSeparatesTheMeasuredPair` (`lane_test.go`) — §10's `dev-v0` pair: equal containment,
  different namespaces.
- `TestSupportLexicalSeparatesTheMeasuredPair` (`support_test.go`) — the same pair, the 14/16 and 5/16.
- `TestNumericMeasuredPair` (`support_numeric_test.go`) — the same pair, the numeric arm.
- `TestJudgeAgreesWithDecideLane` (`cause_test.go`) — the order of checks agrees with the namespace
  rule on every input.

Run them with `cd gateway && go test ./internal/reuse/`.

**Replaying Examples A, B, D and E.**
1. Stop any gateway, then run `make cache-reset`. It deletes the `t1:`, `t2:`, `lru:`, `dep:` and
   `entry:` keys and keeps the corpus. Never use FLUSHDB: it drops every search index.
2. Start `make dev`. It starts with MIXED on (Step 3). For Example E's off arm, start
   `LANE_SIGMA_HI=0.20 make dev` after a new `make cache-reset`.
3. Send each question, with its `product_id`, to `POST /ask` in the order of Part 3. `make ask` sends no
   `product_id`, so use `ask.sh` in `docs/work/2026-11-07-tier2-doc-examples/`.

The model words its answers differently on each run, so the answers and the `S_lex` values change.
Retrieval, lanes and namespaces should not. Examples A, B and D ran with MIXED off, but their lanes are
the same either way, because their policy fractions are 0, 0.75 or 0.80. `make demo` and
`make demo-reset` still use `dev-v0`, and they refuse while Redis holds `v1`.

**Decisions and contracts behind the rules:**

- `docs/decisions.md`:
  - **ADR-004**: one search, inside the namespace;
  - **ADR-009**: the gate is served, and every judged candidate gets one cause;
  - **ADR-010**: the gate's on/off switch;
  - **ADR-016**: the MIXED band and its arm;
  - **ADR-018**: `product_id` in the Tier-1 key;
  - **ADR-019**: the served rule, and containment as a logged counterfactual;
  - **ADR-020** and **ADR-021**: retrieval with a `product_id` keeps this product's category of
    policy, and fills other products' places with this product's own chunks.
- `docs/contracts/interfaces.md`: §A (the HTTP response), §D (the cache records), §H (the evaluation
  log).
- `docs/work/2026-10-14-real-answer-sample/`: the full data behind Example C.
- `docs/work/2026-10-30-adr-019-theta-overlap/` and `docs/work/2026-10-30-condition-routing-probe/`: the
  `v1` measurements in §8 and §12a.
- `docs/work/2026-11-07-tier2-doc-examples/`: the gateway logs, the answers and the scripts behind
  Examples A, B, D and E.
- `docs/0. progress 16-10.md` §1.5: the old `dev-v0` demo of 15 Oct 2026, which Example A replaced.
- `docs/1-System Docs/Redis-Data Structure.md` §5: the Tier-2 record field by field.
