# Task: W5 feasibility spike — freeze generation LLM + memory envelope

**One sentence:** Run the W5 feasibility spike against the real hardware constraint (machine shares
RAM with other daily-driver apps, disciplined to ~9-10 GB used / ~5-6 GB free before testing), find
that the frozen ADR-002 model (Gemma 4 E4B) does not hold green pressure even at the lightest
config, escalate through ADR-017's own escalation clause to a smaller model, and freeze the result.

**Serves:** `docs/time_line.md` W5, blocking gate 1 (`/spike` → freeze ADR-017, record μ_gen) and
gate 2 (embedding/chunking still separately open — not touched by this task).

**Acceptance (ties to W5 Done-when):**
- Memory budget measured and published (empirical, not assumed).
- Envelope frozen at green pressure under sustained concurrent load at the chosen config.
- μ_gen recorded.
- ADR-017 flipped from Open to Decided.
- Generation-LLM choice re-frozen (supersedes ADR-002) with alternatives and rejection reasons on
  the record.

**Out of scope:** embedding model choice (ADR-003, separate open item), chunking config (ADR-014,
separate open item), building `dev-v0` or the actual ingestion pipeline (later W5 tasks), building
`rag/`/`gateway/` source (W6+).

**Context — why the original choice didn't survive contact with measurement:**
The proposal's hardware envelope (§7) assumes ~16 GB available to the system under test. The
author's actual machine runs other projects continuously; empirically only ~1-6 GB is free at any
time, not the ~14-16 GB the original spike design implicitly assumed. Measured on this real
constraint: Gemma 4 E2B (the smallest Gemma 4 variant, smallest available quant) already enters
**yellow** memory pressure (`kern.memorystatus_vm_pressure_level=2`) at the lightest possible
config (`num_ctx=4096`, `NUM_PARALLEL=1`, single request) — 7.7 GB resident. This is exactly the
condition ADR-017 already names as its own escalation trigger: *"Not even NUM_PARALLEL=1 green at
num_ctx=4096 → the binding constraint is the model, not concurrency. Escalate to a smaller
quantization or model."* No smaller official quant exists for Gemma 4 E2B, so the escalation went
to smaller models, tested empirically across five candidates (Gemma 3 1B, Gemma 3 4B, Qwen2.5 3B,
Qwen3 4B, Qwen3.5 2B) for both memory footprint and RAG-QA reasoning quality (5 domain-specific
test questions per candidate, including a lookalike-trap and a grounding/refusal test). Full detail
in `docs/worklog/W05.md`.
