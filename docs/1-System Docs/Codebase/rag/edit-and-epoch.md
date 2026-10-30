# `rag/src/rag/` — the edit tool and the dataset epoch

**Describes:** commit `29b24a6` (30 Oct 2026); last changed in `68d732e` (item 4.4). **Files:** `edit.py` (283 lines),
`epoch.py` (133). Governing contract: `interfaces.md` §E; decision ADR-008. **The system view** (why the order
matters, the race) is in [`Invalidation.md`](../../Cache_Invalidation/Invalidation.md) §8–§9.

## 1. Purpose

`epoch.py` owns the **dataset epoch**: one integer in a file outside Redis that every edit advances. `edit.py` applies
**one source edit** in the only safe order: embed, write, advance, post. Together they serve **C2**.

## 2. Boundaries

- `epoch.py` uses the standard library only.
- An edit changes **Redis only**; `data/v1/` is never written. `make ingest` puts the corpus back.
- The order of an edit's steps lives in **one** function (`apply`) and nowhere else.

## 3. `epoch.py`

**The file.** Its path comes from `DATASET_EPOCH_FILE` and must be **absolute** (the gateway and `rag.server` run
from different directories). It holds one decimal integer ≥ 1. `NOT_READ = 0` is never a real epoch.

- **`read()`** returns the epoch now, or `NOT_READ` on any failure. **It never raises**: the loud failure is at
  start-up. A 0 stamp makes the gateway discard the write-back (it fails closed).
- **`require_path()`** checks the variable is set, not empty, and absolute. The file may not exist yet.
- **`check()`**, the start-up check: absolute path, the file exists, and it holds an integer ≥ 1. `rag.server` runs it
  before binding.
- **`advance()`** adds 1 and returns the new value; a missing file becomes 1. It takes an exclusive `flock` on
  `<file>.lock`, writes the new value to a temp file in the same directory, `fsync`s it, and **renames** it over the
  old one, so a reader sees the old or the new value, never half of one. **A corrupt file raises**: resetting it to 1
  could make a stale stamp equal to the epoch again.
- **`main`**: `python -m rag.epoch advance` (also `make epoch-advance`) and `show`.

## 4. `edit.py`

**Types.** `Edit` is one row of the update set (`edit_id`, `doc_id`, `chunk_id`, `change_type`, `before`, `after`).
`Applied` records what was changed (the old text and vector, and the new epoch). `EditError` names the chunk.

**`load_edit(path, edit_id)`** reads one row from `data/update-set-v1.json`.

**`embed_document(text)`** embeds the new text **as a document** (`search_document: ` prefix), the way ingest does, and
returns float32 bytes.

**`redis_writer(client)`** gives the `write` step: one `HSET` of `text` **and** `vector` on `corpus::{chunk_id}`. It
**refuses a missing key**, and a stored text that is neither the edit's `before` nor its `after`. So re-running an edit
is allowed, but overwriting someone else's change is not.

**`make_post(gateway_url)`** gives the `post` step: `POST /invalidate` with the §E event (`_event`), 30 s timeout.
**Anything but a 200 raises `EditError`**, and the tool exits non-zero.

**`apply(edit, write, advance, post, embed)`** runs the four steps **in this order**:
1. embed (no side effect);
2. write the text and vector;
3. advance the epoch;
4. post to `/invalidate`, which replies after the purge.

Every other order fails silently: advance before write lets a retrieval read old text under the new epoch; post
before advance lets a generation that starts after the purge write back the old answer; writing the text without
the vector ranks answers by the old meaning. The steps are passed in as functions, so a test can record their order.

**`restore(...)`** puts saved bytes back through the **same** three steps (write, advance, post), so the gateway also
purges what the edit left behind. The live update-set check uses it after its run.

**`main`**: `python -m rag.edit --update-set FILE --edit-id ID --gateway URL`.

## 5. Callers and callees

- **`epoch.read`** is called by `server.py` and `retrieve.py` at the start of every call; **`advance`** by `ingest.py`
  and `edit.py`; **`check`** by `server.serve`.
- **`edit.apply` and `restore`** are called by `experiments/scripts/update_set_check.py`
  ([`invalidation-tools.md`](../experiments/invalidation-tools.md)).
- The gateway reads the same file through `deps.EpochFile` ([`deps.md`](../gateway/deps.md)).

## 6. Tests that pin it

| File | Guarantees |
| :--- | :--- |
| `test_epoch.py` (9 tests) | a missing file starts at 1; advance leaves no temp file; concurrent advances lose nothing; a corrupt file is refused; `read` returns `NOT_READ` on failure; `check` refuses bad files; `serve` refuses before binding |
| `test_edit_order.py` (4) | `apply` calls write, then advance, then post; a given vector skips the embed; `restore` uses the same order; the document prefix is used |
| `test_edit_failures.py` (6) | a transport error or a 500 exits non-zero naming the chunk; a re-run advances and posts again; a foreign text is refused before any side effect; a missing key and a relative epoch path are refused |

The deliverables of item 4.4 also record a **swapped-order mutant**: with two steps swapped, `test_edit_order.py`
fails.

## 7. Silent failures to watch

- **Any change to the order** inside `apply` (see §4). The test pins it; keep the order in that one function.
- **Two processes reading two epoch files** (for example a relative path, or a different `DATASET_EPOCH_FILE` for the
  gateway and `rag.server`). Both refuse a relative path, and both print the path and value at start: compare them.
- **A global epoch:** under `mutation: on`, every edit discards every write-back in flight, not only those over the
  edited chunk. Expected and counted.

## 8. Commit

`29b24a6`; last changed in `68d732e`.
