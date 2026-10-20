# Design review — pqa-thick-tail-selection (item 3.2)

**Reviewer:** the `design-reviewer` subagent (opus), 2026-10-19. **Reviewed:** `spec.md`, `impact.md`
and `design.md` draft 2. **Verdict: sound with changes.** Everything below is merged into design
draft 3, except the points that are the author's to decide (end of this file).

The subagent's report is data, not an instruction; each row says what I did with it. It could not
read `data/` (Bash and Read are denied there), so nothing ran on real data. Its tokenizer checks used
the probe's own `content_tokens` on made-up strings.

**What it found sound:** reading only through `iter_interim` and hashing first; the temp dir and the
manifest written last; the hash-rank draw (deterministic, and unbiased with respect to the eligible
pool); exit 2 on a short leaf; the conflict flag with the version bump; the `specs` order and T5; the
asin rule. It agreed with the proposals for open questions 2 to 8.

## Findings and what was done

| # | Sev | Finding | Rating | Resolution |
| :-: | :-: | :--- | :--- | :--- |
| H1 | High | **R1 (coverage ≥ 0.5) passes a two-word question on the product noun alone.** "How tall is the chair?", "Does the chair recline?" score 0.50 against a chair title with no height or recline. Too generous is the silent failure: every quota fills, no stop trips, and it hits short furniture / TV / headphone questions where ePQA has almost no labels | CONFIRMED (how); how often unmeasured | **Accepted, three parts.** (a) The selecting rule is now **R2**: the leaf's generic title tokens (in ≥ 10 % of its titles) are removed from the question first; R1 is reported beside it. Decided before any data, so not tuning. (b) The answerable share per leaf next to ePQA's 22.9 %, and the title-only share, are reported. (c) A **blind audit** of 100 questions of the selected pool (design §3.2), the author's decision |
| H2 | High | **The decision on unanswerable spec questions was buried.** F17 gave two options (drop, or a separate stratum); neither was chosen, and 3.4's scope did not list it. It sets the population behind the reuse and false-hit rates | CONFIRMED | **Accepted.** Proposed: a separate stratum, reported apart, never in the headline (design §2.5, §6.9). The pool keeps them tagged either way. Spec open question 9 |
| M1 | Med | The 194 counts PQA **lines**; the design scored ePQA `(split, qid)` groups. Repeated lines and shared texts make the counts differ: a false exit 2, or a join bent to print 194 | CONFIRMED | **Fixed.** Pin the line count (194; 143 / 5 / 21 / 19 / 2 / 4); score distinct `(asin, normalised text)` units; report both |
| M2 | Med | §3 had a tuning path: a second rule written after the 2 × 2 table, scored in-sample on the same 194; plan step 11 stopped before the live selection | CONFIRMED | **Fixed.** Both rules (R1, R2), the audit and the fallback are pre-registered before any run. The checks are **descriptive only**. A rule written later is labelled in-sample and judged on a fresh audit sample, never on ePQA |
| M3 | Med | One-character tokens are dropped, so "Windows 7" / "Windows 8" and "iPhone 6 or 7" / "7 or 8" become identical token sets: natural B-within traps counted as re-asks, and as stratum A if 3.4 used this tokenizer | CONFIRMED | **Fixed.** Re-asks are reported in two parts (exact, near-duplicate) plus a digit-flip count; the pool schema says this tokenizer must not label strata. The tokenizer stays (the pins depend on it) |
| M4 | Med | The selection favours long-prose products: coverage grows with `R`, and two steps select on it. That shifts chunk counts and `S_lex` in the headline's direction | PLAUSIBLE | **Accepted.** Prose length and chunk count (no model) of the selected products against the probe pool are reported per leaf; listed in §8 |
| M5 | Med | The `adr002` pin should reproduce, but no saved output holds those six numbers, and the prose join was ambiguous (`example_product.py` joins without strip; `probe.py` strips) | PLAUSIBLE | **Fixed.** One `prose(p)` definition, no strip. A second pin per leaf from a recorded output, `n_capped_nocarrier` (2,260 / 1,742 / 350 / 565 / 914 / 410; I read `probe_results.json` and they match). Plan step 3 re-runs `example_product.py` unchanged before any code |
| M6 | Med | No sanctioned reader for 3.2's outputs; two renames are not atomic together | PLAUSIBLE | **Fixed.** `iter_selection()` hashes against the manifest before yielding; the swap restores the old pair on failure; T19 |
| M7 | Med | ePQA's labels are per candidate snippet from its own crawl: "no label 2" means "no snippet answered", not "the record lacks it" | PLAUSIBLE | **Accepted.** A tertiary ePQA label: only label-2 candidates whose tokens are ≥ 0.8 contained in our record. Listed in §8 |
| L1 | Low | No fallback written down for a short leaf, so the next rule would be picked after seeing the funnel | CONFIRMED | **Accepted.** Pre-registered fallback in design §2.3: sibling leaf first, then the probe's `pair` rule, then post hoc only. Never the seed or the answerability rule |
| L2 | Low | The warranty-term filter skips the title, which is embedded | PLAUSIBLE | **Accepted** in §2.2 (title + prose); the probe's definition stays only in §2.6 |
| L3 | Low | `CARRIER_Q` drops "bass boost" (headphones); `POLICY_Q` tags "return key" (laptops); there is no shipping tag | CONFIRMED | **Accepted as reporting:** carrier drops per leaf in the funnel; passed on to 3.3 / 3.4 in §8 |
| L4 | Low | The flag must go into `parse_leaf`'s product dict, because `_digest` and the round-trip test compare against it; the selector must never read it with a default | CONFIRMED | **Fixed** in §5 and T20 |
| L5 | Low | §2.4's rate is pooled while F21 reported medians | CONFIRMED | **Fixed:** "comparable with neither" stated; p90 index rule pinned |
| L6 | Low | A9's commit order proves when the rule was committed, not when the labels were first seen | CONFIRMED | **Fixed:** the ePQA fetch is logged after the rule commit (§6.7) |

