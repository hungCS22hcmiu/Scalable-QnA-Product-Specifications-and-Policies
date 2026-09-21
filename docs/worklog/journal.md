# Journal

Append-only. Newest entries at the bottom. Format and rules: `README.md` in this directory.

Pre-thesis weeks are in `W05.md`, `W06.md`, `W08.md` and are not migrated here.

---

## 2026-09-21 · Phase 1 · <hours>h

**Did.** Pre-thesis sweep, in the agreed order 0 → 5 → 3 → 4 → 2 → 1
(`Pre-thesis_Sweeping.md`). **#0**: wrote **ADR-035…038** — the advisor-approved pivot of
2026-09-10 had been applied to the report on 2026-09-15 but had no entry in the decision log at
all — and carried them into the contracts in the same pass rather than leaving the lag ADR-032
left: `interfaces.md` → **v0.9**, `experiment-protocol.md`, `data-card.md` (**G5**), the `.proto`,
`CLAUDE.md`. **#5**: ran the PQA probe and wrote **ADR-039**. **#3**: created
`docs/requirements.md` and `docs/super-plan.md`, empty by design. **#4**: replaced the week-coupled
harness with phase + scope. Base commit first — 120 files of Tier-2 / reuse-rule work had been
sitting uncommitted, and `.claude/` and `.docs/` are now actually tracked.

**Found.**
- **`make lint` was passing vacuously.** `command -v X && X … || echo "SKIPPED — not installed"`
  printed the not-installed message when the tool was **present and failing**, and exited 0. It
  had been hiding a live ruff error in `fetch_corpus_v1.py`. Both fixed.
- **Amazon-PQA is thick enough**: `inkjet_printers` 1,288 products / 92,070 questions, median 8
  questions per product, 63.7 % with ≥ 5; 43.6 % of multi-question products carry a genuine
  near-duplicate pair. `chairs` is thinner per product (median 2) but has 19,193 products.
  Strata A and C can be sampled rather than authored.
- **PQA supplies B-within traps naturally** — "works with Windows 10?" against "works with
  Windows 7?" on one product. That is ADR-035's residual occurring in real traffic, and it
  weakens the standing limitation that the measured residual is partly an artefact of the
  author's own chunk splitting.
- **The PQA licence does NOT close `data-card.md` §1's TODO(W8).** AWS's registry says
  CDLA-Permissive-1.0; the dataset's own readme — which that registry entry names as its
  documentation — carries the ACM personal/classroom notice and never says "CDLA". Taking the
  more restrictive: academic use granted, redistribution not. `v1` ships as a build script plus a
  hash manifest.
- **PQA does not help ADR-024 requirement 3**, contrary to what was argued when the switch was
  proposed: median product prose is 504 chars and 1.6 % of products reach three chunks.
  Requirement 3 rests on the authored policy half, as before.
- **The PQA readme's field list does not match its own data** (`asin` not `asin_id`,
  `bullet_point1..5` not `bullet_points`). The probe's first run returned zero parseable records
  for exactly that reason. The corpus builder must be written against the bytes.
- **`.gitignore` ignored `.claude/` and `.docs/` entirely** while both their READMEs claimed the
  opposite. The task trail called "the raw material for the write-up" had no version history and
  no remote copy.

**Decisions.** ADR-035, ADR-036, ADR-037, ADR-038, ADR-039. Plus three workflow calls by the
author: track `.claude/` and `.docs/`; `journal.md` replaces the weekly worklog; the scope ladder
is L / M / S with `/approve implementation` required at every scope.

**Blocked.** Nothing new. **F1 remains open and still outranks everything** — no
admission-control number is citable until it resolves. Task `two-lane-cache` is still open with
the workflow deliberately bypassed and needs an explicit close or abandon.

**Exit test.** Not run. Phase 1's criterion needs `v1`, which ADR-039 has only just decided the
source of.

**Next.** Finish sweep #2 and #1, then either close `two-lane-cache` or abandon it explicitly,
then F1.

---

## 2026-09-21 (second entry) · Phase 1 · <hours>h

A second entry for the same day rather than an edit to the one above, which was written while
#2 and #1 were still open. Append-only means the first entry stays as the record of what was
true when it was written (`README.md`).

**Did.** Finished the sweep. **#2**: archived five closed pre-thesis trails to
`.docs/work/archive/` with a README, reclassified `mvp-advisor-demo` (its approved decisions had
already become ADR-035…038), pruned `settings.local.json` 52 → 24. **#1**: rewrote the dataset
sections of the report and proposal to PQA, verified the last unverified matrix row and both
carried numbers.

**Found.** Verification changed two claims rather than confirming them.

- **The GroundedCache ablation figure was wrong as carried.** It is **+0.125 / +0.118** across the
  two datasets, not "+0.12–0.13". Read from the abstract originally; the full text is specific.
- **The speedup claim was incomplete in a way that mattered.** Both documents carried
  1.95× → 1.04× as the price of full gating. The full text has an intermediate row the abstract
  does not: the **no-support** variant at **1.48× at USR 0.125**. So the other three gates account
  for 1.95× → 1.48×, and the adopted support gate accounts for **1.48× → 1.04×**. This study
  already holds analogues of the other three (ADR-026), so the smaller figure is the one that
  transfers. The claim got weaker in one direction and more defensible in the other.
