# Block B attempts — item 3.6

Every attempt, the discarded ones too: time, command, memory readings, outcome.
Memory level: `sysctl kern.memorystatus_vm_pressure_level`. First written as "0 green, 1 yellow, 2 urgent" (the repo's rule); the
SDK says 1 normal, 2 warn, 4 critical. Corrected in `approvals.md`. The readings in the table are raw sysctl values.

## Author's decision on memory (2026-10-22, in chat)

At the preflight the level read 2 with no model loaded. The author said to start anyway: "this is not
a session for measurement to collect the statistic". Recorded as a deviation from S3 / A10. What it
means here: the gate runs and records the readings; `freeze_corpus.py freeze` still refuses a report
with a non-green reading, so a freeze under non-green memory needs a separate decision from the author.

## Log

| time | step | command | memory | outcome |
| :--- | :--- | :--- | :--- | :--- |
| 22:52 | 16 | `make pqa-select-verify`, `make workload-verify`, `make redis-check`, `launchctl list \| grep redis-stack`, Ollama version | 2 (no model loaded) | pass; Ollama 0.33.2; no model loaded; Redis noeviction; `K` 1274 / 622 / 652, capacity 318 / 156 / 163 |
| 22:54 | 16 | `make env-check` (loads the LLM too), then `ollama stop` on the LLM | 2 before, 1 after | pass: np=1, ctx 8192, Ollama 0.33.2, blob matches; LLM unloaded, embedding model stays loaded |
| 22:54 | 17 | `make corpus-assemble` | 1 | A1 met: 152 + 12 = 164 files, every copy equals its source by sha256, `ls data/v1 \| wc -l` = 164 |
| 22:54 | 18 | run 1: `DATASET_VERSION=v1 make ingest` | 1 before, 1 after | 164 docs, 539 chunks, 19 s |
| 22:55 | 18 | run 1: `make corpus-index-check` | 1 | PASS: 539 chunks; ids, texts, vectors and the embedding model digest checked |
| 22:55 | 18 | run 1: `make gate-corpus REPORT=…/run1/report.json RETRIEVAL_OUT=…/run1 VECTORS=…/vectors.json` | 53 readings, all 1 | **G1 FAIL** (21 within split, need 50); stage 2 took 86 s; 0 of 1274 vectors differ from the 3.4 file; S4 and S5 not raised; no digest printed. Run kept as the figure; see `gate-failure.md` |
| 22:58 | 20 | `probe_checks.py --export-dir data/v1-draft/gate/run1` | 1 | wrote `probe-checks.md`, counts only, no asin or qa_id |
| 23:00 | 19 | decision point | | S1: stop. Steps 21 – 22 skipped. `gate-failure.md` written; the author is told |
| 23:06 | 24 | `DATASET_VERSION=dev-v0 make ingest` (loads the embedding model) | 1 before, 2 after | 44 docs, 44 chunks, tag `dev-v0`, 44 keys. Not a measurement |
| 23:07 | 26 | `make verify` | 2 | PASS (exit 0): go vet, build, test; ruff; 23 rag + 672 experiments tests. Proto drift SKIPPED |
| 23:40 | 26 | `/ai-review` fixes, then `make verify` again | | see `review.md`, "Code review" |
