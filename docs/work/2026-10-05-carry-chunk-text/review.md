# Design review — carry-chunk-text

**Reviewer:** `design-reviewer` (opus), 2026-10-05, reviewing `design.md` revision 2.

**Method:** the review was read-only. No model was loaded and Ollama was never called. Three read-only probes were run:
- `redis-cli` reads on DB 0;
- `go test -count=1 -v -run TestSeam ./internal/ragclient/`, which runs the unit package only and opens no network connection;
- `import rag.server` with Redis and Ollama pointed at a closed port.

**CONFIRMED** means checked against the code, against the installed LlamaIndex source (llama-index-core 0.14.23, llama-index-vector-stores-redis 0.8.0), or by a probe. **PLAUSIBLE** means reasoned only. The reviewer has no write tool, so Claude saved this report as returned.

**Verdict: sound with changes. No blocker. D1-a is approved.**

- **The production change is right, and it is the smallest one.**
  - Alignment holds by construction on every path through `retrieve()`.
  - `c.text` is the schema `text` field.
  - The hash holds no second copy of the text that could drift: `_node_content` is written with its text removed.
  - The oracle reads the same hash Redis returned for each id. All 44 keys were checked.
- **The weak point is the check that certifies the seam, not the seam.** As designed, `make seam-check` can print PASS without running the test (S1, confirmed today). It can also pass against a single listener that is running code older than the working tree (S2). Both produce a check that proves nothing, which is exactly what this task exists to rule out.
- **On D1: keep D1-a.** The stated reason reaches the right conclusion by an incomplete argument:
  - D1-b would need the contract phase.
  - Before 1.3 lands, D1-b would not even be loud in §H: F-E would record a stale-server run as provenance refusals.
  - What D1-a lacks is a hand-off that 2.1 will actually read (S3).

## Findings, most severe first

