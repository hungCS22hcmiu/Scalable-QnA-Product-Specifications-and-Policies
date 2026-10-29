"""One source edit: new text and vector, then the epoch, then the gateway's purge (item 4.4).

    python -m rag.edit --update-set FILE --edit-id ID --gateway URL

The ORDER is the point, and it is fixed in `apply` and nowhere else (interfaces.md E, order rule 2):

    embed   no side effect; the vector of the new text, embedded the way ingest embeds
    write   `text` and `vector` of corpus::{chunk_id}, in one HSET
    advance the dataset epoch, N to N+1
    post    POST /invalidate on the gateway, which replies after the purge has finished

A wrong order is silent. Advance before write: a retrieval between the two reads the OLD text under
the NEW epoch, and the write-back guard lets it through. Post before advance: a generation that
started after the purge still carries the old epoch and writes back. Write only `text`, not
`vector`: answers are built on the new text but ranked by the old meaning, with no error (design.md,
failure mode 1).

This file sits beside ingest.py, which also writes the corpus and advances the epoch. It does NOT
touch data/v1/: an edit changes Redis only. `DATASET_VERSION=v1 make ingest` puts the corpus back.
"""

import argparse
import json
import struct
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import redis

from rag import config, epoch, store
from rag.embedding import OllamaEmbedding

CHANGE_TYPES = ("substantive", "cosmetic")
POST_TIMEOUT_S = 30.0


class EditError(Exception):
    """An edit step failed. The message names the chunk."""


@dataclass(frozen=True)
class Edit:
    edit_id: str
    doc_id: str
    chunk_id: str
    change_type: str
    before: str
    after: str


@dataclass(frozen=True)
class Applied:
    chunk_id: str
    old_text: str
    old_vector: bytes
    epoch: int
    reply: dict


# write(chunk_id, text, vector, allowed) -> (old_text, old_vector).
# `allowed` is the tuple of texts the chunk may hold now; None means "any text, but the key must
# exist".
Write = Callable[[str, str, bytes, tuple[str, ...] | None], tuple[str, bytes]]
Advance = Callable[[], int]
Post = Callable[[dict], dict]
Embed = Callable[[str], bytes]


def load_edit(path: Path, edit_id: str) -> Edit:
    """The row `edit_id` of the update-set file (data-card.md section 5: a JSON array of rows)."""
    try:
        rows = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise EditError(f"{path}: cannot be read as JSON ({e})") from e
    if not isinstance(rows, list):
        raise EditError(f"{path}: expected a JSON array of edits")
    matches = [r for r in rows if isinstance(r, dict) and r.get("edit_id") == edit_id]
    if len(matches) != 1:
        raise EditError(f"{path}: {len(matches)} rows with edit_id {edit_id!r}, want exactly 1")
    row = matches[0]
    try:
        edit = Edit(
            edit_id=row["edit_id"],
            doc_id=row["doc_id"],
            chunk_id=row["chunk_id"],
            change_type=row["change_type"],
            before=row["before"],
            after=row["after"],
        )
    except KeyError as e:
        raise EditError(f"{path}: edit {edit_id!r} has no field {e.args[0]!r}") from e
    if edit.change_type not in CHANGE_TYPES:
        raise EditError(
            f"edit {edit_id!r}: change_type {edit.change_type!r} is not one of {CHANGE_TYPES}"
        )
    return edit


def embed_document(text: str) -> bytes:
    """The float32 bytes of `text` embedded as a DOCUMENT.

    OllamaEmbedding._get_text_embedding adds the "search_document: " prefix itself, and it is the
    function ingest embeds chunks through. Calling it, and adding no prefix here, is what keeps an
    edited chunk in the same place in vector space as an ingested one. Without the prefix the edited
    chunk drifts and is seldom retrieved, with no error (design.md, failure mode 2).
    """
    vec = OllamaEmbedding()._get_text_embedding(text)
    if len(vec) != config.EMBEDDING_DIM:
        raise EditError(f"the embedding has {len(vec)} dimensions, want {config.EMBEDDING_DIM}")
    return struct.pack(f"<{len(vec)}f", *vec)


def corpus_key(chunk_id: str) -> str:
    # Double colon: LlamaIndex appends its own separator to the configured prefix (store.py).
    return f"{config.CORPUS_KEY_PREFIX}:{chunk_id}"


def _text(raw: bytes | str | None) -> str:
    return raw.decode() if isinstance(raw, bytes) else (raw or "")


