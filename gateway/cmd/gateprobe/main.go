// Command gateprobe runs the gateway's own Tier-2 decision offline over a file of question pairs, for
// docs/work/2026-10-31-rag-correctness/plan.md §3.1 (the generator's prompt). citable: no. It is never on
// the request path, and nothing imports it.
//
// One input line is one pair: the FIRST question's retrieval and its answer under each prompt arm, and the
// SECOND question's retrieval with its evidence text. For each arm it gives the cause the cascade
// (httpapi/cascade.go, tryTier2) would give the second question if the first question's entry were the
// only entry in the cache:
//
//   - the entry's lane and namespace come from the first question's chunks, as the miss path writes them
//     (httpapi/handler.go), and the query's from the second question's chunks;
//   - tryTier2's two guards run first: no chunk, then an empty namespace, each a MISS with no cause;
//   - then reuse.Thresholds.DecideLane, and Judge with the gate on: namespace, similarity, both arms.
//
// The similarity is the cosine of the two questions' embeddings from embed.Client, the gateway's own
// query embedding. Redis computes it as 1 - COSINE distance over the same float32 vectors
// (cache/tier2.go), so the two can differ only in the last float32 digits, which matters only on tau
// itself. A namespace mismatch comes back as NAMESPACE, where the gateway's scoped search would not find
// the entry at all; either way the pair is not served.
//
// Both support arms are also scored on every pair, whatever tau says (support_* fields), so the prompt's
// effect on support can be read apart from tau. They are never a serve decision: served is Judge's.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"log"
	"math"
	"os"

	"github.com/hung/thesis/gateway/internal/embed"
	"github.com/hung/thesis/gateway/internal/reuse"
)

type pair struct {
	Kind     string            `json:"kind"`
	FirstID  string            `json:"first_id"`
	SecondID string            `json:"second_id"`
	Q1       string            `json:"q1"`
	PID1     string            `json:"pid1"`
	Chunks1  []string          `json:"chunks1"`
	Answers  map[string]string `json:"answers"` // prompt arm -> the first question's answer
	Q2       string            `json:"q2"`
	PID2     string            `json:"pid2"`
	Chunks2  []string          `json:"chunks2"`
	Texts2   []string          `json:"texts2"`
}

type armResult struct {
	Cause            string  `json:"cause"`
	Served           bool    `json:"served"`
	SupportScored    bool    `json:"support_scored"`
	SupportAdmits    bool    `json:"support_admits"`
	SupportLex       float64 `json:"support_lex"`
	SupportNumericOK bool    `json:"support_numeric_ok"`
}

// result holds IDs and numbers only: question and chunk text stay in the input file.
type result struct {
	Kind       string               `json:"kind"`
	FirstID    string               `json:"first_id"`
	SecondID   string               `json:"second_id"`
	Similarity float64              `json:"similarity"`
	EntryLane  string               `json:"entry_lane"`
	EntryNS    string               `json:"entry_ns"`
	QueryLane  string               `json:"query_lane"`
	QueryNS    string               `json:"query_ns"`
	Arms       map[string]armResult `json:"arms"`
}

