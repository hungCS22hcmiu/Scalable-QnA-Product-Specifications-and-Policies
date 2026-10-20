# Impact: policy-documents (item 3.3)

**Analyst:** impact-analyst subagent, 2026-10-20. I worked from `spec.md` as first written; `design.md` does not exist yet.

> **Note added on saving (2026-10-20).** The analyst read `spec.md` only. `design.md` draft 1 was
> written at the same time, and it settles two points below: doc ids are **derived from the
> fields** (`policy-return-…`, singular), so v1's electronics return document is
> `policy-return-electronics` and does **not** reuse dev-v0's `policy-returns-electronics` (§7 B);
> and the derived-id check is P3 (§9 point 2). Two claims were checked by hand on saving. Policy ids
> appear in `interfaces.md` only as examples: **correct**. §7 D, "if 14 days and $45 fall in
> different chunks, a cached answer that states both is supported by no single chunk": **not
> correct**. `numSupported` (`gateway/internal/reuse/support_numeric.go:185`) checks each number on
> its own against every chunk, so two numbers may sit in two chunks. What "chunks are read alone"
> (`decisions.md:75`) means is that a number and **its unit** must be in the same chunk, attached
> ("14 calendar days" loses the unit). `design.md` draft 2's W3 covers that instead. Every other
> finding is merged into draft 2.

## Verdict

The technical risk is low, but the item carries a lot of weight for validity. No frozen value moves, no `interfaces.md` surface changes, no cut scope comes back, no dependency is added, and there is no run to invalidate (`experiments/results/` holds only `.gitkeep`). The two new fields are inert. I ran `record_to_document` on a record with and without `policy_kind` and `condition`: the text, the metadata keys and the chunk count were the same. But this item writes half of the measured corpus, so **the experiment phase is required**, for the same reason as at 3.2. The real risks are silent, and they sit in the writing:
- the scan's word list
- a document naming its twin's condition
- filler text shared across documents
- a ≥ 3-chunk count that depends on an unpinned `llama-index-core`

Settle all four in `design.md` and commit them before the first document (P6).

## 1. Files touched and layering

| Path | Change |
| :--- | :--- |
| `data/policies-v1/` (13 × `{doc_id}.json`) | new and tracked (`git check-ignore` matches nothing) |
| `experiments/scripts/check_policies.py`, `experiments/tests/test_check_policies.py` | new |
| `Makefile` | new `policy-check` target |
| `docs/data-card.md` §2, Schemas, §7 | fill `:94`, `:160`, `:263`; `:76` still lists shipping |
| `docs/architecture.md` | tree `:82`, `:100-117`; command table `:222`; inventory `:241` |
| `docs/decisions.md` | ADR-012 and its summary row, if the author agrees |
| trail `evidence/sources.md` | new |
| *Only if G5 is folded in:* `corpus_gate.py`, `test_corpus_gate.py` | see §8 |

Nothing changes in `rag/`, `gateway/`, `contracts/`, `interfaces.md` or the `.proto`.

**Layering is OK.**
- **experiments → rag has precedent.** `select_pqa.py:547-550` already imports `rag.ingest` lazily, and so does `corpus_gate.py:504-505`. `rag` never imports `experiments`. Importing `rag.ingest` also pulls in `redis` and the vector store (`ingest.py:13`, `store.py:12-14`), but it opens no connection, so "no Redis, no Ollama" holds.
- **check_policies → corpus_gate (if G5 is folded in) has precedent too.** `select_pqa.py:50` does `import build_pqa`, and the tests get the path from `experiments/tests/conftest.py:7`. The gate owns G5 and the checker calls it. `corpus_gate` must never import the checker, or there is a cycle.
- **The new data folder** is allowed once the tree lists it (`architecture.md:16-17`). One naming risk: `data/<dataset_version>/` is the corpus of record (`architecture.md:127-128`), and `policies-v1` looks like a version name but is not one. The tree entry should say "the source of v1's policy documents, not a dataset version; 3.6 copies it into `data/v1/`". Never pass it as `VERSION=` or as `DATASET_VERSION`.
- **Blocker for implementation:** this session denies Read and Write on `data/`. The author must grant access to `data/policies-v1/` before anything can be written or checked.

## 2. Frozen values and measured paths

