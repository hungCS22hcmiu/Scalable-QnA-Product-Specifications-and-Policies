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
| 2026-10-21T11:04:21+00:00 | `label-05.rows.jsonl` | `2f63c0b431da3a9a` | claude-opus-5-5 | `f4035be73a5637c2` | label 87, name 8, natural 9, policy 6 | 0 | 0 |
| 2026-10-21T11:05:30+00:00 | `label-06.rows.jsonl` | `5fc6cff958e6de6a` | claude-opus-5-5 | `f4035be73a5637c2` | label 58, name 8, natural 3, policy 5 | 0 | 0 |
| 2026-10-21T11:06:39+00:00 | `label-07.rows.jsonl` | `ecd5ae44f8b8ff9e` | claude-opus-5-5 | `f4035be73a5637c2` | label 58, name 8, natural 13, policy 4 | 0 | 0 |
| 2026-10-21T11:08:08+00:00 | `label-08.rows.jsonl` | `e78b627800810a47` | claude-opus-5-5 | `f4035be73a5637c2` | label 80, name 8, natural 13, policy 10 | 0 | 0 |
| 2026-10-21T11:09:38+00:00 | `label-09.rows.jsonl` | `50d0c232df27e481` | claude-opus-5-5 | `f4035be73a5637c2` | label 72, name 8, natural 9, policy 10 | 0 | 0 |
| 2026-10-21T11:11:21+00:00 | `label-10.rows.jsonl` | `d4eaf70adaba0125` | claude-opus-5-5 | `f4035be73a5637c2` | label 78, name 8, natural 16, policy 17 | 0 | 0 |
| 2026-10-21T15:07:19+00:00 | `label-11.rows.jsonl` | `97e14f1a0c857b35` | claude-opus-5-5 | `f4035be73a5637c2` | label 71, name 8, natural 13, policy 15 | 0 | 0 |
| 2026-10-21T15:08:42+00:00 | `label-12.rows.jsonl` | `153b89d1cd19e17c` | claude-opus-5-5 | `f4035be73a5637c2` | label 66, name 8, natural 13, policy 12 | 0 | 0 |
