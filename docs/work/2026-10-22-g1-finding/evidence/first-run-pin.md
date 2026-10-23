# The first run, preserved and pinned — written 2026-10-23, before any code

Hashes and counts only. The files themselves are gitignored (`data/v1-draft/gate/first-run/`); they hold asin-bearing paths.

Run 1 of item 3.6 wrote its report to `data/v1-draft/gate/run1/`, which is also the default folder of the next run. To keep the
only copy of the 21-pair report from being overwritten (design review, finding 3), it was copied to `first-run/` on 2026-10-23.

| File | sha256 |
| :--- | :--- |
| `report.json` | `c1ad09eeb2b6ac8cd0cc9d07dbe5d022d473a0486bc27bb927c71c05fe2ff039` |
| `retrieval-validation.json` | `1e2e17357c456c296e0b01a9178013e0f3ff523cc23135fead3306910da7bc57` |
| `retrieval-test.json` | `7a90de70423cf89ec46ef041a7c640395324bec09e679631f5c6314a8c7ced5f` |

**Snapshot digest of the accepted files** (the 164 corpus files and the 3 workload files, 167 in all), computed with
`corpus_gate.snapshot_digest(freeze_files(data/v1, data/workload-v1.json))`:

`a5708fefa62cec0aef5505e9e5242bc04bf351fd02a2efb5da54a98f211bb2e4`

It begins with `a5708fefa62c`, the prefix the gate printed in run 1 as "it would have been". The allowance in the design is
pinned to this value: if any corpus or workload file changes, the allowance stops working and a new decision is needed.
