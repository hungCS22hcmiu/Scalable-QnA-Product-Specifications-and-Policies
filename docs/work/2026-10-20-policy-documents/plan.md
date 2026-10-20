# Plan — policy-documents (super-plan item 3.3)

**Draft 2** · 2026-10-20 · follows `design.md` draft 2 and the proposed answers (`spec.md` 1–10).
Each step ends in something that can be checked. Steps 1–3 come **before any policy text exists**
(P6). A different answer to an open question changes the steps that name it.

## Before any text

- [x] **1. Access, and one count.** ✅ *2026-10-21: the counts came from `make policy-sources` (counts only, through `iter_selection`): 10 risky titles, kept by the author; the author then narrowed the deny rule.* The author grants this session Read and Write on
      `data/policies-v1/` and Read on `data/v1-draft/products/` (U5). Then count the 152 titles
      that say "Renewed", "International Version" or "No warranty" (U8). If any, report to the
      author before step 3: 3.2's selection is frozen by ADR-011.
- [x] **2. Sources.** ✅ *2026-10-21: every term sourced (`evidence/sources.md`); the maker rule amended twice by the author before the pages it selects were fetched; the laptops region split dropped by the fallback; three weak sources flagged.* ◐ *(history:)* *Partly done 2026-10-20 (`evidence/sources.md`): every return term and the furniture warranty (10 years). The source-choice rule was written before any warranty page was fetched. Laptops' Amazon terms rest on the 2026-10-03 reading (three re-fetches gave HTTP 503), and Amazon's help pages conflict on some Renewed items. Phones, laptops and electronics warranty wait on the maker rule, which needs step 1.* Fetch the primary page for every term in `design.md` §2: the return terms
      again, the warranty terms for the first time. In `evidence/sources.md`: URL, fetch date, the
      one stating line, and the term in `terms` form. Apply §2's fallback (no source, a vague term,
      or the same term on both sides → no split) and report every dropped split to the author.
      *Check:* every row of §2 has a concrete term from a primary source, or is dropped.
- [x] **3. Commit the rules.** ✅ *`c9a93f6`, 2026-10-20, before any policy text existed.* One commit, **before step 4**, holding:
      `CONDITION_AXES`, `condition_hits`, `load_policy_records`, `check_g5` in `corpus_gate.py`,
      wired into stage 1 with the "five criteria" wording; `check_policies.py`; `make policy-check`;
      the tests below; and the writing rules and word list as `design.md` §4–§5 state them.
      *Check:* `make test` and `ruff check experiments` pass; `make policy-check` on an empty folder
      exits 2.

  Tests, all with fixtures in `tmp_path`, never under `data/`:
  - P1: a 2-chunk record fails and is named; a 3-chunk one passes.
  - P2: a record naming its sibling's value fails; one naming both values fails and names both;
    a record with no condition naming `opened` fails; a return record naming `warranty` fails;
    `new` outside the grade family passes, inside the renewed record fails; `renewed` does not hit
    `new`; `un-opened` hits `opened`; products are ignored; every offender reported in one pass.
  - P3: wrong `category`, wrong `policy_kind`, an unknown axis, a `doc_id` other than the derived
    one, two records with one key, a split family with one value only, a title without its value
    word, a non-ASCII character, an extra or missing field — each fails.
  - P4: two identical chunks fail.
  - P11: `record_to_document(policy).metadata` has exactly `doc_id`, `kind`, `category`, `title`.
  - P12: a number not in `terms` fails; "one year" fails; "14 calendar days" with `terms`
    `["14 days"]` fails; two durations fail; siblings with equal `terms` fail.
  - P13: a main term outside chunk 0 fails.
  - G5 runs in the gate's stage 1; the freeze message says five criteria and keeps the author's
    read; G5's counts are in the report JSON.
  - P10: `git status --porcelain data/` is unchanged by the suite. *(Done as a command at
    `/verify`, as `spec.md` P10 states, not as a test: a test that shells out to git is fragile.)*

  **Step 3 result (2026-10-20):** `/verify` — gofmt **PASS**, go vet **PASS**, go build **PASS**, go
  test **PASS**, `ruff check rag experiments` **PASS**, pytest **PASS** (rag 15, experiments 370),
  proto drift **PASS** (`make proto`, no diff); `git status --porcelain data/` empty before and
  after. `make policy-check` on the absent folder exits 2. Hand mutants: 7 of 7 caught (G5 back to
  the both-values rule; no plain-`new` skip; no word boundary; `MIN_CHUNKS = 2`; no stray-number
  check; no white-space normalising in the identical-chunk check; the `kind` axis ignored).
  Deviation: the `Makefile` gate comments ("five criteria") were updated here rather than at step
  7, so this commit never says "four" next to a five-criterion gate.

