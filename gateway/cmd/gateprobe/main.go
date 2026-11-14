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
//
// Two more modes, for item 6.0a (docs/work/2026-11-13-tier2-scope-by-evidence/), both citable: no:
//
//	gateprobe -routing <requests.jsonl> <workload.json>
//	    Offline, no model. For every logged retrieval of a policy-gold question (its gold evidence is one
//	    policy document), the policy namespace by the old top-chunk rule (the first policy chunk's document)
//	    and by the vote (reuse.Namespace, ADR-028), each compared with the gold document. It prints the
//	    two counts and exits 1 when the vote is correct for fewer questions than the top chunk.
//	gateprobe -embedcheck <vectors.json> <n>
//	    Loads the embedding model. Embeds n stored workload questions through the gateway's own client
//	    (embed.Client.Query) and prints the cosine against the stored vector, by qa_id and never the
//	    text. It exits 1 when any cosine is under 0.9999: tau_P was calibrated on the stored vectors, so
//	    they must be the vectors the gateway computes.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math"
	"os"
	"sort"
	"strings"

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
	routing := flag.Bool("routing", false, "item 6.0a: top-chunk against vote routing, offline: -routing <requests.jsonl> <workload.json>")
	embedcheck := flag.Bool("embedcheck", false, "item 6.0a: gateway embedding against the stored vector: -embedcheck <vectors.json> <n>")
	flag.Parse()
	switch {
	case *routing && *embedcheck:
		log.Fatal("gateprobe: -routing and -embedcheck are two modes; pick one")
	case *routing:
		os.Exit(runRouting(flag.Args()))
	case *embedcheck:
		os.Exit(runEmbedCheck(flag.Args()))
	}
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

// ---------------------------------------------------------------------------------------------------
// -routing (item 6.0a, done condition 5)
// ---------------------------------------------------------------------------------------------------

// routingRecord is the part of a raw/requests.jsonl record this mode reads.
type routingRecord struct {
	QueryRaw          string   `json:"query_raw"`
	RetrievedChunkIDs []string `json:"retrieved_chunk_ids"`
}

// workloadQuery is the part of a workload record this mode reads.
type workloadQuery struct {
	QAID     string   `json:"qa_id"`
	Question string   `json:"question"`
	DocIDs   []string `json:"doc_ids"`
}

// topChunkPolicyDoc is the old POLICY namespace rule of ADR-024, kept here only to be compared: the
// document of the highest-ranked policy chunk. reuse.Namespace no longer does this (ADR-028).
func topChunkPolicyDoc(chunkIDs []string) string {
	for _, id := range chunkIDs {
		if strings.HasPrefix(id, "policy-") {
			if i := strings.IndexByte(id, '#'); i >= 0 {
				return id[:i]
			}
			return id
		}
	}
	return ""
}

// routingCounts are the numbers -routing prints.
type routingCounts struct {
	Questions   int // policy-gold questions with a logged retrieval
	NoRetrieval int // policy-gold questions whose record has no retrieval (a Tier-1 hit): not counted
	TopCorrect  int
	VoteCorrect int
	VoteOnly    int // vote right, top chunk wrong
	TopOnly     int // top chunk right, vote wrong
}

// countRouting applies both rules to every record that matches a policy-gold question. A question is
// policy-gold when its gold evidence is exactly one document and that document is a policy. A rule is
// correct when the policy document it names is the gold document; a retrieval with no policy chunk names
// "" and is wrong for both.
func countRouting(records []routingRecord, workload []workloadQuery) routingCounts {
	gold := make(map[string]string)
	for _, q := range workload {
		if len(q.DocIDs) == 1 && strings.HasPrefix(q.DocIDs[0], "policy-") {
			gold[q.Question] = q.DocIDs[0]
		}
	}
	var c routingCounts
	for _, r := range records {
		doc, ok := gold[r.QueryRaw]
		if !ok {
			continue
		}
		if len(r.RetrievedChunkIDs) == 0 {
			c.NoRetrieval++
			continue
		}
		c.Questions++
		top := topChunkPolicyDoc(r.RetrievedChunkIDs) == doc
		// The product is "": with no product the POLICY namespace is the policy document alone, which is
		// what the vote picks (reuse.Namespace, ADR-028).
		vote := reuse.Namespace(reuse.LanePolicy, r.RetrievedChunkIDs, "") == doc
		if top {
			c.TopCorrect++
		}
		if vote {
			c.VoteCorrect++
		}
		switch {
		case vote && !top:
			c.VoteOnly++
		case top && !vote:
			c.TopOnly++
		}
	}
	return c
}

