# Presenter script for the advisor pitch

Companion to `slides.md` (revised 2026-09-10, v2 — diagram/table-first) and `Recommended_system.md`
(the research memo Parts 3–5 are built from). This is the **talk track** — the slides are
deliberately sparse (diagram or table + a few words), so this file carries the explanation you
actually say out loud. Each beat is tagged to its backing so a follow-up question has a one-lookup
answer instead of an improvised one.

> **Note on numbering.** `RS §X` = `Recommended_system.md`. `EP §X` = `experiment-protocol.md`.
> `DC §X` = `data-card.md`. `Proposal §N` = `Final_Proposal.md`.

> **Framing.** The whole talk presents the **proposed system** — the thesis-phase build plan — as
> the main content, not what currently runs. Don't narrate the pre-thesis build, badges, or
> specific test runs anywhere except slide 16, where it's a short, deliberate summary.

**How to use this:** the slide gives the audience something to look at; you supply the sentences.
Read once for shape, then talk from memory using `slides.md`'s numbers as anchors. Keep language
plain — this room needs the system's behavior and why it's correct, not embedding math or model
internals.

---

## 1 · Title

No backing needed. State who you are, the title, and the frame for today: a scoping decision on
the thesis-phase plan, not a defence rehearsal. Six concrete items need a yes/no by the end,
surfaced naturally through the talk rather than read as a checklist.

## 2 · The cost of serving locally

**Say:** This machine answers about one question every five seconds, measured. That's not a weak
setup — it's close to what generation costs on fixed hardware. Point at the table: redundant
traffic means most of that cost, today, is repeats paying full price; a fixed memory budget means
overload doesn't degrade gracefully, it can swap and take everything down with it. The idea this
whole thesis is built on: convert that redundant, compute-bound cost into memory-bound cache
lookups — and the rest of the talk is about whether that's *safe* to do.

**Backing.** The ~5-second figure is a feasibility-spike measurement (`decisions.md` ADR-017), not
a citable throughput number — say so if pressed. Load-conversion framing is `Final_Proposal.md` §3.

## 2b · The idea — load conversion

**Say:** Open by naming what kind of statement this is, because it blocks the commonest misreading:
this is **not** a latency formula and not a predicted throughput — it's a **ceiling**, the highest
request rate this fixed envelope sustains before queues grow and the gateway starts shedding. Give
it its lineage in one clause if the room is technical: it's the **bottleneck law** from operational
analysis, written for two resources. Then state it in words before pointing at it: the max
sustainable rate is whichever term binds first — the expensive generation path, or the cheap
cache-hit path — and raising the hit rate moves load off the expensive term onto the cheap one.
Read the *shape*, not the symbols: as `h` rises the left term grows without bound because fewer
requests need the model, while the right term falls because more requests need the lookup;
somewhere they cross, and at that point the binding constraint moves **off the language model onto
the lookup path**. If asked why `min` and not a sum: these are two constraints on the *same* λ, not
two capacities you may add — a system is limited by whichever path saturates first.

Then the sentence that carries the actual idea, and the one most likely to be skipped: **the gain
is not that a cached answer is faster.** It's that a cached answer **doesn't consume the scarce
resource** — no permit, no unified memory, nothing touching the model's KV cache. It moves a unit
of work from the constrained resource onto an idle one. That's why the formula needs two separate
service rates rather than one latency discount, and it's the clean answer to "isn't this just
RAGCache / prefix caching?": **those make a miss cheaper, this makes misses not happen**, and only
the second moves the binding constraint off generation. They compose rather than compete.

Then the honest finding, stated as a result and not an apology: on this envelope the crossover sits
at roughly **0.997** hit rate while the highest `h` the redundancy sweep can reach without going
degenerate is about **0.988**. The crossover is **unreachable here**, so the system stays
generation-bound throughout its operating range. Say plainly this was **pre-registered before
measuring**. Then close the loop on falsifiability, because "we didn't see the crossover" sounds
like a failure and is not: the model is falsifiable *precisely because* it predicts a crossover —
"caching helps" is unfalsifiable and therefore worthless as a claim — and what **would** falsify S1
is measured λ_max failing to track the binding term `μ_gen/(1−h)` across the sweep, or a near-zero
hit-rate spread across the three skews.

