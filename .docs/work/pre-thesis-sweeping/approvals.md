# Approvals — pre-thesis-sweeping

| Phase | State | Who / when |
| :--- | :--- | :--- |
| impact | not produced | — |
| contract | **not produced** | — |
| experiment | **not produced** | — |
| implementation | **not granted** | — |

## ADRs recorded by this task

Cited here because `frozen-guard.sh` releases edits to `docs/decisions.md` and the other frozen
documents only against a cited ADR. These four were **decided with the advisor on 2026-09-10** and
applied to the report and proposal on 2026-09-15; the decision log had no record of any of them,
which is `Pre-thesis_Sweeping.md` §0 — the blocking finding that everything else stood on.

| ADR | Decision | Frozen artifacts it authorises changing |
| :--- | :--- | :--- |
| **ADR-035** | Adopt the answer–evidence support gate (lexical at the published `tau_s`, plus a numeric arm), as an on/off ablation arm | `decisions.md`; `interfaces.md` §H (refusal cause code); `experiment-protocol.md` (config 4 becomes two arms) |
| **ADR-036** | Retire the unfiltered similarity-only phase, `tau_high`, and the inline `similarity_only_decision` | `decisions.md`; `interfaces.md` §H; `experiment-protocol.md` §4/§6 and the drop order |
| **ADR-037** | `Retrieve` returns chunk text — `interfaces.md` **v0.9** | `interfaces.md` §B; `contracts/rag/v1/rag.proto` |
| **ADR-038** | Condition-splitting is a `v1` corpus requirement; corpus gate gains **G5** | `decisions.md`; `data-card.md` §2, §7 |

## What is recorded but NOT yet carried into the contracts

`decisions.md` is written. `interfaces.md`, `experiment-protocol.md` and `data-card.md` are **not
yet edited** to match — the same lag that ADR-032 left behind and that `two-lane-cache`'s trail had
to record as "still owed". Tracked here so it is not rediscovered:

- [ ] `interfaces.md` → **v0.9**: §B `texts` (ADR-037), §H refusal cause code and the removal of
      `similarity_only_decision` (ADR-035, ADR-036), plus the version bump and Versioning section.
- [ ] `contracts/rag/v1/rag.proto`: `repeated string texts` on `RetrieveResponse` (ADR-037).
- [ ] `experiment-protocol.md`: *decisions changed by provenance* as a cross-configuration join on
      the static-cache arm; configuration 4 as two arms; drop order corrected (ADR-035, ADR-036).
- [ ] `data-card.md`: §7 gate becomes **five** criteria (G5 structural, stage 1); §2 records
      condition-splitting (ADR-038).
- [ ] `CLAUDE.md`: the interfaces reference still reads v0.8.

## Open, and not this task's to decide

- **Task `two-lane-cache`** — close properly or explicitly abandon (`Pre-thesis_Sweeping.md` §0.2).
- **F1** (Ollama overriding `OLLAMA_NUM_PARALLEL` to `-np 1`) — outside this order and above it.
