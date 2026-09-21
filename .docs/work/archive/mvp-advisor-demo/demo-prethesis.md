# Demo script — advisor meeting, 2026-09-10

**Purpose:** a literal, step-by-step runbook for tomorrow's meeting — what to run, what to click,
what to say, in order. Companion to `Recommended_system.md` (the discussion material) and
`backup-run-2026-09-05.md` (the fallback transcript if live demo fails).

**Shape of the meeting:** ~5 minutes live demo (grounds the conversation in what actually runs),
then the rest is discussion of `Recommended_system.md`'s findings and its six-question agenda —
**not** a feature demo, because G4/C2/condition-tagging are not built yet. Don't over-run part A.

---

## ⚠️ Read this before touching `script.md`

`script.md` §8 *"What already runs"* currently claims the epoch guard and invalidation mechanics
were *"executed and asserted, not self-reported."* **This is no longer true and must not be said
tomorrow.** Verified this session: `gateway/internal/deps/` is a package-doc stub with zero logic,
and the write-back epoch comparison does not exist in `handler.go`. Invalidation is this week's
(W9) gate, not a shipped result. If asked about invalidation tomorrow, describe the **frozen
design** (`interfaces.md` §E — reverse dependency map, single writer goroutine, blind purge, epoch
guard) as designed-and-not-yet-built, never as running. `script.md` itself needs this paragraph
corrected before it is used again for anything past tomorrow — flagged here so it isn't forgotten.

---

## Pre-flight (do this before the advisor arrives, not while they watch)

