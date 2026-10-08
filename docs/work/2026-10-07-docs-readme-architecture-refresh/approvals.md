# Approvals — docs-readme-architecture-refresh

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M     | n/a (scope S) | | |
| contract       | if §B/§D | n/a — no contract touched | | |
| experiment     | if measured | n/a — nothing measured | | |
| implementation | always   | yes      | 2026-10-07 | — (`/approve implementation`; no frozen value, contract or ADR touched; invalidates no run) |

**Invalidates:** nothing. Prose in two files; no frozen value, contract, ADR or measured path
changes; no `run_id` exists.

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-07 | **Implement the README and architecture.md refresh as specced**, `CLAUDE.md` left out | `/approve implementation` | none: prose only, no runs exist |
| 2026-10-07 | **Close without `/verify` or `/ai-review`** — docs-only, nothing to build, test or lint. Recorded as a waiver, not a pass | "không cần verify hay review vì đây chỉ là sửa docs. /done" | none |

## Open

Did not gate `/approve implementation`. Two things the author may want to know — (the first is now
decided by approving; the second is still open) —
1. §2 of `architecture.md` will describe the import graph as it is (`httpapi` the only composer),
   which is **stricter** than the diagram it replaces. It is written as an observation, not a rule.
2. `CLAUDE.md` is stale on the `interfaces.md` version (v0.9 → v0.12). Not edited; say so if wanted.
