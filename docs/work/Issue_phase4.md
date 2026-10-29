# Issues found while closing Phase 4

Written 2026-10-29, after item 4.4 and Phase 4 closed (commits `68d732e`, `6a469e9`, `650a1ec`). Two issues
need debugging, and three more are open but are not bugs. They are in order of importance. The short form is
in `docs/super-plan.md`, Phase 4, "Found while closing 4.4, not yet items".

---

## Issue 1 — Ollama's prompt cache uses about 6 GB of RAM

**Status:** open. The next `/bugfix`. It blocks item 7.1 and every citable run that loads the LLM.

### Symptom

During the 4.4 live runs (`docs/work/2026-10-29-update-set/evidence/live1`–`live3`), Ollama's Qwen runner
used about 6.3 GB. That is more than three times the 1.7 GB in the README's stack table. Memory pressure
moved from 1 (green) to 2 (yellow) during each run.

### Mechanism

The evidence is in `~/.ollama/logs/server.log`, at the last load of `qwen3.5:2b-q4_K_M`
(blob `sha256-7a3a8d55…f520`).

- **The cache.** Ollama 0.33.2 starts `llama-server` with no `--cache-ram`, so llama-server's **prompt
  cache** gets its default limit of **8192 MiB**. The cache keeps the state of earlier prompts in RAM, so a
  later prompt can skip re-reading a shared start. The log says so at load: "prompt cache is enabled, size
  limit: 8192 MiB", and "use `--cache-ram 0` to disable the prompt cache".
- **Why each entry is heavy.** Qwen 3.5 is a hybrid model: 6 attention layers and 24 recurrent layers. A
  saved prompt holds both kinds of state, about 67 MB on average. One run ended with "cache state: 89 prompts,
  5976.794 MiB (limits: 8192.000 MiB …)". The cache keeps growing until it reaches 8 GB.
- **It gives almost nothing back.** In the last run, 116 of 130 Qwen prompts logged "forcing full prompt
  re-processing due to lack of cache data (likely due to SWA or hybrid/recurrent memory)". Only 12 logged
  "restored context checkpoint", and most of those reused 46–91 tokens. Averaged over all requests, the cache
  saved about 0.02 s against a median of 3.4 s per request: 1.3 s to read the prompt (about 620 tokens at 485
  tokens/s) and 2.0 s to generate (about 72 tokens at 36 tokens/s).
- **A side issue: the vision encoder.** Ollama passes the model file a second time as `--mmproj`, so Qwen's
  vision encoder loads too. The log lists "model size: 1945.46 MiB" for it, plus 223 MiB and 25 MiB of
  compute buffers, and we never send images. How much of that stays in RAM is not known.

What a load costs without the cache, from the same log:

| Part | Size |
| :--- | :--- |
| Text model weights | 1.57 GB (397.85 MiB CPU + 1175 MiB Metal) |
| KV cache, recurrent state, compute buffers | about 0.2 GB (96 + 19 + 56 + 16 MiB) |
| Embedding model (`nomic-embed-text`) | 0.37 GB |

### Why it matters

- **It breaks a claim in the thesis.** CLAUDE.md and the admission argument say memory is fixed when the
  runner loads, and that admitting requests adds none. On Ollama 0.33.2 this is false: memory grows with each
  new prompt.
- **It breaks the envelope.** Other apps already use about 9–10 GB of the 16 GB. Another 6–8 GB pushes the
  machine into yellow or red, so any Phase 7 run would be invalid.
- **It is a hidden second cache.** In the `no-cache` configuration, the same popular question is sent many
  times (Zipf), and llama-server could reuse most of that prompt's prefill. The baseline would look faster than
  it is, and the comparison with the gateway's cache would be biased.
- **Nothing catches it today.** `make env-check` checks the slot count, `num_ctx`, the Ollama version and
  the weights blob, but not this cache.

### What we know about a fix

This comes from reading the binaries. Nothing has been changed yet.

- The bundled `llama-server` (`/Applications/Ollama.app/Contents/Resources/llama-server`) has
  `--cache-ram N`: "set the maximum cache size in MiB (default: 8192, -1 - no limit, 0 - disable)". It also
  reads the environment variable **`LLAMA_ARG_CACHE_RAM`**.
- Ollama (`…/Resources/ollama`) has no setting of its own for this, and passes no `--cache-ram`. So
  `LLAMA_ARG_CACHE_RAM=0` in Ollama's environment should turn the cache off, **if** Ollama passes its
  environment down to the llama-server it starts.
