"""Item 4.4: completeness, exactness and precision of source-aware invalidation, from saved IDs.

    python3 experiments/scripts/score_update_set.py EVIDENCE_DIR      # writes EVIDENCE_DIR/score.json

Reads six files from `EVIDENCE_DIR/private/`. They hold `qa_id`s and chunk IDs, which can carry an ASIN,
so they are gitignored (the author's decision of 2026-10-29). It never reads Redis or a service. It
writes `score.json` to `EVIDENCE_DIR/` with sorted keys and no time stamp, so two runs on one folder
print the same bytes (done condition 9). `score.json` holds counts keyed by `edit_id`, entry IDs and
check names, and no chunk ID or `qa_id`: it is the one committed result. It exits 1 when any check
fails.

The words, as in design.md section 1:
  Present before (P)  entries named in oracle.json that have a `t1:` key or a `t2:` record in the
                      BEFORE snapshot. An entry that was never stored (a discarded write-back, a failed
                      embed) is not in P, so it cannot make the purge look better than it was.
  Dependents (D)      entries in P whose sources meet an edited chunk. The sources come from the
                      evaluation log's MISS records (oracle.json), never from `dep:*`: a registration
                      that never happened must not be able to hide itself.
  Gone (G)            entries in P with no `t1:` key and no `t2:` record in the AFTER snapshot.
  Completeness        |D and G| / |D|. Must be 1.
  Exactness           |G minus D|: entries that were present and are gone, with no edited source. Must be 0.
  Precision           the share of D and G whose sources meet a `substantive` chunk. Reported, no target.
                      An entry under both a substantive and a cosmetic edit counts as needed.

Input shapes (all JSON):
  oracle.json           [{qa_id, entry_id, entry_sources, outcome, writeback_discarded}]
  labels.json           [{edit_id, chunk_id, change_type}]
  snapshot-*.json       {entry_id: {t1_keys: [str], t2: bool, entry: bool}}
  replies.json          [{edit_id, chunk_id, ok, purged, failed, errors}]    ok: the edit tool exited 0
  reask.json            [{qa_id, outcome, entry_id}]                          the dependents' questions asked again
"""

import argparse
import json
import sys
from pathlib import Path

INPUTS = {
    "oracle": "oracle.json",
    "labels": "labels.json",
    "before": "snapshot-before.json",
    "after": "snapshot-after.json",
    "replies": "replies.json",
    "reask": "reask.json",
}
HIT_OUTCOMES = ("TIER1_HIT", "TIER2_HIT")
PRIVATE = "private"  # the subfolder of the evidence folder that holds the input files


def load(evidence: Path) -> dict:
    data = {}
    for name, filename in INPUTS.items():
        path = Path(evidence) / PRIVATE / filename
        try:
            data[name] = json.loads(path.read_text())
        except (OSError, ValueError) as e:
            raise SystemExit(f"score_update_set: cannot read {path}: {e}") from e
    return data


def present(snapshot: dict, entry_id: str) -> bool:
    """An entry is in the cache when either tier still holds it."""
    rec = snapshot.get(entry_id)
    return bool(rec and (rec.get("t1_keys") or rec.get("t2")))


def score(data: dict) -> dict:
    labels = data["labels"]
    edited = {row["chunk_id"]: row["change_type"] for row in labels}
    substantive = {c for c, t in edited.items() if t == "substantive"}

    entries: set[str] = set()
    sources: dict[str, set[str]] = {}
    for rec in data["oracle"]:
        entry_id = rec.get("entry_id") or ""
        if not entry_id:
            continue
        entries.add(entry_id)
        sources.setdefault(entry_id, set())
        if rec.get("outcome") == "MISS":
            sources[entry_id].update(rec.get("entry_sources") or [])

    before, after = data["before"], data["after"]
    p = {e for e in entries if present(before, e)}
    d = {e for e in p if sources[e] & edited.keys()}
    g = {e for e in p if not present(after, e)}
    dependents_gone = d & g
    non_dependents_gone = g - d
    needed = {e for e in dependents_gone if sources[e] & substantive}

    per_edit = []
    for row in sorted(labels, key=lambda r: r["edit_id"]):
        deps = {e for e in d if row["chunk_id"] in sources[e]}
        per_edit.append(
            {
                "edit_id": row["edit_id"],
                "change_type": row["change_type"],
                "dependents": len(deps),
                "dependents_gone": len(deps & g),
            }
        )

    replies = data["replies"]
    reply_entries = {
        e for r in replies for e in (r.get("purged") or []) + (r.get("failed") or [])
    }
    purged_anywhere = {e for r in replies for e in (r.get("purged") or [])}
    reply_by_edit = {r.get("edit_id") for r in replies}

    reask_hits = sorted(
        r["entry_id"]
        for r in data["reask"]
        if r.get("outcome") in HIT_OUTCOMES and r.get("entry_id") in d
    )

    checks = {
        "labels_name_distinct_chunks": len(edited) == len(labels),
        "every_edit_has_a_reply": reply_by_edit == {r["edit_id"] for r in labels},
        "every_reply_is_ok_and_nothing_failed": all(
            r.get("ok") is True and not r.get("failed") and not r.get("errors")
            for r in replies
        ),
        "reply_entries_are_in_the_oracle": reply_entries <= entries,
        "dependents_are_named_in_replies": d <= purged_anywhere,
        "every_edit_has_a_dependent": all(row["dependents"] > 0 for row in per_edit),
        "some_present_entries_depend_on_no_edited_chunk": len(p - d) > 0,
        "no_reask_hits_a_dependent": not reask_hits,
        "completeness_is_1": bool(d) and dependents_gone == d,
        "exactness_is_0": not non_dependents_gone,
    }
    failures = sorted(name for name, ok in checks.items() if not ok)

    return {
        "checks": checks,
        "completeness": len(dependents_gone) / len(d) if d else None,
        "counts": {
            "dependents": len(d),
            "dependents_gone": len(dependents_gone),
            "edits": len(labels),
            "entries_in_oracle": len(entries),
            "gone": len(g),
            "needed": len(needed),
            "present_before": len(p),
            "reask_hits_on_dependents": len(reask_hits),
        },
        "dependents_not_gone": sorted(d - g),
        "exactness": len(non_dependents_gone),
        "failures": failures,
        "non_dependents_gone": sorted(non_dependents_gone),
        "ok": not failures,
        "per_edit": per_edit,
        "precision": len(needed) / len(dependents_gone) if dependents_gone else None,
    }


def render(result: dict) -> str:
    """The one text form, written to score.json and printed: sorted keys, no time stamp."""
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "evidence", type=Path, help="the evidence folder; score.json is written there"
    )
    args = parser.parse_args(argv)

    result = score(load(args.evidence))
    text = render(result)
    (args.evidence / "score.json").write_text(text)
    sys.stdout.write(text)
    if not result["ok"]:
        print(
            f"score_update_set: FAILED checks: {', '.join(result['failures'])}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
