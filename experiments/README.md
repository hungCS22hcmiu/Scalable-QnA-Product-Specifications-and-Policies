# experiments/

| Dir | Contents |
| :--- | :--- |
| `scripts/` | workload generator, replay harness, judge, figure generators |
| `k6/` | load scenarios (W8+, run off-box) |
| `results/{run_id}/` | `manifest.yaml` (required) · `raw/` (**write-once**) · `figures/` (regenerated, gitignored) |

`raw/` is immutable once written (`experiment-protocol.md` §3, `.docs/ai/rules.md` #3).
If a run is wrong, record a new `run_id` — never edit history. Figures regenerate via `make figures`.