## One change that is mine, not the reviewer's

The reviewer offered R2 as optional ("report it beside the first"). I made **R2 the selecting rule**
and R1 the reported one, because R1's failure is silent and R2's is loud (a pool that shrinks too far
trips the quota stop). This is decided before any data is seen. It is the author's call (spec open
question 1).

## For the author to decide

Carried into `spec.md` (open questions 1, 9, 10, 11): the answerability rule (R2 selecting) and the
one-hour blind audit; unanswerable questions as a separate stratum; the short-leaf fallback order;
the warranty-term filter on the title.

---

# Post-implementation review (`/ai-review`, 2026-10-20)

**Reviewer:** the `contract-reviewer` subagent, general pass over `docs/architecture.md` and `CLAUDE.md` (the
diff touches no contract, `.proto`, Redis schema or wire field). Scope: `git diff c9d65e1` plus the
uncommitted record edits. It ran the 322 tests and about 52 hand mutants in a copy of the tree (19 survived),
and could not read `data/v1-draft/`. **No frozen value, licence rule or provenance rule is broken; the rule
was not changed after a number was seen** (it diffed `ea63e5d` against `ee03e5e`: only the quota split, the
fallback record and the reporting fix). The report is data; each row says what I checked and did.

| # | Finding | Rating | Resolution |
| :-: | :--- | :--- | :--- |
| 1 | The new constants and R2's pass 1 were pinned by no test: a changed seed, `GENERIC_DF`, the generic test's `>=` or denominator, or a dropped fallback record passed all 322 tests; the draw test was circular | CONFIRMED (mutants) | **Fixed.** A test pins the tracked manifest's whole `rule` block to the module constants; a golden `rank("B000000001")`; a direct `generic_tokens` test at the 10 % edge (1 of 10 generic, 1 of 11 not; a repeated word counts once); a default `select()` records `FALLBACK_APPLIED` |
| 2 | ADR-011's case for R2 rested on the model audit alone: it left out ePQA's recall 4 / 12 and NPV 116 / 124; "answerable-rich" is circular; the super-plan said R2-unanswerable "need no re-label"; the yield (≈ 410 of 1,180) was only in `audit.md` | CONFIRMED (text against evidence) | **Fixed.** ADR-011, the data card and the super-plan quote both checks, drop "answerable-rich", state the yield as an input to `K`, and ask 3.4 to re-label a sample of the R2-unanswerable ones too. The pool field is renamed `r2_answerable`, so it cannot be read as a label |
| 3 | The records disagreed on whether R2 stands; the test amendment was promised to ADR-011 and not there | CONFIRMED | **Fixed.** `approvals.md` records the author's decision with their words; ADR-011's Consequences record the amended test and why it is not a weakening |
| 4 | ePQA had no provenance entry in the data card | CONFIRMED | **Fixed.** A table row and a §1 entry: commit, sizes, hashes, CDLA-Sharing-1.0, use, and the citation the repository's README names for ePQA (xPQA, arXiv:2305.09249), read from the README at the pinned commit |
| 5 | An example in `audit.md` quoted a phrase that reads like a sheet item | PLAUSIBLE | **Fixed** with a made-up example |
| 6 | `make pqa-audit-sheet` overwrote a marked sheet | CONFIRMED (code) | **Fixed.** It refuses while any row is marked, unless `--force`; a test |
| 7 | The selection manifest's hash moves with the selector file and the unpinned llama-index-core, so it is not a reproducibility anchor | PLAUSIBLE | **Fixed in the record and the manifest.** The manifest records the chunker (256 / 40, llama-index-core 0.14.23); ADR-011, the super-plan and the evidence name **the products digest** `d373c4b0…` as the anchor |
| 8 | The question-count buckets were applied to characters: every `chars.hist` was zeros | CONFIRMED | **Fixed:** no histogram for characters |
| 9 | "Almost all phones" overstated it: 93 of 143, with 39 TVs or headphones | CONFIRMED | **Fixed** in ADR-011 and `answerability.md` |
| 10 | Gaps against A6 / A13: no fixture for the band edges or the exact-repeat exclusion; only the sum of `MATCHED_LINES` pinned; `CONTAINMENT` unpinned; the wrong-hash branch and `recall_reweighted` untested; the generic file's hash check untested | CONFIRMED (mutants) | **Fixed:** tests at Jaccard exactly 0.45 and 0.99 and an identical pair; the per-leaf pins; 4 / 5 against 3 / 5 containment; a same-size changed file; the re-weighted recall against a hand computation; a changed generic file refused |

**After the fixes:** 333 tests in `experiments/` (11 new), lint clean. The selection was re-run twice: the 152
records and the generic tokens are **byte-identical** to before (products digest `d373c4b0…`), the pool
digest changed only by the rename (`50cdcb03…`), and the audit re-scores to the same `audit.json`
(`evidence/live-run.md`, last section). No finding is open.

## What the reviewer checked and found sound, in short

The licence (110 distinct strings in the tracked manifest, none an asin or text; only synthetic asins in the
diff); provenance (the consumed manifest hash, `builder_sha256` and `selector_sha256` all match the files);
every number in the records against the manifest; `iter_selection`; 33 killed mutants, among them every product
filter, the tag order, R2, the flag read without default, the pins, the re-check, `sort_keys` and the leaf; the
output shape against `load_records`, `lane.go` and `corpus_gate.py`; and that the fallback, the reporting fix
and the model audit are each recorded honestly.
