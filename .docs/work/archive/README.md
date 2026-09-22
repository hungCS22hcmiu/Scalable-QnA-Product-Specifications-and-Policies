# Archived task trails

Closed trails from the pre-thesis phase, moved here **2026-09-21** (`Pre-thesis_Sweeping.md` §2.2,
§2.4). They are archived, **not deleted**, and the reason is evidence rather than sentiment.

`.docs/README.md` states why this directory exists at all: the write-up must produce a **design
chapter** and an **evaluation chapter**, and both ask *"what did you actually do, in what order,
and why"* — a question memory will not answer months later. These five trails are that record for
everything before the thesis phase. They have version history for the first time as of the
2026-09-21 base commit; before that `.gitignore` excluded `.docs/` entirely.

**Do not edit them.** A closed trail is a record of what was believed and decided at the time. If
something in one turns out to have been wrong, that correction belongs in `docs/decisions.md` or
`docs/worklog/journal.md`, not in a rewrite of the history.

| Trail | What it holds | Still cited by |
| :--- | :--- | :--- |
| `w5-feasibility-spike` | The memory-envelope measurement that froze `num_ctx` and `OLLAMA_NUM_PARALLEL`, and the five-model comparison that replaced the generation LLM | ADR-017, ADR-021 |
| `w5-corpus-pipeline` | `dev-v0` ingestion, chunking, the stable chunk-ID scheme | ADR-008, ADR-014 |
| `w6-rag-gateway-skeleton` | The Go↔Python seam coming up end to end | `interfaces.md` §B |
| `proposal-research-spine` | The rebuild of the proposal's research logic — why each design decision is argued the way it is | `Final_Proposal.md` |
| `mvp-advisor-demo` | ⚠️ **Reclassified.** Filed as a task trail, but it held *approved decisions* | see below |

## `mvp-advisor-demo` — why it was reclassified, and what moved out of it

`Pre-thesis_Sweeping.md` §2.4 found that this directory was doing two jobs. It was filed as a task
trail, but `Recommended_system.md` §5–§6 held **decisions the advisor approved on 2026-09-10** that
the decision log had no record of. A decision living only in a task trail is invisible to everyone
who reads `docs/` as the source of truth — which is everyone, by instruction.

The decisions were lifted into the decision log on 2026-09-21 and are now in force there:

| ADR | What it records |
| :--- | :--- |
| **ADR-035** | Adopt the answer–evidence support gate at its published threshold, as an on/off ablation arm |
| **ADR-036** | Retire the unfiltered similarity-only phase, `tau_high`, and the inline counterfactual |
| **ADR-037** | `Retrieve` returns chunk text — the contract change without which the gate cannot run |
| **ADR-038** | Condition-splitting as a `v1` corpus requirement; the corpus gate's fifth criterion |

**`Recommended_system.md` is still live reading, not history.** Its §4 and §8 are the build order
for what those ADRs decided, and its §4 ranks **F1** first — no admission-control number is citable
until that resolves. `docs/super-plan.md` cites it as the build order until #3 is filled.
