# Plan — pqa-thick-tail-selection (item 3.2)

**Draft 3, 2026-10-19:** the impact and design-review findings are merged. Steps assume the proposed
answer to every open question in `spec.md`. Nothing here starts before `/approve implementation`.

Each code step ends green (`make test`, `ruff check experiments`) unless it says otherwise. Test
numbers (T1 …) are `design.md` §4.

## A. Before any code

- [x] 1. Memory check (`sysctl kern.memorystatus_vm_pressure_level`). No model is loaded, so this is a
      note, not a gate; but step 3 holds a whole leaf in memory. *2026-10-20: level 2, 42 % free.*
- [x] 2. Confirm whether an ePQA copy exists under `data/` (this session cannot list `data/`; the
      author can, or `make` can). *Deferred to step 13: `ls data/raw` was denied; the fetch target
      reports a file it finds.*
- [x] 3. **Re-derive the `adr002` pins:** run `example_product.py` unchanged on each of the six raw
      leaves (`python3 docs/work/2026-10-03-pqa-category-choice/scripts/example_product.py <leaf> <department>`),
      smallest leaf first, and record each "candidates qualifying" count in `evidence/probe-pins.md`.
      If one differs from ADR-002's table, **stop and show the author** (design §2.6).
      *Done 2026-10-20: all six equal ADR-002 (`evidence/probe-pins.md`).*

## B. The builder change (open question 3 = exclude)

- [x] 4. `build_pqa.py`: `fields_conflict` on the product dict in `parse_leaf`; `MANIFEST_VERSION` → 2.
      Tests first: the flag on two disagreeing records, the field-slot test, `prose_conflicts`
      equals the number of flags, `load_manifest` refuses version 1. All 103 old tests stay green.
      *Done: 6 new tests, red first, then 109 green. A new Stop 3 check, `check_flags`: a parse that
      flags the wrong products keeps `prose_conflicts` right and passes Stop 3c, so only it sees that.*
- [x] 5. **Live:** `make pqa-build` twice and `make pqa-verify`: one new manifest sha256, three
      times; 78 flags (5 / 21 / 13 / 1 / 31 / 7). Record in `evidence/live-run.md`. Commit the new
      `data/pqa-manifest.json`. *Done: `741d52e3…` three times; `make verify` green (264 + 15).*

## C. The selector, offline

- [x] 6. `select_pqa.py` skeleton: the constants of design §2 (probe ones copied, departments from
      `build_pqa.LEAVES`), the guard, the manifest read once and hashed, two passes through
      `iter_interim`, the re-check after the pass. T1, T2, T12, T17, T20.
- [x] 7. `tag()` with R1 and R2 and the generic set; the funnel; the two probe-pool counts and pins.
      T7, T8, T9, T13, T16.
- [x] 8. The draw and the quota stop. T10, T11.
- [x] 9. The writers, the `.pqa-select-*` temp dir, the swap with restore, the manifest last,
      cleanup on every exit, and `iter_selection`. T3, T4, T5, T6, T18, T19.
- [x] 10. The report (design §2.4): funnel, distribution, answerable shares, prose and chunks,
      re-asks in two parts and the digit-flip count. T14.
- [x] 11. The audit sheet and its scorer (design §3.2). T21.
- [x] 12. `make pqa-select`, `make pqa-audit-sheet`, `make pqa-audit-score`. **Commit here.** The
      whole rule, both answerability rules, the seed, the audit design and the fallback are now in
      git before any live run and before ePQA is fetched (A9).
      *Done 2026-10-20: 47 tests (`test_select_pqa.py`), 311 in `experiments/` in all, lint clean.
      Also `make pqa-select-verify`. Three things changed while writing it, each before any run:
      `first_failure` reads `fields_conflict` before any step, so a line without it raises whatever
      it would fail; the probe-pool records get a `doc_id` of the real form, because the chunker
      counts the metadata; and the audit reports precision, the negative predictive value and a
      re-weighted recall (design §3.2, corrected), because the 15 : 10 sample is not the pool's ratio.
      `re.I` became `re.IGNORECASE` (lint); the value is the same, and T12 compares the flags.*

## D. The answerability check against ePQA

- [x] 13. `make epqa-fetch` (curl, a pinned commit, into `data/raw/epqa/`); keep the curl log with
      its time (review L6); pin the three sha256 in the script. *Done: commit `cec976cc…`, fetched
      09:15:09Z, two minutes after the rule commit; no earlier copy existed (closes step 2).*
- [x] 14. `answerability_check.py` and `make pqa-answerability`. T15. *8 tests.*
- [x] 15. **Live:** run it. `evidence/answerability.json` (counts) and a short reading in
      `evidence/answerability.md`. Not a gate: the numbers go to the author. *Done: the 194 pin held;
      R2 precision 4 / 19 against ePQA's primary label, κ 0.17.*

## E. The live selection and the audit

