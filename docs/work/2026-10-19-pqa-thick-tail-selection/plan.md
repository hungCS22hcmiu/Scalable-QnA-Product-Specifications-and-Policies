# Plan — pqa-thick-tail-selection (item 3.2)

**Draft 3, 2026-10-19:** the impact and design-review findings are merged. Steps assume the proposed
answer to every open question in `spec.md`. Nothing here starts before `/approve implementation`.

Each code step ends green (`make test`, `ruff check experiments`) unless it says otherwise. Test
numbers (T1 …) are `design.md` §4.

## A. Before any code

- [x] 1. Memory check (`sysctl kern.memorystatus_vm_pressure_level`). No model is loaded, so this is a
      note, not a gate; but step 3 holds a whole leaf in memory. *2026-10-20: level 2, 42 % free.*
- [ ] 2. Confirm whether an ePQA copy exists under `data/` (this session cannot list `data/`; the
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

- [ ] 6. `select_pqa.py` skeleton: the constants of design §2 (probe ones copied, departments from
      `build_pqa.LEAVES`), the guard, the manifest read once and hashed, two passes through
      `iter_interim`, the re-check after the pass. T1, T2, T12, T17, T20.
- [ ] 7. `tag()` with R1 and R2 and the generic set; the funnel; the two probe-pool counts and pins.
      T7, T8, T9, T13, T16.
- [ ] 8. The draw and the quota stop. T10, T11.
- [ ] 9. The writers, the `.pqa-select-*` temp dir, the swap with restore, the manifest last,
      cleanup on every exit, and `iter_selection`. T3, T4, T5, T6, T18, T19.
- [ ] 10. The report (design §2.4): funnel, distribution, answerable shares, prose and chunks,
      re-asks in two parts and the digit-flip count. T14.
- [ ] 11. The audit sheet and its scorer (design §3.2). T21.
- [ ] 12. `make pqa-select`, `make pqa-audit-sheet`, `make pqa-audit-score`. **Commit here.** The
      whole rule, both answerability rules, the seed, the audit design and the fallback are now in
      git before any live run and before ePQA is fetched (A9).

## D. The answerability check against ePQA

- [ ] 13. `make epqa-fetch` (curl, a pinned commit, into `data/raw/epqa/`); keep the curl log with
      its time (review L6); pin the three sha256 in the script.
- [ ] 14. `answerability_check.py` and `make pqa-answerability`. T15.
- [ ] 15. **Live:** run it. `evidence/answerability.json` (counts) and a short reading in
      `evidence/answerability.md`. Not a gate: the numbers go to the author.

## E. The live selection and the audit

- [ ] 16. Memory check. `make pqa-select` twice: same manifest sha256; the probe pins hold; record
      the funnel, distribution and shares in `evidence/live-run.md`. If a leaf is short, **stop**
      and ask the author which pre-registered fallback step to apply (design §2.3).
- [ ] 17. `make pqa-audit-sheet`; **the author marks the 100 questions** (about one hour);
      `make pqa-audit-score`; `evidence/audit.json` and a short reading.

## F. The record

- [ ] 18. `data-card.md` §1 and §3: the selection rule (R2, with R1 reported), the product count
      (152), the realised distribution, the answerable shares, the re-ask counts (both definitions
      and populations), the ePQA agreement and the audit, the limitation on C1, the stratum for
      unanswerable questions, and the decisions on the 78 and on warranty terms. The Schemas block:
      the real product record and the pool line (replacing `product-B08XYZ`). Mark the pools at
      `:52,63` as the probe's rule. Fill only the `TODO(W8)`s this item owns.
- [ ] 19. `architecture.md`: the tree and §5 list `select_pqa.py`, `answerability_check.py`,
      `data/v1-draft/products/`, `question-pool.jsonl`, `audit/`, `data/pqa-selection.json`,
      `data/raw/epqa/`.
- [ ] 20. **ADR-011 (data)**, if the author agrees: the frozen rule, the seed, R2, the two new
      filters, the fallback steps applied (if any), the live funnel; `Invalidates: none — no runs yet`.
- [ ] 21. `super-plan.md` at `/done`: the 3.2 row, the Phase 3 progress line, the stale "manifest
      not committed yet" in the 3.1 row (`:393`), and 3.4's inherited constraints (the stratum for
      unanswerable questions; read through `iter_selection`; do not label strata with this
      tokenizer; "return key"; no shipping tag).
- [ ] 22. `/verify`, `/ai-review`, `/done`.

**Passed on, not done here:** `data/workload-v1.json` (the gate's default path) is not gitignored,
and 3.4 will write PQA question text to it (impact F11). Stale prose for the author:
`data/README.md`, `.gitignore:21-24`, `data-card.md:48` (impact F14).
