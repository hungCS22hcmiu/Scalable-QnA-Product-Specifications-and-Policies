# Design review — policy-documents (item 3.3)

**Reviewer:** design-reviewer subagent (opus), 2026-10-20, on `design.md` **draft 1**.
**Verdict: sound, with changes.** The shape is right: document-level split, doc ids derived from the
fields, one G5 implementation, rules committed before any text, no retrieval in this item. H1–H3 are
rule changes and must land **before plan step 3**, because P6 freezes the rules once the first
document exists.

**Resolution:** every finding is accepted and merged into `design.md` **draft 2**, except where the
last column says otherwise. Two become new open questions for the author (`spec.md` 9 and 10). The
reviewer checked the claims draft 1 left to `impact.md` itself (L6); `impact.md` has since been
saved, and the two reports agree except on one point, settled from the code (see M1).

## Findings

| ID | Sev | Finding | Suggested change | Resolution (draft 2) |
| :-- | :-- | :--- | :--- | :--- |
| H1 | High | **The scan misses the most natural G5 violation.** Draft 1 fails a document only when it names *two* values of one axis. Real text names one value and leaves the other implied: a domestic warranty that says "not valid outside the United States", an electronics return policy that says "opened TVs carry a fee". Each passes and still holds two answers under one `doc_id`; G5 reports "after = 0" while the namespace cannot separate the pair | Fail any document that names a value it did not declare. No condition → no value of any axis; a split document → only its own value. Outside the grade family, skip grade's plain words (`new`, `brand-new`) | **Accepted.** §5 and §6: the undeclared-value rule. Also adds impact §7 C's fourth axis, `kind` (a return document never names warranty words, and the reverse) |
| H2 | High | **Conditions outside the three axes pass silently**: member and card-holder windows, holiday windows, receipt or no receipt, state exceptions, terms per leaf (TVs vs headphones, chairs vs desks). Membership answers are also dynamic | A `terms` field (ignored by ingest). The checker fails a number in the text that is not in `terms`, and a document with two windows of one kind. W7 excludes membership, holiday, receipt and state rules. Extend U7 to furniture | **Accepted, simplified.** §3 `terms`; W7: **the only numbers in a text are its `terms`** (no separate authored-number list: refund timing is written without a number); at most one duration and one amount per document; U7's rule covers furniture |
| H3 | High | **Most sibling chunks carry no condition signal**, so drafting style decides which sibling ranks first. Measured on a 494-word draft: 4 chunks, the title only in chunk 0, 2 of 4 chunks naming no condition. RQ2a's residual and the namespace's false misses then follow drafting choices | Fix one W5 rule now. Recommended: shared sections use the **same text** in both siblings, and **each section names the document's own value once**, so rank 1 turns on the condition word. The other option ("only the opening names it") is fine if chosen and recorded. Titles use the canonical value word. The checker prints, per chunk, whether it names its value | **Accepted as the proposal; the choice goes to the author** (`spec.md` question 9). §4 W5 (minimal pairs), §2 titles, §6 per-chunk print |
| M1 | Medium | **"The numeric check refuses them by construction" is probably false.** The arm accepts a number if any one fresh chunk has it (`support_numeric.go:185`), and the sibling's chunk 0 will often be in the fresh top 5. One direction is blind to both arms: the phones pair differs only by "$45", "no fee" has no number, and `no` is a stopword | Remove "by construction". Record per pair whether it differs by a number or by words, and in which direction. A 3.6 statistic with no LLM: does the fresh top-k hold the sibling's term chunk? | **Accepted.** §7.4 rewritten; the per-pair record goes to `data-card.md` §2; the statistic is carried to 3.6. *Settled from the code:* the reviewer is right that each number is checked on its own (`numSupported`); `impact.md` §7 D said otherwise and carries a correction |
| M2 | Medium | **Folded into the gate, G5's PASS claims less than §7's G5** but reads as the full G5. The scan checks words on declared axes only | Keep the fold. G5's summary says "declared axes, lexical"; §7 and the freeze message keep the author's read (P8) as part of G5 | **Accepted.** §6 |
| M3 | Medium | **A split with the same answer on both sides is not caught** (a maker that serves its warranty worldwide). It refuses safe reuse and grows RQ2a's denominator with safe pairs | Split only when the two terms differ; the checker compares the siblings' `terms` | **Accepted.** §2 fallback, §6 check |
| M4 | Medium | **A vague term makes reuse look safe** ("depends on the country", "contact the seller"): the reference answer is vague for every question on that document. ADR-011's F17 problem again | W3: the main term is concrete: a number with its unit, or a plain "not covered" / "not accepted" | **Accepted.** §4 W3 |
| M5 | Medium | **Grade, and region framed as "International Models", are properties of a listing**, not a state of one product. They feed B-cross or invented B-within pairs; packaging and kind give natural B-within pairs. 3.2 did not exclude titles with "(Renewed)" or "International Version" | State per axis which stratum it feeds. Frame region as a condition of use ("warranty service outside the US"). Count "Renewed", "International Version", "No warranty" in the 152 titles before writing | **Accepted.** §2: region is framed as **where service is asked for** (the PQA traffic: "does the warranty remain valid in India?"); a per-axis stratum table; the title count is plan step 1 (needs `data/` access). Whether to keep the grade split goes to the author (`spec.md` question 10) |
| M6 | Medium | **W8 conflicts with §7**, whose fix for a failed G1 is to "differentiate policy windows … lengthen policy documents", i.e. to edit text because of a retrieval result | Text may change only as a recorded §7 fix at 3.6, citing the gate output, before any reuse rule runs | **Accepted.** §4 W8 |
| L1 | Low | **The laptops pair mixes two stores** (Target 30, Amazon 90), against the one-source rule of questions 3 and 4. Furniture moves from ADR-002's 90 days to 180 / 365, so ADR-002's "14 / 30 / 30 / 90" no longer holds | Amazon for both laptop sides. ADR-012 lists the windows that replace ADR-002's, and says once that the store combines four retailers' policies | **Accepted.** §2, §9 |
| L2 | Low | **Gaps in the word list**: a non-breaking hyphen (U+2011) defeats `pre-owned` and `open-box`; `U.S. model`, `outside the US`, `country of purchase` do not match. Unicode dashes also change how the numeric arm attaches units | ASCII before scanning, or ASCII text. Add the US variants and `country of purchase`. Terms only in units the numeric arm reads | **Accepted.** §4 W9 (ASCII only, checked); §5 list widened. `used` is **not** added: "if the item has been used" is ordinary return wording, and under H1 it would fail every document |
| L3 | Low | "The term falls in chunk 0" is reasoned, not checked | The checker asserts chunk 0 holds the main term | **Accepted.** §6 |
| L4 | Low | After 3.6 there are two copies; P1, P3 and P4 check one, the gate the other | 3.6 asserts the copies are byte-identical | **Carried to 3.6** (§10) |
| L5 | Low | `snapshot_digest` hashes files, not chunks, and the splitter is unpinned: chunk ids can move under the same digest | Also record a digest of (chunk_id, sha256 of chunk text) | **Carried to 3.6** (§10) |
| L6 | Low | `impact.md` was missing; the fields-are-inert claim is correct; other touch points: data-card §2 "shipping", §7 "four" and "check by hand", ADR-002's windows, the numeric unit list (draft until the freeze), the `policy-returns#chunk-2` example. Singular `return` is safe | Write `impact.md`; update the Schemas example id | **Done / accepted.** `impact.md` saved; the Schemas example is plan step 7 |
| L7 | Low | Nothing pins that the new fields stay out of metadata. If `condition` reached the index, a filter on it would be a condition classifier on the hit path (cut scope) | Test: `record_to_document(policy).metadata` has exactly `doc_id`, `kind`, `category`, `title` | **Accepted.** P11 |
| L8 | Low | "~45 policy chunks" is low: 391 words → 3 chunks, 494 → 4; 13 documents at 550–800 words give ~52–78 | Correct §7.6 and U3 | **Accepted.** |