- [x] 16. Memory check. `make pqa-select` twice: same manifest sha256; the probe pins hold; record
      the funnel, distribution and shares in `evidence/live-run.md`. If a leaf is short, **stop**
      and ask the author which pre-registered fallback step to apply (design §2.3).
      *First run 2026-10-20: the probe pins held; TVs short (13 of 19). Stopped. The author applied
      fallback step 1 (TVs 13 + headphones 25). Then 152 products, 4,706 pool lines, the same
      selection sha256 `036dcae8…` twice, `pqa-select-verify` passes (`evidence/live-run.md`).*
- [x] 17. `make pqa-audit-sheet`; **the author marks the 100 questions** (about one hour); *(marked by Claude at the author's request: a model audit, `evidence/audit.md`; precision 21 / 60)*
      `make pqa-audit-score`; `evidence/audit.json` and a short reading.

## F. The record

- [x] 18. `data-card.md` §1 and §3: the selection rule (R2, with R1 reported), the product count
      (152), the realised distribution, the answerable shares, the re-ask counts (both definitions
      and populations), the ePQA agreement and the audit, the limitation on C1, the stratum for
      unanswerable questions, and the decisions on the 78 and on warranty terms. The Schemas block:
      the real product record and the pool line (replacing `product-B08XYZ`). Mark the pools at
      `:52,63` as the probe's rule. Fill only the `TODO(W8)`s this item owns.
- [x] 19. `architecture.md`: the tree and §5 list `select_pqa.py`, `answerability_check.py`,
      `data/v1-draft/products/`, `question-pool.jsonl`, `audit/`, `data/pqa-selection.json`,
      `data/raw/epqa/`.
- [x] 20. **ADR-011 (data)**, written 2026-10-20 (the author agreed to close 3.2 with it): the frozen rule, the seed, R2, the two new
      filters, the fallback steps applied (if any), the live funnel; `Invalidates: none — no runs yet`.
- [x] 21. `super-plan.md` at `/done`: the 3.2 row, the Phase 3 progress line, the stale "manifest
      not committed yet" in the 3.1 row (`:393`), and 3.4's inherited constraints (the stratum for
      unanswerable questions; read through `iter_selection`; do not label strata with this
      tokenizer; "return key"; no shipping tag).
- [x] 22. `/verify`, `/ai-review`, `/done`. *2026-10-20: `make verify` green (333 + 15; proto drift is not a `make verify` target, so not run); `/ai-review` found 10, all fixed (`review.md`); `/done` below.*

**Passed on, not done here:** `data/workload-v1.json` (the gate's default path) is not gitignored,
and 3.4 will write PQA question text to it (impact F11). Stale prose for the author:
`data/README.md`, `.gitignore:21-24`, `data-card.md:48` (impact F14).

## Outcome — closed 2026-10-20

**Shipped.** `experiments/scripts/select_pqa.py` (the selection, `iter_selection`, the blind audit),
`experiments/scripts/answerability_check.py` (the ePQA check), `build_pqa.py`'s `fields_conflict` flag
(`MANIFEST_VERSION` 2), seven Make targets, 75 tests. Tracked outputs: `data/pqa-manifest.json`
(`741d52e3…`) and `data/pqa-selection.json`. Gitignored drafts: 152 product records (digest `d373c4b0…`), a
4,706-question pool, the generic tokens, the marked audit sheet; `data/raw/epqa/`. Records: `data-card.md`
§1, §3 and Schemas (**the Done-when**), **ADR-011**, `architecture.md`, `super-plan.md` (the 3.2 row, the
Phase 3 progress line, 3.4's inherited constraints).

**What the numbers say.** The probe's pools reproduce exactly. R2 is a high-recall, low-precision
pre-filter: precision 35 % (a model audit) and 21 % (ePQA); NPV 97.5 % and 93.5 %. The selection favours
long product text (2 – 5 chunks against 1 – 2), a C1 limitation.

**Departures, each recorded:** fallback step 1 applied by the author (TVs 13 + headphones 25); the audit
marked by a model at the author's request, not human-verified; one test amended and one renamed field, with
the reasons in `approvals.md`.

**Deferred, to a named owner:**
- **3.4:** re-label every R2-answerable workload query and a sample of the R2-unanswerable ones; keep the
  unanswerable stratum; read the drafts through `iter_selection`; never label strata with the probe's
  tokenizer; policy questions are scarce (127); `data/workload-v1.json` must be gitignored before it holds
  PQA text.
- **3.6:** `K` comes from a pool whose true answerable yield is estimated (≈ 410 of 1,180), not measured;
  the selected products' long titles: one probe-pool title already makes `make ingest` fail, so the freeze
  must ingest the drafts once before hashing.
- **For the author (stale prose, not this item's):** `data/README.md`; `.gitignore:21-24`;
  `data-card.md:48` (the builder no longer downloads).

**Follow-up worth a task:** none outside the items above.