**If pressed on the numbers — better said unprompted than extracted:**

- **`h` is not a knob.** It's the reuse actually *accepted* — every candidate the lexical-support
  gate refuses counts as a **miss**. So the safety mechanism deliberately lowers `h`, and therefore
  deliberately lowers λ_max. That trade-off is the thesis, and slides 9b/10 are where it's priced.
  Related bound worth volunteering: **`h ≤ ρ`** — a hit rate above the traffic's intrinsic
  redundancy is obtainable only by being **wrong**, which is why correctness is a clause of the
  definition of scalable (S3), not a caveat beside it.
- **`μ_hit` is two numbers, not one.** Tier-1 ≈ 8000 rps (a hash read); Tier-2 ≈ 61 rps (pays an
  embedding round-trip). Always quote the Tier-2 figure — it's conservative, so it under-reports
  our own ceiling.
- **`μ_gen` ≈ 0.19 req/s**, = 28.2 tok/s ÷ ~150 output tokens, and it is **spike-level** (one batch
  of four concurrent generations to completion, 8.9 s wall) — not a sustained-load
  characterisation. What the spike already settles is the *shape*: `μ_gen ≪ μ_hit` is an **observed
  property of this envelope**, not an assumption of the model.
- **Did you measure μ_hit?** Yes — 2026-09-06, but **co-hosted, so not citable**: a shakedown, not a
  result. The pre-registered falsification trigger was μ_hit ≤ ~16 rps; the probe returned ≈ 61, so
  the trigger did **not** fire and S1's wording stands. Be precise about the margin rather than
  letting it be dug out: that's **3.8×**, not an order of magnitude. The off-box Phase 1
  re-measurement is what actually settles it.
- **One number that makes "generation-bound" concrete:** at `h = 0.983` — the simulated sweep's top
  skew — the generation term is ≈ 11 req/s while the hit term is still ≈ 62. Even at the most
  favourable reachable hit rate, generation binds by more than 5×.
- **Where the model is a simplification.** It's a fluid, mean-rate argument, so a burst of misses
  can still shed even while λ < λ_max — which is exactly *why admission control is a separate
  mechanism* (Part 3) rather than a consequence of the cache: λ_max gives the average ceiling, the
  permit pool handles instantaneous variance. And the two paths aren't perfectly disjoint resources
  — every Tier-1 miss runs retrieval even when Tier-2 then hits — but generation is bound at
  Metal/memory while hits are bound at Redis/CPU, so the approximation errs conservative.

**Backing.** `Final_Proposal.md` §3 (the formula itself); EP §6 Headline A / S1 for the exact
pre-registration language — *"the pre-registered expectation is therefore that h* lies outside the
reachable range... reported as a quantitative result, not as a failed measurement."* ADR-027 for the
crossover restatement and the 16 rps trigger; `docs/learning/22-load-conversion.md` §2 (derivation),
§4 (why h* is unreachable), §4b (the probe that checked the trigger), §9 (response-level vs.
inference-level caching). The `μ_gen`/`h*` figures exist but are spike-level and co-hosted
respectively — **not** the citable evaluation-phase numbers, and say that distinction if pressed on
exact values.

## 3 · Why a simple cache isn't enough

**Say:** Walk the table. Exact-text caching only catches byte-identical repeats. Similarity-only
caching — the standard approach — catches paraphrases, but similarity measures *wording*, not
*correctness*: two near-identical questions can have different correct answers, and a
similarity-only cache can't tell. That's the actual research problem this thesis solves — reuse
based on evidence, not wording — plus a separate mechanism (Part 3) that keeps the machine healthy
under load.

**Backing.** RS §1 / RS §3.2 — "similarity is high but the correct answer is opposite" is the
structural failure the whole design responds to.

---

## 4 · System overview

