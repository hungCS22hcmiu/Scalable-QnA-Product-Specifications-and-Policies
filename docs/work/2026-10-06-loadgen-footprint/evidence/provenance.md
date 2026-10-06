# Provenance of the recorded runs

What is, and is not, recoverable about the code and the machine behind `evidence/footprint/` (run A) and
`evidence/footprint-mixed/` (run B). Written 2026-10-07, after the AI review found the gap.

## What the headers carry

`header.json` of both runs records the git SHA **`17bf221`** (HEAD, after the F-H commit, so ADR-006's condition
on 1.6's first `RUN_ID` holds), `tree_dirty: true` and **`sut_dirty: false`** (`git status --porcelain --
gateway rag` was empty: the system under test is the committed code), the k6 version (v1.7.1), the core count,
`OLLAMA_KEEP_ALIVE` (5m0s), the command-line arguments, the SUT's process ids, and a snapshot of the machine
before and after (`ollama ps`, `vm_stat`, the top-5 CPU processes, the raw memory sysctls).

## What they do not carry, and why it is not recoverable

- **The sampler** (`experiments/scripts/loadgen_footprint.py`) and **`ask.js`** were **uncommitted** when the
  runs were taken (`tree_dirty: true` covers exactly this), and the headers did not hash them. Run A used the
  sampler as it stood after the shakedown; run B used it after the `workload_arg` fix. **Neither version was
  kept**, so neither hash can be supplied.
- **`ask.js`** has since had its header comment rewritten (comment lines only; `git diff` shows no code line
  changed, and `k6 inspect` still parses it). k6 reads `ask.js` at every invocation, so both runs used the
  pre-edit file, whose code is identical.

## What was done about it

- Since this review the header also records `sampler_sha256` and `ask_js_sha256`, so a *future* run is
  attributable. `summarize` refuses to guess the core count when `header.json` is missing.
- The sampler was **changed after the runs** (guards for a wrong process, for sampled CPU far below `wait4`'s
  total and for many discarded ticks; a dependency-region-safe flush that follows `--redis-port`; the LLM
  runner's RSS column; a non-zero exit status when rows are excluded; the hashes). The tables of both runs
  were **regenerated from the stored per-second CSVs** with the changed module. **The two main tables, every
  row in `summary.json`, the fit and every exclusion are identical to the originals** (compared with `diff`
  and by value on 2026-10-07); the regenerated `footprint.md` differs only by the new columns and the reworded
  window note. No recorded row trips a new guard.
- The sampler module as of the end of the review round has sha256 prefix `79f8137bb50a8b23`
  (`mutation_run.txt` records it); the rebuilt tables came from that file.

## What this means for a reader

Treat the recorded numbers as produced by *a version of the sampler whose behaviour is pinned by the stored
CSVs and by the regeneration check above*, not by a hash. The derived table can be rebuilt from the CSVs
(`loadgen_footprint.py summarize`); the CSVs themselves were written by the unrecoverable version.

## Cosmetic, for the author before anything is committed

`header.json` holds the names of the processes using the most CPU at the time (some are the author's own
applications), and the k6 stdout/stderr files hold absolute `/Users/...` paths. Neither is a contract matter;
this remote is public, so review them before `git add`.
