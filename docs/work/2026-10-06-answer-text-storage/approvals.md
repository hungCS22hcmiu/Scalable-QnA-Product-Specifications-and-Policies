# Approvals — answer-text-storage

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-06 | — (`impact.md` §1, §5: no frozen experimental value touched; **no `run_id` invalidated**, none exist. It changes a frozen *document* (§H), which is the contract phase below) |
| contract       | **required** (§H, `interfaces.md` v0.11) | yes      | 2026-10-06 | ADR-005, **approved as drafted in `contract-draft.md`** (A1–A9, B1–B2); applied verbatim at plan step 1. Two `⟦PENDING⟧` markers are inside the approved text and are closed at step 9: the drain-rate numbers, and the Spotlight call (open question 6, **still the author's**). §A–§G, the `.proto` and every JSON key are untouched; no frozen value changes |
| experiment     | **required, record-only** (`impact.md` §5) | yes (record-only) | 2026-10-06 | — Experiment record below. Adds writer-goroutine work on a measured path and new INCOMPLETE conditions; changes no key, span or counting rule. Invalidates no `run_id`: none exist. The drain-rate numbers are recorded at plan step 7 and written into ADR-005 at step 9 |
| implementation | always   | yes      | 2026-10-06 | ADR-005 (applied at plan step 1; `⟦PENDING⟧` closed at step 9) |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-06 | **Commit F-A (`78ae546`), then open item 1.5 at scope L** | "commit F-A rồi mở 1.5 scope L" | — |
| 2026-10-06 | **Defaults for decisions 1–3**: keep the `raw/answers/{sha}.txt` directory; count a failed JSONL line write and the `Close` error as INCOMPLETE (D3); a guard refusal voids the run | "dùng default cho 1-3" | — (no run exists) |
| 2026-10-06 | **Publication: ignore `experiments/results/*/raw/` now.** Done in this session: `.gitignore:64`, and `super-plan.md` 5.4's *Done when* reworded to "clean checkout **plus the raw archive**". `manifest.yaml` and `.gitkeep` stay trackable | "ignore raw/ luôn" | none: `raw/` never held a tracked file (`git ls-files experiments/results` = `.gitkeep`). **5.4 must now ship an archive step**; recorded, not designed here |

## Open — needs the author (each has a default, taken and reversible unless marked)

Decisions that **gate `/approve contract`**, because they change §H's text or the layout:

1. ✅ **DECIDED (default): the directory.** *Was:* `raw/answers/{sha}.txt` directory, or one `raw/answers.jsonl`? (`design.md` §1, review 15.)
   The file is the smallest version: no temp/`Link`/`Remove`, no three-step `Open`, no per-file
   Spotlight/APFS cost; it loses atomic per-answer publication and open-by-hash. **Default: the
   directory**, because the plan names it and 5.1 reads by hash.
2. ✅ **DECIDED (default): yes.** *Was:* count a failed JSONL line write, and the `Close` error, as INCOMPLETE (D3)? Review 8 shows it
   is what makes "no unnamed file" loud, not scope creep. **Default: yes.** If cut, ADR-005 states the
   asymmetry instead.
3. ✅ **DECIDED (default): yes.** *Was:* does a guard refusal void the run? **Default: yes** (a call site skipped `SetAnswer`; a retry
   would otherwise mask it).
4. **The INCOMPLETE conditions as a new Research Requirement.** The skeleton `requirements.md`
   assigns no IDs yet; recorded here and in ADR-005.

Decisions that gate **ADR-005's closing (step 9)**, not the code:

5. ✅ **DECIDED 2026-10-06: ignore `raw/`.** *Was:* ⚠️ publication posture. `experiments/results/*/raw/` is **not gitignored** and `origin` is
   public GitHub (`impact.md` §4, ✔︎ checked). `requests.jsonl` already carries verbatim PQA
   `query_raw`; this adds PQA-derived answer text; it collides with `super-plan.md` 5.4's "clean
   checkout". **Recommendation:** ignore `experiments/results/*/raw/` now and reword 5.4 to "clean
   checkout + the raw archive". The author said yes, so `.gitignore` and 5.4 changed (see the decisions table). ADR-005 records the
   posture at step 9. **Follow-on for 5.4:** a clean checkout no longer carries `raw/`, so
   `make figures` needs the raw archive to be put back first; that is 5.4's to design.
6. **Spotlight** (review 9, ✔︎ `/` is indexed): exclude `experiments/results/` as a **run
   precondition**, or measure it? Needed before Phase 3.

Not gating this task:

7. **U8, temperature 1.** `super-plan.md` says it "needs an investigation before 1.5 or 5.1 is built
   on it." `spec.md` argues it does not gate 1.5 and does gate 5.1. **The author's plan text; the
   author decides.**
8. **5.1's verdict key** (review 10). A bare `answer_sha256` cannot key Tier-2 verdicts. v0.11 does
   not re-ratify the label; **`super-plan.md` 5.1's wording is flagged, not edited.**
9. **The shared helper `checkEveryRecord`** (`harness_test.go:1023`): strengthening it would give ~30
   tests the file check, but edits an existing test and CLAUDE.md makes tests immutable. **Default:
   no**; new assertions live in new files. It needs the author's explicit say-so.
10. **Stale `v0.9` strings** (`CLAUDE.md:106`, `.claude/agents/contract-reviewer.md:11`,
    `architecture.md:30`). Edited only with the author's OK.

## Experiment record (phase approved 2026-10-06, record-only)

Nothing is re-measured: no run exists (`experiments/results/` holds only `.gitkeep`). From the 1.5
commit on, a run is recorded and judged as follows.

**What changes on a measured path.**
- **Hit path:** one string-header assignment per served request (`rec.SetAnswer`). The SHA-256 was
  already computed there. No timed span changes: `t_tier1_ms` wraps only `Cache.Get`, and
  `t_total_ms` / `latency_ms` already included the hash.
- **Writer goroutine** (off the request path): a map lookup per record, and per **distinct** answer a
  create, write, chmod, close, link and remove. It already did one unbuffered `write(2)` per record.
- **Memory:** each buffered record pins its answer text (worst case 4096 × answer size, a few MB).
- **Disk:** one file per distinct served answer, at least 4 KB each on APFS. Spotlight will import
  each (**unmeasured**, open question 6).

**What does not change.** No §H key, no span, no counting rule, no frozen value. `latency_ms`,
`t_*_ms`, `cache`, `similarity`, `shed` and every other field mean what they meant before.

**What a run now needs to be admissible.** It is **INCOMPLETE and not admissible** if any of: records
were dropped (as before); a record's line failed to encode; a hash a record names has no file when the
run ends; a record's answer text did not hash to its `answer_sha256` (a **guard refusal**, never
cleared by a retry); the log failed to close. The verdict is the gateway's exit status and its log
until P1's manifest exists; it is **not** in `raw/`.

