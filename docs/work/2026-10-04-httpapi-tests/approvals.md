# Approvals — httpapi-tests

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes — `/approve impact`. **Invalidates: nothing.** No frozen value is touched and no `run_id` exists; the one source change is type-only, 2.05 ns per call either way (`impact.md` §2, "Invalidates") | 2026-10-04 | none |
| contract       | if §B/§D — **not required.** No §A–§H surface, `.proto` or §D schema changes (`impact.md` §5) | | | |
| experiment     | if measured — **not required.** Nothing about what is measured or counted changes; the hit path changes in type only (`impact.md` §2, §6) | | | |
| implementation | always   | yes — `/approve implementation`. Impact approved; contract and experiment not required; open items 1, 2 and 4 decided | 2026-10-04 | none |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-04 | Open item 1.2 as `httpapi-tests` at scope **L**, after committing the dated-folder change | "ok làm đi" — to *"commit … rồi mở `/task httpapi-tests L`"* | none |
| 2026-10-04 | **Item 1, U5, the coalescing seam: option (a).** Add an exported, read-only `coalesce.Group.Waiters(key)` that wraps the existing `waiters`. The coalescing test waits on `Waiters(t1Key) == 3` before releasing the leader. `Waiters` is never called on the request path and its value is never logged (`impact.md` §6) | Chose *"Thêm Waiters(key) (Recommended)"*, asked to *"resolve từng cái 1,2,4"* | none |
| 2026-10-04 | **Item 2, the tests 1.3 may change.** Item 1.3 may change exactly `TestTier2RefusesAnEntryFromAnotherNamespace` and `TestBelowTauDoesNotEnterTheBand`, each under a decision recorded in 1.3's own trail, for example whether a refusal's `similarity` may become `null` and what that does to §A's lookalike-trap demonstration. **If 1.3 breaks any other test of this task, 1.3 is wrong.** It may not change the `cache` outcome or the HTTP status of either test (`impact.md` §7) | Chose *"Cho 1.3 sửa đúng 2 test này (Recommended)"* | none |
| 2026-10-04 | **Item 4, where the immutability rule applies.**<br>• `harness_test.go` (the fakes and helpers) is **scaffolding**. It may gain behaviour for a new seam, such as a `cacheStore` method that Phase 4 adds, with a note in the task that adds it.<br>• It may **not** loosen a strict check: `TopK != 0` → error, unknown embed input → 500, aligned `texts`, `Answer` dropping its last source, equal epochs. Loosening one counts as changing an assertion.<br>• The assertions in `ask_test.go` fall under the normal rule: changed only after an RCA, with the author's confirmation | Chose *"Tách harness và assertion (Recommended)"* | none |

**For 1.3's spec, not decided here.** Existing tests outside this task assert fields that 1.3
retires: `telemetry/evallog_test.go:69` (the `similarity_only_decision` key) and
`reuse/rule_test.go:99-100`, `:121-135` and `:182-213` (`SimilarityOnly`, `TauHigh`). Changing them
is 1.3's decision, recorded in 1.3's trail (`review.md` N6, `impact.md` §7).

## Open — needs the author

Items 1, 2 and 4 are decided above. These two do not block implementation.

- **Item 3, the order of the follow-up bugfixes** (`spec.md`, F-A to F-J). **Recommended:**
  - **Before 1.6 and before any Phase 7 run:** F-A (miscounts most abandonments) and F-F (cheap,
    although avoidable by stopping the load before SIGTERM). F-D's client-side 200 is also worth
    closing then.
  - **In 1.3's spec:** state whether 1.3 removes F-E and F-G, since both come from the unfiltered
    phase.
  - **Afterwards:** F-B, F-C, F-H, F-J.
  - **F-I** is an input to Phase 4's design, not a bugfix.
- **Item 5, F-K: the served Tier-2 rule is similarity ∧ namespace, while the thesis claims four
  conjuncts** (`spec.md`). θ reaches only the logged counterfactual, `ConfigID` selects nothing,
  and `decisions.md` records no decision about either. This is **above this task**, and does not
  block it, because the fixtures satisfy all four conjuncts. It does need an owner:
  - a new ADR that records the namespace rule as the claim, or
  - an item, probably in Phase 2, beside the support gate, that puts θ into the served decision
    and makes `ConfigID` select the configuration.

  Until one of those exists, item 6.1's θ sweep would move no served decision.

## Taken by Claude as a default, open to reversal

- **An interface for the cache, not real Redis.** This is forced: RediSearch indexes only DB 0,
  which the dev cache occupies (`design.md` §2).
- **RAG and the embedder faked at the wire, behind the real clients.** That is what made F-A
  visible. An interface-level fake would have returned `context.Canceled` directly and hidden it.
- **Malformed requests (405 and 400): the response is asserted, the eval record is not.** Whether
  such a request counts as a request in §H is not this task's decision.
