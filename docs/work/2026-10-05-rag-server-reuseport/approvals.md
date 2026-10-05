# Approvals — rag-server-reuseport

| Phase          | Required | Approved | When | ADR |
| :---           | :---     | :---     | :--- | :--- |
| impact         | L, M — **not required** at S | | | |
| contract       | if §B/§D — **not required.** No wire, schema or §H change; the server's bind option is not a contract surface | | | |
| experiment     | if measured — **not required.** No measured path or number changes; the fix refuses a shared port, a state no valid run may be in | | | |
| implementation | always   | yes — `/approve implementation`. Scope S accepted as written; spec reviewed; impact, contract and experiment not required | 2026-10-05 | none |

## Human decisions

| Date | Decision | Author's words | Invalidates |
| :--- | :--- | :--- | :--- |
| 2026-10-05 | Open `/bugfix rag-server-reuseport`, after 1.4's commit | `/bugfix rag-server-reuseport` | — |
| 2026-10-05 | **Approve implementation at scope S.** Not raised to L | `/approve implementation` | none. No frozen value, contract or measured path changes |

## Open — needs the author

*None. Scope S was accepted at `/approve implementation`.*

## Taken by Claude as a default, open to reversal

- **Both causes in one task.** (b) is what makes (a) bite: an orphan from `make dev` is the stale
  server. Neither is complete alone.
- **The wildcard/specific residual is recorded, not fixed** (`spec.md`, "Out of scope").
- **The port pre-check in `make dev`**, added during implementation (`spec.md`, "Amendment").
  Without it, the gateway can still reach a stale server when the new one fails to bind after
  `sleep 2`. A few shell lines in the same recipe; scope unchanged.
