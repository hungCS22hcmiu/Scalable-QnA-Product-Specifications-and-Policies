package ragclient_test

// Plan step 1 of item 2.3 (docs/work/2026-10-14-refusal-cause-code/plan.md, design.md 10): the support
// gate scored on answers the system REALLY generated, before the gate is wired into anything served.
//
// What it does. For each question in the frozen file sample-questions.md it runs Retrieve and Answer
// through the real ragclient (so the LLM generates), then scores the answer with SupportLexical and
// SupportNumeric against (a) its own retrieval, and for parts (b) and (c) against the retrieval of
// the second question of the pair. It prints one JSON row per score, prefixed "SAMPLE ", and a
// summary. It ASSERTS NOTHING ABOUT THE VERDICTS: the numbers are logged, never pinned, and no rule
// is edited because of them (tau_s = 0.6, the stopwords, the tokenizer, the numeric rules and the
// unit list all stay as they are).
//
// What a pass means. The frozen file was the one hashed in approvals.md, every question was
// answered, and every row was scored. It says nothing about whether the gate is any good: n is 16,
// 5 and 6, a go/no-go check and not an estimate.
//
// It needs a running rag.server, Redis and the LLM, so it is skipped unless RAG_SEAM_ADDR is set,
// and unless RAG_SAMPLE=1 as well: generation loads the LLM, and the Phase 2 rule is to read
// `sysctl kern.memorystatus_vm_pressure_level` first. Output is NOT citable (dev-v0). Run:
//
//	RAG_SEAM_ADDR=127.0.0.1:50052 RAG_SAMPLE=1 go test -count=1 -timeout 30m -v \
//	  -run '^TestSupportSample$' ./internal/ragclient/
//
// The generation is at temperature 1 (U8), so a second run gives different answers. The first run
// is the sample; a rerun is a new sample and is recorded as one.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/hung/thesis/gateway/internal/ragclient"
	"github.com/hung/thesis/gateway/internal/reuse"
)

// sampleQuestionsSHA256 is the hash recorded in approvals.md (step 1a) before any answer existed.
const sampleQuestionsSHA256 = "93bc8f43f239b1819ab3d641fa53501bdf2e3e9766a3a9d613f675974ebdc033"

const sampleQuestionsPath = "../../../docs/work/2026-10-14-refusal-cause-code/sample-questions.md"

// sampleBand is the gateway's default lane band (cmd/gateway/main.go: LANE_SIGMA = LANE_SIGMA_HI =
// 0.20, collapsed). The lane is only REPORTED here.
var sampleBand = reuse.LaneBand{Lo: 0.20, Hi: 0.20}

type sampleRow struct {
	Part, ID, Kind                  string
	Question, ProductID             string // the question answered
	EvidenceQuestion, EvidenceProd  string // the question whose retrieval is the evidence ("" = its own)
	YesNo                           bool
	Lane, Namespace                 string // of the evidence retrieval
	AnswerNamespace                 string // of the answered question's own retrieval
	SameNamespace                   bool
	EvidenceChunks                  []string
	Answer                          string
	LexScore                        float64
	LexContentTokens                int
	LexRefuses, LexScored           bool
	NumNumbers, NumUnsupported      int
	NumUnreadable, NumUnitless      int
	NumRefuses, NumScored           bool
	NumericRefusesWhereLexicalAdmit bool
}

// parseSampleFile reads the three markdown tables of sample-questions.md. A row is a line whose first
// cell is an id such as a01, b3 or c2.
func parseSampleFile(t *testing.T, raw string) (a, b, c [][]string) {
	t.Helper()
	for line := range strings.SplitSeq(raw, "\n") {
		if !strings.HasPrefix(line, "| ") {
			continue
		}
		// Strip ONE pipe at each end, not a cutset: a row may end in an empty cell (the yn column),
		// and trimming "| " off the end would swallow it.
		cells := strings.Split(strings.TrimSuffix(strings.TrimPrefix(strings.TrimSpace(line), "|"), "|"), "|")
		for i := range cells {
			cells[i] = strings.TrimSpace(cells[i])
		}
		if len(cells) < 2 || len(cells[0]) < 2 {
			continue
		}
		switch cells[0][0] {
		case 'a':
			if len(cells) == 5 {
				a = append(a, cells)
			}
		case 'b':
			if len(cells) == 3 {
				b = append(b, cells)
			}
		case 'c':
			if len(cells) == 6 {
				c = append(c, cells)
			}
		}
	}
	return a, b, c
}

