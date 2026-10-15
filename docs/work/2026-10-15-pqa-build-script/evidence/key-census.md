# Key census of the real PQA bytes (plan step 1)

**Taken:** 2026-10-15, first 200 lines of each of the six leaf files in `data/raw/pqa/`, by a throwaway
script outside the repo. **Key names, value types and counts only. No PQA text is recorded here.**

## Result

- All six leaves carry **exactly 14 keys**, equal to `REAL_FIELDS` in `design.md` §3. (This note first
  said 15: a miscount of mine, caught by the test `test_the_real_field_set_is_the_fourteen_keys_in_the_bytes`
  on 2026-10-15. The tables below always showed 14.) No key outside the
  list, no readme name (`asin_id`, `bullet_points`, `is_yes-no_question`, `yes-no_answer`) in any line.
- Every value is a `str`, except `answers`, which is a `list`.
- Every entry of `answers` is an object with one key, `answer_text`, a `str` (all 3,046 entries over the
  1,200 lines sampled). The entry shape the interim relies on holds.
- 0 lines failed to parse as a JSON object in the 1,200 sampled.
- Fields that are empty in some records, as the data card said: `brand_name`, `bullet_point4/5`
  (TVs), `product_description`. In no leaf was any field empty in **all** 200 sampled lines.

## Non-empty counts per leaf (of 200 lines)

| field | phones | laptops | TVs | headphones | chairs | desks |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `asin`, `question_id`, `question_text`, `question_type`, `answer_aggregated`, `answers`, `item_name` | 200 | 200 | 200 | 200 | 200 | 200 |
| `brand_name` | 117 | 101 | 184 | 180 | 132 | 85 |
| `bullet_point1` | 200 | 200 | 184 | 199 | 194 | 200 |
| `bullet_point2` | 194 | 200 | 184 | 199 | 192 | 199 |
| `bullet_point3` | 194 | 200 | 184 | 199 | 186 | 199 |
| `bullet_point4` | 194 | 200 | 109 | 198 | 185 | 197 |
| `bullet_point5` | 190 | 200 | 105 | 198 | 181 | 193 |
| `product_description` | 103 | 104 | 81 | 19 | 50 | 109 |

## What this settles and what it does not

- Settles design §7.1 (the real field set matches) for the sampled lines.
- Does **not** settle design §7.2 (a field empty in a whole leaf) or the existence of a rare extra key
  further down a file. A key that first appears after line 200 would be caught by Stop 2(b), and the
  pinned counts by Stop 3, on the first real build.
