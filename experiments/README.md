# experiments/

| Dir | Contents |
| :--- | :--- |
| `scripts/` | corpus gate (`corpus_gate.py`) · corpus fetcher · ad-hoc load burst · admission self-check. ⚠️ **The workload generator, replay harness, judge harness and figure generators do NOT exist yet** — this row claimed all four until 2026-09-21. They are `super-plan.md` items 3.4, 5.1 and 5.4; `make figures` invokes a script that is not there |
| `k6/` | load scenarios (W8+, run off-box) |
| `results/{run_id}/` | `manifest.yaml` (required) · `raw/` (**write-once**) · `figures/` (regenerated, gitignored) |

`raw/` is immutable once written (`experiment-protocol.md` §3, `.docs/ai/rules.md` #3).
If a run is wrong, record a new `run_id` — never edit history. Figures regenerate via `make figures`.