func noneToEmpty(s string) string {
	if s == "none" {
		return ""
	}
	return s
}

func TestSupportSample(t *testing.T) {
	addr := os.Getenv("RAG_SEAM_ADDR")
	if addr == "" || os.Getenv("RAG_SAMPLE") != "1" {
		t.Skip("set RAG_SEAM_ADDR and RAG_SAMPLE=1 (this loads the LLM; read the memory pressure first)")
	}

	raw, err := os.ReadFile(sampleQuestionsPath)
	if err != nil {
		t.Fatalf("reading the frozen question file: %v", err)
	}
	sum := sha256.Sum256(raw)
	if got := hex.EncodeToString(sum[:]); got != sampleQuestionsSHA256 {
		t.Fatalf("sample-questions.md sha256 %s, want %s: the questions were changed after they were frozen", got, sampleQuestionsSHA256)
	}
	a, b, c := parseSampleFile(t, string(raw))
	if len(a) != 16 || len(b) != 5 || len(c) != 6 {
		t.Fatalf("parsed %d, %d and %d rows; the frozen file has 16, 5 and 6", len(a), len(b), len(c))
	}

	rag, err := ragclient.New(addr)
	if err != nil {
		t.Fatalf("ragclient.New(%s): %v", addr, err)
	}
	t.Cleanup(func() { _ = rag.Close() })

	type answered struct {
		ret *ragclient.RetrieveResult
		ans string
	}
	generate := func(q, pid string) answered {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()
		ret, err := rag.Retrieve(ctx, q, 0, pid)
		if err != nil {
			t.Fatalf("Retrieve(%q): %v", q, err)
		}
		if len(ret.ChunkIDs) == 0 || len(ret.Texts) != len(ret.ChunkIDs) {
			t.Fatalf("Retrieve(%q): %d chunks, %d texts: the sample needs evidence text", q, len(ret.ChunkIDs), len(ret.Texts))
		}
		ans, err := rag.Answer(ctx, q, 0, ret.ChunkIDs, pid)
		if err != nil {
			t.Fatalf("Answer(%q): %v", q, err)
		}
		return answered{ret: ret, ans: ans.Text}
	}
	retrieve := func(q, pid string) *ragclient.RetrieveResult {
		ctx, cancel := context.WithTimeout(context.Background(), time.Minute)
		defer cancel()
		ret, err := rag.Retrieve(ctx, q, 0, pid)
		if err != nil {
			t.Fatalf("Retrieve(%q): %v", q, err)
		}
		if len(ret.ChunkIDs) == 0 || len(ret.Texts) != len(ret.ChunkIDs) {
			t.Fatalf("Retrieve(%q): %d chunks, %d texts", q, len(ret.ChunkIDs), len(ret.Texts))
		}
		return ret
	}
	score := func(row sampleRow, ans string, ev *ragclient.RetrieveResult, own *ragclient.RetrieveResult) sampleRow {
		lane := reuse.Classify(ev.ChunkIDs, sampleBand)
		row.Lane = string(lane)
		row.Namespace = reuse.Namespace(lane, ev.ChunkIDs, row.EvidenceProd)
		ownLane := reuse.Classify(own.ChunkIDs, sampleBand)
		row.AnswerNamespace = reuse.Namespace(ownLane, own.ChunkIDs, row.ProductID)
		row.SameNamespace = row.Namespace != "" && row.Namespace == row.AnswerNamespace
		row.EvidenceChunks = ev.ChunkIDs
		row.Answer = ans
		lex := reuse.SupportLexical(ans, ev.Texts, ev.ChunkIDs)
		num := reuse.SupportNumeric(ans, ev.Texts, ev.ChunkIDs)
		row.LexScored, row.LexScore, row.LexContentTokens, row.LexRefuses = lex.Scored, lex.Score, lex.ContentTokenCount, lex.Refuses()
		row.NumScored, row.NumNumbers, row.NumUnsupported = num.Scored, num.Numbers, num.Unsupported
		row.NumUnreadable, row.NumUnitless, row.NumRefuses = num.Unreadable, num.Unitless, num.Refuses()
		row.NumericRefusesWhereLexicalAdmit = num.Refuses() && !lex.Refuses()
		return row
	}

	var rows []sampleRow
	emit := func(r sampleRow) {
		rows = append(rows, r)
		j, _ := json.Marshal(r)
		t.Logf("SAMPLE %s", j)
	}

	// Part (a): the answer against its own retrieval.
	for _, r := range a {
		id, q, pid, yn := r[0], r[1], noneToEmpty(r[2]), r[4] == "yn"
		g := generate(q, pid)
		emit(score(sampleRow{Part: "a", ID: id, Kind: "own", Question: q, ProductID: pid, EvidenceProd: pid, YesNo: yn}, g.ans, g.ret, g.ret))
	}
	// Part (b): own retrieval (floor), then the paraphrase's retrieval (the reuse case).
	for _, r := range b {
		id, q, p := r[0], r[1], r[2]
		g := generate(q, "")
		emit(score(sampleRow{Part: "b", ID: id, Kind: "own", Question: q}, g.ans, g.ret, g.ret))
		emit(score(sampleRow{Part: "b", ID: id, Kind: "paraphrase", Question: q, EvidenceQuestion: p}, g.ans, retrieve(p, ""), g.ret))
	}
	// Part (c): the answer to q against the retrieval of p, whose correct answer differs.
	for _, r := range c {
		id, kind, q, qpid, p, ppid := r[0], r[1], r[2], noneToEmpty(r[3]), r[4], noneToEmpty(r[5])
		yn := strings.Contains(kind, "yn")
		g := generate(q, qpid)
		emit(score(sampleRow{Part: "c", ID: id, Kind: kind, Question: q, ProductID: qpid, EvidenceQuestion: p, EvidenceProd: ppid, YesNo: yn},
			g.ans, retrieve(p, ppid), g.ret))
	}

	// The summary: counts only, nothing judged.
	var below, numRef, numNotLex, yn, ynBelow int
	var scores []float64
	for _, r := range rows {
		if r.Part == "c" || (r.Part == "b" && r.Kind == "paraphrase") {
			continue
		}
		scores = append(scores, r.LexScore)
		if r.LexRefuses {
			below++
		}
		if r.NumRefuses {
			numRef++
		}
		if r.NumericRefusesWhereLexicalAdmit {
			numNotLex++
		}
		if r.YesNo {
			yn++
			if r.LexRefuses {
				ynBelow++
			}
		}
	}
	sort.Float64s(scores)
	t.Logf("SUMMARY floor rows=%d S_lex sorted=%v below_0.6=%d numeric_refuses=%d numeric_refuses_lexical_admits=%d yesno=%d yesno_below_0.6=%d",
		len(scores), scores, below, numRef, numNotLex, yn, ynBelow)
	var reuseRows, reuseLex, reuseNum int
	for _, r := range rows {
		if r.Part == "b" && r.Kind == "paraphrase" {
			reuseRows++
			if r.LexRefuses {
				reuseLex++
			}
			if r.NumRefuses {
				reuseNum++
			}
		}
	}
	t.Logf("SUMMARY reuse(b) pairs=%d lexical_refuses=%d numeric_refuses=%d", reuseRows, reuseLex, reuseNum)
	for _, r := range rows {
		if r.Part == "c" {
			t.Logf("SUMMARY negative %s kind=%q same_namespace=%v lexical_refuses=%v numeric_refuses=%v", r.ID, r.Kind, r.SameNamespace, r.LexRefuses, r.NumRefuses)
		}
	}
	if len(rows) != 16+10+6 {
		t.Fatalf("%d rows scored, want 32", len(rows))
	}
}
