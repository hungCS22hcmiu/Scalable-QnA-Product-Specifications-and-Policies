| Phase          | Required | Approved | When       | ADR      |
| impact         | yes      | yes      | 2026-08-15 |          |
| contract       | yes      | yes      | 2026-08-15 | ADR-021  |
| experiment     | yes      | yes      | 2026-08-15 | ADR-021  |
| implementation | yes      | n/a      |            |          |

Note: W5–W7 phase gate is lightweight (ADR-020) — source edits (none in this task) are allowed
without `READY_TO_IMPLEMENT`. The frozen-value tripwire (`frozen-guard.sh`) is armed regardless;
the `ADR-021` citation above is what releases it for editing `docs/decisions.md`,
`docs/interfaces.md`, and `docs/experiment-protocol.md`.
