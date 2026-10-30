# The update set — 20 controlled edits that measure invalidation

**For:** a reader who is new to this project · **Describes:** the code at commit `29b24a6` (30 Oct 2026),
checked on 30 Oct 2026. The update-set scripts last changed in `68d732e` (item 4.4).
**About the numbers:** every number here comes from three functional runs on `v1` (29 Oct 2026, pressure 1–2).
**None is citable.** RQ3's numbers come from item 6.5.

**Read first:** [`Invalidation.md`](Invalidation.md), for what a purge does. This doc is about how the purge is
**measured**. The file format is in `docs/data-card.md` §5.

---

## 1. What the update set is for

Blind purge removes **every** answer built on an edited chunk (`Invalidation.md` §2). Two questions follow:
- **Does it remove all of them?** That is **completeness**. It must be 1.
- **How many did it remove for nothing?** A small rewording also removes answers that were still correct.
  That is **over-invalidation**, the price blind purge pays for completeness, and **precision** measures it.

The update set is a fixed list of edits, each labelled with whether it changes an answer, so both can be
counted instead of assumed.

## 2. The 20 edits

| | Policy chunks | Product chunks | Total |
| :--- | ---: | ---: | ---: |
| `substantive`: changes a fact an answer could state | 5 | 5 | 10 |
| `cosmetic`: rewords, keeps every fact and number | 5 | 5 | 10 |
| **Total** | **10** | **10** | **20** |

- **20 different chunks**, one edit each.
- **Only chunks that the questions really reach.** A probe (`make update-set-probe`) records which chunks the
  validation questions retrieve. Every edited chunk is retrieved by questions from at least 5 seed clusters,
  so every edit has answers to purge.
- **The drafting rules.** A `substantive` edit changes a number, a time window, a condition or a spec value.
  A `cosmetic` edit rewords, and a validator checks that every number in the old text is still in the new
  one. Each edit also says which cached answers should go stale, or why none should (`expected_effect`).
- **The demo edit**, `edit-001`, changes "30 days" to "14 days" in the first chunk of
  `policy-return-electronics`, a policy we wrote ourselves.
- **The author reviewed every label** on 29 Oct 2026. Four product rewordings (a section label and one phrase
  each) were accepted as `cosmetic`.
- **The file is private.** `data/update-set-v1.json` holds Amazon-PQA product text, so it is gitignored. The
  tracked `data/update-set-manifest.json` holds only its sha256 and its counts. `make update-set-verify`
  checks the set against the `v1` chunk texts, offline.

## 3. One run, step by step

`make update-set-check EVIDENCE=<new folder>` runs the whole check (`experiments/scripts/update_set_check.py`).
It loads both models. It is **not a measurement**: memory pressure is recorded, never a gate. While it runs,
Redis differs from `v1`, so nothing else may use Redis or Ollama.

1. **Check the preconditions** and save the original text and vector of every chunk it will edit.
2. **Force the race** (`Invalidation.md` §9): ask a question that reads the 30-day chunk, apply that edit
   1.5 s later, and check that the write-back is discarded.
3. **Reset and fill the cache:** up to 3 validation questions per edit, from different clusters, plus 10
   questions that no edit touches.
4. **Snapshot both tiers**, apply the 20 edits through `rag.edit`, and **snapshot again**.
5. **Ask every dependent's question again.** None may come back as a hit.
6. **Restore** the 20 chunks, stop, reset, and check that every chunk holds its saved text and vector.
7. **Score** the saved IDs (§4).

The cache is **unbounded** during the run, so no eviction can look like a purge. Files that hold question IDs
or chunk IDs (which can carry an Amazon product ID) stay in `EVIDENCE/private/`, gitignored. Only `score.json`
(counts, keyed by `edit_id`) and `pressure.txt` are committed.

## 4. The three numbers

`make update-set-score EVIDENCE=<folder>` (`experiments/scripts/score_update_set.py`) reads only the saved files,
never Redis. It uses three sets:
- **Present before (P):** answers that were in Tier 1 or Tier 2 in the first snapshot.
- **Dependents (D):** answers in P whose sources include an edited chunk.
- **Gone (G):** answers in P that are in neither tier in the second snapshot.

