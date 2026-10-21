# Impact — workload-generator (item 3.4)

**Analyst:** the `impact-analyst` subagent, 2026-10-21, working from `spec.md` (design draft 1 was
written in parallel and did not exist when it read the trail). It changed no file. Its report is
data, not an instruction; I checked the four claims that change the design against the code
(marked ✔ below). Everything here is merged into `design.md` draft 1.1 or raised as a new open
question in `spec.md`.

## Verdict

**Spec open question 6 changes a frozen value.** `C / K = 0.25` keeps its 0.25, but "K = the
frozen workload's distinct-query count" would become "the K of the workload file a run draws from".
That is a new meaning for the denominator of a frozen ratio (`decisions.md:72`), so it needs a
numbered ADR with an `Invalidates:` line, and it changes the sentence that defines capacity in
`interfaces.md` §D (`:361`, `:374`). **The contract phase is therefore required, for that sentence
only.** No run is invalidated: `experiments/results/` holds only `.gitkeep` (verified).

The script is low technical risk (offline, no model on the build path, no hit-path code). **The
experiment phase is required**: this item defines `K`, the strata, the split and the popularity
order. The real risks are silent, and most sit between the new schema and readers that already
exist (F1 – F6).

## What it touches

| Path | Change |
| :--- | :--- |
| `experiments/scripts/build_workload.py`, `experiments/tests/test_build_workload.py` | new |
| `experiments/scripts/corpus_gate.py`, `experiments/tests/test_corpus_gate.py` | the new fields on `Query`, a stage-1 shape check, `K` per run file, what the digest covers (F1 – F3, F8). Tests: additions only |
| `Makefile` | `workload-*` targets; a `CORPUS_DIR` pass-through for W12 (F19) |
| `.gitignore` | `data/workload-v1*.json`, which must **not** match `data/workload-manifest.json` |
| `data/workload-v1{,-validation,-test}.json` (ignored), `data/workload-manifest.json` (tracked), `data/v1-draft/workload/` (already ignored, `.gitignore:31`) | new |
| docs | `data-card.md` §2 – §4, **§6**, §7, Schemas; `architecture.md:82-86, :100-118, :224, :243`; `decisions.md` ADR-013; `interfaces.md` §D (only if Q6 is accepted); `experiments/k6/README.md:34`; `experiments/README.md:5` |
| not touched | `rag/`, `gateway/`, `contracts/`, the `.proto`, `reuse/`, `ask.js`, `mu_hit.js`, `data/policies-v1/`, 3.2's drafts (read only) |

