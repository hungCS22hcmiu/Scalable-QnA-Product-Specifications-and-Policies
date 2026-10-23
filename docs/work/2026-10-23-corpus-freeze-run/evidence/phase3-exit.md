# Phase 3 exit, run by hand — 2026-10-23 (plan step 12)

The line, as amended in `docs/super-plan.md` at the author's instruction to close the phase (the wording ADR-014 proposed): *G2…G5 pass, G1 is
recorded as ADR-014's finding with its counts, and `make gate-corpus` prints the snapshot digest under a recorded failure · `K`, the derived
capacity and every frozen corpus statistic are recorded in `data-card.md` · the validation/test splits are frozen with the dataset.*

| Clause | Command or file | Result |
| :--- | :--- | :--- |
| G2, G3, G4, G5, `W`, `S` pass | the gate output of runs A and B | PASS in both (G2 in each split) |
| G1 recorded as ADR-014's finding, with its counts | gate output; `data/v1-freeze.json` `known_failures`; `data-card.md` §7 | G1 FAIL 21 = 13 + 8, floor 50, 18 across; recorded as `known_failures` (ADR-014); `data-card.md` §7 has the status paragraph |
| `make gate-corpus` prints the digest under a recorded failure | runs A and B | `--- FREEZE WITH A RECORDED FAILURE (G1, ADR-014) ---`, digest `a5708fefa62c…` (the pin), exit 3 |
| `K`, capacity and every frozen corpus statistic are in `data-card.md` | `grep -n "TODO(W8)" docs/data-card.md` | 4 matches: the purpose sentence (line 6) and three markers that are not this item's (paraphrase set, update set ×2). `K` 622 / 652, capacity 156 / 163, the G1 – G5 results, the pair breakdown, the overlap distribution, the strata and the trap fractions are filled |
| The splits are frozen with the dataset | `data/v1-freeze.json` (167 files = 164 corpus + the whole workload file and its two split files); `make corpus-verify` | PASS: 167 files, 539 chunks, the embedding model and the retrieval config |

**Result: the amended exit is met.** Against the original line ("G1…G5 all pass") it is **not** met, by design (ADR-014): G1 failed and is
recorded as a finding. The record, the ADRs and the data card all say so, and nowhere is it called a pass.
