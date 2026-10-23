# Approvals — corpus-freeze

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | yes      | 2026-10-22 | ADR-014 (to write, plan step 23) |
| contract       | if §B/§D | not required (`impact.md` §6) | | |
| experiment     | if measured | yes   | 2026-10-22 | ADR-014 (to write, plan step 23) |
| implementation | always   | yes      | 2026-10-22 | ADR-014 (to write, plan step 23) |

**Opened 2026-10-22** by `/task corpus-freeze L`. Scope L because the item freezes a corpus and a
workload, adds the first dataset-version switch, and records the numbers every later run depends on.

**State of the trail (2026-10-22):** `spec.md` draft 3 · `impact.md` (subagent `impact-analyst`) ·
`design.md` draft 3 · `review.md` (subagent `design-reviewer`, opus: *sound with changes*, 18 findings,
all accepted and merged) · `plan.md` draft 1. Nothing is approved yet.

**Impact approved 2026-10-22** by the author (`/approve impact`), on `impact.md`. This approves the
blast-radius reading only: the files and targets touched, the finding that the item changes **no existing
frozen value** and creates new ones (`v1`, its digest, `K` 622 / 652 with capacity 156 / 163, the chunk
digest), and the list of what binds forward. It does **not** answer the open questions in `spec.md`, and it
does not approve the experiment or implementation phases. **Invalidates: none — no runs yet**
(`experiments/results/` holds only `.gitkeep`; Redis holds no cache key).

**Experiment approved 2026-10-22** by the author (`/approve experiment`), on `spec.md` draft 3,
`design.md` draft 3 and `plan.md` draft 1. As listed under "What the experiment approval covers" below, it
fixes, before any gate run on `v1`: stop rules **S1 – S5** and S1's list of allowed next steps after a
fail; "run 1 is the figure" (S2); the carried measurements, with U10 and the sibling rate on validation
only; the G1 and G2 breakdown by pair type; and the contents of the freeze record. **Changing any of these
after the first gate run needs this phase approved again.**
**Open questions 1 – 11 were not answered one by one.** The author approved the documents that contain the
proposed answers (as at item 3.4), so the proposals stand as written: the env override with default
`dev-v0` and its three guards (1), `data/v1-freeze.json` with no file names (2), S1 as written (3),
carried measurements recorded only (4), no hash of the unit-list file (5), one shared split function with
the golden node dump (6), the manifest hash in the record (7), run 2 re-ingests (8), no `pyproject.toml`
pin (9), S1's list and S5 (10), and the restore path dropped and carried to Phase 4 (11). If the author
wants a different answer to any of them, it must be said **before** `/approve implementation`.
**Invalidates: none — no runs yet.** The gate run on `v1` will be the first measurement on this corpus.

**Implementation approved 2026-10-22** by the author (`/approve implementation`), after impact and
experiment. The contract phase is not required. `READY_TO_IMPLEMENT` is written. This unlocks the code
(`plan.md` Block 0 and Block A, steps 1 – 15). **Plan Block B, the measurement block, still waits for the
author's separate go** (the stop after step 15): it ingests `v1` over the `dev-v0` index and holds the machine
for several minutes. The stop rules S1 – S5 are in force from the first gate run.
**Invalidates: none — no runs yet.**

**Phases required, per `impact.md`:** impact · experiment · implementation. The contract phase is **not**
required: no `interfaces.md` surface, wire field or `.proto` changes, and §D v0.15 already expects the
freeze. Scope L also needs the design and the opus design review, which are done.

**What the experiment approval covers.** The gate run is the measurement that fixes the corpus statistics.
Approving the experiment phase approves: stop rules S1 – S5 and the list of allowed next steps after a fail;
"run 1 is the figure" (S2); the carried measurements with U10 and the sibling rate on validation only; the
pair breakdown as part of G1 and G2; and the freeze record's contents. The stop rules must be approved
**before the first gate run on `v1`**.

