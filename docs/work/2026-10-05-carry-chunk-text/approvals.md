# Approvals — carry-chunk-text

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes — `/approve impact`. **Invalidates: nothing.** No frozen value is touched and no `run_id` exists; the measured path grows 0.6–1.6 µs per Tier-1 miss, below §H's resolution (`impact.md` §2, "Invalidates") | 2026-10-05 | none |
| contract       | if §B/§D — **not required.** `texts = 4` is §B v0.9 as frozen; no `.proto`, stub, §D or §H change (`impact.md` §5) | | | |
| experiment     | if measured — **not required.** Nothing logged or counted changes; the one timed span (`t_overlap_ms`) grows 0.6–1.6 µs, and no `run_id` exists (`impact.md` §2, §6) | | | |
| implementation | always   | yes — `/approve implementation`. Impact approved; contract and experiment not required; design rev 3 carries every `review.md` finding; D1-a approved on condition S3 | 2026-10-05 | none |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-05 | **Fix the two mutation gaps and rerun** (plan step 6): the new unit test's slice aliasing (M9), and the M5 mutation the compiler caught. The test is new in this task and not yet accepted, so the immutability rule did not apply | Chose *"Fix both, rerun (Recommended)"* | none |
| 2026-10-05 | **Run the live seam check under memory pressure level 2 (urgent)**, beyond the yellow allowed for test runs. It is deterministic pass/fail with no timing cited; `nomic-embed-text` was already resident | Chose *"Run it now under urgent"* | none. Nothing from these runs is a measurement |
| 2026-10-05 | **Approve implementation** against `design.md` revision 3 and `plan.md` | `/approve implementation` | none |
| 2026-10-05 | **Approve the impact analysis** (`impact.md`), after a walk-through of what it says about this task. The two corrections `review.md` made to it (legacy-branch `""` and the `_node_content` fallback cannot reach `texts`) are on record there | `/approve impact` | **No `run_id`**: none exists. The Tier-2 μ_hit ≈ 61 req/s planning figure was taken without `texts`, was never citable, and moves < 0.01 % (`impact.md` §2) |
| 2026-10-05 | **Commit item 1.2 first** (spec acceptance 0). `/verify` green, nothing skipped. Committed as `8d637f7` on a new branch `httpapi-tests`, then fast-forwarded into `main` at the author's request ("merge vào main đi"); the stray 1.1 note in `resolve-f1/approvals.md` was left out | "commit 1.2 trước đi" | none |
| 2026-10-05 | **Scope L, not M.** Opened as `/task carry-chunk-text M`. Asked because the ladder names "anything measured" and a silent seam error as L (`spec.md`, "Why scope L") | Chose *"L (Recommended)"* | none |

## Open — needs the author

1. **`rag-server-reuseport`** (`super-plan.md:132-135`) should close before 2.1's live
   reproduction and before any Phase 7 run (`review.md` S3, F9). This task's evidence sidesteps it
   by owning its server; `make dev` and `make measure` do not. Not a blocker for this task.

## Found while implementing — for the author, not fixed here

- **`make dev` may orphan `rag.server`.** Its recipe starts `( cd $(RAG) && $(PY) -m rag.server ) &`
  and traps `kill $rag_pid`, but `$!` is the PID of the *subshell*, which bash does not reliably
  replace with Python. Killing the subshell can leave the server running and still bound to
  `:50051`. This is a plausible source of the six stale servers found on 2026-10-03
  (`rag-server-reuseport`). `make seam-check` avoids it with `exec`. Not verified on `make dev`
  itself; it belongs with `rag-server-reuseport`.

## Taken by Claude as a default, open to reversal

- **D1-a, contract-literal.** An absent `texts` is `nil` with no error. **Approved by `review.md`**
  on condition S3: the obligation (nil with non-empty `ChunkIDs` is not scored, not SUPPORT, not
  gate-off) goes into the `Texts` doc comment and, at `/done`, into super-plan's 2.1 row. D1-b would
  have needed the contract phase (`design.md` §2, D1).
- **Every `review.md` finding applied** (S1–S5, N1–N6; its "Resolutions" table). The two that shape
  the work most: `make seam-check` starts its own `rag.server` from the working tree on
  `127.0.0.1:50052` instead of trusting `:50051` (S2), and it fails unless the log proves the
  subtests ran (S1).
- **The live check lives in `ragclient`** as an env-gated `_test.go` that imports go-redis for the
  oracle. It adds no production dependency (`design.md` §3c).