| # | Sev. | Finding | Check | Proposed resolution (author decides) |
| :---: | :---: | :--- | :---: | :--- |
| **S1** | should-fix | **`make seam-check` can pass without running the test.**<br>• `go test -run TestSeam` with no matching test prints `testing: warning: no tests to run`, then `PASS`, then `ok … [no tests to run]`, and exits 0. This was run today against `./internal/ragclient/`, where `TestSeam` does not exist yet. A renamed test function or a drifted `-run` pattern gives the same output on the evidence run.<br>• A skip also exits 0. The test skips when `RAG_SEAM_ADDR` is unset, so a misspelled variable in the recipe yields `--- SKIP` and exit 0. §3d says "`-v` makes a skip visible", but visible is not failing. The evidence file would then hold a skip, recorded as acceptance 6.<br>• F4 closes "set but unreachable, so it skips" inside the test. Nothing closes "the variable never reached the test", which is a failure of the target itself | CONFIRMED (probe) | The recipe runs under `set -o pipefail` and tees the output to the evidence file. It fails unless:<br>• it finds `--- PASS: TestSeam`, plus one `--- PASS` line for each of L1, L2, L3 and the shift subtest;<br>• and it finds none of `--- SKIP`, `no tests to run` or `(cached)` |
| **S2** | should-fix | **The single-listener guard detects an ambiguous port, not a stale process.**<br>• F1's own row names a case the guard does not close: *"a stale server from another post-1.4 build passes it for the wrong code"*. A `make dev` started before the last edit to `server.py` or `retrieve.py` is exactly one listener, and it runs old code.<br>• The mutation runs depend on the same thing. M1–M3 count as "caught by 3c" only if the server is restarted after each edit. In the silent direction: an edit made after a passing server start is never seen by a re-run.<br>• The guard also pulls `rag-server-reuseport` (`super-plan.md:132-135`) into this task's evidence, although the task does not need `:50051` at all | CONFIRMED by reading. `config.py:47` makes the address configurable (`RAG_GRPC_ADDR`), and `Makefile:122-126` already uses the start-and-trap pattern | **The target owns the server:**<br>1. Check that a private port is free (for example `127.0.0.1:50052`).<br>2. Start `python3 -m rag.server` from the working tree, with `RAG_GRPC_ADDR` set to that port and the same `REDIS_URL` the oracle reads.<br>3. Wait for the listener, with a timeout.<br>4. Run the test against it.<br>5. Kill the server on exit (`trap`).<br>The evidence then certifies the code in the tree, every mutation run restarts itself, and the dev stack on `:50051` is untouched. Keep the `:50051` count as an informational line for `rag-server-reuseport`, not as a gate |
| **S3** | should-fix | **D1-a's hand-off is recorded where 2.1 will not read it.**<br>• D1-a is safe only if 2.1 treats `Texts == nil && len(ChunkIDs) > 0` as a condition of its own. It must be neither `SUPPORT` nor the gate-off `null` signature (`interfaces.md:486-487`).<br>• The obligation is written only in this trail's `approvals.md` and in design §6. The author of 2.1 will read super-plan's 2.1 row and the `RetrieveResult` declaration they are about to consume, and Edit 2's comment there says only "nil when the service sent none".<br>• An empty retrieval also yields `Texts == nil`. So 2.1 has to key on `len(ChunkIDs) > 0`, and nothing tells it that | CONFIRMED by reading | 1. Edit 2's comment on `Texts` states the obligation: nil with non-empty `ChunkIDs` means the service sent no evidence (for example, a pre-1.4 server). Such a request must not be scored, must not be refused as SUPPORT, and must not be logged as gate-off.<br>2. At `/done`, `super-plan.md:164` gains the same sentence in 2.1's row, not only the ✅ on 1.4.<br>3. `approvals.md` "Open" gains one line: `rag-server-reuseport` should close before 2.1's live reproduction and before any Phase 7 run |
| **S4** | should-fix | **The mutation table tests the code, but not the guards the design relies on.**<br>• No row shows that `-count=1`, the Fatal-not-Skip rule, or S1's output check ever fires. Each is a one-line edit away from a vacuous pass.<br>• **M3 is in the wrong file.** `server.py` holds `RetrievedChunk`s, not nodes, so `get_content(MetadataMode.ALL)` cannot be written there. M3 is a mutation of `_to_chunks` (`retrieve.py:69`).<br>• **`MetadataMode.LLM` and `EMBED` are equivalent mutants.** Ingest excludes every metadata key from both (`ingest.py:88-89`, persisted in `_node_content`, checked on a live key). Both therefore return the raw text, and 3c is right to pass them. Only `ALL` changes the text.<br>• 3b's "aligned" row catches a sort or a reverse in `ragclient` only if its fixture is neither sorted nor symmetric | CONFIRMED | Add three target mutations to `evidence/mutations.txt`:<br>• **T1:** run the target twice. The second run must still show the tests executing, with no `(cached)`.<br>• **T2:** run the test with `RAG_SEAM_ADDR` pointed at a closed port. It must exit non-zero, not skip.<br>• **T3:** rename the test function. The target must exit non-zero (S1).<br>Move M3 to `retrieve.py:_to_chunks` with `MetadataMode.ALL`, and record LLM and EMBED as equivalent mutants. 3b's aligned fixture is in non-sorted, non-palindromic order |
| **S5** | should-fix | **F4c is narrower than "not closable inside `verify`", and its silent part can be checked offline.** F4c has three parts:<br>• **(b) The legacy branch sets `text=""`.** This cannot reach `texts`. The legacy branch builds a `TextNode` with no metadata (`base.py:788-797`), so `_to_chunks` raises `KeyError` on `metadata["chunk_id"]` first. That is loud, and it takes the existing retrieve-failure path.<br>• **(c) `text` drops out of `return_fields`.** This yields `""`, not stale text. `_node_content` is written with `remove_text=True` (`base.py:344-345`), and the live key holds `text: ''`, so the fallback at `base.py:785` returns empty. 3c step 2 catches it whenever 3c runs.<br>• **(a) The `get_content` default changes.** This is the silent part. If the default became `ALL`, every `texts[i]` would carry `doc_id`, `title`, `category` and the other metadata tokens. 2.1's `S_lex` would count them as evidence, which inflates support and causes silent false admits. `pyproject.toml` pins only `llama-index-core>=0.11` | CONFIRMED (source, live key) | Add one offline pytest in a new file, with no production change. It passes a `TextNode` with non-empty metadata, wrapped in `NodeWithScore`, through `_to_chunks`, and asserts that `text` equals the raw text. Restate F4c as part (c) only: it needs the live stack, and 3c step 2 catches it |
| N1 | nit | **L2's premise is reasoned, but cited as if a test pinned it.**<br>• §3c says `test_retrieve_scoping.py:67-84` "pins this pair as one where the product's own chunk does not rank naturally". It does not. That test asserts only that the scoped result has no kitchen chunk (`:78`) and the unscoped one has one (`:84`).<br>• The premise is likely true: `product-laptops-02#chunk-0` contains no power or watt term, and 11 of the 44 chunks do (read today). But it is unmeasured.<br>• Expect L2 to be one chunk long. If L1's five results are all other products, `_drop_other_products` empties the list and the splice leaves `[laptops-02]` | PLAUSIBLE | Correct the citation. U2 stands as written. Optionally issue L1 twice and assert identical `chunk_ids` (U7), so "absent from L1" does not rest on an untested assumption that the Ollama query embedding is bit-identical across calls |
| N2 | nit | **Acceptance 5's `git diff --exit-code` cannot see untracked files.** `harness_test.go` and `ask_test.go` are untracked today. If 1.2 is committed only in part, an edit to an untracked file passes the check | CONFIRMED (`git status`) | Use `test -z "$(git status --porcelain -- gateway/internal/httpapi/)"` |
| N3 | nit | **`lsof` counts lines, not listeners.** It also sees only this user's processes without sudo | CONFIRMED | Moot under S2. If the check is kept, count `lsof -t … \| sort -u` |
| N4 | nit | **The first call has a cold load.** The first `Retrieve` loads `nomic-embed-text`, and the Python embed timeout is 60 s (`embedding.py:29`). If the test's deadline is shorter, a cold load reads as a seam fault | PLAUSIBLE | Use a context deadline above 60 s, and a failure message that names the cold load |
| N5 | nit | **F6 overstates the invalid-UTF-8 path.** A Python `str` reaches Redis only through redis-py's strict UTF-8 encoder. So a lone surrogate from a JSON `\ud800` escape fails `make ingest` before any `Retrieve` can see it | PLAUSIBLE (redis-py's default `encoding_errors="strict"` was not checked in source) | Move U5 to 3.1, as "the builder must not emit it", rather than as a per-query MISS |
| N6 | nit | **A sentence in §2 is wrong as written.** §2 says "No path builds `texts` from a second query", but the splice *is* a second query (`retrieve.py:116`). Alignment holds because each spliced node carries its own id and text in one object, built by the same `_extract_node_and_score` with the same return fields | CONFIRMED | Say that instead |