From them:

| Number | Formula | Target |
| :--- | :--- | :--- |
| **Completeness** | dependents gone ÷ dependents, `|D ∩ G| / |D|` | must be 1 |
| **Exactness** | answers gone that had no edited source, `|G − D|` | must be 0 |
| **Precision** | among dependents gone, the share whose sources include a `substantive` chunk | reported, no target |

**Three choices keep the numbers honest:**
- **The sources come from the evaluation log, never from `dep:*`.** If a registration never happened, `dep:*`
  would not list the answer, and a score read from it would never see the miss. The log records what each
  answer was really built on.
- **An answer that was never stored is not in P.** A discarded write-back cannot make the purge look better
  than it was.
- **The snapshots scan every `t1:*` key**, so a Tier-1 copy that the purge missed is found.

The scorer also checks ten conditions. Among them: every edit got a reply with nothing failed, every edit had
at least one dependent, some stored answers depend on no edited chunk (otherwise exactness proves nothing),
and no re-asked question hit a dependent. It exits 1 if any check fails. Two runs on one folder print the
same bytes.

## 5. The limit: precision is judged per edit, not per entry

A dependent of a `substantive` edit counts as **needed**, even when its own answer does not use the fact that
changed. For example, if the edited chunk also stated a packaging rule, an answer about packaging built on it
still counts as needed, although it is still correct. An answer under both a `substantive` and a `cosmetic`
edit also counts as needed.

So, if the labels are right, **the reported precision is an upper bound**: the true share of purges that were
needed can only be lower. Judging each answer on its own would need a label per answer, not per edit, and the
plan does not yet say whether item 6.5 does that.

## 6. What the runs showed (not citable)

Three runs on 29 Oct 2026 (`docs/work/2026-10-29-update-set/evidence/`, `MUTATION=on`, default arms):

| Run | Completeness | Exactness | Precision | Time |
| :--- | :--- | ---: | ---: | ---: |
| `live1` | 1.0 (57 of 57) | 0 | 0.684 | 476 s |
| `live2` | 1.0 (57 of 57) | 0 | 0.702 | 383 s |
| `live3` | 1.0 (59 of 59) | 0 | 0.695 | 521 s |

**In `live3`:** 69 answers were stored, 59 depended on an edited chunk, and all 59 were gone afterwards. 41 of
them depended on a `substantive` edit, so precision is 41 / 59 = 0.695. In other words, about 3 purges in 10
removed an answer that a `cosmetic` edit alone had touched. Every check passed, and the race was forced and
discarded.

**Per edit**, the number of dependents ranged from 2 to 11. The per-edit counts add up to 97, more than 59,
because one answer can use several edited chunks.

## 7. In Phase 6 (item 6.5)

RQ3 reuses this set at `mutation: on`, with the Phase 6 harness and judged labels, on the held-out split.
Completeness and precision are reported again, split into `substantive` and `cosmetic` edits, and they replace
the functional numbers above. Completeness below 1 stops the item as a defect. `Invalidation.md` §12 has the
full RQ3 plan.

## 8. Commands

| Command | What it does |
| :--- | :--- |
| `make update-set-verify` | checks `data/update-set-v1.json` offline: counts, before and after texts, the 30 → 14 day edit, the hash |
| `make update-set-probe OUT=<file>` | which chunks each validation question retrieves (IDs only; loads the embedding model) |
| `make update-set-check EVIDENCE=<new folder>` | the live run of §3 (loads both models; not a measurement) |
| `make update-set-score EVIDENCE=<folder>` | the three numbers of §4, from the saved files |
| `make cache-reset` | clears `t1:`, `t2:`, `lru:`, `dep:` and `entry:` keys, never with `FLUSHDB`; refuses while a gateway runs |

**Further reading:** `docs/data-card.md` §5 (the file); the trail `docs/work/2026-10-29-update-set/` (design and
deliverables); `docs/super-plan.md` Phase 4 and item 6.5.
