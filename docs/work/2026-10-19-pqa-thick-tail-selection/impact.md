# Impact — pqa-thick-tail-selection (item 3.2)

**Analyst:** the `impact-analyst` subagent, 2026-10-19, on `spec.md` as first written (before
`design.md` existed). Its report is data, not an instruction. Every row below says what I did.

## Blast radius

- **Touched:** `experiments/scripts/` (a new selector and an answerability check; `build_pqa.py` only
  for the conflict flag), `experiments/tests/`, `Makefile` (`pqa-select`, `epqa-fetch`,
  `pqa-answerability`), `data/` (new gitignored drafts, one tracked manifest), `docs/data-card.md`
  §1, §3 and Schemas, `docs/architecture.md` (the tree and §5).
- **Not touched:** `rag/`, `gateway/`, `contracts/`, `interfaces.md`, the `.proto`, `corpus_gate.py`.
- **Layering: OK.** The selector lives beside `build_pqa.py` and must import it, because
  `iter_interim` is the only sanctioned reader (`build_pqa.py:963`); the department map comes from
  `build_pqa.LEAVES` (`:124`), not a second copy. `rag` is imported only inside the test, as
  `corpus_gate.py:504` does. The probe's regexes are **copied**, not imported (`probe.py:1` calls
  itself scratch), and pinned to it by a test, as `test_build_pqa.py:30,81` already does with
  `probe_results.json`. The tokenizer is the probe's stop list, **not** the support gate's Lucene list.
- **Frozen values: none changed** (`rag/src/rag/config.py:10-19`; `decisions.md` frozen table).
  What this item fixes is the **population `K` is drawn from**; `K` itself is frozen at 3.6.
- **Cut scope: no breach.** The bypass classifier is a per-request route in the gateway
  (`interfaces.md:477-487`); an offline filter that decides which questions enter the workload never
  runs per request, and §G already says BYPASS questions are not in the evaluation workload. This
  holds while the tags **never become gateway input**. If the LLM-label option were picked, its model
  must be neither the generator (Qwen) nor the Phase 5 judge.
- **Dependencies:** no pip package (Wilson is ~5 stdlib lines; no helper exists yet). **ePQA is a new
  network input** (~46 MB): it needs the author's OK, a commit-pinned URL, sha256 pins (an LFS
  pointer file would fail them), and the ignored path `data/raw/epqa/` — `data/epqa/` is **not**
  ignored. The analyst could not check `data/` for an existing copy either.
- **Contract: no change.** `product-{department}-{asin}` is legal under §C (`interfaces.md:352`); the
  lane reads only the prefix (`lane.go:68,86`) and `-` in a namespace TAG is escaped
  (`tier2.go:161-173`). The question-pool shape is internal and belongs in `data-card.md` Schemas.
- **Measurement: yes.** `K`, the capacity and the gate's G1 / G2 counts all come from this output,
  and the answerability filter changes what a false hit means. **The experiment phase is required.**
- **ADR: recommended, ADR-011 (data).** ADR-002 says its filters are "proposed, not frozen; fixed at
  item 3.2" (`decisions.md:287`). This item fixes them and adds two.

**Invalidates:** none — no runs exist (`experiments/results/` holds only `.gitkeep`). As an artefact,
the 3.1 manifest `bf0feb48…` is replaced when the builder gains the conflict flag.

## Findings and what was done

