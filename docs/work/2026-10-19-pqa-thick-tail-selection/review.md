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
