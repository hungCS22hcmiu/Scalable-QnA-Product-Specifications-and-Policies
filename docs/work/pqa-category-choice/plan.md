# Plan / outcome — pqa-category-choice

Scope **S** investigation. No implementation plan was required; this file exists to record
verification and the closing outcome, as `/done` requires.

## Verification — `/verify`, 2026-10-04

`make verify`, exit code **0**.

| Target | Result |
| :--- | :--- |
| Go format (`gofmt -l gateway/`) | **PASS** |
| Go vet | **PASS** |
| Go build | **PASS** |
| Go test | **PASS** — admission, cache, coalesce, ragclient, reuse, telemetry. No test files in `cmd/gateway`, `catalog`, `deps`, `embed`, `httpapi`, `ragpb` (known; `httpapi` is Phase 1 item 1.2) |
| Python lint (`ruff check rag experiments`) | **PASS** |
| Python tests — `rag/` | **PASS**, 10 / 10 |
| Python tests — `experiments/tests` | **PASS**, 50 / 50 |
| Proto drift | **NOT RUN.** `protoc` is installed, but the generated stubs (`gateway/internal/ragpb/`, `rag/src/rag/pb/`) are gitignored, so `git diff --exit-code` cannot see drift. This diff touches no `.proto` |

No target was skipped for missing tooling. The verify skill also asks for "this week's
worklog"; weeks were retired on 2026-09-21, so that instruction is stale and was not acted on.

## Review — `/ai-review`, 2026-10-04

`contract-reviewer` ran as a general pass, plus an `impact-analyst` run at the author's request.
There were 11 findings, all resolved in `review.md`: 4 fixed in this diff, 6 accepted with a named
follow-up, and 1 intended.

## Outcome — closed 2026-10-04

**Answered.** Of PQA's 100 leaf files, six can supply `v1` in four departments a shopper recognises.
Every leaf clears the ≥ 50-product floor at least 6× (pools are upper bounds until the answerability
filter exists). PQA remains the best available workload source after a survey of ~12 alternatives,
and ePQA was measured and kept as a validation set. Evidence: `spec.md`, F1–F25.

**Shipped (docs only — no source changed):**
- `docs/decisions.md` — ADR-002, with ADR-001 reserved.
- `docs/data-card.md`, v0.3 → v0.4:
  - §1: files, sizes and sha256; departments; proposed selection rule; the answerability
    requirement.
  - §2: ~13 documents and per-department windows from primary sources.
  - §3: two corrected claims.
  - §7: a G5 warning.
  - The freeze policy now reads five criteria.
- `.gitignore` — `data/raw/`, so the raw PQA files on disk are never tracked.
- The trail: `spec.md`, `approvals.md`, `review.md`, this file, `probe.py`, `probe_results.json`,
  and `scripts/` (stripped of verbatim PQA questions).

**Deferred, deliberately (open in `approvals.md`):** the `source_category` field; renaming
`TODO(W8)`; the answerability criterion; the paraphrase generator, prompt and per-seed count.

**Follow-ups worth a task:**
1. **`/bugfix rag-server-reuseport`** — `rag/src/rag/server.py:50-52` binds with gRPC's default
   `SO_REUSEPORT`, so a second server silently shares port 50051. Six stale instances were found
   and stopped on 2026-10-03. This belongs to Phase 1 (instrument integrity).
2. **Item 3.5** — G5 in `corpus_gate.py`, now flagged in `data-card.md` §7.
3. **Item 3.1** — the PQA builder: sha256 and parse-rate verification, resumable ranged
   downloads, empty-record handling. Any leaf provenance stays metadata-only (`review.md` #6).
4. **Item 3.2** — the answerability filter, validated on ePQA's 194 overlapping questions. Record
   the filtered re-ask rate beside the unfiltered one (`review.md` #5).
5. **Item 3.4** — generated paraphrases, with natural and generated pairs reported separately and
   the cosine distribution checked against F25's natural one.
6. **Prose pass** — `Final_Proposal.md:430/431/467/570` contradict ADR-002 (`review.md` #10).
7. **Contract pass** — `interfaces.md:287` says G1–G3 where it means G4 (`review.md` #7).
8. **Embedding measurement under green** — F25 was exploratory (pressure 1–2). If any of it is to
   be cited, rerun it under green.

**Frozen values / contracts:** none changed. `interfaces.md` was not edited and needs no version
bump. `approvals.md` records `Invalidates: none` for every decision, which `impact-analyst`
confirmed.