func runRouting(args []string) int {
	if len(args) != 2 {
		log.Print("usage: gateprobe -routing <requests.jsonl> <workload.json>")
		return 2
	}
	f, err := os.Open(args[0])
	if err != nil {
		log.Printf("gateprobe: %v", err)
		return 1
	}
	defer f.Close()
	var records []routingRecord
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1<<20), 16<<20)
	for sc.Scan() {
		if strings.TrimSpace(sc.Text()) == "" {
			continue
		}
		var r routingRecord
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			log.Printf("gateprobe: %s: %v", args[0], err)
			return 1
		}
		records = append(records, r)
	}
	if err := sc.Err(); err != nil {
		log.Printf("gateprobe: %v", err)
		return 1
	}
	blob, err := os.ReadFile(args[1])
	if err != nil {
		log.Printf("gateprobe: %v", err)
		return 1
	}
	var workload []workloadQuery
	if err := json.Unmarshal(blob, &workload); err != nil {
		log.Printf("gateprobe: %s: %v", args[1], err)
		return 1
	}

	c := countRouting(records, workload)
	if c.Questions == 0 {
		log.Print("gateprobe: no policy-gold question has a logged retrieval; nothing to compare")
		return 1
	}
	fmt.Printf("routing: %d policy-gold questions with a logged retrieval (%d more have none)\n", c.Questions, c.NoRetrieval)
	fmt.Printf("  top-chunk rule correct: %d\n", c.TopCorrect)
	fmt.Printf("  vote correct:           %d\n", c.VoteCorrect)
	fmt.Printf("  vote right and top wrong: %d; top right and vote wrong: %d\n", c.VoteOnly, c.TopOnly)
	if c.VoteCorrect < c.TopCorrect {
		fmt.Println("routing: FAIL, the vote is correct for fewer questions than the top chunk")
		return 1
	}
	fmt.Println("routing: PASS, vote-correct >= top-chunk-correct")
	return 0
}

// ---------------------------------------------------------------------------------------------------
// -embedcheck (item 6.0a, done condition 10)
// ---------------------------------------------------------------------------------------------------

// embedMinCosine is the least cosine between a stored vector and the gateway's own embedding of the same
// question that still counts as the same vector (float32 rounding and the HTTP round trip only).
const embedMinCosine = 0.9999

func runEmbedCheck(args []string) int {
	if len(args) != 2 {
		log.Print("usage: gateprobe -embedcheck <vectors.json> <n>")
		return 2
	}
	var n int
	if _, err := fmt.Sscanf(args[1], "%d", &n); err != nil || n < 1 {
		log.Printf("gateprobe: n=%q is not a positive integer", args[1])
		return 2
	}
	blob, err := os.ReadFile(args[0])
	if err != nil {
		log.Printf("gateprobe: %v", err)
		return 1
	}
	var stored map[string]struct {
		Question string    `json:"question"`
		Vector   []float32 `json:"vector"`
	}
	if err := json.Unmarshal(blob, &stored); err != nil {
		log.Printf("gateprobe: %s: %v", args[0], err)
		return 1
	}
	ids := make([]string, 0, len(stored))
	for id := range stored {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	if len(ids) == 0 {
		log.Print("gateprobe: the vectors file is empty")
		return 1
	}
	if n > len(ids) {
		n = len(ids)
	}

	ollamaURL := os.Getenv("OLLAMA_BASE_URL")
	if ollamaURL == "" {
		ollamaURL = "http://localhost:11434"
	}
	emb := embed.New(ollamaURL, embed.Model)
	bad := 0
	for k := 0; k < n; k++ {
		// n ids spread over the sorted list, so three checks do not all come from one product.
		id := ids[k*len(ids)/n]
		got, err := emb.Query(context.Background(), stored[id].Question)
		if err != nil {
			log.Printf("gateprobe: embedding %s: %v", id, err)
			return 1
		}
		if len(got) != len(stored[id].Vector) {
			log.Printf("gateprobe: %s: the gateway's vector has %d dims, the stored one %d", id, len(got), len(stored[id].Vector))
			return 1
		}
		cos := cosine(got, stored[id].Vector)
		verdict := "ok"
		if cos < embedMinCosine {
			verdict = "TOO LOW"
			bad++
		}
		fmt.Printf("embedcheck: %s cosine %.6f %s\n", id, cos, verdict)
	}
	if bad > 0 {
		fmt.Printf("embedcheck: FAIL, %d of %d under %.4f\n", bad, n, embedMinCosine)
		return 1
	}
	fmt.Printf("embedcheck: PASS, %d of %d at or over %.4f\n", n, n, embedMinCosine)
	return 0
}