## D1: the reviewer's ruling

**D1-a is approved for this task.** The recommendation reaches the right conclusion. Three corrections to its argument follow, and one condition.

1. **D1-b would need the contract phase.**
   - §B (`interfaces.md:209-210`) makes "absent entirely" a valid state.
   - The v0.9 note (`interfaces.md:44`) gives "an absent `texts` is today's behaviour exactly" as the reason the change is additive.
   - Rejecting absence at the only client changes what a frozen sentence means, even though no byte on the wire changes. `approvals.md` lists "contract: if §B/§D".
   - The spec declares no contract change, so D1-b falls outside this task by the task's own terms. That alone settles it here.
2. **Before 1.3, D1-b is less loud than claimed.** A retrieve error leaves `retrieved == nil`, with two consequences:
   - **On a banded request.** When the nearest entry clears τ, `tryTier2` sets `EnteredBand` before its nil check (`cascade.go:106-112`). The record then says `entered_band: true` and `source_overlap: 0`, and logs the similarity-only counterfactual as MISS (`handler.go:284-307`). This is F-E.
   - **On the miss path.** `retrievedIDs` is nil, so `Answer` re-embeds the query inside the permit (`handler.go:388-409`, `server.py:31-36`). That adds about 18 ms to `t_generate_ms`.
   - So a stale server under D1-b produces a visible collapse of Tier-2 hits, but the §H records attribute it to provenance. D1-b moves the misattribution; it does not remove it.
3. **Strictness per request in `ragclient` is the wrong layer for a fault that belongs to one process.** A stale server is a property of the connection, not of a request. Two things close it:
   - **A run that owns its server.** This is S2's pattern, which `rag-server-reuseport` would extend to `make dev` and `make measure`.
   - **2.1 counting the condition.** The gateway's own multiplexed connection is the only vantage point that certifies the gateway's instance. 2.1 can count `Texts == nil && len(ChunkIDs) > 0` as a distinct condition, which gives that certification without narrowing §B. This is what D1-b would have been good for, and it belongs to 2.1.
4. **Condition: S3.** Without a hand-off in the code and in super-plan's 2.1 row, D1-a stays safe only as long as someone remembers it.

**On "the gateway dials once and multiplexes":** this is correct, and slightly worse than stated.
- A gRPC client reconnects after a transport failure. On a port shared through `SO_REUSEPORT`, one run can therefore move between instances and be only *partly* without texts.
- Which listener macOS hands a new connection to is not established here.
- This is PLAUSIBLE. It strengthens the case for closing `rag-server-reuseport` before 2.1, not the case for D1-b.

## Unknowns