## Open questions — where the reviewer disagreed or added a condition

- **Q2 (warranty as published): agree**, with one condition: if U1 drops both region splits, phones,
  laptops and electronics share one term with no condition, and `data-card.md` §2 requirement 2 is
  then **not met** for 3 of 4 departments. ADR-012 says exactly that, not "met in part".
  → **Accepted** (§9).
- **Laptops: Amazon for both sides** (L1). → **Accepted.**
- **Q6 (Claude drafts): agree.** Draft from the term table, **not** with the fetched pages in
  context: the simplest way to keep W1 true. → **Accepted** (§4 W1).
- **Q7 (fold G5): agree, with M2.** Not a scope trap. → **Accepted.**
- **Q1, Q3, Q4, Q5, Q8: agree.**

## Unknowns the reviewer added (all in `design.md` §8)

1. Does the embedding rank the right sibling first? `opened` / `unopened` is close to a negation.
   3.6 (G1 / G2).
2. How often does the fresh top-5 hold the sibling's term chunk (M1)? 3.6, no LLM.
3. How many of the 152 titles say "Renewed" or "International Version" (M5)? Now, one grep, once
   `data/` is readable.
4. Which chunk positions do workload questions retrieve? If almost always chunk 0, "≥ 3 chunks gives
   a gradient" overstates: the gradient then comes from mixing many documents' chunk 0s. 3.6.
5. Do the warranty sources give per-region terms, or only vague ones (U1, M3, M4)? Plan step 2.

*The reviewer's splitter and word-list tests used its own made-up text, from the scratchpad. Nothing
under `data/` was read and no repo file was changed.*

---

# `/ai-review` — the implementation (2026-10-21)

