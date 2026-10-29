# Condition routing — does retrieval pick the right condition document?

Not a task trail: a measurement taken in chat on 2026-10-30, cited by `docs/1-System Docs/Tier 2.md` §12a.

- **What:** for questions grounded in a condition-split policy (opened / unopened, new / renewed, domestic /
  international), is the **rank-1 policy document** of the product-scoped retrieval the right one? That document
  is the POLICY lane's namespace, so it is what keeps an "opened" answer away from an "unopened" question.
- **Part 1:** the 134 `v1` validation questions grounded in such a policy, split by whether the condition word
  appears in the question.
- **Part 2:** 43 synonym rewrites of real validation questions ("still sealed" for unopened, "used" for opened,
  "factory-sealed" for new). They were authored for this probe and are not part of the frozen workload.
- **Conditions:** `v1` in Redis, memory pressure 2, embedding model only. **citable: no.**
- **Files:** `condition_routing_probe.py` (the probe) and `summary.txt` (its output, numbers and document IDs only).
- **Re-run:** `python3 docs/work/2026-10-30-condition-routing-probe/condition_routing_probe.py`, from the repo
  root, with `v1` in Redis.