| # | Status |
| :---: | :--- |
| U1 | **Settled by reading, and stronger than the design claims.** The chain is:<br>• `NodeWithScore.get_content` defaults to `NONE` (`schema.py:1087-1088`);<br>• `TextNode` then returns `self.text` (`:810-814`);<br>• `self.text` is set from the `text` field (`base.py:785`).<br>The live key's `_node_content` holds `text: ''`, so there is no second copy that could diverge. 3c still verifies it byte for byte |
| U2 | Stands. See N1 |
| U3 | **Settled.**<br>• `import rag.server` succeeds in 1.6 s with `REDIS_URL` and `OLLAMA_BASE_URL` pointed at `127.0.0.1:1`.<br>• Module level only constructs `httpx.Client` objects (`embedding.py:24`, `generate.py:22`), and they do not connect.<br>• llama-index-core's NLTK check is lazy (`utils.py:104-135`), and its data is cached.<br>• The monkeypatch target is right: `server.py:17` calls `retrieve.retrieve` through the module |
| U4 | Today: no listener on `:50051`, and no `rag.server` process. Moot under S2 |
| U5 | See N5 |
| U6 | **Settled.**<br>• DB 0 holds 44 `corpus::*` keys, one chunk per document.<br>• For all 44, the key suffix equals the `chunk_id` field, which equals the `id` field (`ingest.py:84-85`).<br>• So `HGET corpus::<chunk_ids[i]> text` reads the hash that FT.SEARCH returned for that id |
| U7 (new) | Is the Ollama query embedding bit-identical across two calls, so that L1 and L2 see the same unscoped ranking? N1's double L1 settles it |

## Checked and found sound

- **Alignment holds by construction on every path** (`retrieve.py:128-132`):
  - `_drop_other_products` filters node objects, so each text travels with its own metadata.
  - `_ensure_own_chunk` prepends a node from a second, filtered FT.SEARCH, built by the same `_extract_node_and_score` with the same `return_fields`.
  - `_to_chunks` runs once, on the final list.
- **The oracle is independent of the code.** It shares data with the server, not code.
  - It certifies alignment at the seam, which `interfaces.md:212` defines as the hash's `text` field. It does not certify that the corpus is correct.
  - A wrong DB, a wrong instance, or a wrong key format returns `redis.Nil`, which fails.
- **The shift test works.** With two or more pairwise-distinct texts, a rotation mismatches at every index. Both M6 and an order-insensitive checker are caught.
- **The measured path barely moves.**
  - The protobuf backend is upb, the one `impact.md` benchmarked.
  - FT.SEARCH already returns `text` (`base.py:177-182`), and `_to_chunks` already computes it.
  - Edit 1 therefore adds serialisation only: no Redis read and no round-trip.
- **Nothing measured or frozen changes.**
  - No §H field, frozen value, or metric definition moves.
  - `ErrTextsMisaligned` cannot be reached from the in-tree server.
  - No model on the hit path, no read of the query text, and no cut scope comes back.
- **Layering:** `go list -deps` without `-test` excludes the test-only go-redis import, so impact.md's grep is the right check.
- **No smaller design exists.** L3 adds a multi-paragraph byte-equality case on the same code path, and it is optional.
- **Two corrections to `impact.md`, for the record.** Neither changes the design:
  - S4/S6's legacy-branch `""` cannot reach `texts` (S5 (b)).
  - S4's `_node_content` fallback cannot return stale text, because `_node_content` holds none (S5 (c)).

---

**Summary:** 0 blocking, 5 should-fix (S1–S5), 6 nits (N1–N6).

**D1:** D1-a is approved, on the condition that S3 is applied: the nil-with-chunk-ids obligation goes into the `Texts` doc comment and into super-plan's 2.1 row. D1-b would need the contract phase. It is also less loud than claimed before 1.3, because F-E would record a stale server as provenance refusals. And it puts a fault that belongs to one process in the per-request layer. The stale-server hazard is closed by a run that owns its server, together with 2.1 counting nil texts as a distinct condition.

**Most urgent:** S1 and S2. Both are vacuous-pass paths in `make seam-check`, the one thing this task delivers. S1 was confirmed today: `go test -run TestSeam` with no matching test exits 0 and prints PASS.

## Resolutions

*Added by Claude after the review. Every should-fix and nit is applied in `design.md` revision 3,
`spec.md` and `plan.md`. Each is a default the author can reverse (`approvals.md`).*