**No frozen value changes:**
- chunking and retrieval: 256 / 40 and `top_k` 5 (`config.py:14-16`)
- embedding model and dim (`:10-11`)
- `DATASET_VERSION` stays `dev-v0` (`:19`); 3.6 bumps it
- the Redis schema (`store.py:27-46`)
- FLAT, eviction, capacity, δ and `num_ctx` are not touched

**Runs invalidated: none.** There are no runs yet. `v1` is not frozen, so editing its content now is free. After 3.6, any edit means a new `dataset_version` (`interfaces.md:354`).

**ADR:** none is forced, because no frozen value moves. ADR-012 (data) is still worth writing, because ADR-002 left the warranty sources and terms open (`decisions.md:296-299`).

**The two new fields never reach embedded text or Redis:**
- `record_to_document` copies only `doc_id`, `kind`, `category` and `title` into metadata (`ingest.py:64-69`).
- The embedded text is `title + "\n\n" + text` (`ingest.py:54-55`).
- All metadata is excluded from the embedding and LLM text (`ingest.py:88-89`).
- No Redis field exists for either new field (`store.py:27-46`).
- Measured: with and without the two fields, the text and the metadata keys `[category, doc_id, kind, title]` are equal, and so is the chunk count.

**Two things do reach a measured path:**
- **`category` is set on policy chunks for the first time** (dev-v0 wrote `""`, `data-card.md:90`) and lands in the Redis `category` tag. Nothing on the hit path reads it: retrieval filters by `doc_id` (`retrieve.py:99-100`) and the catalog by `kind` (`catalog.go:57`). That is intended; it is the join key.
- **Title and `doc_id` length count against the chunk size.** LlamaIndex measures the metadata while it splits (`llama_index/core/node_parser/interface.py:270-291`), and ingest sets the exclusions only after splitting (`ingest.py:88`). The title is also in chunk 0's embedded text, so it names the condition there.

**Keep the fields inert with one unit test:** `record_to_document` gives the same output with and without them.

## 3. Cut scope

**No breach.** Nothing is on the do-not-reinstate list (`CLAUDE.md`; `Final_Proposal.md:599`).

**One near-miss.** `Final_Proposal.md:435` rejected "an explicit condition **tag** on chunks", meaning a fifth term in the rule. The `condition` field is legal only because it stays in the source record and is read offline (by G5 and by 3.4). It must never reach chunk metadata, Redis or the gateway. Say so in ADR-012 and in data-card Schemas.

**The lexical scan is not the bypass classifier.** It runs offline over documents, never per request, and it never reads the query.

## 4. Dependencies

**None.** The checker uses `llama-index-core`, already a `rag` dependency (`pyproject.toml:12`), plus the standard library. It runs offline, so nothing stays in memory during a run: 0 MB of the envelope. No sign-off needed.

## 5. Contract

**No change, so the contract phase is not required.**
- **The proposed ids conform to §C.** Ids like `policy-returns-phones-opened`:
  - begin with `policy-` (`interfaces.md:352`; G4 at `corpus_gate.py:181-198`; `record_kind` at `ingest.py:39-44`)
  - contain no `#` (`docID` cuts at the first `#`, `lane.go:140-145`) and no `|` (`mixedSeparator`, `lane.go:211`)
  - may contain `-`, which the Tier-2 TAG query escapes (`tier2.go:161-174`)
- **`interfaces.md` names policy doc ids only in examples** (`:184`, `:351-352`, `:438-439`, `:584-585`, `:611-613`), never as a rule. The §B comment about "four policy docs" (`:298-307`) is history about dev-v0 and stays true.
- **The record shape lives in `data-card.md` Schemas** (`:178-181`), not in `interfaces.md`. Changing it is a data-card and ADR change, not a contract change.
- See 7(B) for §C's "never reused for a different document".

## 6. Measurement

**Yes, so the experiment phase is required.** No run happens in this item (P7), so nothing is re-measured. But this item fixes the inputs of G1 and G2 (the policy pairs), G5's count, RQ2a's B-within condition pairs, the lane split and the policy-lane namespace. That is the same reason 3.2 needed the phase (`2026-10-19-pqa-thick-tail-selection/impact.md:33-34`).

