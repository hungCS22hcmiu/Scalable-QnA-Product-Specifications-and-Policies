---
description: Open a task that changes structure but not behaviour — defaults to scope M
argument-hint: <slug> [what is being restructured]
---

Open a **refactor** task: same behaviour, better structure. Run `/task $1 M $2`.

**The defining constraint: behaviour does not change.** State up front how that will be
demonstrated, not asserted — normally that the existing tests pass untouched, and for anything on
a measured path that a pinned golden value reproduces exactly. This repo already has the habit:
the four decisive similarities `0.4237 / 0.9244 / 0.9382 / 0.9578` were re-run after every
restructuring of the cascade, and they are the reason those changes are trustworthy.

- **No test may be modified.** A refactor that needs a test changed is not a refactor.
- Touching `reuse/` → **L**, even for a pure move. The golden values are the only thing standing
  between a restructuring and a silently different rule.
- **A refactor is never bundled with a fix or a feature.** If you find a bug mid-refactor, stop,
  record it, finish or abandon the refactor, then `/bugfix` it. Bundled, neither change can be
  reviewed and the golden values no longer prove anything.
