# Pre-thesis Sweeping

**Opened:** 2026-09-15 · **Purpose:** close out everything still sitting in the pre-thesis phase, so
the thesis phase starts from a clean base. **Lifespan:** delete this file once every row below is
either done or has moved into an ADR, a requirements document, or the super plan.

**Authority.** This file **points at** `docs/` and never restates it. Where it and `docs/` disagree,
`docs/` is right. Where it records a decision not yet in `docs/`, that decision **is not yet made** —
it is a proposal waiting for an ADR.

---

## Status board

| # | Concern | State | Blocked on |
| :---: | :--- | :--- | :--- |
| **0** | **`docs/` does not know about the approved pivot** | 🟢 **done 2026-09-21** — ADR-035…038 written, and carried into `interfaces.md` (v0.9), `experiment-protocol.md`, `data-card.md` (G5), `CLAUDE.md` | — |
| 1 | Rewrite `Pre-Thesis_Report_Full.md` (+ `Final_Proposal.md`) | 🟡 C1 alignment done 2026-09-15 | §4.2 waits on #5 · §5.1 waits on #3 |
| 2 | Refactor `docs/` · `.docs/` · `.claude/` | 🟡 §2.3 deletes and §2.6 drift done 2026-09-21; §4.5 tracking resolved (both now tracked) | the rest waits on decisions in #3, #4 |
| 3 | Super plan + FR/NFR/RR | 🟡 **shape signed off 2026-09-21; both files created empty** (`docs/requirements.md`, `docs/super-plan.md`) | filling them — and `time_line.md`'s retirement waits on #4 |
| 4 | Harness re-engineering (scope-based, week-free) | 🔴 not started | two open decisions below |
| 5 | Dataset: Amazon-Reviews-2023 + AmazonQA → **Amazon-PQA** | 🟢 **done 2026-09-21** — probe run (§5.6), adopted by **ADR-039**, `data-card.md` §1/§3 rewritten. Redistribution stays **closed**: build script + hash manifest | — |

---

## 0. The blocking finding

The advisor approved the pivot in `.docs/work/mvp-advisor-demo/Recommended_system.md` §5–§6, but the
**decision log has no record of it.** ADRs stop at **ADR-034**. Nothing exists for the support gates,
the retirement of the unfiltered similarity-only phase, the retrieval contract change, or
condition-splitting.

Everything else in this file stands on what is actually decided, so this goes first.

### 0.1 ADRs owed — ✅ written 2026-09-21