**Say:** Point at the diagram. A gateway sits between clients and the two expensive pieces it
protects — retrieval and a language model — both used as-is, not modified. Everything inside the
gateway box is the contribution: two governors, two separate stores (the cache and the retrieval
index — worth naming, they're not the same thing). Call out one detail explicitly: retrieval never
needs a permit, only generation does — that's why a Tier-2 candidate can always be checked for
lexical support before anything touches the memory budget. Say plainly: retrieval and the model are a black box on
purpose, nothing about their internals is being contributed or measured.

**Backing.** Matches `Final_Proposal.md` §6's component boundaries. This is RS §5's proposed
architecture, redrawn without a built/proposed split since this talk *is* the proposal.

## 5 · How a question flows through the system

**Say:** Walk the sequence top to bottom: exact match first, cheapest, no model involvement.
On a miss, embedding the question and retrieving supporting material happen **concurrently** — one
doesn't wait on the other. The partition is worked out from what retrieval actually returned, the
semantic search is scoped to it, and a candidate still has to clear the lexical-support check before
it's served. Only the bottom branch, gated by admission control, ever touches the model — and note the
write-back step registers dependencies, which is what Part 4's invalidation slide purges by later.
Say the punchline pointing at the top branches: this is what makes served traffic exceed what the
model alone could sustain.

**Backing.** RS §5's proposed sequence diagram, simplified. If asked directly "is this what runs
today" — be direct: this is the target design for the thesis phase; today's build is summarized
honestly on slide 16.

## 5b · Framework, tools, and technologies

**Say:** One line per row, don't dwell — this slide exists so nobody has to ask "what's it built
in," not to defend any one choice. Go for the gateway, for the concurrency primitives the admission
pool and dependency map are built on, not for any language-specific advantage — the reuse-safety
experiment would test identically in another language. Redis Stack because it's a real vector
database via RediSearch, not just a key-value cache, and because FLAT gives exact search — no
approximate-nearest-neighbor noise mixed into the very signal being measured. Python/LlamaIndex for
ingestion and retrieval, mature tooling, not reinvented. Ollama native on the host, never Docker,
because macOS containers can't reach the Metal GPU. Qwen 3.5 2B and nomic-embed-text were both
picked by measuring candidates against this machine's real memory ceiling, not by reputation.
Close on the two rules that keep this list honest: the LLM and embedding model are frozen once
chosen, and everything on this slide is an *architectural* pick, not a research one.

**Backing.** `Final_Proposal.md` §7's Technical Stack table and its R/A/I tiering (architectural
choices must fit requirements and not confound the experiment; novelty is neither claimed nor
required here). If asked "why not LangChain" or "why not a dedicated vector DB" — same answer
either time: not on the critical path of what's being measured, and the alternative would cost more
of the fixed memory envelope than it returns. `ADR-003`/`ADR-021` for the two frozen-by-measurement
model picks.

---

## 6 · The mechanism

**Say:** Point at the first diagram — a request either gets a free slot, waits briefly if there's
room, or is rejected cleanly once both are full. Rejecting fast is a feature: it protects
everything else from degrading together. Second diagram: if several people ask the exact same
question at once, one generation runs and everyone shares the result instead of paying N times.
Walk the table as the summary line for each. None of this touches the model's internals — it's
ordinary concurrency control (a bounded worker pool, a queue, deduplication of in-flight work)
applied to a resource that happens to be a language model.

**Backing.** `Final_Proposal.md` §6's admission-control description. Frame this for a backend
audience explicitly as familiar ground — semaphore, bounded queue, request coalescing.

## 7 · Why this is an independent contribution

**Say:** Walk the table top to bottom. This doesn't depend on the caching result — it stands alone.
It's not a novel pattern — it's recognized, active practice in current systems that serve language
models at scale. The caching-focused prior work this thesis is positioned against doesn't do this
at all — none of it bounds concurrent load or sheds under memory pressure. Land on the weighting:
60% of the engineering contribution is this governor, not the cache.

**Backing.** RS §3.6 — cites current (2026) LLM-serving admission-control literature and
production practice, and states the prior-art gap explicitly: "the 60% systems pillar is untouched
by either [prior-art] system." Keep the table's claims as the spoken content; don't recite specific
paper names unless asked.

---

## 8 · The workflow

