---
description: Build + test + lint. Reports SKIPPED for absent tooling — never a vacuous pass.
---

Run the verification suite. Report a table: target → **PASS** / **FAIL** / **SKIPPED — not installed**.

Prefer `make verify` if the Makefile target exists; otherwise run these directly:

| Target | Command | If tool absent |
| :--- | :--- | :--- |
| Go format | `gofmt -l gateway/` (must output nothing) | SKIPPED |
| Go vet | `cd gateway && go vet ./...` | SKIPPED |
| Go build | `cd gateway && go build ./...` | SKIPPED |
| Go test | `cd gateway && go test ./...` | SKIPPED |
| Python lint | `ruff check rag/ experiments/` | SKIPPED — `pip3 install ruff` |
| Python tests | `pytest rag/ experiments/` | SKIPPED — `pip3 install pytest` |
| Proto drift | `make proto` then `git diff --exit-code` on generated stubs | SKIPPED — protoc/buf absent |

**Never report PASS for a target that did not run.** A missing linter is `SKIPPED`, and skipped targets
must be listed in the summary so the gap stays visible. Installing the absent tooling is a W5 setup task.

## On failure — the one-fix rule

1. **Exactly one** quick-fix attempt, if the cause is obvious and local (a typo, a missing import, a
   formatting nit). Re-run `/verify`.
2. If it still fails, **stop fixing** and hand off to `/rca`. Do not iterate.

**Tests are immutable.** A failing test means the code is wrong until an RCA proves otherwise. A test may
be changed only if the RCA demonstrates it is stale or the spec changed, **and the human confirms
explicitly** — recorded in `docs/work/<task>/approvals.md`. Never weaken an assertion to get green.

Record the result in the active task's `plan.md` and in this week's worklog.