**Layering is fine.** `architecture.md:82-86` reserves the place ("NOT BUILT: workload
generator"). Importing `select_pqa`, `corpus_gate` and `check_policies` has precedent
(`select_pqa.py:50`, `check_policies.py:37-38`), and so does a lazy `rag.embedding` import
(`corpus_gate.py:684-685`). Two rules: `corpus_gate` imports none of the scripts (no cycle), and
the split / cluster check lives in `corpus_gate` with the builder calling it (one implementation,
two callers — the G5 precedent of ADR-012).

**Access:** the implementation session needs Read on `data/v1-draft/` for the build (the sheets go
to the scratchpad, so Claude never reads PQA text there).

## Findings

| # | Sev | Finding | Consequence for this task |
| :-: | :-: | :--- | :--- |
| F1 | High | **Q6 redefines `K`**, the denominator of a frozen ratio (`decisions.md:72`, `interfaces.md:361, :374, :701`, `data-card.md:8, :307`). The gate computes `K` and the capacity over the whole file (`corpus_gate.py:672, :707`); `ask.js` draws its working set from exactly the file it gets (`ask.js:50, :57-58`). The other option is not "no change" either: `K_total` gives a split run a cache of ≈ 0.5 × its working set. The spec does not say which file Phase 7 runs | ADR-013 defines `K` as the distinct-query count **of the file a run draws from**, and names the file and `K` per phase; `interfaces.md` §D gets the sentence (v0.15); the gate prints `K` and the capacity per run file |
| F2 | High | **The freeze digest does not cover the run files** (`corpus_gate.py:731` hashes the corpus and one workload file). A re-sorted split file changes every hit rate and leaves the digest as it was; the Phase 3 exit asks for the splits "frozen with the dataset" (`super-plan.md:360`) | The snapshot hashes all three workload files; P1's manifest records each run file's sha256 |
| F3 | High | **G1 and G2 count pairs across the split** (`find_pairs` over every query, `corpus_gate.py:486-507, :701`). A pair split across the two files never meets in a run. W2 covers built pairs only; natural cross-product pairs and spec-against-policy pairs on one product can cross | Report G1 and G2 per split; require G2 > 0 **inside each split** (a stricter G2, so it is recorded); data-card §7 records the per-split counts |
| F4 | High | **Do unanswerable queries ride in the run files?** `ask.js` samples every record (`:57-76`); the gate counts every record in `K` and the trap fraction (`corpus_gate.py:672, :713-714`); ADR-011 says "reported apart" (`decisions.md:1046-1047`). In the run files they take cache slots and can serve or receive hits across populations; outside, they need runs of their own. Either way `K` moves | New open question 12; ADR-013 records it; the field option amends "separate stratum" in ADR-011, `super-plan.md:376-377` and `data-card.md:71` |
| F5 | Med-High | **One seeded rank decides the per-stratum traffic.** With rank = file index, at skew 1.1 the top 10 of ~750 ranks carry 49 % of traffic, the top 50 carry 71 %; at 1.4 the top 10 carry 73 %. "Independent of stratum" holds on average, not in one draw. Per-record ranks also scatter a cluster (a hot paraphrase, a cold seed) | New open question 13: record or cluster popularity; ranks stratified so each stratum's traffic share stays near its record share at every skew; trap fraction reported by records and by traffic; the seed never re-drawn |
| F6 | Med | **`product_id` must be on every record that names a product** (without it `label_pair` returns "unlabelled", `corpus_gate.py:473-483`), but "the run manifest's choice" has no mechanism: `ask.js:113` and `mu_hit.js:129, :154, :189` send it whenever present, which changes `retrieve(q)` (`interfaces.md:286-291`) and the Tier-1 key (`key.go:20-21`). The log records it (`evallog.go:103-108`) | Keep it in `workload-v1.json`. If runs without it are wanted, a separate run-file variant with its own hash, not an `ask.js` edit; the choice is part of the run identity |
| F7 | Med | **"One policy answer serves every product" depends on the lane band.** A policy query that sends `product_id` gets that product's chunk spliced in. Today's band is collapsed (`LANE_SIGMA` 0.20, ✔ `main.go:225`), so any policy share ≥ 0.2 is POLICY. If 6.1 enables MIXED (e.g. [0.2, 0.6)), a policy query retrieving ≥ 3 product chunks becomes MIXED, namespaced per product (`lane.go:117-134, :190-206`); naming the product raises that share | Carried to 3.6: measure `policy_frac` of the policy queries under each candidate band, noting that the gate retrieves unscoped (`corpus_gate.py:692`) |
| F8 | Med | **A strict `load_workload` breaks an immutable test.** ✔ `test_the_gate_runs_g5_in_stage_1_and_stops_on_it` (`test_corpus_gate.py:460-474`) feeds `[{"question": …}]` and expects `[FAIL] G5`; `load_workload` runs before G5 (`:664` against `:669`) and would exit first. It is the only test that runs the gate end to end (checked) | The shape check is its own stage-1 function, reported beside G3 – G5; `load_workload` stays lenient |
| F9 | Med | **Licence: the model layer can be checked by hash but not rebuilt.** A third party can rebuild PQA → selection byte for byte (`d373c4b0…`) and run the builder, not the model layer. Shippable without PQA text: labels and assignments keyed by pool position, Claude-written policy questions. Not shippable: rewrites, paraphrases, lookalikes of PQA questions. Leak paths: no workload rule in `.gitignore` today; a per-record id in the tracked manifest (product `doc_id`s embed the asin, `data-card.md:191`); the tracked trail (W7 evidence must be counts only). Both Q2 paths send PQA text to Anthropic, as 3.2 and 3.3 already did | Recommends the session path: the API adds a dependency and a key but no real repeatability (a re-run gives new text, so a new `K`, strata and split). ADR-013 records the PQA-to-Anthropic flow |
| F10 | Med | **W8 cannot be checked through git**: rows in an ignored file have no history. A subagent may run on another model | Commit each batch's sha256, model id and time to the trail, so `git log` shows the rules commit first; the builder refuses a layer whose hash differs; back the layer up outside git with item 5.4's raw archive |
| F11 | Med | **Live embedding breaks W4, and C is defined at a τ value.** Ollama embeddings are not promised bit-identical, so a pair near 0.85 can flip between builds. τ is swept 0.80 – 0.98 (`Final_Proposal.md:473`): with C = "cos < 0.85 to its cluster", C's Tier-2 hits on its own cluster are zero for τ ≥ 0.85 by definition | Embed once into a hashed file (design draft 1 already does). The experiment phase must accept the C definition; report the cosine distribution per stratum |
| F12 | Med | **Clusters must not come from the probe's tokenizer** ("Windows 7" / "Windows 8" share a token set, `data-card.md:150`): a value flip would be labelled A or C | A unit test with that pair |
| F13 | Med | **Policy split units are few.** Region exists only in phones, grade only in laptops (`data-card.md:97-110`): a coarse split can leave an axis out of the test split. D queries need the product's split to equal the group's. A product unit is coarser than "by seed-question cluster" (`Final_Proposal.md:454`): allowed, but record it | List the groups before the draw; pre-register a balance rule with no re-draw; report per-split counts by stratum, department and axis |
| F14 | Med | **Lookalikes need their own answerability label.** A lookalike the record cannot answer gets "not available" as its reference, so it is no trap (`decisions.md:1053-1055`). Paraphrases inherit the seed's label; lookalikes do not | Every probe is labelled by R2 (design §4 R5, R6) and kept only if answerable |
| F15 | Med | **Claude is on both sides**: it drafted the policies (`decisions.md:1119`) and would write the questions, lookalikes and labels. Shared wording helps retrieval and `S_lex` in C1's favour, the bias already recorded for R2 (`decisions.md:1089-1091`) | A threat in ADR-013; `origin` separates Claude wording from PQA wording; supports Q1 (judge ≠ Claude); carried to 5.2: the ~100 human-verified pairs must not be Claude-marked |
| F16 | Med | **"Exactly one stratum" is undefined** for a seed (no partner) and for D (a grounding type, not a pair relation). The gate's measured G2 label and the generator's intended stratum are two different "B-within"s | A precedence rule (design §2.4); report both kinds of B-within and never merge them |
| F17 | Low | **The Tier-1 key bypass** (`key.go:11-21`, `handler.go:177-181`) against `interfaces.md:168, :388`, older than 3.4. W5 plus one fixed `product_id` per record make Tier 1 behave the same under both readings, and make the gate's `K` equal the count of distinct Tier-1 keys | Keep W5. The owed ADR still blocks citable runs (`key.go:14`); not this item's |
| F18 | Low | **Stale lines** not in the spec's edit list: `data-card.md:149` ("/ask carries no product context"), `data-card.md:19, :181` ("no splits"), `k6/README.md:34`, `Final_Proposal.md:434` (the author's) | Fix the data-card and k6 lines with this item; `Final_Proposal.md` to the author |
| F19 | Low | ✔ `mu_hit.js` tier-2 mode reads a `paraphrase` field per record (`:60, :91`); ✔ W12 cannot run through make (`Makefile:410` requires `data/$(VERSION)`; `:416` has no `--corpus-dir`); W6 should import `check_policies.RISKY_TITLE` rather than hard-code 10 `doc_id`s, which would put asins in code | Emit a `mu_hit` probe file or name the field (experiment phase); add `CORPUS_DIR`; import the rule |