def redis_writer(client: redis.Redis) -> Write:
    """`write` over a redis client. It refuses a missing key, and a text the chunk should not hold.

    A re-run is allowed (the chunk holds `after` already) and a foreign change is not (it holds
    neither `before` nor `after`): the tool then touches nothing, and says so.
    """

    def write(
        chunk_id: str, text: str, vector: bytes, allowed: tuple[str, ...] | None
    ) -> tuple[str, bytes]:
        key = corpus_key(chunk_id)
        old_raw, old_vector = client.hmget(key, ["text", "vector"])
        if old_raw is None or old_vector is None:
            raise EditError(f"chunk {chunk_id}: {key} is missing or has no text or vector")
        old_text = _text(old_raw)
        if allowed is not None and old_text not in allowed:
            raise EditError(
                f"chunk {chunk_id}: the stored text is neither the edit's before nor its after; "
                "something else changed it, and nothing was written"
            )
        client.hset(key, mapping={"text": text, "vector": vector})
        return old_text, old_vector

    return write


def make_post(
    gateway_url: str,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = POST_TIMEOUT_S,
) -> Post:
    """`post` over httpx. Any failure to get a 200 raises EditError naming the chunk."""
    url = gateway_url.rstrip("/") + "/invalidate"

    def post(event: dict) -> dict:
        chunk_id = event["chunk_id"]
        try:
            # trust_env=False: a proxy set in the shell must not stand between us and 127.0.0.1.
            with httpx.Client(transport=transport, timeout=timeout, trust_env=False) as client:
                resp = client.post(url, json=event)
        except httpx.HTTPError as e:
            raise EditError(f"chunk {chunk_id}: POST {url} failed: {e!r}") from e
        try:
            body = resp.json()
        except ValueError:
            body = {"body": resp.text[:200]}
        if resp.status_code != 200:
            detail = json.dumps(body)[:400]
            raise EditError(f"chunk {chunk_id}: POST {url} returned {resp.status_code}: {detail}")
        if not isinstance(body, dict):
            raise EditError(
                f"chunk {chunk_id}: POST {url} returned 200 with a body that is not an object"
            )
        return body

    return post


def _event(chunk_id: str, change_type: str, new_text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": chunk_id.split("#", 1)[0],
        "change_type": change_type,
        "new_text": new_text,
        "dataset_version": config.DATASET_VERSION,
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def apply(
    edit: Edit,
    *,
    write: Write,
    advance: Advance,
    post: Post,
    embed: Embed = embed_document,
    vector: bytes | None = None,
) -> Applied:
    """Run one edit: embed, write, advance, post. The order is fixed here and tested.

    `vector`, when given, skips the embed: the epoch race computes it before its question is sent,
    so the embed does not eat the timing window.
    """
    new_vector = vector if vector is not None else embed(edit.after)
    old_text, old_vector = write(edit.chunk_id, edit.after, new_vector, (edit.before, edit.after))
    new_epoch = advance()
    reply = post(_event(edit.chunk_id, edit.change_type, edit.after))
    return Applied(edit.chunk_id, old_text, old_vector, new_epoch, reply)


def restore(
    chunk_id: str,
    text: str,
    vector: bytes,
    change_type: str,
    *,
    write: Write,
    advance: Advance,
    post: Post,
) -> dict:
    """Put saved bytes back through the same three steps, so the gateway purges what the edit left.

    The chunk may hold any text now (the saved bytes are the authority), but its key must exist.
    """
    write(chunk_id, text, vector, None)
    advance()
    return post(_event(chunk_id, change_type, text))


def _real_ops(gateway_url: str) -> tuple[Write, Advance, Post, Embed]:
    return (
        redis_writer(store.get_redis_client()),
        epoch.advance,
        make_post(gateway_url),
        embed_document,
    )


def main(
    argv: list[str] | None = None,
    *,
    make_ops: Callable[[str], tuple[Write, Advance, Post, Embed]] = _real_ops,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m rag.edit", description=__doc__.split("\n")[0])
    parser.add_argument("--update-set", required=True, type=Path, help="the update-set JSON file")
    parser.add_argument("--edit-id", required=True)
    parser.add_argument(
        "--gateway", required=True, help="the gateway's base URL, e.g. http://127.0.0.1:18081"
    )
    args = parser.parse_args(argv)

    # Before anything is written: an edit with no usable epoch file must change nothing.
    try:
        epoch_path = epoch.require_path()
        edit = load_edit(args.update_set, args.edit_id)
    except (EditError, epoch.EpochError) as e:
        print(f"edit FAILED: {e}", file=sys.stderr)
        return 1

    try:
        write, advance, post, embed = make_ops(args.gateway)
        applied = apply(edit, write=write, advance=advance, post=post, embed=embed)
    except EditError as e:  # the message names the chunk
        print(f"edit FAILED: {e}", file=sys.stderr)
        return 1
    except (epoch.EpochError, redis.RedisError, httpx.HTTPError) as e:
        print(f"edit FAILED: chunk {edit.chunk_id}: {e!r}", file=sys.stderr)
        return 1

    print(f"edit={edit.edit_id} chunk={applied.chunk_id} change_type={edit.change_type}")
    print(f"epoch_file={epoch_path} epoch={applied.epoch}")
    print(f"reply={json.dumps(applied.reply, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