**Reviewer:** `contract-reviewer` subagent, over `git diff a88c3b1..HEAD` (`c9a93f6`, `a3cca5a`,
`3c88dfe`; the working tree was clean). It read `interfaces.md`, `architecture.md`, `CLAUDE.md`'s
constraints, the frozen-values table and this trail. *The skill's "rules #1, #5, #6, #10" point at a
rules file deleted on 2026-09-22; the reviewer was pointed at those living documents instead.*

**Seam: clean.** No `gateway/`, `rag/`, `contracts/` or `interfaces.md` change. All 12 ids conform to
§C and pass `rag.ingest.load_records`; `policy_kind`, `condition` and `terms` cannot reach chunk
metadata, Redis or the gateway. Counts in the docs (12, 48 chunks, G5 4 / 0) are true; `c9a93f6`
precedes the first `data/policies-v1/` commit; no frozen value is weakened.

| ID | Sev | Finding | Verdict | Resolution |
| :-- | :-- | :--- | :--- | :--- |
| F1 | High | Both phones warranty records held the literal `For {v} service` twice: in the generator a `.replace("{v}", v)` bound to one string of `para(...)`. Every check, every test and the author's read passed it | CONFIRMED | **Fixed.** The generator uses f-strings; `check_schema` fails any `{ } < >` in title or text (`test_a_placeholder_left_in_the_text_fails`; mutant caught). The two documents changed, so they are re-read |
| F2 | Medium | G5 passed "outside **of** the United States", "outside the USA", "non-US", "foreign", "other countries", "worldwide", "unsealed", "reopened", "open the box", and any phrase broken by a line break or a double space | CONFIRMED | **Fixed:** white space is collapsed before matching, and the words are added. **A rule change after the text existed**, recorded in `approvals.md`; it only widens the list, and none of the 12 documents hits an added word. Tests `test_g5_catches_the_reworded_sibling_value`, `test_g5_catches_reworded_packaging_words`; mutants caught |
| F3 | Medium | The international phones warranty said "not covered" but its shared sections listed "typical covered faults", and it pointed to its sibling ("back where it was bought") | CONFIRMED | **Fixed, the author's decision:** W5 is waived for the phones warranty pair, and the international document is rewritten to be true on its own (no section describes service anywhere else). Sibling Jaccard 0.55. Recorded in ADR-012 and `data-card.md` §2; **the experiment row is approved again** (`approvals.md`) |
| F4 | Low | Shared text carried small rule breaches: "claim with a gift receipt" (W7), a gift store-credit path, "damaged by use" in the unopened furniture text; also a conditional SIM step, an applied-screen-protector exception and a headphone hygiene rule | CONFIRMED | **Fixed, the author's decision:** the gift / receipt sentences are removed and "damaged by use" becomes "damaged" (a word diff against the approved text shows only these). The SIM step, the screen-protector and the hygiene rules are **accepted and recorded** in `data-card.md` §2 (none is a condition axis) |
| F5 | Low | W7's worded-number check saw only `day / week / month / year`; "three business days", "forty-five dollars", "forty-eight hours", "fifty percent" passed | CONFIRMED | **Fixed:** number words before any unit the numeric arm reads, one optional word between. Tests added; ordinary "one of our team" still passes; mutant caught |
| F6 | Low | `main` crashed with a traceback on a malformed file instead of reporting it (exit 1 either way) | CONFIRMED | **Fixed:** `load_records` errors are reported; only splittable records are split. Tests on bad JSON, a missing `doc_id`, a top-level list and a non-string `text`; mutant caught |
| F7 | Low | G5 passed a corpus with no policy documents ("0/0 clean") | CONFIRMED | **Fixed:** G5 fails when it gets no policy records (`test_g5_fails_a_corpus_with_no_policy_documents`; mutant caught). Department coverage stays `check_policies`' job |
| F8 | Low | Nothing tested that G5 is wired into the gate's stage 1 | CONFIRMED | **Fixed:** `test_the_gate_runs_g5_in_stage_1_and_stops_on_it` calls `corpus_gate.main --structural-only`; dropping `g5` from `criteria` is caught |
| F9 | Low | (a) ADR-012 said "terms come from primary pages", against its own weak sources; (b) ADR-002's row did not say it is amended; (c) `data/README.md` said all contents are gitignored; (d) the data-card header was stale; (e) spec P5's git-log evidence is missing for the Samsung, HP and Sony rows, committed with the documents | CONFIRMED | **(a)–(d) fixed.** **(e) accepted and recorded** in `approvals.md`: the three pages were fetched and the terms recorded before those documents were drafted in the session, but they were committed together, so git cannot show the order |

**Not verified by the reviewer:** the brand and title counts, which come from `data/v1-draft/`
(denied). They are `make policy-sources` output, reproducible by anyone with the drafts.

**After the fixes:** `make policy-check` passes on all 12; `pytest experiments/tests` 392 passed;
`ruff` clean; 7 new hand mutants (F1, F2 ×2, F5, F6, F7, F8), all caught.