- **`K` and capacity:** not directly affected. `K` is the number of distinct workload queries (`corpus_gate.py:492`), and that comes from 3.4.
- **Lanes:** `PolicyFraction` is counted over `top_k` 5 (`lane.go:80-91`).
  - dev-v0 had 4 policy chunks, so policy questions scored 0.40–0.80 (`lane.go:30-32`).
  - v1 will have at least 39 (13 × ≥ 3), so most policy questions will score 1.0.
  - A product question that retrieves one warranty chunk scores 0.2. That reaches the default `Lo` 0.20, and with the band collapsed (`main.go:225-226`) the question goes to POLICY. With more policy chunks this will happen more often.
  - The dev-v0 band evidence (`main.go:219-224`) does not carry over to v1. The band is swept on v1 anyway; record this, do not fix it here.
- **Namespace:** the policy lane takes the `doc_id` of the rank-1 policy chunk (`lane.go:195`). There will be 13 namespaces instead of 4, and each split family gives two that differ only by condition. That is the design (`data-card.md:245-249`).
- **What the experiment approval records:** the writing rules, the condition list and the scan's word list, committed before the first document (P6), and no retrieval run before 3.6 (P7).

## 7. Hidden coupling

**A. Chunk counting**
- **`llama-index-core` is unpinned:** `pyproject.toml:12` says `>=0.11`, the installed version is 0.14.23, and tiktoken 0.13.0 comes in with it. A reinstall can change chunk counts.
- **How much text 3 chunks need:** with a title of this length, a synthetic repeated sentence needed about **360 words** of body text. Real prose will differ.
- **Count chunks the way ingest does:** call `splitter.get_nodes_from_documents([record_to_document(r)])`, as `select_pqa.py:555` does. Never split `policy_to_text` alone, because that drops the metadata from the count.
- **Record the versions and leave a margin:** print them, as `select_pqa.describe_default_chunker` does (`:528-540`). Avoid documents at exactly 3 chunks, and re-run `policy-check` at the 3.6 freeze.

**B. Two copies, and the names**
- **The snapshot covers `data/v1/` only** (`corpus_gate.py:551`). `data/policies-v1/` is not in the digest; only 3.6's copy is. The two copies can drift with no error. Carry to 3.6: check that the copy equals the source byte for byte.
- **`policy_kind` values:** the selector's `POLICY_Q` keys are `return` and `warranty` (`select_pqa.py:80-83`). The proposed values match, so keep those exact strings. Doc ids say `returns`, plural, so 3.4 must join on the field and never parse the `doc_id`. One pool question can carry both kinds (`select_pqa.py:230`).
- **A dev-v0 id may be reused:** dev-v0 tracks `policy-returns-electronics.json`, and v1's single electronics returns document would naturally get the same id with different text.
  - §C says a `doc_id` is "never reused for a different document" (`interfaces.md:352`), although uniqueness is only required per dataset version (`:355`).
  - Redis is safe: ingest's overwrite drops the old keys (RedisVectorStore `create_index` calls `drop=True`).
  - The risk is for a reader: one chunk id with two texts in dev-v0 logs and v1 logs.
  - This is cheap to fix now and impossible after the freeze. Pick a new id, or write in ADR-012 that the reuse is deliberate.

**C. The condition scan and the writing rules**
- **The scan's word list is part of the instrument:**
  - "unopened" contains "opened", so match whole words.
  - "new" is common English ("we send a new one"), so the grade axis needs phrases, not the bare word.
  - A lexical scan misses paraphrases such as "if the seal is broken"; `Final_Proposal.md:435` says the same about keyword rules. So the declared `condition` field and the author's read (P8) are the real guard, and the scan is a backstop.
  - Commit the word list with the writing rules (P6), or it can end up fitted to the text.
- **Twin references break G5.** "International purchases are not covered", written in a domestic document, names both values. It is the most natural sentence to write, and it puts both conditions in one document, which is exactly what G5 forbids. Writing rule: a document never names its twin's value, not even to exclude it.
- **Return and warranty in one document:** `Final_Proposal.md:435` names "the return and warranty windows" in one chunk as the same hazard. P3 separates the kinds by document, but nothing stops a return document from stating the warranty length. Consider scanning `policy_kind` as a fourth axis.
- **Filler text:**
  - ≥ 3 chunks needs about 350 words or more per document.
  - Filler shared across documents gives identical chunks, which P4 catches. Identical chunks give identical vectors and exact ties under FLAT, and Redis then decides the order, so rank-1 (the namespace) may not be stable. P4 matters; keep it.
  - Near-identical filler makes rank-1 between twins close to random for a question that names no condition.
  - The writing rules should say how filler is written.

