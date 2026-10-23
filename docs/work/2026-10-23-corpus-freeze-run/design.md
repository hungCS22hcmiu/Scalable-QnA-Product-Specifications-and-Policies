# Design — corpus-freeze-run

**Inherited.** There is no new design: nothing is built in this task. The freeze tooling is designed in
`2026-10-22-corpus-freeze/design.md` (opus design review in its `review.md`, plus a code review of 9 findings), and the allowance in
`2026-10-22-g1-finding/design.md` (opus design review of 7 findings, plus a code review of 4). Both reviews are resolved. Scope L asks for a
design and a review; this task points to them instead of repeating them, and says so in `spec.md`.

## The run, in order (what is new here is only the order and the folder names)

```
assemble (again, idempotent) ─► ingest v1 ─► index check ─► gate A  ─► freeze-a/        exit 3, expected
                                 │                                    compare with first-run/ by hand (S1)
                                 └─ fresh ingest ─► index check ─► gate B  ─► freeze-b/  exit 3, expected
freeze   (RUN1=freeze-a  RUN2=freeze-b)  ─► data/v1-freeze.json  ─► corpus-verify ─► corpus-index-check
documents (data-card §7, ADR-015, architecture, README, super-plan)  ─► restore dev-v0  ─► make verify
```

## Failure modes

| Failure | Silent? | Guard |
| :--- | :--- | :--- |
| Memory not at `1` during a run | would be | the gate reads it itself and flags S3; `freeze` re-checks; the author checks it before |
| A re-run overwrites the first run | would be | new folders; `first-run/` holds hashes in `evidence/first-run-pin.md` |
| Run B quietly differs from run A | would be | `freeze` refuses on pass/fail, accepted set, digest, stack; the counts are compared by hand against the first run |
| A file changed after the pin | would be | the gate does not honour `--accept-failed` (digest differs); `freeze` re-checks |
| The tree is dirty while a run is made | would be | `git.tree_clean` false and `freeze` refuses (S6) |
| The record looks like a pass | would be | `passed: false` in both reports, `known_failures` in the record, ADR-014 and ADR-015 |
| A tracked file gets an asin or qa_id | would be | `freeze` refuses; a grep of every changed file at the end |

## Unknowns

1. Whether run A reproduces the first run **exactly** (same retrieval exports, same sha256). The offline checks said yes; the first live
   re-run will show. If the exports differ but the counts agree, that is recorded and S1 does not fire; if a count differs, it does.
2. Whether `make` handles exit 3 cleanly in the real target (tested only on a scratch recipe).
3. What `data-card.md` §7 needs beyond the ten markers: the status paragraph wording for G1 is proposed in the plan and is the author's.