## The documents

- [x] **4. Draft the documents** ✅ *2026-10-21: the 12 files are in `data/policies-v1/` (byte-identical to the drafts the author read; the trail keeps only the generator), `make policy-check` passes on them, and `test_the_tracked_policy_corpus_is_the_adr_012_set_and_passes_every_check` guards them (it fails when one is broken on purpose).* ◐ *(history:)* *2026-10-21: all **12** drafted (the laptops region split dropped by §2's fallback) and passing `make policy-check` on `evidence/drafts/`: 562–590 words, 4 chunks each, the term in chunk 0, G5 0 of 12. G5 caught one stray `opened` in a phones warranty draft; the text was fixed. Left: move into `data/policies-v1/` (needs the author's settings edit) and add the test over the tracked folder.* ◐ *8 of 13 drafted 2026-10-20 (all returns + furniture warranty), in `evidence/drafts/` (uncommitted) from `make_drafts.py`, until `data/policies-v1/` is writable. `make policy-check POLICY_DIR=docs/work/2026-10-20-policy-documents/evidence/drafts` passes every check except the three missing warranty families. On the way the checker caught the drafts short of 550 words, a 2-chunk furniture warranty, and one identical chunk between the furniture siblings (P4); each was fixed in the text, never in a rule.* into `data/policies-v1/`, one family at a time, siblings side by
      side (W5), from the term table only (W1). After each family: `make policy-check`. A failure
      changes the text, never a rule or a word. When all 13 pass, add **one test over the tracked
      folder**, so `make test` catches a later edit that breaks a rule (impact §7 D).
      *Check:* `make policy-check` exits 0; `make test` passes.
- [x] **5. The author's read.** ✅ *2026-10-21: all 12 read, none sent back (`approvals.md`).* The author reads each document against W1–W9 and approves it or
      sends it back. One line per document in `approvals.md` (P8).

## Records

- [x] **6. `data-card.md`:** ✅ *2026-10-21 (uncommitted): §1 risky titles, §2 the documents, sources, rules, pair table, requirement 2 in part; Schemas; §7 G5 and the counts; Ethics.* §2 (the doc_id list and titles; terms and sources; the writing rules;
      who wrote the text; per sibling pair, a number or words and in which direction; the stratum
      each axis feeds; the region sentence for the Ethics line; shipping dropped); Schemas (the
      policy document; the singular example id; the fields never reach metadata); §7 (five criteria,
      the author's read inside G5, the before / after counts, the splitter version). Remove the
      `TODO(W8)`s these fill, and only those.
- [x] **7. `architecture.md`** ✅ *(committed in `a3cca5a`; super-plan rows 3.3 and 3.5 and the progress paragraph, 2026-10-21, uncommitted)* (the folder, "not a dataset version"; the script; "G5 not built"
      goes); **`super-plan.md`** (rows 3.3 and 3.5, the Phase 3 progress paragraph, §10's carries
      into 3.6); **Makefile** comments ("four criteria", "G1..G4", "G3/G4 only").
- [x] **8. ADR-012** (data), with the real terms and sources (`design.md` §9 point 8). ✅ *2026-10-21, uncommitted.*

## Close

- [ ] **9.** `/verify`, then `/ai-review`, then `/done`.

  **`/verify`, 2026-10-21, before the documents commit:** gofmt, go vet, go build, go test, ruff, pytest (rag 15, experiments 373) and proto drift all **PASS**, none skipped; `git status --porcelain data/` unchanged by the suite.

**Not in this plan:** any retrieval, embedding or LLM run (P7); building `data/v1/` and everything
in `design.md` §10 (3.6); any `rag/`, `reuse/` or `interfaces.md` change.
