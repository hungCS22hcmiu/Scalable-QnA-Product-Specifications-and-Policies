# Impact — lexical support arm (item 2.1)

**Lead risk: this item does not change a frozen value, but it *creates* one.** The stop-word list,
the ≥3-character rule and the tokeniser's normalisation (case folding, punctuation, Unicode) are
*part of S_lex's definition*. Once any run logs `support_lex`, editing that list silently rescales
every score against a `τ_s` that cannot move to compensate (pinned, never swept). Pin the list and
the normalisation rule **in-repo, as a literal, with its source**, in this task's `approvals.md`
now — 2.2/2.3 inherit it.

| Package | Touch | Note |
| :--- | :--- | :--- |
| `gateway/internal/reuse/` | new file `support.go` + `support_test.go` | the only package touched |
| `gateway/internal/{httpapi,telemetry,ragclient,cache}` | none | out of scope per `spec.md` |
| `docs/contracts/interfaces.md` | none | fields already at v0.9 |

**1. Packages / layering.** `reuse/` only; no new import edge. **A new file, not an edit to
`rule.go`/`lane.go`** — those own the chunk-ID conjuncts; this is the text conjunct.
⚠️ The signature must take `(answer string, texts, chunkIDs []string)`, **never
`*ragclient.RetrieveResult`**: `ragclient` imports gRPC, and `reuse/` must stay infrastructure-free
(`architecture.md` §2). The nil-`Texts` rule (`ragclient/retrieve.go:24-33`) therefore needs a
**tri-state return** (`scored bool` alongside the score) so the caller can count the condition —
counting is not `reuse/`'s (no state, no I/O).

**2. Frozen values / runs.** `τ_s = 0.6` is already frozen as **inherited state**
(`decisions.md:68`) — **no new ADR for the pin**. `cascade.go:88-130` calls only `Classify`,
`Namespace`, `DecideLane`, `Decide`; the served decision is untouched. **Invalidates: none — no
runs yet, and no served path changes.** ⚠️ Keep `τ_s` a package **const**, not a `Thresholds`
field — a field invites a `getenvFloat` in `main.go:175` and makes a never-swept value sweepable.

**3. Dropped scope.** No. §12's list is bypass classifier / learned predictor / predictor-gated
invalidation / semantic routing / SSE / HNSW. The gate scores the **cached answer** against **fresh
evidence text**, never the query — the query text is not read at all. The lexical arm is explicitly
the *kept* arm (the numeric arm is droppable).

**4. Dependency.** None required, and none permitted: `go.mod` is grpc/go-redis/protobuf only.
A third-party stop-word module would break §2's stdlib-only rule. Write ~30 words as a Go literal.

**5. Contract.** No. `support_lex` is specified at `interfaces.md:550,600`; nothing wires to it here.

**6. Measurement.** No. `telemetry/` and `experiments/` unchanged; nothing logged, nothing counted.

**7. Hidden couplings.** `doc.go` says "the source-overlap reuse rule and the cascade" — one-line
update. No file lists in the `Makefile` (`test:` is `go test ./...`), no golangci config, all
`Thresholds{}` literals are keyed. ⚠️ **The pinned pair in `lane_test.go:434-497` carries chunk IDs
only — no text.** The new fixture's answer/evidence text must be **lifted from the `dev-v0` chunks
those IDs name** (`policy-returns-electronics#chunk-0`, `policy-warranty#chunk-0`) and recorded as
such, not authored until it passes. Authoring text to clear 0.6 is tuning to make a headline work.
Note `cache/normalize.go` deliberately does **no** stop-word removal, guarded by
`TestNormalizeDoesNotStemOrDropStopwords` — the two lists must not be shared or unified.

> **Required phases:** impact · implementation

## Amendment 2026-10-12 — plan.md step 8b (live check)

Written by the main session, **not** by `impact-analyst`, and made after the author ran
`/approve impact`. The table above says `reuse/` is "the only package touched"; with step 8b that
is no longer exactly true:

| Touch | What | Note |
| :--- | :--- | :--- |
| `gateway/internal/ragclient/support_live_test.go` | new, **test-only**, package `ragclient_test` | adds a test-time edge `ragclient_test → reuse`. `reuse/` still imports nothing, so it stays a leaf and stays falsifiable in isolation (`architecture.md` §2); `ragclient`'s production imports are unchanged. `architecture.md` calls the current graph "an observation, not a rule" |
| `Makefile` | new `support-check` target + `.PHONY` entry | `seam-check`'s recipe is **not** edited; its startup block is copied |

Still true: no served code outside `reuse/` changes, `cascade.go` is untouched, no contract or
telemetry change, no new module dependency (`go-redis` and `grpc` are already in `go.mod`), no
frozen value touched, no run invalidated. The live test is read-only against Redis and is skipped
unless `RAG_SEAM_ADDR` is set, so `make verify` is unaffected.
