# Design — policy-documents (super-plan item 3.3)

**Draft 2** · 2026-10-20 · merges `impact.md` and `review.md` (verdict *sound, with changes*; every
finding accepted). It uses the **proposed** answer to every open question in `spec.md` (1–10). An
answer that differs changes the section that names it.

*Changes from draft 1:* the undeclared-value rule and a fourth axis, `kind` (H1); the `terms` field
and the numbers rule (H2); siblings as minimal pairs (H3, question 9); region framed as where
service is asked for, and a stratum per axis (M5); Amazon for both laptop sides (L1); ASCII only
(L2); terms checked in chunk 0 (L3); a split needs two different, concrete terms (M3, M4); W8 allows
a recorded §7 fix (M6); §10, what 3.6 inherits.

## 1. What gets built

| Artefact | Tracked | What it is |
| :--- | :---: | :--- |
| `data/policies-v1/{doc_id}.json` × 13 | yes | The policy records (§2, §3). The source of v1's policies, **not a dataset version**: never pass it as `VERSION=` or `DATASET_VERSION` |
| `experiments/scripts/check_policies.py`, `make policy-check` | yes | The checker (§6). No Redis, no Ollama |
| `CONDITION_AXES`, `condition_hits()`, `check_g5()`, `load_policy_records()` in `corpus_gate.py` | yes | The scan, written once; G5 joins stage 1 (question 7) |
| `experiments/tests/test_check_policies.py`, new cases in `test_corpus_gate.py` | yes | Fixtures in `tmp_path` on both sides of every check, and one test over the tracked folder |
| `evidence/sources.md` (this trail) | yes | URL, fetch date and the one line that states each term |
| `data-card.md` §2, Schemas, §7, Ethics · `architecture.md` · `super-plan.md` rows 3.3 and 3.5 · `Makefile` comments · ADR-012 | yes | Records |

The order of work, which the commit history must show:

```
step 1  access to data/ + count risky words in the 152 titles (U8)
step 2  fetch sources ──► term table (evidence/sources.md); apply §2's fallback
step 3  ONE commit: rules (§4) + word list (§5) + checker + G5 + tests          ← before any text
                         │
                         ▼
step 4  draft one family (siblings side by side, from the term table only)
                         │
                         ▼
        make policy-check ──fail──► change the TEXT, never a rule or a word
                         │ pass
                         ▼
step 5  author reads each document ──reject──► change the text
                         │ approve (one line each in approvals.md)
                         ▼
steps 6–9  data-card, architecture.md, super-plan, ADR-012 ──► /verify, /ai-review, /done
```

No retrieval, embedding or LLM run happens in this item (P7). The first one is G1 / G2 at 3.6.

## 2. The document set

`doc_id` is **derived from the fields**: `policy-{policy_kind}-{category}`, plus `-{value}` when
`condition` is set (checked, P3). The singular `return` matches `select_pqa.POLICY_Q`, and it keeps
v1's `policy-return-electronics` apart from dev-v0's `policy-returns-electronics`.

| `doc_id` | `condition` | Main term (to confirm) | Source to check |
| :--- | :--- | :--- | :--- |
| `policy-return-phones-unopened` | packaging = unopened | 14 days, no fee | Best Buy, activatable devices |
| `policy-return-phones-opened` | packaging = opened | 14 days, $45 restocking fee | Best Buy |
| `policy-return-laptops-new` | grade = new | 30 days | Amazon, standard returns |
| `policy-return-laptops-renewed` | grade = renewed | 90 days | Amazon Renewed Guarantee |
| `policy-return-electronics` | — | 30 days | Target, electronics |
| `policy-return-furniture-unopened` | packaging = unopened | 365 days | IKEA |
| `policy-return-furniture-opened` | packaging = opened | 180 days | IKEA |
| `policy-warranty-phones-domestic` | region = domestic | ~1 year | a phone maker's US limited warranty |
| `policy-warranty-phones-international` | region = international | to find | the same maker, on service outside the US |
| `policy-warranty-laptops-domestic` | region = domestic | ~1 year | a laptop maker's US limited warranty |
| `policy-warranty-laptops-international` | region = international | to find | the same maker, on service outside the US |
| `policy-warranty-electronics` | — | ~1 year | a TV maker and a headphone maker |
| `policy-warranty-furniture` | — | multi-year | IKEA or an office-chair maker |