1. **Memory pressure check — first, every time** (CLAUDE.md's standing rule):
   ```
   sysctl kern.memorystatus_vm_pressure_level    # want 0 (green)
   ```
   If not green: close browser tabs / other apps, recheck. Do not proceed on yellow/red.
2. **Cold, clean state:**
   ```
   make demo-reset      # flushes both tiers + corpus index, re-ingests dev-v0
   ```
   Confirm the printed line reads `corpus:44  t1:0  t2:0`.
3. **Start the stack:**
   ```
   make dev
   ```
   Confirm the banner shows `tau=0.850 theta=0.60` and `memory available` comfortably above the
   25% floor. Leave this terminal visible but out of the way — the gateway's log lines double as
   a live, unstaged confirmation that the numbers on screen are real.
4. **Open the UI:** `http://localhost:8080` — confirm the product list loads (`GET /products`
   returning the `dev-v0` catalog). If the list is empty, the corpus index didn't rebuild; re-run
   `make demo-reset`.
5. **Have this file and `backup-run-2026-09-05.md` open** in a second window, not just in memory.

---

## Optional — admission-control self-check (before the meeting, not part of the demo)

`experiments/scripts/verify_admission.sh` is a self-verification script only — **not** part of
the rehearsed Part A, and its numbers are **not citable**. It exists so you can eyeball, tonight,
that the permit pool / shed / coalescing mechanics described on slide 5 actually behave as
described, against a real running gateway rather than only the Go unit tests
(`gateway/internal/admission/pool_test.go`).

```bash
sysctl kern.memorystatus_vm_pressure_level   # check first, every time — CLAUDE.md's standing rule
make dev
# in a second terminal:
./experiments/scripts/verify_admission.sh
```

It runs two checks: `N_DISTINCT` (default 8) concurrent *different* questions, to watch the
permit pool admit some and shed the rest; and `N_IDENTICAL` (default 5) concurrent *identical*
questions, to watch `singleflight` coalesce them onto one generation (same `answer_sha`,
near-identical `latency_ms`, wall time close to one generation rather than five).

⚠️ The default `GEN_QUEUE_BUDGET` (`main.go`) is `2×permits = 8`, so 8 concurrent requests will
**queue rather than shed immediately** under default settings. To reproduce the exact
"4×200 / 4×503" split reported on slide 5, start the gateway with the queue disabled:
```bash
cd gateway && GEN_QUEUE_BUDGET=0 go run ./cmd/gateway
```

---

## If the advisor wants to see each component run separately

`make dev` bundles Redis-check + RAG service + gateway (which itself serves the UI) into one
command. If asked to show each piece individually, here is the **actual** command each one runs
under the hood — not a simplified version, the literal invocation from `Makefile` and
`vite.config.js`. Run in this order, each in its own terminal tab, left running.

### 0 — Redis (usually already running as a background service, not started per-demo)

```bash
redis-cli PING
```
Expect: `PONG`. If not running (rare — it's a LaunchAgent, `launchctl load -w
~/Library/LaunchAgents/com.redis-stack.server.plist` per `CLAUDE.md`), that command starts it;
otherwise nothing to do here.

**To reset Redis's memory (flush both cache tiers + the corpus index)** — the literal command
`make demo-reset` wraps is:
```bash
redis-cli FLUSHALL
```
Do **not** run this bare, mid-demo, without the guards `make demo-reset` actually checks first:
1. **Stop the gateway first.** `FLUSHALL` drops `idx:cache` along with the keys, and the gateway
   only calls `EnsureCacheIndex` at startup — flushing under a live gateway leaves it writing
   `t2:*` records into an index that no longer exists (verified 2026-09-05: step 3 never reaches
   `TIER2_HIT`, and nothing reports an error).
2. **This machine is shared** — `FLUSHALL` wipes *every* database on the Redis server, not just
   this project's keys. Check first: `redis-cli --scan | grep -vE '^(corpus:|t1:|t2:|dep:|entry:|lru:)'`
   — if that prints anything, stop and investigate before flushing.
3. **Re-ingest afterward** — a flush also drops the corpus index, so the RAG service has nothing
   to retrieve from until `make ingest` (or `make demo-reset`, which does both) runs again.

Prefer `make demo-reset` itself unless the point is specifically to show the raw command —
it runs all three checks above plus the re-ingest, in the right order.

### 1 — Ollama (usually already running as the menu-bar app, not started per-demo)

```bash
pgrep -x ollama || ollama serve
```
If a process is already running, this prints its PID and does nothing further. If not, `ollama
serve` starts it in the foreground (own terminal, `Ctrl-C` to stop). Verify the two required
models are present before going further:
```bash
ollama list | grep -E "qwen3.5:2b|nomic-embed-text"
```
Expect both `qwen3.5:2b-q4_K_M` and `nomic-embed-text:latest` listed. (`ollama ps` shows what's
currently *loaded into RAM* — expect it empty until the first real question triggers a MISS; this
is lazy-loading, not a fault.)

### 2 — RAG service (Python), own terminal, foreground

```bash
cd rag && python3 -m rag.server
```
Expect: `rag.server listening on 0.0.0.0:50051`. This is the literal command `make dev` backgrounds
for you — running it directly just keeps it in the foreground of its own tab, easier to point at.

### 3 — Gateway (Go), own terminal, foreground — this is also what serves the UI

Run from the **repo root** (same starting point as steps 0–2), not from inside `gateway/`:
```bash
RESULTS_DIR="$PWD/experiments/results" UI_DIR="$PWD/ui/dist" go run -C gateway ./cmd/gateway
```
`-C gateway` (Go 1.20+; this repo is on 1.26) tells `go run` to change into `gateway/` itself
before building, which is why `$PWD` needs no `../` — it is still the repo root when the shell
expands it, *before* `-C` changes anything. Both env vars matter: `RESULTS_DIR` defaults to the
relative `"experiments/results"` (`main.go`), which resolves wrong once `go run` is working from
inside `gateway/`; `UI_DIR` defaults to empty, which serves API-only with no UI at all.

Expect the same banner as `make dev` (`tau=0.850 theta=0.60 ...`, `admission permits=4 ...`,
`serving demo UI from .../ui/dist`, `gateway listening on :8080`). **The UI needs no separate
command** — open `http://localhost:8080` now. If asked "why isn't the UI its own service" — say
so directly: it's a static bundle the gateway serves from disk, deliberately not a running Node
process, so nothing competes with the model for the memory envelope (`ui/vite.config.js`'s own
comment says this).

### 3b — OPTIONAL: UI as a genuinely separate process (only if asked to see it standalone)

```bash
cd ui && npm run dev
```
Expect Vite to print its own URL (typically `http://localhost:5173`). This is a **hot-reload dev
server**, not what runs during the actual demo or defense — it proxies `/ask`, `/products`,
`/stats` to `:8080` (see `ui/vite.config.js`), so step 3's gateway must still be running for it to
show real data. Close this (`Ctrl-C`) once shown; it is not part of the rehearsed script.

---

## Part A — live demo via the UI (~5 minutes)

Use the UI (`ProductChat` page), not `curl`/CLI — the badge, similarity/overlap pair, and chunk
list render directly, which is more legible to someone watching over your shoulder than terminal
JSON. All queries below are the **exact pinned pair** from `backup-run-2026-09-05.md` — verified
2026-09-05, don't improvise new wording live.

Navigate to any headphones product's chat page for steps 1–3; the trap in step 4 needs a sofa
product's page instead (different `product_id` — the retrieval/grounding is what matters, not
which product page you happen to be on, since these are `dev-v0` policy questions).

### Step 1 — fresh question (the cost every uncached system pays)
Type:
```
Am I entitled to a full refund on my headphones 30 days after delivery?
```
**Expect:** grey `MISS` badge, several seconds (dev-v0/demo, ~3–5 s machine-dependent — never cite
one number, say "a few seconds").

**Say:** "This is what every question costs without a cache — the model actually runs."

### Step 2 — exact repeat (Tier 1)
Type the **identical** sentence again.

**Expect:** green `TIER1 HIT` badge, effectively instant.

**Say:** "Same question, byte for byte — hash lookup, no embedding call, no model."

### Step 3 — paraphrase (Tier 2)
Type:
```
Is a full refund possible for my headphones 30 days after delivery?
```
**Expect:** blue `TIER2 HIT` badge, `similarity ≈ 0.975`, `source_overlap = 1.00`.

**Say:** "Different wording, same evidence — the embedding recognizes the paraphrase, and the
overlap rule confirms the grounding actually matches before serving."

### Step 4 — the trap (high similarity, wrong evidence) — the moment that matters most
On a **sofa** product's chat page, type:
```
Am I entitled to a full refund on my sofa 30 days after delivery?
```
**Expect:** grey `MISS` badge, `similarity ≈ 0.869` (**above** the 0.85 threshold), `source_overlap
≈ 0.40` (**below** the 0.6 threshold).

**Say, and show the two chunk lists on screen:**
> "One noun different — headphones to sofa. The embedding thinks this is safely similar to the
> cached electronics-return answer: 0.869, above threshold. But the grounding disagrees — put both
> chunk-ID lists on screen and let the room check the intersection themselves. Two shared policy
> chunks out of five in the cached entry — 0.40, below the rule's threshold. This is a fixed
> similarity cache getting it wrong and this system refusing correctly, on the same input."

If asked "what about τ = 0.86?" — answer from memory, don't guess: *verified 2026-09-05, the trap
still refuses at τ = 0.86 (0.8689 still clears it, containment still refuses); it stops working at
τ = 0.87.* State up front that τ/θ here are demo values, the real result is the swept frontier.

### Counters sidebar
Point at it after step 4: 4 requests, 2 hits, hit rate 50%, **generations avoided: 2** — say this
number out loud, it's the cheapest piece of scalability evidence visible without the recorded load
clip (which doesn't exist yet — this is the pre-thesis stage, not the defense).

### Optional, only if asked about the Tier-1 fix specifically
A same-session fix scopes the Tier-1 key by `product_id` (workflow bypass, recorded in
`.docs/work/two-lane-cache/approvals.md`). Not part of the rehearsed script above — only mention
if the conversation specifically goes there (e.g. the "what if two products share a literal
question" line of questioning).

---

## Part B — transition to discussion (the actual point of tomorrow)

**Say, verbatim or close to it:**
> "That's what's built and measured as of last week. Since then I found a research direction I
> want to walk through with you before building more — it changes what the headline claim looks
> like, and I'd rather get that right before spending the remaining weeks on it."

Then open `Recommended_system.md` and go through, in order:
1. §2 (current state table) — 30 seconds, orients them.
2. §3.1 executive summary, then §3.2 (the G4 finding) in full — this is the one worth spending
   real time on.
3. §3.3 (the hit-rate/safety tension) — the uncomfortable finding, say it before they find it.
4. §7 (the six-question agenda) — work through these **as decisions to get today**, not just
   information to convey.

Do **not** re-read §8 (the execution plan) aloud — that's for you after the meeting, not a thing
to present. If the advisor wants to see it, it's there.

---

## If something breaks live

1. **Ollama/Redis died, or no time for a live run:** switch to `backup-run-2026-09-05.md` — it is
   a verbatim transcript of the exact same four steps, captured clean. Narrate from it directly;
   the numbers match what live would show.
2. **Memory pressure went yellow/red mid-setup:** do not run `make dev`. Fall back to the
   transcript immediately rather than risk a stall or swap in front of the advisor.
3. **UI won't load:** fall back to `make demo` in the terminal (same four steps, same numbers,
   just less visual) — see the transcript for exact expected output.

---

## After the meeting

Whatever gets decided against the six-question agenda, write it down the same day — in
`docs/decisions.md` as ADR(s) if anything is confirmed, and update `Recommended_system.md`'s
status line (currently "DRAFT — nothing decided") to reflect what was actually approved. Then, and
only then, start on `Recommended_system.md` §8's execution plan in priority order.