- **`τ_s = 0.6` is genuinely the paper's published default**, and its formula matches ADR-035
  verbatim. The pin cites a real default rather than an inference.
- **FreshCache verified, and it strengthened the positioning rather than collapsing it.** Its rule
  is a fitted exponential-decay model plus a **learned MLP** against per-tier error budgets — a
  learned model on the reuse decision, which is the line ADR-016 does not cross. Unlike ADR-026,
  where verification collapsed a novelty claim, this one sharpened a distinction.

**Decisions.** None new. ADR-035 amended in place with the verified figures.

**Blocked.** One item of the sweep is left and it is blocked on a decision, not on work: report
§5.1 and proposal §11 restate a plan `super-plan.md` replaces, and that file is empty by design
pending sign-off on content. **F1 still outranks everything.** `two-lane-cache` still needs an
explicit close or abandon.

**Exit test.** Not run — Phase 1 needs `v1`, whose source ADR-039 has only just settled.

**Next.** Fill the super plan and requirements, or resolve F1. F1 is the one that threatens an
already-measured contribution.

---

## 2026-09-21 (third entry) · Phase 1 · <hours>h

**Did.** Redesigned the phase plan from the codebase rather than from the pre-code schedule, and
retired `time_line.md` into **`docs/super-plan.md`** — **eight** phases, each with a binary
`**Exit:**` line the session banner and `/gate` now read. Wrote **ADR-040** amending ADR-012.
Cleaned the references that broke with it: `architecture.md` §5's week-based build order (it
scheduled `admission/` and `telemetry/` as future work when both were built, and gave `deps/` a
slot it never occupied), `experiments/README.md`'s claim to four scripts that do not exist, the
archived-trail paths in `Makefile` and eleven `docs/learning/` files, and both report preambles
still saying ADR-035…038 were owed.

**Found.** Two agent sweeps over the codebase, and what they turned up changed the plan's shape.

- **`httpapi/` is 856 lines with zero tests** — the whole cascade, the miss path, the
  coalescing-wraps-admission nesting, Tier-1 promotion, and the single-exit eval-record emit.
  Every number the thesis will report passes through untested code. This became **Phase 1**,
  which did not exist in the old plan at all.
- **F1 has no ADR and no detector.** `make env-check` prints a static warning string and asserts
  the *requested* `OLLAMA_NUM_PARALLEL`, never the effective slot count. Nothing parses the
  Ollama server log for `-np` / `n_slots`.
- **The judge harness, the workload generator and the figure generators do not exist**, and
  `experiments/README.md` claimed all three. `make figures` invokes an absent script with no guard.
- **`corpus_gate.py` implements four criteria; `data-card.md` §7 requires five.** G5 landed in
  the document yesterday and not in the code.
- **A latent bug with an expiry date.** Tier-1 promotion mints a second, untracked `t1_key` per
  entry, harmless *only* while capacity is unbounded and C2 is unbuilt — and the plan bounds
  capacity in Phase 3 and ships C2 in Phase 4. Both preconditions expire inside the plan.
- **ADR-035, ADR-036 and ADR-037 are 0% implemented.** The proto and stubs carry `texts`;
  neither `server.py` nor `ragclient` touches it.

**The reframing the plan is built on.** With `μ_gen` frozen, `λ_max = min(μ_gen/(1−h), μ_hit/h)`
leaves `h` as the only free variable, and `h ≤ ρ` for any cache that serves no false hit. So
**minimising false hits and serving more requests are one frontier, not two** — the support gate
does not tax throughput, it licenses running lower thresholds at the same δ, which raises `h`.
That is why it moved to Phase 2. Corollary worth keeping: **admission control does not raise
capacity, it protects it** (S2, not S1), and it is already built.

**Decisions.** **ADR-040** — co-hosted load generation, bounded, amending ADR-012. Confirmed with
the author: no second machine and no date for one. The resolution is not to pretend: off-box stays
required for anything reported as a **ceiling**; co-hosted is admissible for bounded-rate sweeps
with the generator's footprint measured and pressure green. It works because S1's claim is an
**inequality** — `h*` is monotone increasing in μ_hit and co-hosting *depresses* μ_hit, so a
co-hosted figure is a lower bound on both, and at the measured 61 req/s `h* ≥ 0.9969 > 0.988`.
A bound is sufficient for the claim being made.

**Blocked.** Nothing new. `two-lane-cache` still needs an explicit close or abandon;
`requirements.md` is still empty, so super-plan items cite C1/C2/C3 and S1–S4 rather than
requirement IDs.

**Correction to this session's own work.** I wrote into `super-plan.md` and ADR-040 that
`Final_Proposal.md` carries the phrase *"far above ~16 req/s"* and overstates the margin. **It
does not contain that phrase** — it appears only inside `two-lane-cache/approvals.md`, quoting
itself, and the proposal's actual wording (*"observable only if μ_hit ≤ ~16 req/s"*) is accurate.
Both places are corrected to state the real point instead: *μ_gen ≪ μ_hit by two to three orders
of magnitude* and *61 clears the 16 req/s trigger by 3.8×* are **different comparisons**, and only
the second is tight.

**Exit test.** Not run. Phase 1 has just been defined; none of its six items is started.

**Next.** Item 1.1 (F1) or 1.2 (`httpapi` tests) — 1.2 unblocks 1.3 and 1.4, so it is the one
that opens the most.