The store combines four retailers' return policies (Best Buy, Amazon, Target, IKEA), one per
department. This replaces ADR-002's "14 / 30 / 30 / 90": furniture becomes 180 / 365 and laptops
gain a 90-day side. ADR-012 records it.

**Titles are fixed now** (the title is embedded, in chunk 0 only), with the canonical value word:
`{Kind} - {Department}[, {Value}]`: `Return Policy - Phones, Opened`, `Return Policy - Laptops,
Renewed`, `Warranty - Phones, International Service`, `Return Policy - Electronics`. ASCII hyphen.

**Region is where service is asked for**, for a product bought from the store: *"is it covered if
I use it in India?"*, the shape of the real PQA traffic (`data-card.md` §2). A fixed term, not a
personal one, so the Ethics line's locale rule does not apply; `data-card.md` says so in one
sentence.

**Which stratum each axis can feed** (3.4 uses this):

| Axis | Where | A natural same-product pair? | Feeds |
| :--- | :--- | :--- | :--- |
| packaging | phones and furniture returns | yes: "return it if opened?" against "unopened?" | B-within |
| region | phones and laptops warranty | yes, as framed above | B-within |
| kind | every department | yes: "warranty period?" against "return period?" | B-within |
| grade | laptops returns | **no**: a listing is either new or renewed | category-level pairs, or B-cross if a renewed product exists (U8) |

**Fallback, fixed now.** A split stays only if both sides have a primary source **and** concrete
terms (W3) **and** the two terms differ. Otherwise the family becomes one document without that
condition, and the count falls below 13. A condition or a term is never invented.

**The G5 numbers for `data-card.md` §7.** *Before*: the split families that hold both values (5,
or fewer after the fallback): each would put an opposing pair under one `doc_id` if not split.
*After*: the documents naming an undeclared value, which must be 0. The checker prints both.

## 3. The schema

```json
{ "doc_id": "policy-return-phones-opened",
  "title": "Return Policy - Phones, Opened",
  "category": "phones",
  "policy_kind": "return",
  "condition": { "axis": "packaging", "value": "opened" },
  "terms": ["14 days", "$45"],
  "text": "..." }
```

- Exactly these seven fields.
- `category` is one of the four departments, read from `build_pqa.LEAVES` (no second copy). Never
  empty, never null: v1 has no global policy (question 1).
- `policy_kind` is a key of `select_pqa.POLICY_Q`: `return` or `warranty`.
- `condition` is `null` or one axis and value from `CONDITION_AXES` (§5; not the `kind` axis).
- `terms` lists the document's terms, the main one first. Each is `{digits} {day|days|month|months|year|years}`,
  `${digits}`, or exactly `not covered` / `not accepted`: only units the numeric arm already reads,
  so the corpus never forces a `reuse/` edit. At most one duration and at most one amount.
- `text` is ASCII paragraphs separated by blank lines. No Markdown.
- **`policy_kind`, `condition` and `terms` are inert for ingest.** `record_to_document` embeds only
  title and text and copies only `doc_id`, `kind`, `category`, `title` into metadata
  (`ingest.py:54-70`); measured by the impact analysis. They must **never** reach chunk metadata,
  Redis or the gateway: a condition tag on the hit path is the rule term `Final_Proposal.md:435`
  rejected. P11 pins it.

## 4. The writing rules (committed before the first document)

- **W1 — Original text.** Modelled on real pages, never copied. Drafted **from the term table
  only**, with no source page in context. From a source only the term is taken.
- **W2 — One outline per kind, 550–800 words.**
  *Return:* who and what it covers, and the window · the condition the item must be in, what to
  include · how to start a return · the refund: method and timing · exceptions · exchanges.
  *Warranty:* what it covers and for how long · what is covered · what is not · how to claim ·
  repair, replacement or refund · proof of purchase and transfer.
