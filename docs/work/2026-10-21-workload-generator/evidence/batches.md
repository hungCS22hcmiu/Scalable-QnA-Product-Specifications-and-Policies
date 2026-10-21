# Model-layer batches — item 3.4

One line per imported rows file, written by `make workload-import` (impact F10, spec W8). Hashes and
counts only: no question text and no asin. The rows themselves are in
`data/v1-draft/workload/model-layer.jsonl` (gitignored), each stamped with its batch (the first 16
characters of the file's sha256), the model id and the first 16 characters of `rules.md`'s sha256.

| Imported (UTC) | Rows file | sha256 (16) | Model | rules.md (16) | Accepted | Skipped | Rejected |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: |
| 2026-10-21T10:57:49+00:00 | `label-01.rows.jsonl` | `e9559c943704cfb1` | claude-opus-5-5 | `f4035be73a5637c2` | label 63, name 8, natural 10, policy 10 | 0 | 0 |
| 2026-10-21T10:59:18+00:00 | `label-02.rows.jsonl` | `502bca9dfad2bb8e` | claude-opus-5-5 | `f4035be73a5637c2` | label 63, name 8, natural 9, policy 7 | 0 | 0 |
| 2026-10-21T11:01:21+00:00 | `label-03.rows.jsonl` | `08adb4ce168401fe` | claude-opus-5-5 | `f4035be73a5637c2` | label 74, name 8, natural 2, policy 9 | 0 | 0 |
| 2026-10-21T11:02:40+00:00 | `label-04.rows.jsonl` | `2ff391c286516db9` | claude-opus-5-5 | `f4035be73a5637c2` | label 67, name 8, natural 12, policy 2 | 0 | 0 |
