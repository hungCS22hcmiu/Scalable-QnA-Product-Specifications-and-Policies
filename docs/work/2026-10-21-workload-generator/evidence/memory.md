# Memory pressure log — item 3.4

`sysctl kern.memorystatus_vm_pressure_level`: `0` green, `1` / `2` yellow or urgent (CLAUDE.md).
Nothing in this item is a timed measurement: the embedding of a text does not depend on pressure.
The rule here is plan step 4's: an Ollama step does not start in red, and every level is recorded.

| When | Step | Level | Model loaded | Note |
| :--- | :--- | :---: | :--- | :--- |
| 2026-10-21 16:58 | 1, access and memory | 2 | none | `ollama serve` (Ollama.app) running, no model called |
| 2026-10-21 17:10 | 4, pilot | 1 → 2 | nomic-embed-text | 38 synthetic texts; level 2 after the run, never red |
| 2026-10-22 | 11, embed | 2 → 2 | nomic-embed-text | 1,274 vectors in 25 s; swap 5.28 → 5.49 of 6.14 GB (free 867 → 659 MB); model stopped after; run with the author's word, not a measurement |