**Comparability across the commit.** A log written before it has no answer store and **cannot be
judged**; every other field of it is comparable. Nothing existing needs re-running.

**Recorded at plan step 7** (`evidence/drain-rate.md`; exploratory, pressure level 2, not citable;
written into ADR-005):
- the writer's drain: an already-seen record adds **nothing measurable** (≈ 4 µs, the pre-1.5 line
  cost); a **first sighting adds ≈ 440 µs** (~110× a line write), so the writer sustains **≈ 2,250
  first sightings/s**;
- the real bound: distinct answers ≤ `0.25·K`; a worst-case burst of them can drop only above ≈
  16,300 req/s (K = 2,000), ≈ 5,200 (K = 5,000), ≈ 1,450 (K = 10,000), and any burst of ≥ 4,096 first
  sightings (K ≥ 16,384) overflows alone. At the planning figures (Tier-2 ≈ 61 req/s) the margin is
  ≥ 35×. **Only a Tier-1-heavy phase at thousands of req/s over a large K, in its first seconds, can
  drop**; a Phase 7 run of that kind checks `Dropped()` and `AnswersMissing()` first;
- `go test -race` on `telemetry`, `httpapi` and `cmd/gateway`: ok; five repetitions of `telemetry`: ok;
- **not measured:** Spotlight, the gateway under load, a green-pressure run, filesystems other than APFS.

