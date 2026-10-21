# Pilot — where synthetic pairs fall against 0.85 (plan step 4, review U13)

**2026-10-21, 17:10.** 25 pairs, 38 distinct texts, all written for the pilot: the product names
(Zenvo X2, Orbis 14 Pro, Lumio 55 QLED, …) are invented, and **no PQA text is used**. Each text is
embedded through the frozen query path, `rag.embedding.OllamaEmbedding.get_query_embedding` (it adds
`search_query: `), with `nomic-embed-text` (digest `0a109f422b47`, 768 dimensions), and each pair
is compared with `corpus_gate.cosine` against `SIM_FLOOR = 0.85`. A second run gave the same table
to the last digit. Memory pressure: level 1 before, level 2 after, never red (`memory.md`). The
script stayed in the session scratchpad (sha256 `cf4abe37416f54c1…`); every pair is in the table.

| # | Kind | Expected | Query a | Query b | cosine | ≥ 0.85 |
| ---: | :--- | :--- | :--- | :--- | ---: | :---: |
| 1 | close paraphrase | A | How long does the Zenvo X2 battery last? | How long does the battery in the Zenvo X2 last? | 0.992 | yes |
| 2 | close paraphrase | A | Does the Orbis 14 Pro have a backlit keyboard? | Does the Orbis 14 Pro come with a backlit keyboard? | 0.991 | yes |
| 3 | close paraphrase | A | What is the screen resolution of the Lumio 55 QLED? | What screen resolution does the Lumio 55 QLED have? | 0.991 | yes |
| 4 | close paraphrase | A | Can the Halden task chair arms be adjusted? | Are the arms on the Halden task chair adjustable? | 0.966 | yes |
| 5 | close paraphrase | A | Do the Brava Q3 headphones fold flat? | Can the Brava Q3 headphones fold flat? | 0.994 | yes |
| 6 | far paraphrase | A or C | How long does the Zenvo X2 battery last? | On a single charge, how many hours will I get from the Zenvo X2? | 0.888 | yes |
| 7 | far paraphrase | A or C | Does the Orbis 14 Pro have a backlit keyboard? | Will the keys on the Orbis 14 Pro light up in the dark? | 0.823 | no |
| 8 | far paraphrase | A or C | What is the screen resolution of the Lumio 55 QLED? | Is the Lumio 55 QLED a 4K set or 1080p? | 0.817 | no |
| 9 | far paraphrase | A or C | Can the Halden task chair arms be adjusted? | Is it possible to raise or lower the armrests of the Halden task chair? | 0.888 | yes |
| 10 | far paraphrase | A or C | What is the maximum height of the Corvel standing desk? | How tall can the Corvel standing desk go? | 0.959 | yes |
| 11 | name-swap (B-cross) | trap | How long does the Zenvo X2 battery last? | How long does the Kestrel M5 battery last? | 0.668 | no |
| 12 | name-swap (B-cross) | trap | Does the Orbis 14 Pro have a backlit keyboard? | Does the Vantor 15 Air have a backlit keyboard? | 0.782 | no |
| 13 | name-swap (B-cross) | trap | Can the Halden task chair arms be adjusted? | Can the Marlow mesh chair arms be adjusted? | 0.788 | no |
| 14 | name-swap (B-cross) | trap | Do the Brava Q3 headphones fold flat? | Do the Solace H7 headphones fold flat? | 0.803 | no |
| 15 | spec lookalike (B-within) | trap | How long does the Zenvo X2 battery last? | How long does the Zenvo X2 battery take to charge? | 0.941 | yes |
| 16 | spec lookalike (B-within) | trap | What is the screen resolution of the Lumio 55 QLED? | What is the refresh rate of the Lumio 55 QLED? | 0.886 | yes |
| 17 | spec lookalike (B-within) | trap | What is the maximum height of the Corvel standing desk? | What is the maximum weight the Corvel standing desk can hold? | 0.932 | yes |
| 18 | policy-condition twin | trap | Is there a fee to return the Zenvo X2 after I open it? | Is there a fee to return the Zenvo X2 if it is still unopened? | 0.925 | yes |
| 19 | policy-condition twin | trap | How many days do I have to return the Halden task chair if I opened it? | How many days do I have to return the Halden task chair if it is unopened? | 0.948 | yes |
| 20 | condition-department twin | trap | How many days do I have to return a new laptop? | How many days do I have to return a renewed laptop? | 0.947 | yes |
| 21 | policy-kind twin | trap | How long is the return window for the Lumio 55 QLED? | How long is the warranty on the Lumio 55 QLED? | 0.886 | yes |
| 22 | policy-kind twin | trap | How long do I have to send back the Brava Q3 headphones? | How long are the Brava Q3 headphones covered by warranty? | 0.831 | no |
| 23 | policy-region twin | trap | Is the Zenvo X2 warranty valid in the United States? | Is the Zenvo X2 warranty valid if I bought it abroad? | 0.888 | yes |
| 24 | unrelated, same product | neither | Does the Zenvo X2 support wireless charging? | What colors does the Zenvo X2 come in? | 0.746 | no |
| 25 | unrelated, same product | neither | Does the Orbis 14 Pro have a backlit keyboard? | How much does the Orbis 14 Pro weigh? | 0.697 | no |

## What it shows

- **Close paraphrases are A.** All five at 0.966 – 0.994.
- **Far paraphrases split.** Three of five are at or above 0.85 (0.888, 0.888, 0.959), two fall
  just below (0.817, 0.823). So stratum C will not be empty, which was U2's worry, and A / C
  really is decided by measurement.
- **Name swaps (B-cross) fall below the floor.** All four at 0.668 – 0.803. Under this embedding
  a different product name moves a question a long way, so a B-cross probe can only be reached at
  the low end of the τ sweep (0.80). This answers U3 on synthetic text.
- **Same-product traps sit above it.** Spec lookalikes 0.886 – 0.941; condition twins 0.925 –
  0.948 (RQ2a's cases); the department-level laptops twin 0.947; the region twin 0.888; the kind
  twins 0.886 and 0.831, depending on the wording.
- **Unrelated questions on one product stay low.** 0.697 and 0.746: naming the product does not on
  its own lift two questions above 0.85 (U4, first view).

## Decision

**No constant in `design.md` §2.2 moves.** Each kind lands where its role needs it, or where the
result is something to report, not to fix:

- The traps RQ2a reads (condition twins) are well above the floor, so the minimal-pair groups and
  `TWIN_PRODUCTS_PER_CELL = 20` stay.
- B-cross below 0.85 is a finding about the embedding, not a reason to build more or fewer swaps.
  It is cheap (the script swaps the name), it measures what the namespace costs at low τ, and the
  similarity bins of §8 A1 will show where it falls. `SPEC_LOOKALIKES_PER_PRODUCT = 1` stays.
- The far paraphrase is what makes C exist, so `PARAPHRASES_PER_SEED = 2` (one close, one far)
  stays.

**The limit (U13).** Invented names are not words the model has seen. Real names with shared parts
("Galaxy A10e" against "Galaxy A20") may sit closer than these swaps, so step 11 measures the real
distribution and the build report gives the cosine per stratum and per `probe_kind`. This pilot was
the last point where a constant could move; from step 5 on they are fixed.
