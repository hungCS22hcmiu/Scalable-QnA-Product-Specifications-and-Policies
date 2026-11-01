# experiments/

| Dir | Contents |
| :--- | :--- |
| `scripts/` | corpus gate (`corpus_gate.py`) · corpus freeze (`freeze_corpus.py`, `make corpus-assemble` / `corpus-index-check` / `corpus-freeze` / `corpus-verify`, item 3.6) · envelope check (`env_check.py`, `make env-check`, ADR-003) · Amazon-PQA builder (`build_pqa.py`, `make pqa-fetch` / `pqa-build` / `pqa-verify`, item 3.1) · workload generator (`build_workload.py`, `make workload-*`, item 3.4) · ad-hoc load burst · admission self-check · replay (`replay.py`, `make replay`) · gold-anchored references (`judge_references.py`, `make judge-gold-check` / `judge-references`) · run manifest (`run_manifest.py`, `make run-manifest` / `run-manifest-check`) · judge (`judge.py`, `make judge` / `judge-sanity`), item 5.1. ⚠️ **The figure generators do NOT exist yet** (`super-plan.md` item 5.4); `make figures` invokes a script that is not there |
| `judge/` | the frozen judge, tracked: `prompt-v1.txt` and `judge-v1.json` (ADR-022) |
| `references/{split}/` | the gold-anchored reference set, **gitignored** (question text and PQA-grounded answers): `index.jsonl`, `answers/`, `version.json` (`interfaces.md` §I) |
| `k6/` | load scenarios, run **co-hosted** (ADR-001: no second machine exists; co-hosted figures are bounds, never ceilings) |
| `results/{run_id}/` | `manifest.yaml` (required, tracked; `make run-manifest`, `interfaces.md` §I) · `raw/` (**write-once**, **gitignored** since 2026-10-06: `requests.jsonl` and `raw/answers/{answer_sha256}.txt`, ADR-005) · `judge/` (**gitignored**, written once by `make judge`) · `figures/` (regenerated, gitignored) |

`raw/` is immutable once written (write-once). It is **not published**: it holds Amazon-PQA question text
and LLM answers grounded on PQA chunks, and this remote is public.
If a run is wrong, record a new `run_id` — never edit history. Figures regenerate via `make figures`.