func main() {
	in := flag.String("in", "", "pairs file, one JSON pair per line")
	out := flag.String("out", "", "results file to create, one JSON result per line; never overwritten")
	tau := flag.Float64("tau", 0.85, "similarity floor (the gateway's REUSE_TAU default)")
	flag.Parse()
	if *in == "" || *out == "" {
		log.Fatal("gateprobe: -in and -out are required")
	}

	ollamaURL := os.Getenv("OLLAMA_BASE_URL")
	if ollamaURL == "" {
		ollamaURL = "http://localhost:11434"
	}
	emb := embed.New(ollamaURL, embed.Model)
	// The gateway's default band: MIXED off (ADR-016), as cmd/gateway's bandFromEnv gives when unset.
	band := reuse.LaneBand{Lo: reuse.PinnedLo, Hi: reuse.PinnedLo}
	t := reuse.Thresholds{Tau: *tau}

	f, err := os.Open(*in)
	if err != nil {
		log.Fatalf("gateprobe: %v", err)
	}
	defer f.Close()
	w, err := os.OpenFile(*out, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o644)
	if err != nil {
		log.Fatalf("gateprobe: %v", err)
	}
	enc := json.NewEncoder(w)

	ctx := context.Background()
	vecs := map[string][]float32{}
	vec := func(q string) []float32 {
		if v, ok := vecs[q]; ok {
			return v
		}
		v, err := emb.Query(ctx, q)
		if err != nil {
			log.Fatalf("gateprobe: %v", err)
		}
		vecs[q] = v
		return v
	}

	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1<<20), 16<<20)
	n := 0
	for sc.Scan() {
		var p pair
		if err := json.Unmarshal(sc.Bytes(), &p); err != nil {
			log.Fatalf("gateprobe: line %d: %v", n+1, err)
		}
		// The seam's alignment rule (interfaces.md §B): texts[i] is chunk_ids[i]'s text. A shifted array
		// would score support against the wrong chunks with no error.
		if len(p.Texts2) != len(p.Chunks2) {
			log.Fatalf("gateprobe: pair %s: %d chunk IDs but %d texts", p.SecondID, len(p.Chunks2), len(p.Texts2))
		}
		if err := enc.Encode(judgePair(t, band, p, cosine(vec(p.Q1), vec(p.Q2)))); err != nil {
			log.Fatalf("gateprobe: %v", err)
		}
		n++
	}
	if err := sc.Err(); err != nil {
		log.Fatalf("gateprobe: %v", err)
	}
	if err := w.Close(); err != nil {
		log.Fatalf("gateprobe: %v", err)
	}
	log.Printf("gateprobe: %d pairs judged at tau=%.2f -> %s", n, *tau, *out)
}

func judgePair(t reuse.Thresholds, band reuse.LaneBand, p pair, sim float64) result {
	entryLane := reuse.Classify(p.Chunks1, band)
	r := result{
		Kind: p.Kind, FirstID: p.FirstID, SecondID: p.SecondID, Similarity: sim,
		EntryLane: string(entryLane), EntryNS: reuse.Namespace(entryLane, p.Chunks1, p.PID1),
		Arms: make(map[string]armResult, len(p.Answers)),
	}
	queryLane := reuse.Classify(p.Chunks2, band)
	if len(p.Chunks2) > 0 {
		r.QueryLane, r.QueryNS = string(queryLane), reuse.Namespace(queryLane, p.Chunks2, p.PID2)
	}
	for arm, answer := range p.Answers {
		sr := reuse.CheckSupport(answer, p.Texts2, p.Chunks2)
		a := armResult{
			SupportScored:    sr.Scored(),
			SupportAdmits:    sr.Scored() && !sr.Refuses(),
			SupportLex:       sr.Lex.Score,
			SupportNumericOK: sr.Numeric.Admits(),
		}
		switch {
		case len(p.Chunks2) == 0:
			a.Cause = "NO_CHUNKS"
		case r.QueryNS == "":
			a.Cause = "NO_NAMESPACE"
		default:
			d := t.DecideLane(reuse.LaneInput{
				Similarity: sim,
				QueryLane:  queryLane,
				QueryNS:    r.QueryNS,
				EntryLane:  entryLane,
				EntryNS:    r.EntryNS,
			})
			j := t.Judge(reuse.GateOn, d, sim, answer, p.Texts2, p.Chunks2)
			a.Cause, a.Served = j.Cause, j.Served()
		}
		r.Arms[arm] = a
	}
	return r
}

// cosine stops on a zero vector rather than return NaN: encoding/json cannot write NaN, and an all-zero
// embedding is a defect, not a similarity.
func cosine(a, b []float32) float64 {
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		log.Fatal("gateprobe: a zero embedding vector")
	}
	return dot / (math.Sqrt(na) * math.Sqrt(nb))
}
