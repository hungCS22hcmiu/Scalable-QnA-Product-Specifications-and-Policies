# Golden node digests — item 3.6, plan steps 2 and 4

Written by `tools/golden_nodes.py --record` with the **old** `rag/src/rag/ingest.py`
(git blob `95c92ce6555ecc9708bd4b931f07297b0d591f12`), before the refactor. After the move into `records_to_nodes`,
`tools/golden_nodes.py --check` must give the same two digests.

The digest is a sha256 over a dump of every node `ingest.main` builds: class, id, text in
three metadata modes, metadata in order, both excluded-key lists, start and end index,
`ref_doc_id`, relationships, node hash and the template fields. v1 is the 152 drafts and
the 12 policy documents. No text is kept, only the digests.

**Finding while taking it.** The splitter links each chunk to its neighbours by a random
UUID; `ingest` renames the chunk afterwards and leaves those links alone, so PREVIOUS and
NEXT hold stale random ids that change on every run (513 of the 539 v1 nodes; none in
dev-v0, where every document is one chunk). They reach Redis inside `_node_content`.
Harmless for retrieval, but nothing may ever hash `_node_content` or the whole hash:
the index check hashes `chunk_id` and `text` only. The dump above replaces each UUID by a
label in order of first appearance, so the chain structure is kept and the randomness is not.

| dataset | nodes | digest |
| :--- | ---: | :--- |
| dev-v0 | 44 | 3ba50b71799c6c6089a90df89f5917b7b2d1ae051bbe62dd3b44a65865c1b321 |
| v1 | 539 | b2959feb769b795c3176ba791398f239b8ea50995d450c3e062c498e55fb3c37 |
