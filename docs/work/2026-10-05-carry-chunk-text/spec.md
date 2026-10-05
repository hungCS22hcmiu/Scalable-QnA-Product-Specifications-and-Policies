# Spec — carry-chunk-text

**Scope:** L · **Opened:** 2026-10-05 · **Phase:** 1, item **1.4**

## The change in one sentence

Make the Python `Retrieve` handler populate `RetrieveResponse.texts` with each returned chunk's
text, positionally aligned with `chunk_ids`, and make `ragclient.Retrieve` carry that array to the
gateway as `RetrieveResult.Texts`. Prove the alignment with an end-to-end check whose oracle does
not depend on either side's code.

## What it serves

- **Phase 1, item 1.4** (`super-plan.md`): *"An end-to-end test asserts `texts[i]` is the text of
  `chunk_ids[i]`, and a deliberately shifted array fails it."*
- **Exit-criterion clause discharged:** *"`texts` flows Python → Go with positional alignment
  asserted."*
- **Discharges:** **C1**. The support gate (Phase 2, item 2.1) compares a cached answer against
  chunk text, and the gateway has never held chunk text. `contracts/requirements.md` is still
  empty, so there is no FR/NFR/RR ID to cite yet.
- **Unblocks:** 2.1 (lexical arm). Its "Unblocked when" cell names 1.4.

## Why scope L

The author passed M, then chose L when asked on 2026-10-05 (`approvals.md`, Human decisions).
Three reasons:

1. **It is on the measured path.** `Retrieve` runs concurrently with the embedding on every Tier-1
   miss (`handler.go:260-271`), so a heavier response is inside `t_overlap_ms` and inside Tier-2
   μ_hit.
2. **Its characteristic failure is silent.** `interfaces.md:215-219`: *"A `texts` array shifted by
   one scores a cached answer against the WRONG chunk's text and returns a support verdict that is
   wrong with no error raised anywhere."* That is the definition of L in the ladder: *"a silent
   error costs the study rather than an afternoon."*
3. **It is a seam.** `/feature` raises M to L at a seam, and this is the gRPC seam.

What keeps it from being larger: **no contract changes.** `texts = 4` is already in
`contracts/rag/v1/rag.proto:51` and in both generated stubs (`rag_pb2.py`, `rag.pb.go:113`).
`interfaces.md` §B was frozen at v0.9 with this field in it. This task conforms to the contract.
It does not amend it.

## Current state (2026-10-05)

| Side | File | Today |
| :--- | :--- | :--- |
| Proto | `contracts/rag/v1/rag.proto:41-51` | `repeated string texts = 4`, documented as aligned |
| Python | `rag/src/rag/server.py:16-22` | `RetrieveResponse` built with `chunk_ids`, `scores`, `dataset_epoch`. **No `texts`.** `RetrievedChunk.text` is already in hand |
| Python | `rag/src/rag/retrieve.py:64-74` | `_to_chunks` sets `text = n.get_content()`. LlamaIndex sets `node.text` from the schema's `text` field (`llama_index/vector_stores/redis/base.py:785`), which is in the default return fields (`:177-181`) |
| Go | `gateway/internal/ragclient/retrieve.go:13-17, :32-36` | `RetrieveResult` has no `Texts`. `resp.GetTexts()` is never read |
| Go test harness | `gateway/internal/httpapi/harness_test.go:490-503` | The wire fake **already** sends aligned `texts` (built for 1.4 by 1.2) |

## Acceptance — each is a check that can be run

*Revised after `impact.md` (its "Corrections" table, items 1–6) and `review.md` (S1, S2, S5, N2).*

0. **Precondition.** Item 1.2's work is committed before implementation starts, so acceptance 5
   has a base to diff against (`impact.md`, "Precondition, not a phase").
