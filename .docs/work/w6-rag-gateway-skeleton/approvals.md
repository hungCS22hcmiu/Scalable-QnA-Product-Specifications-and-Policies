| Phase          | Required | Approved | When       | ADR |
| impact         | yes      | yes      | 2026-09-03 | —   |
| contract       | no       | n/a      |            |     |
| experiment     | no       | n/a      |            |     |
| implementation | yes      | yes      | 2026-09-03 | ADR-021, ADR-017, ADR-014, ADR-003, ADR-015 |

**Frozen values invoked, not changed** (`impact.md` §2 — "Invalidates: none";
`experiments/results/` holds no run directories):

- **ADR-021** — `qwen3.5:2b-q4_K_M`, `think: false` on every call (`rag/src/rag/config.py`,
  consumed by `generate.py`; never a per-request override).
- **ADR-017** — `num_ctx = 8192`; `OLLAMA_NUM_PARALLEL = 4` is a server-side env var, verified by
  `make env-check`, never a request option.
- **ADR-014** — `top_k = 5`, pinned in `rag/src/rag/config.py` only. Per `impact.md`'s lead risk,
  Go sends `0` ("server default") and Python resolves it; a literal `5` in Go is the silent-drift
  path this decision exists to close.
- **ADR-003** — `nomic-embed-text`, 768-dim, invoked indirectly through `retrieve.py`.
- **ADR-015** — Tier-1 key normalization (lowercase, collapse whitespace, strip punctuation),
  exactly as written. No stemming/stopwords/synonyms: that would be both an ADR-015 change and a
  reuse decision `cache/` must never make.

**New Go dependencies signed off** (`.docs/ai/rules.md` #9, `impact.md` §4): `google.golang.org/grpc`,
`google.golang.org/protobuf` (mandated by the proto, ADR-007), `redis/go-redis/v9`. Gin/Fiber cut —
`interfaces.md` §A is one JSON route, and `fasthttp` lacks the `context` deadline/cancellation
semantics the W16 permit pool depends on.

**Contract phase not required** — implements `interfaces.md` §A/§B/§D as written, no `.proto` edit
(`impact.md` §5). **Experiment phase not required** — p50 miss latency is a worklog number, not a
campaign: no `run_id`, no `manifest.yaml`, no write to `results/*/raw/` (`impact.md` §6).
