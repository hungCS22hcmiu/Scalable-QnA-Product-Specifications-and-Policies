# The audit of the selected pool (plan step 17, design §3.2)

**⚠️ A model audit, not a human one.** The author did not have time to mark the 100 questions and asked
Claude (Opus 5.5) to mark them on 2026-10-20. That departs from the pre-registration ("the auditor is the
author, not a model: a model label would be a third rule, not a check"; `approvals.md`). Two limits follow,
and every use of these numbers must carry them:

- **The marker is not independent of the rule.** Claude wrote R2. The sheet hid the tags, and the marks
  were made row by row from the text alone, but knowing how R2 decides could bias a mark toward or against
  it without leaving a trace.
- **It is a model label.** The result may not be described as human-verified. It is a third rule beside R1
  and R2, applied by a stricter reader.

**The marking rule** (stated to the author before marking): *yes* only when `product_text` alone fully
answers the question, an explicit negative included (a made-up example: a spec line saying the screen has no
touch support answers "does it have a touchscreen?");
*no* for anything that needs outside knowledge (carriers or countries not named, whether a program runs),
for a partial or merely implied answer, and for opinion questions. Marks by item: `audit-marks.json`
(item numbers only, no text). Counts: `audit.json`.

## Result

22 of 100 marked *yes*. Against R2's tags:

| | Tagged answerable (60) | Tagged unanswerable (40) |
| :--- | ---: | ---: |
| Marked yes | 21 (tp) | 1 (fn) |
| Marked no | 39 (fp) | 39 (tn) |

- **Precision 21 / 60 = 35 %**, 95 % Wilson [24.2 %, 47.6 %]. By department (counts only, no intervals):
  laptops 8 / 15, furniture 7 / 15, phones 3 / 15, electronics 3 / 15.
- **Negative predictive value 39 / 40 = 97.5 %**, [87.1 %, 99.6 %].
- **Recall re-weighted** to the selected pool's tags (1,180 answerable, 3,399 unanswerable): about **83 %**.

## Reading

1. **R2 is a high-recall, low-precision filter.** When it says *unanswerable* it is almost always right;
   when it says *answerable* it is right about one time in three. This agrees with the ePQA check (precision
   4 / 19 = 21 %, `answerability.md`), from a different reader and a different population.
2. **The common false positive is "the word is there, the answer is not":** the record mentions Bluetooth,
   a carrier, a screen, Windows, and the question asks something about it that the text does not settle
   (design §2.1 named this bias before any run). Phones and electronics, where questions are about
   compatibility and use, are worst.
3. **What it means for the 1,180 "answerable" questions:** at 35 % precision, perhaps 410 of them
   (Wilson range roughly 285 – 560) are truly answerable from the record. Many selected products will
   then have fewer than the 5 truly answerable questions the `answerable` step asked for.
4. **What it does not change:** the probe pins, the draw and the outputs are what the pre-registered rule
   produced, and none of them is altered by this result. Whether R2 stands is the author's decision.