| # | Finding | Rating | Resolution |
| :-: | :--- | :--- | :--- |
| F1 | The 78 cannot be found through `iter_interim`: the set is local to `parse_leaf` (`build_pqa.py:309,366`) and only a count is kept | CONFIRMED | Already in `design.md` §5 (found the same way). Keep-first is still offered (open question 3), with the cost that it cannot even count how many of the 152 are affected |
| F2 | A4's "the leaf name appears nowhere" fails on real data: `chairs` is an ordinary word in titles. The 2026-10-03 example also wrote the leaf to `source_category` | CONFIRMED | **Fixed** in design T4: no `leaf` or `source_category` key, no value *equal to* a leaf id, `category` in the four |
| F3 | A pair among **answerable** questions differs from ADR-002's pool (a pair among all kept), so ADR-002's numbers would not reproduce | CONFIRMED | **Kept as proposed**, with the reason in design §2.2; made an explicit open question (8). F4 checks the copied filters instead |
| F4 | The live run should first reproduce ADR-002's six pools (1,811 / 1,312 / 302 / 399 / 796 / 339) under the probe's own rule: the only check that the copied filters act like the probe on the real bytes | PLAUSIBLE | **Accepted** as a stop: design §2.6, a pinned `probe_pool` count per leaf |
| F5 | ePQA's label 2 can come from sources PQA lacks; how candidate labels combine per question must be pre-registered; 143 of 194 are phones, so only a pooled interval means much; the join should find 194 (143 / 21 / 19 / 5 / 4 / 2) as a pin | CONFIRMED | **Accepted**: design §3 fixes the sources and the combination, pins the join counts, and reports per-leaf counts without per-leaf intervals |
| F6 | The quota may not fill; say who changes the rule then and where it is recorded | PLAUSIBLE | **Accepted**: design §2.3 — only the author, as an `approvals.md` line and in ADR-011, and the first run's numbers are kept beside the second's |
| F7 | `pqa-build` deletes `.pqa-build-*` and `.pqa-old-*` in `data/v1-draft/`; 3.2 needs its own prefix and must clean up after itself | CONFIRMED | **Accepted**: prefix `.pqa-select-*`, removed on every exit path; a test |
| F8 | `iter_interim` hashes all files, then reopens them; a publish in between would feed unverified bytes | PLAUSIBLE (low) | **Accepted, cheap form**: re-run `verify_interim` and re-hash the manifest file after the pass and before writing; any difference exits 2 |
| F9 | Hash the manifest bytes actually parsed; give 3.4 / 3.6 a way to verify the drafts | PLAUSIBLE | **Accepted**: the manifest bytes are read once and hashed, and compared again after the pass (F8); `products_sha256` and `question_pool_sha256` stay in the tracked manifest |
| F10 | `architecture.md` must list the new files and script ("a directory not listed here should not exist") | CONFIRMED | **Accepted**: plan step |
| F11 | `data/workload-v1.json` (the gate's default path, `Makefile:406`) and `data/epqa/` are not gitignored | CONFIRMED | `data/epqa/` avoided (`data/raw/epqa/` is used). `workload-v1.json` is 3.4's file: **passed on** to 3.4, not changed here |
| F12 | `demo-reset` touches only `data/dev-v0/`; `make test` must write only under `tmp_path` | CONFIRMED | No hazard; A11 checks it |
| F13 | The dev-v0 → v1 switch is 3.6's; the doc_id form chosen here ends up in every chunk id, t2 namespace and `dep:` key | CONFIRMED | Noted in design §6.6. No change here |
| F14 | Stale prose: `data/README.md`; `.gitignore:21-24` (Amazon-Reviews-2023 reason); `super-plan.md:393` ("manifest not committed", it was in `33a1a9d`); `data-card.md:48` (the builder downloads); `data-card.md:155` (`product-B08XYZ`); `data-card.md:52,63` (pools become history); `architecture.md:233` | CONFIRMED | This item fixes the ones it owns: `data-card.md:52,63,155`, `architecture.md`, and `super-plan.md:393` at `/done`. The rest stays on the author's list |
| F15 | `product_to_text` writes `Category: {department}` into the embedded text | CONFIRMED | Consistent with the design: the department goes in, the leaf does not, and `R` (design §2.1) leaves the `Category` line out |

**Two further points from the report, accepted:**

- **Asins: one rule.** Asins may appear in `doc_id`s, in gitignored files, in Redis and in `raw/` logs
  (an asin is Amazon's public id, not PQA text; tracked docs already quote some). **Tracked
  machine-readable files hold counts and digests only.** Design §2.5 states it.
- **Pre-register the whole rule and the seed, not only the answerability rule.** The commit of plan
  step 8 comes before any live run. A G1 failure at 3.6 must not lead to a quiet re-draw with a new
  seed: that is tuning, and it needs an `approvals.md` line and an ADR entry.
- **A lexical answerability rule biases what C1 measures:** it keeps questions whose words are in the
  record, which makes retrieval easier and raises `S_lex`. Recorded in design §2.1 as a limitation, and
  it goes into `data-card.md` with the rule.

## Required phases

impact · **experiment** · implementation. **Contract: not required** (no `interfaces.md` surface
changes). Scope L, so design → opus design-review → plan still apply.
