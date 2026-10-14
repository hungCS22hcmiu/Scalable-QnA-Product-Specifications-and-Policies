# Sample questions — plan step 1a (frozen before any answer is generated)

Source of facts: the dev-v0 chunks quoted verbatim in
`docs/work/2026-10-10-support-gate-lexical-arm/design.md`, "The pinned fixture" (products
`headphones-01`, `-02`, `-03`, `-04`, `-09`; `policy-returns-electronics`; `policy-warranty`), and the
five question/paraphrase pairs in `experiments/k6/mu_hit.js` (the smoke fallback, lines 71-87).
`data/` was not read. The shipping policy and the UltraBook Pro 14 are named only by the `mu_hit.js`
pairs; nothing here assumes their content.

**This file is frozen when its sha256 is recorded in `approvals.md`. It may not be edited after the
first answer is generated.** A question is never replaced because of what its answer scored.
`product_id` is sent with the question as a gateway request would send it; "none" means omitted.
`yn` marks a yes/no question, which is reported apart.

dev-v0 is the development corpus. Nothing here is a citable result.

## Part (a) — floor: 16 answers, each scored against its own retrieval

| id | question | product_id | lane (expected) | yn |
| :-- | :--- | :--- | :--- | :-: |
| a01 | What is the battery life of the EarBuds Pop 3? | product-headphones-03 | SPEC | |
| a02 | How much does the SoundMax ANC Pro weigh? | product-headphones-01 | SPEC | |
| a03 | Does the SoundMax ANC Lite have active noise cancelling? | product-headphones-02 | SPEC | yn |
| a04 | Which Bluetooth version does the EarBuds Pop 3 Pro use? | product-headphones-04 | SPEC | |
| a05 | Is the EarBuds Pop 3 Pro water resistant? | product-headphones-04 | SPEC | yn |
| a06 | How long does the Conference Buds battery last with the charging case? | product-headphones-09 | SPEC | |
| a07 | How long do I have to return a laptop for a full refund? | none | POLICY | |
| a08 | Who pays for return shipping if I change my mind? | none | POLICY | |
| a09 | How long is the warranty on headphones? | none | POLICY | |
| a10 | How long is the warranty on laptops, and what does it not cover? | none | POLICY | |
| a11 | What does the shipping policy say? | none | POLICY | |
| a12 | Can I return the EarBuds Pop 3 after 30 days? | product-headphones-03 | MIXED | yn |
| a13 | Does the warranty on the EarBuds Pop 3 cover battery defects? | product-headphones-03 | MIXED | yn |
| a14 | How much RAM does the UltraBook Pro 14 have? | none | SPEC | |
| a15 | what is the battery life of the EarBuds Pop 3 | product-headphones-03 | SPEC | |
| a16 | Which of the two warranty lengths applies to a pair of headphones? | none | POLICY | |

The lane column is what the question is written to ask. It is **not** asserted: the lane the system
really assigns is recorded in the result.

## Part (b) — reuse case: 5 pairs; the answer to `q` is scored against the retrieval of `p`

The five pairs of `mu_hit.js`, in its order, with no `product_id`. Each row is scored two ways: the
answer to `q` against its own retrieval (a floor), and against the retrieval of `p` (the reuse case).

| id | q (answered) | p (paraphrase; retrieval only) |
| :-- | :--- | :--- |
| b1 | what is the battery life of the EarBuds Pop 3 | what is the battery life of the EarBuds Pop 3 headphones |
| b2 | how long do I have to return an item | how long do I have to return a purchase |
| b3 | what does the shipping policy say | what does the shipping policy state |
| b4 | how much RAM does the UltraBook Pro 14 have | how much memory does the UltraBook Pro 14 have |
| b5 | Am I entitled to a full refund on my headphones 30 days after delivery? | Is a full refund possible for my headphones 30 days after delivery? |

## Part (c) — negative pairs: the answer to `q` is scored against the retrieval of `p`, whose correct answer differs

Same-evidence pairs share a namespace, so configuration 4 offers the candidate to the gate. A pair
with the same evidence chunk **cannot** be separated by this gate: the gate checks that the cached
answer is supported by the fresh evidence, and it is. That is the residual the claim carries (it is
a count here, not a defect). The "gate alone" pairs cross products, so the namespace would stop
them before the gate in configuration 4; they test the arms alone.

| id | kind | q (answered) | product_id of q | p (retrieval only) | product_id of p |
| :-- | :--- | :--- | :--- | :--- | :--- |
| c1 | same namespace | What is the battery life of the EarBuds Pop 3? | product-headphones-03 | How much does the EarBuds Pop 3 weigh? | product-headphones-03 |
| c2 | same namespace, yn | Does the EarBuds Pop 3 Pro have active noise cancelling? | product-headphones-04 | Is the EarBuds Pop 3 Pro water resistant? | product-headphones-04 |
| c3 | gate alone | What is the battery life of the SoundMax ANC Pro? | product-headphones-01 | What is the battery life of the SoundMax ANC Lite? | product-headphones-02 |
| c4 | same namespace | How long is the warranty on headphones? | none | How long is the warranty on laptops? | none |
| c5 | same namespace | How long do I have to return a laptop for a full refund? | none | Who pays for return shipping if I change my mind? | none |
| c6 | gate alone, yn | Does the EarBuds Pop 3 have active noise cancelling? | product-headphones-03 | Does the EarBuds Pop 3 Pro have active noise cancelling? | product-headphones-04 |

## What is reported (fixed now)

For every row: the lane and namespace the system assigned; the retrieved chunk IDs; `S_lex`;
`ContentTokenCount`; the numeric verdict (`Numbers`, `Unsupported`, `Unreadable`, `Unitless`); and
whether each arm refuses. Summaries: the `S_lex` distribution of (a) and (b); how many are below
0.6; numeric refusals; numeric refusals the lexical arm admits; yes/no rows apart; for (c) the
refused and the admitted count, with the admitted same-evidence pairs named as the residual; and,
for any zero count, the 95 % Wilson upper bound. n is a go/no-go check, not an estimate.
**Nothing is tuned and no rule is edited because of these numbers.**