**D. Other**
- **The numeric arm reads each chunk alone** (`decisions.md:75`). If "14 days" and "$45" fall in different chunks, a cached answer that states both is supported by no single chunk and is refused. Chunk borders depend on A. Fix the rule (for example, each term's numbers in one sentence) before writing, never after a run.
- **The region axis and the data card's Ethics line:** `data-card.md:269` says answers that vary by locale bypass the cache. A warranty keyed on where the product was bought is a fixed term, not a personal one. Write it that way, and add one sentence to the data card.
- **Tests and data:** unit tests must use `tmp_path` fixtures (P10). `make verify` does not run `policy-check` (`Makefile:287-295`), so a later edit to a document can break the ≥ 3-chunk rule silently until 3.6.

## 8. If G5 is folded in (open question 7)

I recommend the fold, in its narrow form. One implementation and no mirror is the G3 lesson (`corpus_gate.py:75-83`). It costs roughly 60–100 lines plus tests.

- **`corpus_gate.py`:**
  - Add a pure `check_g5(records)` that reports every offender, as G4 does.
  - Add a loader for whole policy records. `load_corpus_doc_ids` returns ids only (`:123-137`), and `rag.ingest.load_records` stops at the first problem (`:126-128` says why it is not used).
  - Put the condition table in a named constant beside `SIM_FLOOR` (`:61-66`).
  - Add g5 to `criteria = [g3, g4]` (`:490`) and to the `passed` line (`:524`).
  - Update the wording: the "four criteria" docstring table (`:10-17`), `:24-26`, the `--structural-only` help (`:464`), `:499` and "All four criteria pass" (`:557`).
  - Add the G5 counts to the report JSON (`:577-590`).
- **Policy documents only.** At 3.6 the gate reads `data/v1/`, including 152 products, and a product record may say "new" and "renewed". I could not verify this: `data/` is unreadable in this session, and the selector has no renewed filter.
- **Define "before / after" from the corpus** (`data-card.md:263`) so neither number is made up. Before = the split families that have both values (5 here). After = the documents naming two values of one axis, which must be 0.
- **`make policy-check` imports `check_g5`; it does not call the gate's CLI.** The CLI needs a workload even with `--structural-only` (`corpus_gate.py:477-479`, `Makefile:409-413`), none exists before 3.4, and the gate reads `data/v1` (`:470`), not `data/policies-v1`.
- **Tests:** add to `test_corpus_gate.py`: a pass, a fail that names both values, every offender reported, and products ignored. No existing test asserts "four", so nothing is changed, only added.
- **Docs and Makefile:**
  - Makefile comments `:399-404` ("all four criteria", "G1..G4", "G3/G4 only").
  - `data-card.md:199-203` ("all four criteria", "G5 is not implemented yet") needs rewriting; `:211-213` already lists G5 as structural.
  - `architecture.md:82` ("G5 NOT BUILT") and `:241` change. `:222` already says "G1–G5", which is wrong today and becomes right after the fold.
  - In `super-plan.md`, 3.5 closes with 3.3, and its Done-when "names both" (`:414`) is the same check as P2.

## 9. Smallest change

The spec is close to minimal. Four ways to keep it small:

1. **Drop shipping** (open question 1), and record the drop. The pool has no shipping tag, shipping has no condition axis, and it is close to dynamic content. `data-card.md:76` still lists shipping.
2. **Add no further fields.** The two new fields repeat what the `doc_id` says. Add one P3 check that the `doc_id` is built from (`policy_kind`, `category`, `condition`) by one rule, so the two can never disagree.
3. **Fold G5 in the narrow form:** one pure function and one constant in `corpus_gate.py`, and no new gate CLI mode.
4. **Do not pin `llama-index-core` in `rag/` here.** Record the version, and carry the pin to 3.6.

**Invalidates:** none, because no runs exist yet (`experiments/results/` holds only `.gitkeep`). `v1` is not frozen, and `data/dev-v0/` is not touched.

> **Required phases:** impact · experiment · implementation. The contract phase is not required. Scope L, so design → opus design-review → plan still apply.
