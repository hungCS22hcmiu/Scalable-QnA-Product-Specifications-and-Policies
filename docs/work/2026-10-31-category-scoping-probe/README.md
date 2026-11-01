# Category scoping — does product-scoped retrieval bring in another category's policy?

Not a task trail: a change and a measurement made in chat on 2026-10-31, at the author's instruction, and recorded
by **ADR-020**.

- **What:** for each `v1` validation question with a `product_id`, the categories of the policy chunks in its
  scoped top 5, and the category of the rank-1 policy chunk. Rank-1 policy is the POLICY lane's namespace and the
  policy half of the MIXED namespace. Lanes are recomputed as the gateway does (MIXED off and on).
- **Before and after** the swap in `rag/src/rag/retrieve.py` (`_ensure_category_policies`). Both outputs are in
  `summary.txt`, with the three authored questions that do not name their category.
- **Conditions:** `v1` in Redis, embedding model only. Pressure 1 before both runs; 2 at the end of the second.
  **citable: no.**
- **Files:** `category_probe.py` (the probe) and `summary.txt` (its output, counts and document IDs only).
- **Re-run:** `python3 docs/work/2026-10-31-category-scoping-probe/category_probe.py`, from the repo root, with
  `v1` in Redis.
