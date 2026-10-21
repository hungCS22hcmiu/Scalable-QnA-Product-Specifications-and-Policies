# Model-layer batches — item 3.4

One line per imported rows file, written by `make workload-import` (impact F10, spec W8). Hashes and
counts only: no question text and no asin. The rows themselves are in
`data/v1-draft/workload/model-layer.jsonl` (gitignored), each stamped with its batch (the first 16
characters of the file's sha256), the model id and the first 16 characters of `rules.md`'s sha256.

| Imported (UTC) | Rows file | sha256 (16) | Model | rules.md (16) | Accepted | Skipped | Rejected |
| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: |