1. **Python, unit.** A pytest test calls `RagServicer.Retrieve` with `retrieve.retrieve` replaced
   by a fixture of ≥ 3 chunks whose texts are distinct and not derivable from their IDs. It asserts
   the fake was called, `len(texts) == len(chunk_ids)`, and `texts[i] == fixture_text[chunk_ids[i]]`
   for every `i`. A second offline test passes a `TextNode` with non-empty metadata through
   `_to_chunks` and asserts the raw text comes back (`review.md` S5). Both run without Redis or
   Ollama.
2. **Go, unit.** New `ragclient` tests, in a **new file** (`retrieve_test.go` stays byte-identical:
   tests are immutable). An aligned response yields `RetrieveResult.Texts` equal to the wire array.
   An absent `texts` yields `nil` with no error. A **partial** population returns the sentinel
   `ErrTextsMisaligned`, asserted with `errors.Is`, in **both** directions
   (`len(texts) < len(chunk_ids)` and `>`) and with `chunk_ids` empty but `texts` not
   (`interfaces.md:209-210`: *"there is no partial population"*).
3. **End to end, Python → Go, live.** A Go test dials the **running** Python server through the
   real `ragclient` and checks every `texts[i]` against an oracle independent of both sides: the
   schema `text` field of `corpus::<chunk_ids[i]>`, read directly from Redis (`HGet(...).Result()`;
   `redis.Nil` fails). Before any loop it asserts `len(texts) == len(chunk_ids) ≥ 1` and that every
   element is non-empty, so an absent array **fails**. It covers one unscoped query and one scoped
   query on which the `_ensure_own_chunk` splice (`retrieve.py:105-119`) is **shown to fire**: the
   product's chunk is absent from the unscoped result for the same query and at index 0 of the
   scoped one.
4. **The shift is caught.** The same alignment checker, run with `texts` rotated by one, **fails**.
   It runs on the **unscoped** response, after asserting `len ≥ 2` and that the texts are pairwise
   distinct, so the rotation cannot pass by accident.
5. **Nothing else moves.** `make verify` passes, and
   `test -z "$(git status --porcelain -- gateway/internal/httpapi/)"` holds; `git diff` alone cannot
   see an untracked file (`review.md` N2). The harness is scaffolding, and per
   the 1.2 trail (`approvals.md`, item 4) it may not loosen its aligned-`texts` check.
6. **Evidence.** One run of `make seam-check` is saved as `evidence/seam-check.txt`. The target
   **starts its own `rag.server` from the working tree** on a private port and kills it on exit
   (`review.md` S2), runs `go test -count=1 -v`, prints the memory-pressure level first, and
   **fails unless** the log shows `--- PASS` for `TestSeam` and its subtests `L1`, `L2`, `L3` and
   `shift`, with no `--- SKIP`, `no tests to run` or `(cached)` (`review.md` S1). Enabled and
   unreachable is a failure, never a skip.
7. **Mutations.** `evidence/mutations.txt` records M1–M9 and T1–T4 (`design.md` §4), each caught.

## Out of scope

- **Consuming `texts`.** No code in `httpapi/` or `reuse/` reads `Texts`. The support gate is 2.1.
- **What the gate does when `texts` is absent.** That is 2.1's to decide. This task records the
  question and two traps for 2.1 (`impact.md` §7): refusing with `refusal_cause: SUPPORT` credits
  the gate with refusals it never computed, and logging `support_lex: null` on the gate-on arm
  writes the signature §H reserves for the gate-off arm.
- **Any change to the contract**: `interfaces.md`, the `.proto`, or §H. `texts` is not logged.
- **`Answer`.** It reads chunk text itself (`fetch_by_ids`) and is unchanged.
- **`scores` alignment.** It is the same kind of invariant, but item 1.4 names only `texts`.
- **The stale-server hazard** (`rag-server-reuseport`, `super-plan.md:132-135`). This task's
  evidence sidesteps it by owning its server, but fixing it for `make dev` and `make measure` stays
  the author's open decision. It should close before 2.1's live reproduction and Phase 7.
- **Measuring the payload's effect on μ_hit.** Phase 7 measures μ_hit with `texts` on, because the
  measured system is the one that carries them.