- **W3 — The main term is concrete and opens the document**: a number with its unit, or "not
  covered" / "not accepted". It is written exactly as in `terms`, the number and unit attached
  ("14 days", never "14 calendar days": the numeric arm then loses the unit, and a correct cached
  answer is refused). It falls in chunk 0 (checked).
- **W4 — Conditions.** A document names **only its declared value**; one with no condition names
  none. It never names its sibling's value, not even to exclude it ("not valid outside the United
  States" is a violation in the domestic document), and never points to its sibling. A return
  document never names warranty words, and a warranty document never names return-window words
  (the `kind` axis). A family not split by an axis does not discuss it.
- **W5 — Siblings are minimal pairs** (question 9). Same outline, and the **same text** in every
  section, except that each section names the document's own value once and the term sentences
  differ. So which sibling ranks first turns on the condition word, which is what RQ2a asks about.
  The checker prints, per chunk, whether it names its value.
- **W6 — Department, not product.** About the department's kind of product ("phones", "TVs and
  headphones", "chairs and desks"); no brand, model or product feature. **One term per document**,
  even in a two-leaf department: if TV and headphone (or chair and desk) sources differ, the author
  picks one before writing and the data card says so.
- **W7 — No second condition, no dynamic content.** The only numbers in a text are its `terms`; no
  duration in words ("one year", "a year"). No member, card-holder, holiday, receipt or state rules.
  No product prices, stock, order status, dates or promotions. Refund timing is written without a
  number ("within a few business days").
- **W8 — Text is never changed to move a retrieval result.** The one exception is a recorded §7 fix
  at 3.6 that cites the gate output behind it, made before any reuse rule runs. After the freeze any
  change is a new `dataset_version`.
- **W9 — ASCII only** in title and text: no curly quotes, Unicode dashes or non-breaking spaces
  (they defeat the word list and change how the numeric arm attaches units). Checked.

## 5. The word list

Lower case; a match may not touch an ASCII letter or digit on either side (so `opened` does not
match inside `unopened`, `new` not inside `renewed`, and `un-opened` *does* hit `opened`: a loud
error, not a silent one). Errs wide: a wrong hit costs a reworded sentence, a miss is silent.

| Axis | Value | Words |
| :--- | :--- | :--- |
| `packaging` | `opened` | opened, open-box, open box |
| | `unopened` | unopened, sealed, factory-sealed |
| `grade` | `new` | new, brand-new — **scanned only in the grade family**, as they are ordinary English elsewhere ("a new gift card") |
| | `renewed` | renewed, refurbished, pre-owned, second-hand |
| `region` | `domestic` | domestic, US model, US version, U.S. model, U.S. version |
| | `international` | international, abroad, overseas, outside the United States, outside the US, outside the U.S., imported, country of purchase |
| `kind` | `return` | return window, return period, restocking |
| | `warranty` | warranty, warranties |

`used` is **not** listed: "if the item has been used" is ordinary return wording and would fail
every document. The list is a floor, not a proof (§7.2).

## 6. The checker and G5 — function contracts

**`corpus_gate.py`** (G5; this closes 3.5):

- `CONDITION_AXES: dict[str, dict[str, tuple[str, ...]]]` — §5, beside `SIM_FLOOR`.
- `condition_hits(text: str) -> dict[str, dict[str, list[str]]]` — per axis, each value whose words
  appear, with the words. Pure.
