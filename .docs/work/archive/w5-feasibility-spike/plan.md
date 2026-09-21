# Plan

- [x] Measure Gemma 4 E2B (smallest Gemma 4 variant, q4_K_M — smallest available quant) at the
      lightest config (`num_ctx=4096`, `NUM_PARALLEL=1`) — result: 7.7 GB resident, **yellow**
      pressure. Triggers ADR-017's own escalation clause.
- [x] Empirically compare candidate replacement models on (a) memory footprint at
      `NUM_PARALLEL∈{1,4}` × `num_ctx∈{4096,8192}` and (b) RAG-QA reasoning quality (5 structured
      domain questions: spec extraction, policy arithmetic, lookalike-trap discrimination,
      grounding/refusal, multi-attribute comparison with arithmetic): Gemma 3 1B, Gemma 3 4B,
      Qwen2.5 3B, Qwen3 4B, Qwen3.5 2B.
- [x] Update Ollama (0.22.1 → 0.32.13) after discovering Qwen3.5 2B failed with HTTP 500 on the old
      version — confirmed architecture support was the gap, not a permanent model defect.
- [x] Confirm `think: false` is required for Qwen3.5 2B (default thinking-mode otherwise burns
      ~5x the tokens/latency for no visible benefit on this task).
- [x] Measure the largest cell (`num_ctx=8192`, `NUM_PARALLEL=4`) under realistic (short,
      structured) concurrent prompts — 1.7 GB resident, green, μ_gen ≈ 28.2 tok/s aggregate.
- [x] Write ADR-021 (generation LLM: Qwen 3.5 2B replaces Gemma 4 E4B, supersedes ADR-002) to
      `docs/decisions.md`, with alternatives-rejected and the mandatory `Invalidates:` line.
- [x] Flip ADR-017 in `docs/decisions.md` from Open to Decided (frozen) with the measured pair.
- [x] Fill `docs/experiment-protocol.md` §1.1's memory-budget table and update §1's frozen-LLM line.
- [x] Update `docs/interfaces.md`'s `model_used` example/literal and the Versioning "Frozen
      study-wide" line (v0.3 → v0.4).
- [x] Append a `/log`-style entry to `docs/worklog/W05.md` recording the session.
- [x] Report the ADR IDs and one-line decisions.