**Say:** Walk the flowchart top to bottom — this is the whole two-tier idea in one picture. Exact
match, cheapest. Otherwise: retrieve supporting material, work out the partition from that
material (never guessed from wording), search only inside it, and if a candidate survives a
lexical-support check, serve it — otherwise generate fresh. The table underneath is the one-line
version of each stage, useful if a question zeroes in on one box.

**Backing.** `interfaces.md` §A/§D for the two-tier contract; RS §5 for the partition +
lexical-support design. `Final_Proposal.md` §6.3 for scope if asked: only "stable" content (specs/policies) is
cached at all — dynamic content (stock/price) bypasses the cache entirely.

## 8b · Three outcomes, in detail

**Say:** Same idea as slide 8, now as the three concrete request paths, because "what does each
outcome actually cost" is a fair systems question and deserves a precise answer. Tier-1 hit:
straight hash lookup, nothing else runs. Tier-2 hit: retrieval and the partition rule run, the
search is scoped, the lexical-support check has to pass — still no generation. Miss: the only path that
ever touches admission control and the model, and the only one that writes back to both stores and
registers dependencies for invalidation. Point at the third diagram specifically when Part 4's
invalidation slide comes up later — this is where "register dependencies" happens.

**Backing.** Structurally, this is RS §5's proposed sequence design split into its three outcome
branches. Don't cite specific latency numbers here — none from the pre-thesis build are citable
(slide 16); the point of this slide is the *shape* of each path, not a measured cost.

## 9 · Why similarity alone is unsafe

**Say:** Walk the table as a concrete instance of slide 3's abstract claim: two questions worded
almost identically, differing only in which product or condition they're about, can have
completely different correct answers — while their similarity score reads high. A similarity-only
cache cannot tell these apart. It serves the wrong answer with no visible sign of error. This is
the concrete failure the next slide's two fixes exist to close.