- `check_g5(records: list[dict]) -> Criterion` — `policy-` records only (products are ignored). The
  allowed values of a document are its declared condition and `kind = policy_kind`; grade's plain
  words are skipped unless the document's family is split by grade. **Every other hit fails**, with
  the document, the value and the words; when two values of one axis hit, the detail **names both**
  (3.5's Done-when). Every offender is reported in one pass. Summary: `declared axes, lexical: N
  families split, M of D documents clean` (M2).
- `load_policy_records(dir) -> list[dict]` — every `policy-*.json`, problems reported in one pass
  (as `load_corpus_doc_ids` does, and unlike `rag.ingest.load_records`).
- Stage 1 runs G3, G4 and G5. "Four" becomes "five" in the docstring, the `--structural-only` help,
  `emit`'s freeze message and `data-card.md` §7. The freeze message and §7 keep **the author's read
  as part of G5**: the scan alone does not prove §7's G5. G5's counts go into the `--report` JSON.
- `corpus_gate` never imports `check_policies` (no cycle).

**`check_policies.py`** (`make policy-check`; default `data/policies-v1`):

- Loads through `rag.ingest.load_records`. Every record must be `policy-`.
- **Schema** (P3): §3's fields and values; the derived `doc_id`; one record per (`policy_kind`,
  `category`, `condition`); every family complete (one document with no condition, or two with one
  axis and both its values); the title holds the declared value word; ASCII (W9).
- **Terms and numbers** (P12): `terms` format; at most one duration and one amount; siblings' `terms`
  differ (M3); every digit run in title and text lies inside an occurrence of a `terms` entry; no
  duration in words (`one|two|…|ninety|a|an` + `day|week|month|year`).
- **Chunks** (P1, P4, P13): `splitter.get_nodes_from_documents([record_to_document(r)])` with
  `SentenceSplitter(CHUNK_SIZE, CHUNK_OVERLAP)` from `rag.config`, the path ingest takes (metadata
  counts against the chunk size while splitting). ≥ 3 chunks; chunk 0 holds `terms[0]`; no two chunk
  texts identical after stripping white space.
- Calls `corpus_gate.check_g5` (P2).
- Prints, per document: words, chunks, chunks naming its value, terms in chunk 0. Then the splitter
  (chunk size, overlap, `llama-index-core` version), G5 before / after, and the token Jaccard of each
  sibling pair (**a statistic, not a gate**).
- Exit 0 on pass; 1 on any failure, all printed; 2 if the folder is missing or empty.

## 7. Failure modes — silent ones first

1. **Splitter drift.** `llama-index-core` is unpinned (`>=0.11`; 0.14.23 installed). Another version
   can split the same text differently, and a document at 3 chunks drops to 2 with no error.
   *Mitigation:* the 550-word floor (measured: 391 words → 3 chunks, 494 → 4, so one chunk of
   margin); the version is printed; 3.6 re-runs the check and pins (§10).
2. **The scan is a floor.** It sees only §5's words: "if the seal is broken" names `opened` and
   passes. *Mitigation:* the undeclared-value rule (one stray word fails), the wide list, W4, and the
   author's read (P8), which stays part of G5.
3. **The corpus shapes RQ2a.** Siblings written very differently are easy to separate; nearly the
   same, hard. *Mitigation:* W5 fixes minimal pairs in advance, so the result is about the condition
   word; W8 forbids tuning; the sibling Jaccard and the per-chunk value count are reported.
4. **Reading the support gate per pair.** The numeric arm accepts a number if **any** fresh chunk
   holds it (`support_numeric.go:185`), and with minimal pairs the sibling's chunk 0 will often be in
   the fresh top 5. One direction is blind to both arms: "no fee" has no number, and `no` is a
   stopword. *Mitigation:* nothing is claimed "by construction"; `data-card.md` §2 records, per pair,
   whether it differs by a number or by words, and in which direction; 3.6 measures how often the
   fresh top-k holds the sibling's term chunk (§10).
5. **Unit detachment.** "14 calendar days" in evidence carries no unit, so a correct "14 days" is
   refused. *Mitigation:* W3, and P12 checks the `terms` form verbatim.
6. **A second condition.** A member or holiday window, or two terms for two leaves, puts two answers
   under one `doc_id` on no listed axis. *Mitigation:* W6, W7 and the numbers check.
7. **Exact ties.** Identical text embeds identically, and the index's tie order then picks the
   rank-1 document (the namespace). *Mitigation:* P4. Minimal pairs differ by the condition word in
   every section, so their chunks are near-identical, never identical.
8. **Lane drift.** ~52–78 policy chunks instead of 4. A product question that retrieves one policy
   chunk scores `PolicyFraction` 0.2, the default `Lo`, and goes to POLICY (impact §6). The dev-v0
   band evidence does not carry over. *Mitigation:* W6. Measured and swept at 3.6, not fixed here.
9. **The condition reaches the hit path.** *Mitigation:* the fields stay in the source record; P11.
10. **A broken join** (`category: "phone"`). *Mitigation:* P3.
11. **Copied wording** makes the release claim false. *Mitigation:* W1; `sources.md` quotes one line
    per term.

## 8. Unknowns that still need verifying

- **U1 — The warranty terms are not fetched yet**, and international ones may be vague (M4). Plan
  step 2; §2's fallback applies.
- **U2 — Is 550 words enough on real prose?** Measured on synthetic text only. The checker answers
  it per document.
- **U3 — Lane and namespace behaviour on ~52–78 policy chunks.** 3.6.
- **U4 — How the FLAT index orders exact ties.** Avoided by P4, not answered.
- **U5 — Access to `data/`.** Read and Bash are denied there in this session. Plan step 1.
- **U6 — Condition questions for 3.4.** None of the 127 pool policy questions is tagged by
  condition; most condition questions will be constructed. W3 makes each condition document answer
  its own case in its opening section.
- **U7 — Two-leaf departments.** W6's one-term rule; the sources decide whether it bites.
- **U8 — Do any of the 152 titles say "Renewed", "International Version" or "No warranty"?** 3.2 did
  not filter them, and such a title can contradict a policy document. One grep at plan step 1; if
  any, the author decides before step 3 (3.2's selection is frozen by ADR-011, so changing it
  reopens 3.2).
- **U9 — Does the embedding rank the right sibling first?** `opened` / `unopened` is close to a
  negation. 3.6 (G1 / G2).
- **U10 — How often does the fresh top-5 hold the sibling's term chunk?** 3.6, no LLM.
- **U11 — Which chunk positions do questions retrieve?** If almost always chunk 0, the gradient
  comes from mixing many documents' chunk 0s, and "≥ 3 chunks gives a gradient" overstates. 3.6.

## 9. The proposed answers, with reasons

1. **Shipping: drop.** No shipping question in the pool; no condition; an empty join key; close to
   dynamic content.
2. **Warranty: as published.** Nothing is invented. If phones, laptops and electronics share ~1 year,
   `data-card.md` §2's "genuinely differ" holds only through furniture and the region pairs, and the
   sameness measures the namespace cost. **If both region splits are dropped, requirement 2 is not
   met for 3 of 4 departments**, and ADR-012 says exactly that.
3. **Furniture: IKEA, 180 / 365.** One source for both sides.
4. **Phones opened: Best Buy.** One source for the window and the fee.
5. **`data/policies-v1/`, tracked**, listed in `architecture.md` as the source of v1's policies, not a
   dataset version.
6. **Claude drafts from the term table only, the author approves each document,** and
   `data-card.md` says so.
7. **Fold G5 in**, narrow: one constant and one pure function, no new gate mode. Its PASS says
   "declared axes, lexical", and the author's read stays part of G5.
8. **ADR-012 (data):** the set, the schema, the terms and sources, the rules; that the store combines
   four retailers and replaces ADR-002's windows; that `condition` and `terms` never reach metadata.
9. **Siblings: minimal pairs.** Rank 1 then turns on the condition word, so differences between
   axes are about the condition, not about drafting. The other option: only the opening section
   names the value, and the rest is worded freely; it reads more like a real page, but drafting
   then moves the result.
10. **Keep the grade split.** Real stores split it, and it adds a lookalike pair and a namespace for
    G1. Recorded as feeding no natural same-product pair. The other option: drop it (12 documents).

## 10. Carried to 3.6

- Assert that `data/v1/`'s policy files equal `data/policies-v1/` byte for byte (review L4).
- Record a digest of (`chunk_id`, sha256 of the chunk text) beside the file digest, and pin
  `llama-index-core` (L5, impact §9 point 4). Re-run `make policy-check` at the freeze.
- For each B-within condition pair: does the fresh top-k hold the sibling's term chunk (M1, U10)?
- The lane band on v1: dev-v0's evidence does not carry over (impact §6).
- The numeric unit list freezes with the corpus; v1's policies use only days, months, years and `$`.
