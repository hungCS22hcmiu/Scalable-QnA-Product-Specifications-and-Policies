"""Apply each mutation of design.md §7 to the source, run the httpapi suite, record what failed, restore.

Run from anywhere: python3 docs/work/2026-10-04-httpapi-tests/evidence/mutate.py [M1 M2 ...]
Every mutation must print CAUGHT. The source files are restored even if the run is interrupted.
"""
import re, subprocess, sys, pathlib

GW = pathlib.Path(__file__).resolve().parents[4] / "gateway"
H = GW / "internal/httpapi/handler.go"
E = GW / "internal/embed/client.go"
C = GW / "internal/httpapi/cascade.go"

M1_OLD = """	gen, err, shared := h.Generations.Do(coalesceKey, func() (*generation, error) {
		permit, err := h.Admission.Acquire(ctx)
		if err != nil {
			return nil, err
		}"""
M1_NEW = """	outerPermit, outerErr := h.Admission.Acquire(ctx)
	if outerErr == nil {
		defer outerPermit.Release()
	}
	var gen *generation
	var shared bool
	err = outerErr
	if outerErr == nil {
	gen, err, shared = h.Generations.Do(coalesceKey, func() (*generation, error) {
		permit := outerPermit"""

MUTATIONS = {
    "M1 permit acquired outside Generations.Do": [
        (H, M1_OLD, M1_NEW),
        (H, "\t\t}, nil\n\t})\n\n\tswitch {", "\t\t}, nil\n\t})\n\t}\n\n\tswitch {"),
    ],
    "M2 eval emit only on the MISS branch": [
        (H, "\t\th.Eval.Log(rec)\n", ""),
        (H, "\twriteJSON(w, askResponse{\n\t\tAnswer:          result.Text,",
            "\th.Eval.Log(rec)\n\twriteJSON(w, askResponse{\n\t\tAnswer:          result.Text,"),
    ],
    "M3 Tier-2 t1_key from the raw question": [
        (H, "\t\t\t\tT1Key:          t1Key,", "\t\t\t\tT1Key:          cache.Key(req.Question, req.ProductID),"),
    ],
    "M4 second entry_id for the Tier-2 write": [
        (H, "\t\t\t\tEntryID:        entryID,\n\t\t\t\tQueryText:", "\t\t\t\tEntryID:        cache.NewEntryID(),\n\t\t\t\tQueryText:"),
    ],
    "M5 rec.Shed dropped": [
        (H, "rec.Shed, rec.Cache = true, cacheShed", "rec.Cache = cacheShed"),
    ],
    "M6 serve Tier 2 on similarity alone": [
        (H, "\tif t2.NSDecision.Reuse {", "\tif t2.Found && t2.Candidate.Similarity >= h.Thresholds.Tau {"),
    ],
    "M7 Tier-1 promotion deleted": [
        (H, "\t\t\tputCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), bumpTimeout)",
            "\t\t\treturn\n\t\t\tputCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), bumpTimeout)"),
    ],
    "M8 a failed Tier-1 write-back fails the request": [
        (H, '\t\t\tlog.Printf("gateway: tier-1 write-back failed for request_id=%s: %v", requestID, err)',
            "\t\t\treturn nil, err"),
    ],
    "M9 a cancellation classified as SHED": [
        (H, "\tcase errors.Is(err, admission.ErrShed):", "\tcase errors.Is(err, admission.ErrShed), errors.Is(err, context.Canceled):"),
    ],
    "M10 nil retrieved IDs passed to Answer": [
        (H, "h.RAG.Answer(ctx, req.Question, topKServerDefault, retrievedIDs, req.ProductID)",
            "h.RAG.Answer(ctx, req.Question, topKServerDefault, nil, req.ProductID); _ = retrievedIDs"),
    ],
    "M11 coalesce key without product_id": [
        (H, "\tcoalesceKey := t1Key", "\tcoalesceKey := normalized"),
    ],
    "M12 Namespace omitted from the Tier-2 write": [
        (H, "\t\t\t\tNamespace:      writeNS,", '\t\t\t\tNamespace:      "",'),
    ],
    "M13 Retrieve's IDs written to both tiers": [
        (H, "\t\t\tAnswer:         result.Text,\n\t\t\tSourceChunkIDs: result.SourceChunkIDs,",
            "\t\t\tAnswer:         result.Text,\n\t\t\tSourceChunkIDs: retrievedIDs,"),
        (H, "\t\t\t\tSourceChunkIDs: result.SourceChunkIDs,\n\t\t\t\tT1Key:",
            "\t\t\t\tSourceChunkIDs: retrievedIDs,\n\t\t\t\tT1Key:"),
    ],
    "M14 X-Thesis-Stratum not read": [
        (H, "\t\tStratum:         stratumHeader(r),", "\t\tStratum:         nil,"),
    ],
    # Added after the implementation review (review.md, "Implementation review"): each is a probe a
    # reviewer showed the first suite missed.
    "M15 similarity reported as 1 - cosine": [
        (H, "\t\ts := t2.Candidate.Similarity", "\t\ts := 1 - t2.Candidate.Similarity"),
    ],
    "M16 source_overlap reported as 1 - overlap": [
        (H, "\t\to := t2.Decision.Overlap", "\t\to := 1 - t2.Decision.Overlap"),
    ],
    "M17 TIER2_HIT entry_sources set to the retrieved IDs": [
        (H, "rec.EntrySources = t2.Candidate.Entry.SourceChunkIDs", "rec.EntrySources = retrieved.ChunkIDs"),
    ],
    "M18 MISS entry_sources set to the retrieved IDs": [
        (H, "rec.EntrySources = gen.SourceChunkIDs", "rec.EntrySources = retrievedIDs"),
    ],
    "M19 TIER2_HIT record drops retrieved_chunk_ids and the epoch": [
        (H, "\t\trec.AnswerSHA256 = sha256Hex(t2.Candidate.Entry.Answer)\n",
            "\t\trec.AnswerSHA256 = sha256Hex(t2.Candidate.Entry.Answer)\n\t\trec.RetrievedChunkIDs, rec.DatasetEpoch = nil, nil\n"),
    ],
    "M20 Tier-1 promotion written without sources": [
        (H, "\t\t\t\tSourceChunkIDs: sources,", "\t\t\t\tSourceChunkIDs: nil,"),
    ],
    "M21 record's epoch taken from Answer": [
        (H, "\t\tentryID := cache.NewEntryID()", "\t\trec.DatasetEpoch = &result.DatasetEpoch\n\t\tentryID := cache.NewEntryID()"),
    ],
    "M22 trim to 0 (unbounded) instead of the configured capacity": [
        (H, "h.Cache.TrimToCapacity(ctx, h.Capacity)", "h.Cache.TrimToCapacity(ctx, 0)"),
    ],
    "M23 MISS does not touch its entry": [
        (H, "\t\th.touch(ctx, entryID)\n", ""),
    ],
    "M24 TIER2_HIT touches the request_id": [
        (H, "h.touch(ctx, t2.Candidate.Entry.EntryID)", "h.touch(ctx, requestID)"),
    ],
    "M25 scoped-search error serves the global nearest": [
        (C, '\t\tlog.Printf("gateway: tier-2 namespace search failed, degrading to MISS: %v", err)\n\t\treturn out',
            '\t\tlog.Printf("gateway: tier-2 namespace search failed, degrading to MISS: %v", err)\n\t\tout.NSDecision.Reuse = true\n\t\treturn out'),
    ],
    "M26 tau judged on the global nearest, not the served candidate": [
        (C, "\t\t\tSimilarity: c.Similarity,", "\t\t\tSimilarity: nearest.Similarity,"),
    ],
    "M27 theta joins the served decision and the namespace term is deleted": [
        (C, "h.Cache.NearestTier2InNamespace(ctx, vec, out.QueryNS, 1)", "h.Cache.NearestTier2(ctx, vec, 1)"),
        (C, "\t\t\tEntryNS:    c.Entry.Namespace,", "\t\t\tEntryNS:    out.QueryNS,"),
        (C, "\t\tif d.Reuse {", "\t\tif d.Reuse && reuse.Overlap(retrieved.ChunkIDs, c.Entry.SourceChunkIDs) >= h.Thresholds.Theta {"),
    ],
    # Not in design.md §7: checks that the strict fakes (N1) catch what they claim to.
    "X1 top_k sent as 5": [
        (H, "const topKServerDefault = 0", "const topKServerDefault = 5"),
    ],
    "X2 nomic query prefix dropped": [
        (E, 'const queryPrefix = "search_query: "', 'const queryPrefix = ""'),
    ],
}

