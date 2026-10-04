# Spec — resolve-f1

**Scope:** L · **Opened:** 2026-10-04 · **Phase:** 1, item **1.1**

## The change in one sentence

Make `make env-check` verify the **effective** generation slot count, meaning the slot count the
running `llama-server` runner actually serves for the frozen LLM, not the value requested through
`OLLAMA_NUM_PARALLEL`. Then record, in a numbered ADR, what the envelope's frozen value becomes and
what μ_gen ≈ 28.2 tok/s means, given that the runner has never served more than one slot.

## What it serves

- **Phase 1, item 1.1** (`super-plan.md`): *"`make env-check` fails when effective ≠ frozen, and
  an ADR records the consequence for μ_gen."*
- **Exit-criterion clause discharged:** *"`make env-check` fails when the effective Ollama slot
  count differs from the frozen value."*
- **Discharges:** **S1** (capacity: μ_gen is the left term of λ_max) and **S2** (stability: the
  admission pool is sized from this value). `contracts/requirements.md` is still empty, so there
  is no FR/NFR/RR ID to cite yet.
- **Standing constraint 1:** *"F1 sits above the order."* No admission-control number is citable
  until this closes.

## F1, confirmed on 2026-10-04

Until today F1 was a note in `decisions.md`, `Makefile:64` and `main.go:160`. It is now confirmed
from the **running** server's own log. Evidence is preserved in `evidence/ollama-np-override.txt`,
because the source file lives under `/private/tmp`, which is cleared on reboot.

| Observation (ollama 0.33.2, server up since 2026-09-06) | Count |
| :--- | ---: |
| Server environment `OLLAMA_NUM_PARALLEL` | **4** |
| `qwen35` runner loads | 26 |
| `WARN sched.go:509 "model architecture does not currently support parallel requests" architecture=qwen35` | **26 / 26** |
| Runner launched with `-c 8192 -np 1` | **26 / 26** |
| Runner reports `n_slots = 1, n_ctx_slot = 8192` | **26 / 26** |
| Any runner with `-np` ≠ 1, or `n_slots` ≠ 1 | **0** |

**The cause is an Ollama scheduler rule, not a configuration mistake.** Ollama's scheduler refuses
parallel requests for the `qwen35` architecture and launches the runner at `-np 1` whatever the
environment requests. No environment setting changes this. Only a different model architecture or
a different serving stack could.

**The older logs say something different, and weaker.** In `~/.ollama/logs/server-{3,4,5}.log`
(2026-08-15/16, a different Ollama build: `llama_server.go:431` against today's `:433`), every
server start carried `OLLAMA_NUM_PARALLEL:1`. So in the surviving W5-era logs, 4 was never even
requested. The logs from before 2026-08-15 19:00 have rotated away. **No surviving log shows a
`qwen35` runner with more than one slot, ever.** The spike itself ran on Ollama **0.32.13**, while
the live server is **0.33.2**, and no tracked file pins the version (`impact.md` §4).

Three consequences frame the decision:

1. **μ_gen ≈ 28.2 tok/s was, on all surviving evidence, a one-slot rate** recorded as *"aggregate
   at `OLLAMA_NUM_PARALLEL = 4`"*.
2. **The gateway grants 4 permits** (`main.go:165`) **to a server that serves one stream.** Three
   admitted requests queue *inside* Ollama, where the gateway can neither see nor shed them. Any
   shed rate or p99 taken in this configuration would partly describe Ollama's internal queue.
   *(Corrected after `impact.md` §3: none has been recorded yet. The risk is forward-looking,
   which is why it must close before Phase 7.)*
3. **The W5 spike pre-registered this outcome.** Its go/no-go clause reads: *"admission pool admits
   one generation at a time … degenerates to a mutex … proposal §5/§6.2 must be reframed around
   queueing and shedding"* (`21aaaec^:.claude/commands/spike.md`). That branch fired and nobody
   noticed. `Final_Proposal.md:338` records the opposite (`impact.md` §1).

## Acceptance — runnable checks

1. **The detector fails on a mismatch.** With the frozen LLM loaded, `make env-check` exits
   non-zero whenever the runner's effective slot count differs from the frozen value, and it
   prints both values.
2. **The detector fails closed.** `make env-check` exits non-zero, with the reason printed, when
   the effective value cannot be established: Ollama unreachable, the model not loaded and not
   loadable, no runner matched, more than one runner matched, or an argument that cannot be
   parsed. "Unverifiable" must never read as "verified".
3. **The detector logic is tested offline.** A pytest suite runs the parsing and decision logic
   against captured `ps`/log fixtures: a matching runner passes; `-np 4` against a frozen 1 fails;
   the embedding runner alone fails (it must not be mistaken for the LLM's); zero or two LLM
   runners fail. The suite needs no running Ollama.
4. **The ADR exists.** `decisions.md` carries a numbered entry (the next free number is **ADR-003**:
   ADR-001 is reserved, ADR-002 is taken). It states the frozen slot value, what μ_gen ≈ 28.2
   tok/s means under it, and what the decision **invalidates**.
5. **Every pin agrees with the ADR.** Each pin listed in `impact.md` §1 ("must change") carries
   the same frozen value: the Makefile export and spike echo, the LaunchAgent plist, the gateway's
   permit default, `decisions.md` *Inherited state*, `interfaces.md:507`, `CLAUDE.md` and
   `README.md`. A `grep` over the tracked tree finds no other live statement of the old value.
   History, `pool_test.go`'s mechanism constant and the ADR's own text are exempt.
6. **On the live machine, `make env-check` passes** once the pins agree, with Ollama running and
   the LLM loaded.

## Out of scope

- **Changing the LLM.** The model is frozen (`CLAUDE.md`). A model whose architecture Ollama
  parallelises would be a model swap, and that invalidates every cross-configuration comparison.
- **Upgrading Ollama, or serving through raw `llama-server`.** Either is a serving-stack change.
  The ADR may name it as a future option, but this task does not take it.
- **Re-measuring μ_gen under sustained load.** That is Phase 7. This task decides what the
  existing spike number *means*. It does not replace it.
- **The embedding runner's single slot.** `nomic-bert` also launched at `-np 1`, 48 / 48 times.
  That bears on the Tier-2 hit path's μ_hit, not on F1. It is recorded as a finding for Phase 7
  and not acted on here.
- **Sweeping `GEN_QUEUE_BUDGET`.** Its default **does** change, 8 → 2, because the rule
  `2 × permits` (`main.go:168`) is kept. The ADR accepts that explicitly, and the value is a DEMO
  value, not a frozen one. No new queue size is chosen here.
- **ADR-001** (co-hosted measurement, item 1.6).
- **`Final_Proposal.md` prose.** It is gitignored submitted prose. Its F1-affected sentences
  (§3, §7 and the μ_gen bullets) are listed as a follow-up and not edited here.
