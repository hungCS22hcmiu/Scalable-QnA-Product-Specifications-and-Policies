# experiments/

| Dir | Contents |
| :--- | :--- |
| `scripts/` | corpus gate (`corpus_gate.py`) · envelope check (`env_check.py`, `make env-check`, ADR-003) · corpus fetcher · ad-hoc load burst · admission self-check. ⚠️ **The workload generator, replay harness, judge harness and figure generators do NOT exist yet** — this row claimed all four until 2026-09-21. They are `super-plan.md` items 3.4, 5.1 and 5.4; `make figures` invokes a script that is not there |
| `k6/` | load scenarios (W8+, run off-box) |
| `results/{run_id}/` | `manifest.yaml` (required) · `raw/` (**write-once**, **gitignored** since 2026-10-06: `requests.jsonl` and `raw/answers/{answer_sha256}.txt`, ADR-005) · `figures/` (regenerated, gitignored) |

`raw/` is immutable once written (write-once). It is **not published**: it holds Amazon-PQA question text
and LLM answers grounded on PQA chunks, and this remote is public.
If a run is wrong, record a new `run_id` — never edit history. Figures regenerate via `make figures`.