| # | Resolution | Where |
| :---: | :--- | :--- |
| S1 | Applied. The target tees to the evidence file under `pipefail` and fails unless the four `--- PASS` lines are present and `--- SKIP`, `no tests to run` and `(cached)` are absent | design §3d; spec acc. 6; plan §4 |
| S2 | Applied. The target owns its server: a private port (`127.0.0.1:50052`), started from the working tree, waited for, killed on exit. The `:50051` count becomes an informational line | design §3d, §5 F1; spec acc. 6; plan §4–§6 |
| S3 | Applied. The obligation goes into the `Texts` doc comment (Edit 2) and, at `/done`, into super-plan's 2.1 row. `rag-server-reuseport` is added to "Open" | design §2, §6; plan §3, §7; approvals |
| S4 | Applied. T1–T3 added. M3 moved to `retrieve.py:_to_chunks` with `MetadataMode.ALL`; LLM and EMBED recorded as equivalent mutants. 3b's aligned fixture is non-sorted and non-palindromic | design §3b, §4 |
| S5 | Applied. New offline pytest on `_to_chunks` with non-empty metadata. F4c restated as part (c) only | design §3a, §5; spec acc. 1; plan §2 |
| N1 | Applied. Citation corrected; L1 issued twice and compared (U7); L2 may be one chunk long | design §3c, §7 |
| N2 | Applied. Acceptance 5 uses `git status --porcelain` | spec acc. 5; plan §2 |
| N3 | Moot under S2. The informational `:50051` line counts unique PIDs | design §3d |
| N4 | Applied. The test's context deadline is 90 s, and the failure message names the cold load | design §3c |
| N5 | Applied. U5 handed to 3.1 as "the builder must not emit it" | design §5 F6, §7 |
| N6 | Applied. §2's sentence rewritten | design §2 |

---

# Implementation review — `/ai-review`, 2026-10-05

**Reviewer:** `contract-reviewer`, routed because the diff touches a §B wire field
(`RetrieveResponse.texts`). `design-reviewer` does not apply after implementation. Scope: `git diff`
(`server.py`, `ragclient/retrieve.go`, `Makefile`) plus the three new test files. Read-only: no
`make seam-check`, no server, no model.

**Verdict: no findings. The diff conforms to `interfaces.md` §B**, including the positional-alignment
invariant and the `text` schema field.

| Checked | Result |
| :--- | :--- |
| Frozen values | None changed |
| Provenance on the wire | `chunk_ids`, `scores`, `dataset_epoch` built from the same `chunks` list as before; `texts` from that list too, so aligned by construction and rank order untouched. `texts = 4` already in the `.proto` and both stubs |
| `text` schema field | `_to_chunks` takes `n.get_content()` from the same node as the chunk id; the live test compares it with the Redis `text` field |
| `ragclient` length rule | Absent or exactly `len(chunk_ids)`; anything else is `ErrTextsMisaligned`, matching "no partial population" |
| Redis writes / eviction regions | `seam_live_test.go` issues only `Ping` and `HGet`, refuses any DB but 0, and fails on `redis.Nil`. Nothing touches `dep:*` or `entry:*` |
| Import graph | `go list -deps ./internal/ragclient \| grep -i redis` is empty; go-redis only in `ragclient_test` |
| §H and computed numbers | No logged field or computation changed; `Texts` has no reader yet |
| Runs | `go vet`, `go test ./internal/ragclient` (live test skipped), `pytest rag/tests/test_retrieve_texts.py` (3) pass |

Examined and not findings: `corpusKeyPrefix = "corpus::"` equals `CORPUS_KEY_PREFIX` plus the `:`
`retrieve.py` adds; `texts` and `chunk_ids` stay aligned after a splice; an empty retrieval yields a
legal `Texts == nil`.

## Found by the mutation run, not by a reviewer — resolved

Recorded here so every implementation finding sits in one place (`design.md` §4, `evidence/mutations.txt`).

| # | Finding | Check | Resolution |
| :---: | :--- | :---: | :--- |
| I1 | `retrieve_texts_test.go` handed `tc.texts` to the fake, and `GetTexts()` returns that slice, so a client that reorders `Texts` in place rewrote the expected values: mutations M9a/M9b passed the unit test. Offline-only gap; `make seam-check` caught M9a | CONFIRMED (mutation run 1) | **Fixed.** The fake receives `slices.Clone` of ids and texts. Run 2: M9a/M9b caught |
| I2 | Mutation M5 deleted the length-check `case`, leaving `fmt` unused, so the compiler failed and the run said nothing about the test | CONFIRMED (mutation run 1) | **Fixed** in `mutate.py`: M5 disables the case (`case false && …`). Run 2: caught by the short, long and texts-without-ids rows |

**Unresolved findings: none.** `/done` is not blocked by this review.
