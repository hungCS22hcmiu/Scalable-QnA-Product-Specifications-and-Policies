# The answerability rule against ePQA's labels (plan step 15, design §3.1)

**Run:** 2026-10-20, `make pqa-answerability`, on the rule committed in `ea63e5d` (16:13:43 +0700). ePQA
was fetched afterwards, at 2026-10-20T09:15:09Z = 16:15:09 +0700 (`epqa-fetch.log`), at commit
`cec976cc…`. Counts: `answerability.json`. Memory pressure level 1; no model loaded. **Descriptive
only, as pre-registered: nothing here decides anything.**

## What it found

- **The join reproduces the probe:** 194 matched PQA lines, 143 / 5 / 21 / 19 / 2 / 4 per leaf, equal to
  the pin. They form **188 units** (distinct asin + text): **143 spec**, 40 carrier (dropped, all phones),
  5 policy.
- **ePQA calls few of them answerable from the record's kind of text.** Primary label (label 2 from a
  `bullet` or `description` candidate): **12 of 143 (8.4 %)**. Secondary (attributes too): 32. Tertiary
  (a label-2 bullet or description candidate that is really in our record): 7.
- **R2 tags 19 of 143 answerable (13.3 %).** Against the primary label:

  | Rule | Tagged | Agreement | κ | Precision | Recall |
  | :--- | ---: | ---: | ---: | :--- | :--- |
  | R2 | 19 | 0.839 | 0.17 | 4 / 19 = 21 % [8.5, 43.3] | 4 / 12 = 33 % [13.8, 60.9] |
  | R1 | 25 | 0.825 | 0.24 | 6 / 25 = 24 % [11.5, 43.4] | 6 / 12 = 50 % [25.4, 74.6] |

  Against the tertiary label, R2's precision is 3 / 19 (16 %) and its recall 3 / 7. Intervals are 95 %
  Wilson, pooled over the six leaves.
- **Almost all of it is phones:** 93 of the 143 spec units. Chairs 2, desks 4, laptops 5: the check
  says nothing about furniture or laptops, as design §8.2 said it would.

## Reading

1. **Agreement is high only because most questions are negatives both ways.** κ of 0.17 (R2) and 0.24
   (R1) is slight agreement. Most of R2's "answerable" tags are not what ePQA's annotators found
   answered by a bullet or the description.
2. **R2 is not more precise than R1 here.** R2 was chosen before any data to stop product-noun matches
   (review H1). On these 143 phone-heavy questions it removes 6 tags and its precision does not rise.
   n is small (19 and 25 tagged), and the intervals overlap almost completely.
3. **Two explanations, which this check cannot separate:** "presence is not an answer" (design §2.1:
   the record mentions the word but does not answer), or ePQA's own limitation (review M7: its labels
   are on its own candidate snippets, so "no label 2" can mean "no snippet answered"). The tertiary
   label was meant to narrow this, and it has only 7 positives.
4. **What the pre-registration says happens now:** nothing automatic. The **blind audit of the selected
   pool** (design §3.2) is the check on the population the study uses, and the only one that sees
   furniture. If the author wants a different rule, it is written down first, labelled **in-sample**
   with respect to these 143 questions, and judged on a fresh audit sample, never on these labels.
