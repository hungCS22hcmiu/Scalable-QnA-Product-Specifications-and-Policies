# Approvals — pqa-build-script (item 3.1)

Nothing reads this file automatically. It is the human record of what was reviewed. **The three `/approve`
rows were ticked by the author's own `/approve` commands on 2026-10-15** (impact, design, implementation); I never ticked one.

| Phase          | Required    | Approved | When | ADR |
| :---           | :---        | :---     | :--- | :--- |
| impact         | L, M        | yes      | 2026-10-15 | none needed |
| contract       | if §B/§D    | not required: no contract, proto or wire change (`impact.md`) | | |
| experiment     | if measured | not required: builds the corpus, changes no measured path (`impact.md`) | | |
| design         | L           | yes      | 2026-10-15 | none needed |
| design-review  | L           | done by the `design-reviewer` subagent, 2026-10-15, verdict "sound with changes", all merged (`review.md`) | | |
| implementation | always      | yes      | 2026-10-15 | none needed |

## Decisions taken so far

- **2026-10-15 — branch.** The author said working on `main` is fine. No feature branch.
- **2026-10-15 — scope L.** The script is in `experiments/` and defines the corpus that every
  measurement reads. Between M and L, the larger.
- **2026-10-15 — changes I made on my own after the reviews** (all inside the spec's purpose; undo any
  you dislike): the stricter Stop 2(b) and Stop 3 output pins; `--check` replaced by `--verify`; no
  Python network code (`make pqa-fetch` uses `curl`); answers kept in the interim (this reverses my first draft);
  `line_no` per question; manifest renamed last; A6 uses two hash seeds.

## Open questions — resolved by the author, 2026-10-15

The author agreed to every proposal, and chose option A for question 4. This was a decision, not a phase
approval; the `/approve` commands came afterwards.

1. Manifest path: `data/pqa-manifest.json`. **Yes.**
2. Keep the answer strings in the interim. **Yes.**
3. Lone surrogate: replace with U+FFFD and count. **Yes.**
4. The 175 stale files and `product-*.json`: **option A.** 3.2 writes to a fresh `data/v1-draft/products/`
   and refuses to run while `data/v1-draft/product-*.json` exist. 3.1 deletes nothing.
5. Download: `curl -C -` in a Make target. **Yes.**
6. 3.2 owns the interim schema. **Yes.**
7. Narrow `make demo-reset` to restore `data/dev-v0/` only. **Yes** (plan step 11; one line, outside 3.1's files).

## What this change invalidates

Nothing. No run on `v1` exists (`experiments/results/` holds only `.gitkeep`), `dev-v0` is untouched,
and no frozen value changes (`impact.md`). **Indirect, binds at the freeze (3.6):** the skip rules,
"first parsed record wins" and surrogate replacement shape the question pool that `K` and
`cache_capacity = round(0.25 × K)` come from. After 3.6, a change to any of them needs a new
`dataset_version`. If implementation finds anything else (for example a glob that reads
`data/v1-draft/`), the finding goes here before the code does.

## Pins

Stop 3's pins come from `docs/work/2026-10-03-pqa-category-choice/probe_results.json`. Any later change to a pin or to
`IGNORED_KEYS` is recorded here, with the reason and who agreed.

*(none: the real run passed on its first attempt, with no pin edited and `IGNORED_KEYS` empty)*