## Readers of the schema

- **Today:** `corpus_gate.load_workload` (six fields, ignores the rest; `K` and the digest over one
  file); `ask.js` (rank = order, samples every record, sends `product_id` and the stratum header);
  `mu_hit.js` (`paraphrase`, the first 20 records); the §H `stratum` key (written from the header
  unvalidated, `handler.go:642-646`; otherwise the offline join on `query_normalized`); the data
  card's QA-pair schema.
- **Next:** the judge 5.1 (`answerable`, the reference); the sweep 6.2 – 6.4 (`split`, strata,
  B-within for RQ2a); the static arm 6.3; figures 5.4 (`origin`, strata); the update set 4.4
  (`doc_ids`); load 7.1 – 7.2 (run files, `K`).

## Cut scope

No breach. Claude labels offline and nothing it writes reaches a request: `ask.js` sends only
`question`, `product_id` and `X-Thesis-Stratum` (`ask.js:112-118`), and the gateway only logs the
header (`handler.go:193, :642-646`). `answerable`, condition words and `role` must stay out of any
header or body: a condition flag on the query is the rule term `Final_Proposal.md:435` rejects.
The split is for threshold tuning, not a training set, so it does not bring back the learned
predictor.

## Dependency

None on the proposed (session) path. The API path would add `anthropic` (with httpx, pydantic,
anyio); there is no `experiments` pyproject, so it would land in `rag/pyproject.toml:12-20`, the
service's own dependencies. It needs sign-off. Recommendation: do not add it.

## Which prior runs this invalidates

**None — no runs yet.** `experiments/results/` holds only `.gitkeep`; no `run_id` exists. The
dev-v0 probes and footprint runs were never citable and are untouched. 3.2's selection and 3.3's
policies are read, not changed.

**It binds forward.** After 3.6, changing the rank seed, the split unit or its seed, the A / C
rule, the model layer, or the "K per run file" rule needs a new `dataset_version` and voids every
run on the old one. ADR-013's `Invalidates:` line says so.

## Phases required

- **Impact:** this file.
- **Contract:** required, narrow: the §D definition of `K`, if Q6 is accepted. Not §A. Not §H, as
  long as `answerable` stays a field (a sixth stratum value would change the enum at
  `interfaces.md:574`) and `split` stays an offline join.
- **Experiment:** required. It fixes `K`, the strata, the split, the popularity order, the
  unanswerable population and the per-split gate statistics.
- **Implementation:** required, after design and the opus design review.