All four are in `docs/decisions.md`, and the documents they touch were edited in the same pass rather
than left to drift (the lag `two-lane-cache`'s trail had to record as "still owed" after ADR-032).
`interfaces.md` is at **v0.9**; `data-card.md` §7's gate is at **five** criteria; the run manifest
gains `support_gate`, because configuration 4 is two arms and `(config_id, mutation)` no longer
identifies a run on its own. Execution trail: `.docs/work/pre-thesis-sweeping/`.

**Still owed as code, not as decisions** — ADR-035's gate, ADR-036's removals and ADR-037's seam
work are recorded, not implemented. Build order is `Recommended_system.md` §4/§8, and F1 precedes it.


| ADR | Title | Touches | Why it cannot wait |
| :--- | :--- | :--- | :--- |
| **035** | Adopt the answer–evidence support gates (`S_lex` at [6]'s published `τ_s = 0.6`, plus the numeric arm) | `decisions.md` | The whole C1 reframe rests on it |
| **036** | Retire the unfiltered similarity-only phase, `τ_high`, and the inline `similarity_only_decision` | `decisions.md`, `experiment-protocol.md` | Changes how *decisions-changed-by-provenance* is computed |
| **037** | `Retrieve` returns chunk text | `interfaces.md` §B (**frozen**), `contracts/rag/v1/rag.proto`, both sides of the seam | **The support gate cannot run at all without it** |
| **038** | Condition-splitting as a `v1` corpus requirement | `decisions.md`, `data-card.md` | Cheap before the freeze, impossible after |

### 0.2 Two live items the pivot does not clear

- **F1 — Ollama overrides `OLLAMA_NUM_PARALLEL` to `-np 1`.** The permit pool may be bounding to a
  concurrency the model server never offers, which means any shed rate measured so far describes the
  harness rather than the gateway. **No admission-control number is citable until this resolves.**
  `Recommended_system.md` §4 ranks it first for exactly this reason, and it is still open
  (`worklog/W08.md`, two entries).
- **Task `two-lane-cache` is open with the workflow deliberately bypassed.** Its own `approvals.md`
  records: no spec, no impact, no plan, `READY_TO_IMPLEMENT` written by hand, branch not mergeable,
  three unmet prerequisites. It has to be closed properly or explicitly abandoned before the new
  harness (#4) replaces the workflow that opened it.

---

## 1. Rewrite the report and the proposal

**Done 2026-09-15 — C1 alignment only.** Both documents now carry the reframed claim consistently:
the namespace-partitioned containment rule plus the answer–evidence support gate; the retirement of
the unfiltered phase and `τ_high`; the residual (same-evidence, opposite-condition queries) stated
*inside* the claim; the headline as a frontier rather than a speedup; condition-splitting as a corpus
requirement; config 4 split into two ablation arms. Two references added and verified by fetching the
sources: **[26]** Proof-Carrying Numbers, **[27]** The Semantic Illusion.

### 1.1 Decisions taken while doing it — confirm or reverse

1. **The static-cache ablation moved from droppable to non-negotiable.** Retiring the inline
   counterfactual makes *decisions-changed-by-provenance* a cross-configuration join, valid only where
   both runs saw identical cache state. The old drop order listed the static arm at position 5 **and**
   called that metric non-negotiable; both could not hold.
2. **One differentiator against GroundedCache was withdrawn.** Adopting its fourth gate makes the
   remaining delta smaller than the proposal previously claimed. Written out plainly rather than
   quietly dropped.
3. **`τ_s` is pinned at the published default, not swept.** Sweeping it would make five free
   parameters against the baseline's one — worsening the unequal-tuning objection — and would turn a
   citation into a result needing its own defence. Ships as an on/off ablation arm.
4. **`τ_high` retired, not disabled.** A threshold set to a value believed unreachable *was* reached:
   `sim >= τ_high` with a literal repeat re-embedding to a bit-identical vector gives cosine exactly
   `1.0`. It served a reuse with no provenance check at all.

### 1.2 Still to rewrite

- **§4.2 / §9.3 dataset sections** — blocked on #5. Currently describe the Amazon-Reviews-2023 ×
  AmazonQA join and its unverified join rate. If PQA is adopted, that entire risk paragraph is deleted
  rather than edited.
- **§5.1 phase plan** (report) and **§11 timeline** (proposal) — blocked on #3. Both currently restate
  a plan that #3 replaces.
- **§10.1 verification matrix** — the ⬜ rows (FreshCache, serving-scheduler) are this phase's stated
  exit criterion and are still unverified.
- **Two unverified numbers** are carried in both documents with explicit ⚠️ markers and must be
  checked against the GroundedCache PDF before the thesis document or any slide: the **+0.12–0.13**
  unsafe-rate increase when the support gate is removed, and the **1.95× → 1.04×** speedup collapse
  with all gates enabled.

---

## 2. Refactor `docs/` · `.docs/` · `.claude/`

### 2.1 Keep untouched — the spine

`decisions.md` · `interfaces.md` · `experiment-protocol.md` · `data-card.md` ·
`design/architecture.md` · `defense_demo.md` · every `learning/NN-*.md` · all four `.docs/ai/*`.

### 2.2 Archive, do **not** delete

The four pre-thesis task trails (`w5-feasibility-spike`, `w5-corpus-pipeline`,
`w6-rag-gateway-skeleton`, `proposal-research-spine`) and `worklog/W05|W06|W08.md`.

Reason, not sentiment: `.docs/README.md` and `worklog/README.md` both state these exist to write the
**design chapter and the evaluation chapter** — "what did I do, in what order, and why", a question
memory will not answer in December. `W08.md` alone holds the μ_hit probe numbers, the G1 = 0 / G2 = 0
shakedown result, and the reasoning behind ADR-030…033. Deleting it destroys evidence, not clutter.

### 2.3 Delete

~~`.pytest_cache/` · `.ruff_cache/` · `docs/.DS_Store` · `.claude/scheduled_tasks.lock`~~ — **deleted
2026-09-21**, and all four are now in `.gitignore` so they cannot come back as tracked files.
Still to do: prune `.claude/settings.local.json` (**41 allow entries**, many one-shot junk such as
`Bash(kill 8460)` and single-use `awk` invocations).

### 2.4 Reclassify

`.docs/work/mvp-advisor-demo/` is filed as a *task trail* but now holds **approved decisions**. Split
it: the decisions become ADRs in `docs/` (§0.1), the rest archives.

### 2.5 Add

The requirements document and super plan (#3); the ADRs (§0.1); a replacement for `time_line.md`,
which is organised by week and cannot survive #4.

### 2.6 Drift found

- ~~`CLAUDE.md` and `.docs/ai/rules.md` cite **`docs/Final_Proposal.md`**~~ — **fixed 2026-09-21**
  (three references in `CLAUDE.md`, one in `.docs/ai/review-checklist.md`; `rules.md` had none). The
  files still live at **`docs/learning/`**, which remains wrong as *placement*: two top-level thesis
  documents inside a folder named `learning/`. Moving them is #2's call, since `docs/learning/` is
  gitignored as a whole and a move changes what is published.
- **Also fixed 2026-09-21, found while doing the above:** `CLAUDE.md` still stated C1 as *"retrieval
  provenance beats embedding similarity"* — the claim ADR-026 narrowed and the pivot replaced — and
  still described `data-card.md` §7's gate as **three** criteria when it had been four since ADR-032
  and is now five. Both corrected.
- **A vacuous pass in the Makefile**, found by running `make verify` for the base commit:
  `command -v X && X … || echo "SKIPPED — not installed"` printed the not-installed message when the
  tool was **present and failing**, and exited 0. It had been hiding a live ruff error in
  `fetch_corpus_v1.py`. Fixed, and the error with it.

---

## 3. Super plan + FR / NFR / RR

Agreed in shape. Three things to settle first.

1. **Four plan documents would exist, not one.** Today: `docs/time_line.md`, `Final_Proposal.md`
   §11/§12/§13, report §5.1. Proposal: the super plan becomes the single source for **execution**;
   §12 (drop order) and §13 (deliverables) stay where they are because many documents cite them, and
   `time_line.md` is retired into it.
2. **Split the requirements three ways, not two.** Most of this project's binding constraints are
   *experimental obligations* rather than runtime qualities — frozen values, green memory pressure,
   δ ≤ 5 %, swept-not-hand-set, pre-registered nulls, tune-on-validation/report-on-test. Filing them
   under NFR buries them. Proposed: **FR** (system behaviour) · **NFR** (performance, reliability,
   observability) · **RR — Research Requirements** (measurement validity). RR is what defends the
   thesis in front of the committee.
3. **Traceability is the point.** Every super-plan item cites `FR-xx / NFR-xx / RR-xx` **and** its
   ADR. That chain — requirement → design → code → measurement — is what makes the work auditable.

**Create empty first, fill only after final sign-off.** Confirmed.

---

## 4. Harness re-engineering

### 4.1 Week coupling — the actual blast radius

**11 files**: `hooks/lib.sh` (`current_week()`, `week_row()`, `RUNWAY_LAST_WEEK`),
`hooks/inject-context.sh`, `hooks/gate-check.sh`, `hooks/done-check.sh`, and the commands
`week` · `log` · `gate` · `done` · `task` · `task-status` · `consistency`.

### 4.2 Keep — not week-coupled, still correct

`/approve` · `/verify` · `/ai-review` · `/rca` · `/adr` · all four subagents · and above all
**`frozen-guard.sh`**, which is the real protection here: changing a frozen value produces no error
and silently voids every prior measurement.

### 4.3 Change

`gate-check.sh` from "W8 onward" to "by scope" · `lib.sh` loses the week block · `/week` `/log`
`/gate` replaced.

### 4.4 Add

`/feature` · `/bugfix` · `/refactor` · `/investigate`, plus a **`design-reviewer` (opus)** subagent —
this does not exist today; `impact-analyst` answers blast radius, not "is this design sound, what is
the hidden risk".

Scope ladder as described: **Large** = Spec → Impact → Design (sequence / activity / class diagrams,
function contracts, failure modes, edge cases, unknowns to verify) → opus design review →
Implementation plan → implement + unit tests → verify → done. **Medium** and **Small** collapse phases
— which phases exactly is still open.

### 4.5 ⚠️ Correction to what was said on 2026-09-15

I previously recommended keeping the durable task trail in `.docs/work/` "because it is committed".
**That is wrong.** `.gitignore` lines 6–7 ignore **`.claude/` and `.docs/` entirely.** Both of their
READMEs claim otherwise — `.claude/README.md` says *"Tooling is tracked; only `settings.local.json`
and `state/` are ignored"*, and `.docs/README.md` says *"It is committed."* Neither is true.

Consequences:

- ~~The task trail … **has no version history and no remote copy.**~~ **Resolved 2026-09-21**: the
  author chose to track both. `.gitignore` now ignores only `settings.local.json`, `state/` and the
  scheduled-tasks lock; `.claude/README.md` dates the correction rather than reading as if it had
  always been true. `docs/learning/` stays ignored — that one is deliberate (§6).
- The choice in #4 between `.claude/current-task` and `.docs/work/<slug>/` is **not** a
  tracked-versus-untracked choice today. Both are untracked.
- The two READMEs must be corrected, or `.gitignore` changed, or both — but the mismatch cannot stand,
  because someone will rely on one of them.

### 4.6 Two decisions still open

- **Where the task log lives**, given 4.5. Recommendation unchanged in shape (pointer in `.claude/`,
  durable trail in `.docs/work/`) but it now needs `.docs/` to actually be tracked to mean anything.
- **What replaces the worklog.** Dropping weeks removes the chronology and the hours, both of which
  the write-up needs. Proposal: `docs/worklog/journal.md`, append-only, dated, no week structure.

---

## 5. Dataset

### 5.1 The finding

**Amazon-PQA deletes the join problem rather than reducing it.** Each PQA record carries
`question_id, question_text, answer_text, asin_id, bullet_points, product_description, brand_name,
item_name, is_yes-no_question, yes-no_answer` — the product content sits **in the same record as the
question**. `Amazon-Reviews-2023` is then not needed at all, so `asin` vs `parent_asin` stops being a
risk to measure and becomes a risk that does not exist.

| Property | Value |
| :--- | :--- |
| Licence | **CDLA-Permissive-1.0** (AWS Open Data Registry) → redistribution with attribution |
| Scale | 10 M questions · 20.7 M answers · 1.5 M products · **100 subcategories** (Aug 2020) |
| Access | Public S3, no credentials: `aws s3 ls --no-sign-request s3://amazon-pqa/` |
| Shape | One JSON file per category, 67 MB – 700 MB each — download 3–5, not the 17 GB archive |

**This closes `data-card.md` §1's `TODO(W8)` redistribution question** for the product *and* question
halves, which is the blocker `worklog/W08.md` records against the `v1` freeze.

**Category granularity is a bonus for ADR-024 requirement 2** (per-category return *and* warranty
windows that genuinely differ): `chairs` `beds` `mattresses` `home_office_desks` ·
`earbud_headphones` `headsets` `monitors` `led_&_lcd_tvs` · `jeans` `fashion_sneakers` ·
`batteries` `led_bulbs` · `inkjet_printers`.

### 5.2 The cost

PQA has **no structured spec dictionary**. `rag/src/rag/ingest.py:product_to_text()` renders
`record["specs"]` as `- key: value`; PQA offers free-text `bullet_points` + `product_description`.
That is a change in the **corpus builder**, not the pipeline — and it arguably helps ADR-024
requirement 3, since prose chunks past `chunk_size` more readily than a spec table. The existing
`data/v1-draft/` (175 files) would be discarded.

### 5.3 What PQA still does not give

Policy documents and policy questions. Searched: **no public dataset of retail return/warranty
policies with questions exists.** Policies stay authored in-house, stratum B stays mostly authored,
and the limitation in report §4.5.2 stands unchanged. Non-Amazon alternatives are effectively absent —
the PQA literature is Amazon-dominated, hetPQA is also Amazon, ESCI was already rejected.

### 5.4 Before committing

Download **one** category file and measure the **questions-per-product distribution**. Strata A and C
need genuine natural paraphrase clusters per product; if PQA is thin there, the advantage over
authoring shrinks.

### 5.5 ⚠️ Live risk

~~`data/v1-draft/` — **175 files staged in git**~~ — **closed 2026-09-21**: unstaged, and
`data/v1-draft/` added to `.gitignore` alongside `data/v1/`. The files remain on disk and the script
regenerates them. Note that §5.6's licence finding means the *replacement* corpus inherits the same
constraint, so this exclusion is permanent rather than provisional.

---

### 5.6 PROBE RUN 2026-09-21 — the result, and two things it reverses

Run against the real data, not the documentation: `amazon_pqa_inkjet_printers.json` (128 MB,
complete) and `amazon_pqa_chairs.json`. No AWS CLI needed — the bucket serves over plain HTTPS.
Script: scratchpad `pqa_probe.py`.

#### ✅ §5.4's question is answered: PQA is **not** thin

| | `inkjet_printers` | `chairs` |
| :--- | ---: | ---: |
| products (`asin`) | 1,288 | **19,193** |
| questions | 92,070 | 88,268 |
| questions per product — mean / median / max | **71.5 / 8 / 5,741** | 4.6 / 2 / 367 |
| products with ≥ 2 questions | **82.5 %** | 58.3 % → **11,190 products** |
| products with ≥ 5 questions | **63.7 %** | 24.3 % → **4,664 products** |
| answers per question — mean / median | 2.4 / 2 | 2.1 / 1 |

**The two categories are thick in different ways, and both are usable.** Printers give *deep*
clusters on few products; chairs give *shallow* clusters on many. Since the workload needs a
distinct-query count `K` and ADR-027 derives cache capacity from it, either shape reaches `K` —
they just reach it with a different number of products, which is what the selection strategy has
to account for.

And they are **genuine paraphrase clusters**, which is what §5.4 actually asked. Across the
category, **43.6 %** of multi-question products carry at least one near-duplicate question pair
(content-word Jaccard 0.45–0.99, excluding exact repeats):

- *"can it print address labels?"* / *"Does it print labels?"* — **stratum C**, different wording,
  same grounding.
- *"Does this have usb slot? can i just insert usb stick and print?"* / *"Does it have usb slot? i
  can just insert usb and print?"* — near-literal, **stratum A**.

#### ⭐ An unlooked-for finding: PQA supplies **B-within traps naturally**

The same clustering surfaced pairs that look like paraphrases and have **different answers**:

- *"Does printer work with windows 10?"* / *"Will this unit work with Windows 7?"*
- *"will it work with an IPAD 2?"* / *"Does this printer work with an iPad and an iPhone?"*

Same product, same shape, one condition flipped — which is exactly **ADR-035's residual** and
exactly what `data-card.md` §2's **B-within** stratum is built to hold. Today those pairs would be
author-constructed, and report §4.5.2 / limitation 10 concedes that the measured residual is
*"partly a property of how carefully the author split conditions."* Natural traps weaken that
objection materially. **This is a reason to adopt PQA that neither §5.1 nor §5.4 anticipated.**

One product's twelve questions also span refurbishment, warranty period, ink, scanning and fax —
several distinct groundings per product, and *"Warranty period?"* arrives naturally, which is the
policy-side question the authored policy corpus has to join to.

#### ⚠️ Reversal 1 — the licence does **NOT** close `data-card.md` §1's `TODO(W8)`

§5.1 records *"Licence: CDLA-Permissive-1.0 (AWS Open Data Registry) → redistribution with
attribution"* and concludes the redistribution question is closed. **Two authoritative sources
disagree, and the more restrictive one is the dataset's own.**

| Source | Says |
| :--- | :--- |
| AWS Open Data Registry (`datasets/amazon-pqa.yaml`) | `License: https://cdla.dev/permissive-1-0/` |
| `s3://amazon-pqa/readme.txt` — which that same registry entry names as `Documentation:` | *"Permission to make digital or hard copies … for **personal or classroom use** … provided that copies are **not made or distributed for profit or commercial advantage** … **For all other uses, contact the owner/author(s). Copyright held by the owner/author(s).**"* |

That second text is the **ACM personal/classroom-use notice**, not CDLA-Permissive-1.0, and the word
"CDLA" appears **zero** times in the readme. CDLA-Permissive grants redistribution; the readme
grants personal and classroom copying and reserves everything else.

**What this changes.** Using PQA for this thesis is squarely covered — academic use is the granted
case, with the required citation (Rozen et al., NAACL 2021; the readme supplies the BibTeX).
**Publishing a derived corpus on a public git remote is not clearly covered**, which is the exact
question `data-card.md` §1 `TODO(W8)` asks. So the conclusion is the same as before the switch, and
it is the one **ADR-013 already anticipated**: keep `data/v1/` gitignored and ship a
**download + build script plus a hash manifest**, not the raw data. PQA deletes the *join* problem
(§5.1's real win) — it does not delete the *redistribution* problem.

#### ⚠️ Reversal 2 — §5.2's chunking claim is wrong as measured

§5.2 argues the switch to prose *"arguably helps ADR-024 requirement 3, since prose chunks past
`chunk_size` more readily than a spec table."* Measured:

| | `inkjet_printers` |
| :--- | ---: |
| product prose (5 bullets + description), median chars | **504** (≈ 126 tokens) |
| products estimated to yield ≥ 3 chunks at `chunk_size = 256` | **1.6 %** |

`product_description` is frequently **empty**; the bullets carry the content and they are short.
PQA products would ingest at roughly **one chunk each** — the same shape as `dev-v0`, which is what
`corpus_gate.py`'s G1 measured at **0 qualifying pairs**.

**This is less damaging than it first looks, and the distinction matters.** ADR-024 requirement 3 is
about **policy** documents, which stay authored in-house and are written to length deliberately.
`dev-v0`'s G1 failure came from having only **44 chunks in total**, so every question retrieved a
near-identical set; one PQA category alone supplies **~1,288** product chunks, so corpus *diversity*
is not the problem it was. What the measurement does kill is the claim that switching to PQA helps
requirement 3 — it does not help it at all, and requirement 3 rests entirely on the authored
policy half, exactly as it did before.

#### ⚠️ The readme's own field list does not match its own data

§5.1's field list is copied faithfully from `readme.txt` — and **the readme is wrong**. Verified
against the bytes:

| `readme.txt` says | the data actually has |
| :--- | :--- |
| `asin_id` | **`asin`** |
| `bullet_points` (one field) | **`bullet_point1` … `bullet_point5`** (five fields) |
| `is_yes-no_question` | **`question_type`** (`"yes-no"` \| `"WH"`) |
| `answer_text`, `yes-no_answer` | **`answers`** (list of `{answer_text}`), **`answer_aggregated`** |

A corpus builder written against the documentation produces **empty records silently** — the first
run of this probe returned "no parseable records" for exactly that reason. Whoever writes the
builder must read the bytes first.

#### Category dependence — select products, do not sample them

`inkjet_printers` has a median of 8 questions per product against `chairs`' 2 — a **4× difference
between two categories both named in §5.1's shortlist**. The distribution is also extremely skewed
*within* a category (printers: p99 = 958, max = 5,741), so the workload build must **select into the
thick tail**, never sample uniformly: a uniform draw from `chairs` returns mostly single-question
products, from which no stratum A or C pair can be built at all.

Corollary for ADR-024 requirement 2 (per-category warranty windows): the categories that
differentiate the policy corpus are chosen for *policy* realism, while product thickness varies
independently of that. The two constraints have to be satisfied together, and §5.1's shortlist was
assembled against the first one only.

#### The call this leaves to the human

1. **Adopt PQA?** The probe says yes on thickness, and adds the natural-B-within argument.
2. **Accept that redistribution stays closed** and that `v1` ships as a build script + hash
   manifest (ADR-013's path), rather than as tracked data.
3. **Which categories**, given the thickness varies by category and drives how many products are
   needed to reach the workload's distinct-query count `K` (ADR-027 derives capacity from it).

All three want an ADR once decided — this file records a proposal, not a decision (see Authority).

---

## 6. Loose findings, not owned by any single concern

| Finding | Risk |
| :--- | :--- |
| `docs/learning/` is gitignored — deliberately, to keep submitted prose off a public remote and avoid self-matching in plagiarism detection | The proposal and the report have **no version history**. The 2026-09-15 C1 rewrite is not recoverable. Consider a local backup or a private remote |
| `.claude/` and `.docs/` gitignored while both READMEs claim they are tracked (§4.5) | The write-up's raw material is unbacked, and two documents actively mislead |
| `settings.local.json` — 52 allow entries, much of it one-shot | Noise; obscures which permissions are real |
| Two GroundedCache figures unverified (§1.2) | They now carry weight in the C1 argument in both documents |

---

## Suggested order

**0 → 5 → 3 → 4 → 2 → 1(remainder)** — confirmed by the author 2026-09-21. **0 and 5 are done. 3's shape is signed off and its two files exist, empty by design.** Next: **4** (harness), which also unblocks retiring `time_line.md` and the remainder of **2**.

ADRs first, because everything else cites them. Dataset next, because it decides the content of report
§4.2 and unblocks the `v1` freeze that Phase 1's exit criterion depends on. Then requirements, then the
harness, then the documentation clean-up, and the remaining prose rewrite last — it should be written
against a base that has stopped moving.

**F1 sits outside this order and above it.** It threatens an already-measured contribution, and no
admission-control number is citable until it is resolved.
