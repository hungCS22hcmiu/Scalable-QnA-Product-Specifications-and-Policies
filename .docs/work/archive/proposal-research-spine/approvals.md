| Phase          | Required | Approved | When       | ADR                        |
| impact         | yes      | yes      | 2026-08-18 |                            |
| contract       | no       | n/a      |            |                            |
| experiment     | yes      | yes      | 2026-08-18 | ADR-023                    |
| implementation | yes      | yes      | 2026-08-18 | ADR-022, ADR-023, ADR-024  |

Human approval recorded 2026-08-18 (plan approved in session). W5-W7 phase gate is lightweight
(ADR-020), but this task edits all three frozen documents, so the ADR citations above are what
release `frozen-guard.sh`:

- **ADR-022** - admission-control mechanism. Closes the largest gap found: the 60%-weighted systems
  contribution had **no ADR at all**.
- **ADR-023** - five-configuration ladder x source-mutation axis. Changes `config_id` semantics in
  `experiment-protocol.md` Section 2, so the experiment phase is required.
- **ADR-024** - `v1` corpus data model: product<->policy join key, per-category warranty windows,
  multi-chunk policy documents, A/B/C/D stratum taxonomy, and the sensitivity gate's overlap formula.

**Invalidates: none.** `experiments/results/` contains no run directories - confirmed 2026-08-18.
Restructuring the configuration ladder today voids zero measurements.