**Open questions** (`spec.md` 1 – 11, each with a proposed answer). Two are new from the review and are the
author's: **10** (S1's list and S5) and **11** (the restore path is dropped here and carried to Phase 4).
Open question 9 (no `pyproject.toml` pin; record the version) needs the author's sign-off by the
repository rule on dependencies. None is answered yet.

**Invalidates:** none — no runs exist (`experiments/results/` holds only `.gitkeep`; Redis holds no cache
key; checked in `impact.md`). It binds forward: after the freeze, a change to any of the 164 corpus files or
3 workload files, the chunking, the text format, the embedding model or its prefixes, `top_k`, the
scoped-retrieval code, the gate's constants, or ADR-013's list needs a new `dataset_version` and a new gate
run.

**Carried out of this item:** to P1 — call `make corpus-index-check` at run start and before any reference
generation, set `CACHE_CAPACITY` from the run file's `K`, fix the stale `K` comment at
`gateway/cmd/gateway/main.go:267-268`; to Phase 4 — a restore path for `data/v1/`, the epoch's source
(ADR-008); to the author — `CLAUDE.md`'s single-`K` sentence.

## Block B run and its outcome (2026-10-22)

**Go for Block B** given by the author in chat ("can we start Block B?"). Run 1 stopped under **S1**: G1 failed,
21 pairs inside a split, 29 short of the 50 needed (13 validation, 8 test). Counts in `evidence/gate-failure.md`.
Steps 21 – 22 (run 2, freeze) were not run. **Nothing was frozen: ADR-014 ("`v1` is frozen") is not written,
and its "to write" entries in the table above are void.** No frozen value changed; `Invalidates: none — no runs yet`
still holds.

**S3 waived for the session, by the author, in chat.** At the preflight the pressure level read 2 with no model
loaded (1 after the LLM was unloaded, and 1 for all 53 readings of the run). The author said to start anyway:
"we can start, since this is not session for measurement to collect the statistic". This is a deviation from S3 and
from acceptance A10, and it is recorded here because a stop rule is changed only in this file. What it covers:
this one stopped run. What it does not cover: any run that is to be frozen. Those need level 0, and `freeze` still
refuses a report with a non-green reading. The numbers of this run are indicative and are not cited anywhere.

**Next step after S1, chosen by the author in chat:** close this task as a recorded stop and open a new task
about the corpus and workload. That is option (2) of S1 (reopen item 3.3 or 3.4 under its own approvals). The new
task is not opened by this one. My reading of what it needs, for the author to decide: the name-swap probes sit at
cosine 0.66 – 0.80, below the 0.85 floor, so they never count as G1 pairs; the policy-condition pairs are far
above 0.85 but share chunks (J mostly 0.2 – 0.5). Neither is a change to the gate: lowering a threshold after
seeing the data is option (3) and needs its own ADR and pre-registration.

**Not touched by this task:** `.claude/settings.json` (the author's own uncommitted change, which drops the
`Read` deny rules for `data/raw`, `data/v1-draft` and `data/v1`). Noted by `/ai-review`; it is the author's
decision and is not part of this commit.

**Correction to the S3 waiver above (2026-10-22, later).** On this Mac the sysctl returns 1 (normal), 2 (warn) or 4 (critical): `DISPATCH_MEMORYPRESSURE_*` in the SDK's `dispatch/source.h`, and a reading of 1 with 47 % of memory free. The only reading of 2 was the preflight's; all 53 readings of the run were 1, the normal level. So the run did not need a waiver, and the sentence "the numbers of this run are indicative and are not cited anywhere" is **withdrawn**. The repo's "0 = green" is wrong, and S3 and acceptance A10 as written ("level 0") cannot be met on this machine. The author's reading to confirm: `1` is green. Code, tests, Makefile, CLAUDE.md and README still say 0; see `docs/work/2026-10-22-g1-finding/spec.md`, section "The memory scale".
