---
description: Run this week's "Done when" exit test concretely and report PASS or FAIL
argument-hint: [week number, defaults to current]
---

Prove the weekly exit test — **do not self-report it.** Run the actual checks.

1. Read the **Done when** cell for the week from `docs/time_line.md`. Quote it verbatim.

2. **Decompose it into independently checkable criteria** and run each. Examples:

   | Week | Criterion | How to check it for real |
   | :--- | :--- | :--- |
   | W5 | envelope frozen at green | `experiment-protocol.md` §1.1 budget table has no `TODO(spike)`; ADR-017 status is Decided |
   | W5 | retrieval returns chunk IDs | run the retrieval path on 10 test queries; assert every result carries `{doc_id}#chunk-{n}` |
   | W6 | answer over gRPC with sources | call `Answer`; assert `source_chunk_ids` is non-empty |
   | W6 | Tier-1 hit under 10 ms | same question twice; assert second is `TIER1_HIT` and `latency_ms < 10` |
   | W7 | paraphrase hits, unrelated misses | run both; assert `TIER2_HIT` and `MISS` respectively |
   | W8 | sensitivity gate passes | count pairs with `sim ≥ 0.85 ∧ overlap ≤ 0.2`; assert ≥ ~50 |

3. **Report a table**: criterion → PASS / FAIL / **NOT RUNNABLE YET** (and why).

   A criterion you cannot execute is **not** a pass. Say `NOT RUNNABLE YET` and name what is missing.
   Vacuous passes are the failure mode this command exists to prevent.

4. **Record the result** in `docs/worklog/W<NN>.md` under `**Exit test:**`.

5. If FAIL: state the single smallest thing that would move it to PASS. Per Ground Rule 5 in
   `docs/time_line.md`, next week starts by closing this gate — not by starting new work.