**Backing.** RS §3.2's framing; structurally grounded in `docs/learning/10-theory-of-the-two-
tiers.md` §E, now independently supported by literature on embeddings' blindness to exactly this
kind of distinction (RS §3.2/§3.4). Keep any example verbal and generic — nothing here is a
citable measured number.

## 9b · How the evidence check actually decides

**Say:** Two stages, in sequence, and they read different things. The first stage — partition plus
similarity — asks *where*: does this question's grounding put it in the same product, or the same
policy, as the cached candidate, and is the wording close enough? That narrows the field to
something worth checking at all. The second — lexical support — asks a different question: *what do
those chunks actually say*? Does the cached answer's own wording still show up in the
freshly-retrieved material? A candidate has to clear both.

Walk the worked example next, it's real, not constructed: an electronics-return answer and a
warranty question land in similarly-scored candidates on similarity alone — similarity can't
separate them. The words do: "return / refund / window / day" versus "warranty / defect / coverage"
barely share anything, so the lexical check is what actually refuses.

**One correction to make out loud, because it's a fair question to anticipate:** the current
report's frozen C1 claim is a *different*, older rule — chunk-ID containment, comparing which
chunks came back as sets, not what they say. Measured on this project's own corpus it scored two
opposite-correct-answer cases identically, 0.80 and 0.80, and partition-matching alone already beat
it on every disagreement measured. It isn't gone — it's still reported as one of the five compared
configurations (Part 5) — but it is no longer part of what this design proposes to actually serve.
That's a live, open framing question for today, not a settled rewrite.

Then the honest limit, stated before it's asked: if one paragraph states both an "opened" and an
"unopened" condition together, and the same paragraph gets fetched for both questions, both stages
above see identical evidence either way — neither can tell the readings apart, because nothing
about *which condition the question means* is visible to either. That's not a runtime problem at
all — it has to be closed one level earlier, when the content is written: keep opposing conditions
in separate chunks so there's something for these checks to actually compare.

**Backing.** The partition mechanism is `reuse/lane.go`'s built `Classify`/`Namespace`/
`DecideNamespace` — its own comment states plainly "there is deliberately no containment term."
The older chunk-ID containment formula (`|retrieved ∩ entry_sources| / |entry_sources|`) is
`reuse/rule.go`'s built `Overlap()`, this thesis's original frozen C1 claim (`CLAUDE.md`
"Provenance-first, and deterministic"), now computed only as the evaluation counterfactual — see
`cascade.go`'s own comment, "the two verdicts side by side ARE the experiment." The lexical-support
check and its worked trace are RS §3.2 (GroundedCache's G4 gate, `τ_s=0.6` paper default) —
proposed, not yet built; RS §3.2 is explicit that G4 is an evidence-*mismatch* detector and does not
itself close the same-chunk/opposite-condition case. Condition-tagging is RS §3.4 (⭐
second-strongest direction), already partly required by the corpus design (`decisions.md` ADR-024
requirement 3). If asked "is this proven" — be direct: the worked example is real (this project's
own measured pair); the G4/condition-tagging mechanisms themselves are structural argument plus
literature triangulation, not yet measured on this project's own corpus. If asked "so is C1
changing" — be direct: that is precisely today's agenda item 6 (RS §5, §7) — not decided yet.

## 10 · Two fixes, and what's still open

**Say:** The recap, one line per row. Partitioning closes cross-product/cross-policy mismatches by
construction — different row entirely from the previous slide. The lexical-support check just
walked through closes same-partition mismatches. Neither catches the case where the *same* material is
fetched both times but the question flips one small, meaning-changing word — because neither check
reads that specific word, only which chunks and which words came back. That gets closed by how the
source content is written, not by a runtime rule: condition-tagging, from the previous slide.

**Backing.** RS §3.2's "Consequence" paragraph and RS §3.4's condition-tagging entry — already
partly required by the corpus design (`decisions.md` ADR-024 requirement 3). Same citations as the
previous slide; this one is the recap table, not new material.

## 11 · Invalidation

**Say:** First diagram, the purge: an edit event carries what changed and lands on a channel, read
by a single writer goroutine — worth naming explicitly, because a single writer is what makes this
safe under concurrent edits without a lock on the read path. It updates an in-process index, looks
up every cache entry that depends on the changed content, deletes each one from *both* cache
tiers — not just one — deletes the dependency record itself, and bumps a version counter. Reads
stay lock-free throughout; only the one writer goroutine ever mutates state. Second diagram is the
race this design has to close: a generation that started *before* an edit must not save its answer
*after* the purge already ran, or it resurrects exactly what was just removed — so every write-back
reads the version first and discards if it's advanced past what it started with. Land on the
positioning line from the table: this is the same pattern CDNs have used for over a decade for
this exact problem — tag-based cache invalidation (Akamai, Fastly-style surrogate keys). Not novel;
well-understood, applied in a new setting.

**Backing.** `interfaces.md` §E's frozen design (reverse dependency index, single writer, blind
purge, a version counter guarding the write-back race). RS §3.5's CDN-analogy positioning — say the
sentence aloud, it reframes invalidation from "the hard unsolved problem" to "the standard solution
for this shape of problem."

---

## 12 · Dataset and workload

**Say:** Name the sources directly, don't leave it vague. Product catalog and specs come from
McAuley-lab's Amazon product data — a public, real product dataset out of UCSD. Product questions
come from AmazonQA, the companion Q&A dataset from the same group — real shopper questions, so the
phrasing carries genuine paraphrase structure rather than being invented. Policy questions are
authored in-house, because no public dataset contains store-policy Q&A at all, and the invalidation
experiment needs edits under the author's own control anyway. On top of both: hard cases built on
purpose — similar wording, different correct answer — so the safety mechanism is actually
exercised. Flag the one open item plainly: the Amazon/AmazonQA data's redistribution terms aren't
resolved yet (no license stated on the dataset card) — the fallback if it isn't permitted is a
download+build script and a hash manifest instead of shipping the raw data. The workload also has
to clear quality gates before use; a corpus that fails gets fixed, not worked around.

**Backing.** DC §1 (Amazon product-data sourcing + the license caveat), DC §3 (AmazonQA sourcing),
DC §2 (in-house policy corpus and why), DC §4 (the hard-case set), DC §7 (the four-criterion gate,
`make gate-corpus`, already implemented).

## 13 · Configurations compared

**Say:** Five setups, same workload: no cache, exact-match only, a similarity-only cache (what an
off-the-shelf tool does), the source-overlap rule, and the full system. Each also runs twice —
content static, and content edited mid-run — to see whether invalidation holds up under real change.

**One naming note, worth being precise about if asked:** config 4 is this thesis's *original*
frozen rule — the chunk-ID containment score from slide 9b, run alone with no partitioning. It is
kept as a reported baseline. The mechanism slide 9b actually walked through — partitioning plus the
lexical-support gate — only shows up inside config 5, the full system, alongside admission control
and invalidation. There is no config that runs partitioning + lexical-support in isolation, apart
from everything else; that's a fair question to flag as open, not paper over.

**Backing.** `Final_Proposal.md` §9.2's five-configuration grid, `CLAUDE.md`'s "Five cache
configurations" list (config 4 is named there, verbatim, "source-overlap rule"); `decisions.md`
ADR-023's static/mutation factor — a run is identified by (config, mutation), never config alone.

## 14 · Metrics — two headlines

**Say:** Two columns, two questions. Systems: does the gateway let the machine serve more traffic
without breaking — throughput as load increases, clean rejection under overload, staying in a safe
memory zone throughout (a run that leaves it is discarded, never averaged in). Research: is the
reuse decision actually safe — reuse rate vs. wrong-answer rate, the source-overlap rule vs. the
naive baseline, at a pre-agreed acceptable error rate, graded by an independent AI referee that never
generated the answer it's grading. The line underneath both columns is what keeps either headline
honest: latency compared at *matched* reuse rate, so "reuses more" can't quietly also mean "costs
more per request."

**Backing.** EP §4 in full — this slide compresses its operational definitions (goodput vs. shed,
hit-path latency decomposition, end-to-end p95 at matched hit rate, the frozen LLM-judge prompt).
If asked for the acceptable-error number: **δ ≤ 5%, provisional**, finalized against a human-
verified sample partway through the evaluation (`decisions.md` ADR-006, EP §5).

## 15 · Statistical rigor

**Say:** Four short disciplines, each one sentence. Thresholds tuned on one split, reported on a
separate held-out split — never the same data twice. Results split by whether a trap pair spans
two products (a simpler rule could also catch it) or stays within one product (only this design's
approach catches it) — if the advantage lives entirely in the easy category, that's reported
plainly. A no-benefit outcome is written down as a possibility before the data exists, with the
diagnostics that explain it. And every rate carries a confidence interval, from repeated runs.

**Backing.** EP §5 (validation/test split by seed-cluster, avoiding paraphrase leakage); DC §2's
B-within/B-cross split (`decisions.md` ADR-028 — "if the advantage rests entirely on B-cross, a
`product_id` key would have matched it, and that's what gets reported"); EP §6's pre-registered
null.

## 16 · Developed so far, and limitations

**Say:** Two tables, both stated plainly rather than left for a question to surface. Built: the
retrieval pipeline end to end, the gateway's admission control and both cache tiers implemented and
functionally tested on a small trial corpus, and a web interface used during development. Not yet
built: the lexical-support check (G4) is designed, not implemented; invalidation is designed, not
implemented, and is the next build item; retrieval has no awareness yet of which page a question
came from, working from wording alone — a known constraint the evaluation design already accounts
for; admission-control numbers so far are small functional trials, and there's an open question
about whether the underlying model-serving tool actually honors the concurrency the gateway
assumes, to be confirmed before any number is reported as final. Close directly: none of tonight's
pre-thesis numbers are citable — they confirm the mechanisms run, not the evaluation.

**Backing.** RS §2's current-state table and RS §4's priority order map directly onto this slide's
two tables — RS's priority order (resolve the concurrency question, then invalidation, then the
lexical-support check, then the content-authoring decision) is the literal thesis-phase plan if this pitch
is approved.

---

## Closing / Q&A

Work the table in `slides.md` from memory — eight entries, each answerable in two or three
sentences. If a question goes somewhere the slides don't cover, say "that's open, here's how I'd
approach it" rather than improvise a number. Nothing in this deck is a citable result — say so
directly if anyone tries to quote a figure from tonight.