- Related options: `--ctx-checkpoints N` (env `LLAMA_ARG_CTX_CHECKPOINTS`, default 32) may be part of why
  each entry is heavy. `--no-mmproj` (env `LLAMA_ARG_MMPROJ_AUTO`) controls the vision encoder.
- The runner command Ollama used:
  `llama-server --model <blob> -c 8192 -np 1 … --mmproj <same blob> --flash-attn auto -b 512 -ub 512
  --context-shift --keep 4`.

### Unknowns the RCA must settle

1. Does the variable reach llama-server? Ollama.app starts from launchd, so it may need `launchctl setenv`
   and a restart of Ollama.
2. Can the vision encoder be turned off? Ollama passes `--mmproj` on the command line, and a flag on the
   command line usually wins over an environment variable.
3. Does turning the cache off change response time? The log suggests about 1 % at most, but it must be
   measured.
4. Does the setting survive an Ollama restart, an Ollama update, and a reboot?

### Draft done conditions

- **The failing check first:** send about 50 different prompts and record llama-server's memory and the log's
  "cache state" line. Before the fix, memory grows. After the fix, it stays flat, and the log says "prompt cache
  is disabled".
- **Response time:** the median request time on the same prompts, before and after, stays within a limit
  chosen in advance.
- **`make env-check` fails while the cache is on.** That way an Ollama update cannot bring it back silently.
- **A decision record.** This changes the frozen Ollama envelope (ADR-003's runner), and the 1.7 GB figure
  must be checked again.

---

## Issue 2 — tools still tied to the retired `dev-v0`

**Status:** open, smaller. The author retired `dev-v0` on 2026-10-29, so Redis now holds `v1` (539 chunks).

| Tool | What happens with `v1` in Redis |
| :--- | :--- |
| `make demo-reset` | **Dangerous.** It runs `FLUSHALL`, then ingests `dev-v0`. One run wipes `v1`, `idx:cache`, `dep:` and `entry:` from Redis. Its guard checks only port 8080, so a gateway on another port is not caught. |
| `make demo` | Broken. The four questions (`DEMO_Q1`, `DEMO_Q3`, `DEMO_Q4` in the `Makefile`) are about `dev-v0` products: "my headphones", "my sofa". |
| `make seam-check` | Broken. `gateway/internal/ragclient/seam_live_test.go` pins `product-laptops-02`. |
| `make support-check` | Broken. `gateway/internal/ragclient/support_live_test.go` pins `product-headphones-03` and `policy-returns-electronics`. |

**Why it matters.**
- **`seam-check` is the only live check** that `texts` reach Go aligned with `chunk_ids`. CLAUDE.md says to
  re-run it after any retrieval change, and today it cannot run on the working corpus.
- **The demo is a Phase 8 deliverable.** And **`demo-reset` can silently cost us the working corpus.**
  Restoring it takes `make ingest`, then `make corpus-index-check`, about a minute.
- **It is not a silent-wrong-number bug.** Each tool fails loudly or wipes data in plain sight.

**The fix needs the author's approval.** `seam_live_test.go` and `support_live_test.go` are existing tests,
so moving them to `v1` products is the author's call, as with the two scoping tests in 4.4. A quick guard for
`demo-reset` can come first: refuse while Redis holds `v1`.

---

## Open, but not bugs

- **No super-plan item owns RQ3's TTL baseline.** `Final_Proposal.md` RQ3 compares blind purge against a swept
  TTL curve, and no item builds it. This is a planning decision: add an item, or cut it by the drop order in
  `Final_Proposal.md` §12.
- **CLAUDE.md has stale lines** (the author's file). It says `deps/` "is a one-line stub", `make ingest` reads
  `dev-v0`, `interfaces.md` is "at v0.9", and "admitting requests adds no memory".
- **Precision is judged per edit, not per entry** (item 4.4, design §2). Every dependent of a `substantive`
  edit counts as needed, even when its answer does not use the changed fact. This is a method limit. Phase 7
  should report it next to the number.

## Suggested order

1. Issue 1, as a `/bugfix`. It affects every LLM run, and it blocks item 7.1.
2. Issue 2, as a small task, with the author's approval for the two test files and the `demo-reset` guard
   first.
3. The TTL decision and the CLAUDE.md edits, whenever the author likes.