only = sys.argv[1:]
originals = {H: H.read_text(), E: E.read_text(), C: C.read_text()}
try:
    for name, edits in MUTATIONS.items():
        if only and name.split()[0] not in only:
            continue
        texts = dict(originals)
        for path, old, new in edits:
            n = texts[path].count(old)
            assert n == 1, f"{name}: expected 1 match, found {n}: {old!r}"
            texts[path] = texts[path].replace(old, new)
        for path, t in texts.items():
            path.write_text(t)
        r = subprocess.run(["go", "test", "-count=1", "-timeout=300s", "./internal/httpapi/"],
                           cwd=GW, capture_output=True, text=True)
        failed = sorted(set(re.findall(r"--- FAIL: (Test\w+)", r.stdout)))
        build = "build failed" in r.stdout or "[setup failed]" in r.stdout or r.returncode not in (0, 1)
        verdict = "CAUGHT" if failed else ("BUILD ERROR" if r.returncode else "NOT CAUGHT")
        print(f"{name}\n  {verdict}: {', '.join(failed) if failed else ''}")
        if verdict == "BUILD ERROR":
            print(r.stdout[-1500:], r.stderr[-1500:])
        for path, t in originals.items():
            path.write_text(t)
finally:
    for path, t in originals.items():
        path.write_text(t)