**How to read a later `Dropped() > 0`.** After this commit it can come from the writer being slower
than before. The step-7 numbers say whether that is plausible at the real bound. A figure that
excludes such a run must say why; one that includes it must not call the run complete.

## Post-approval wording corrections to the approved contract text (2026-10-06)

The contract was approved as drafted. Applying it, a `contract-reviewer` pass found **wording that
overstated what the design does**. Corrected in `interfaces.md`, `decisions.md` and `contract-draft.md`
(kept in sync), **before anything is committed**. **None changes a behaviour, a field, a key or a
frozen value**; each makes a sentence true. Recorded because the author approved the earlier wording.

- **Rule 5, order.** "The file was visible before the line" held only for a hash's first successful
  write. A hash whose first write failed and was retried by a later record has its first line before
  its file. Now: the *writer* publishes the file first; a reader cannot check it from `raw/`;
  admissibility turns on the file existing at the end.
- **Rule 5, "no file that no record names"** is scoped to `{sha}.txt`; a `.answer-*.tmp` left by a
  failed temp removal is not a violation (rule 1 says so).
- **Rule 8:** `dataset_epoch_at_retrieval` *is* logged; what `raw/` lacks is the update set with its
  epochs.
- **Wording unified:** "failed to **encode or write**" everywhere (the counter covers both); the
  guard is "checked at a hash's first sighting"; `decisions.md` P1 (not `super-plan.md`); F-F is a
  `super-plan.md` finding and the race is part of it per the 1.2 trail; SHED/ABANDONED/
  GENERATION_FAILED are named as log-only `cache` values; "a MISS whose generation completed though
  the client left"; "a second generation **can be** a different answer"; ADR's `EEXIST` sentence; the
  ADR's U8 sentence no longer says "does not gate" and "not decided" at once.
- **Added to ADR-005:** with `raw/` outside version control git no longer enforces write-once and an
  edit to a finished run would leave no trace; a hash manifest is not planned (5.4 / P1).
- **`super-plan.md`:** Phase 5's **Exit** line (the one the banner prints) now says "plus the raw
  archive", as 5.4's row already did.
- **Not changed:** the contract reviewer's items 11–13 (stale `v0.9` strings and documents that plan
  step 8 updates) are step 8's; item 15 (UTF-8 as a conditional absolute) is softened in rule 7 only.

## Taken by Claude as a default, open to reversal

- **Empty answer text is a real answer** (stored as an empty file; "has an answer" is
  `answer_sha256 != ""`).
- **EEXIST on `Link` is success**, argued from the fresh directory and the single writer.
- **No `storeBlob` hedge** for 5.1's SOURCE text under `mutation: on` (review 16): it would be unused
  code, and no field can be added without a contract decision.
- **Spec's U8 reading** (it does not gate 1.5) is Claude's, recorded so it is visible.

## Notes

- The `/task` template rendered with its arguments shifted again ("task `L` at scope `$2`"). The
  intended values were used: slug `answer-text-storage`, scope `L`. Third time in this repository;
  the template, not the task, is at fault.
- Scope L, not M: `interfaces.md` §H is a frozen contract and the artefact is what the judge reads
  (5.1). A silent error (a hash a record names with no file) costs the study every verdict.
- **Correction to an earlier report.** `/verify`'s "proto drift" row was reported as clean on the F-A
  close and before. Both stub directories are gitignored (`.gitignore:40-41`), so that check cannot
  fail. It checked nothing. `/verify` for this task uses `git diff --exit-code contracts/` and says so.
