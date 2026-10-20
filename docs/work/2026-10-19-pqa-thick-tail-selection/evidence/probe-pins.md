# The `adr002` pins, re-derived from a program output (plan step 3)

**Run:** 2026-10-20. `docs/work/2026-10-03-pqa-category-choice/scripts/example_product.py`, **unchanged**,
once per leaf on the pinned raw files in `data/raw/pqa/`, smallest leaf first. Only the line
`=== candidates qualifying: N` and the peak memory were read; the rest of the output (one product
record and its questions) was not kept. **Not a measurement:** no model was loaded.

Memory pressure was **level 2** throughout (42 % free before the first run, 34 – 38 % between runs).
That makes a measurement invalid, but this is a count over fixed bytes, and memory pressure cannot
change it.

| Leaf | Department | Candidates qualifying | ADR-002 | Peak RSS |
| :--- | :--- | ---: | ---: | ---: |
| `home_office_desks` | furniture | 339 | 339 | 411 MB |
| `chairs` | furniture | 796 | 796 | — (not timed) |
| `led_&_lcd_tvs` | electronics | 302 | 302 | 670 MB |
| `over-ear_headphones` | electronics | 399 | 399 | 822 MB |
| `traditional_laptops` | laptops | 1,312 | 1,312 | 1,279 MB |
| `unlocked_cell_phones` | phones | 1,811 | 1,811 | 2,242 MB |

**All six equal ADR-002's table.** The `adr002` pins of `design.md` §2.6 now rest on a program output,
not only on prose. No pin changes.

The first attempt at the chairs and TV runs used a shell loop with `set -- $leaf`. zsh does not
split an unquoted variable into words, so the script got one argument and failed before reading any
file (22 MB peak, no output). Both leaves were re-run one at a time. It was my mistake, not the data's.
